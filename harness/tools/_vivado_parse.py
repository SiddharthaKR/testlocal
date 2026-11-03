"""Parse Vivado reports into JSON (stdout). Called by _vivado.sh.
argv: mode dir top period_ns vivado_rc seconds
"""
import json
import re
import sys
from pathlib import Path

mode, d, top, period, rc, secs = sys.argv[1:7]
d, period = Path(d), float(period)


def read(name):
    p = d / name
    return p.read_text(errors="replace") if p.exists() else ""


def util(rpt, *names):
    # rows like "| Slice LUTs | 123 | 0 | ..." -> first number after the name
    for n in names:
        m = re.search(r"^\|\s*" + re.escape(n) + r"\*?\s*\|\s*(\d+)", rpt, re.M)
        if m:
            return int(m.group(1))
    return None


u = read("utilization.rpt")
t = read("timing_summary.rpt")
res = {
    "status": "OK" if rc == "0" else "ERROR",
    "top": top, "mode": mode, "period_ns": period, "vivado_seconds": int(secs),
    "LUT": util(u, "Slice LUTs", "CLB LUTs"),
    "FF": util(u, "Slice Registers", "CLB Registers"),
    "DSP": util(u, "DSPs", "DSP48E1"),
    "CARRY4": util(u, "CARRY4"),
    "WNS": None,
}
# Design Timing Summary table: the first numeric row is WNS TNS ...
m = re.search(r"WNS\(ns\).*?\n[-\s]+\n\s*(-?\d+\.\d+)", t, re.S)
if m:
    res["WNS"] = float(m.group(1))
    res["Fmax_MHz"] = round(1000.0 / (period - res["WNS"]), 1)
    res["timing_met"] = res["WNS"] >= 0

if mode == "impl":
    paths = []
    for blk in read("paths.rpt").split("Slack")[1:6]:
        g = lambda pat: (re.search(pat, blk) or [None, None])[1]
        paths.append({"slack": g(r"^\s*\(?\w*\)?\s*:\s*(-?[\d.]+)ns"),
                      "source": g(r"Source:\s+(\S+)"),
                      "dest": g(r"Destination:\s+(\S+)"),
                      "logic_levels": g(r"Logic Levels:\s+(\d+)")})
    res["critical_paths"] = paths

s = [f"{mode.upper()}: {res['status']}  top={top}  ({secs}s)",
     f"  LUT={res['LUT']} FF={res['FF']} DSP={res['DSP']} CARRY4={res['CARRY4']}",
     f"  WNS={res['WNS']} ns @ {period} ns  Fmax={res.get('Fmax_MHz')} MHz  timing_met={res.get('timing_met')}"]
for p in res.get("critical_paths", []):
    s.append(f"  path slack={p['slack']} levels={p['logic_levels']} {p['source']} -> {p['dest']}")
s.append(f"  full reports: {d}/")
res["summary"] = "\n".join(s)
print(json.dumps(res, indent=2))
