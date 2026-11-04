// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// HIDDEN JUDGE TESTBENCH (Track B, MEDIUM). Never copied into the workspace.
// Equivalence: reference red_pitaya_iq_modulator_block (+ product_sat, saturate; modules prefixed ref_)
// vs candidate, parameters as instantiated by red_pitaya_iq_block
// (INBITS=24, OUTBITS=14, SINBITS=17, GAINBITS=18, SHIFTBITS=8).
// dat_o, signal_q1_o and signal_q2_o must ALL equal the reference outputs delayed by ONE common lag k in
// [0, MAX_LAG] (the reference's own outputs have different latencies; the lag is applied to each equally).
// The module has no reset: outputs are ignored for SETTLE_CYCLES (8) after start.
//
// Plusargs: +seed=<int> +cycles=<int> +out=<file>
// Output file lines:
//   LAG <k> <match> <mismatch> <first_cycle> <exp> <got>     (exp/got = low 32 bits of {dat,q1,q2})
//   XCOUNT <n>
//   COMPARED <n> EXCLUDED 0 SAT_HI <n> SAT_LO <n> FSAT <n> Q1SAT <n> Q2SAT <n>
`timescale 1ns/1ps
module tb_iq_mod_equiv;

localparam MAX_LAG = 8;
localparam SETTLE_CYCLES = 8;
localparam INB = 24, OUTB = 14, SINB = 17, GB = 18, SHB = 8;
localparam NS = 8;       // 0 sin, 1 cos, 2..5 g1..g4, 6 signal1_i, 7 signal2_i

reg clk = 0;
reg signed [SINB-1:0] sin = 0, cos = 0;
reg signed [GB-1:0] g1 = 0, g2 = 0, g3 = 0, g4 = 0;
reg signed [INB-1:0] s1 = 0, s2 = 0;
wire signed [OUTB-1:0] r_d, r_q1, r_q2, c_d, c_q1, c_q2;

always #4 clk = ~clk;

ref_red_pitaya_iq_modulator_block #(.INBITS(INB), .OUTBITS(OUTB), .SINBITS(SINB), .GAINBITS(GB), .SHIFTBITS(SHB))
   R (.clk_i(clk), .sin(sin), .cos(cos), .g1(g1), .g2(g2), .g3(g3), .g4(g4), .signal1_i(s1), .signal2_i(s2),
      .dat_o(r_d), .signal_q1_o(r_q1), .signal_q2_o(r_q2));
red_pitaya_iq_modulator_block #(.INBITS(INB), .OUTBITS(OUTB), .SINBITS(SINB), .GAINBITS(GB), .SHIFTBITS(SHB))
   C (.clk_i(clk), .sin(sin), .cos(cos), .g1(g1), .g2(g2), .g3(g3), .g4(g4), .signal1_i(s1), .signal2_i(s2),
      .dat_o(c_d), .signal_q1_o(c_q1), .signal_q2_o(c_q2));

integer seed, ncyc, fo, cyc = -1;
reg [8*256-1:0] outf;

reg [3*OUTB-1:0] hist [0:MAX_LAG];
integer match [0:MAX_LAG], mism [0:MAX_LAG], first_c [0:MAX_LAG], first_e [0:MAX_LAG], first_g [0:MAX_LAG];
integer k, xcount = 0, compared = 0, sat_hi = 0, sat_lo = 0, fsat = 0, q1sat = 0, q2sat = 0;
reg [3*OUTB-1:0] cv;

initial for (k = 0; k <= MAX_LAG; k = k + 1) begin
   match[k] = 0; mism[k] = 0; first_c[k] = -1; first_e[k] = 0; first_g[k] = 0; hist[k] = 0;
end

always @(posedge clk) begin
   #1;
   cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = {r_d, r_q1, r_q2};
   cv = {c_d, c_q1, c_q2};
   if (cyc >= SETTLE_CYCLES + MAX_LAG) begin
      compared = compared + 1;
      if (^cv === 1'bx) xcount = xcount + 1;
      for (k = 0; k <= MAX_LAG; k = k + 1) begin
         if (cv === hist[k]) match[k] = match[k] + 1;
         else begin
            if (mism[k] == 0) begin first_c[k] = cyc; first_e[k] = hist[k]; first_g[k] = cv; end
            mism[k] = mism[k] + 1;
         end
      end
      // coverage counters (reference behaviour)
      if (r_d == 14'sh1FFF) sat_hi = sat_hi + 1;
      if (r_d == 14'sh2000) sat_lo = sat_lo + 1;
      if (R.firstproduct1 == 14'sh1FFF || R.firstproduct1 == 14'sh2000 ||
          R.firstproduct2 == 14'sh1FFF || R.firstproduct2 == 14'sh2000) fsat = fsat + 1;
      if (r_q1 == 14'sh1FFF || r_q1 == 14'sh2000) q1sat = q1sat + 1;
      if (r_q2 == 14'sh1FFF || r_q2 == 14'sh2000) q2sat = q2sat + 1;
   end
end

// ---- stimulus helpers ----
function integer urange(input integer lo, input integer hi);
   urange = lo + ({$random(seed)} % (hi - lo + 1));
endfunction

function integer rs(input integer w);
   integer r;
   begin r = $random(seed); rs = r >>> (32 - w); end
endfunction

function integer ext(input integer W, input integer sel);
   case (sel)
      0: ext = (1 << (W-1)) - 1;
      1: ext = -(1 << (W-1));
      2: ext = 0;
      3: ext = 1;
      4: ext = -1;
      5: ext = (1 << (W-1)) - 2;
      default: ext = -(1 << (W-1)) + 1;
   endcase
endfunction

integer pw [0:NS-1];
integer smode [0:NS-1], swid [0:NS-1], shold [0:NS-1], sval [0:NS-1];
integer s, i, seglen;

task step_sig(input integer n);
begin
   case (smode[n])
      0: sval[n] = rs(swid[n]);
      1: begin if (shold[n] <= 0) begin sval[n] = rs(swid[n]); shold[n] = urange(2, 300); end
               shold[n] = shold[n] - 1; end
      2: sval[n] = ext(pw[n], urange(0, 6));
      default: begin if (shold[n] <= 0) begin sval[n] = ext(pw[n], urange(0, 6)); shold[n] = urange(2, 300); end
               shold[n] = shold[n] - 1; end
   endcase
end
endtask

task new_segment;
begin
   for (s = 0; s < NS; s = s + 1) begin
      i = urange(0, 99);
      smode[s] = (i < 35) ? 0 : (i < 65) ? 1 : (i < 80) ? 2 : 3;
      swid[s] = (urange(0, 1) == 0) ? pw[s] : urange(1, pw[s]);
      shold[s] = 0;
   end
end
endtask

initial begin
   if (!$value$plusargs("seed=%d", seed)) seed = 1;
   if (!$value$plusargs("cycles=%d", ncyc)) ncyc = 5000;
   if (!$value$plusargs("out=%s", outf)) outf = "equiv.txt";
   fo = $fopen(outf, "w");
   pw[0] = SINB; pw[1] = SINB;
   for (s = 2; s < 6; s = s + 1) pw[s] = GB;
   pw[6] = INB; pw[7] = INB;
   for (s = 0; s < NS; s = s + 1) begin smode[s] = 0; swid[s] = pw[s]; shold[s] = 0; sval[s] = 0; end

   while (cyc < ncyc) begin
      new_segment;
      seglen = urange(50, 1500);
      for (i = 0; i < seglen && cyc < ncyc; i = i + 1) begin
         @(negedge clk);
         for (s = 0; s < NS; s = s + 1) step_sig(s);
         sin = sval[0]; cos = sval[1]; g1 = sval[2]; g2 = sval[3]; g3 = sval[4]; g4 = sval[5];
         s1 = sval[6]; s2 = sval[7];
      end
   end

   for (k = 0; k <= MAX_LAG; k = k + 1)
      $fwrite(fo, "LAG %0d %0d %0d %0d %0d %0d\n", k, match[k], mism[k], first_c[k], first_e[k], first_g[k]);
   $fwrite(fo, "XCOUNT %0d\n", xcount);
   $fwrite(fo, "COMPARED %0d EXCLUDED 0 SAT_HI %0d SAT_LO %0d FSAT %0d Q1SAT %0d Q2SAT %0d\n",
           compared, sat_hi, sat_lo, fsat, q1sat, q2sat);
   $fclose(fo);
   $finish;
end

endmodule
