# CANARY-b81aed453118 (hidden file marker)
"""Track C self-test: review set compiles like the original; scorer gives the
expected counts on synthetic answers. Exit 0 if all checks pass."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "judge" / "pid_equiv"))
import bugs as B              # noqa: E402
import score as S             # noqa: E402
from run_judge import iverilog_bins  # noqa: E402  (same iverilog lookup as the B judge)

import yaml                   # noqa: E402

fail = 0


def check(name, ok, detail=""):
    global fail
    print(f"  {'ok   ' if ok else 'WRONG'} {name}{(': ' + detail) if detail else ''}")
    fail |= not ok


iverilog, _ = iverilog_bins()
tops = ["red_pitaya_pid_block", "red_pitaya_filter_block", "red_pitaya_iq_block", "red_pitaya_asg_ch"]
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    B.build(td / "bug")
    (td / "orig").mkdir()
    for f in B.REVIEW + B.DEPS:
        (td / "orig" / f).write_bytes((B.RTL / f).read_bytes())
    for top in tops:
        res = {}
        for s in ("orig", "bug"):
            r = subprocess.run([iverilog, "-g2012", "-s", top, "-o", str(td / f"{s}.vvp")]
                               + [str(p) for p in sorted((td / s).glob("*.v"))], capture_output=True, text=True)
            res[s] = (r.returncode, r.stdout.lower().count("warning") + r.stderr.lower().count("warning"))
        check(f"{top} compiles with bugs", res["bug"][0] == 0, f"rc={res['bug'][0]}")
        check(f"{top} no new warnings (bugs not flagged by compiler)", res["bug"][1] == res["orig"][1],
              f"{res['orig'][1]} -> {res['bug'][1]}")
    # line counts unchanged so the answer key lines are valid in the review files
    for f in B.REVIEW:
        a = len((B.RTL / f).read_bytes().splitlines()); b = len((td / "bug" / f).read_bytes().splitlines())
        check(f"{f} line count unchanged", a == b, f"{a} vs {b}")

# every level: its review set compiles with exactly its bugs, and its own key scores 100%
for level, lv in B.LEVELS.items():
    with tempfile.TemporaryDirectory() as td:
        out = B.build(Path(td), level)
        n_changed = sum((out / f).read_bytes() != (B.RTL / f).read_bytes() for f in lv["review"])
        tops = [Path(f).stem for f in lv["review"] if f != "red_pitaya_lpf_block.v"]
        rcs = [subprocess.run([iverilog, "-g2012", "-s", t, "-o", str(Path(td) / "x.vvp")]
                              + [str(p) for p in sorted(out.glob("*.v"))], capture_output=True).returncode
               for t in tops]
        check(f"level {level}: review set compiles", not any(rcs), str(rcs))
        check(f"level {level}: every review file has a seeded bug", n_changed == len(lv["review"]),
              f"{n_changed}/{len(lv['review'])}")
    k = yaml.safe_load((HERE / f"answer_key_{level}.yaml").read_text())
    r = S.score([dict(file=b["file"], line=b["line"], description=b["description"]) for b in k["bugs"]], k)
    check(f"level {level}: own answer key scores {len(k['bugs'])}/{len(k['bugs'])}",
          r["found"] == len(k["bugs"]) and r["false_positives"] == 0, f"{r['found']} fp {r['false_positives']}")

key = yaml.safe_load((HERE / "answer_key_hard.yaml").read_text())
exact = [dict(file=b["file"], line=b["line"], description=b["description"]) for b in key["bugs"]]
n = len(exact)
cases = [
    ("answer key itself", exact, n, 0),
    ("all lines +3", [dict(d, line=d["line"] + 3) for d in exact], n, 0),
    ("all lines -3", [dict(d, line=d["line"] - 3) for d in exact], n, 0),
    ("empty answer", [], 0, 0),
    ("one bogus line", [dict(file="red_pitaya_asg_ch.v", line=30, description="x")], 0, 1),
    # from a real Gemma run: right line, explanation does not identify the bug -> near miss, not found
    ("vague report on bug line", [dict(file="red_pitaya_pid_block.v", line=316,
      description="overly complex overflow logic, risking functional bugs during saturation checks")], 0, 0),
    # from a real Gemma run: exact line of a known upstream issue, 1 line from a seeded bug
    ("upstream issue next to a bug", [dict(file="red_pitaya_filter_block.v", line=80,
      description="shift segment may be out of range for the LPF block")], 0, 0),
    # keyword must be a whole word: "sign" inside "signal"/"assign"/"design" is not an explanation
    ("keyword inside another word", [dict(file="red_pitaya_pid_block.v", line=205,
      description="the assign of the error signal looks odd in this design")], 0, 0),
    ("known upstream kd issue", [dict(file="red_pitaya_pid_block.v", line=270, description="x")], 0, 0),
    ("duplicate report", exact[:1] * 3, 1, 0),
    ("path prefix + backslashes", [dict(d, file="review\\" + d["file"]) for d in exact], n, 0),
]
print("  scorer:")
for name, reps, want_found, want_fp in cases:
    r = S.score([dict(file=Path(str(x["file"]).replace("\\", "/")).name, line=x["line"],
                      description=x["description"]) for x in reps], key)
    check(name, (r["found"], r["false_positives"]) == (want_found, want_fp),
          f"found {r['found']} fp {r['false_positives']} (want {want_found}, {want_fp})")
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:
    t.write("not json")
reps, err = S.load_reports(t.name)
check("garbage file -> warning, no crash", reps == [] and err is not None)
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:   # seen from Gemma in a real run
    t.write('[{"file": "red_pitaya_asg_ch.v", "line": 121, "description": "a $124\\mu\\text{s}$ delay"}]')
reps, err = S.load_reports(t.name)
check("LaTeX backslashes repaired", len(reps) == 1 and reps[0]["line"] == 121 and "repaired" in (err or ""), str(err))
sys.exit(1 if fail else 0)
