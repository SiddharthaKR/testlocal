# Spec: `red_pitaya_gain_block` (programmable gain, shift and offset)

Write a new Verilog module, `red_pitaya_gain_block.v`. It must match the Python golden model `gain_model.py` **bit for bit**.

## Ports (same style as `red_pitaya_pid_block.v`)

```verilog
module red_pitaya_gain_block (
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
| `0x100` | gain | R/W | 16-bit signed in `wdata[15:0]`; reads back sign-extended to 32 bits |
| `0x104` | shift | R/W | 4-bit unsigned in `wdata[3:0]` (0..15); reads back zero-extended |
| `0x108` | offset | R/W | 14-bit signed in `wdata[13:0]`; reads back sign-extended to 32 bits |
| `0x200` | GAIN_BITS | R | constant 16 |

Unknown addresses read 0. On reset, all registers are 0.

## Arithmetic (must match `gain_model.py` exactly)

```
p = x * gain                                             full precision (14 x 16 bits, no overflow)
r = (p + (shift > 0 ? 1 << (shift-1) : 0)) >>> shift     arithmetic shift right, round half up
y = sat14(r + offset)
sat14(v) clamps v to [-8192, 8191]
```
- x and y are signed 14-bit. gain is signed 16-bit. offset is signed 14-bit.
- The offset is added **after** the shift and rounding, and saturation is applied once at the end.
- There is no state and no feedback: each output depends only on the matching input sample and the current register values.

## Timing / throughput
- One output sample per clock (fs = clk = 125 MHz).
- Output latency: any **fixed** latency of 0 to 4 clock cycles from `dat_i` to `dat_o` is acceptable, and it must be the same for every register setting. State it in `AGENT_REPORT.md`.
- Target clock: 125 MHz (8 ns period).

## Golden model
`gain_model.py` (in this folder):
- `gain_block(x, gain, shift, offset)`: bit-true output
- CLI: `<python> gain_model.py run --in stim.txt --out y.txt --gain 3000 --shift 8 --offset 100`. Files have one signed integer per line. Use the Python command named by `PYTHON=` in `tools/tool_env.sh`.

## How you will be judged (by an independent checker you cannot see)
- Hidden stimuli: several signal types and several (gain, shift, offset) settings, including settings and inputs that drive the output into saturation, and a setting with shift = 0. Your output must match the model exactly at a single fixed latency of 0 to 4 cycles.
- Register readback (including sign extension and the constant), and no X/Z on `dat_o` after reset.
- Synthesis resources and timing are reported.
