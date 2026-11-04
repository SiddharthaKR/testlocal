# What the hidden judges actually check

Audience: an FPGA engineer who found the hidden testbenches hard to read.
Goal: explain WHAT is verified and WHY, without reading code.
Everything below was read from the code in this repo. The self-tests
(`bash harness/judge/judge_selftest.sh all` and `py basic/selftest.py`) were run to
confirm the behaviour; the numbers quoted (latencies, coverage counts, failing
cases) come from those runs. Where the code is ambiguous this is said explicitly.

---------------------------------------------------------------------------

## 1. How every judge works

```
 agent workspace                 judge (runs ONLY after the agent has stopped)
 ---------------                 ---------------------------------------------
 agent writes X      ------>     1. build hidden inputs the agent never saw
 (Verilog / Python /             2. run the candidate on them
  bugs.json)                     3. compare with a GOLDEN reference
                                    - Python bit-true model          (Track H, basic)
                                    - the ORIGINAL Verilog           (Track B)
                                    - a list of seeded bugs          (Track C)
                                 4. verdict + judge.json
```

The agent only ever sees a spec, a golden model (for H) and a small "mini check". The
real testbenches, stimuli, parameter sets and seeded-bug list are in `harness/judge/`
and `basic/tasks/*/hidden/`. Every hidden file carries a canary string; `leak_check.py`
(section 7) looks for it.

### Rules shared by all hardware judges

| Rule | What it means in plain words |
|---|---|
| Fixed latency allowed | The candidate may add pipeline stages, but the delay between input and output must be the SAME for every sample and for every test case. |
| Latency search | The judge does not know the candidate's latency. It tries k = 0, 1, 2, ... and accepts the first k for which ALL samples match exactly. |
| Bit exact | No tolerance. One wrong LSB on one sample fails that case. |
| Same latency for all cases | Different register settings or input types must not change the latency (a hidden mode where the output is taken one register earlier is a real bug class). |
| Settle window | Output samples in the first `SETTLE_CYCLES = 8` clocks after reset release are ignored where reset behaviour matters (see below). |
| X/Z = fail | Any unknown (X or Z) output after the settle window fails, even if a latency otherwise matches. |
| Deterministic | Fixed random seed `20261103` (`common.py`), so the same candidate always gets the same verdict. |
| Self-test | Reference solutions must PASS and deliberately broken copies must FAIL (below). |

### The latency search with a tiny example

The testbench drives one input sample per clock and logs the output once per clock, as
rows `n = 0, 1, 2, ...`. After the stimulus ends it keeps driving 0 for a few more rows
(12 for the generic H testbench, 8 for the notch testbench, 8 for the basic gain
testbench) so that late outputs can still appear.

Example, expected model output `y[0..3] = 10, 20, 30, 40`, candidate with 2 extra stages:

```
row n          :  0    1    2    3    4    5
DUT dat_o      :  0    0   10   20   30   40
k=0 compares y[n] with row n   -> 10 vs 0   mismatch
k=1 compares y[n] with row n+1 -> 10 vs 0   mismatch
k=2 compares y[n] with row n+2 -> 10,20,30,40 all match  => latency 2, PASS
```
If no k matches, the judge reports the k with the MOST matching samples as "best lag" and
the first mismatch at that k. That is the number to look at when debugging.

Maximum allowed latency: gain 4, notch 4, FIR 8 (Track H); lag 0..8 (Track B);
0..4 (basic gain).

### What "latency 0" means differs per judge (surprising, verify before comparing numbers)

* Track H samples `dat_o` 1 ns AFTER each rising edge. A design with exactly one register
  stage between `dat_i` and `dat_o` therefore shows latency 0. The reference gain block has
  3 register stages (`x0`, `p`, `out`) and the judge reports latency 2; the reference notch
  reports 2; the reference FIR reports 4. So H latency = register stages minus 1.
  (A purely combinational path would also show 0.)
* Basic fpga_gain samples 1 ns after the FALLING edge, i.e. before the next rising edge.
  The same 3-stage reference is reported as latency 3. So basic latency = register stages.
* Track B never talks about absolute latency: it measures candidate output versus the ORIGINAL
  design's output, delayed by k. k = 0 means "same as original", k = 1 means "one cycle
  slower than the original" (reference optimized solutions show k = 1).

### The settle window and why it exists

`SETTLE_CYCLES = 8` (`harness/judge/common.py`): samples are ignored for the first 8 clocks
after `rstn_i` is released. Reason (comment in `common.py`, and `harness/tasks/B/KNOWN_ISSUES.md`
item K5): in PyRPL's PID, `out_buffer` has no reset, so `dat_o` is X for the first cycles even in
the original design. A judge that insisted on non-X from cycle 0 would fail the original.
The IQ demodulator and modulator have no reset at all, so the same window is used from the start
of the simulation.

Detail on where it matters: in the Track H filter runs the first logged row is already about
22 or more clocks after reset (bus writes plus 10 idle clocks come first), so the window
removes nothing there. It matters in (a) the H check `no_x_after_reset` (looks at cycles
8..39 with `dat_i = 0` and nothing configured), and (b) all Track B runs, where the comparison
starts at cycle `SETTLE_CYCLES + MAX_LAG` = 16 so the 8-deep history of reference outputs is full.

