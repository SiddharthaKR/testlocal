# CANARY-b81aed453118 (hidden file marker)
"""
Detect whether the agent saw hidden judge/solution material.

  leak_check.py <run_dir> <workspace_dir>   -> prints JSON, exit 1 if a leak is found

Scans every logged LLM request body (<run_dir>/requests/*.json, i.e. everything
the model was shown, including tool outputs) and every workspace file for the
canary string and hidden path names (common.LEAK_MARKERS).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANARY, LEAK_MARKERS  # noqa: E402


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def check(run_dir, ws):
    hits = []
    for p in sorted(Path(run_dir, "requests").glob("*.json")):
        try:
            body = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            body = p.read_text(encoding="utf-8", errors="replace")
        text = "\n".join(strings(body))
        for m in LEAK_MARKERS:
            if m in text:
                i = text.index(m)
                hits.append(dict(where=f"requests/{p.name}", marker=m,
                                 context=text[max(0, i - 80): i + 80].replace("\n", " ")))
    for p in Path(ws).rglob("*"):
        if p.is_file() and ".git" not in p.parts and p.stat().st_size < 5_000_000:
            if CANARY in p.read_text(encoding="utf-8", errors="ignore"):
                hits.append(dict(where=f"workspace/{p.relative_to(ws)}", marker=CANARY, context=""))
    # one entry per (where, marker)
    seen, uniq = set(), []
    for h in hits:
        if (h["where"], h["marker"]) not in seen:
            seen.add((h["where"], h["marker"])); uniq.append(h)
    leaked = [h for h in uniq if h["marker"] == CANARY]
    attempts = [h for h in uniq if h["marker"] != CANARY]
    # leak = hidden CONTENT reached the model or workspace (canary seen).
    # access attempts = hidden path names in the traffic (reported, not failed).
    return dict(leak_suspected=bool(leaked), leaks=leaked[:20],
                n_access_attempts=len(attempts), access_attempts=attempts[:20])


if __name__ == "__main__":
    r = check(sys.argv[1], sys.argv[2])
    print(json.dumps(r, indent=1))
    sys.exit(1 if r["leak_suspected"] else 0)
