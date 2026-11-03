# Spec: `red_pitaya_notch_block` (second-order IIR notch filter)

Write a new Verilog module, `red_pitaya_notch_block.v`. It must match the Python golden model `notch_model.py` **bit for bit**.

## Ports (same style as `red_pitaya_pid_block.v`)

```verilog
module red_pitaya_notch_block (
   input                    clk_i,    // 125 MHz processing clock
   input                    rstn_i,   // synchronous reset, active low
   input  signed [14-1:0]   dat_i,    // input sample, one per clock
   output signed [14-1:0]   dat_o,    // output sample, one per clock
   input         [16-1:0]   addr,     // bus address (byte offset)
   input                    wen,      // bus write enable
   input                    ren,      // bus read enable
   output reg               ack,      // bus acknowledge
   output reg    [32-1:0]   rdata,    // bus read data
   input         [32-1:0]   wdata     // bus write data
);
```

The bus behaves exactly like `red_pitaya_pid_block.v`: on every clock, `ack <= wen|ren`, and `rdata` is registered from `addr` (one cycle of read latency). The judge waits for `ack`.

## Register map

| addr | name | access | format |
|---|---|---|---|
| `0x100` | b0 | R/W | 18-bit signed Q2.16 in `wdata[17:0]`; reads back sign-extended to 32 bits |
| `0x104` | b1 | R/W | same |
| `0x108` | b2 | R/W | same |
| `0x10C` | a1 | R/W | same |
| `0x110` | a2 | R/W | same |
| `0x114` | bypass | R/W | bit 0. 1 = `dat_o` is `dat_i` delayed by the same fixed latency as the filter path |
| `0x200` | COEF_FRAC | R | constant 16 |

Unknown addresses read 0. On reset, all coefficients and bypass are 0.

## Arithmetic (must match `notch_model.py` exactly)

```
acc  = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]   (full precision, no overflow)
y[n] = sat14( (acc + 2^15) >>> 16 )      arithmetic shift right, i.e. round half up
sat14(v) clamps v to [-8192, 8191]
```
- x and y are signed 14-bit. Coefficients are signed 18-bit with 16 fraction bits.
- The feedback terms use the **saturated** `y` values.
- All filter state starts at 0 after reset.
- Products are 14×18 bits. Size the accumulator so nothing overflows (at least 35 bits signed).

## Timing / throughput
- One output sample per clock (fs = clk = 125 MHz).
- Output latency: any **fixed** latency of ≤ 4 clock cycles from `dat_i` to `dat_o` is acceptable. State it in `AGENT_REPORT.md`.
- Target clock: 125 MHz (8 ns period).
- **Hard point:** the recursive path (y[n-1] → multiply by a1 → accumulate → round → saturate → y[n]) has to complete in **one clock cycle**, because y[n] is needed for y[n+1]. You can pipeline the feed-forward part (the b terms) freely. You cannot pipeline the feedback loop without changing the result.

## Golden model
`notch_model.py` (in this folder):
- `notch_coeffs(f0, r)`: quantized coefficients
- `notch(x, coeffs)`: bit-true output
- CLI: `<python> notch_model.py coeffs --f0 5e6 --r 0.99` and `<python> notch_model.py run --in stim.txt --out y.txt --f0 5e6 --r 0.99`. Files have one signed integer per line. Use the Python command named by `PYTHON=` in `tools/tool_env.sh`.

## How you will be judged (by an independent checker you cannot see)
- Hidden stimuli: several signal types and several coefficient sets, including inputs that drive the output into saturation. Your output must match the model exactly at a single fixed latency of 0–4 cycles.
- Register readback, bypass mode, and no X/Z on `dat_o` after reset.
- Synthesis resources and timing are reported.
