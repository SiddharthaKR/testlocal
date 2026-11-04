# CANARY-b81aed453118 (hidden file marker)
"""
Compare DUT output against the bit-true model with latency search.

DUT CSV (written by the judge testbench), header "cyc,n,x,y":
  cyc = clock cycles since rstn_i was released
  n   = stimulus index (0 = first sample driven); rows continue after the
        stimulus ends (input held at 0) so output latency can be absorbed
  y   = dat_o as signed decimal, or "x"/"z" if unknown

Rules:
  - rows with cyc < SETTLE_CYCLES are ignored (common.SETTLE_CYCLES)
  - any X/Z in y after the settle window -> FAIL (no_x)
  - PASS if some latency k in [0, MAX_LATENCY] gives dut_y[n+k] == expected[n]
    for every stimulus sample n
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SETTLE_CYCLES  # noqa: E402

MAX_LATENCY = 4


def load_dut_csv(path):
    """Return (ys by n, x_count). ys[n] is int or None for X/Z."""
    ys, n_x = {}, 0
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["cyc"]) < SETTLE_CYCLES:
                continue
            v = row["y"].strip().lower()
            if "x" in v or "z" in v:
                ys[int(row["n"])] = None
                n_x += 1
            else:
                ys[int(row["n"])] = int(v)
    return ys, n_x


def compare(expected, ys, n_x, max_latency=None):
    n = len(expected)
    best = None
    for k in range((MAX_LATENCY if max_latency is None else max_latency) + 1):
        got = [ys.get(i + k) for i in range(n)]
        bad = [i for i in range(n) if got[i] != expected[i]]
        r = dict(latency=k, n_match=n - len(bad), n_compared=n,
                 first_mismatch=None if not bad else
                 dict(n=bad[0], expected=expected[bad[0]], got=got[bad[0]]))
        if best is None or r["n_match"] > best["n_match"]:
            best = r
        if not bad:
            break
    best["no_x"] = n_x == 0
    best["n_x"] = n_x
    best["pass"] = best["n_match"] == n and best["no_x"]
    return best


def compare_files(expected_txt, dut_csv, max_latency=None):
    with open(expected_txt) as f:
        expected = [int(l) for l in f if l.strip()]
    ys, n_x = load_dut_csv(dut_csv)
    return compare(expected, ys, n_x, max_latency)


if __name__ == "__main__":
    import json
    print(json.dumps(compare_files(sys.argv[1], sys.argv[2]), indent=1))