### How we know the judge itself is right (self-test)

`judge_selftest.sh` runs, per block:
1. the reference solution: must PASS;
2. several hand-made broken copies (one-line edits generated by `make_broken.py` /
   `make_*_solutions.py`): each must FAIL.

If a broken copy passed, the stimuli would be too weak. All of these held in the last run
(Track H: 1 + 5 + 1 + 7 + 1 + 8 variants as listed below; Track B; Track C; basic).

---------------------------------------------------------------------------

## 2. Track H: build a new block from a spec

Files: `harness/judge/notch/{run_judge.py, levels.py, gen_stimuli.py, compare.py,
tb_dsp_judge.v (easy, medium), tb_notch_judge.v (hard)}`; specs in `harness/tasks/H/`.

Flow for every level:
1. `gen_stimuli.py` writes 4 stimulus files per parameter set (4096 samples each, 14-bit signed)
   and the expected output from the Python model.
2. For each (parameter set, stimulus) = one "case": a fresh simulation: reset, bus writes of the
   registers, 10 idle clocks, then stream the samples. Each case therefore starts from a clean state.
3. `compare.py` does the latency search above.
4. A separate "checks" simulation tests register readback, bypass (hard only) and X after reset.
5. PASS needs all of: every case bit exact; the SAME latency in every case; every check passing.

### The four stimulus types (same for all three levels)

| Name | Signal | Why it is there |
|---|---|---|
| `sig` | wanted tone (2500 amplitude, at min(f0/10, 0.5 MHz)) + interference tone at f0 (4000 amplitude) + noise (sigma 20), clipped to 14 bits | Realistic filter use, mostly in the linear range: catches rounding and coefficient errors |
| `rand` | uniform random over the full 14-bit range | Forces saturation constantly and exercises every bit of data and accumulator |
| `chirp` | linear sweep DC to fs/2, amplitude 8000 | Every frequency; near full scale, so long stretches of the sweep saturate for the big-gain sets |
| `impulse` | +8191 at n = 0, then -8192 at n = 2048, zeros elsewhere | Shows the impulse response (tap order, delay alignment) and recovery after saturation; only a few samples are non-zero so offsets in time show up clearly |

`f0` for the `sig` tone comes from each parameter set. Number of saturated expected samples
per case is recorded in `judge.json` (`n_saturated`) so you can see saturation was really reached.
Note that `n_saturated` counts any expected output equal to a rail, including a legitimate
constant (e.g. gC with offset 8191).

### 2.1 EASY: `red_pitaya_gain_block`

What the block does (one line): `y = sat14( ((x*gain + round_term) >>> shift) + offset )`,
round half up, no state.

Registers:

| addr | reg | width | readback |
|---|---|---|---|
| 0x100 | gain | 16-bit signed | sign-extended to 32 |
| 0x104 | shift | 4-bit unsigned (0..15) | zero-extended |
| 0x108 | offset | 14-bit signed | sign-extended |
| 0x200 | GAIN_BITS | read only | constant 16 |

Parameter sets (4 sets x 4 stimuli = 16 cases):

| Set | gain, shift, offset | Effective gain | Purpose |
|---|---|---|---|
| gA | -1500, 9, -37 | about -2.93 | Negative gain; large inputs saturate on both rails |
| gB | 300, 8, 25 | about 1.17 | Mostly linear (`sig` does not saturate); `rand`/`chirp` clip a little; tests rounding |
| gC | -32768, 15, 8191 | exactly -1.0 | Extreme gain value and largest shift; offset at +max so the offset add itself saturates |
| gD | 7, 0, -100 | 7.0 | shift = 0 (no rounding term; the "shift > 0" special case), saturates on almost everything |

Register / X checks (`rb_...` per address, plus `no_x_after_reset`):
* after reset: gain, shift, offset read 0 and 0x200 reads 16;
* sign extension and field width: write 0x18000 to gain, expect 0xFFFF8000 (upper bits ignored);
  write 0xFFFF7FFF, expect 0x7FFF; shift written 0xFFFFFFF5 reads 5, 0xF reads 0xF
  (only 4 bits kept); offset 0x2000 reads 0xFFFFE000, 0xFFFFDFFF reads 0x1FFF;
* the constant 0x200 survives a write of 0x55;
* unknown addresses (0x10C, 0x300, 0x0FC) read 0, even after writing 0x1234 to 0x10C.

Broken variants (all FAIL in the self-test):

| Variant | What is wrong | Caught by |
|---|---|---|
| truncate | truncates instead of round half up | gA, gB `sig/rand/chirp` etc. (6 of 16 cases): only samples whose dropped bits are >= half differ, so needs non-saturated, non-trivial data |
| no_sat | wraps instead of saturating | 15 of 16 cases (everything that saturates); impossible to hide with `rand` |
| sat_polarity | positive overflow goes to the negative rail | 15 of 16 cases |
| offset_before_shift | offset added before the shift | 12 cases (gA, gB, gC; gD has shift 0 so the order does not matter) |
| unsigned_gain | gain treated as unsigned | 8 cases (gA and gC, the two sets with negative gain; gB and gD have positive gain and pass) |
| shift_narrow | shift register only 3 bits | `rb_0x104` (writing 0xF reads back 7) AND filter cases with shift >= 8 (gA, gB) |
| latency_shift0 | extra shortcut when shift = 0: output one register earlier | NO sample is wrong; every case matches, but gD cases settle at latency 1 while others at 2. Caught only by the "same latency for all cases" rule |

