`timescale 1ns/1ps

// Synchronous-read, single-write-port memory intended for Gowin BSRAM
// inference.  The registered read data is deliberately kept separate from
// reset: reset must not clear model/activity contents on the hardware path.
module ecg_sync_dp_ram #(
    parameter integer DATA_WIDTH = 8,
    parameter integer ADDR_WIDTH = 1,
    parameter integer DEPTH = 2
) (
    input  wire                         clk,
    input  wire                         wr_en,
    input  wire [ADDR_WIDTH-1:0]        wr_addr,
    input  wire signed [DATA_WIDTH-1:0] wr_data,
    input  wire                         rd_en,
    input  wire [ADDR_WIDTH-1:0]        rd_addr,
    output reg  signed [DATA_WIDTH-1:0] rd_data
);
    // Keep this array visible for simulation Golden loading.  The write and
    // registered read pattern is the portable Gowin-compatible part.
    (* ram_style = "block" *)
    reg signed [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    always @(posedge clk) begin
        if (wr_en)
            mem[wr_addr] <= wr_data;
        // Unconditional registered read is the canonical Gowin block-RAM
        // template.  rd_en is used only to qualify the consumer; holding the
        // address/output while idle is unnecessary for this FSM.
        rd_data <= mem[rd_addr];
    end
endmodule
