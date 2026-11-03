"""
LLM metrics for one run, from <run>/requests.jsonl (+ run_meta.json, judge.json).

  metrics.py <run_dir>     -> prints JSON, writes <run_dir>/metrics.json

Includes peak prompt tokens vs the model's context limit (context_limit in
run_meta.json, else config/env.yaml).
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if p.exists() else []


def compute(run):
    run = Path(run)
    meta = json.loads((run / "run_meta.json").read_text()) if (run / "run_meta.json").exists() else {}
    judge = json.loads((run / "judge.json").read_text()) if (run / "judge.json").exists() else {}
    env = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
    reqs = load_jsonl(run / "requests.jsonl")

    limit = meta.get("context_limit") or env.get("context_limit")
    prompt = [r["prompt_tokens"] or 0 for r in reqs]
    compl = [r["completion_tokens"] or 0 for r in reqs]
    peak = max(prompt, default=0)
    llm_s = sum((r["t_end"] or r["t_start"]) - r["t_start"] for r in reqs)
    ttft = [r["t_first_token"] - r["t_start"] for r in reqs if r.get("t_first_token")]
    m = dict(
        assist=bool(meta.get("assist") or judge.get("assist")),
        n_requests=len(reqs),
        n_errors=sum(r["status"] != 200 for r in reqs),
        prompt_tokens_total=sum(prompt),
        completion_tokens_total=sum(compl),
        total_tokens=sum(prompt) + sum(compl),
        peak_prompt_tokens=peak,
        context_limit=limit,
        peak_context_pct=round(100 * peak / limit, 1) if limit else None,
        n_near_limit=sum(p > 0.9 * limit for p in prompt) if limit else None,
        usage_estimated=any(r["usage_estimated"] for r in reqs),
        llm_seconds=round(llm_s, 1),
        median_ttft_seconds=round(sorted(ttft)[len(ttft) // 2], 2) if ttft else None,
        n_hints=max((r.get("n_hints", 0) for r in reqs), default=0),
        judge_status=judge.get("status"),
    )
    return m


if __name__ == "__main__":
    m = compute(sys.argv[1])
    Path(sys.argv[1], "metrics.json").write_text(json.dumps(m, indent=1))
    print(json.dumps(m, indent=1))
