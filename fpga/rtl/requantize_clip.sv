`timescale 1ns/1ps

// Signed accumulator -> signed INT8 requantization.
// For shift > 0, round to nearest with sign-symmetric half-step handling.
module requantize_clip #(
    parameter integer ACC_WIDTH  = 32,
    parameter integer MULT_WIDTH = 32,
    parameter integer OUT_WIDTH  = 8
) (
    input  logic signed [ACC_WIDTH-1:0]  acc,
    input  logic signed [ACC_WIDTH-1:0]  offset,
    input  logic signed [MULT_WIDTH-1:0] multiplier,
    input  logic        [5:0]            shift,
    output logic signed [OUT_WIDTH-1:0]  result
);
    localparam integer PRODUCT_WIDTH = ACC_WIDTH + MULT_WIDTH + 1;
    logic signed [ACC_WIDTH:0] adjusted;
    logic signed [PRODUCT_WIDTH-1:0] product;
    logic signed [PRODUCT_WIDTH-1:0] rounded;
    logic signed [PRODUCT_WIDTH-1:0] scaled;
    logic signed [PRODUCT_WIDTH-1:0] round_term;
    logic signed [PRODUCT_WIDTH-1:0] max_value;
    logic signed [PRODUCT_WIDTH-1:0] min_value;

    always_comb begin
        adjusted = $signed(acc) + $signed(offset);
        product = adjusted * $signed(multiplier);
        round_term = '0;
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
