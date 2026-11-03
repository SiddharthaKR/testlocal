"""
Bit-true golden model of the notch filter (red_pitaya_notch_block).

Definition (must be matched exactly by the hardware):
  coeffs b0,b1,b2,a1,a2: signed 18-bit, Q2.16 (COEF_FRAC = 16)
  acc  = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]   (full precision)
  y[n] = sat14((acc + 2**15) >> 16)        arithmetic shift, round half up
  sat14 clamps to [-8192, 8191]; the feedback uses the SATURATED y
  x, y: signed 14-bit; state starts at zero

Coefficients from notch frequency f0 and pole radius r:
  w0 = 2*pi*f0/fs,  b = [1, -2cos(w0), 1],  a = [-2r cos(w0), r^2]
  each quantized as round(c * 2**16)

CLI:
  notch_model.py coeffs --f0 5e6 --r 0.99 [--fs 125e6]
  notch_model.py run --in stim.txt --out y.txt (--f0 F --r R | --coeffs b0,b1,b2,a1,a2)
Files: one signed decimal integer per line.
"""
import argparse
import math

COEF_FRAC = 16
COEF_BITS = 18
DATA_BITS = 14
FS_DEFAULT = 125e6

DATA_MIN, DATA_MAX = -(1 << (DATA_BITS - 1)), (1 << (DATA_BITS - 1)) - 1
COEF_MIN, COEF_MAX = -(1 << (COEF_BITS - 1)), (1 << (COEF_BITS - 1)) - 1


def quantize(c):
    q = int(round(c * (1 << COEF_FRAC)))
    if not COEF_MIN <= q <= COEF_MAX:
        raise ValueError(f"coefficient {c} does not fit in {COEF_BITS}-bit Q2.{COEF_FRAC}")
    return q


def notch_coeffs(f0, r, fs=FS_DEFAULT):
    """Return integer coefficients (b0, b1, b2, a1, a2)."""
    w0 = 2 * math.pi * f0 / fs
    return (quantize(1.0), quantize(-2 * math.cos(w0)), quantize(1.0),
            quantize(-2 * r * math.cos(w0)), quantize(r * r))


def sat14(v):
    return DATA_MIN if v < DATA_MIN else DATA_MAX if v > DATA_MAX else v


def notch(x, coeffs):
    """Bit-true filter. x: iterable of ints in [-8192, 8191]. Returns list of ints."""
    b0, b1, b2, a1, a2 = coeffs
    half = 1 << (COEF_FRAC - 1)
    x1 = x2 = y1 = y2 = 0
    y = []
    for xn in x:
        xn = int(xn)
        if not DATA_MIN <= xn <= DATA_MAX:
            raise ValueError(f"input sample {xn} is not signed 14-bit")
        acc = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        yn = sat14((acc + half) >> COEF_FRAC)   # Python >> is arithmetic
        x2, x1, y2, y1 = x1, xn, y1, yn
        y.append(yn)
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
    c = sub.add_parser("coeffs", help="print quantized coefficients")
    r = sub.add_parser("run", help="filter a stimulus file")
    for p in (c, r):
        p.add_argument("--f0", type=float)
        p.add_argument("--r", type=float)
        p.add_argument("--fs", type=float, default=FS_DEFAULT)
    r.add_argument("--coeffs", help="b0,b1,b2,a1,a2 as integers")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "run" and a.coeffs:
        co = tuple(int(v) for v in a.coeffs.split(","))
    elif a.f0 is not None and a.r is not None:
        co = notch_coeffs(a.f0, a.r, a.fs)
    else:
        ap.error("give --f0 and --r (or --coeffs for run)")

    if a.cmd == "coeffs":
        for name, v in zip(("b0", "b1", "b2", "a1", "a2"), co):
            print(f"{name} = {v:7d}  (0x{v & 0x3FFFF:05X} as 18-bit)")
    else:
        y = notch(read_ints(a.inp), co)
        write_ints(a.out, y)
        print(f"wrote {len(y)} samples to {a.out} (coeffs {co})")


if __name__ == "__main__":
    main()
