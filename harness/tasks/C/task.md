# Task C: review modules for functional bugs

Review these Verilog modules (in `review/`) for **functional bugs**:

{REVIEW_FILES}

Any other files in `review/` are dependencies, so the set compiles. You do not need to review them.

A functional bug is anything that makes the hardware compute the wrong result, for example:
- wrong sign or bit width
- wrong bit slice
- saturation to the wrong limit
- missing reset
- blocking `=` in a clocked block
- a missing pipeline register

Style issues and lint warnings do not count.

Create `bugs.json` early, as soon as you find the first bug, and add to it as you go. A missing file scores zero. Write it in the workspace root, as a JSON list:

```json
[
  {"file": "red_pitaya_lpf_block.v", "line": 42, "description": "one sentence: what is wrong and its effect"}
]
```

- `line` is the line number in the file as given.
- Report each bug once.
- False alarms count against you.

You may compile and simulate with `tools/run_sim.sh` to confirm a suspicion. Finish with `AGENT_REPORT.md`.
