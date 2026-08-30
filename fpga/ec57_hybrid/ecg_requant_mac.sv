`timescale 1ns / 1ps

// =============================================================================
// Module: ecg_requant_mac
// Description: Parameterized Fixed-Point Requantization & Clamping Unit for
//              Twelve-Lead ECG QN88 Accelerator Infrastructure.
//
// Mathematical Specification:
//   1. Intermediate Product (64-bit signed):
//      prod = $signed(in_acc) * $signed(in_mult)
//   2. Symmetric Round-Half-Away-From-Zero (shift in 0..31):
//      If shift == 0:
//          round_term = 0
//      Else if prod >= 0:
//          round_term = 1 <<< (shift - 1)
//      Else (prod < 0):
//          round_term = (1 <<< (shift - 1)) - 1
//      scaled_val = (prod + round_term) >>> shift
//   3. Saturation Clamping (Signed INT8: [-128, +127]) & Optional ReLU:
//      If relu_en && scaled_val < 0:
//          out_data = 0
//      Else:
//          out_data = clamp(scaled_val, -128, +127)
//
// Pipeline timing: two registered stages. If in_valid/data are sampled at
// rising edge E0, out_valid/data are registered at rising edge E1. This is one
// full clock period after acceptance; callers driving just after an edge wait
// two subsequent rising edges, as shown in the testbench.
// =============================================================================

module ecg_requant_mac #(
    parameter int ACC_WIDTH   = 32, // Input accumulator bit-width (signed int32)
    parameter int MULT_WIDTH  = 32, // Multiplier bit-width (signed int32)
    parameter int OUT_WIDTH   = 8,  // Output activation bit-width (signed int8)
    parameter int SHIFT_WIDTH = 5   // Shift bit-width (covers 0..31)
)(
    input  wire                          clk,
    input  wire                          rst_n,      // Active-low async assert, sync release
    
    // Handshake and Data Inputs
    input  wire                          in_valid,   // Input valid strobe
    input  wire signed [ACC_WIDTH-1:0]   in_acc,     // Signed int32 accumulator
    input  wire signed [MULT_WIDTH-1:0]  in_mult,    // Signed int32 multiplier
    input  wire        [SHIFT_WIDTH-1:0] in_shift,   // Shift amount (0..31)
    input  wire                          relu_en,    // 1 = enable ReLU, 0 = linear bypass
    
    // Pipeline Outputs (capture edge E0 -> registered output edge E1)
    output reg                           out_valid,  // Output valid strobe
    output reg  signed [OUT_WIDTH-1:0]   out_data    // Saturated signed int8 output
);

    // Dynamic saturation bounds
    localparam signed [63:0] MAX_SIGNED_VAL = (64'sd1 <<< (OUT_WIDTH - 1)) - 64'sd1;
    localparam signed [63:0] MIN_SIGNED_VAL = -(64'sd1 <<< (OUT_WIDTH - 1));

    // -------------------------------------------------------------------------
    // Pipeline Stage 1: Hardware Signed Multiplier (64-bit full product)
    // -------------------------------------------------------------------------
    reg signed [63:0]            stage1_prod;
    reg        [SHIFT_WIDTH-1:0] stage1_shift;
    reg                          stage1_relu;
    reg                          stage1_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage1_valid <= 1'b0;
            stage1_prod  <= 64'sd0;
            stage1_shift <= {SHIFT_WIDTH{1'b0}};
            stage1_relu  <= 1'b0;
        end else begin
            stage1_valid <= in_valid;
            if (in_valid) begin
                stage1_prod  <= $signed(in_acc) * $signed(in_mult);
                stage1_shift <= in_shift;
                stage1_relu  <= relu_en;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Stage 2 Combinational Logic: Rounding, Arithmetic Shift, & Clamp
    // -------------------------------------------------------------------------
    reg signed [63:0]          round_term;
    reg signed [63:0]          prod_rounded;
    reg signed [63:0]          scaled_val;
    reg signed [OUT_WIDTH-1:0] clamped_val;

    always @(*) begin
        // Round-half-away-from-zero term generation
        if (stage1_shift == {SHIFT_WIDTH{1'b0}}) begin
            round_term = 64'sd0;
        end else begin
            if (stage1_prod >= 64'sd0) begin
                round_term = (64'sd1 <<< (stage1_shift - 1));
            end else begin
                round_term = (64'sd1 <<< (stage1_shift - 1)) - 64'sd1;
            end
        end

        prod_rounded = stage1_prod + round_term;
        scaled_val   = prod_rounded >>> stage1_shift;

        // Dynamic Clamping / Saturation with optional ReLU
        if (stage1_relu && (scaled_val < 64'sd0)) begin
            clamped_val = {OUT_WIDTH{1'b0}};
        end else if (scaled_val > MAX_SIGNED_VAL) begin
            clamped_val = MAX_SIGNED_VAL[OUT_WIDTH-1:0];
        end else if (scaled_val < MIN_SIGNED_VAL) begin
            clamped_val = MIN_SIGNED_VAL[OUT_WIDTH-1:0];
        end else begin
            clamped_val = scaled_val[OUT_WIDTH-1:0];
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Stage 2 Register Output
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
            out_data  <= {OUT_WIDTH{1'b0}};
        end else begin
            out_valid <= stage1_valid;
            if (stage1_valid) begin
                out_data <= clamped_val;
            end
        end
    end

endmodule
