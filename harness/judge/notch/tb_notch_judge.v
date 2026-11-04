// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// Hidden judge testbench for red_pitaya_notch_block.
// Plusargs:
//   +mode=filter +stim=<file> +out=<csv> +n=<N> +b0=.. +b1=.. +b2=.. +a1=.. +a2=..
//   +mode=checks +out=<txt> [+stim=<file> +n=<N>]   (register / bypass / X checks)
// SETTLE_CYCLES (8) is applied by compare.py on the "cyc" column, not here.
`timescale 1ns/1ps
module tb_notch_judge;

localparam MAXLAT_PAD = 8;   // extra zero samples after stimulus

reg clk = 0, rstn = 0;
reg  signed [13:0] din = 0;
wire signed [13:0] dout;
reg  [15:0] addr = 0;
reg  wen = 0, ren = 0;
reg  [31:0] wdata = 0;
wire ack;
wire [31:0] rdata;

always #4 clk = ~clk;

red_pitaya_notch_block dut (
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

integer fo, fs, i, n, rc, v, ok, nerr;
integer b0, b1, b2, a1, a2;
reg [8*256-1:0] stimf, outf, mode;
reg [31:0] rd;
integer xs [0:65535];

task load_stim;
begin
   fs = $fopen(stimf, "r");
   if (fs == 0) begin $display("FATAL cannot open stim"); $finish; end
   for (i = 0; i < n; i = i + 1) rc = $fscanf(fs, "%d\n", xs[i]);
   $fclose(fs);
end
endtask

task check(input [8*32-1:0] name, input integer pass, input integer got, input integer exp);
begin
   $fwrite(fo, "CHECK %0s %0s got=%0d exp=%0d\n", name, pass ? "PASS" : "FAIL", got, exp);
end
endtask

initial begin
   if (!$value$plusargs("mode=%s", mode)) mode = "filter";
   if (!$value$plusargs("out=%s", outf)) outf = "out.csv";
   if (!$value$plusargs("n=%d", n)) n = 0;
   if (!$value$plusargs("stim=%s", stimf)) stimf = "";
   fo = $fopen(outf, "w");

   repeat (4) @(posedge clk);
   @(negedge clk) rstn = 1;

   if (mode == "filter") begin
      rc = $value$plusargs("b0=%d", b0); rc = $value$plusargs("b1=%d", b1);
      rc = $value$plusargs("b2=%d", b2); rc = $value$plusargs("a1=%d", a1);
      rc = $value$plusargs("a2=%d", a2);
      load_stim;
      bus_write(16'h114, 0);
      bus_write(16'h100, b0); bus_write(16'h104, b1); bus_write(16'h108, b2);
      bus_write(16'h10C, a1); bus_write(16'h110, a2);
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
      check("no_x_after_reset", nerr == 0, nerr, 0);

      // --- reset values (spec: all coefficients and bypass are 0 after reset), read before any write
      bus_read(16'h100, rd); check("reset_b0", rd === 32'h0, rd, 0);
      bus_read(16'h104, rd); check("reset_b1", rd === 32'h0, rd, 0);
      bus_read(16'h108, rd); check("reset_b2", rd === 32'h0, rd, 0);
      bus_read(16'h10C, rd); check("reset_a1", rd === 32'h0, rd, 0);
      bus_read(16'h110, rd); check("reset_a2", rd === 32'h0, rd, 0);
      bus_read(16'h114, rd); check("reset_bypass", rd === 32'h0, rd, 0);

      // --- register readback: negative and positive 18-bit values, sign-extended
      ok = 1;
      bus_write(16'h100, 32'h0002_0001); bus_read(16'h100, rd); check("rb_b0", rd === 32'hFFFE_0001, rd, 32'hFFFE_0001);
      bus_write(16'h104, 32'h7FFE_1234); bus_read(16'h104, rd); check("rb_b1", rd === 32'hFFFE_1234, rd, 32'hFFFE_1234);
      bus_write(16'h108, 32'h0001_FFFF); bus_read(16'h108, rd); check("rb_b2", rd === 32'h0001_FFFF, rd, 32'h0001_FFFF);
      bus_write(16'h10C, 32'h0003_0000); bus_read(16'h10C, rd); check("rb_a1", rd === 32'hFFFF_0000, rd, 32'hFFFF_0000);
      bus_write(16'h110, 32'h0000_ABCD); bus_read(16'h110, rd); check("rb_a2", rd === 32'h0000_ABCD, rd, 32'h0000_ABCD);
      bus_write(16'h114, 32'h0000_0001); bus_read(16'h114, rd); check("rb_bypass", rd[0] === 1'b1, rd, 1);
      bus_read(16'h200, rd); check("rb_coef_frac", rd === 32'd16, rd, 16);

      // --- bypass: dat_o must equal dat_i at one fixed latency in [0,4]
      if (stimf != "" && n > 0) begin
         load_stim;
         $fwrite(fo, "BYPASS_CSV_BEGIN\ncyc,n,x,y\n");
         for (i = 0; i < n + MAXLAT_PAD; i = i + 1) begin
            @(negedge clk);
            din = (i < n) ? xs[i] : 0;
            @(posedge clk); #1;
            $fwrite(fo, "%0d,%0d,%0d,%0d\n", cyc, i, din, dout);
         end
         $fwrite(fo, "BYPASS_CSV_END\n");
      end
   end
   $fclose(fo);
   $finish;
end

// watchdog
initial begin #50_000_000; $display("FATAL timeout"); $finish; end

endmodule
