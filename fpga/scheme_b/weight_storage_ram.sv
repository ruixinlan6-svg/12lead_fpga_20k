`timescale 1ns/1ps

// Dual-Port Weight Storage RAM (16KB / 16384 bytes)
// Port A: Written by UART RX loader during payload reception (10,293 bytes).
// Port B: Read by Layer DMA controller to stream layer weights into on-chip cache.

module weight_storage_ram #(
    parameter integer ADDR_WIDTH = 14,
    parameter integer DEPTH = 16384
) (
    input  wire                  clk,
    input  wire                  wr_en,
    input  wire [ADDR_WIDTH-1:0] wr_addr,
    input  wire [7:0]            wr_data,
    input  wire                  rd_en,
    input  wire [ADDR_WIDTH-1:0] rd_addr,
    output reg  [7:0]            rd_data
);

    reg [7:0] mem [0:DEPTH-1];

    always @(posedge clk) begin
        if (wr_en) begin
            mem[wr_addr] <= wr_data;
        end
        if (rd_en) begin
            rd_data <= mem[rd_addr];
        end
    end

endmodule