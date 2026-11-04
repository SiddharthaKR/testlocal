"""
Logging pass-through proxy for OpenAI-compatible endpoints (stdlib only).

  $PYTHON harness/proxy/llm_proxy.py --run-dir runs/<id> [--port N] [--upstream URL]

Defaults for port/upstream come from config/env.yaml. Per request it appends
one JSON line to <run-dir>/requests.jsonl and saves the body to
<run-dir>/requests/<n>.json. Handles SSE streaming and non-streaming.
"""
import argparse
import http.client
import itertools
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-length",
               "host", "accept-encoding", "proxy-connection", "upgrade", "te"}


def est_tokens(chars):
    return max(1, chars // 4) if chars else 0


def message_chars(body):
    return len(json.dumps(body.get("messages", []), ensure_ascii=False))


def count_hints(body):
    n = 0
    for m in body.get("messages", []):
        if m.get("role") != "user":
            continue
        c = m.get("content")
        texts = [c] if isinstance(c, str) else [p.get("text", "") for p in (c or []) if isinstance(p, dict)]
        # opencode run wraps the CLI message in quotes: '"HINT: ..."'
        n += any(t.lstrip().lstrip("\"'").startswith("HINT:") for t in texts)
    return n


def delta_chars(chunk):
    n = 0
    for ch in chunk.get("choices", []):
        d = ch.get("delta") or ch.get("message") or {}
        n += len(d.get("content") or "") + len(d.get("reasoning_content") or d.get("reasoning") or "")
        for tc in d.get("tool_calls") or []:
            f = tc.get("function") or {}
            n += len(f.get("name") or "") + len(f.get("arguments") or "")
    return n


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = None        # urllib.parse result
    run_dir = None
    lock = threading.Lock()
    counter = itertools.count(1)

    def log_message(self, fmt, *args):  # quiet default access log
        pass

    def do_GET(self):
        self._forward(None)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self._forward(raw)

    def _target_path(self):
        # client baseURL is http://localhost:PORT/v1; upstream path already ends with /v1
        base = self.upstream.path.rstrip("/")
        p = self.path
        if base and p.startswith("/v1"):
            p = p[3:]
        return base + p

    def _forward(self, raw):
        body, is_chat = None, False
        if raw:
            try:
                body = json.loads(raw)
                is_chat = isinstance(body, dict) and "messages" in body
            except ValueError:
                pass
        stream = bool(is_chat and body.get("stream"))
        if stream:
            body.setdefault("stream_options", {})["include_usage"] = True
            raw = json.dumps(body).encode()

        rec = {"n": None, "path": self.path, "t_start": time.time(), "t_first_token": None,
               "t_end": None, "prompt_tokens": None, "completion_tokens": None,
               "usage_estimated": False, "n_messages": len(body["messages"]) if is_chat else 0,
               "n_hints": count_hints(body) if is_chat else 0, "stream": stream,
               "model": body.get("model") if is_chat else None, "status": None}
        if is_chat:
            rec["n"] = next(self.counter)
            (self.run_dir / "requests").mkdir(parents=True, exist_ok=True)
            (self.run_dir / "requests" / f"{rec['n']:05d}.json").write_bytes(raw)

        cls = http.client.HTTPSConnection if self.upstream.scheme == "https" else http.client.HTTPConnection
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
        if raw is not None:
            headers["Content-Length"] = str(len(raw))
        # hosted APIs (e.g. Google AI Studio) rate-limit: retry 429/503 with backoff before answering
        rec["retries"] = 0
        for attempt in range(6):
            conn = cls(self.upstream.hostname, self.upstream.port, timeout=600)
            try:
                conn.request(self.command, self._target_path(), body=raw, headers=headers)
                resp = conn.getresponse()
            except OSError as e:
                rec["status"] = f"upstream_error: {e}"
                self.send_error(502, str(e))
                self._log(rec, is_chat)
                return
            if resp.status not in (429, 503) or attempt == 5:
                break
            wait = float(resp.getheader("Retry-After") or 0) or min(60, 5 * 2 ** attempt)
            resp.read(); conn.close()
            rec["retries"] += 1
            time.sleep(wait)

        rec["status"] = resp.status
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in HOP_HEADERS:
                self.send_header(k, v)

        out_chars, usage = 0, None
        if stream and resp.status == 200:
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for line in resp:  # SSE is line-delimited
                    s = line.strip()
                    if s.startswith(b"data:") and s[5:].strip() not in (b"", b"[DONE]"):
                        try:
                            chunk = json.loads(s[5:])
                            c = delta_chars(chunk)
                            if c and rec["t_first_token"] is None:
                                rec["t_first_token"] = time.time()
                            out_chars += c
                            usage = chunk.get("usage") or usage
                        except ValueError:
                            pass
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(line), line))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                rec["status"] = "client_disconnected"
        else:
            data = resp.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            rec["t_first_token"] = time.time()
            if is_chat:
                try:
                    j = json.loads(data)
                    usage = j.get("usage")
                    out_chars = delta_chars(j)
                except ValueError:
                    pass
        conn.close()

        if is_chat:
            if usage and usage.get("prompt_tokens") is not None:
                rec["prompt_tokens"] = usage.get("prompt_tokens")
                rec["completion_tokens"] = usage.get("completion_tokens")
                # AI Studio Gemma reports completion_tokens=0; the real count is total - prompt
                if not rec["completion_tokens"] and (usage.get("total_tokens") or 0) > rec["prompt_tokens"]:
                    rec["completion_tokens"] = usage["total_tokens"] - rec["prompt_tokens"]
            else:
                rec["usage_estimated"] = True
                rec["prompt_tokens"] = est_tokens(message_chars(body))
                rec["completion_tokens"] = est_tokens(out_chars)
        self._log(rec, is_chat)

    def _log(self, rec, is_chat):
        rec["t_end"] = time.time()
        if not is_chat:
            return
        with self.lock, open(self.run_dir / "requests.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


class QuietServer(ThreadingHTTPServer):
    """opencode closing a keep-alive connection is normal: log one line instead of a traceback."""
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys as _sys
        err = _sys.exc_info()[1]
        if isinstance(err, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            print(f"client {client_address[0]}:{client_address[1]} disconnected", flush=True)
        else:
            super().handle_error(request, client_address)


def main():
    env = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--port", type=int, default=env["proxy_port"])
    ap.add_argument("--upstream", default=env["upstream_url"])
    a = ap.parse_args()
    Proxy.upstream = urllib.parse.urlparse(a.upstream)
    Proxy.run_dir = Path(a.run_dir).resolve()
    Proxy.run_dir.mkdir(parents=True, exist_ok=True)
    srv = QuietServer(("127.0.0.1", a.port), Proxy)
    print(f"llm_proxy: 127.0.0.1:{a.port} -> {a.upstream}  log={Proxy.run_dir}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
