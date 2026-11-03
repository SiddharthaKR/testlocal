"""
Compare runs side by side (steps, tool calls, compile fails/fixes, truncation, compaction, speed).

  compare_runs.py --label 32k <run_dir>... --label 64k <run_dir>... [--out PREFIX]

Prints a markdown table; with --out writes PREFIX.md and PREFIX.json.
"""
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path


def load_jsonl(p):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def text_of(m):
    c = m.get("content")
    return c if isinstance(c, str) else json.dumps(c) if c else ""


def compile_events(body):
    """Ordered list of True (ok) / False (fail) from shell/execute tool results."""
    names, ev = {}, []
    for m in body["messages"]:
        if m["role"] == "assistant":
            for tc in m.get("tool_calls") or []:
                names[tc["id"]] = tc["function"]["name"]
        elif m["role"] == "tool" and names.get(m.get("tool_call_id")) in ("shell", "execute"):
            t = text_of(m)
            if "COMPILE: FAIL" in t or "EQUIV: COMPILE FAIL" in t:
                ev.append(False)
            elif "COMPILE: OK" in t or re.search(r"EQUIV:?\s+(PASS|FAIL)", t):
                ev.append(True)
    return ev


def med(xs):
    return round(statistics.median(xs), 1) if xs else None


def analyze(run):
    run = Path(run)
    meta, judge = load_json(run / "run_meta.json"), load_json(run / "judge.json")
    reqs = load_jsonl(run / "requests.jsonl")
    limit = meta.get("context_limit") or 0
    track = meta.get("track")
    out = dict(run=run.name, track=track, assist=bool(meta.get("assist")), model=meta.get("model"),
               context_limit=limit, steps=len(reqs), agent_min=round((meta.get("wall_seconds") or 0) / 60, 1))
    if track == "C":
        out["result"] = f"found {judge.get('found')}/{judge.get('n_bugs')}, FP {judge.get('false_positives')}"
    else:
        out["result"] = judge.get("status")

    # sizes of request bodies, keyed by request n (file NNNNN.json)
    sizes = {}
    for r in reqs:
        p = run / "requests" / f"{r['n']:05d}.json"
        if p.exists():
            sizes[r["n"]] = p.stat().st_size
    body = None
    if sizes:
        big = max(sizes, key=lambda k: (sizes[k], k))
        body = json.loads((run / "requests" / f"{big:05d}.json").read_text(encoding="utf-8"))

    # tool calls
    names = Counter()
    if body:
        for m in body["messages"]:
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    names[tc["function"]["name"]] += 1
    out["tool_calls"] = sum(names.values())
    out["tool_counts"] = dict(names.most_common())

    # compile
    ev = compile_events(body) if body else []
    out["n_compile_fail"] = ev.count(False)
    out["n_compile_ok"] = ev.count(True)
    out["fixes"] = sum(1 for a, b in zip(ev, ev[1:]) if a is False and b is True)
    out["final_compile_ok"] = ev[-1] if ev else None

    # truncation / compaction
    trunc, compact = [], []
    prev = None
    for r in reqs:
        if prev:
            pt, ps = prev.get("prompt_tokens"), sizes.get(prev["n"])
            ct, cs = r.get("prompt_tokens"), sizes.get(r["n"])
            if None not in (pt, ct, ps, cs) and ct < pt and cs > ps:
                trunc.append(dict(request=r["n"], prompt_tokens=f"{pt}->{ct}"))
            if r.get("n_messages") is not None and prev.get("n_messages") is not None \
                    and r["n_messages"] < prev["n_messages"]:
                compact.append(r["n"])
        prev = r
    near = [r["n"] for r in reqs if limit and (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0) >= 0.98 * limit]
    out["truncation"] = trunc
    out["near_limit"] = near
    out["truncation_suspected"] = bool(trunc or near)
    for r in reqs:  # summarization prompt in the last user/system message
        p = run / "requests" / f"{r['n']:05d}.json"
        if r["n"] in compact or not p.exists():
            continue
        msgs = json.loads(p.read_text(encoding="utf-8"))["messages"]
        last = next((m for m in reversed(msgs) if m["role"] in ("user", "system")), None)
        if last and "summar" in text_of(last).lower():
            compact.append(r["n"])
    out["compaction"] = sorted(compact)
    out["compaction_happened"] = bool(compact)

    # speed
    gen = [r["completion_tokens"] / (r["t_end"] - r["t_first_token"]) for r in reqs
           if (r.get("completion_tokens") or 0) > 20 and r.get("t_end") and r.get("t_first_token")
           and r["t_end"] - r["t_first_token"] > 0]
    pre = [r["prompt_tokens"] / (r["t_first_token"] - r["t_start"]) for r in reqs
           if r.get("prompt_tokens") and r.get("t_first_token") and r.get("t_start")
           and r["t_first_token"] - r["t_start"] > 0]
    out["gen_tps"], out["prompt_tps"] = med(gen), med(pre)
    peak = max([r.get("prompt_tokens") or 0 for r in reqs], default=0)
    out["peak_prompt_tokens"] = peak
    out["peak_ctx_pct"] = round(100 * peak / limit, 1) if limit else None
    return out


