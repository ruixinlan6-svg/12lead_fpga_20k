`timescale 1ns / 1ps

// =============================================================================
// Module: ecg_gowin_primitives_microbench_top
// Description: Non-prunable Gowin EDA Synthesis & PnR Microbenchmark Top for
//              Twelve-Lead ECG QN88 Generic RTL Infrastructure Primitives.
//
// Instantiates:
//   1. ecg_sync_sp_ram #(DATA_WIDTH=8, DEPTH=2048) -> Expected: 1 BSRAM
//   2. ecg_sync_dp_ram #(DATA_WIDTH=8, DEPTH=2048) -> Expected: 1 BSRAM (SDPB)
//   3. ecg_requant_mac #(ACC_WIDTH=32, MULT_WIDTH=32, OUT_WIDTH=8, SHIFT_WIDTH=5)
//      -> Expected: 1..4 DSP blocks (18x18 multipliers)
//
// Key Fixes:
//   - Pipelined SP & DP RAM read-valid flags (1-cycle latency alignment) to
//     prevent uninitialized X/Z from contaminating the signature accumulator.
//   - Strict data gating before XOR reduction.
//
// Target Hardware: GW2AR-LV18QN88C8/I7 (27.000 MHz Clock)
// =============================================================================

module ecg_gowin_primitives_microbench_top (
    input  wire        clk,
    input  wire        rst_n,
    
    // External Stimulus & Control Interface (Narrow IO to avoid QN88 pin limits)
    input  wire        din_valid,
    input  wire [7:0]  din_data,
    input  wire [1:0]  ctrl_mode,
    
    // Observable Outputs (Signature Accumulator & Flags)
    output reg         dout_valid,
    output reg  [7:0]  dout_data,
    output reg  [3:0]  status_flags
);

    // -------------------------------------------------------------------------
    // 1. Dynamic Stimulus Generation & Shift Register Bank
    // -------------------------------------------------------------------------
    reg [10:0] sp_addr_reg;
    reg [7:0]  sp_din_reg;
    reg        sp_en_reg;
    reg        sp_we_reg;
    
    reg [10:0] dp_wr_addr_reg;
    reg [7:0]  dp_wr_data_reg;
    reg        dp_wr_en_reg;
    reg [10:0] dp_rd_addr_reg;
    reg        dp_rd_en_reg;
    
    reg signed [31:0] mac_acc_reg;
    reg signed [31:0] mac_mult_reg;
    reg        [4:0]  mac_shift_reg;
    reg               mac_relu_reg;
    reg               mac_valid_reg;

    // Free-running pseudo-random sequence to guarantee continuous switching
    reg [15:0] lfsr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr            <= 16'hACE1;
            sp_addr_reg     <= 11'd0;
            sp_din_reg      <= 8'd0;
            sp_en_reg       <= 1'b0;
            sp_we_reg       <= 1'b0;
            dp_wr_addr_reg  <= 11'd0;
            dp_wr_data_reg  <= 8'd0;
            dp_wr_en_reg    <= 1'b0;
            dp_rd_addr_reg  <= 11'd0;
            dp_rd_en_reg    <= 1'b0;
            mac_acc_reg     <= 32'sd0;
            mac_mult_reg    <= 32'sd0;
            mac_shift_reg   <= 5'd0;
            mac_relu_reg    <= 1'b0;
            mac_valid_reg   <= 1'b0;
        end else begin
            // LFSR update (XOR taps 16, 14, 13, 11)
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};

            if (din_valid) begin
                // Shift-in external byte to modulate internal parameters
                mac_acc_reg    <= {mac_acc_reg[23:0], din_data};
                mac_mult_reg   <= {mac_mult_reg[23:0], mac_acc_reg[31:24]};
                mac_shift_reg  <= din_data[4:0];
                mac_relu_reg   <= din_data[5];
                mac_valid_reg  <= 1'b1;

                sp_addr_reg    <= {sp_addr_reg[2:0], din_data};
                sp_din_reg     <= din_data ^ 8'hA5;
                sp_en_reg      <= 1'b1;
                sp_we_reg      <= din_data[0];

                dp_wr_addr_reg <= {dp_wr_addr_reg[2:0], din_data};
                dp_wr_data_reg <= din_data ^ 8'h5A;
                dp_wr_en_reg   <= din_data[1];
                dp_rd_addr_reg <= dp_wr_addr_reg ^ {3'b000, din_data};
                dp_rd_en_reg   <= 1'b1;
            end else if (ctrl_mode == 2'b01) begin
                // Continuous dynamic operation mode via LFSR
                mac_acc_reg    <= mac_acc_reg + { {16{lfsr[15]}}, lfsr };
                mac_mult_reg   <= {mac_mult_reg[30:0], lfsr[0]} ^ 32'h00010001;
                mac_shift_reg  <= lfsr[4:0];
                mac_relu_reg   <= lfsr[6];
                mac_valid_reg  <= lfsr[7];

                sp_addr_reg    <= sp_addr_reg + 11'd1;
                sp_din_reg     <= lfsr[7:0];
                sp_en_reg      <= 1'b1;
                sp_we_reg      <= lfsr[8];

                dp_wr_addr_reg <= dp_wr_addr_reg + 11'd1;
                dp_wr_data_reg <= lfsr[15:8];
                dp_wr_en_reg   <= lfsr[9];
                dp_rd_addr_reg <= dp_rd_addr_reg + 11'd3;
                dp_rd_en_reg   <= 1'b1;
            end else begin
                mac_valid_reg  <= 1'b0;
                sp_en_reg      <= 1'b0;
                dp_wr_en_reg   <= 1'b0;
                dp_rd_en_reg   <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // 2. Device Under Test (DUT) Instantiations
    // -------------------------------------------------------------------------

    // DUT 1: Parameterized Single-Port Synchronous RAM (2048 x 8 = 16 Kbit -> 1 BSRAM)
    wire [7:0] sp_dout;
    ecg_sync_sp_ram #(
        .DATA_WIDTH (8),
        .DEPTH      (2048)
    ) u_sp_ram (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (sp_en_reg),
        .we    (sp_we_reg),
        .addr  (sp_addr_reg),
        .din   (sp_din_reg),
        .dout  (sp_dout)
    );

    // DUT 2: Parameterized Simple Dual-Port Synchronous RAM (2048 x 8 = 16 Kbit -> 1 BSRAM)
    wire [7:0] dp_rd_data;
    ecg_sync_dp_ram #(
        .DATA_WIDTH (8),
        .DEPTH      (2048)
    ) u_dp_ram (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (dp_wr_en_reg),
        .wr_addr (dp_wr_addr_reg),
        .wr_data (dp_wr_data_reg),
        .rd_en   (dp_rd_en_reg),
        .rd_addr (dp_rd_addr_reg),
        .rd_data (dp_rd_data)
    );

    // DUT 3: Parameterized Requant MAC (32x32 -> 64-bit -> Shift/Round -> INT8)
    wire signed [7:0] mac_out_data;
    wire              mac_out_valid;
    ecg_requant_mac #(
        .ACC_WIDTH   (32),
        .MULT_WIDTH  (32),
        .OUT_WIDTH   (8),
        .SHIFT_WIDTH (5)
    ) u_requant_mac (
        .clk       (clk),
        .rst_n     (rst_n),
        .in_valid  (mac_valid_reg),
        .in_acc    (mac_acc_reg),
        .in_mult   (mac_mult_reg),
        .in_shift  (mac_shift_reg),
        .relu_en   (mac_relu_reg),
        .out_valid (mac_out_valid),
        .out_data  (mac_out_data)
    );

    // -------------------------------------------------------------------------
    // 3. RAM Read Valid Pipeline (1-cycle latency alignment)
    // -------------------------------------------------------------------------
    reg sp_dout_valid;
    reg dp_dout_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sp_dout_valid <= 1'b0;
            dp_dout_valid <= 1'b0;
        end else begin
            sp_dout_valid <= sp_en_reg;
            dp_dout_valid <= dp_rd_en_reg;
        end
    end

    // Gated terms: strictly 0 when not valid, preventing uninitialized RAM read propagation
    wire [7:0] sp_term  = sp_dout_valid ? sp_dout : 8'd0;
    wire [7:0] dp_term  = dp_dout_valid ? dp_rd_data : 8'd0;
    wire [7:0] mac_term = mac_out_valid ? mac_out_data : 8'd0;

    // -------------------------------------------------------------------------
    // 4. Observable Output Signature Accumulator
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dout_valid   <= 1'b0;
            dout_data    <= 8'd0;
            status_flags <= 4'd0;
        end else begin
            dout_valid   <= sp_dout_valid | dp_dout_valid | mac_out_valid;
            
            // Signature reduction accumulates strictly valid data terms
            if (sp_dout_valid | dp_dout_valid | mac_out_valid) begin
                dout_data <= dout_data ^ sp_term ^ dp_term ^ mac_term;
            end
            
            status_flags <= {
                mac_out_valid,
                sp_dout_valid,
                dp_dout_valid,
                (mac_out_data == 8'sd127) | (mac_out_data == -8'sd128)
            };
        end
    end

endmodule
