`timescale 1ns / 1ps

// =============================================================================
// Module: lead_sqi_select
// Description: Multi-lead Signal Quality Index (SQI) evaluator and lead selection.
//              Sequential multi-cycle evaluator for high Fmax timing closure.
// =============================================================================

module lead_sqi_select (
    input  wire        clk,
    input  wire        rst_n,

    // Sample Input Interface (12 leads per sample period)
    input  wire        sample_valid,
    input  wire [3:0]  channel_idx,         // 0..11
    input  wire signed [15:0] sample_in,

    // SQI Window Status & Selected Leads
    output reg         window_updated,
    output reg  [3:0]  valid_leads_count,   // 0..12
    output reg  [3:0]  lead_idx_0,          // Best lead
    output reg  [3:0]  lead_idx_1,          // 2nd best lead
    output reg  [3:0]  lead_idx_2,          // 3rd best lead
    output reg         degraded_one_lead,   // Only 1 lead valid
    output reg         signal_loss          // 0 leads valid
);

    localparam WINDOW_SIZE = 9'd500;

    // Per-lead statistics accumulators for current window
    reg [8:0]  sample_count;
    reg signed [15:0] min_val [0:11];
    reg signed [15:0] max_val [0:11];
    reg signed [15:0] prev_sample [0:11];
    reg [8:0]  sat_count [0:11];
    reg [8:0]  noise_count [0:11];
    reg [1:0]  consec_sat [0:11];

    // Frozen Valid Leads bitmap
    reg [11:0] lead_valid_mask;

    // Sequential Evaluation State Machine
    typedef enum logic [1:0] {
        SQI_ACCUM,
        SQI_EVAL,
        SQI_RANK,
        SQI_UPDATE
    } sqi_state_t;

    sqi_state_t eval_state;
    reg [3:0]   eval_ch;
    reg [11:0]  temp_mask;
    reg [3:0]   temp_vcount;
    reg [3:0]   temp_sel0, temp_sel1, temp_sel2;

    integer ch;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sample_count       <= 9'd0;
            window_updated     <= 1'b0;
            valid_leads_count  <= 4'd12;
            lead_idx_0         <= 4'd1;  // Default Lead II
            lead_idx_1         <= 4'd0;  // Default Lead I
            lead_idx_2         <= 4'd6;  // Default Lead V1
            degraded_one_lead  <= 1'b0;
            signal_loss        <= 1'b0;
            lead_valid_mask    <= 12'hFFF;
            eval_state         <= SQI_ACCUM;
            eval_ch            <= 4'd0;
            temp_mask          <= 12'hFFF;
            temp_vcount        <= 4'd12;
            temp_sel0          <= 4'd1;
            temp_sel1          <= 4'd0;
            temp_sel2          <= 4'd6;

            for (ch = 0; ch < 12; ch = ch + 1) begin
                min_val[ch]     <= 16'sh7FFF;
                max_val[ch]     <= -16'sh8000;
                prev_sample[ch] <= 16'sd0;
                sat_count[ch]   <= 9'd0;
                noise_count[ch] <= 9'd0;
                consec_sat[ch]  <= 2'd0;
            end
        end else begin
            window_updated <= 1'b0;

            case (eval_state)
                SQI_ACCUM: begin
                    if (sample_valid) begin
                        if (sample_in < min_val[channel_idx]) min_val[channel_idx] <= sample_in;
                        if (sample_in > max_val[channel_idx]) max_val[channel_idx] <= sample_in;

                        if (sample_in >= 16'sd32760 || sample_in <= -16'sd32760) begin
                            sat_count[channel_idx] <= sat_count[channel_idx] + 9'd1;
                            if (consec_sat[channel_idx] < 2'd3)
                                consec_sat[channel_idx] <= consec_sat[channel_idx] + 2'd1;
                        end else begin
                            consec_sat[channel_idx] <= 2'd0;
                        end

                        if (sample_count > 9'd0) begin
                            logic signed [15:0] delta;
                            delta = sample_in - prev_sample[channel_idx];
                            if (delta > 16'sd400 || delta < -16'sd400)
                                noise_count[channel_idx] <= noise_count[channel_idx] + 9'd1;
                        end
                        prev_sample[channel_idx] <= sample_in;

                        if (channel_idx == 4'd11) begin
                            if (sample_count == WINDOW_SIZE - 9'd1) begin
                                sample_count <= 9'd0;
                                eval_ch      <= 4'd0;
                                temp_mask    <= 12'd0;
                                temp_vcount  <= 4'd0;
                                eval_state   <= SQI_EVAL;
                            end else begin
                                sample_count <= sample_count + 9'd1;
                            end
                        end
                    end
                end

                SQI_EVAL: begin
                    // Sequential 1-channel per cycle validity evaluation
                    begin
                        logic is_valid;
                        logic [15:0] p2p;
                        p2p = max_val[eval_ch] - min_val[eval_ch];
                        is_valid = (p2p >= 16'd10) && (sat_count[eval_ch] < 9'd5) && (consec_sat[eval_ch] < 2'd3) && (noise_count[eval_ch] < 9'd5);

                        temp_mask[eval_ch] <= is_valid;
                        if (is_valid) temp_vcount <= temp_vcount + 4'd1;

                        // Reset channel accumulators
                        min_val[eval_ch]     <= 16'sh7FFF;
                        max_val[eval_ch]     <= -16'sh8000;
                        sat_count[eval_ch]   <= 9'd0;
                        noise_count[eval_ch] <= 9'd0;
                        consec_sat[eval_ch]  <= 2'd0;

                        if (eval_ch == 4'd11) begin
                            eval_ch    <= 4'd0;
                            temp_sel0  <= 4'd15;
                            temp_sel1  <= 4'd15;
                            temp_sel2  <= 4'd15;
                            eval_state <= SQI_RANK;
                        end else begin
                            eval_ch <= eval_ch + 4'd1;
                        end
                    end
                end

                SQI_RANK: begin
                    // Sequential ranking across 12 channels
                    if (temp_mask[eval_ch]) begin
                        if (temp_sel0 == 4'd15) temp_sel0 <= eval_ch;
                        else if (temp_sel1 == 4'd15) temp_sel1 <= eval_ch;
                        else if (temp_sel2 == 4'd15) temp_sel2 <= eval_ch;
                    end

                    if (eval_ch == 4'd11) begin
                        eval_state <= SQI_UPDATE;
                    end else begin
                        eval_ch <= eval_ch + 4'd1;
                    end
                end

                SQI_UPDATE: begin
                    lead_valid_mask   <= temp_mask;
                    valid_leads_count <= temp_vcount;
                    degraded_one_lead <= (temp_vcount == 4'd1);
                    signal_loss       <= (temp_vcount == 4'd0);

                    if (temp_sel0 != 4'd15) lead_idx_0 <= temp_sel0;
                    if (temp_sel1 != 4'd15) lead_idx_1 <= temp_sel1; else lead_idx_1 <= (temp_sel0 != 4'd15 ? temp_sel0 : 4'd1);
                    if (temp_sel2 != 4'd15) lead_idx_2 <= temp_sel2; else lead_idx_2 <= (temp_sel0 != 4'd15 ? temp_sel0 : 4'd1);

                    window_updated <= 1'b1;
                    eval_state     <= SQI_ACCUM;
                end
            endcase
        end
    end

endmodule
