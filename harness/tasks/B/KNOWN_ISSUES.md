# pid_ref.v — known issues (Track B reference)

Source: `vendor/pyrpl/pyrpl/fpga/rtl/red_pitaya_pid_block.v` @ `7b0ac7a` (tag `demo-baseline`).

## Fixed in pid_ref.v (the only functional change)

| # | Issue | Fix |
|---|---|---|
| F1 | Module-level `kd_reg_s` (and `kd_mult`, `kd_reg`, `kd_reg_r`) re-declared inside unnamed generate blocks. The module-level `kd_reg_s` used in `pid_sum` is never driven, so it is X in simulation. | Single module-level `wire signed [15+GAINBITS-DSR:0] kd_term`, driven from named blocks `g_d` (DERIVATIVE=1: `kd_term = kd_reg_s`) / `g_nod` (DERIVATIVE=0: `kd_term = 0`). `pid_sum` uses `kd_term`. Width is unchanged (30 bits). With DERIVATIVE=0, as instantiated, the result is bit-identical to synthesized hardware (Vivado ties the undriven net to 0). |

Verified (iverilog 12): after reset the original module gives X on `dat_o` for 192/192 cycles, and pid_ref.v gives X on 0/192.

## Kept bit-identical on purpose (do not "fix" — the judge reference must match the original)

| # | Location (original line) | Issue | Effect |
|---|---|---|---|
| K1 | 250 | `{IBW-16-ISR{set_ival[15]}}` is a zero-width replication (IBW = ISR+16). | Legal in SystemVerilog when it is inside a larger concatenation. **iverilog 12.0 (`-g2012`) accepts it unchanged**, and the `ival` write of -3805 reads back -3805 (sign extension correct). No rewrite needed. |
| K2 | 104–109 | `pause_i`, `pause_p`, `pause_d` are never declared, so Verilog creates them as implicit 1-bit wires. The declared `pause_*_on_sync` wires are unused. | None (functionally correct). Fails under `` `default_nettype none ``. |
| K3 | 244 | `ki_mult` is reset with `{15+GAINBITS{1'b0}}` but declared `[16+GAINBITS-1:0]`. | None (zero-extended). Width warning. |
| K4 | 290 | `kd_mult` zero value is `{15+GAINBITS-1{1'b0}}`, one bit short. | None (DERIVATIVE=0, and it is zero anyway). |
| K5 | 332–340 | `out_buffer` (ARBITRARY_SATURATION stage) has no reset. | `dat_o` is X for the first cycles after reset. **The judges ignore outputs during `SETTLE_CYCLES = 8` after `rstn_i` is released** (`harness/judge/common.py`). |
| K6 | 122 | `set_ival <= 14'd0` assigned to a 16-bit reg. | None. |
| K8 | filter_block.v:76 | `red_pitaya_filter_block` passes a 5-bit `shift` into `red_pitaya_lpf_block`, which expects 6 bits (FILTERSHIFTBITS=5). | None (zero-padded). iverilog warns 4×. Note: pid_ref also depends on `red_pitaya_lpf_block.v`. |
| K7 | 141–142 | `out_min/out_max <= wdata` (32-bit truncated to 14). | None (truncation is the intended behaviour). |
