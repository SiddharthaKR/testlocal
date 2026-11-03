# Task B: optimize the PyRPL PID block

`red_pitaya_pid_block` (in `pyrpl/pyrpl/fpga/rtl/red_pitaya_pid_block.v`) fails timing at **{T_TARGET} ns**.

Close timing and reduce resources **without changing function, ports, parameters or register map**.

- Output latency may increase by a few cycles (pipelining). Each extra cycle costs phase margin, so add only what you need.
- The starting `red_pitaya_pid_block.v` is upstream PyRPL with one simulation fix (`kd_term`). `tasks/B/ref/` holds a copy of it as the functional reference; do not edit it.
- Check equivalence with `tools/run_equiv.sh` after every change.
- Measure each change with `tools/run_impl.sh red_pitaya_pid_block {T_TARGET} <files...>`. The PID needs `red_pitaya_filter_block.v` and `red_pitaya_lpf_block.v`. If it prints SKIPPED, say so.
- Report each change with its measured effect in `AGENT_REPORT.md`.
