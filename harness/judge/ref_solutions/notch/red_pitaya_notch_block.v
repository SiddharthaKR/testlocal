// CANARY-b81aed453118 (hidden file marker: if this string reaches the agent, the run is flagged)
// Reference solution for the Track H judge self-test (hidden from the agent).
// Direct Form I biquad notch, bit-exact with notch_model.py. Three registers from
// dat_i to dat_o (input, feed-forward, output/feedback); the judge reports latency 2.

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

// input delay line
reg signed [14-1:0] x0, x1, x2;
// feed-forward sum (pipelined, outside the recursion)
reg signed [ACC-1:0] ff;
// output / feedback state (saturated)
reg signed [14-1:0] y1, y2;

wire signed [ACC-1:0] acc = ff - a1*y1 - a2*y2;
wire signed [ACC-1:0] rnd = (acc + (1 <<< (COEF_FRAC-1))) >>> COEF_FRAC;
wire signed [14-1:0]  sat = (rnd >  8191) ? 14'sd8191  :
                            (rnd < -8192) ? -14'sd8192 : rnd[14-1:0];

always @(posedge clk_i) begin
   if (rstn_i == 1'b0) begin
      x0 <= 0; x1 <= 0; x2 <= 0;
      ff <= 0;
      y1 <= 0; y2 <= 0;
   end
   else begin
      x0 <= dat_i;
      x1 <= x0;
      x2 <= x1;
      ff <= b0*x0 + b1*x1 + b2*x2;
      y1 <= sat;
      y2 <= y1;
   end
end

// x2 is aligned with y1 (both 3 cycles after dat_i)
assign dat_o = bypass ? x2 : y1;

endmodule
