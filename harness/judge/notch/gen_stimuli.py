# CANARY-b81aed453118 (hidden file marker)
"""
Hidden stimuli + expected outputs for the notch judge (never shown to the agent).

  gen_stimuli.py <outdir> [--n 4096] [--seed S]

Writes <outdir>/stim/<case>.txt, <outdir>/expected/<case>.txt and
<outdir>/cases.json. Deterministic for a given seed.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tasks" / "H"))
sys.path.insert(0, str(HERE.parent))
import notch_model as nm          # noqa: E402
from common import DEFAULT_SEED   # noqa: E402

FS = nm.FS_DEFAULT

# >= 2 coefficient sets with different f0 and r. "lowf" puts b1 near -2.0,
# close to the 18-bit limit, to catch coefficient width bugs.
COEF_SETS = {
    "c5M":   dict(f0=5e6,   r=0.99),
    "c20M":  dict(f0=20e6,  r=0.95),
    "lowf":  dict(f0=0.3e6, r=0.999),
}


def clip14(v):
    return np.clip(np.round(v), nm.DATA_MIN, nm.DATA_MAX).astype(np.int64)


def wanted_freq(f0):
    """Frequency of the wanted signal in the 'sig' stimulus (amplitude WANTED_AMP)."""
    return min(f0 / 10, 0.5e6)


WANTED_AMP = 2500


def stimuli(n, f0, rng):
    t = np.arange(n) / FS
    out = {}
    # (a) wanted signal + interference at the notch frequency + noise (like the viz)
    out["sig"] = clip14(2500 * np.sin(2 * np.pi * wanted_freq(f0) * t)
                        + 4000 * np.sin(2 * np.pi * f0 * t) + rng.normal(0, 20, n))
    # (b) random full-scale: drives the output into saturation
    out["rand"] = rng.integers(nm.DATA_MIN, nm.DATA_MAX + 1, n)
    # (c) linear chirp DC -> fs/2, near full scale
    out["chirp"] = clip14(8000 * np.sin(np.pi * (FS / 2) / (n / FS) * t ** 2))
    # (d) positive full-scale impulse, then negative full-scale impulse halfway
    imp = np.zeros(n, dtype=np.int64)
    imp[0], imp[n // 2] = nm.DATA_MAX, nm.DATA_MIN
    out["impulse"] = imp
    return out


def generic(a, out, rng):
    """easy / medium: cases come from the level registry (levels.py)."""
    import levels as L
    lv = L.LEVELS[a.level]
    cases = []
    for sname, p in lv["sets"].items():
        params = {k: v for k, v in p.items() if k != "f0"}
        for stim_name, x in stimuli(a.n, p["f0"], rng).items():
            name = f"{sname}_{stim_name}"
            y = lv["model"](x.tolist(), params)
            nm.write_ints(out / "stim" / f"{name}.txt", x.tolist())
            nm.write_ints(out / "expected" / f"{name}.txt", y)
            cases.append(dict(name=name, coef_set=sname, params=params, reg_writes=[list(w) for w in lv["regs"](params)],
                              f0=p["f0"], f_wanted=wanted_freq(p["f0"]), wanted_amp=WANTED_AMP, n=a.n,
                              n_saturated=int(sum(v in (nm.DATA_MIN, nm.DATA_MAX) for v in y))))
    meta = dict(seed=a.seed, fs=FS, n=a.n, level=a.level, module=lv["module"], cases=cases)
    (out / "cases.json").write_text(json.dumps(meta, indent=1))
    print(f"{len(cases)} cases -> {out} (seed {a.seed}, level {a.level})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--n", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--level", default="hard", choices=["easy", "medium", "hard"])
    a = ap.parse_args()
    out = Path(a.outdir)
    (out / "stim").mkdir(parents=True, exist_ok=True)
    (out / "expected").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)

    if a.level != "hard":
        return generic(a, out, rng)

    cases = []
    for sname, p in COEF_SETS.items():
        co = nm.notch_coeffs(p["f0"], p["r"], FS)
        for stim_name, x in stimuli(a.n, p["f0"], rng).items():
            name = f"{sname}_{stim_name}"
            y = nm.notch(x.tolist(), co)
            nm.write_ints(out / "stim" / f"{name}.txt", x.tolist())
            nm.write_ints(out / "expected" / f"{name}.txt", y)
            cases.append(dict(name=name, coef_set=sname, f0=p["f0"], r=p["r"], coeffs=list(co), f_wanted=wanted_freq(p["f0"]), wanted_amp=WANTED_AMP,
                              n=a.n, n_saturated=int(sum(v in (nm.DATA_MIN, nm.DATA_MAX) for v in y))))
    meta = dict(seed=a.seed, fs=FS, n=a.n, cases=cases)
    (out / "cases.json").write_text(json.dumps(meta, indent=1))
    print(f"{len(cases)} cases -> {out} (seed {a.seed})")


if __name__ == "__main__":
    main()
