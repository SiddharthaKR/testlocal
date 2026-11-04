---
name: python-tdd
description: Test-first workflow for small pure Python functions with plain assert tests, including edge cases for integer and fixed-point arithmetic. Use before implementing any Python function that has a written spec.
---

# Python test-first workflow

1. Read the spec once. Work out 3 input/output examples by hand, including one awkward one.
2. Write the test file FIRST, with plain `assert`s (no framework needed):
   ```python
   from mymod import f
   assert f(2, 3) == 6, "basic: 2*3"
   assert f(-2, 3) == -6, "negative input"
   print("ALL TESTS OK")
   ```
   Give every assert a message so a failure says exactly which case broke. Exit non-zero on failure
   (an uncaught `AssertionError` does that).
3. Run it. It must FAIL, and for the right reason (stub raises, wrong value), not because of a typo.
4. Implement the smallest thing that could pass. Run again. Read the FIRST failure only, fix it, repeat.
5. Before finishing, re-read the spec line by line and add a test for every sentence you have not covered.

## Edge cases worth testing
- Negative numbers on every input, and sign changes between input and output.
- Rounding ties (x.5) for both signs; remember `>>` on Python ints floors, so negative ties need a check.
- Zero and identity values (0, 1, "no-op" parameters): the result should be obvious.
- Limits: the maximum, the minimum, and one step beyond each (max+1, min-1) for clamping or overflow.
- Parameters at their smallest and largest legal values (for example a shift of 0 and the biggest shift).
- Default arguments and non-default arguments: test both, since defaults are easy to get wrong.
- Invalid input: if the spec says what happens (error, clamp), test it.

## Style
- Keep functions pure: no globals, no printing, same input gives the same output.
- Compute with full-precision Python ints (they never overflow) and clamp or convert only at the end.
- Cross-check with an independent formulation when you can (for example brute force on a small range).
- Never weaken a test to make it pass; fix the code, unless the test contradicts the spec.
- Finish with a short note of what was tested and the actual test output, not a claim.
