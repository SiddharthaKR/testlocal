---
name: python-tdd
description: Test-first workflow for small pure Python functions with plain assert tests; edge cases for integer/fixed-point code. Load before implementing a Python function.
---

# Python test-first workflow

1. Read the spec once; write down 3 example inputs/outputs by hand.
2. Write `test_<module>.py` FIRST, plain `assert`s, no pytest needed:
   ```python
   from mymod import f
   assert f(2, 3) == 6, "basic"
   print("ALL TESTS OK")
   ```
   Give every assert a message so a failure says which case broke.
3. Run it (use the `run_tests` tool). It must FAIL for the right reason (stub raises).
4. Implement the smallest thing that passes, run again, repeat.
5. Before finishing, re-read the spec and add the cases you forgot.

## Edge cases to always test (integer / fixed-point code)
- Negative inputs, and negative gain (Python `>>` floors, which is the arithmetic shift).
- Rounding ties: x.5 for both signs (e.g. 5/2 -> 3 and -5/2 -> -2 for round half up).
- shift == 0 (no rounding term), and the largest shift.
- Both limits and one step beyond them: max, max+1, min, min-1 (saturation both rails).
- Non-default parameters (e.g. `bits=8`) and the default.

## Style
- Keep functions pure: no globals, no printing inside, same input gives same output.
- Compute with full-precision Python ints, clamp only at the end.
- Do not edit the tests to make them pass; fix the code, unless the test contradicts the spec.