### 2.2 MEDIUM: `red_pitaya_fir_block`

What it does: 8-tap FIR, `acc = h0*x[n] + h1*x[n-1] + ... + h7*x[n-7]`,
`y = sat14((acc + 2^15) >>> 16)`. Taps are 18-bit signed Q2.16; `h0` is the newest sample.
No feedback, so the candidate may pipeline freely (latency up to 8 allowed; reference uses 4).

Registers: 0x100 + 4*k for h0..h7 (18-bit signed, sign-extended on read), 0x200 constant 16.

Parameter sets (3 sets x 4 stimuli = 12 cases):

| Set | Taps (Q2.16 integers) | Purpose |
|---|---|---|
| hLP | `lowpass_taps(8 MHz)` = 1009, 3827, 10871, 17060, 17060, 10871, 3827, 1009 (sum 65534, unity DC gain) | Realistic symmetric lowpass; no saturation at all in this set. Tone at 30 MHz is attenuated. Detects any LSB-level rounding error. |
| hBOOST | 98304, -81920, 65536, -49152, 32768, -16384, 8192, -4096 | Sum of |h| about 5.4, alternating signs: heavy saturation, and the accumulator sees large positive and negative partial sums |
| hEXT | 131071, -131072, 100000, -90000, 65536, -65535, 30001, -1 | Asymmetric, h0 = largest positive and h1 = most negative 18-bit value: catches wrong tap order, narrow tap storage, narrow accumulator |

Checks: all 8 taps read 0 after reset; for each tap k, write `0x30000 + 0x1234 + k` (bit 17 set with
garbage above bit 17) and expect the 18-bit sign-extended negative value; then write
`0xFFFC0000 | (0x1FFFF - k)` and expect the positive value near the maximum; constant 0x200 = 16
survives a write; 0x120 and 0x300 read 0. Each readback is done right after the write to that tap.
(The reads do not re-check earlier taps after a later write, so tap-to-tap aliasing is only caught by
the filter cases, not the readback.)

Broken variants:

| Variant | What is wrong | Caught by |
|---|---|---|
| truncate | no round term | all 12 cases |
| no_sat | wrap | hBOOST and hEXT `rand/chirp/impulse` (6 cases) |
| sat_polarity | wrong rail | the same 6 cases |
| tap_order | h0 applied to the oldest sample (symmetric pairs swapped) | 8 cases; symmetric hLP cannot see it, which is why hBOOST and hEXT are asymmetric |
| tap3_off_by_one | h3 sees x[n-4] | all 12 (latency of failing cases scatter between 4 and 5) |
| h7_narrow | h7 stored in 16 bits | readback `rb_0x11c` (read 0x123b instead of 0xFFFF123B); the filter cases still match because the test values are small |
| acc_narrow | accumulator 32 instead of 36 bits | only 4 cases, those that drive big sums: hBOOST/hEXT `rand` and `chirp` |
| tap7_misaligned | last product skips one pipeline stage (misaligned in time) | 11 cases, partly at lag 0 vs 4 |

### 2.3 HARD: `red_pitaya_notch_block`

What it does: 2nd-order IIR notch. `acc = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]`,
`y = sat14((acc + 2^15) >>> 16)`. The feedback uses the SATURATED y. Max latency 4 (reference: 2).
The feedback loop must close in one clock, which is the hard part: only the b terms can be pipelined.

Registers: 0x100 b0, 0x104 b1, 0x108 b2, 0x10C a1, 0x110 a2 (18-bit signed Q2.16, sign-extended on read),
0x114 bypass (bit 0), 0x200 constant 16. Bypass = `dat_o` is `dat_i` delayed by the SAME latency as the filter.

The hard level uses the older testbench (`tb_notch_judge.v`): it writes bypass = 0 then the five
coefficients itself, whereas easy/medium receive their register writes from a file.

Coefficient sets (3 sets x 4 stimuli = 12 cases):

| Set | f0, r | Coefficients (b0,b1,b2,a1,a2) | Purpose |
|---|---|---|---|
| c5M | 5 MHz, 0.99 | 65536, -126954, 65536, -125685, 64232 | Typical |
| c20M | 20 MHz, 0.95 | 65536, -70232, 65536, -66720, 59146 | Different notch frequency, less sharp |
| lowf | 0.3 MHz, 0.999 | 65536, -131057, 65536, -130926, 65405 | b1 = -131057 against a limit of -131072 (18-bit): any coefficient storage narrower than 18 bits breaks. Poles almost on the unit circle: tiny rounding differences are amplified in the feedback |

Checks:

| Check | What it does |
|---|---|
| `no_x_after_reset` | 40 clocks after reset with `dat_i = 0`: `dat_o` must not be X from cycle 8 on |
| `rb_b0 .. rb_a2` | write 0x20001 / 0x7FFE1234 / 0x1FFFF / 0x30000 / 0xABCD, expect sign-extended 18-bit values 0xFFFE0001, 0xFFFE1234, 0x0001FFFF, 0xFFFF0000, 0x0000ABCD |
| `rb_bypass` | write 1, bit 0 reads 1 (only bit 0 is checked) |
| `rb_coef_frac` | 0x200 reads 16 |
| `bypass` | with bypass = 1, `dat_o` must equal `dat_i` (the first random stimulus, `c5M_rand`) at one fixed latency, and that latency must equal the filter's latency (run_judge.py compares the two). Garbage coefficients are loaded at that time, so a filter that "leaks" into bypass is caught |

