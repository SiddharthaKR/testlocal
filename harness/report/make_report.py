"""
Management report for demo runs (self-contained HTML, opens offline).

  make_report.py <run_dir>     -> <run_dir>/report.html (+ report.md, PNGs)
  make_report.py --summary     -> runs/summary.html across all runs

A run dir holds run_meta.json, judge.json, judge_data/, requests.jsonl
(see run_demo.sh). Missing pieces are shown as "not available", never guessed.
Assisted runs carry an "ASSISTED RUN" banner and are kept out of real results.
"""
import argparse
import base64
import html
import io
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import metrics as M  # noqa: E402

FS = 125e6
TRACK_NAMES = {"H": "New filter block from a spec", "B": "Speed up an existing block", "C": "Bug hunt"}

# validated reference palette (dataviz skill): red/green kept for before/after per the brief,
# always with a text label and distinct line styles
C_BEFORE, C_AFTER, C_MODEL, C_INK, C_MUTED, C_BASE = "#e34948", "#008300", "#0b0b0b", "#0b0b0b", "#52514e", "#2a78d6"

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "axes.labelcolor": C_MUTED, "xtick.color": C_MUTED,
                     "ytick.color": C_MUTED, "axes.titleweight": "bold", "axes.titlesize": 13,
                     "axes.grid": True, "grid.color": "#ecebe7", "grid.linewidth": 0.8, "lines.linewidth": 2})


def esc(s):
    return html.escape(str(s))


