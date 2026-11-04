# Task B (medium): optimize the PyRPL IQ modulator

`red_pitaya_iq_modulator_block` (in `pyrpl/pyrpl/fpga/rtl/red_pitaya_iq_modulator_block.v`) fails timing at **{T_TARGET} ns**.

Close timing and reduce resources **without changing function, ports or parameters**.

- Output latency may increase by a few cycles (pipelining). Each extra cycle costs phase margin, so add only what you need. All three outputs (`dat_o`, `signal_q1_o`, `signal_q2_o`) must end up delayed by the same number of cycles relative to the original; if you pipeline one path, align the others.
- The starting file is upstream PyRPL. `tasks/B/ref/` holds a copy of it (with `red_pitaya_product_sat.v` and `red_pitaya_saturate.v`) as the functional reference; do not edit it.
- Check equivalence with `tools/run_equiv.sh` after every change.
- Measure each change with `tools/run_impl.sh red_pitaya_iq_modulator_block {T_TARGET} <files...>`. The modulator needs `red_pitaya_product_sat.v` and `red_pitaya_saturate.v`. If it prints SKIPPED, say so.
- Report each change with its measured effect in `AGENT_REPORT.md`.
