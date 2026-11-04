"""Hidden judge for fpga_gain. Usage: judge.py <workspace>. Exit 0 = PASS, 1 = FAIL."""
import math, os, random, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "agent"))
import model  # the ORIGINAL golden model, not the workspace copy

SETTINGS = [(3000, 8, 100), (-12345, 7, -500), (32767, 10, 200), (1, 0, 0)]  # (gain, shift, offset)
SKIP = 8          # ignore the first cycles after reset
MAXLAT = 4


def bin_(name):
    d = os.environ.get("IVERILOG_DIR", "")
    return os.path.join(d, name) if d else name


def stimuli(n=600):
    rnd = random.Random(1234)
    noise = [rnd.randint(-8192, 8191) for _ in range(n)]
    sine = [max(-8192, min(8191, round(8191 * math.sin(2 * math.pi * k / 37)))) for k in range(n)]
    return {"random": noise, "sine": sine}


def fail(msg, score=0.0):
    print(f"SCORE: {score:.0f}% of hidden test samples correct")
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    ws = os.path.abspath(sys.argv[1])
    dut = os.path.join(ws, "red_pitaya_gain_block.v")
    if not os.path.isfile(dut):
        fail("red_pitaya_gain_block.v not found in the workspace")
    tmp = tempfile.mkdtemp(prefix="judge_gain_")
    comp = subprocess.run([bin_("iverilog"), "-g2012", "-o", "sim.vvp",
                           os.path.join(HERE, "hidden", "tb.v"), dut],
                          cwd=tmp, capture_output=True, text=True)
    if comp.returncode != 0:
        errs = [l for l in (comp.stderr + comp.stdout).splitlines() if "error" in l.lower()]
        fail("does not compile: " + (errs or comp.stderr.strip().splitlines() or ["?"])[0])
    latencies, n_ok, n_all, problems = None, 0, 0, []
    for sname, x in stimuli().items():
        model.write_ints(os.path.join(tmp, "stim.txt"), x)
        for g, s, o in SETTINGS:
            exp = model.gain_block(x, g, s, o)
            args = [bin_("vvp"), "sim.vvp", f"+gain={g}", f"+shift={s}", f"+offset={o}",
                    "+stim=stim.txt", "+out=out.txt"]
            sim = subprocess.run(args, cwd=tmp, capture_output=True, text=True, timeout=120)
            tag = f"{sname}, gain={g} shift={s} offset={o}"
            try:
                raw = open(os.path.join(tmp, "out.txt")).read().split()
            except OSError:
                fail(f"simulation produced no output ({tag})")
            # X/Z counts as wrong; score every case (no early stop) so partial progress is visible
            y = [int(t) if t.lstrip("-").isdigit() else None for t in raw]
            y += [None] * (len(exp) + MAXLAT - len(y))
            idx = range(SKIP, len(exp))
            wrong = {L: sum(y[i + L] != exp[i] for i in idx) for L in range(MAXLAT + 1)}
            best = min(wrong, key=wrong.get)
            n_ok += len(idx) - wrong[best]; n_all += len(idx)
            ok = {L for L, w in wrong.items() if w == 0}
            latencies = ok if latencies is None else latencies & ok
            if wrong[best] and not problems:
                i = next(i for i in idx if y[i + best] != exp[i])
                problems.append(f"output differs from model ({tag}): {wrong[best]} of {len(idx)} samples wrong, "
                                f"e.g. input #{i}: got {'X' if y[i + best] is None else y[i + best]}, "
                                f"expected {exp[i]}")
    score = 100 * n_ok / max(n_all, 1)
    if problems:
        fail(problems[0], score)
    if not latencies:
        fail("latency is not the same for all settings", score)
    print(f"SCORE: {score:.0f}% of hidden test samples correct")
    print(f"PASS: bit-exact on {len(SETTINGS) * 2} cases at fixed latency {min(latencies)}")
    sys.exit(0)


main()
