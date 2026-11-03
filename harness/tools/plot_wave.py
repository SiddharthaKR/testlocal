"""plot_wave.py <csv> [col1,col2,...] [--start N] [--len N] [-o out.png]

Plot CSV columns (header row required) against sample index, for quick inspection.
"""
import argparse
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("csv")
ap.add_argument("cols", nargs="?", default="")
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--len", type=int, default=2000)
ap.add_argument("-o", "--out", default=None)
a = ap.parse_args()

with open(a.csv, newline="") as f:
    rows = list(csv.reader(f))
hdr, data = [h.strip() for h in rows[0]], rows[1:]
cols = [c.strip() for c in a.cols.split(",") if c.strip()] or hdr
missing = [c for c in cols if c not in hdr]
if missing:
    raise SystemExit(f"unknown columns {missing}; available: {hdr}")

sl = data[a.start:a.start + a.len]
fig, ax = plt.subplots(figsize=(10, 4))
for c in cols:
    i = hdr.index(c)
    ax.plot(range(a.start, a.start + len(sl)), [float(r[i]) for r in sl], label=c)
ax.set_xlabel("sample"); ax.legend(); ax.grid(alpha=.3)
out = a.out or a.csv.rsplit(".", 1)[0] + ".png"
fig.tight_layout(); fig.savefig(out, dpi=100)
print(f"wrote {out} ({len(sl)} samples, cols {cols})")
