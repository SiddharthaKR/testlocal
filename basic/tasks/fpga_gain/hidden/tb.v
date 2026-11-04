// Hidden testbench: configures the DUT over the bus, streams a stimulus file (one integer
// per line) one sample per clock, and writes dat_o once per clock (one integer per line).
// Plusargs: +gain= +shift= +offset= +stim=<file> +out=<file>
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

  task bus_write(input [15:0] a, input [31:0] d);
    begin
      @(negedge clk); addr = a; wdata = d; wen = 1;
      @(negedge clk); wen = 0;
      @(negedge clk);                         // ack is visible here
    end
  endtask

  initial begin
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