Broken variants:

| Variant | What is wrong | Caught by |
|---|---|---|
| truncate | no rounding | all 12 cases |
| unsat_feedback | feeds back the unsaturated sum, output still saturated | 8 cases: c5M `rand/chirp/impulse`, c20M `rand/chirp`, lowf `rand/chirp/impulse`. The `sig` cases never saturate and all pass: this bug is invisible unless the output actually hits a rail |
| a1_sign | wrong sign on a1 | all 12 |
| coef16 | coefficients stored in 16 bits | all 12 cases (b1 does not fit) and all 5 coefficient readbacks |
| bypass_latency | bypass path one register shorter | filter cases ALL pass at latency 2; fails only in the bypass check: "bypass latency 1 != filter latency 2" |

---------------------------------------------------------------------------

## 3. Track B: optimise an existing block (equivalence)

Files: `harness/judge/pid_equiv/{run_judge.py, tb_iq_demod_equiv.v, tb_iq_mod_equiv.v,
tb_pid_equiv.v}`, references in `harness/judge/ref_solutions/{iq_demod, iq_mod, pid}`.

### What "equivalent" means

The ORIGINAL design (vendor RTL, modules renamed with a `ref_` prefix so both live in one
simulation) and the candidate get the same inputs. The candidate output must equal the original
output delayed by ONE common k cycles, with k in 0..8:

```
original  :  ... a  b  c  d  e ...
candidate :  ... .  .  a  b  c ...      <- k = 2, accepted if it holds for ALL compared cycles
```
The testbench keeps a history of the last 9 original outputs and, for each of the 9 lags in
parallel, counts matches and mismatches over 100,000 cycles (`--cycles`). The smallest k with zero
mismatches is the latency. If several outputs exist (two for demod, three for modulator) they
are compared as one concatenated word, so ALL outputs must share the same k. For the modulator,
the original's own outputs have different internal latencies; the same extra delay k is applied to
each, so a candidate that delays only one output by a different amount fails.

FAIL reasons (from `run_judge.py`): no lag matches; X/Z samples; register readback differs (PID);
fewer than half of `--cycles` were actually compared (judge coverage problem); compile error.

Important limit: without Vivado this judge can only prove "same behaviour" (plus the cost of the
extra latency); it cannot show "faster" or "smaller". QoR (timing and resources) is measured
separately by `run_demo.sh` via `run_impl.sh` (Vivado). In `judge.json` it shows as
`qor: SKIPPED` when Vivado is not used.

### Phase cost

`phase_cost_deg_at_1MHz = 360 * 1 MHz * k * clk_period` (k from the search, `clk_period_ns` from
`config/env.yaml`). For k = 1 at 8 ns this is 2.88 degrees. It is the "price" of added latency
in phase margin at a 1 MHz crossover, reported only on PASS.

### Exclusion window after register writes (PID only)

Cycles within `EXCL = MAX_LAG + 2 = 10` clocks after any bus write are not compared (counted as
"EXCLUDED"). Reason: when the pipeline gets deeper, a register change reaches the output at a
different sample than "original delayed by k"; comparing right after the write would be unfair to a
correct pipelined design. IQ blocks have no bus, so `EXCLUDED = 0`.

### 3.1 EASY: `red_pitaya_iq_demodulator_block`

Function: multiplies the 14-bit input by sin and by cos (17-bit) and outputs two 24-bit rounded
slices (`signal1_o`, `signal2_o`). Parameters as instantiated in the IQ block: INBITS 14, OUTBITS 24,
SINBITS 17, SHIFTBITS 1. No reset.

Stimulus: three input signals (sin, cos, signal) driven independently in segments of 50 to 1500 clocks.
Per segment and per signal:

| Choice | Probability / range | Why |
|---|---|---|
| fresh random value every clock | 35% | generic data |
| random value held 2..300 clocks | 30% | slowly changing input, like a real signal; constant stretches expose registers that hold stale data |
| corner values every clock | 15% | max, min, 0, 1, -1, max-1, min+1 chosen at random: carry chains, sign handling, overflow |
| corner value held 2..300 clocks | 20% | the same, but stable |
| width | 50% full width, 50% random narrower width 1..W bits | small-amplitude numbers exercise the low bits and the rounding constant, which full-scale random data hides |

Coverage counters reported in `judge.json`: `negp` (cycles with signal1_o < 0), `posp` (signal2_o > 0),
`fs` (input at a rail). Last run: 99,985 compared cycles, negp 39,866, posp 40,738, fs 8,439. These are
only reported, never required.

Broken variants (the optimized reference adds one register per output, k = 1, phase cost 2.88):

