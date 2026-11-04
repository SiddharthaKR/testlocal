"""
Bit-true golden model of the gain block (red_pitaya_gain_block).

Definition (must be matched exactly by the hardware):
  gain:   signed 16-bit integer          (-32768 .. 32767)
  shift:  unsigned 4-bit integer         (0 .. 15)
  offset: signed 14-bit integer          (-8192 .. 8191)
  p = x * gain                           (full precision, no overflow)
  r = (p + (1 << (shift-1) if shift > 0 else 0)) >> shift     arithmetic shift, round half up
  y = sat14(r + offset)                  sat14 clamps to [-8192, 8191]
  x, y: signed 14-bit. No state: every output depends only on its own input sample.

CLI:
  gain_model.py run --in stim.txt --out y.txt --gain G --shift S --offset O
Files: one signed decimal integer per line.
"""
import argparse

DATA_BITS = 14
DATA_MIN, DATA_MAX = -(1 << (DATA_BITS - 1)), (1 << (DATA_BITS - 1)) - 1
GAIN_MIN, GAIN_MAX = -(1 << 15), (1 << 15) - 1
OFFS_MIN, OFFS_MAX = DATA_MIN, DATA_MAX
SHIFT_MIN, SHIFT_MAX = 0, 15
GAIN_BITS = 16


def sat14(v):
    return DATA_MIN if v < DATA_MIN else DATA_MAX if v > DATA_MAX else v


def gain_block(x, gain, shift, offset):
    """Bit-true output. x: iterable of ints in [-8192, 8191]. Returns list of ints."""
    if not GAIN_MIN <= gain <= GAIN_MAX:
        raise ValueError(f"gain {gain} is not signed 16-bit")
    if not SHIFT_MIN <= shift <= SHIFT_MAX:
        raise ValueError(f"shift {shift} is not in 0..15")
    if not OFFS_MIN <= offset <= OFFS_MAX:
        raise ValueError(f"offset {offset} is not signed 14-bit")
    half = (1 << (shift - 1)) if shift > 0 else 0
    y = []
    for xn in x:
        xn = int(xn)
        if not DATA_MIN <= xn <= DATA_MAX:
            raise ValueError(f"input sample {xn} is not signed 14-bit")
        p = xn * gain
        r = (p + half) >> shift          # Python >> is arithmetic
        y.append(sat14(r + offset))
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
    r = sub.add_parser("run", help="process a stimulus file")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--gain", type=int, required=True)
    r.add_argument("--shift", type=int, required=True)
    r.add_argument("--offset", type=int, default=0)
    a = ap.parse_args()
    y = gain_block(read_ints(a.inp), a.gain, a.shift, a.offset)
    write_ints(a.out, y)
    print(f"wrote {len(y)} samples to {a.out} (gain {a.gain}, shift {a.shift}, offset {a.offset})")


if __name__ == "__main__":
    main()
