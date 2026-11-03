# CANARY-b81aed453118 (hidden file marker)
"""Generate the Track B reference solution (optimized PID, +1 latency) and its
broken variants from harness/tasks/B/pid_ref.v. Run by judge_selftest.sh."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = (HERE.parents[2] / "tasks" / "B" / "pid_ref.v").read_text().replace("\r\n", "\n")
CANARY = "// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)\n"


def apply(src, subs, name):
    for old, new in subs:
        assert src.count(old) == 1, f"{name}: pattern not found exactly once: {old!r}"
        src = src.replace(old, new)
    return src


# Optimization: pause mux moved onto the multiplier operand, product registered
# (DSP48 MREG), integrator output re-registered to keep P and I aligned.
# Net effect: +1 cycle latency, identical function.
OPT = [
    ("wire signed [15+GAINBITS-1: 0] kp_mult       ;",
     "reg  signed [15+GAINBITS-1: 0] kp_mult       ;   // OPT: registered product (MREG)\n"
     "wire signed [15-1: 0] error_p = (pause_p==1'b1) ? 15'sd0 : error;   // OPT: pause on operand"),
    ("      kp_reg  <= {15+GAINBITS-PSR{1'b0}};",
     "      kp_reg  <= {15+GAINBITS-PSR{1'b0}};\n      kp_mult <= {15+GAINBITS{1'b0}};"),
    ("      kp_reg <= kp_mult[15+GAINBITS-1:PSR] ;",
     "      kp_mult <= $signed(error_p) * $signed(set_kp);\n      kp_reg <= kp_mult[15+GAINBITS-1:PSR] ;"),
    ("assign kp_mult = (pause_p==1'b1) ? $signed({15+GAINBITS{1'b0}}) : $signed(error) * $signed(set_kp);\n", ""),
    ("assign int_shr = $signed(int_reg[IBW-1:ISR]) ;",
     "assign int_shr = $signed(int_reg[IBW-1:ISR]) ;\n"
     "reg signed [IBW-ISR-1: 0] int_shr_r;   // OPT: align I path with the extra P stage\n"
     "always @(posedge clk_i) if (rstn_i == 1'b0) int_shr_r <= 0; else int_shr_r <= int_shr;"),
    ("assign pid_sum = $signed(kp_reg) + $signed(int_shr) + $signed(kd_term);",
     "assign pid_sum = $signed(kp_reg) + $signed(int_shr_r) + $signed(kd_term);"),
]

BROKEN = {
    # removed arbitrary saturation
    "no_arb_sat": [("\t\t\tif (pid_out >= out_max)\n\t\t\t\tout_buffer <= out_max;\n"
                    "\t\t\telse if (pid_out <= out_min)\n\t\t\t\tout_buffer <= out_min;\n\t\t\telse\n", "")],
    # changed output saturation polarity
    "sat_polarity": [("pid_out <= 14'h1FFF;", "pid_out <= 14'hXXXX;"),
                     ("pid_out <= 14'h2000;", "pid_out <= 14'h1FFF;"),
                     ("pid_out <= 14'hXXXX;", "pid_out <= 14'h2000;")],
    # extra stage only on the P path (P and I misaligned)
    "p_only_delay": [("$signed(int_shr_r) + $signed(kd_term)", "$signed(int_shr) + $signed(kd_term)")],
    # integrator wraps instead of saturating
    "int_wrap": [("else if (int_sum[IBW+1-1:IBW+1-2] == 2'b01) //normal positive saturation",
                  "else if (1'b0) //normal positive saturation"),
                 ("else if (int_sum[IBW+1-1:IBW+1-2] == 2'b10) // negative saturation",
                  "else if (1'b0) // negative saturation")],
    # register map changed: Kp readback returns Ki
    "readback": [("16'h108 : begin ack <= wen|ren; rdata <= {{32-GAINBITS{1'b0}},set_kp}; end",
                  "16'h108 : begin ack <= wen|ren; rdata <= {{32-GAINBITS{1'b0}},set_ki}; end")],
}

opt = apply(REF, OPT, "opt")
(HERE / "red_pitaya_pid_block.v").write_text(CANARY + "// TRACK B REFERENCE SOLUTION (optimized, +1 latency)\n" + opt)
(HERE / "broken").mkdir(exist_ok=True)
for name, subs in BROKEN.items():
    (HERE / "broken" / f"{name}.v").write_text(CANARY + f"// BROKEN VARIANT '{name}'\n" + apply(opt, subs, name))
print("ok:", ", ".join(["red_pitaya_pid_block.v"] + [f"broken/{n}.v" for n in BROKEN]))
