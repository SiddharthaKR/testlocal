# CANARY-b81aed453118 (hidden file marker)
"""Generate the Track B MEDIUM reference solution (optimized iq modulator, +1 latency on all outputs)
and its broken variants from the vendor red_pitaya_iq_modulator_block.v.
Dependencies (product_sat, saturate) are the unmodified vendor files (the judge adds them).
Run by judge_selftest.sh."""
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ENV = yaml.safe_load((ROOT / "config" / "env.yaml").read_text())
SRC = (ROOT / str(ENV["pyrpl_repo"]) / str(ENV["pyrpl_rtl"]) / "red_pitaya_iq_modulator_block.v").read_text()
SRC = SRC.replace("\r\n", "\n")
CANARY = "// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)\n"


def apply(src, subs, name):
    for old, new in subs:
        assert src.count(old) == 1, f"{name}: pattern not found exactly once: {old!r}"
        src = src.replace(old, new)
    return src


# Optimization: the two second-stage products are registered (DSP48 MREG) before the sum, and the q1/q2
# quadrature outputs get a matching extra register. Net effect: +1 cycle on dat_o, q1 and q2.
OPT = [
    ("assign secondproduct1 = firstproduct1_reg * sin;\nassign secondproduct2 = firstproduct2_reg * cos;",
     "wire signed [OUTBITS+1+SINBITS-1-1:0] secondproduct1_c = firstproduct1_reg * sin;\n"
     "wire signed [OUTBITS+1+SINBITS-1-1:0] secondproduct2_c = firstproduct2_reg * cos;\n"
     "reg signed [OUTBITS+1+SINBITS-1-1:0] secondproduct1_r;   // OPT: registered products (MREG)\n"
     "reg signed [OUTBITS+1+SINBITS-1-1:0] secondproduct2_r;\n"
     "always @(posedge clk_i) begin\n"
     "    secondproduct1_r <= secondproduct1_c;\n"
     "    secondproduct2_r <= secondproduct2_c;\n"
     "end\n"
     "assign secondproduct1 = secondproduct1_r;\n"
     "assign secondproduct2 = secondproduct2_r;"),
    ("assign signal_q1_o = q1_product_reg;\nassign signal_q2_o = q2_product_reg;",
     "reg signed [OUTBITS-1:0] q1_product_reg2;   // OPT: align quadrature outputs with the extra dat_o stage\n"
     "reg signed [OUTBITS-1:0] q2_product_reg2;\n"
     "always @(posedge clk_i) begin\n"
     "    q1_product_reg2 <= q1_product_reg;\n"
     "    q2_product_reg2 <= q2_product_reg;\n"
     "end\n"
     "assign signal_q1_o = q1_product_reg2;\n"
     "assign signal_q2_o = q2_product_reg2;"),
]

BROKEN = {
    # sum of the two products turned into a difference (dat_o sign of the Q term)
    "sum_sign": [("secondproduct_sum <= secondproduct1 + secondproduct2;",
                  "secondproduct_sum <= secondproduct1 - secondproduct2;")],
    # final saturation replaced by wrap-around truncation
    "no_sat": [("secondproduct_out <= secondproduct_sat;",
                "secondproduct_out <= secondproduct_sum[SINBITS-1+OUTBITS-1:SINBITS-1];")],
    # offset g2 replaced by g3
    "g2_offset": [("$signed(g2[GAINBITS-1:GAINBITS-OUTBITS])", "$signed(g3[GAINBITS-1:GAINBITS-OUTBITS])")],
    # q2 quadrature scaled by g4 instead of g3
    "q2_gain": [(".factor1_i(signal2_i),\n  .factor2_i(g3),", ".factor1_i(signal2_i),\n  .factor2_i(g4),")],
    # sin and cos swapped in the second product
    "sincos_swap": [("firstproduct1_reg * sin;", "firstproduct1_reg * cosX;"),
                    ("firstproduct2_reg * cos;", "firstproduct2_reg * sin;"),
                    ("cosX", "cos")],
    # q2 misses the extra stage (one output delayed, the other not)
    "q2_not_delayed": [("assign signal_q2_o = q2_product_reg2;", "assign signal_q2_o = q2_product_reg;")],
}

opt = apply(SRC, OPT, "opt")
(HERE / "red_pitaya_iq_modulator_block.v").write_text(
    CANARY + "// TRACK B (MEDIUM) REFERENCE SOLUTION (optimized, +1 latency)\n" + opt, newline="\n")
(HERE / "broken").mkdir(exist_ok=True)
for name, subs in BROKEN.items():
    (HERE / "broken" / f"{name}.v").write_text(CANARY + f"// BROKEN VARIANT '{name}'\n" + apply(opt, subs, name), newline="\n")
print("ok:", ", ".join(["red_pitaya_iq_modulator_block.v"] + [f"broken/{n}.v" for n in BROKEN]))
