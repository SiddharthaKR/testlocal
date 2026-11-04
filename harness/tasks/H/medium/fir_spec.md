# Spec: `red_pitaya_fir_block` (8-tap FIR filter)

Write a new Verilog module, `red_pitaya_fir_block.v`. It must match the Python golden model `fir_model.py` **bit for bit**.

## Ports (same style as `red_pitaya_pid_block.v`)

```verilog
module red_pitaya_fir_block (
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
| `0x100` | h0 | R/W | 18-bit signed Q2.16 in `wdata[17:0]`; reads back sign-extended to 32 bits |
| `0x104` | h1 | R/W | same |
| `0x108` | h2 | R/W | same |
| `0x10C` | h3 | R/W | same |
| `0x110` | h4 | R/W | same |
| `0x114` | h5 | R/W | same |
| `0x118` | h6 | R/W | same |
| `0x11C` | h7 | R/W | same |
| `0x200` | COEF_FRAC | R | constant 16 |

Unknown addresses read 0. On reset, all taps are 0.

## Arithmetic (must match `fir_model.py` exactly)

```
acc  = h0*x[n] + h1*x[n-1] + h2*x[n-2] + ... + h7*x[n-7]    (full precision, no overflow)
y[n] = sat14( (acc + 2^15) >>> 16 )      arithmetic shift right, i.e. round half up
sat14(v) clamps v to [-8192, 8191]
```
- x and y are signed 14-bit. Taps are signed 18-bit with 16 fraction bits (range -2.0 to +1.99998).
- `h0` multiplies the newest sample `x[n]`, `h7` the oldest `x[n-7]`.
- The delay line starts at 0 after reset (x[m] = 0 for m < 0).
- Products are 14 x 18 bits. Size the accumulator so nothing overflows (at least 35 bits signed: a sum of 8 products needs 3 more bits than one product).
- There is no feedback.

## Timing / throughput
- One output sample per clock (fs = clk = 125 MHz).
- Output latency: any **fixed** latency of 0 to 8 clock cycles from `dat_i` to `dat_o` is acceptable. State it in `AGENT_REPORT.md`.
- Target clock: 125 MHz (8 ns period). Eight 14x18 multiplications and their sum in one cycle will probably not meet 8 ns, but because there is no feedback you may pipeline the multipliers and the adder tree freely; this only changes the latency.

## Golden model
`fir_model.py` (in this folder):
- `lowpass_taps(fc)`: example quantized lowpass taps
- `fir(x, h)`: bit-true output
- CLI: `<python> fir_model.py taps --fc 8e6` and `<python> fir_model.py run --in stim.txt --out y.txt --h h0,h1,h2,h3,h4,h5,h6,h7`. Files have one signed integer per line. Use the Python command named by `PYTHON=` in `tools/tool_env.sh`.

## How you will be judged (by an independent checker you cannot see)
- Hidden stimuli: several signal types and several tap sets (including asymmetric sets with taps near the 18-bit limits), including inputs that drive the output into saturation. Your output must match the model exactly at a single fixed latency of 0 to 8 cycles.
- Register readback (including sign extension of every tap and the constant), and no X/Z on `dat_o` after reset.
- Synthesis resources and timing are reported.
