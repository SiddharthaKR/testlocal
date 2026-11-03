// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// HIDDEN JUDGE TESTBENCH (Track B). Never copied into the workspace.
// Equivalence: reference PID (modules prefixed ref_) vs candidate red_pitaya_pid_block,
// same inputs and same bus, randomized segments with saturation episodes.
//
// Plusargs: +seed=<int> +cycles=<int> +out=<file>
// Output file lines:
//   LAG <k> <match> <mismatch> <first_cycle> <exp> <got>     for k = 0..MAX_LAG
//   XCOUNT <n>                    candidate X/Z samples in compared cycles
//   RB <addr> <ref> <cand> <PASS|FAIL>   first mismatch per address, then summary
//   RBSUM <reads> <mismatches>
//   COMPARED <n> EXCLUDED <n> SAT_HI <n> SAT_LO <n> ISAT <n> ARBSAT <n>
//
// Rules: samples are compared only after SETTLE_CYCLES (8) after reset, and
// not within EXCL cycles after a bus write (register changes may take effect
// at a different sample when the pipeline depth changes).
`timescale 1ns/1ps
module tb_pid_equiv;

localparam MAX_LAG = 8;
localparam SETTLE_CYCLES = 8;
localparam EXCL = MAX_LAG + 2;

reg clk = 0, rstn = 0, sync = 1;
reg  signed [13:0] din = 0, ddin = 0;
reg  [15:0] addr = 0;
reg  wen = 0, ren = 0;
reg  [31:0] wdata = 0;
wire signed [13:0] r_out, c_out, r_dout, c_dout;
wire r_ack, c_ack;
wire [31:0] r_rdata, c_rdata;

always #4 clk = ~clk;

ref_red_pitaya_pid_block R (.clk_i(clk), .rstn_i(rstn), .sync_i(sync), .dat_i(din), .dat_o(r_out),
   .diff_dat_i(ddin), .diff_dat_o(r_dout), .addr(addr), .wen(wen), .ren(ren),
   .ack(r_ack), .rdata(r_rdata), .wdata(wdata));
red_pitaya_pid_block C (.clk_i(clk), .rstn_i(rstn), .sync_i(sync), .dat_i(din), .dat_o(c_out),
   .diff_dat_i(ddin), .diff_dat_o(c_dout), .addr(addr), .wen(wen), .ren(ren),
   .ack(c_ack), .rdata(c_rdata), .wdata(wdata));

integer seed, ncyc, fo, cyc = -1, last_wr = -1000;
reg [8*256-1:0] outf;

// ---- output comparison with lag search ----
reg signed [13:0] hist [0:MAX_LAG];
integer match [0:MAX_LAG], mism [0:MAX_LAG], first_c [0:MAX_LAG], first_e [0:MAX_LAG], first_g [0:MAX_LAG];
integer k, xcount = 0, compared = 0, excluded = 0;
integer sat_hi = 0, sat_lo = 0, isat = 0, arbsat = 0;

initial for (k = 0; k <= MAX_LAG; k = k + 1) begin
   match[k] = 0; mism[k] = 0; first_c[k] = -1; first_e[k] = 0; first_g[k] = 0; hist[k] = 0;
end

always @(posedge clk) if (rstn) begin
   #1;
   cyc = cyc + 1;
   for (k = MAX_LAG; k > 0; k = k - 1) hist[k] = hist[k-1];
   hist[0] = r_out;
   if (cyc >= SETTLE_CYCLES + MAX_LAG) begin
      if (cyc - last_wr <= EXCL) excluded = excluded + 1;
      else begin
         compared = compared + 1;
         if (^c_out === 1'bx) xcount = xcount + 1;
         for (k = 0; k <= MAX_LAG; k = k + 1) begin
            if (c_out === hist[k]) match[k] = match[k] + 1;
            else begin
               if (mism[k] == 0) begin first_c[k] = cyc; first_e[k] = hist[k]; first_g[k] = c_out; end
               mism[k] = mism[k] + 1;
            end
         end
         // coverage counters (reference behaviour)
         if (R.pid_out == 14'h1FFF) sat_hi = sat_hi + 1;
         if (R.pid_out == 14'h2000) sat_lo = sat_lo + 1;
         if (R.int_reg == {1'b0,{47{1'b1}}} || R.int_reg == {1'b1,{47{1'b0}}}) isat = isat + 1;
         if (r_out !== R.pid_out) arbsat = arbsat + 1;
      end
   end
end

// ---- bus ----
integer rb_reads = 0, rb_bad = 0;
task bus_write(input [15:0] a, input [31:0] d);
begin
   @(negedge clk); addr = a; wdata = d; wen = 1;
   @(negedge clk); wen = 0; last_wr = cyc;
end
endtask

// read both DUTs at once; registers whose value is static must match exactly
task bus_read_cmp(input [15:0] a);
begin
   @(negedge clk); addr = a; ren = 1;
   @(negedge clk); ren = 0;
   rb_reads = rb_reads + 1;
   if (r_ack !== c_ack || r_rdata !== c_rdata) begin
      if (rb_bad < 20) $fwrite(fo, "RB %h %h %h FAIL ack=%b/%b\n", a, r_rdata, c_rdata, r_ack, c_ack);
      rb_bad = rb_bad + 1;
   end
end
endtask

function [31:0] rnd(input integer bits);   // uniform random of 'bits' bits
   rnd = $random(seed) & ((bits >= 32) ? 32'hFFFF_FFFF : ((32'd1 << bits) - 1));
endfunction

function signed [13:0] srnd14(input integer shift);   // signed full-scale >>> shift
   reg signed [13:0] v;
   begin v = $random(seed); srnd14 = v >>> shift; end
endfunction

reg signed [15:0] plant;   // closed-loop plant state (first-order low-pass of -dat_o)

function integer urange(input integer lo, input integer hi);
   urange = lo + ({$random(seed)} % (hi - lo + 1));
endfunction

// static, readable registers (0x100 = integrator state, excluded)
reg [15:0] rb_addrs [0:14];
initial begin
   rb_addrs[0]=16'h104; rb_addrs[1]=16'h108; rb_addrs[2]=16'h10C; rb_addrs[3]=16'h110;
   rb_addrs[4]=16'h120; rb_addrs[5]=16'h124; rb_addrs[6]=16'h128; rb_addrs[7]=16'h12C;
   rb_addrs[8]=16'h200; rb_addrs[9]=16'h204; rb_addrs[10]=16'h208; rb_addrs[11]=16'h20C;
   rb_addrs[12]=16'h220; rb_addrs[13]=16'h224; rb_addrs[14]=16'h228;
end

// ---- stimulus ----
integer seg, seglen, i, mode, sat_ep, isat_ep, j;
integer lo, hi, tmp, amp;
reg signed [31:0] walk;

initial begin
   if (!$value$plusargs("seed=%d", seed)) seed = 1;
   if (!$value$plusargs("cycles=%d", ncyc)) ncyc = 5000;
   if (!$value$plusargs("out=%s", outf)) outf = "equiv.txt";
   fo = $fopen(outf, "w");

   repeat (4) @(posedge clk);
   @(negedge clk) rstn = 1;
   walk = 0;

   while (cyc < ncyc) begin
      // ---- new segment: randomize configuration ----
      sat_ep = (urange(0, 4) == 0);          // ~20%: forced saturation episode
      isat_ep = sat_ep && urange(0, 1);      // half of them: integrator-only (kp = 0) so I saturation reaches dat_o
      bus_write(16'h104, sat_ep ? (urange(0, 1) ? 14'sd8191 : -14'sd8192) : srnd14(urange(0, 3)));                // setpoint
      bus_write(16'h108, isat_ep ? 0 : sat_ep ? (32'h40_0000 | rnd(22)) : rnd(urange(6, 13)));  // kp (PSR=12: gain < 2 normally)
      bus_write(16'h10C, sat_ep ? (32'h7F_0000 | rnd(16)) : (urange(0, 1) ? 0 : rnd(urange(0, 21))));    // ki (ISR=32)
      bus_write(16'h110, rnd(24));                                   // kd (DERIVATIVE=0)
      bus_write(16'h120, urange(0, 1) ? 32'h0 : rnd(32));            // filter
      if (!isat_ep && urange(0, 9) < 3) begin                        // arbitrary saturation (30%)
         lo = urange(-8192, 8191); hi = urange(-8192, 8191);
         if (urange(0, 4) != 0 && lo > hi) begin tmp = lo; lo = hi; hi = tmp; end
         bus_write(16'h124, lo); bus_write(16'h128, hi);
      end else begin
         bus_write(16'h124, 32'h2000); bus_write(16'h128, 32'h1FFF);
      end
      bus_write(16'h12C, sat_ep ? 0 : rnd(4));                                    // diff mode + pause bits
      bus_write(16'h100, (urange(0, 9) == 0) ? rnd(16) : srnd14(urange(2, 6)));  // ival: mostly small, sometimes full range
      for (j = 0; j < 15; j = j + 1) bus_read_cmp(rb_addrs[j]);

      mode = sat_ep ? urange(2, 3) : urange(0, 7);   // 4..7: closed loop; sat episodes use DC-heavy inputs
      amp = sat_ep ? 0 : urange(1, 5);
      seglen = sat_ep ? urange(3000, 6000) : urange(300, 2500);
      plant = 0;
      for (i = 0; i < seglen && cyc < ncyc; i = i + 1) begin
         @(negedge clk);
         case (mode)
            0: din = srnd14(amp);                       // white noise
            1: begin walk = walk + urange(-16, 16);                  // random walk
                  if (walk > 8191) walk = 8191; if (walk < -8192) walk = -8192; din = walk; end
            2: din = (i % 200 < 100) ? (14'sd8191 >>> amp) : (-14'sd8192 >>> amp); // square
            3: if (urange(0, 50) == 0) din = srnd14(amp);             // piecewise constant
            default: begin                                           // closed loop: plant = LPF(-dat_o) + noise
               plant = plant - (plant >>> 3) - ($signed(R.dat_o) >>> 4);
               din = plant + (srnd14(urange(5, 9)));
            end
         endcase
         ddin = ddin + urange(-32, 32);
         if (urange(0, 200) == 0) sync = ~sync;                      // pause on sync
         if (urange(0, 800) == 0) bus_write(16'h100, srnd14(urange(1, 6)));  // mid-segment ival write
      end
   end

   for (k = 0; k <= MAX_LAG; k = k + 1)
      $fwrite(fo, "LAG %0d %0d %0d %0d %0d %0d\n", k, match[k], mism[k], first_c[k], first_e[k], first_g[k]);
   $fwrite(fo, "XCOUNT %0d\n", xcount);
   $fwrite(fo, "RBSUM %0d %0d\n", rb_reads, rb_bad);
   $fwrite(fo, "COMPARED %0d EXCLUDED %0d SAT_HI %0d SAT_LO %0d ISAT %0d ARBSAT %0d\n",
           compared, excluded, sat_hi, sat_lo, isat, arbsat);
   $fclose(fo);
   $finish;
end

endmodule