def png_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def load_json(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else {}


def fmt_dur(s):
    if s is None:
        return "n/a"
    s = float(s)
    return f"{s / 60:.1f} min" if s >= 90 else f"{s:.0f} s"


# --------------------------------------------------------------------------- Track H
def read_ints(p):
    return np.array([int(l) for l in Path(p).read_text().split()], dtype=float)


def read_dut(p, latency, n):
    y = {}
    for row in Path(p).read_text().splitlines()[1:]:
        cyc, i, x, v = row.split(",")
        try:
            y[int(i)] = float(v)
        except ValueError:
            y[int(i)] = np.nan
    return np.array([y.get(i + latency, np.nan) for i in range(n)])


def spectrum_db(s):
    s = np.nan_to_num(s[len(s) // 2:])            # skip start-up
    win = np.hanning(len(s))
    mag = np.abs(np.fft.rfft(s * win)) / (win.sum() / 2)
    return np.fft.rfftfreq(len(s), 1 / FS), 20 * np.log10(mag / 8192 + 1e-12)


def track_h(run, judge):
    data = Path(run) / "judge_data"
    meta = load_json(data / "cases.json")
    case = next((c for c in meta.get("cases", []) if c["name"].endswith("_sig")), None)
    jcase = next((c for c in judge.get("cases", []) if case and c["name"] == case["name"]), None)
    passed = judge.get("status") == "PASS"
    out = dict(figures=[], headline=None, sub=None)
    if not case or not jcase or not (data / f"dut_{case['name']}.csv").exists():
        st = judge.get("status")
        if st == "COMPILE_ERROR":
            out["headline"] = "The AI's design did not compile"
            out["sub"] = "The Verilog it wrote has syntax errors, so it could not be tested."
        elif st == "JUDGE_ERROR":
            out["headline"] = "The checker failed on this run"
            out["sub"] = "This is a problem in the test setup, not a verdict on the AI. Details are in the technical section."
        elif st == "NO_CANDIDATE":
            out["headline"] = "The AI did not produce a design"
            out["sub"] = f"No {judge.get('module', 'red_pitaya_notch_block')}.v was written."
        else:
            out["headline"] = "The design could not be checked"
            out["sub"] = "The independent checker produced no result."
        return out

    if judge.get("level", "hard") != "hard":
        return track_h_simple(data, case, jcase, judge, passed, out)

    n = case["n"]
    lat = jcase.get("latency") or 0
    x = read_ints(data / "stim" / f"{case['name']}.txt")
    model = read_ints(data / "expected" / f"{case['name']}.txt")
    y = read_dut(data / f"dut_{case['name']}.csv", lat, n)
    t = np.arange(n) / FS
    wanted = case.get("wanted_amp", 2500) * np.sin(2 * np.pi * case.get("f_wanted", case["f0"] / 10) * t)

    f, X = spectrum_db(x)
    _, Y = spectrum_db(y)
    k = int(np.argmin(np.abs(f - case["f0"])))
    w = slice(max(k - 3, 0), k + 4)
    atten = float(X[w].max() - Y[w].max())
    f0_mhz = case["f0"] / 1e6

    if passed:
        out["headline"] = f"Interference reduced by {atten:.0f} dB"
        out["sub"] = (f"The new hardware block removes a {f0_mhz:g} MHz interference tone and matches the "
                      f"design model exactly on {len(judge['cases'])} hidden test signals.")
    else:
        out["headline"] = "The new block did not pass the hidden check"
        out["sub"] = (f"It matched the design model on {judge.get('n_pass', 0)} of {len(judge.get('cases', []))} "
                      f"hidden test signals. Plots below show what the hardware actually produced.")

    show = slice(n // 2, n // 2 + int(4e-6 * FS))
    t_us = t[show] * 1e6
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax[0].plot(t_us, x[show], color=C_BEFORE, lw=1.4, label="signal going in")
    ax[0].plot(t_us, wanted[show], "--", color=C_INK, lw=1.4, label="wanted signal")
    ax[0].set_title("BEFORE: the wanted signal is buried in interference", loc="left")
    ax[1].plot(t_us, y[show], color=C_AFTER, lw=1.4, label="signal coming out")
    ax[1].plot(t_us, wanted[show], "--", color=C_INK, lw=1.4, label="wanted signal")
    ax[1].set_title("AFTER the hardware filter" + (": interference removed" if passed else ""), loc="left")
    for a in ax:
        a.set_ylabel("signal level"); a.set_ylim(-8192, 8191)
    h0, l0 = ax[0].get_legend_handles_labels()
    h1, l1 = ax[1].get_legend_handles_labels()
    fig.legend(h0 + h1[:1], l0 + l1[:1], loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False)
    fig.tight_layout()
    ax[1].set_xlabel("time (microseconds)")
    out["figures"].append((png_b64(fig), "Before the filter the wanted signal (dashed) is hidden under a fast "
                           "interfering tone; after the hardware filter the output follows the wanted signal."
                           if passed else "What went in and what came out of the hardware; the dashed line is "
                           "the signal we want to keep."))

    fig, a = plt.subplots(figsize=(10, 3.6))
    a.plot(f / 1e6, X, color=C_BEFORE, lw=1.2, alpha=0.85, label="before")
    a.plot(f / 1e6, np.maximum(Y, -138), color=C_AFTER, lw=1.6, ls="-", label="after")   # keep silence visible
    if passed:
        a.annotate(f"interference\n{-atten:.0f} dB", xy=(f0_mhz, Y[w].max()), xytext=(f0_mhz + 2.5, -45),
                   arrowprops=dict(arrowstyle="->", color=C_INK), color=C_INK)
    a.set_xlim(0, min(15, max(15, f0_mhz * 1.6))); a.set_ylim(-140, 5)
    a.set_title("Frequency view: the interference spike is removed" if passed else "Frequency view", loc="left")
    a.set_xlabel("frequency (MHz)"); a.set_ylabel("level (dB)"); a.legend(frameon=False)
    silent = bool(np.nanmax(np.abs(np.nan_to_num(y))) == 0)
    out["figures"].append((png_b64(fig), f"Each spike is one tone in the signal; the spike at {f0_mhz:g} MHz "
                           f"(the interference) drops by {atten:.0f} dB while the wanted signal is untouched."
                           if passed else "Each spike is one tone in the signal. " +
                           ("The hardware output is silent (all zero), shown along the bottom." if silent else
                            "Compare the 'before' and 'after' lines; the check failed, so no reduction is claimed.")))

    seg = slice(n // 2, n // 2 + 300)
    fig, a = plt.subplots(figsize=(10, 3.4))
    a.plot(np.arange(n)[seg], model[seg], color=C_BASE, lw=5, alpha=0.35, label="design model (Python)")
    a.plot(np.arange(n)[seg], y[seg], color=C_INK, lw=1.3, label="hardware output")
    exact = bool(np.array_equal(model, y))
    a.set_title("Hardware matches design model exactly" if exact else "Hardware differs from the design model",
                loc="left")
    a.set_xlabel("sample number"); a.set_ylabel("signal level")
    a.legend(frameon=False, loc="lower right", bbox_to_anchor=(1, 1.0), ncol=2)
    out["figures"].append((png_b64(fig), "The hardware output (thin line) lies exactly on top of the design "
                           "model (wide line) for every sample." if exact else
                           "Where the thin line leaves the wide one, the hardware gives a different answer "
                           "from the design model."))
    out["atten_db"] = round(atten, 1) if passed else None
    return out


H_PLAIN = {"easy": ("gain block", "scales and shifts a signal"),
           "medium": ("8-tap filter", "smooths and shapes a signal")}


def track_h_simple(data, case, jcase, judge, passed, out):
    """Easy/medium spec tasks: what goes in/out, and hardware vs design model."""
    what, does = H_PLAIN.get(judge.get("level"), ("block", "processes a signal"))
    n_cases, n_pass = len(judge.get("cases", [])), judge.get("n_pass", 0)
    if passed:
        out["headline"] = f"New {what} matches the design exactly"
        out["sub"] = (f"The AI wrote a {what} that {does}. On {n_cases} hidden test signals, its output "
                      f"is identical to the design model, sample for sample.")
    else:
        out["headline"] = f"The new {what} did not pass the hidden check"
        out["sub"] = (f"It matched the design model on {n_pass} of {n_cases} hidden test signals. "
                      f"The plots show what the hardware actually produced.")
    n = case["n"]
    lat = jcase.get("latency") or 0
    x = read_ints(data / "stim" / f"{case['name']}.txt")
    model = read_ints(data / "expected" / f"{case['name']}.txt")
    y = read_dut(data / f"dut_{case['name']}.csv", lat, n)
    seg = slice(n // 2, n // 2 + 300)
    k = np.arange(n)[seg]
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True)
    ax[0].plot(k, x[seg], color=C_BEFORE, lw=1.3)
    ax[0].set_title("Signal going in", loc="left")
    ax[1].plot(k, y[seg], color=C_AFTER, lw=1.3)
    ax[1].set_title("Signal coming out of the AI's hardware", loc="left")
    for a in ax:
        a.set_ylabel("signal level"); a.set_ylim(-8192, 8191)
    ax[1].set_xlabel("sample number"); fig.tight_layout()
    out["figures"].append((png_b64(fig), f"One of the hidden test signals before and after the {what}."))
    fig, a = plt.subplots(figsize=(10, 3.4))
    a.plot(k, model[seg], color=C_BASE, lw=5, alpha=0.35, label="design model (Python)")
    a.plot(k, y[seg], color=C_INK, lw=1.3, label="hardware output")
    exact = bool(np.array_equal(model, y))
    a.set_title("Hardware matches design model exactly" if exact else "Hardware differs from the design model",
                loc="left")
    a.set_xlabel("sample number"); a.set_ylabel("signal level")
    a.legend(frameon=False, loc="lower right", bbox_to_anchor=(1, 1.0), ncol=2)
    out["figures"].append((png_b64(fig), "The hardware output (thin line) lies exactly on top of the design "
                           "model (wide line) for every sample." if exact else
                           "Where the thin line leaves the wide one, the hardware gives a different answer "
                           "from the design model."))
    return out


# --------------------------------------------------------------------------- Track B
def track_b(run, judge):
    out = dict(figures=[], headline=None, sub=None)
    # the run records the baseline it was judged against; fall back to the current one
    base = load_json(Path(run) / "baseline.json") or load_json(ROOT / "harness" / "tasks" / "B" / "baseline.json")
    cand = load_json(Path(run) / "impl.json")
    cyc = judge.get("coverage", {}).get("compared")
    if judge.get("status") == "PASS":
        lat = judge.get("latency", 0)
        out["sub"] = (f"Same behaviour as the original over {cyc:,} random test cycles"
                      + (f", with {lat} extra clock cycle{'s' if lat != 1 else ''} of delay." if lat else "."))
    else:
        out["sub"] = (f"Over {cyc:,} random test cycles its output differed from the original design."
                      if cyc else "The optimized block could not be checked against the original design.")

    have_qor = cand.get("status") == "OK" and base.get("LUT") is not None
    if have_qor:
        fb, fc = base.get("Fmax_MHz"), cand.get("Fmax_MHz")
        out["headline"] = (f"Max speed {fb:.0f} → {fc:.0f} MHz" if judge.get("status") == "PASS"
                           else "Optimization changed the behaviour")
        labels = ["logic cells", "storage cells", "multipliers"]
        keys = ["LUT", "FF", "DSP"]
        bv, cv = [base.get(k) or 0 for k in keys], [cand.get(k) or 0 for k in keys]
        # one scale for all resources: % change vs the original (counts differ by 100x)
        pct = [100.0 * (c - b) / b if b else 0.0 for b, c in zip(bv, cv)]
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.4), gridspec_kw=dict(width_ratios=[3, 1.4]))
        ys = np.arange(len(keys))[::-1]
        ax[0].barh(ys, pct, 0.55, color=C_BASE)
        ax[0].axvline(0, color=C_MUTED, lw=1)
        lim = max(10.0, max(abs(p) for p in pct) * 1.6)
        ax[0].set_xlim(-lim, lim); ax[0].grid(axis="y", visible=False)
        ax[0].set_yticks(ys, [f"{l}\n{b_} → {c_}  ({p_:+.0f}%)" for l, b_, c_, p_ in zip(labels, bv, cv, pct)])
        ax[0].set_xlabel("change vs original (%)  ·  left = uses less")
        ax[0].set_title("Resources used", loc="left")
        ax[1].bar([0, 1], [fb, fc], 0.6, color=["#c3c2b7", C_BASE])
        ax[1].set_ylim(0, max(fb, fc) * 1.18); ax[1].grid(axis="x", visible=False)
        ax[1].set_xticks([0, 1], ["original", "optimized"]); ax[1].set_title("Max speed (MHz)", loc="left")
        for i, v in enumerate([fb, fc]):
            ax[1].text(i, v, f"{v:.0f}", ha="center", va="bottom", color=C_INK)
        out["figures"].append((png_b64(fig), "Left: how much more or less of the chip the optimized version uses, "
                               "per kind of resource; right: the fastest clock each version can run at "
                               "(higher is better)."))
    elif judge.get("status") == "NO_CHANGE":
        out["headline"] = "The AI did not change the design"
        out["sub"] = "The block is unchanged, so there is no optimization to check."
    elif judge.get("status") == "COMPILE_ERROR":
        out["headline"] = "The AI's modified design did not compile"
        out["sub"] = "The Verilog it changed has syntax errors, so its behaviour could not be compared."
    elif judge.get("status") == "JUDGE_ERROR":
        out["headline"] = "The checker could not grade this design"
        out["sub"] = "The equivalence check crashed or saw no valid outputs (often unknown/X values from the design)."
    else:
        out["headline"] = ("Same behaviour, speed not measured" if judge.get("status") == "PASS"
                           else "Optimization changed the behaviour")
        out["note"] = "Resource and speed measurement needs the FPGA vendor tools, which are not installed here."
    return out


CLASS_WORDS = {"sign": "wrong sign", "saturation_polarity": "limits swapped", "slice_off_by_one": "wrong bits used",
               "blocking_assignment": "timing mix-up", "removed_pipeline_register": "missing delay stage",
               "missing_reset": "no start-up value"}


def track_c(run, judge):
    if not judge or "found" not in judge:
        return dict(figures=[], headline="Bug hunt result not available", sub="")
    meta = load_json(Path(run) / "run_meta.json")
    f, n, fp = judge["found"], judge["n_bugs"], judge["false_positives"]
    took = f" in {fmt_dur(meta['wall_seconds'])}" if meta.get("wall_seconds") else ""
    out = dict(figures=[], headline=f"Found {f} of {n} bugs{took}",
               sub=f"{n} bugs were hidden in {len(judge.get('review_files') or []) or 'several'} real FPGA source files. "
                   f"The AI also raised {fp} false "
                   f"alarm{'s' if fp != 1 else ''}." + (" Its answer file could not be read."
                                                        if judge.get("status") == "INVALID_OUTPUT" else ""))
    bugs = judge["per_bug"]
    cols = 5
    rows = (len(bugs) + cols - 1) // cols
    fig, a = plt.subplots(figsize=(10, 1.25 * rows + 0.9))
    for k, b in enumerate(bugs):
        x, y = k % cols, rows - 1 - k // cols
        a.add_patch(plt.Rectangle((x + 0.04, y + 0.06), 0.92, 0.88, color=C_AFTER if b["found"] else "#e2e1dc"))
        a.text(x + 0.5, y + 0.62, "FOUND" if b["found"] else "missed", ha="center", va="center", fontsize=11,
               fontweight="bold", color="white" if b["found"] else C_MUTED)
        a.text(x + 0.5, y + 0.3, CLASS_WORDS.get(b["cls"], b["cls"]), ha="center", va="center", fontsize=9.5,
               color="white" if b["found"] else C_MUTED)
    a.set_xlim(0, cols); a.set_ylim(0, rows); a.axis("off")
    a.set_title(f"Found {f} of {n} bugs" + (f"  ·  {fp} false alarm{'s' if fp != 1 else ''}" if fp else ""),
                loc="left")
    png = png_b64(fig)
    (Path(run) / "bughunt.png").write_bytes(png)
    out["figures"].append((png, "Each box is one hidden bug; green boxes were found by the AI, grey "
                           "ones were missed. The label says what kind of mistake it was."))
    out["status_override"] = "SCORED"
    return out


def time_figure(track, agent_s):
    est = yaml.safe_load((ROOT / "config" / "engineer_estimates.yaml").read_text()) or {}
    hrs = est.get(track)
    if not hrs or not agent_s:
        return None
    fig, a = plt.subplots(figsize=(10, 1.9))
    vals = [agent_s / 3600, float(hrs)]
    a.barh([1, 0], vals, 0.55, color=[C_BASE, "#c3c2b7"])
    a.set_yticks([1, 0], ["AI agent (measured)", "engineer estimate"])
    for i, v in zip([1, 0], vals):
        a.text(v, i, f"  {v:.1f} h", va="center", color=C_INK)
    a.set_xlabel("hours"); a.grid(axis="y", visible=False)
    a.set_title("Time to finish the task", loc="left")
    return png_b64(fig), "How long the AI agent took, next to an engineer's estimate for doing the same task by hand."


# --------------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#f6f5f2;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e2e1dc;--ok:#008300;--bad:#c62f2e;
--warnbg:#fff2cc;--warnink:#5c4100;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121211;--card:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--line:#33322f;--ok:#3fa53f;--bad:#e66767;--warnbg:#4a3a00;--warnink:#ffe7a3;--accent:#3987e5}}
:root[data-theme="dark"]{--bg:#121211;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#33322f;--ok:#3fa53f;
--bad:#e66767;--warnbg:#4a3a00;--warnink:#ffe7a3;--accent:#3987e5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:15px;font-weight:600;color:var(--ink2);margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em}
.headline{font-size:clamp(28px,5vw,44px);font-weight:700;line-height:1.15;margin:6px 0 8px}
.sub{color:var(--ink2);font-size:18px;margin:0 0 20px}
.verdict{display:inline-block;font-weight:700;font-size:14px;padding:3px 10px;border-radius:999px;border:1.5px solid}
.pass{color:var(--ok)}.fail{color:var(--bad)}
.banner{background:var(--warnbg);color:var(--warnink);font-weight:700;padding:10px 16px;border-radius:8px;
margin-bottom:18px;letter-spacing:.04em}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
.card img{width:100%;height:auto;display:block;border-radius:6px;background:#fff}
.cap{color:var(--ink2);margin:10px 2px 0;font-size:15px}
.note{color:var(--ink2);font-style:italic}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.tile .headline{font-size:26px}
details{margin-top:28px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 16px}
summary{cursor:pointer;font-weight:600;color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
td,th{border-bottom:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600}
.grid td,.grid th{text-align:center;padding:12px 8px}.grid th.task{text-align:left;font-size:15px;color:var(--ink)}
.grid .big{font-size:20px;font-weight:700}.grid .small{color:var(--ink2);font-size:13px}
.grid td.good{background:color-mix(in srgb,var(--ok) 12%,transparent)}
.grid td.bad{background:color-mix(in srgb,var(--bad) 9%,transparent)}.grid td.empty{color:var(--ink2)}
h2.model{font-size:16px;margin:22px 0 4px}
code,pre{font:13px ui-monospace,Consolas,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere}
a{color:var(--accent)}.scroll{overflow-x:auto}
"""


def page(title, body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>")


def kv_table(rows):
    return "<div class='scroll'><table>" + "".join(
        f"<tr><th>{esc(k)}</th><td>{esc("n/a" if v is None else v)}</td></tr>" for k, v in rows) + "</table></div>"


def run_report(run):
    run = Path(run)
    meta, judge = load_json(run / "run_meta.json"), load_json(run / "judge.json")
    track = meta.get("track") or judge.get("track")
    assist = bool(meta.get("assist") or judge.get("assist"))
    met = M.compute(run)
    builder = {"H": track_h, "B": track_b, "C": track_c}.get(track)
    if builder is None:
        raise SystemExit(f"{run}: unknown track {track!r}")
    r = builder(run, judge)
    status = judge.get("status", "NO RESULT")
    leak = load_json(run / "leak_check.json")

    tf = time_figure(track, meta.get("wall_seconds"))
    if tf:
        r["figures"].append(tf)

    b = []
    if assist:
        b.append("<div class='banner'>ASSISTED RUN: the agent was given a partly written starting file. "
                 "Not a real result.</div>")
    if meta.get("demo_model") is False:
        b.append(f"<div class='banner'>PLUMBING TEST: model {esc(meta.get('model'))} is not the demo model. "
                 "Not a demo result.</div>")
    if meta.get("agent_timed_out"):
        b.append("<div class='banner'>The agent ran out of time and was stopped.</div>")
    if leak.get("leak_suspected"):
        b.append("<div class='banner'>INVALID RUN: the agent saw hidden test material.</div>")
    b.append(f"<h1>Track {esc(track)}: {esc(TRACK_NAMES.get(track, ''))} · "
             f"{esc(meta.get('level', judge.get('level', 'hard')).capitalize())} level</h1>")
    b.append(f"<div class='headline'>{esc(r['headline'])}</div>")
    b.append(f"<p class='sub'>{r['sub']}</p>")
    if track == "C" and "found" in judge:
        b.append(f"<span class='verdict pass'>Independent score: {judge['found']} of {judge['n_bugs']}</span>")
    else:
        cls = "pass" if status == "PASS" else "fail"
        b.append(f"<span class='verdict {cls}'>Independent check: {'PASSED' if status == 'PASS' else 'FAILED'}</span>")
    if r.get("note"):
        b.append(f"<p class='note'>{esc(r['note'])}</p>")
    for png, cap in r["figures"]:
        b.append(f"<div class='card'><img alt='{esc(cap)}' src='data:image/png;base64,"
                 f"{base64.b64encode(png).decode()}'><p class='cap'>{esc(cap)}</p></div>")

    rows = [("run", run.name), ("model", meta.get("model", "n/a")), ("assisted", assist),
            ("judge status", status), ("wall time", fmt_dur(meta.get("wall_seconds"))),
            ("LLM time", fmt_dur(met["llm_seconds"])), ("Vivado time", fmt_dur(meta.get("vivado_seconds"))),
            ("requests", met["n_requests"]), ("total tokens", f"{met['total_tokens']:,}"),
            ("peak prompt tokens", f"{met['peak_prompt_tokens']:,} of {met['context_limit']:,} context "
                                   f"({met['peak_context_pct']}%)" if met["context_limit"] else met["peak_prompt_tokens"]),
            ("requests above 90% of context", met["n_near_limit"]),
            ("token counts estimated", met["usage_estimated"]), ("human hints", met["n_hints"]),
            ("leak check", "leak suspected" if leak.get("leak_suspected") else
             (f"clean ({leak.get('n_access_attempts', 0)} access attempts)" if leak else "not run")),
            ("pyrpl commit", meta.get("pyrpl_commit", "n/a"))]
    if track == "H":
        rows += [("latency (cycles)", judge.get("latency")), ("interference reduction (dB)", r.get("atten_db"))]
        rows += [(f"case {c['name']}", f"{'PASS' if c['pass'] else 'FAIL'} lat={c.get('latency')} "
                  f"match={c.get('n_match')}/{c.get('n_compared')} first_mismatch={c.get('first_mismatch')}")
                 for c in judge.get("cases", [])]
        rows += [(f"check {k}", f"{'PASS' if v['pass'] else 'FAIL'} {v['detail']}")
                 for k, v in judge.get("checks", {}).items()]
    if track == "B":
        rows += [("latency (cycles)", judge.get("latency")),
                 ("phase cost at 1 MHz (deg)", judge.get("phase_cost_deg_at_1MHz")),
                 ("coverage", judge.get("coverage")), ("readback", judge.get("readback")),
                 ("reasons", "; ".join(judge.get("reasons", [])) or "none")]
    if track == "C":
        rows += [("found / seeded", f"{judge.get('found')} / {judge.get('n_bugs')}"),
                 ("false positives", judge.get("false_positives")), ("duplicates", judge.get("duplicates")),
                 ("near misses (right line, explanation does not name the bug)", judge.get("near_misses")),
                 ("known upstream issues reported", judge.get("known_upstream")),
                 ("line match window", f"±{judge.get('match_window')}"),
                 ("input warning", judge.get("input_warning") or "none")]
        rows += [(f"bug {p['id']}", f"{'FOUND' if p['found'] else 'missed'}  {p['file']}:{p['line']}  ({p['cls']})")
                 for p in judge.get("per_bug", [])]
        rows += [(f"report {r['file']}:{r['line']}", f"{r['verdict']}: {r['description']}")
                 for r in judge.get("reports", [])[:40]]
    if judge.get("error"):
        rows.append(("judge error", judge["error"]))
    rows += [("judge seed", judge.get("seed")), ("judge seconds", judge.get("judge_seconds"))]
    b.append("<details><summary>Technical details (for engineers)</summary>" + kv_table(rows) + "</details>")

    title = f"Track {track} {'(assisted) ' if assist else ''}report"
    (run / "report.html").write_text(page(title, "\n".join(b)), encoding="utf-8")
    (run / "report.md").write_text(f"# {title}\n\n**{r['headline']}**\n\n{html.unescape(r['sub'])}\n\n"
                                   f"Judge: {status}\n", encoding="utf-8")
    return dict(track=track, assist=assist, status=status, headline=r["headline"], run=run.name,
                found=judge.get("found"), n_bugs=judge.get("n_bugs"),
                plumbing=meta.get("demo_model") is False,
                level=meta.get("level", "hard"), model=meta.get("model", "?"),
                wall_seconds=meta.get("wall_seconds"), total_tokens=met["total_tokens"],
                peak_context_pct=met["peak_context_pct"], leak=bool(leak.get("leak_suspected")))


def summary(runs_dir):
    runs_dir = Path(runs_dir)
    res = []
    for d in sorted(p for p in runs_dir.iterdir() if (p / "run_meta.json").exists()):
        try:
            res.append(run_report(d))
        except Exception as e:   # one broken run must not hide the others
            res.append(dict(run=d.name, track=load_json(d / "run_meta.json").get("track"), status="REPORT_ERROR",
                            headline=f"report failed: {e}", assist=False, total_tokens=0, wall_seconds=None,
                            peak_context_pct=None, leak=False))
    LEVELS = ("easy", "medium", "hard")

    def cell(runs, t):
        """One plain-language result for a (track, level) group of real runs."""
        if not runs:
            return "<td class='empty'>not run yet</td>"
        wt = [r["wall_seconds"] for r in runs if r["wall_seconds"]]
        tm = f"<div class='small'>{len(runs)} run{'s' if len(runs) != 1 else ''}" +              (f" · median {fmt_dur(statistics.median(wt))}" if wt else "") + "</div>"
        if t == "C":
            fs = [r["found"] for r in runs if r.get("found") is not None]
            big = f"{statistics.median(fs):g} of {runs[-1]['n_bugs']} bugs found" if fs else "no score"
            ok = bool(fs) and statistics.median(fs) >= runs[-1]["n_bugs"] / 2
        else:
            npass = sum(r["status"] == "PASS" for r in runs)
            big = f"{npass} of {len(runs)} {'kept behaviour' if t == 'B' else 'passed'}"
            ok = npass > 0
        return f"<td class='{'good' if ok else 'bad'}'><div class='big'>{esc(big)}</div>{tm}</td>"

    def real(r):
        return not r["assist"] and not r["leak"] and not r.get("plumbing") and             r["status"] not in ("JUDGE_ERROR", "REPORT_ERROR")

    b = ["<h1>AI-assisted FPGA development: summary of all runs</h1>",
         "<p class='sub'>Three tasks, each at three difficulty levels. Each cell counts every real run "
         "(never just the best one). Assisted, test-setup and invalid runs are listed below but not counted.</p>"]
    for model in sorted({r.get("model", "?") for r in res if real(r)}):
        b.append(f"<h2 class='model'>Model: {esc(model)}</h2><div class='card scroll'><table class='grid'>"
                 "<tr><th></th>" + "".join(f"<th>{lv.capitalize()}</th>" for lv in LEVELS) + "</tr>")
        for t in ("H", "B", "C"):
            row = [r for r in res if r["track"] == t and real(r) and r.get("model", "?") == model]
            b.append(f"<tr><th class='task'>{esc(TRACK_NAMES[t])}</th>" +
                     "".join(cell([r for r in row if r.get("level", "hard") == lv], t) for lv in LEVELS) + "</tr>")
        b.append("</table></div>")
    if not any(real(r) for r in res):
        b.append("<p class='note'>No real runs yet.</p>")
    b.append("<p class='note'>Speed and size results for “Speed up an existing block” need the FPGA vendor "
             "tools; without them the check confirms the behaviour is unchanged.</p>")
    rows = "".join(
        f"<tr><td><a href='{esc(r['run'])}/report.html'>{esc(r['run'])}</a></td>"
        f"<td>{esc(r['track'])} · {esc(r.get('level', 'hard'))}</td>"
        f"<td>{'ASSISTED' if r['assist'] else ('INVALID' if r['leak'] else 'PLUMBING' if r.get('plumbing') else 'real')}</td>"
        f"<td class='{'pass' if r['status'] == 'PASS' else '' if r['status'] == 'SCORED' else 'fail'}'>"
        f"{esc(r['status'] if r['status'] != 'SCORED' else str(r['found']) + '/' + str(r['n_bugs']))}</td>"
        f"<td>{esc(r['headline'])}</td></tr>" for r in res)
    b.append("<div class='card scroll'><table><tr><th>run</th><th>track</th><th>kind</th><th>check</th>"
             f"<th>result</th></tr>{rows}</table></div>")
    tech = "".join(f"<tr><td>{esc(r['run'])}</td><td>{r['total_tokens']:,}</td><td>{esc(r['peak_context_pct'])}%"
                   f"</td><td>{fmt_dur(r['wall_seconds'])}</td></tr>" for r in res)
    b.append("<details><summary>Technical details (for engineers)</summary><div class='scroll'><table>"
             f"<tr><th>run</th><th>tokens</th><th>peak context</th><th>wall time</th></tr>{tech}</table></div>"
             "</details>")
    (runs_dir / "summary.html").write_text(page("Demo summary", "\n".join(b)), encoding="utf-8")
    return runs_dir / "summary.html"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows console is cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    a = ap.parse_args()
    if a.summary:
        print(f"wrote {summary(a.runs)}")
    elif a.run_dir:
        r = run_report(a.run_dir)
        print(f"wrote {Path(a.run_dir) / 'report.html'}: {r['headline']}")
    else:
        ap.error("give a run dir or --summary")
