# Task: gain block

Implement the Verilog module `red_pitaya_gain_block` exactly as described in `spec.md`.

1. Write `red_pitaya_gain_block.v` in this folder (the workspace root).
2. Write a testbench `tb.v` that sets gain/shift/offset over the bus, streams stimulus
   samples, and writes the output `dat_o` to a text file (one integer per line). Compare
   it with `model.py` (see `spec.md`). Use several settings and inputs that saturate.
3. Simulate (iverilog and vvp are installed) and iterate until the output is bit-exact.
4. Write `AGENT_REPORT.md`: your design, the latency you chose, and the evidence
   (tool output). Mention anything that is still not working.

{HELP}
