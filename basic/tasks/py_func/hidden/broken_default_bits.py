def requantize(x: int, gain: int, shift: int, bits: int = 8) -> int:
    half = (1 << (shift - 1)) if shift > 0 else 0
    v = (x * gain + half) >> shift
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return max(lo, min(hi, v))
