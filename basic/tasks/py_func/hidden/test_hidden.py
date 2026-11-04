from fixedpoint import requantize as rq

CASES = [  # (x, gain, shift, bits, expected)
    (100, 3, 0, 14, 300),          # shift=0, no rounding
    (-100, 3, 0, 14, -300),
    (5, 1, 1, 14, 3),              # 2.5 -> tie rounds up
    (-5, 1, 1, 14, -2),            # -2.5 -> tie rounds up (toward +inf)
    (3, 1, 1, 14, 2),              # 1.5 -> 2
    (-3, 1, 1, 14, -1),            # -1.5 -> -1
    (1, 1, 2, 14, 0),              # 0.25 -> 0
    (-1, 1, 2, 14, 0),             # -0.25 -> 0
    (-3, 1, 2, 14, -1),            # -0.75 -> -1
    (1000, 100, 4, 14, 6250),      # normal
    (8191, 32767, 0, 14, 8191),    # saturate high
    (-8192, 32767, 0, 14, -8192),  # saturate low
    (8191, -32768, 3, 14, -8192),  # negative gain saturates low
    (8191, 32767, 4, 14, 8191),    # saturate high with shift
    (100, 1, 0, 8, 100),           # bits=8 in range
    (200, 1, 0, 8, 127),           # bits=8 high rail
    (-200, 1, 0, 8, -128),         # bits=8 low rail
    (127, 1, 0, 8, 127),
    (-128, 1, 0, 8, -128),
]

# run every case (no early stop) so the judge can report a score, not just pass/fail
first_bad, n_ok = None, 0
checks = [((x, g, s, b), want) for x, g, s, b, want in CASES] + [((7, 3, 2), "default-bits")]
for args, want in checks:
    try:
        got = rq(*args)
        if want == "default-bits":
            want = rq(7, 3, 2, 14)          # default bits is 14
        ok = got == want
    except Exception as e:                  # a crash counts as a wrong answer
        got, ok = f"{type(e).__name__}: {e}", False
    n_ok += ok
    if not ok and first_bad is None:
        first_bad = f"requantize{args} = {got}, expected {want}"
print(f"SCORE: {100 * n_ok / len(checks):.0f}% ({n_ok} of {len(checks)} hidden cases correct)")
if first_bad:
    raise AssertionError(first_bad)
print(f"HIDDEN TESTS OK: {len(checks)} cases")