| Variant | What is wrong | Why caught |
|---|---|---|
| no_round | rounding constant removed | off by one LSB in many samples (first mismatch cycle 17: expected 2951576 got 2951575) |
| sincos_swap | sin and cos swapped | outputs swapped |
| one_out_delayed | only one output gets the extra stage | one common k fails (no lag matches both outputs) |
| neg_input | input sign flipped | all outputs wrong |
| slice_off_by_one | output slice taken one bit higher | outputs doubled/halved |

### 3.2 MEDIUM: `red_pitaya_iq_modulator_block`

Function: `dat_o` = saturated sum of (gain1*signal1 + offset(g2)) * sin and (gain4*signal2) * cos, plus
two quadrature outputs `signal_q1_o`, `signal_q2_o` (signal1/2 times g3, scaled and saturated).
Parameters: INBITS 24, OUTBITS 14, SINBITS 17, GAINBITS 18, SHIFTBITS 8. No reset.

Stimulus: eight signals (sin, cos, g1..g4, signal1, signal2) with the same segment/mode scheme as
the demodulator (including narrow-width values and corner values). Corner values drive the gains to
their extremes, which is how the two saturation stages (after the first product, and after the sum)
get exercised. Coverage counters: `sat_hi`, `sat_lo` (dat_o at the rails), `fsat` (the first-stage
product saturated, read from inside the reference), `q1sat`, `q2sat`.

Broken variants: sum_sign (difference instead of sum), no_sat (wrap instead of saturate),
g2_offset (g3 used as offset), q2_gain (q2 scaled by g4), sincos_swap, q2_not_delayed (one output
misses the extra stage). All FAIL.

### 3.3 HARD: `red_pitaya_pid_block` (with filter and lpf blocks)

Function: PyRPL PID: error = input - setpoint, P/I/D terms, integrator with saturation, output
saturation, programmable "arbitrary" output min/max, input filter, differential mode, pause on sync.
The reference is `harness/tasks/B/pid_ref.v` (the vendor file plus one simulation fix
for the undriven `kd_reg_s`). Bus and 15 static registers are compared too.

Stimulus: segments of 300..2500 clocks. At the start of each segment ALL registers are rewritten at
random:

| Register | Normal segment | Saturation episode |
|---|---|---|
| setpoint 0x104 | random, from full scale down to 1/8 scale | +8191 or -8192 |
| kp 0x108 | 6 to 13 random bits (gain < 2) | at least 0x400000 (huge gain); in the integrator-only half: 0 |
| ki 0x10C | 50% zero, else random up to 21 bits | at least 0x7F0000 |
| kd 0x110, filter 0x120 | random (filter 50% off) | same |
| out_min / out_max 0x124/0x128 | 30%: random pair (a pair generated inverted is put in order 80% of the time, so 20% of such pairs stay min > max); else full range | integrator-only half: always full range; other episodes: as in a normal segment |
| mode bits 0x12C | random | 0 |
| ival 0x100 | mostly small, sometimes full range | same |

About 20% of segments are "saturation episodes": long (3000..6000 clocks), DC-heavy inputs (square
wave or piecewise-constant), setpoint at a rail, huge kp or ki, so the output and the integrator are
driven into saturation and stay there. Half of these episodes set kp = 0 ("integrator-only"), so
that the integrator's own saturation is visible at `dat_o` (otherwise the proportional term would
dominate). Without such episodes the integrator wrap/saturate logic is almost never reached: the
`int_wrap` variant differs from the reference in only 448 of 97,397 compared cycles.

Input types in a normal segment (8 modes, chosen uniformly): white noise of random amplitude; random walk;
square wave; piecewise-constant steps; and four closed-loop modes (4..7) where the plant is a first-order
low-pass of `-dat_o` plus noise, built from the REFERENCE output. Purpose: with open-loop inputs and random
gains the PID output tends to sit on a rail; closed loop keeps the loop around its operating point so the
linear region, the integrator and the filters are exercised. (The code only says "closed loop";
this motivation is the obvious reading, not stated in the code.) The difference input (`diff_dat_i`)
is a random walk; `sync_i` toggles at random (about 1 in 200 clocks); mid-segment writes of `ival` occur
about once per 800 clocks.

Readback: after each segment's register writes, 15 registers are read from both designs and compared
(`ack` and `rdata` must be identical): 0x104, 0x108, 0x10C, 0x110, 0x120, 0x124, 0x128, 0x12C and the
constants 0x200, 0x204, 0x208, 0x20C, 0x220, 0x224, 0x228. 0x100 (the integrator state) is NOT compared.
The testbench comment says "static, readable registers (0x100 = integrator state, excluded)": the value
at 0x100 changes every clock and depends on when it is sampled, so with a deeper pipeline it could
legitimately differ (this reasoning is inferred, the code only states the exclusion). Last run: 735 reads
(49 segments), 0 mismatches for the reference.

Coverage counters (last run, 100,000 cycles): compared 97,397, excluded 2,588, `sat_hi` 34,172 (output at
+rail), `sat_lo` 6,180, `isat` 1,425 (integrator at its limit), `arbsat` 58,194 (output differs from the
internal PID output, i.e. the arbitrary min/max clamp was active). These are reported, not enforced:
nothing fails if a counter is 0.

Broken variants (reference optimized solution: k = 1):

