# CANARY-b81aed453118 (hidden file marker)
"""
Track B judge: latency-tolerant bit-exact equivalence of an optimized PID
against pid_ref.v, plus QoR (if Vivado is available).

  run_judge.py <outdir> <candidate.v> [extra candidate .v ...]
               [--cycles 100000] [--seed S] [--assist] [--level easy|medium|hard]

Levels: hard = red_pitaya_pid_block (default), medium = red_pitaya_iq_modulator_block,
easy = red_pitaya_iq_demodulator_block (references are the vendor RTL).

The reference is pid_ref.v + vendor filter/lpf blocks, with module names
prefixed "ref_" so both designs live in one simulation. Candidate files not
given fall back to the vendor filter/lpf blocks.
Exit: 0 PASS, 1 FAIL.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from common import SETTLE_CYCLES, DEFAULT_SEED  # noqa: E402

ENV = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
RTL = ROOT / str(ENV["pyrpl_repo"]) / str(ENV["pyrpl_rtl"])
PID_REF = ROOT / "harness" / "tasks" / "B" / "pid_ref.v"
DEPS = ["red_pitaya_filter_block.v", "red_pitaya_lpf_block.v"]
REF_MODULES = ["red_pitaya_pid_block", "red_pitaya_filter_block", "red_pitaya_lpf_block"]
# level -> module, testbench, reference files, default candidate deps (vendor RTL), modules to prefix ref_
LEVELS = {
    "hard": dict(module="red_pitaya_pid_block", tb="tb_pid_equiv.v", ref=[PID_REF] + [RTL / d for d in DEPS],
                 deps=DEPS, ref_modules=REF_MODULES),
    "medium": dict(module="red_pitaya_iq_modulator_block", tb="tb_iq_mod_equiv.v",
                   ref=[RTL / f for f in ["red_pitaya_iq_modulator_block.v", "red_pitaya_product_sat.v",
                                          "red_pitaya_saturate.v"]],
                   deps=["red_pitaya_product_sat.v", "red_pitaya_saturate.v"],
                   ref_modules=["red_pitaya_iq_modulator_block", "red_pitaya_product_sat", "red_pitaya_saturate"]),
    "easy": dict(module="red_pitaya_iq_demodulator_block", tb="tb_iq_demod_equiv.v",
                 ref=[RTL / "red_pitaya_iq_demodulator_block.v"], deps=[],
                 ref_modules=["red_pitaya_iq_demodulator_block"]),
}
MAX_LAG = 8
F_C = 1e6   # crossover frequency for the phase-margin cost


def winpath(d):
    d = str(d)
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", d):
        d = f"{d[1]}:{d[2:]}"
    return d


def iverilog_bins():
    d = str(ENV.get("iverilog_dir") or "auto")
    if d == "auto":
        return "iverilog", "vvp"
    return str(Path(winpath(d)) / "iverilog"), str(Path(winpath(d)) / "vvp")


def prefix_ref(src_text, modules=REF_MODULES):
    for m in modules:
        src_text = re.sub(rf"\b{m}\b", f"ref_{m}", src_text)
    return src_text


def parse(out_txt):
    r = dict(lags={}, rb_fail=[])
    for line in Path(out_txt).read_text().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "LAG":
            k, match, mism, fc, fe, fg = [int(t) if re.fullmatch(r"-?\d+", t) else -1 for t in f[1:7]]  # X outputs print non-integers
            r["lags"][k] = dict(match=match, mismatch=mism, first_cycle=fc, expected=fe, got=fg)
        elif f[0] == "XCOUNT":
            r["x_count"] = int(f[1])
        elif f[0] == "RB":
            r["rb_fail"].append(" ".join(f[1:]))
        elif f[0] == "RBSUM":
            r["rb_reads"], r["rb_mismatch"] = int(f[1]), int(f[2])
        elif f[0] == "COMPARED":
            it = iter(f)
            r["coverage"] = {k.lower(): int(v) for k, v in zip(it, it)}
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("candidate", nargs="+")
    ap.add_argument("--cycles", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--assist", action="store_true")
    ap.add_argument("--level", default="hard", choices=["easy", "medium", "hard"])
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.outdir).resolve(); data = out / "judge_data"; data.mkdir(parents=True, exist_ok=True)
    log = data / "judge.log"; log.write_text("")
    iverilog, vvp = iverilog_bins()

    lv = LEVELS[a.level]
    cand = [Path(c).resolve() for c in a.candidate]
    names = {c.name for c in cand}
    cand += [RTL / d for d in lv["deps"] if d not in names]

    ref_dir = data / "ref"; ref_dir.mkdir(exist_ok=True)
    refs = []
    for src in lv["ref"]:
        dst = ref_dir / f"ref_{src.name}"
        dst.write_text(prefix_ref(src.read_text(), lv["ref_modules"]))
        refs.append(dst)

    res = dict(track="B", assist=a.assist, seed=a.seed, cycles=a.cycles, settle_cycles=SETTLE_CYCLES,
               max_lag=MAX_LAG, level=a.level, module=lv["module"], candidate=[str(c) for c in cand], status="FAIL")

    def finish(code):
        res["judge_seconds"] = round(time.time() - t0, 1)
        (out / "judge.json").write_text(json.dumps(res, indent=1))
        print(f"JUDGE B: {res['status']}  latency={res.get('latency')}  "
              f"compared={res.get('coverage', {}).get('compared')} cycles"
              + ("  [ASSIST]" if a.assist else "") + f"  -> {out / 'judge.json'}")
        for r in res.get("reasons", []):
            print("  " + r)
        sys.exit(code)

    with open(log, "a") as f:
        rc = subprocess.run([iverilog, "-g2012", "-o", str(data / "equiv.vvp"), str(HERE / lv["tb"])]
                            + [str(p) for p in refs + cand], stdout=f, stderr=subprocess.STDOUT).returncode
    if rc:
        res["status"] = "COMPILE_ERROR"; res["reasons"] = ["compile failed, see judge_data/judge.log"]
        finish(1)
    with open(log, "a") as f:
        subprocess.run([vvp, "-n", str(data / "equiv.vvp"), f"+seed={a.seed}", f"+cycles={a.cycles}",
                        f"+out={data / 'equiv.txt'}"], stdout=f, stderr=subprocess.STDOUT, cwd=data)
    if not (data / "equiv.txt").exists():
        res["reasons"] = ["simulation produced no result"]; finish(1)

    r = parse(data / "equiv.txt")
    res.update(coverage=r.get("coverage", {}), x_count=r.get("x_count"))
    if a.level == "hard":
        res["readback"] = dict(reads=r.get("rb_reads"), mismatches=r.get("rb_mismatch"), first=r["rb_fail"][:5])
    n = res["coverage"].get("compared", 0)
    exact = [k for k, v in sorted(r["lags"].items()) if v["mismatch"] == 0 and v["match"] == n]
    best = max(r["lags"], key=lambda k: r["lags"][k]["match"])
    res["lag_table"] = r["lags"]
    res["latency"] = exact[0] if exact else None
    res["best_lag"] = best
    reasons = []
    if not exact:
        b = r["lags"][best]
        reasons.append(f"no lag in [0,{MAX_LAG}] matches: best lag {best} matches {b['match']}/{n}, first mismatch "
                       f"cycle {b['first_cycle']} expected {b['expected']} got {b['got']}")
    if res["x_count"]:
        reasons.append(f"{res['x_count']} X/Z output samples")
    if r.get("rb_mismatch"):
        reasons.append(f"register readback differs ({r['rb_mismatch']} of {r['rb_reads']} reads)")
    if n < a.cycles // 2:
        reasons.append(f"only {n} cycles compared (judge coverage problem)")
    # coverage counters are measured on the REFERENCE design: a zero means the stimulus stopped
    # exercising that behaviour (e.g. saturation) -> the judge itself is broken, not the candidate
    uncovered = [k for k, v in res["coverage"].items() if k not in ("compared", "excluded") and v == 0]
    if uncovered:
        res["status"] = "JUDGE_ERROR"
        res["error"] = f"hidden stimulus never exercised: {', '.join(uncovered)} (judge coverage problem)"
        res["reasons"] = reasons + [res["error"]]
        finish(2)
    if res["latency"] is not None:
        res["delta_latency"] = res["latency"]
        res["phase_cost_deg_at_1MHz"] = round(360 * F_C * res["latency"] * float(ENV["clk_period_ns"]) * 1e-9, 2)
    res["reasons"] = reasons
    res["status"] = "PASS" if not reasons else "FAIL"
    res["qor"] = {"status": "SKIPPED", "reason": "QoR is measured by run_demo.sh via run_impl.sh (Vivado)"}
    finish(0 if not reasons else 1)


if __name__ == "__main__":
    main()
