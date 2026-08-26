`timescale 1ns/1ps

// Verilog-2001 compatibility form of fpga/rtl/conv1d_mac_int8.sv for the
// installed Gowin parser. Arithmetic and handshake semantics are identical.
module conv1d_mac_int8_gowin #(
    parameter integer ACC_WIDTH = 32
) (
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire in_valid,
    input wire in_last,
    input wire signed [7:0] activation,
    input wire signed [7:0] weight,
    output reg busy,
    output reg done,
    output reg signed [ACC_WIDTH-1:0] result
);
    reg signed [ACC_WIDTH-1:0] accumulator;
    reg signed [15:0] product;
    reg signed [ACC_WIDTH-1:0] product_ext;
    reg signed [ACC_WIDTH-1:0] next_accumulator;

    always @* begin
        product = $signed(activation) * $signed(weight);
        product_ext = {{(ACC_WIDTH-16){product[15]}}, product};
        next_accumulator = accumulator + product_ext;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accumulator <= {ACC_WIDTH{1'b0}};
            result <= {ACC_WIDTH{1'b0}};
            busy <= 1'b0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;
            if (start) begin
                accumulator <= {ACC_WIDTH{1'b0}};
                result <= {ACC_WIDTH{1'b0}};
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
