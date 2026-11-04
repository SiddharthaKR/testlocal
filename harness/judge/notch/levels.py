# CANARY-b81aed453118 (hidden file marker)
"""
Track H level registry (hidden). One entry per level: module name, max latency,
testbench, bit-true model, hidden parameter sets, register writes and the
readback script. Used by run_judge.py and gen_stimuli.py.

  hard   : red_pitaya_notch_block  (legacy path: tb_notch_judge.v, notch-specific plusargs)
  easy   : red_pitaya_gain_block   (generic path: tb_dsp_judge.v)
  medium : red_pitaya_fir_block    (generic path: tb_dsp_judge.v)

Readback script lines: (op, addr, value)  op 0 = write value, op 1 = read and expect value.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE.parents[1] / "tasks" / "H"
sys.path.insert(0, str(TASKS / "easy")); sys.path.insert(0, str(TASKS / "medium")); sys.path.insert(0, str(TASKS))
import gain_model as gm   # noqa: E402
import fir_model as fm    # noqa: E402

M32 = 0xFFFFFFFF


def sx(v, bits):
    """Sign-extend the low `bits` of v to a 32-bit pattern."""
    v &= (1 << bits) - 1
    if v >> (bits - 1):
        v -= 1 << bits
    return v & M32


# --- easy: gain block --------------------------------------------------------
# f0 = frequency of the interference tone in the "sig" stimulus.
GAIN_SETS = {
    # gain ~ -2.9: large inputs saturate
    "gA": dict(gain=-1500, shift=9, offset=-37, f0=5e6),
    # gain ~ 1.17: sig does not saturate, rand/chirp clip a little
    "gB": dict(gain=300, shift=8, offset=25, f0=20e6),
    # gain = -1.0 (shift 15, extreme gain value), offset at +max: heavy positive saturation
    "gC": dict(gain=-32768, shift=15, offset=8191, f0=1e6),
    # shift = 0 (no rounding term), gain 7: saturates on almost everything
    "gD": dict(gain=7, shift=0, offset=-100, f0=10e6),
}

_FIR_LP = fm.lowpass_taps(8e6)
FIR_SETS = {
    # lowpass, unity DC gain: sig mostly passes, tone at f0 attenuated
    "hLP": dict(h=list(_FIR_LP), f0=30e6),
    # alternating strong taps, sum of |h| >> 1: heavy saturation
    "hBOOST": dict(h=[98304, -81920, 65536, -49152, 32768, -16384, 8192, -4096], f0=5e6),
    # asymmetric, taps at the 18-bit limits (tap-order, width and accumulator checks)
    "hEXT": dict(h=[131071, -131072, 100000, -90000, 65536, -65535, 30001, -1], f0=15e6),
}


def _gain_regs(p):
    return [(0x100, p["gain"]), (0x104, p["shift"]), (0x108, p["offset"])]


def _fir_regs(p):
    return [(0x100 + 4 * k, v) for k, v in enumerate(p["h"])]


def _gain_model(x, p):
    return gm.gain_block(x, p["gain"], p["shift"], p["offset"])


def _fir_model(x, p):
    return fm.fir(x, p["h"])


GAIN_RB = [
    # after reset: everything reads 0
    (1, 0x100, 0), (1, 0x104, 0), (1, 0x108, 0), (1, 0x200, 16),
    # sign extension / field widths
    (0, 0x100, 0x0001_8000), (1, 0x100, sx(0x8000, 16)),
    (0, 0x100, 0xFFFF_7FFF), (1, 0x100, 0x0000_7FFF),
    (0, 0x104, 0xFFFF_FFF5), (1, 0x104, 0x5),
    (0, 0x104, 0x0000_000F), (1, 0x104, 0xF),
    (0, 0x108, 0x0000_2000), (1, 0x108, sx(0x2000, 14)),
    (0, 0x108, 0xFFFF_DFFF), (1, 0x108, 0x0000_1FFF),
    # read-only constant and unknown addresses
    (0, 0x200, 0x55), (1, 0x200, 16),
    (0, 0x10C, 0x1234), (1, 0x10C, 0), (1, 0x300, 0), (1, 0x0FC, 0),
]
FIR_RB = [(1, 0x100 + 4 * k, 0) for k in range(8)] + [(1, 0x200, 16)]
for _k in range(8):
    _a = 0x100 + 4 * _k
    # negative value with garbage above bit 17, then a positive near-max value
    FIR_RB += [(0, _a, 0x3_0000 + 0x1234 + _k), (1, _a, sx(0x3_0000 + 0x1234 + _k, 18)),
               (0, _a, 0xFFFC_0000 | (0x1_FFFF - _k)), (1, _a, sx(0x1_FFFF - _k, 18))]
FIR_RB += [(0, 0x200, 0x55), (1, 0x200, 16), (1, 0x120, 0), (1, 0x300, 0)]

LEVELS = {
    "hard": dict(module="red_pitaya_notch_block", max_latency=4, tb="tb_notch_judge.v", bypass=True),
    "easy": dict(module="red_pitaya_gain_block", max_latency=4, tb="tb_dsp_judge.v", bypass=False,
                 sets=GAIN_SETS, regs=_gain_regs, model=_gain_model, readback=GAIN_RB),
    "medium": dict(module="red_pitaya_fir_block", max_latency=8, tb="tb_dsp_judge.v", bypass=False,
                   sets=FIR_SETS, regs=_fir_regs, model=_fir_model, readback=FIR_RB),
}
