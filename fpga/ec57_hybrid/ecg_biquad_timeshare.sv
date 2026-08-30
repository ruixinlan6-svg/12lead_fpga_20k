`timescale 1ns / 1ps

// =============================================================================
// Module: ecg_biquad_timeshare
// Description: Fully parameterized high-speed 12-channel 4th-order Butterworth
//              filter with constant coefficient optimization for >60 MHz.
// =============================================================================

module ecg_biquad_timeshare #(
    parameter NUM_CHANNELS = 12,
    // Butterworth 5-25 Hz Biquad Coefficients @ 250 Hz in Q2.14
    parameter signed [15:0] S1_B0 = 16'sh0A5B,
    parameter signed [15:0] S1_B1 = 16'sh0000,
    parameter signed [15:0] S1_B2 = -16'sh0A5B,
    parameter signed [15:0] S1_A1 = -16'sh3521,
    parameter signed [15:0] S1_A2 = 16'sh1640,

    parameter signed [15:0] S2_B0 = 16'sh4000,
    parameter signed [15:0] S2_B1 = 16'sh0000,
    parameter signed [15:0] S2_B2 = -16'sh4000,
    parameter signed [15:0] S2_A1 = -16'sh38A2,
    parameter signed [15:0] S2_A2 = 16'sh1CD8
)(
    input  wire        clk,
    input  wire        rst_n,

    // Input Sample Interface
    input  wire        sample_valid,        // Asserted once per sample period (250 Hz)
    input  wire [3:0]  channel_idx,         // 0..11
    input  wire signed [15:0] sample_in,    // 16-bit input sample (1 LSB = 5 uV)

    // Output Filtered Sample
    output reg         sample_out_valid,
    output reg  [3:0]  sample_out_channel,
    output reg  signed [15:0] sample_out    // Saturated 16-bit filtered sample
);

    // Channel delay state storage (12 channels)
    reg signed [23:0] s1_d1 [0:NUM_CHANNELS-1];
    reg signed [23:0] s1_d2 [0:NUM_CHANNELS-1];
    reg signed [23:0] s2_d1 [0:NUM_CHANNELS-1];
    reg signed [23:0] s2_d2 [0:NUM_CHANNELS-1];

    // Local pipeline registers
    reg signed [23:0] local_s1_d1, local_s1_d2;
    reg signed [23:0] local_s2_d1, local_s2_d2;
    reg signed [23:0] next_s1_d1, next_s1_d2;
    reg signed [23:0] next_s2_d1, next_s2_d2;
    reg signed [23:0] sos1_y, sos2_y;

    // Multiplier Product Registers
    reg signed [39:0] prod_s1_b0, prod_s1_b1, prod_s1_b2;
    reg signed [39:0] prod_s1_a1, prod_s1_a2;
    reg signed [39:0] prod_s2_b0, prod_s2_b1, prod_s2_b2;
    reg signed [39:0] prod_s2_a1, prod_s2_a2;

    // Helper: 40-bit Saturation to signed 24-bit
    function automatic logic signed [23:0] sat24(input signed [39:0] acc);
        if (acc > 40'sh00_007F_FFFF)
            sat24 = 24'sh7F_FFFF;
        else if (acc < -40'sh00_0080_0000)
            sat24 = -24'sh80_0000;
        else
            sat24 = acc[23:0];
    endfunction

    // Helper: 40-bit Saturation to signed 16-bit
    function automatic logic signed [15:0] sat16(input signed [39:0] acc);
        if (acc > 40'sh00_0000_7FFF)
            sat16 = 16'sh7FFF;
        else if (acc < -40'sh00_0000_8000)
            sat16 = -16'sh8000;
        else
            sat16 = acc[15:0];
    endfunction

    typedef enum logic [3:0] {
        ST_IDLE,
        ST_S1_MULT_B,
        ST_S1_ACC_Y,
        ST_S1_MULT_A,
        ST_S1_UPD_D,
        ST_S2_MULT_B,
        ST_S2_ACC_Y,
        ST_S2_MULT_A,
        ST_S2_UPD_D,
        ST_WRITE_CH
    } filt_state_t;

    filt_state_t state;
    reg [3:0]  curr_ch;
    reg signed [15:0] curr_in;

    integer ch;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state              <= ST_IDLE;
            sample_out_valid   <= 1'b0;
            sample_out_channel <= 4'd0;
            sample_out         <= 16'sd0;
            curr_ch            <= 4'd0;
            curr_in            <= 16'sd0;
            local_s1_d1        <= 24'sd0;
            local_s1_d2        <= 24'sd0;
            local_s2_d1        <= 24'sd0;
            local_s2_d2        <= 24'sd0;
            next_s1_d1         <= 24'sd0;
            next_s1_d2         <= 24'sd0;
            next_s2_d1         <= 24'sd0;
            next_s2_d2         <= 24'sd0;
            sos1_y             <= 24'sd0;
            sos2_y             <= 24'sd0;
            prod_s1_b0         <= 40'sd0;
            prod_s1_b1         <= 40'sd0;
            prod_s1_b2         <= 40'sd0;
            prod_s1_a1         <= 40'sd0;
            prod_s1_a2         <= 40'sd0;
            prod_s2_b0         <= 40'sd0;
            prod_s2_b1         <= 40'sd0;
            prod_s2_b2         <= 40'sd0;
            prod_s2_a1         <= 40'sd0;
            prod_s2_a2         <= 40'sd0;
            for (ch = 0; ch < NUM_CHANNELS; ch = ch + 1) begin
                s1_d1[ch] <= 24'sd0;
                s1_d2[ch] <= 24'sd0;
                s2_d1[ch] <= 24'sd0;
                s2_d2[ch] <= 24'sd0;
            end
        end else begin
            case (state)
                ST_IDLE: begin
                    sample_out_valid <= 1'b0;
                    if (sample_valid) begin
                        curr_ch     <= channel_idx;
                        curr_in     <= sample_in;
                        local_s1_d1 <= s1_d1[channel_idx];
                        local_s1_d2 <= s1_d2[channel_idx];
                        local_s2_d1 <= s2_d1[channel_idx];
                        local_s2_d2 <= s2_d2[channel_idx];
                        state       <= ST_S1_MULT_B;
                    end
                end

                ST_S1_MULT_B: begin
                    prod_s1_b0 <= curr_in * S1_B0;
                    prod_s1_b1 <= curr_in * S1_B1;
                    prod_s1_b2 <= curr_in * S1_B2;
                    state      <= ST_S1_ACC_Y;
                end

                ST_S1_ACC_Y: begin
                    sos1_y <= sat24((prod_s1_b0 >>> 14) + {{16{local_s1_d1[23]}}, local_s1_d1});
                    state  <= ST_S1_MULT_A;
                end

                ST_S1_MULT_A: begin
                    prod_s1_a1 <= sos1_y * S1_A1;
                    prod_s1_a2 <= sos1_y * S1_A2;
                    state      <= ST_S1_UPD_D;
                end

                ST_S1_UPD_D: begin
                    next_s1_d1 <= sat24((prod_s1_b1 >>> 14) - (prod_s1_a1 >>> 14) + {{16{local_s1_d2[23]}}, local_s1_d2});
                    next_s1_d2 <= sat24((prod_s1_b2 >>> 14) - (prod_s1_a2 >>> 14));
                    state      <= ST_S2_MULT_B;
                end

                ST_S2_MULT_B: begin
                    prod_s2_b0 <= sos1_y * S2_B0;
                    prod_s2_b1 <= sos1_y * S2_B1;
                    prod_s2_b2 <= sos1_y * S2_B2;
                    state      <= ST_S2_ACC_Y;
                end

                ST_S2_ACC_Y: begin
                    sos2_y <= sat24((prod_s2_b0 >>> 14) + {{16{local_s2_d1[23]}}, local_s2_d1});
                    state  <= ST_S2_MULT_A;
                end

                ST_S2_MULT_A: begin
                    prod_s2_a1 <= sos2_y * S2_A1;
                    prod_s2_a2 <= sos2_y * S2_A2;
                    state      <= ST_S2_UPD_D;
                end

                ST_S2_UPD_D: begin
                    next_s2_d1 <= sat24((prod_s2_b1 >>> 14) - (prod_s2_a1 >>> 14) + {{16{local_s2_d2[23]}}, local_s2_d2});
                    next_s2_d2 <= sat24((prod_s2_b2 >>> 14) - (prod_s2_a2 >>> 14));
                    state      <= ST_WRITE_CH;
                end

                ST_WRITE_CH: begin
                    s1_d1[curr_ch] <= next_s1_d1;
                    s1_d2[curr_ch] <= next_s1_d2;
                    s2_d1[curr_ch] <= next_s2_d1;
                    s2_d2[curr_ch] <= next_s2_d2;

                    sample_out         <= sat16({{16{sos2_y[23]}}, sos2_y});
                    sample_out_channel <= curr_ch;
                    sample_out_valid   <= 1'b1;
                    state              <= ST_IDLE;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
