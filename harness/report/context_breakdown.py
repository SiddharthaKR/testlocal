"""
Where did the context go? Breaks the largest logged request of a run into
categories (tokens estimated as chars/4) and lists the biggest tool outputs.

  context_breakdown.py <run_dir> [...]     -> prints a table, writes <run>/context_breakdown.json
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def tok(s):
    return len(s) // 4


def categorize(body):
    cat = defaultdict(int)
    cat["tool definitions"] = tok(json.dumps(body.get("tools", [])))
    names, big = {}, []
    for m in body["messages"]:
        role, c = m["role"], m.get("content")
        text = c if isinstance(c, str) else json.dumps(c) if c else ""
        if role == "system":
            cat["system prompt (opencode)"] += tok(text)
        elif role == "user":
            cat["user prompt"] += tok(text)
        elif role == "assistant":
            cat["assistant text"] += tok(text)
            for tc in m.get("tool_calls") or []:
                f = tc["function"]; names[tc["id"]] = f["name"]
                k = {"write": "file writes (args)", "edit": "file edits (args)"}.get(f["name"], "other tool-call args")
                cat[k] += tok(f.get("arguments") or "")
        elif role == "tool":
            name = names.get(m.get("tool_call_id"), "?")
            k = {"read": "file reads (results)", "shell": "shell/tool outputs (results)",
                 "execute": "shell/tool outputs (results)", "grep": "search results", "glob": "search results",
                 "write": "write/edit acks", "edit": "write/edit acks"}.get(name, f"{name} results")
            cat[k] += tok(text)
            big.append((tok(text), text.count("\n") + 1, name, text[:90].replace("\n", " ")))
    return dict(cat), sorted(big, reverse=True)[:6]


def analyze(run):
    run = Path(run)
    reqs = sorted((run / "requests").glob("*.json"))
    if not reqs:
        return None
    sizes = [(len(p.read_bytes()), p) for p in reqs]
    body = json.loads(max(sizes)[1].read_text(encoding="utf-8"))
    cat, big = categorize(body)
    # growth over the run: categories in first vs last agent request
    return dict(run=run.name, request=max(sizes)[1].name, n_messages=len(body["messages"]),
                total_est=sum(cat.values()), categories=dict(sorted(cat.items(), key=lambda x: -x[1])),
                biggest_tool_results=[dict(tokens=t, lines=l, tool=n, start=s) for t, l, n, s in big])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for r in sys.argv[1:]:
        a = analyze(r)
        if not a:
            print(f"{r}: no requests"); continue
        Path(r, "context_breakdown.json").write_text(json.dumps(a, indent=1))
        print(f"\n== {a['run']}  largest request {a['request']}: {a['n_messages']} messages, ~{a['total_est']:,} tokens")
        for k, v in a["categories"].items():
            print(f"   {v:7,}  {100 * v / a['total_est']:5.1f}%  {k}")
        print("   biggest tool results:")
        for b in a["biggest_tool_results"]:
            print(f"   {b['tokens']:6,} tok {b['lines']:4} lines  {b['tool']:6} {b['start']}")
