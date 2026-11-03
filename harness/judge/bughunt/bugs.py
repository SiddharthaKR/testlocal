# CANARY-b81aed453118 (hidden file marker)
"""
Track C seeded bugs: single source of truth.

  bugs.py build <out_rtl_dir>   write the review set (patched modules + unchanged deps)
  bugs.py key                   regenerate answer_key.yaml and patches/*.diff

Every bug is a one-line replacement, so line numbers in the patched files equal
the original ones (the scorer matches within +-3 lines).
"""
import difflib
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENV = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
RTL = ROOT / str(ENV["pyrpl_repo"]) / str(ENV["pyrpl_rtl"])

# files the agent reviews (bugs live here)
REVIEW = ["red_pitaya_pid_block.v", "red_pitaya_filter_block.v", "red_pitaya_lpf_block.v",
          "red_pitaya_iq_block.v", "red_pitaya_asg_ch.v"]
# unchanged dependencies so the review set compiles
DEPS = ["red_pitaya_iq_fgen_block.v", "red_pitaya_iq_demodulator_block.v", "red_pitaya_iq_modulator_block.v",
        "red_pitaya_pfd_block.v", "red_pitaya_product_sat.v", "red_pitaya_saturate.v"]

# (id, file, line, old, new, class, description, keywords)
# keywords: a report only counts as FOUND if its description mentions one of them
# (case-insensitive); right line + wrong explanation is a near miss.
BUGS = [
    ("pid_error_sign", "red_pitaya_pid_block.v", 205,
     "$signed(dat_i_filtered) - $signed(set_sp)", "$signed(set_sp) - $signed(dat_i_filtered)",
     "sign", "error computed as setpoint minus input (sign inverted vs differential branch and PID convention)",
     ['sign', 'invert', 'revers', 'negat', 'setpoint minus', 'opposite', 'polarity', 'swapped operands']),
    ("pid_sat_polarity", "red_pitaya_pid_block.v", 317,
     "pid_out <= 14'h1FFF;", "pid_out <= 14'h2000;",
     "saturation_polarity", "positive overflow saturates to the most negative value 0x2000",
     ['polarity', '2000', 'most negative', 'opposite', 'wrong rail', 'wrong limit', 'swap', 'invert', 'wrong value', 'negative rail', 'min instead', 'minimum instead']),
    ("filter_on_bit", "red_pitaya_filter_block.v", 81,
     ".filter_on(set_filter[j*8+7])", ".filter_on(set_filter[j*8+6])",
     "slice_off_by_one", "filter_on reads bit 6 (the highpass bit) instead of bit 7",
     ['bit 6', 'bit 7', 'highpass', 'high-pass', 'wrong bit', '+6', 'off-by-one', 'off by one']),
    ("lpf_yout_slice", "red_pitaya_lpf_block.v", 100,
     "y[MAXSHIFT+SIGNALBITS-1:MAXSHIFT]", "y[MAXSHIFT+SIGNALBITS-2:MAXSHIFT-1]",
     "slice_off_by_one", "output slice shifted down one bit: drops the sign bit and doubles the output",
     ['sign bit', 'slice', 'off-by-one', 'off by one', 'wrong bits', 'msb', 'doubl', 'factor of 2', 'factor of two', '-2:', 'maxshift-1']),
    ("lpf_blocking", "red_pitaya_lpf_block.v", 109,
     "delta <= signal_i - y_out;", "delta = signal_i - y_out;",
     "blocking_assignment", "blocking '=' in clocked block: y uses the new delta in the same cycle",
     ['blocking']),
    ("asg_pipeline_removed", "red_pitaya_asg_ch.v", 116,
     "$signed(dac_rdat) * $signed({1'b0,set_amp_i})", "$signed(dac_rd) * $signed({1'b0,set_amp_i})",
     "removed_pipeline_register", "multiplier fed from dac_rd, bypassing the dac_rdat timing register",
     ['dac_rd ', 'dac_rd)', 'dac_rdat', 'pipeline', 'bypass', 'skips the register', 'register stage', 'delay stage']),
    ("asg_sat_polarity", "red_pitaya_asg_ch.v", 121,
     "{dac_sum[15-1], {13{~dac_sum[15-1]}}}", "{~dac_sum[15-1], {13{dac_sum[15-1]}}}",
     "saturation_polarity", "output saturation inverted: overflow clamps to the opposite rail",
     ['polarity', 'invert', 'opposite', 'swap', 'wrong rail', 'wrong limit', 'revers', 'wrong direction']),
    ("asg_rep_cnt_reset", "red_pitaya_asg_ch.v", 146,
     "rep_cnt   <= 16'h0 ;", "",
     "missing_reset", "rep_cnt is not reset",
     ['reset', 'uninitiali', 'initial value', 'not initiali']),
    ("iq_cfg_slice", "red_pitaya_iq_block.v", 128,
     "<= wdata[6-1:1];", "<= wdata[5-1:0];",
     "slice_off_by_one", "config bits taken from wdata[4:0] instead of wdata[5:1] (all flags shifted by one)",
     ['slice', 'off-by-one', 'off by one', 'wdata[4', 'wdata[5', 'shifted', 'wrong bit', 'misalign', '[5-1:0]', '[6-1:1]']),
    ("iq_sum_sign", "red_pitaya_iq_block.v", 327,
     "iq_i_sum <= iq_i_sum + quadrature1;", "iq_i_sum <= iq_i_sum - quadrature1;",
     "sign", "I averaging accumulates -quadrature1 (Q path still adds)",
     ['sign', 'subtract', 'minus', 'negat', 'invert', '-quadrature', 'instead of add']),
]

