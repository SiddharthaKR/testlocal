// Reference solution for the judge self-test (hidden from the agent).
// Gain / shift / offset block, bit-exact with gain_model.py. Three registers from
// dat_i to dat_o (input, product, output); the judge reports latency 2.

module red_pitaya_gain_block (
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

localparam GAIN_BITS = 16;
localparam SW = 4;      // shift register width

reg signed [GAIN_BITS-1:0] gain;
reg        [SW-1:0]        shift;
reg signed [14-1:0]        offset;

//  System bus connection
always @(posedge clk_i) begin
   if (rstn_i == 1'b0) begin
      gain <= 0; shift <= 0; offset <= 0;
      ack <= 1'b0;
      rdata <= 32'h0;
   end
   else begin
      if (wen) begin
         if (addr==16'h100) gain   <= wdata[GAIN_BITS-1:0];
         if (addr==16'h104) shift  <= wdata[SW-1:0];
         if (addr==16'h108) offset <= wdata[14-1:0];
      end
      ack <= wen|ren;
      casez (addr)
         16'h100 : rdata <= {{32-GAIN_BITS{gain[GAIN_BITS-1]}},gain};
         16'h104 : rdata <= {{32-SW{1'b0}},shift};
         16'h108 : rdata <= {{32-14{offset[14-1]}},offset};
         16'h200 : rdata <= GAIN_BITS;
         default : rdata <= 32'h0;
      endcase
   end
end

reg signed [14-1:0]  x0;
reg signed [32-1:0]  p;
reg signed [14-1:0]  out;

wire signed [32-1:0] half = (shift == 0) ? 32'sd0 : (32'sd1 <<< (shift - 1));
wire signed [32-1:0] sum  = p + half;
wire signed [32-1:0] rnd  = sum >>> shift;
wire signed [32-1:0] tot  = rnd + offset;
wire signed [14-1:0] sat  = (tot >  8191) ? 14'sd8191  :
                            (tot < -8192) ? -14'sd8192 : tot[14-1:0];

always @(posedge clk_i) begin
   if (rstn_i == 1'b0) begin
      x0 <= 0; p <= 0; out <= 0;
   end
   else begin
      x0  <= dat_i;
      p   <= x0 * gain;
      out <= sat;
   end
end

assign dat_o = out;

endmodule
