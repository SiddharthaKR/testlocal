// Mini equivalence testbench for run_equiv.sh (agent-visible, small): IQ demodulator.
// Reference = tasks/B/ref (modules prefixed ref_), candidate = red_pitaya_iq_demodulator_block.
// Parameters as used by red_pitaya_iq_block. Reports the best common output lag.
`timescale 1ns/1ps
module tb_equiv_mini_demod;
localparam MAX_LAG = 8;
reg clk = 0;
reg signed [16:0] sin = 0, cos = 0;
reg signed [13:0] sig = 0;
wire signed [23:0] r1, r2, c1, c2;
always #4 clk = ~clk;

ref_red_pitaya_iq_demodulator_block #(.INBITS(14), .OUTBITS(24), .SINBITS(17), .SHIFTBITS(1))
   R (.clk_i(clk), .sin(sin), .cos(cos), .signal_i(sig), .signal1_o(r1), .signal2_o(r2));
red_pitaya_iq_demodulator_block #(.INBITS(14), .OUTBITS(24), .SINBITS(17), .SHIFTBITS(1))
   C (.clk_i(clk), .sin(sin), .cos(cos), .signal_i(sig), .signal1_o(c1), .signal2_o(c2));

integer seed = 11, cyc = 0, k, i, ph, compared = 0, best;
reg [47:0] hist [0:MAX_LAG];
integer ok [0:MAX_LAG], firstbad [0:MAX_LAG];
initial for (k = 0; k <= MAX_LAG; k = k + 1) begin ok[k] = 0; firstbad[k] = -1; hist[k] = 0; end

always @(posedge clk) begin
   #1 cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = {r1, r2};
   if (cyc > 20) begin
      compared = compared + 1;
      for (k = 0; k <= MAX_LAG; k = k + 1)
         if ({c1, c2} === hist[k]) ok[k] = ok[k] + 1;
         else if (firstbad[k] < 0) firstbad[k] = cyc;
   end
end

initial begin
   for (ph = 0; ph < 4; ph = ph + 1)
      for (i = 0; i < 1000; i = i + 1) begin
         @(negedge clk);
         case (ph)
            0: begin sin = $random(seed) >>> 15; cos = $random(seed) >>> 15; sig = $random(seed) >>> 18; end  // full range
            1: begin sin = 17'sd65535; cos = -17'sd65535; sig = $random(seed) >>> 18; end                    // full-scale constants
            2: begin sin = (i % 2) ? 17'sd65535 : -17'sd65536; cos = 17'sd1; sig = (i % 3) ? 14'sd8191 : -14'sd8192; end
            default: begin sin = $random(seed) >>> 25; cos = $random(seed) >>> 25; sig = $random(seed) >>> 25; end // small
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
