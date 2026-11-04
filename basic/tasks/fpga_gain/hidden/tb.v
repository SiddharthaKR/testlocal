// Hidden testbench: configures the DUT over the bus, streams a stimulus file (one integer
// per line) one sample per clock, and writes dat_o once per clock (one integer per line).
// Plusargs: +gain= +shift= +offset= +stim=<file> +out=<file>
//       or  +mode=bus +out=<file>   (bus checks: reset values, readback, constant, unknown address, ack, no X)
`timescale 1ns/1ps
module tb;
  reg clk = 0, rstn = 0;
  reg  signed [13:0] dat_i = 0;
  wire signed [13:0] dat_o;
  reg  [15:0] addr = 0;
  reg         wen = 0, ren = 0;
  reg  [31:0] wdata = 0;
  wire        ack;
  wire [31:0] rdata;

  red_pitaya_gain_block dut (.clk_i(clk), .rstn_i(rstn), .dat_i(dat_i), .dat_o(dat_o),
    .addr(addr), .wen(wen), .ren(ren), .ack(ack), .rdata(rdata), .wdata(wdata));

  always #4 clk = ~clk;                      // 125 MHz

  integer gain, shift, offset, n, fin, fout, i, r, v;
  reg [1023:0] stim_name, out_name;
  reg signed [13:0] mem [0:65535];

  reg [1023:0] mode;
  reg [31:0] got;
  integer acked;

  // read one register; the spec says ack and rdata come one clock after ren
  task bus_read(input [15:0] a, output [31:0] d);
    begin
      @(negedge clk); addr = a; ren = 1;
      @(negedge clk); ren = 0; acked = (ack === 1'b1); d = rdata;
    end
  endtask

  // one bus check: "CHECK <name> PASS|FAIL got=<hex> exp=<hex>"
  task expect_read(input [8*24-1:0] name, input [15:0] a, input [31:0] exp);
    begin
      bus_read(a, got);
      $fdisplay(fout, "CHECK %0s %0s got=%h exp=%h ack=%0d", name,
                (got === exp && acked) ? "PASS" : "FAIL", got, exp, acked);
    end
  endtask

  task bus_write(input [15:0] a, input [31:0] d);
    begin
      @(negedge clk); addr = a; wdata = d; wen = 1;
      @(negedge clk); wen = 0;
      @(negedge clk);                         // ack is visible here
    end
  endtask

  initial begin
    if ($value$plusargs("mode=%s", mode) && mode == "bus") begin
      if (!$value$plusargs("out=%s", out_name)) begin $display("FAIL: missing +out"); $finish; end
      fout = $fopen(out_name, "w");
      repeat (5) @(negedge clk);
      rstn = 1;
      repeat (10) @(negedge clk);
      $fdisplay(fout, "CHECK no_x_after_reset %0s got=%b exp=no-X ack=1", (^dat_o === 1'bx) ? "FAIL" : "PASS", dat_o);
      expect_read("reset_gain",   16'h100, 32'h0);
      expect_read("reset_shift",  16'h104, 32'h0);
      expect_read("reset_offset", 16'h108, 32'h0);
      expect_read("const_0x200",  16'h200, 32'd16);
      expect_read("unknown_addr", 16'h300, 32'h0);
      bus_write(16'h100, 32'hABCD_8001);          // upper junk ignored; -32767 sign-extended
      bus_write(16'h104, 32'hFFFF_FFF5);          // 4-bit field: 5
      bus_write(16'h108, 32'h0000_2005);          // 14-bit signed: -8187 sign-extended
      expect_read("gain_signext",   16'h100, 32'hFFFF_8001);
      expect_read("shift_4bit",     16'h104, 32'h0000_0005);
      expect_read("offset_signext", 16'h108, 32'hFFFF_E005);
      $fclose(fout);
      $finish;
    end
    if (!$value$plusargs("gain=%d", gain) || !$value$plusargs("shift=%d", shift) ||
        !$value$plusargs("offset=%d", offset) || !$value$plusargs("stim=%s", stim_name) ||
        !$value$plusargs("out=%s", out_name)) begin
      $display("FAIL: missing plusargs"); $finish;
    end
    fin = $fopen(stim_name, "r");
    n = 0;
    r = $fscanf(fin, "%d\n", v);
    while (r == 1) begin mem[n] = v; n = n + 1; r = $fscanf(fin, "%d\n", v); end
    $fclose(fin);

    repeat (5) @(negedge clk);
    rstn = 1;
    repeat (2) @(negedge clk);
    bus_write(16'h100, gain);
    bus_write(16'h104, shift);
    bus_write(16'h108, offset);

    fout = $fopen(out_name, "w");
    for (i = 0; i < n + 8; i = i + 1) begin
      @(negedge clk);
      dat_i = (i < n) ? mem[i] : 14'sd0;
      #1 $fdisplay(fout, "%0d", dat_o);       // line i = output seen in the cycle input i is applied
    end
    $fclose(fout);
    $finish;
  end
endmodule
