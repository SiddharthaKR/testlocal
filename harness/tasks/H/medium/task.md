# Task H (medium): implement the 8-tap FIR filter block

Implement `red_pitaya_fir_block` as specified in `tasks/H/fir_spec.md`.

1. Write `red_pitaya_fir_block.v` (put it in `pyrpl/pyrpl/fpga/rtl/`).
2. Write a testbench that drives the module through its bus and data ports, writes its output to CSV, and compares it against `tasks/H/fir_model.py`. Use your own stimuli and tap sets, and include inputs that cause saturation.
3. Simulate with `tools/run_sim.sh <tb.v> <src.v...>` and iterate until the output is bit-exact.
4. Run `tools/run_synth.sh red_pitaya_fir_block <file>` and report resources and timing. If it prints SKIPPED, say so.
5. Write `AGENT_REPORT.md`: your design, the latency you chose, evidence (tool output), and any remaining issues.

Tools print short summaries. Full logs are in `sim_logs/` and `synth_logs/`; open them only when needed.
