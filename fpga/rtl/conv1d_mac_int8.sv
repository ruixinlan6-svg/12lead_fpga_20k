`timescale 1ns/1ps

// Minimal signed INT8 streaming dot product.
// The controller supplies exactly one vector and marks its final pair with
// in_last. The final product is included in result before done is asserted.
module conv1d_mac_int8 #(
    parameter integer ACC_WIDTH = 32
) (
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic                   start,
    input  logic                   in_valid,
    input  logic                   in_last,
    input  logic signed [7:0]      activation,
    input  logic signed [7:0]      weight,
    output logic                   busy,
    output logic                   done,
    output logic signed [ACC_WIDTH-1:0] result
);
    logic signed [ACC_WIDTH-1:0] accumulator;
    logic signed [15:0] product;
    logic signed [ACC_WIDTH-1:0] product_ext;
    logic signed [ACC_WIDTH-1:0] next_accumulator;

    always_comb begin
        product = $signed(activation) * $signed(weight);
        product_ext = {{(ACC_WIDTH-16){product[15]}}, product};
        next_accumulator = accumulator + product_ext;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accumulator <= '0;
            result <= '0;
            busy <= 1'b0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;
            if (start) begin
                accumulator <= '0;
                result <= '0;
                busy <= 1'b1;
            end else if (busy && in_valid) begin
                accumulator <= next_accumulator;
                if (in_last) begin
                    result <= next_accumulator;
                    busy <= 1'b0;
                    done <= 1'b1;
                end
            end
        end
    end
endmodule