def fmt(v, suffix=""):
    return "-" if v is None else f"{v}{suffix}"


def table(rows):
    hdr = ["label", "track", "result", "steps", "tool calls", "compile fail/fix/final ok", "truncation",
           "compaction", "peak ctx %", "gen tok/s", "prompt tok/s", "agent min"]
    lines = ["| " + " | ".join(hdr) + " |", "|" + "|".join("---" for _ in hdr) + "|"]
    for r in rows:
        trunc = ("yes @" + ",".join(str(t["request"]) for t in r["truncation"]) if r["truncation"] else "")
        if r["near_limit"]:
            trunc += (" " if trunc else "") + "near-limit @" + ",".join(map(str, r["near_limit"]))
        fin = {True: "ok", False: "FAIL", None: "n/a"}[r["final_compile_ok"]]
        cells = [r["label"], r["track"] + ("+assist" if r["assist"] else ""), fmt(r["result"]), r["steps"],
                 r["tool_calls"], f"{r['n_compile_fail']}/{r['fixes']}/{fin}", trunc or "no",
                 ("yes @" + ",".join(map(str, r["compaction"]))) if r["compaction"] else "no",
                 fmt(r["peak_ctx_pct"], "%"), fmt(r["gen_tps"]), fmt(r["prompt_tps"]), r["agent_min"]]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(lines)


def notes(rows):
    by = {}
    for r in rows:
        by.setdefault((r["track"], r["assist"]), []).append(r)
    out = []
    for (track, assist), rs in by.items():
        if len({r["label"] for r in rs}) < 2:
            continue
        name = track + ("+assist" if assist else "")
        parts = [f"{r['label']}: {r['result']}, {r['steps']} steps, {r['n_compile_fail']} compile fails, "
                 f"peak {fmt(r['peak_ctx_pct'], '%')}, {r['agent_min']} min" for r in rs]
        out.append(f"- Track {name}: " + " vs ".join(parts))
    return out


def parse(argv):
    groups, out, label = [], None, None
    it = iter(argv)
    for a in it:
        if a == "--label":
            label = next(it)
        elif a == "--out":
            out = next(it)
        else:
            groups.append((label or "run", a))
    return groups, out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    groups, out = parse(sys.argv[1:])
    if not groups:
        print(__doc__); sys.exit(1)
    rows = []
    for label, d in groups:
        a = analyze(d)
        a["label"] = label
        rows.append(a)
    md = table(rows)
    n = notes(rows)
    if n:
        md += "\n\nSide by side:\n" + "\n".join(n)
    print(md)
    if out:
        Path(out + ".md").write_text(md + "\n", encoding="utf-8")
        Path(out + ".json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
