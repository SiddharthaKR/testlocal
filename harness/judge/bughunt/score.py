# CANARY-b81aed453118 (hidden file marker)
"""
Track C scorer.

  score.py <outdir> <bugs.json> [--assist]   -> <outdir>/judge.json

bugs.json: list of {file, line, description} (a top-level {"bugs": [...]} is accepted too).
A report counts as FOUND if its file matches (by basename), its line is within
+-match_window of a seeded bug, AND its description names the problem (one of the
bug's keywords). Each seeded bug is matched at most once (max one-to-one matching,
nearest first; extra correct reports are duplicates). Right place but wrong/vague
explanation = near miss (not credited, not a false alarm). Reports on known upstream
issues (answer_key.yaml "preexisting") are neither found nor false positives; a report
exactly on an upstream-issue line counts as that issue. Everything else is a false positive.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def load_reports(path):
    """Return (reports, error). Tolerates the usual LLM output quirks."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        return [], f"cannot read {path}: {e}"
    if text.startswith("```"):                       # fenced JSON
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    repaired = None
    try:
        data = json.loads(text)
    except ValueError as e:
        # common LLM quirk: LaTeX like "\mu" inside strings -> escape stray backslashes and retry
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        try:
            data = json.loads(fixed)
            repaired = f"bugs.json had invalid escapes ({e}); repaired by escaping stray backslashes"
        except ValueError:
            return [], f"bugs.json is not valid JSON: {e}"
    if isinstance(data, dict):
        data = data.get("bugs", [])
    if not isinstance(data, list):
        return [], "bugs.json must be a list"
    out, bad = [], 0
    for r in data:
        try:
            out.append(dict(file=Path(str(r["file"]).replace("\\", "/")).name, line=int(r["line"]),
                            description=str(r.get("description", ""))[:300]))
        except (KeyError, TypeError, ValueError):
            bad += 1
    warn = [w for w in (repaired, f"{bad} entries without a usable file/line" if bad else None) if w]
    return out, ("; ".join(warn) or None)


STEMS = ("negat", "doubl", "revers", "uninitiali", "not initiali", "invert", "subtract", "misalign",
         "polarity", "satur", "truncat", "swap", "slice", "round")


def keyword_hit(k, text):
    """Whole-word match ('sign' must not match 'signal'/'assign'/'design'), except known word
    stems ('negat' -> negative/negated) which only need a word start. Symbols match literally."""
    k = k.lower().strip()
    if not re.match(r"^[a-z0-9]([a-z0-9 \-]*[a-z0-9])?$", k):   # e.g. "[5-1:0]", "+6", "-quadrature": literal
        return k in text
    start = r"(?<![a-z0-9_])"
    end = "" if k.startswith(STEMS) else r"(?![a-z0-9_])"
    return re.search(start + re.escape(k) + end, text) is not None


def score(reports, key):
    win = key.get("match_window", 3)
    bugs = key["bugs"]
    pre = key.get("preexisting", [])

    def near(r, b):
        return r["file"] == b["file"] and abs(r["line"] - b["line"]) <= win

    def explains(r, b):   # description names what is actually wrong
        d = r["description"].lower()
        return any(keyword_hit(k, d) for k in b.get("keywords", [])) if b.get("keywords") else True

    def on_upstream_line(r):   # exactly inside a known upstream issue, and not exactly on a seeded bug
        return any(r["file"] == p["file"] and p["lines"][0] <= r["line"] <= p["lines"][1] for p in pre) and \
            not any(r["file"] == b["file"] and r["line"] == b["line"] for b in bugs)

    # maximum one-to-one matching (Kuhn's augmenting paths), trying nearer bugs first, so
    # two nearby bugs are both credited when each has its own report
    cand = {i: sorted((j for j, b in enumerate(bugs) if near(r, b) and explains(r, b)),
                      key=lambda j, r=r: abs(r["line"] - bugs[j]["line"]))
            for i, r in enumerate(reports) if not on_upstream_line(r)}
    bug_by = {}

    def augment(i, seen):
        for j in cand[i]:
            if j not in seen:
                seen.add(j)
                if j not in bug_by or augment(bug_by[j], seen):
                    bug_by[j] = i
                    return True
        return False

    for i in sorted(cand, key=lambda i: min((abs(reports[i]["line"] - bugs[j]["line"]) for j in cand[i]),
                                            default=99)):
        augment(i, set())
    rep_by = {i: j for j, i in bug_by.items()}
    verdicts = []
    for i, r in enumerate(reports):
        if i in rep_by:
            v = dict(r, verdict="found", bug=bugs[rep_by[i]]["id"])
        elif on_upstream_line(r):
            v = dict(r, verdict="known_upstream_issue")
        elif any(near(r, b) and explains(r, b) for b in bugs):
            v = dict(r, verdict="duplicate")
        elif any(near(r, b) for b in bugs):
            v = dict(r, verdict="near_miss")   # right place, explanation does not identify the bug
        elif any(r["file"] == p["file"] and p["lines"][0] - win <= r["line"] <= p["lines"][1] + win for p in pre):
            v = dict(r, verdict="known_upstream_issue")
        else:
            v = dict(r, verdict="false_positive")
        verdicts.append(v)
    per_bug = [dict(id=b["id"], file=b["file"], line=b["line"], cls=b["cls"], found=j in bug_by)
               for j, b in enumerate(bugs)]
    return dict(found=len(bug_by), n_bugs=len(bugs),
                false_positives=sum(v["verdict"] == "false_positive" for v in verdicts),
                duplicates=sum(v["verdict"] == "duplicate" for v in verdicts),
                near_misses=sum(v["verdict"] == "near_miss" for v in verdicts),
                known_upstream=sum(v["verdict"] == "known_upstream_issue" for v in verdicts),
                n_reports=len(reports), per_bug=per_bug, reports=verdicts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("bugs_json")
    ap.add_argument("--assist", action="store_true")
    ap.add_argument("--level", default="hard", choices=["easy", "medium", "hard"])
    a = ap.parse_args()
    key = yaml.safe_load((HERE / f"answer_key_{a.level}.yaml").read_text())
    reports, err = load_reports(a.bugs_json)
    res = dict(track="C", level=a.level, assist=a.assist, match_window=key.get("match_window", 3), input_warning=err)
    res.update(score(reports, key))
    res["status"] = "SCORED" if reports or not err else "INVALID_OUTPUT"
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    (out / "judge.json").write_text(json.dumps(res, indent=1))
    print(f"JUDGE C: found {res['found']}/{res['n_bugs']}  false positives {res['false_positives']}  "
          f"near misses {res['near_misses']}  duplicates {res['duplicates']}  known upstream {res['known_upstream']}"
          + (f"  WARNING: {err}" if err else "") + f"  -> {out / 'judge.json'}")


if __name__ == "__main__":
    main()
