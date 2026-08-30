`timescale 1ns / 1ps

// =============================================================================
// Module: ecg_sync_dp_ram
// Description: Parameterized Simple Dual-Port Synchronous Block RAM (SDPB) for
//              Twelve-Lead ECG QN88 Accelerator Infrastructure.
// =============================================================================

module ecg_sync_dp_ram #(
    parameter int    DATA_WIDTH    = 8,
    parameter int    DEPTH         = 256,
    parameter int    ADDR_WIDTH    = (DEPTH > 1) ? $clog2(DEPTH) : 1,
    parameter string INIT_HEX_FILE = ""
)(
    input  wire                  clk,
    input  wire                  rst_n,    // Intentionally unused; caller gates enables
    
    // Write Port
    input  wire                  wr_en,
    input  wire [ADDR_WIDTH-1:0] wr_addr,
    input  wire [DATA_WIDTH-1:0] wr_data,
    
    // Read Port
    input  wire                  rd_en,
    input  wire [ADDR_WIDTH-1:0] rd_addr,
    output reg  [DATA_WIDTH-1:0] rd_data
);

    (* ram_style = "block" *)
    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    initial begin
        if (INIT_HEX_FILE != "") begin
            $readmemh(INIT_HEX_FILE, mem);
        end
    end

    // Pure synchronous memory block: Gowin SDPB BSRAM standard template
    always @(posedge clk) begin
        if (wr_en) begin
            mem[wr_addr] <= wr_data;
        end
        if (rd_en) begin
            rd_data <= mem[rd_addr];
        end
    end

endmodule
