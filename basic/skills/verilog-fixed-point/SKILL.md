---
name: verilog-fixed-point
description: Signed fixed-point arithmetic in Verilog (gain, shift, rounding, saturation, bus registers) and how to verify it against a Python model with a CSV-writing testbench. Load before writing DSP-style RTL.
---

# Verilog fixed-point: practical rules

## Signed arithmetic
- Declare everything that is signed as `signed`: `reg signed [15:0] gain;`. One unsigned
  operand in an expression makes the whole expression unsigned (silent bug).
- Widths: a product needs `wa + wb` bits (14 x 16 -> 30). Declare the result wide enough
  (e.g. 32 bits) BEFORE multiplying. Extra bits are free; lost bits are bugs.
- Use `>>>` (arithmetic shift) on signed values. `>>` shifts in zeros and breaks negatives.
- Slicing (`x[13:0]`) drops the sign information; only slice after saturating.

## Round half up, then shift
```verilog
wire signed [31:0] half = (shift == 0) ? 32'sd0 : (32'sd1 <<< (shift - 1));
wire signed [31:0] r    = (p + half) >>> shift;     // adding 1<<(shift-1) = round half up
```
Plain `p >>> shift` truncates toward minus infinity: wrong for ties and for the .5 case.

## Saturation to 14 bit
```verilog
wire signed [31:0] t = r + offset;                  // do the add at full width
wire signed [13:0] y = (t >  8191) ?  14'sd8191 :
                       (t < -8192) ? -14'sd8192 : t[13:0];
```
Saturate ONCE, at the end, on the wide value. Never clamp an intermediate.

## Registered bus pattern
```verilog
always @(posedge clk_i) if (!rstn_i) begin ... end else begin
  if (wen && addr == 16'h100) gain <= wdata[15:0];
  ack <= wen | ren;
  case (addr) 16'h100: rdata <= {{16{gain[15]}}, gain}; default: rdata <= 0; endcase
end
```
- Read back signed registers sign-extended (`{{N{reg[msb]}}, reg}`), unsigned ones zero-extended.
- Pipeline the datapath (input reg -> multiply reg -> output reg); latency is then fixed.

## Testbench that writes CSV
1. Generate stimulus with Python (one integer per line); read it with `$fscanf`/`$readmemh`.
2. Reset, write the registers through the bus (set `addr/wdata`, pulse `wen` one cycle).
3. Each clock: `$fdisplay(fd, "%0d", dat_o);` (`dat_o` must be `signed` to print negatives).
4. `$finish`. Compare the CSV with the Python model allowing a fixed latency of N cycles:
   `y_hw[i + N] == model[i]`. Print `FAIL ...` on mismatch so the run_sim tool shows it.

## Common mistakes
- Forgetting `signed` on a register, a constant (`1'b1` vs `1'sb1`), or a wire.
- Truncating instead of rounding; saturating before adding the offset.
- Using `<<` / `>>` where `<<<` / `>>>` is needed.
- Shift amount of 0: `1 << (shift-1)` is invalid, special-case it.
- Different latency for different settings (e.g. bypass path when shift == 0).
- Reading X: registers not reset; testbench drives inputs before reset ends.
