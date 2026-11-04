"""Prove the judges before trusting them: reference solutions must PASS, broken ones must FAIL.

    py basic/selftest.py
"""
import glob, os, shutil, subprocess, sys, tempfile

from harness import BASIC, load_config, tool_env

# task -> (name the solution must have inside the workspace)
TARGET = {"fpga_gain": "red_pitaya_gain_block.v", "py_func": "fixedpoint.py"}


def judge(task, candidate, cfg):
    ws = tempfile.mkdtemp(prefix="selftest_ws_")
    try:
        shutil.copy(candidate, os.path.join(ws, TARGET[task]))   # judge sees ONLY the candidate
        r = subprocess.run([sys.executable, os.path.join(BASIC, "tasks", task, "judge.py"), ws],
                           env=dict(os.environ, **tool_env(cfg)), capture_output=True, text=True, timeout=600)
        out = (r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]])[-1]
        return r.returncode == 0, out
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def main():
    cfg = load_config()
    ivl = tool_env(cfg)["IVERILOG_DIR"]
    if not shutil.which(os.path.join(ivl, "iverilog") if ivl else "iverilog"):
        print("SELFTEST: FAILED - iverilog not found (set iverilog_dir in basic/config.yaml or put it on PATH)")
        sys.exit(1)
    bad = 0
    for task in sorted(TARGET):
        hidden = os.path.join(BASIC, "tasks", task, "hidden")
        for f in sorted(glob.glob(os.path.join(hidden, "reference.*")) + glob.glob(os.path.join(hidden, "broken_*"))):
            name = os.path.basename(f)
            if name.startswith("test_") or name.startswith("tb."):
                continue
            want_pass = name.startswith("reference")
            passed, msg = judge(task, f, cfg)
            ok = passed == want_pass
            bad += not ok
            print(f"{'ok   ' if ok else 'WRONG'} {task}/{name}: judge said {'PASS' if passed else 'FAIL'} "
                  f"(expected {'PASS' if want_pass else 'FAIL'}) - {msg}")
    print("SELFTEST: " + ("OK" if bad == 0 else "FAILED"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
