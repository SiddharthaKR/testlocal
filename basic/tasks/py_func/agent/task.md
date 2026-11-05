# Task: requantize

Implement `requantize(x, gain, shift, bits=14)` in `fixedpoint.py` (a stub is provided):

    y = saturate((x * gain + round) >> shift)   to a signed `bits`-bit range
    round = 1 << (shift - 1) if shift > 0 else 0   (round half up)

`>>` on Python ints is an arithmetic (floor) shift, which is what we want, also for
negative numbers. Saturation clamps to [-2**(bits-1), 2**(bits-1) - 1].

1. Write `test_fixedpoint.py` with plain `assert`s (no pytest). Test first.
2. Run it, then implement, then iterate until it passes.
3. Write `AGENT_REPORT.md`: what you implemented and the evidence (tool output).

Editing: re-read a file right before editing it and copy the exact lines. If an edit fails twice
("could not find oldString"), stop retrying it and rewrite the whole file with the write tool.

{HELP}
