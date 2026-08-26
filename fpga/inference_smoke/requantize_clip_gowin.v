`timescale 1ns/1ps

// Verilog-2001 compatibility form of fpga/rtl/requantize_clip.sv for Gowin.
module requantize_clip_gowin #(
    parameter integer ACC_WIDTH = 32,
    parameter integer MULT_WIDTH = 32,
    parameter integer OUT_WIDTH = 8
) (
    input wire signed [ACC_WIDTH-1:0] acc,
    input wire signed [ACC_WIDTH-1:0] offset,
    input wire signed [MULT_WIDTH-1:0] multiplier,
    input wire [5:0] shift,
    output reg signed [OUT_WIDTH-1:0] result
);
    localparam integer PRODUCT_WIDTH = ACC_WIDTH + MULT_WIDTH + 1;
    reg signed [ACC_WIDTH:0] adjusted;
    reg signed [PRODUCT_WIDTH-1:0] product;
    reg signed [PRODUCT_WIDTH-1:0] rounded;
    reg signed [PRODUCT_WIDTH-1:0] scaled;
    reg signed [PRODUCT_WIDTH-1:0] round_term;
    reg signed [PRODUCT_WIDTH-1:0] max_value;
    reg signed [PRODUCT_WIDTH-1:0] min_value;

    always @* begin
        adjusted = $signed(acc) + $signed(offset);
        product = adjusted * $signed(multiplier);
        round_term = {PRODUCT_WIDTH{1'b0}};
        if (shift != 0)
            round_term = ({{(PRODUCT_WIDTH-1){1'b0}}, 1'b1} <<< (shift - 1));
        if (shift == 0)
            rounded = product;
        else if (product < 0)
            rounded = product - round_term;
        else
            rounded = product + round_term;
        scaled = (shift == 0) ? rounded : (rounded >>> shift);
        max_value = (1 <<< (OUT_WIDTH-1)) - 1;
        min_value = -(1 <<< (OUT_WIDTH-1));
        if (scaled > max_value)
            result = max_value[OUT_WIDTH-1:0];
        else if (scaled < min_value)
            result = min_value[OUT_WIDTH-1:0];
        else
            result = scaled[OUT_WIDTH-1:0];
    end
endmodule
