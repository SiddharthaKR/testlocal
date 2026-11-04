def requantize(x: int, gain: int, shift: int, bits: int = 14) -> int:
    """saturate((x*gain + round) >> shift) to signed `bits`; round = 1<<(shift-1) if shift>0 else 0."""
    raise NotImplementedError
