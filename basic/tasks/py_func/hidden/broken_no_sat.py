def requantize(x: int, gain: int, shift: int, bits: int = 14) -> int:
    half = (1 << (shift - 1)) if shift > 0 else 0
    v = (x * gain + half) >> shift
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return v & ((1 << bits) - 1) if v >= 0 else -((-v) & ((1 << bits) - 1))  # wraps instead of saturating
