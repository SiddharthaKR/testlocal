// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// HIDDEN JUDGE TESTBENCH (Track B, EASY). Never copied into the workspace.
// Equivalence: reference red_pitaya_iq_demodulator_block (module prefixed ref_) vs candidate,
// parameters as instantiated by red_pitaya_iq_block (INBITS=14, OUTBITS=24, SINBITS=17, SHIFTBITS=1).
// Both outputs must equal the reference outputs delayed by ONE common lag k in [0, MAX_LAG].
// The module has no reset: outputs are ignored for SETTLE_CYCLES (8) after start.
//
// Plusargs: +seed=<int> +cycles=<int> +out=<file>
// Output file lines:
//   LAG <k> <match> <mismatch> <first_cycle> <exp> <got>     for k = 0..MAX_LAG (exp/got = low 32 bits of {s1,s2})
//   XCOUNT <n>
//   COMPARED <n> EXCLUDED 0 NEGP <n> POSP <n> FS <n>
`timescale 1ns/1ps
module tb_iq_demod_equiv;

localparam MAX_LAG = 8;
localparam SETTLE_CYCLES = 8;
localparam INB = 14, OUTB = 24, SINB = 17;
localparam NS = 3;                       // signals: 0 sin, 1 cos, 2 signal_i

reg clk = 0;
reg signed [SINB-1:0] sin = 0, cos = 0;
reg signed [INB-1:0]  sig = 0;
wire signed [OUTB-1:0] r1, r2, c1, c2;

always #4 clk = ~clk;

ref_red_pitaya_iq_demodulator_block #(.INBITS(INB), .OUTBITS(OUTB), .SINBITS(SINB), .SHIFTBITS(1))
   R (.clk_i(clk), .sin(sin), .cos(cos), .signal_i(sig), .signal1_o(r1), .signal2_o(r2));
red_pitaya_iq_demodulator_block #(.INBITS(INB), .OUTBITS(OUTB), .SINBITS(SINB), .SHIFTBITS(1))
   C (.clk_i(clk), .sin(sin), .cos(cos), .signal_i(sig), .signal1_o(c1), .signal2_o(c2));

integer seed, ncyc, fo, cyc = -1;
reg [8*256-1:0] outf;

reg [2*OUTB-1:0] hist [0:MAX_LAG];
integer match [0:MAX_LAG], mism [0:MAX_LAG], first_c [0:MAX_LAG], first_e [0:MAX_LAG], first_g [0:MAX_LAG];
integer k, xcount = 0, compared = 0, negp = 0, posp = 0, fs = 0;
reg [2*OUTB-1:0] cv;

initial for (k = 0; k <= MAX_LAG; k = k + 1) begin
   match[k] = 0; mism[k] = 0; first_c[k] = -1; first_e[k] = 0; first_g[k] = 0; hist[k] = 0;
end

always @(posedge clk) begin
   #1;
   cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = {r1, r2};
   cv = {c1, c2};
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
      if (r1 < 0) negp = negp + 1;
      if (r2 > 0) posp = posp + 1;
      if (sig == -14'sd8192 || sig == 14'sd8191) fs = fs + 1;
   end
end

// ---- stimulus helpers ----
function integer urange(input integer lo, input integer hi);
   urange = lo + ({$random(seed)} % (hi - lo + 1));
endfunction

function integer rs(input integer w);          // uniform signed random of w bits
   integer r;
   begin r = $random(seed); rs = r >>> (32 - w); end
endfunction

function integer ext(input integer W, input integer sel);   // full-scale / corner values of a W-bit signed port
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

integer pw [0:NS-1];       // port widths
integer smode [0:NS-1], swid [0:NS-1], shold [0:NS-1], sval [0:NS-1];
integer s, i, seglen;

task step_sig(input integer n);
begin
   case (smode[n])
      0: sval[n] = rs(swid[n]);                                          // new random value every cycle
      1: begin if (shold[n] <= 0) begin sval[n] = rs(swid[n]); shold[n] = urange(2, 300); end   // held random
               shold[n] = shold[n] - 1; end
      2: sval[n] = ext(pw[n], urange(0, 6));                              // corner values every cycle
      default: begin if (shold[n] <= 0) begin sval[n] = ext(pw[n], urange(0, 6)); shold[n] = urange(2, 300); end
               shold[n] = shold[n] - 1; end                               // held corner value
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
   pw[0] = SINB; pw[1] = SINB; pw[2] = INB;
   for (s = 0; s < NS; s = s + 1) begin smode[s] = 0; swid[s] = pw[s]; shold[s] = 0; sval[s] = 0; end

   while (cyc < ncyc) begin
      new_segment;
      seglen = urange(50, 1500);
      for (i = 0; i < seglen && cyc < ncyc; i = i + 1) begin
         @(negedge clk);
         for (s = 0; s < NS; s = s + 1) step_sig(s);
         sin = sval[0]; cos = sval[1]; sig = sval[2];
      end
   end

   for (k = 0; k <= MAX_LAG; k = k + 1)
      $fwrite(fo, "LAG %0d %0d %0d %0d %0d %0d\n", k, match[k], mism[k], first_c[k], first_e[k], first_g[k]);
   $fwrite(fo, "XCOUNT %0d\n", xcount);
   $fwrite(fo, "COMPARED %0d EXCLUDED 0 NEGP %0d POSP %0d FS %0d\n", compared, negp, posp, fs);
   $fclose(fo);
   $finish;
end

endmodule
