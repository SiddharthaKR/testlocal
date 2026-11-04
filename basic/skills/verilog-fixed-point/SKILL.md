---
name: verilog-fixed-point
description: Signed fixed-point arithmetic in Verilog (multiply, shift, rounding, saturation, register buses, reset) and how to verify it against a golden model with a self-checking testbench under iverilog. Use before writing or debugging DSP-style RTL.
---

# Verilog fixed-point: practical rules

## Signed arithmetic and widths
- Declare signed things `signed` (`reg signed [15:0] k;`). One unsigned operand makes the whole
  expression unsigned, silently. Constants too: use `8'sd5`, not `5`. Use `$signed(x)` to cast.
- A product needs `wa + wb` bits. Declare the result wide enough BEFORE multiplying, and keep
  the sum of products and offsets at full width. Extra bits are free; lost bits are bugs.
- Use `>>>` on signed values (arithmetic shift). `>>` shifts in zeros and breaks negatives.
- Do not slice (`x[13:0]`) a value before it is saturated; slicing drops the sign.

## Round half up, then shift
```verilog
wire signed [31:0] half = (shift == 0) ? 32'sd0 : (32'sd1 <<< (shift - 1));
wire signed [31:0] r    = (p + half) >>> shift;
```
Adding `1 << (shift-1)` before `>>>` rounds ties up. Plain `>>>` floors. The `shift == 0` case
must be special-cased: `1 << -1` is meaningless.

## Saturation to N bits
```verilog
// t is wide; N = 14 here only as an example
wire signed [N-1:0] y = (t > MAX) ? MAX : (t < MIN) ? MIN : t[N-1:0];
```
Saturate once, at the end, on the wide value; never clamp an intermediate. Add any offset before
saturating if the spec says so.

## Registers, buses, reset
- Registered outputs and a pipeline of fixed depth: latency must not depend on any setting
  (no bypass path for "special" values).
- Reset synchronously and active low where specified: `always @(posedge clk) if (!rstn) ... else ...`.
  Give every register a defined reset value; unreset registers read as X.
- Use non-blocking `<=` in clocked blocks, blocking `=` only in combinational blocks.
- Typical register bus: a write enable and address decode update registers; a read returns
  registered data one cycle later; an acknowledge follows the request; unmapped addresses read 0.
- Read signed registers back sign-extended (`{{N{r[msb]}}, r}`), unsigned ones zero-extended.

## Self-checking testbench against a golden model
1. Generate stimulus and expected output with a Python model (one integer per line).
2. The testbench reads stimulus (`$fscanf`/`$readmemh`), resets, programs the registers, streams samples.
3. Each clock, dump the output: `$fdisplay(fd, "%0d", dat_o);` (output must be `signed` to print negatives).
4. Compare with the model allowing one fixed latency of N cycles (`hw[i+N] == model[i]`); print
   `FAIL ...` with index, got and expected, so a short tool summary shows it. Then `$finish`.
5. Test several settings and stimuli, including ones that saturate and the smallest/largest shifts.

## Syntax pitfalls (Verilog-2001, iverilog `-g2012`)
- Signal names must not contain `$`; do not use it outside system tasks.
- Declare wires/regs at module level, not inside `always`/`begin` blocks (unless the block is named).
- Size every constant (`16'h100`, `14'sd8191`); unsized ones are 32-bit and may surprise you.
- Do not assign one reg from two always blocks; do not mix blocking and non-blocking on one signal.

## Iterating
Fix the FIRST compiler error, recompile, repeat (later errors are often consequences). When the
simulation mismatches, print the first differing index, input, got and expected, and look for the
signature: off by one near ties = rounding, huge values = missing saturation, sign flips = missing `signed`.
