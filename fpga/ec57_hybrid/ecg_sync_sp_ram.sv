`timescale 1ns / 1ps

// =============================================================================
// Module: ecg_sync_sp_ram
// Description: Parameterized Single-Port Synchronous Block RAM (SP) for
//              Twelve-Lead ECG QN88 Accelerator Infrastructure.
// =============================================================================

module ecg_sync_sp_ram #(
    parameter int    DATA_WIDTH    = 8,
    parameter int    DEPTH         = 256,
    parameter int    ADDR_WIDTH    = (DEPTH > 1) ? $clog2(DEPTH) : 1,
    parameter string INIT_HEX_FILE = ""
)(
    input  wire                  clk,
    input  wire                  rst_n,   // Intentionally unused; caller gates en
    input  wire                  en,      // Memory chip enable
    input  wire                  we,      // Write enable (1=write, 0=read)
    input  wire [ADDR_WIDTH-1:0] addr,    // Address port
    input  wire [DATA_WIDTH-1:0] din,     // Data input
    output reg  [DATA_WIDTH-1:0] dout     // Data output (1-cycle latency, read-first)
);

    (* ram_style = "block" *)
    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];

    initial begin
        if (INIT_HEX_FILE != "") begin
            $readmemh(INIT_HEX_FILE, mem);
        end
    end

    // Pure synchronous memory port: Gowin BSRAM standard template
    always @(posedge clk) begin
        if (en) begin
            if (we) begin
                mem[addr] <= din;
            end
            dout <= mem[addr];
        end
    end

endmodule
