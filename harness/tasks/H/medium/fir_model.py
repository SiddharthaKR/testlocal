"""
Bit-true golden model of the 8-tap FIR filter (red_pitaya_fir_block).

Definition (must be matched exactly by the hardware):
  taps h0..h7: signed 18-bit, Q2.16 (COEF_FRAC = 16)
  acc  = sum_{k=0..7} h[k] * x[n-k]       (full precision; x[m] = 0 for m < 0, i.e. state starts at zero)
  y[n] = sat14((acc + 2**15) >> 16)       arithmetic shift, round half up
  sat14 clamps to [-8192, 8191]
  x, y: signed 14-bit. No feedback.

CLI:
  fir_model.py taps --fc 8e6 [--fs 125e6]        quantized windowed-sinc lowpass taps (example helper)
  fir_model.py run --in stim.txt --out y.txt (--fc F | --h h0,h1,...,h7)
Files: one signed decimal integer per line.
"""
import argparse
import math

COEF_FRAC = 16
COEF_BITS = 18
DATA_BITS = 14
NTAPS = 8
FS_DEFAULT = 125e6

DATA_MIN, DATA_MAX = -(1 << (DATA_BITS - 1)), (1 << (DATA_BITS - 1)) - 1
COEF_MIN, COEF_MAX = -(1 << (COEF_BITS - 1)), (1 << (COEF_BITS - 1)) - 1


def sat14(v):
    return DATA_MIN if v < DATA_MIN else DATA_MAX if v > DATA_MAX else v


def lowpass_taps(fc, fs=FS_DEFAULT):
    """Hamming-windowed sinc lowpass, unity DC gain, quantized to Q2.16."""
    m = (NTAPS - 1) / 2.0
    w = []
    for k in range(NTAPS):
        t = k - m
        s = 2 * fc / fs if t == 0 else math.sin(2 * math.pi * fc / fs * t) / (math.pi * t)
        w.append(s * (0.54 - 0.46 * math.cos(2 * math.pi * k / (NTAPS - 1))))
    tot = sum(w)
    q = [int(round(c / tot * (1 << COEF_FRAC))) for c in w]
    return tuple(min(COEF_MAX, max(COEF_MIN, v)) for v in q)


def fir(x, h):
    """Bit-true FIR. x: iterable of ints in [-8192, 8191]; h: 8 ints. Returns list of ints."""
    h = list(h)
    if len(h) != NTAPS:
        raise ValueError("need exactly 8 taps")
    for v in h:
        if not COEF_MIN <= v <= COEF_MAX:
            raise ValueError(f"tap {v} is not signed 18-bit")
    half = 1 << (COEF_FRAC - 1)
    hist = [0] * NTAPS            # hist[k] = x[n-k]
    y = []
    for xn in x:
        xn = int(xn)
        if not DATA_MIN <= xn <= DATA_MAX:
            raise ValueError(f"input sample {xn} is not signed 14-bit")
        hist = [xn] + hist[:-1]
        acc = sum(hk * xk for hk, xk in zip(h, hist))
        y.append(sat14((acc + half) >> COEF_FRAC))   # Python >> is arithmetic
    return y


def read_ints(path):
    with open(path) as f:
        return [int(l) for l in f if l.strip()]


def write_ints(path, vals):
    with open(path, "w") as f:
        f.write("\n".join(str(v) for v in vals) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("taps", help="print quantized lowpass taps")
    r = sub.add_parser("run", help="filter a stimulus file")
    for p in (c, r):
        p.add_argument("--fc", type=float)
        p.add_argument("--fs", type=float, default=FS_DEFAULT)
    r.add_argument("--h", help="h0,...,h7 as integers (Q2.16)")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "run" and a.h:
        h = tuple(int(v) for v in a.h.split(","))
    elif a.fc is not None:
        h = lowpass_taps(a.fc, a.fs)
    else:
        ap.error("give --fc (or --h for run)")

    if a.cmd == "taps":
        for k, v in enumerate(h):
            print(f"h{k} = {v:7d}  (0x{v & 0x3FFFF:05X} as 18-bit)")
    else:
        y = fir(read_ints(a.inp), h)
        write_ints(a.out, y)
        print(f"wrote {len(y)} samples to {a.out} (h {h})")


if __name__ == "__main__":
    main()
