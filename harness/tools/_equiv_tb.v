// Mini equivalence testbench for run_equiv.sh (agent-visible, small).
// Reference = tasks/B/ref (modules prefixed ref_), candidate = red_pitaya_pid_block.
// A few fixed configurations, random input; reports the best output lag.
`timescale 1ns/1ps
module tb_equiv_mini;
localparam MAX_LAG = 8;
reg clk = 0, rstn = 0, sync = 1;
reg  signed [13:0] din = 0;
reg  [15:0] addr = 0; reg wen = 0, ren = 0; reg [31:0] wdata = 0;
wire signed [13:0] r_out, c_out, r_d, c_d; wire r_ack, c_ack; wire [31:0] r_rd, c_rd;
always #4 clk = ~clk;

ref_red_pitaya_pid_block R (.clk_i(clk), .rstn_i(rstn), .sync_i(sync), .dat_i(din), .dat_o(r_out),
   .diff_dat_i(14'd0), .diff_dat_o(r_d), .addr(addr), .wen(wen), .ren(ren), .ack(r_ack), .rdata(r_rd), .wdata(wdata));
red_pitaya_pid_block C (.clk_i(clk), .rstn_i(rstn), .sync_i(sync), .dat_i(din), .dat_o(c_out),
   .diff_dat_i(14'd0), .diff_dat_o(c_d), .addr(addr), .wen(wen), .ren(ren), .ack(c_ack), .rdata(c_rd), .wdata(wdata));

integer seed = 7, cyc = 0, last_wr = 0, k, cfg, i, nrb = 0;
reg signed [13:0] hist [0:MAX_LAG];
integer ok [0:MAX_LAG], firstbad [0:MAX_LAG], fexp [0:MAX_LAG], fgot [0:MAX_LAG];
integer compared = 0;
initial for (k = 0; k <= MAX_LAG; k = k + 1) begin ok[k] = 0; firstbad[k] = -1; hist[k] = 0; end

always @(posedge clk) if (rstn) begin
   #1 cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = r_out;
   if (cyc > 20 && cyc - last_wr > MAX_LAG + 2) begin
      compared = compared + 1;
      for (k = 0; k <= MAX_LAG; k = k + 1)
         if (c_out === hist[k]) ok[k] = ok[k] + 1;
         else if (firstbad[k] < 0) begin firstbad[k] = cyc; fexp[k] = hist[k]; fgot[k] = c_out; end
   end
end

task wr(input [15:0] a, input [31:0] d);
begin @(negedge clk) addr = a; wdata = d; wen = 1; @(negedge clk) wen = 0; last_wr = cyc; end
endtask
task rb(input [15:0] a);
begin @(negedge clk) addr = a; ren = 1; @(negedge clk) ren = 0;
   if (r_rd !== c_rd) begin nrb = nrb + 1; $display("READBACK MISMATCH addr %h: ref %h cand %h", a, r_rd, c_rd); end
end
endtask

integer best;
initial begin
   repeat (3) @(posedge clk); @(negedge clk) rstn = 1;
   for (cfg = 0; cfg < 4; cfg = cfg + 1) begin
      wr(16'h104, cfg * 500);                 // setpoint
      wr(16'h108, 32'h1000 << cfg);           // kp
      wr(16'h10C, (cfg == 2) ? 32'h4000 : 0); // ki
      wr(16'h124, (cfg == 3) ? -2000 : -8192); wr(16'h128, (cfg == 3) ? 3000 : 8191);
      wr(16'h12C, 0);
      wr(16'h100, 0);
      rb(16'h104); rb(16'h108); rb(16'h10C); rb(16'h124); rb(16'h128);
      for (i = 0; i < 1000; i = i + 1) begin
         @(negedge clk) din = $random(seed) >>> 3;
         if (i == 500) sync = 0; if (i == 600) sync = 1;
      end
   end
   best = 0;
   for (k = 0; k <= MAX_LAG; k = k + 1) if (ok[k] > ok[best]) best = k;
   if (ok[best] == compared && nrb == 0)
      $display("EQUIV PASS: candidate = reference delayed by %0d cycles (%0d cycles compared)", best, compared);
   else begin
      $display("EQUIV FAIL: best lag %0d matches %0d/%0d cycles, %0d readback mismatches", best, ok[best], compared, nrb);
      if (firstbad[best] >= 0)
         $display("  first mismatch at cycle %0d: reference %0d, candidate %0d", firstbad[best], fexp[best], fgot[best]);
   end
   $finish;
end
endmodule
