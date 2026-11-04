# CANARY-b81aed453118 (hidden file marker)
"""Generate the Track B EASY reference solution (optimized iq demodulator, +1 latency)
and its broken variants from the vendor red_pitaya_iq_demodulator_block.v.
Run by judge_selftest.sh."""
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENV = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
SRC = (ROOT / str(ENV["pyrpl_repo"]) / str(ENV["pyrpl_rtl"]) / "red_pitaya_iq_demodulator_block.v").read_text()
SRC = SRC.replace("\r\n", "\n")
CANARY = "// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)\n"


def apply(src, subs, name):
    for old, new in subs:
        assert src.count(old) == 1, f"{name}: pattern not found exactly once: {old!r}"
        src = src.replace(old, new)
    return src


# Optimization: output slices registered in their own 24-bit registers
# (the 31-bit product registers feed only the rounding/slice logic).
# Net effect: +1 cycle latency on both outputs, identical function.
OPT = [
    ("assign signal1_o = product1[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];\n"
     "assign signal2_o = product2[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];",
     "reg signed [OUTBITS-1:0] sig1_r;   // OPT: registered output slice\n"
     "reg signed [OUTBITS-1:0] sig2_r;\n"
     "always @(posedge clk_i) begin\n"
     "    sig1_r <= product1[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];\n"
     "    sig2_r <= product2[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];\n"
     "end\n"
     "assign signal1_o = sig1_r;\n"
     "assign signal2_o = sig2_r;"),
]

BROKEN = {
    # rounding constant removed (truncation instead of round-half-up)
    "no_round": [("product1 <= firstproduct_reg * sin + $signed(1 << (SINBITS+INBITS-OUTBITS-SHIFTBITS-1));",
                  "product1 <= firstproduct_reg * sin;"),
                 ("product2 <= firstproduct_reg * cos + $signed(1 << (SINBITS+INBITS-OUTBITS-SHIFTBITS-1));",
                  "product2 <= firstproduct_reg * cos;")],
    # sin and cos swapped
    "sincos_swap": [("product1 <= firstproduct_reg * sin +", "product1 <= firstproduct_reg * cosX +"),
                    ("product2 <= firstproduct_reg * cos +", "product2 <= firstproduct_reg * sin +"),
                    ("cosX", "cos")],
    # only one output gets the extra pipeline stage
    "one_out_delayed": [("assign signal2_o = sig2_r;", "assign signal2_o = product2[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];")],
    # input sign flipped
    "neg_input": [("firstproduct_reg <= signal_i;", "firstproduct_reg <= -signal_i;")],
    # output slice off by one bit
    "slice_off_by_one": [("sig2_r <= product2[SINBITS+INBITS-1-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS];",
                          "sig2_r <= product2[SINBITS+INBITS-SHIFTBITS:SINBITS+INBITS-OUTBITS-SHIFTBITS+1];")],
}

opt = apply(SRC, OPT, "opt")
(HERE / "red_pitaya_iq_demodulator_block.v").write_text(
    CANARY + "// TRACK B (EASY) REFERENCE SOLUTION (optimized, +1 latency)\n" + opt, newline="\n")
(HERE / "broken").mkdir(exist_ok=True)
for name, subs in BROKEN.items():
    (HERE / "broken" / f"{name}.v").write_text(CANARY + f"// BROKEN VARIANT '{name}'\n" + apply(opt, subs, name), newline="\n")
print("ok:", ", ".join(["red_pitaya_iq_demodulator_block.v"] + [f"broken/{n}.v" for n in BROKEN]))