# Real upstream issues, present before seeding. Reports here are neither found nor false positives.
PREEXISTING = [
    ("red_pitaya_pid_block.v", 104, 109, "pause_* used as implicit wires"),
    ("red_pitaya_pid_block.v", 122, 122, "set_ival reset width"),
    ("red_pitaya_pid_block.v", 141, 142, "out_min/out_max assigned from 32-bit wdata"),
    ("red_pitaya_pid_block.v", 244, 244, "ki_mult reset width"),
    ("red_pitaya_pid_block.v", 250, 250, "zero-width replication"),
    ("red_pitaya_pid_block.v", 267, 296, "kd_reg_s re-declared in generate; module-level net undriven"),
    ("red_pitaya_pid_block.v", 325, 325, "pid_sum uses undriven kd_reg_s"),
    ("red_pitaya_pid_block.v", 332, 340, "out_buffer has no reset"),
    ("red_pitaya_filter_block.v", 80, 80, "5-bit shift into 6-bit port"),
    ("red_pitaya_iq_block.v", 139, 140, "duplicated na_sleepcycles write"),
    ("red_pitaya_iq_block.v", 315, 316, "63-bit literal into 62-bit sums"),
]


def patched(fname):
    lines = (RTL / fname).read_bytes().decode().splitlines(keepends=True)
    for bid, f, ln, old, new, *_ in BUGS:
        if f != fname:
            continue
        cur = lines[ln - 1]
        if old not in cur:
            raise SystemExit(f"bug {bid}: {old!r} not on {f}:{ln}: {cur!r}")
        eol = "\r\n" if cur.endswith("\r\n") else "\n"
        body = cur.rstrip("\r\n")
        lines[ln - 1] = (body.replace(old, new) if new else "") + eol   # deletion keeps an empty line
    return "".join(lines)


def build(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in REVIEW:
        (out / f).write_bytes(patched(f).encode())
    for f in DEPS:
        (out / f).write_bytes((RTL / f).read_bytes())
    return out


def key():
    (HERE / "patches").mkdir(exist_ok=True)
    for i, (bid, f, ln, old, new, cls, desc, _kw) in enumerate(BUGS, 1):
        orig = (RTL / f).read_bytes().decode().splitlines(keepends=True)
        one = list(orig); body = one[ln - 1].rstrip("\r\n"); eol = one[ln - 1][len(body):]
        one[ln - 1] = (body.replace(old, new) if new else "") + eol
        d = difflib.unified_diff(orig, one, f"a/{f}", f"b/{f}", n=2)
        (HERE / "patches" / f"{i:02d}_{bid}.diff").write_text("".join(d), newline="")
    ak = dict(bugs=[dict(id=b, file=f, line=ln, cls=c, description=d, keywords=k) for b, f, ln, _, _, c, d, k in BUGS],
              preexisting=[dict(file=f, lines=[a, z], note=n) for f, a, z, n in PREEXISTING],
              review_files=REVIEW, match_window=3)
    (HERE / "answer_key.yaml").write_text("# generated by bugs.py; do not edit by hand\n"
                                          + yaml.safe_dump(ak, sort_keys=False))


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        print(build(sys.argv[2]))
    elif sys.argv[1:2] == ["key"]:
        key(); print(HERE / "answer_key.yaml")
    else:
        raise SystemExit(__doc__)
