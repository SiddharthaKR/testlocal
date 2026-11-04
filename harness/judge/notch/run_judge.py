# CANARY-b81aed453118 (hidden file marker)
"""
Track H judge.

  run_judge.py <outdir> <candidate.v> [--n 4096] [--seed S] [--assist]

Generates hidden stimuli, simulates the candidate with the judge testbench,
compares against notch_model.py, and writes <outdir>/judge.json plus data
files for the report (judge_data/). Exit code: 0 PASS, 1 FAIL, 2 judge error.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import compare as C           # noqa: E402
from common import SETTLE_CYCLES, DEFAULT_SEED  # noqa: E402


def iverilog_bins():
    env = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
    d = str(env.get("iverilog_dir") or "auto")
    if d == "auto":
        return "iverilog", "vvp"
    if os.name == "nt" and d.startswith("/") and len(d) > 2 and d[2] == "/":
        d = f"{d[1]}:{d[2:]}"   # Git Bash /c/x -> c:/x for subprocess
    return str(Path(d) / "iverilog"), str(Path(d) / "vvp")


def run(cmd, cwd, log):
    with open(log, "a") as f:
        f.write("$ " + " ".join(map(str, cmd)) + "\n")
        r = subprocess.run(list(map(str, cmd)), cwd=cwd, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode


def parse_checks(path):
    checks, bypass_rows, inb = {}, [], False
    for line in Path(path).read_text().splitlines():
        if line.startswith("CHECK "):
            _, name, res, *rest = line.split()
            checks[name] = dict(pass_=res == "PASS", detail=" ".join(rest))
        elif line == "BYPASS_CSV_BEGIN":
            inb = True
        elif line == "BYPASS_CSV_END":
            inb = False
        elif inb:
            bypass_rows.append(line)
    return checks, bypass_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("candidate")
    ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--assist", action="store_true", help="record assist: true in judge.json")
    ap.add_argument("--level", default="hard", choices=["easy", "medium", "hard"])
    a = ap.parse_args()
    a.candidate = str(Path(a.candidate).resolve())

    t0 = time.time()
    out = Path(a.outdir).resolve(); out.mkdir(parents=True, exist_ok=True)
    data = out / "judge_data"
    if data.exists():
        shutil.rmtree(data)
    data.mkdir()
    log = data / "judge.log"
    iverilog, vvp = iverilog_bins()

    res = dict(track="H", assist=a.assist, seed=a.seed, settle_cycles=SETTLE_CYCLES,
               max_latency=C.MAX_LATENCY, candidate=str(Path(a.candidate).resolve()),
               cases=[], checks={}, status="FAIL")

    def finish(code):
        res["judge_seconds"] = round(time.time() - t0, 1)
        (out / "judge.json").write_text(json.dumps(res, indent=1))
        print(f"JUDGE H: {res['status']}  cases {res.get('n_pass', 0)}/{len(res['cases'])}  "
              f"checks {sum(c['pass'] for c in res['checks'].values())}/{len(res['checks'])}"
              + ("  [ASSIST]" if a.assist else "") + f"  -> {out / 'judge.json'}")
        sys.exit(code)

    subprocess.run([sys.executable, str(HERE / "gen_stimuli.py"), str(data), "--n", str(a.n),
                    "--seed", str(a.seed)], check=True, stdout=subprocess.DEVNULL)
    meta = json.loads((data / "cases.json").read_text())

    if run([iverilog, "-g2012", "-o", data / "judge.vvp", HERE / "tb_notch_judge.v", a.candidate], data, log):
        res["status"] = "COMPILE_ERROR"
        res["error"] = "candidate failed to compile with the judge testbench (see judge_data/judge.log)"
        finish(1)

    # filter cases
    for c in meta["cases"]:
        stim, exp, csv = data / "stim" / f"{c['name']}.txt", data / "expected" / f"{c['name']}.txt", data / f"dut_{c['name']}.csv"
        b0, b1, b2, a1, a2 = c["coeffs"]
        run([vvp, "-n", data / "judge.vvp", "+mode=filter", f"+stim={stim}", f"+out={csv}",
             f"+n={c['n']}", f"+b0={b0}", f"+b1={b1}", f"+b2={b2}", f"+a1={a1}", f"+a2={a2}"], data, log)
        r = C.compare_files(exp, csv) if csv.exists() else dict(**{"pass": False}, error="no output")
        r.update(name=c["name"], coef_set=c["coef_set"], n_saturated=c["n_saturated"])
        res["cases"].append(r)

    # register / bypass / X checks (bypass uses the first random stimulus)
    chk = data / "checks.txt"
    bstim = data / "stim" / f"{meta['cases'][1]['name']}.txt"
    run([vvp, "-n", data / "judge.vvp", "+mode=checks", f"+out={chk}", f"+stim={bstim}", f"+n={a.n}"], data, log)
    if chk.exists():
        checks, brows = parse_checks(chk)
        res["checks"] = {k: dict(**{"pass": v["pass_"]}, detail=v["detail"]) for k, v in checks.items()}
        (data / "bypass.csv").write_text("\n".join(brows) + "\n")
        bx = [int(l) for l in bstim.read_text().split()]
        ys, nx = C.load_dut_csv(data / "bypass.csv") if brows else ({}, 0)
        br = C.compare(bx, ys, nx) if brows else {"pass": False}
        res["checks"]["bypass"] = {"pass": br["pass"], "detail": f"latency={br.get('latency')} first_mismatch={br.get('first_mismatch')}"}
    else:
        res["checks"]["checks_ran"] = {"pass": False, "detail": "checks simulation produced no output"}

    lats = {c.get("latency") for c in res["cases"] if c.get("pass")}
    res["n_pass"] = sum(c["pass"] for c in res["cases"])
    res["latency"] = lats.pop() if len(lats) == 1 else None
    consistent = len({c.get("latency") for c in res["cases"]}) == 1
    if "bypass" in res["checks"] and res["checks"]["bypass"]["pass"] and res["latency"] is not None:
        blat = int(res["checks"]["bypass"]["detail"].split()[0].split("=")[1])
        if blat != res["latency"]:   # spec: bypass delayed by the SAME latency as the filter
            res["checks"]["bypass"] = {"pass": False, "detail": f"bypass latency {blat} != filter latency {res['latency']}"}
    ok = res["n_pass"] == len(res["cases"]) and consistent and all(v["pass"] for v in res["checks"].values())
    res["status"] = "PASS" if ok else "FAIL"
    for c in res["cases"]:
        if not c["pass"]:
            print(f"  FAIL {c['name']}: lat={c.get('latency')} match={c.get('n_match')}/{c.get('n_compared')} "
                  f"first={c.get('first_mismatch')} n_x={c.get('n_x')}")
    for k, v in res["checks"].items():
        if not v["pass"]:
            print(f"  FAIL check {k}: {v['detail']}")
    finish(0 if ok else 1)


if __name__ == "__main__":
    main()
