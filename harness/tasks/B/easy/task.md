# Task B (easy): optimize the PyRPL IQ demodulator

`red_pitaya_iq_demodulator_block` (in `pyrpl/pyrpl/fpga/rtl/red_pitaya_iq_demodulator_block.v`) fails timing at **{T_TARGET} ns**.

Close timing and reduce resources **without changing function, ports or parameters**.

- Output latency may increase by a few cycles (pipelining). Each extra cycle costs phase margin, so add only what you need. Both outputs (`signal1_o`, `signal2_o`) must keep the same latency relative to each other.
- The starting file is upstream PyRPL. `tasks/B/ref/` holds a copy of it as the functional reference; do not edit it.
- Check equivalence with `tools/run_equiv.sh` after every change.
- Measure each change with `tools/run_impl.sh red_pitaya_iq_demodulator_block {T_TARGET} <files...>`. This module has no dependencies. If it prints SKIPPED, say so.
- Report each change with its measured effect in `AGENT_REPORT.md`.
