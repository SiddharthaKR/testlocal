// Mini equivalence testbench for run_equiv.sh (agent-visible, small): IQ modulator.
// Reference = tasks/B/ref (modules prefixed ref_), candidate = red_pitaya_iq_modulator_block.
// Parameters as used by red_pitaya_iq_block. dat_o, signal_q1_o and signal_q2_o must all equal
// the reference delayed by the same number of cycles (0..8).
`timescale 1ns/1ps
module tb_equiv_mini_mod;
localparam MAX_LAG = 8;
reg clk = 0;
reg signed [16:0] sin = 0, cos = 0;
reg signed [17:0] g1 = 0, g2 = 0, g3 = 0, g4 = 0;
reg signed [23:0] s1 = 0, s2 = 0;
wire signed [13:0] r_d, r_q1, r_q2, c_d, c_q1, c_q2;
always #4 clk = ~clk;

ref_red_pitaya_iq_modulator_block #(.INBITS(24), .OUTBITS(14), .SINBITS(17), .GAINBITS(18), .SHIFTBITS(8))
   R (.clk_i(clk), .sin(sin), .cos(cos), .g1(g1), .g2(g2), .g3(g3), .g4(g4), .signal1_i(s1), .signal2_i(s2),
      .dat_o(r_d), .signal_q1_o(r_q1), .signal_q2_o(r_q2));
red_pitaya_iq_modulator_block #(.INBITS(24), .OUTBITS(14), .SINBITS(17), .GAINBITS(18), .SHIFTBITS(8))
   C (.clk_i(clk), .sin(sin), .cos(cos), .g1(g1), .g2(g2), .g3(g3), .g4(g4), .signal1_i(s1), .signal2_i(s2),
      .dat_o(c_d), .signal_q1_o(c_q1), .signal_q2_o(c_q2));

integer seed = 13, cyc = 0, k, i, ph, compared = 0, best;
reg [41:0] hist [0:MAX_LAG];
integer ok [0:MAX_LAG], firstbad [0:MAX_LAG];
initial for (k = 0; k <= MAX_LAG; k = k + 1) begin ok[k] = 0; firstbad[k] = -1; hist[k] = 0; end

always @(posedge clk) begin
   #1 cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = {r_d, r_q1, r_q2};
   if (cyc > 20) begin
      compared = compared + 1;
      for (k = 0; k <= MAX_LAG; k = k + 1)
         if ({c_d, c_q1, c_q2} === hist[k]) ok[k] = ok[k] + 1;
         else if (firstbad[k] < 0) firstbad[k] = cyc;
   end
end

initial begin
   for (ph = 0; ph < 4; ph = ph + 1)
      for (i = 0; i < 1000; i = i + 1) begin
         @(negedge clk);
         sin = $random(seed) >>> 15; cos = $random(seed) >>> 15;
         case (ph)
            0: begin g1 = $random(seed) >>> 22; g2 = $random(seed) >>> 22; g3 = $random(seed) >>> 22; g4 = $random(seed) >>> 22;
                     s1 = $random(seed) >>> 14; s2 = $random(seed) >>> 14; end         // small gains, no saturation expected
            1: begin g1 = 18'sd131071; g2 = -18'sd131072; g3 = 18'sd131071; g4 = -18'sd131072;
                     s1 = $random(seed) >>> 8; s2 = $random(seed) >>> 8; end          // full-scale gains: saturation
            2: begin g1 = $random(seed) >>> 14; g2 = $random(seed) >>> 14; g3 = $random(seed) >>> 14; g4 = $random(seed) >>> 14;
                     s1 = $random(seed) >>> 8; s2 = $random(seed) >>> 8; end          // random gains and signals
            default: begin g1 = 18'sd256; g2 = 18'sd0; g3 = 18'sd256; g4 = 18'sd256;
                     s1 = $random(seed) >>> 12; s2 = $random(seed) >>> 12; end        // unity-ish gain (binary point 8)
         endcase
      end
   best = 0;
   for (k = 0; k <= MAX_LAG; k = k + 1) if (ok[k] > ok[best]) best = k;
   if (ok[best] == compared)
      $display("EQUIV PASS: candidate = reference delayed by %0d cycles (%0d cycles compared)", best, compared);
   else begin
      $display("EQUIV FAIL: best lag %0d matches %0d/%0d cycles", best, ok[best], compared);
      if (firstbad[best] >= 0) $display("  first mismatch at cycle %0d (outputs differ from reference delayed by %0d)", firstbad[best], best);
   end
   $finish;
end
endmodule
