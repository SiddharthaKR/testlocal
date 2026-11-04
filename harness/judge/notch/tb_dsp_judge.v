// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// Generic hidden judge testbench for the Track H easy / medium levels (no bypass).
// The DUT module name is selected by a macro: iverilog -DDUT_MODULE=red_pitaya_gain_block
// Plusargs:
//   +mode=filter +stim=<file> +out=<csv> +n=<N> +regs=<file>   regs file lines: "<addr hex> <value decimal>"
//   +mode=checks +out=<txt> +script=<file>                     script lines: "<op> <addr hex> <value hex>"
//                                op 0 = bus write, op 1 = bus read and expect value
// SETTLE_CYCLES (8) is applied by compare.py on the "cyc" column, not here.
`timescale 1ns/1ps
`ifndef DUT_MODULE
 `define DUT_MODULE red_pitaya_gain_block
`endif
module tb_dsp_judge;

localparam MAXLAT_PAD = 12;   // extra zero samples after stimulus

reg clk = 0, rstn = 0;
reg  signed [13:0] din = 0;
wire signed [13:0] dout;
reg  [15:0] addr = 0;
reg  wen = 0, ren = 0;
reg  [31:0] wdata = 0;
wire ack;
wire [31:0] rdata;

always #4 clk = ~clk;

`DUT_MODULE dut (
   .clk_i(clk), .rstn_i(rstn), .dat_i(din), .dat_o(dout),
   .addr(addr), .wen(wen), .ren(ren), .ack(ack), .rdata(rdata), .wdata(wdata));

integer cyc = -1;   // cycles since rstn released
always @(posedge clk) if (rstn) cyc <= cyc + 1;

task bus_write(input [15:0] a, input [31:0] d);
begin
   @(negedge clk); addr = a; wdata = d; wen = 1;
   @(negedge clk); wen = 0;
end
endtask

task bus_read(input [15:0] a, output [31:0] d);
integer t;
begin
   @(negedge clk); addr = a; ren = 1;
   @(negedge clk); ren = 0;
   d = 32'hDEAD_BEEF;
   for (t = 0; t < 4; t = t + 1) begin
      if (ack === 1'b1) begin d = rdata; t = 4; end
      else @(negedge clk);
   end
end
endtask

integer fo, fs, fr, i, n, rc, nerr, op, k;
integer val;
reg [15:0] ra;
reg [31:0] rv;
reg [8*256-1:0] stimf, outf, mode, regsf, scriptf;
reg [31:0] rd;
integer xs [0:65535];

initial begin
   if (!$value$plusargs("mode=%s", mode)) mode = "filter";
   if (!$value$plusargs("out=%s", outf)) outf = "out.csv";
   if (!$value$plusargs("n=%d", n)) n = 0;
   if (!$value$plusargs("stim=%s", stimf)) stimf = "";
   if (!$value$plusargs("regs=%s", regsf)) regsf = "";
   if (!$value$plusargs("script=%s", scriptf)) scriptf = "";
   fo = $fopen(outf, "w");

   repeat (4) @(posedge clk);
   @(negedge clk) rstn = 1;

   if (mode == "filter") begin
      fs = $fopen(stimf, "r");
      if (fs == 0) begin $display("FATAL cannot open stim"); $finish; end
      for (i = 0; i < n; i = i + 1) rc = $fscanf(fs, "%d\n", xs[i]);
      $fclose(fs);
      fr = $fopen(regsf, "r");
      if (fr == 0) begin $display("FATAL cannot open regs"); $finish; end
      while ($fscanf(fr, "%h %d\n", ra, val) == 2) bus_write(ra, val);
      $fclose(fr);
      repeat (10) @(negedge clk);
      $fwrite(fo, "cyc,n,x,y\n");
      for (i = 0; i < n + MAXLAT_PAD; i = i + 1) begin
         @(negedge clk);
         din = (i < n) ? xs[i] : 0;
         @(posedge clk); #1;
         $fwrite(fo, "%0d,%0d,%0d,%0d\n", cyc, i, din, dout);
      end
   end
   else begin
      // --- X check right after reset settle (dat_i = 0, nothing configured)
      nerr = 0;
      for (i = 0; i < 40; i = i + 1) begin
         @(posedge clk); #1;
         if (cyc >= 8 && ^dout === 1'bx) nerr = nerr + 1;
      end
      $fwrite(fo, "CHECK no_x_after_reset %0s got=%0d exp=0\n", nerr == 0 ? "PASS" : "FAIL", nerr);

      // --- register script
      fr = $fopen(scriptf, "r");
      if (fr == 0) begin $display("FATAL cannot open script"); $finish; end
      k = 0;
      while ($fscanf(fr, "%d %h %h\n", op, ra, rv) == 3) begin
         if (op == 0) bus_write(ra, rv);
         else begin
            bus_read(ra, rd);
            $fwrite(fo, "CHECK rb%0d_0x%0h %0s got=0x%0h exp=0x%0h\n", k, ra, (rd === rv) ? "PASS" : "FAIL", rd, rv);
            k = k + 1;
         end
      end
      $fclose(fr);
   end
   $fclose(fo);
   $finish;
end

// watchdog
initial begin #50_000_000; $display("FATAL timeout"); $finish; end

endmodule
