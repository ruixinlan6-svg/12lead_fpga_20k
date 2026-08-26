`timescale 1ns/1ps

// Byte-write / word-read parameter store.  It is deliberately isolated from
// the compute memories so Gowin can infer one 32-bit BSRAM per narrow bank;
// the wrapper uses the store only while staging a 25-word SDRAM burst.
module ecg_weight_store #(
    parameter integer WORDS = 2574
) (
    input  wire        clk,
    input  wire        byte_we,
    input  wire [13:0] byte_addr,
    input  wire [7:0]  byte_data,
    input  wire        read_en,
    input  wire [11:0] read_addr,
    output reg [31:0]  read_data
);
    reg [31:0] mem [0:WORDS-1];

    always @(posedge clk) begin
        if (byte_we) begin
            case (byte_addr[1:0])
                2'd0: mem[byte_addr >> 2][7:0] <= byte_data;
                2'd1: mem[byte_addr >> 2][15:8] <= byte_data;
                2'd2: mem[byte_addr >> 2][23:16] <= byte_data;
                default: mem[byte_addr >> 2][31:24] <= byte_data;
            endcase
        end
        if (read_en)
            read_data <= mem[read_addr];
    end
endmodule