| Variant | What is wrong | Caught by |
|---|---|---|
| no_arb_sat | arbitrary saturation removed | segments with out_min/out_max set (first mismatch at cycle 7097) |
| sat_polarity | output saturation swaps rails | first mismatch at cycle 28 |
| p_only_delay | extra stage only on P path; P and I misaligned | best lag 0 matches only 83,235 of 97,397 |
| int_wrap | integrator wraps instead of saturating | kp = 0 integrator-saturation episodes (448 mismatching cycles at the best lag; first mismatch at cycle 44623) |
| readback | Kp register reads back Ki | the readback comparison: 49 of 735 reads differ, while the output matches at k = 1 |

### How the agent's mini check differs from the hidden judge

`harness/tools/run_equiv.sh` with `_equiv_tb.v` (PID), `_equiv_tb_iq_demod.v`, `_equiv_tb_iq_mod.v` is a small
sanity tool the agent can run. It uses the same idea (original delayed by k, k in 0..8) but is far weaker:

| | Agent mini check (`run_equiv.sh`) | Hidden judge |
|---|---|---|
| Length | 4 configs x 1000 cycles (PID) | 100,000 cycles |
| PID configuration | 4 fixed configs (setpoint, kp, ki, one with limits -2000..3000) | random every segment, saturation episodes, closed loop, kd, filter, diff mode, pause on sync |
| Input | uniform random, `sync` pause once | 8 input modes and closed-loop plant |
| Registers read back | 5 (0x104, 0x108, 0x10C, 0x124, 0x128) | 15 per segment |
| Seed | fixed 7 | fixed seed |
| Coverage counters | none | saturation, integrator, arbitrary-saturation counters |
| X check | not done explicitly (X mismatches simply fail) | explicit X count |
| Settle | skips first 20 cycles; excludes 10 cycles after writes | 16 cycles; 10 cycles after writes |

So a design can pass the mini check and still fail the hidden judge, typically on integrator saturation
or arbitrary saturation corner cases. (Why the mini check is weaker was not stated in the files; it is
visibly intended to be a small quick check.)

---------------------------------------------------------------------------

## 4. Track C: bug hunt (code review)

Files: `harness/judge/bughunt/{bugs.py, score.py, answer_key_{easy,medium,hard}.yaml, selftest.py}`.

### How bugs are seeded

`bugs.py` takes the vendor RTL and applies ONE-LINE replacements, so line numbers in the patched files
are the same as in the original. Where a line is deleted the line is left blank. The agent receives only
the patched files (the "review set") and must write `bugs.json`, a list of `{file, line, description}`.
The self-test checks that the patched files still compile with no new compiler warning (so bugs
cannot be found by a compiler) and that line counts are unchanged.

### Levels and bugs

| Level | Files reviewed | Bugs |
|---|---|---|
| easy | filter_block, lpf_block | 3 |
| medium | pid_block, asg_ch (filter, lpf as unchanged dependencies) | 5 |
| hard | pid_block, filter_block, lpf_block, iq_block, asg_ch (plus 6 unchanged dependencies) | 10 |

| Bug id | File : line | Kind | Effect | Levels |
|---|---|---|---|---|
| filter_on_bit | filter_block : 81 | slice off by one | `filter_on` reads bit 6 (the highpass bit) instead of bit 7 | easy, hard |
| lpf_yout_slice | lpf_block : 100 | slice off by one | output slice shifted down one bit: drops sign bit, doubles output | easy, hard |
| lpf_blocking | lpf_block : 109 | blocking assignment | `delta = ...` (blocking) in a clocked block: y sees the new delta in the same cycle | easy, hard |
| pid_error_sign | pid_block : 205 | sign | error = setpoint minus input instead of input minus setpoint | medium, hard |
| pid_sat_polarity | pid_block : 317 | saturation polarity | positive overflow saturates to 0x2000 (most negative) | medium, hard |
| asg_pipeline_removed | asg_ch : 116 | removed pipeline register | multiplier fed from `dac_rd`, bypassing the `dac_rdat` timing register | medium, hard |
| asg_sat_polarity | asg_ch : 121 | saturation polarity | output saturation inverted: clamps to the opposite rail | medium, hard |
| asg_rep_cnt_reset | asg_ch : 146 | missing reset | the line `rep_cnt <= 16'h0;` is deleted | medium, hard |
| iq_cfg_slice | iq_block : 128 | slice off by one | config bits taken from wdata[4:0] instead of wdata[5:1] | hard |
| iq_sum_sign | iq_block : 327 | sign | I averaging accumulates `-quadrature1` (Q path still adds) | hard |

### How scoring works

For each reported item the scorer decides one verdict:

| Verdict | Meaning |
|---|---|
| found | same file name (path prefixes are stripped), line within +-3 of a seeded bug, AND the description contains at least one of that bug's keywords (case-insensitive substring) |
| duplicate | a correct report of a bug that another report has already been credited for |
| near_miss | right place (+-3) but the description does not mention any keyword: no credit, not counted as a false alarm |
| known_upstream_issue | a real issue in the unmodified vendor code (`PREEXISTING` list, e.g. out_buffer without reset, undriven `kd_reg_s`): neither credit nor penalty |
| false_positive | anything else |

