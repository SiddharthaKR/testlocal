// ASSIST SKELETON (run_demo.sh --assist): ports, register map and bus decode are done.
// TODO: implement the datapath per tasks/H/notch_spec.md (bit-exact with notch_model.py).

module red_pitaya_notch_block (
   input                    clk_i,
   input                    rstn_i,
   input  signed [14-1:0]   dat_i,
   output signed [14-1:0]   dat_o,
   input         [16-1:0]   addr,
   input                    wen,
   input                    ren,
   output reg               ack,
   output reg    [32-1:0]   rdata,
   input         [32-1:0]   wdata
);

localparam COEF_FRAC = 16;
localparam CB  = 18;    // coefficient bits
localparam ACC = 40;    // accumulator bits (>= 35 needed)

reg signed [CB-1:0] b0, b1, b2, a1, a2;
reg                 bypass;

//  System bus connection
always @(posedge clk_i) begin
   if (rstn_i == 1'b0) begin
      b0 <= 0; b1 <= 0; b2 <= 0; a1 <= 0; a2 <= 0;
      bypass <= 1'b0;
      ack <= 1'b0;
      rdata <= 32'h0;
   end
   else begin
      if (wen) begin
         if (addr==16'h100) b0 <= wdata[CB-1:0];
         if (addr==16'h104) b1 <= wdata[CB-1:0];
         if (addr==16'h108) b2 <= wdata[CB-1:0];
         if (addr==16'h10C) a1 <= wdata[CB-1:0];
         if (addr==16'h110) a2 <= wdata[CB-1:0];
         if (addr==16'h114) bypass <= wdata[0];
      end
      ack <= wen|ren;
      casez (addr)
         16'h100 : rdata <= {{32-CB{b0[CB-1]}},b0};
         16'h104 : rdata <= {{32-CB{b1[CB-1]}},b1};
         16'h108 : rdata <= {{32-CB{b2[CB-1]}},b2};
         16'h10C : rdata <= {{32-CB{a1[CB-1]}},a1};
         16'h110 : rdata <= {{32-CB{a2[CB-1]}},a2};
         16'h114 : rdata <= {31'h0,bypass};
         16'h200 : rdata <= COEF_FRAC;
         default : rdata <= 32'h0;
      endcase
   end
end

// ---------------------------------------------------------------------------
// TODO: datapath
//  - delay line for x[n-1], x[n-2]; state y[n-1], y[n-2] (saturated)
//  - acc = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]  (>= 35 bits)
//  - y[n] = sat14((acc + 2^15) >>> 16)
//  - bypass: dat_o = dat_i delayed by the SAME latency as the filter path
//  - the feedback loop must complete in one clock cycle
// ---------------------------------------------------------------------------

assign dat_o = 14'sd0;   // TODO: replace

endmodule
