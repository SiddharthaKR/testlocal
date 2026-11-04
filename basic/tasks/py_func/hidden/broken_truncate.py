def requantize(x: int, gain: int, shift: int, bits: int = 14) -> int:
    half = 0
    v = (x * gain + half) >> shift
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return max(lo, min(hi, v))