Matching is one-to-one and maximal (Kuhn augmenting paths, nearest first), so two nearby bugs can both be
credited when each has its own report. A report exactly inside a known upstream line range (and not exactly
on a seeded bug line) is treated as that upstream issue even if a seeded bug is within 3 lines. Example in the
self-test: filter_block line 80 (upstream 5-bit shift) next to the seeded bug at line 81 gives
`known_upstream`, not found and not near_miss.

Keywords are deliberately tied to the real problem: e.g. `lpf_blocking` needs the word "blocking",
`asg_rep_cnt_reset` needs "reset"/"uninitiali...", the saturation-polarity bugs need words like "polarity",
"opposite", "wrong rail", "swap", "invert" (or '2000' for the pid one). So "overly complex overflow logic"
on the right line is a near miss, not a find (taken from a real model run, per `selftest.py`).

Output status: `SCORED`, or `INVALID_OUTPUT` when the file cannot be parsed and has no usable items.

### Robustness features of the scorer

* JSON wrapped in a Markdown fence is unwrapped.
* Stray backslashes inside strings (LaTeX such as `\mu`, `\text`) are escaped and the file re-parsed;
  a warning "repaired" is recorded.
* A top-level `{"bugs": [...]}` is accepted as well as a plain list.
* File names are reduced to their base name, so `review/red_pitaya_asg_ch.v` and Windows backslash paths work.
* Entries without a usable file/line are skipped and counted in the warning.
* Descriptions are cut to 300 characters.

Self-test (`selftest.py`): the review set compiles; each level's own key scores 100%; the hard key shifted by
+3 and -3 lines still scores 100%; empty answer = 0 found; one bogus line = 1 false positive; vague report =
near miss; line 80 = upstream; three copies of one bug = 1 found; path prefix and backslashes accepted; garbage
file gives a warning, not a crash; LaTeX backslashes repaired.

---------------------------------------------------------------------------

## 5. Basic demo judges

These are the small two-task demo (`basic/`). `py basic/selftest.py` confirms: both reference solutions PASS
and both broken variants of each task FAIL.

### 5.1 `fpga_gain` (`basic/tasks/fpga_gain/judge.py`, `hidden/tb.v`)

Block: same as the Track H gain block. Settings `(gain, shift, offset)`:

| Setting | Why |
|---|---|
| (3000, 8, 100) | ordinary positive gain about 11.7; large inputs saturate |
| (-12345, 7, -500) | negative gain about -96, heavy saturation, negative offset |
| (32767, 10, 200) | maximum gain, large shift |
| (1, 0, 0) | identity with shift = 0 (no rounding term) |

Two stimuli of 600 samples each: uniform random in the full 14-bit range (seed 1234), and a full-scale
sine (amplitude 8191, period 37 samples). 8 cases in total.

Method: the hidden testbench resets, writes the three registers, streams the samples and writes `dat_o`
once per line. The judge tries latency 0..4 per case, ignores the first 8 output samples (`SKIP = 8`, counted
as samples, not cycles after reset), and counts wrong samples at the best latency. X/Z counts as wrong. All cases
are scored even after a failure.

