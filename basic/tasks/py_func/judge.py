"""Hidden judge for py_func. Usage: judge.py <workspace>. Exit 0 = PASS, 1 = FAIL."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ws = os.path.abspath(sys.argv[1])
if not os.path.isfile(os.path.join(ws, "fixedpoint.py")):
    print("FAIL: fixedpoint.py not found in the workspace")
    sys.exit(1)
env = dict(os.environ, PYTHONPATH=ws)
r = subprocess.run([sys.executable, os.path.join(HERE, "hidden", "test_hidden.py")],
                   cwd=HERE, env=env, capture_output=True, text=True, timeout=60)
score = next((l for l in r.stdout.splitlines() if l.startswith("SCORE:")), "SCORE: 0% (crashed before any case)")
print(score)
if r.returncode == 0:
    print("PASS: " + (r.stdout.strip().splitlines() or ["hidden tests OK"])[-1])
    sys.exit(0)
last = (r.stderr.strip().splitlines() or ["unknown error"])[-1]
print("FAIL: " + last)
sys.exit(1)