* Score = percentage of compared samples correct at each case's best latency (printed as "SCORE: n% ...").
* PASS needs 100% AND at least one latency that is exact for ALL 8 cases ("latency is not the same for all
  settings" otherwise).
* Self-test results: reference PASS at latency 3; `broken_truncate` FAIL with 26 of 592 samples wrong in the
  first case (so a small bug gives a high score but still fails); `broken_no_sat` FAIL with 544 of 592 wrong.
* There is no register readback test and no separate X test here.

### 5.2 `py_func` (`basic/tasks/py_func/judge.py`, `hidden/test_hidden.py`)

Function: `requantize(x, gain, shift, bits=14)` = `clamp((x*gain + half) >> shift)` with `half = 2^(shift-1)` if
shift > 0 else 0, round half up, clamp to `bits` signed bits.

20 hidden checks. The judge runs every case (a crash counts as wrong), prints
"SCORE: n% (k of N hidden cases correct)", and reports the first failure. PASS needs all 20.

| Group | Cases | What it tests |
|---|---|---|
| shift = 0 | (100,3,0) = 300, (-100,3,0) = -300 | no rounding term at all |
| exact ties, shift 1 | 5/2 = 2.5 gives 3; -5/2 = -2.5 gives -2; 3/2 gives 2; -3/2 gives -1 | round half UP (towards +infinity) for positive and negative ties. Truncation or round-half-away-from-zero fails here |
| non-ties | 0.25 gives 0; -0.25 gives 0; -0.75 gives -1 | negative values rounded via arithmetic shift, not toward zero |
| normal | (1000,100,4) = 6250 | ordinary scale |
| saturation | 8191*32767 >> 0 clamps high; -8192*32767 clamps low; 8191*(-32768)>>3 clamps low (negative gain); high with shift 4 | both rails, with and without a shift |
| `bits = 8` | 100 passes; 200 gives 127; -200 gives -128; 127 and -128 pass unchanged | the `bits` parameter is honoured, rails at exactly the edge |
| default `bits` | `rq(7,3,2)` must equal `rq(7,3,2,14)` | default argument is 14 (the expected value is computed from the candidate itself, not a constant) |

Broken variants: `broken_truncate` (half term always 0) fails the first tie case; `broken_no_sat` (wraps instead
of clamping) fails the first saturation case.

---------------------------------------------------------------------------

## 6. Reading a failure

| Message / status | Plain meaning | What to look at |
|---|---|---|
| `COMPILE_ERROR` | The candidate would not compile together with the hidden testbench (H: `judge_data/judge.log`; B: same) | Port names/widths must match the spec exactly; the testbench instantiates the module by name |
| `NO_CANDIDATE` | The runner found no file with the module name in the agent workspace | The file name and `module <name>` line |
| `no lag in [0,8] matches: best lag k matches a/b, first mismatch cycle c expected e got g` (Track B) | The candidate is not "original delayed by a constant" at any lag. The best lag is shown with its first mismatch | Look at cycle c in a waveform; large `a/b` (e.g. 96,949 of 97,397) means a rare condition such as saturation; small means a systematic error |
| `FAIL <case>: lat=k match=a/b first={n, expected, got}` (Track H) | The case differs from the model; k is the best latency and n the first wrong sample | The case name tells you the stimulus (`rand`, `chirp`, `impulse`, `sig`) and the parameter set; an error only in saturating cases points to saturation/rounding |
| H `FAIL check rb_0x...: got= exp=` | A register readback value is wrong | Sign extension or field width of that register |
| H `FAIL check bypass: bypass latency X != filter latency Y` | Bypass has a different delay from the filter | Align bypass path with filter latency |
| H status FAIL but no line printed | Possible if cases match but the latency differs between cases | In `judge.json`: `latency` is null and the cases show different `latency` values (see surprises; no explicit message exists in Track H for this) |
| `latency is not the same for all settings` (basic only) | Each case is correct at some latency, but no single latency works for all | A mode (e.g. shift = 0) takes a shorter or longer path |
| `bypass latency mismatch` | See above | |
| `register readback differs (n of m reads)` (Track B hard) | A readable register returns something different from the original | Register map and read multiplexer |
| `N X/Z output samples` | Candidate outputs unknown values after the settle window | Missing reset or an uninitialised register that reaches the output |
| `only N cycles compared (judge coverage problem)` | Less than half the cycles were comparable | Judge/setup problem, not the candidate |
| `near_miss` (Track C) | Right line, but your explanation did not name the real problem | Be specific about what is wrong (e.g. "wrong rail", "blocking assignment") |
| `duplicate`, `known_upstream_issue` | No credit, no penalty | |
| `false_positive` | A report with no match to a seeded bug and not a known upstream issue | |
| `INVALID_OUTPUT` | `bugs.json` could not be parsed and nothing usable was in it | JSON syntax |
| `JUDGE_ERROR` | The judge itself crashed (judge.json written by the runner with the error text) | Not a candidate fault; see `judge_console.log` |

---------------------------------------------------------------------------

## 7. Leak check (`harness/judge/leak_check.py`)

Every hidden file contains the canary `CANARY-b81aed453118`. After a run the checker scans every logged LLM
request body (everything the model was shown, including tool output) and every file in the agent workspace.
Finding the canary means hidden content reached the agent: `leak_suspected = true` and exit code 1.
Finding only hidden path names (`ref_solutions`, `harness/judge`, `tb_notch_judge`, `tb_pid_equiv`,
`gen_stimuli`, `make_broken`, `judge_selftest`) is reported as "access attempts" but does not fail the run.

---------------------------------------------------------------------------

## 8. Where the files are

| What | Path |
|---|---|
| Shared constants (settle, seed, canary) | `harness/judge/common.py` |
| Track H runner, level table, stimuli, compare | `harness/judge/notch/{run_judge.py, levels.py, gen_stimuli.py, compare.py}` |
| Track H testbenches | `harness/judge/notch/tb_dsp_judge.v` (easy, medium), `tb_notch_judge.v` (hard) |
| Track H specs and golden models (agent visible) | `harness/tasks/H/{notch_spec.md, notch_model.py}`, `H/easy/`, `H/medium/` |
| Track H reference + broken | `harness/judge/ref_solutions/{gain, fir, notch}/` (`make_broken.py`, `broken/`) |
| Track B runner and testbenches | `harness/judge/pid_equiv/{run_judge.py, tb_iq_demod_equiv.v, tb_iq_mod_equiv.v, tb_pid_equiv.v}` |
| Track B reference + broken | `harness/judge/ref_solutions/{iq_demod, iq_mod, pid}/` (`make_*_solutions.py`) |
| Track B originals the candidate is compared with | `harness/tasks/B/pid_ref.v` (PID); vendor RTL in `vendor/pyrpl/pyrpl/fpga/rtl/` (IQ blocks) |
| Agent mini check | `harness/tools/run_equiv.sh`, `_equiv_tb.v`, `_equiv_tb_iq_demod.v`, `_equiv_tb_iq_mod.v` |
| Track C | `harness/judge/bughunt/{bugs.py, score.py, selftest.py, answer_key_*.yaml, patches/}` |
| Leak check | `harness/judge/leak_check.py` |
| Judge self-test | `harness/judge/judge_selftest.sh [H|B|C|all]`, outputs in `runs/selftest/` |
| Basic demo | `basic/tasks/fpga_gain/{judge.py, hidden/}`, `basic/tasks/py_func/{judge.py, hidden/}`, `basic/selftest.py` |
| Where the judges are called | `harness/run_stages.py` (function `judge`), `run_demo.sh` |
