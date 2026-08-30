`timescale 1ns / 1ps

// =============================================================================
// Module: qrs_detector_fixed
// Description: Multi-stage pipelined QRS complex detector. Isolates multiplier,
//              ring buffer MUXes, and threshold comparison for >50 MHz timing.
// =============================================================================

module qrs_detector_fixed (
    input  wire        clk,
    input  wire        rst_n,

    // Filtered Signal Input (from 5-25 Hz bandpass filter)
    input  wire        sample_valid,        // 250 Hz strobe
    input  wire signed [15:0] filt_sample,  // Filtered sample of primary lead
    input  wire [31:0] sample_time_ms,

    // QRS Detection Outputs
    output reg         qrs_valid,           // Pulse asserted on QRS detection
    output reg  [31:0] qrs_time_ms,         // Estimated R-peak timestamp
    output reg  [15:0] rr_interval_ms,      // Current RR interval (250..2000 ms)
    output reg  [7:0]  hr_bpm,              // Current estimated HR in bpm
    output reg         hr_valid             // HR valid flag
);

    // 1. Derivative Filter: [-1, -2, 0, 2, 1] / 8
    reg signed [15:0] d_buf [0:4];
    reg signed [15:0] deriv_out;

    // 2. Moving Window Integrator
    reg [31:0] mwi_ring [0:29];
    reg [4:0]  mwi_ptr;
    reg [31:0] mwi_sum;
    reg [31:0] sq_reg;
    reg [31:0] old_val_reg;

    // 3. Adaptive Threshold State (operating directly on sum)
    reg [31:0] spki_sum;              // Signal Peak Level Sum
    reg [31:0] npki_sum;              // Noise Peak Level Sum
    reg [31:0] threshold_i1;          // Primary Threshold
    reg [31:0] threshold_i2;          // Searchback Threshold

    // Timers & Refractory Counter
    reg [5:0]  refractory_cnt;        // 50 samples = 200 ms
    reg [15:0] samples_since_qrs;
    reg [15:0] searchback_limit;      // 1.66 * rr_avg

    // Recent 8 RR intervals
    reg [15:0] rr_history [0:7];
    reg [2:0]  rr_hist_ptr;
    reg [3:0]  valid_rr_count;

    // Pipelined Sample Processing Steps
    reg [1:0]  proc_step;
    reg [31:0] latched_time_ms;

    // Sequential Restoring Divider for Heart Rate (60000 / RR_ms)
    reg [4:0]  div_step;
    reg [31:0] div_num;
    reg [15:0] div_den;
    reg [15:0] div_quot;

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            qrs_valid          <= 1'b0;
            qrs_time_ms        <= 32'd0;
            rr_interval_ms     <= 16'd800;
            hr_bpm             <= 8'd75;
            hr_valid           <= 1'b0;

            deriv_out          <= 16'sd0;
            mwi_sum            <= 32'd0;
            mwi_ptr            <= 5'd0;
            sq_reg             <= 32'd0;
            old_val_reg        <= 32'd0;
            proc_step          <= 2'd0;
            latched_time_ms    <= 32'd0;

            spki_sum           <= 32'd1_500_000;
            npki_sum           <= 32'd150_000;
            threshold_i1       <= 32'd487_500;
            threshold_i2       <= 32'd243_750;

            refractory_cnt     <= 6'd0;
            samples_since_qrs  <= 16'd0;
            searchback_limit   <= 16'd332;
            rr_hist_ptr        <= 3'd0;
            valid_rr_count     <= 4'd0;

            div_step           <= 5'd0;
            div_num            <= 32'd0;
            div_den            <= 16'd1;
            div_quot           <= 16'd0;

            for (i = 0; i < 5; i = i + 1) d_buf[i] <= 16'sd0;
            for (i = 0; i < 30; i = i + 1) mwi_ring[i] <= 32'd0;
            for (i = 0; i < 8; i = i + 1) rr_history[i] <= 16'd800;
        end else begin
            qrs_valid <= 1'b0;

            // Sequential HR divider (16 cycles)
            if (div_step > 5'd0) begin
                div_step <= div_step - 5'd1;
                if (div_num >= ({16'd0, div_den} << (div_step - 1))) begin
                    div_num  <= div_num - ({16'd0, div_den} << (div_step - 1));
                    div_quot <= div_quot | (16'd1 << (div_step - 1));
                end
                if (div_step == 5'd1) begin
                    logic [15:0] final_quot;
                    final_quot = (div_num >= {16'd0, div_den}) ? (div_quot | 16'd1) : div_quot;
                    hr_bpm   <= (final_quot > 16'd220) ? 8'd220 : ((final_quot < 16'd30) ? 8'd30 : final_quot[7:0]);
                    hr_valid <= 1'b1;
                end
            end

            // Cycle 0: On sample_valid, update derivative and latch inputs
            if (sample_valid) begin
                d_buf[0] <= filt_sample;
                d_buf[1] <= d_buf[0];
                d_buf[2] <= d_buf[1];
                d_buf[3] <= d_buf[2];
                d_buf[4] <= d_buf[3];

                begin
                    logic signed [19:0] d_sum;
                    d_sum = (d_buf[0] + (d_buf[1] <<< 1) - d_buf[3] - (d_buf[4] <<< 1)) >>> 3;
                    deriv_out <= (d_sum > 20'sd32767) ? 16'sh7FFF : ((d_sum < -20'sd32768) ? -16'sh8000 : d_sum[15:0]);
                end

                latched_time_ms <= sample_time_ms;
                old_val_reg     <= mwi_ring[mwi_ptr];
                proc_step       <= 2'd1;

                if (refractory_cnt > 6'd0)
                    refractory_cnt <= refractory_cnt - 6'd1;

                samples_since_qrs <= samples_since_qrs + 16'd1;
            end else if (proc_step == 2'd1) begin
                // Cycle 1: Compute square of derivative
                sq_reg    <= deriv_out * deriv_out;
                proc_step <= 2'd2;
            end else if (proc_step == 2'd2) begin
                // Cycle 2: Update MWI accumulator and ring buffer
                mwi_ring[mwi_ptr] <= sq_reg;
                mwi_sum           <= mwi_sum + sq_reg - old_val_reg;
                mwi_ptr           <= (mwi_ptr == 5'd29) ? 5'd0 : mwi_ptr + 5'd1;
                proc_step         <= 2'd3;
            end else if (proc_step == 2'd3) begin
                // Cycle 3: Threshold check and QRS detection
                proc_step <= 2'd0;

                if (refractory_cnt == 6'd0) begin
                    if (mwi_sum > threshold_i1) begin
                        // QRS Complex Detected!
                        qrs_valid   <= 1'b1;
                        qrs_time_ms <= latched_time_ms;

                        begin
                            logic [15:0] current_rr_ms;
                            current_rr_ms = samples_since_qrs <<< 2;
                            if (current_rr_ms >= 16'd250 && current_rr_ms <= 16'd2000) begin
                                rr_interval_ms <= current_rr_ms;
                                rr_history[rr_hist_ptr] <= current_rr_ms;
                                rr_hist_ptr <= rr_hist_ptr + 3'd1;
                                if (valid_rr_count < 4'd8) valid_rr_count <= valid_rr_count + 4'd1;

                                div_num  <= 32'd60000;
                                div_den  <= current_rr_ms;
                                div_quot <= 16'd0;
                                div_step <= 5'd16;
                            end
                        end

                        spki_sum     <= (mwi_sum >>> 3) + (spki_sum - (spki_sum >>> 3));
                        threshold_i1 <= npki_sum + (((mwi_sum >>> 3) + (spki_sum - (spki_sum >>> 3)) - npki_sum) >>> 2);
                        threshold_i2 <= (npki_sum + (((mwi_sum >>> 3) + (spki_sum - (spki_sum >>> 3)) - npki_sum) >>> 2)) >>> 1;

                        refractory_cnt    <= 6'd50;
                        samples_since_qrs <= 16'd0;
                    end else if (samples_since_qrs > searchback_limit && mwi_sum > threshold_i2) begin
                        qrs_valid   <= 1'b1;
                        qrs_time_ms <= latched_time_ms;

                        spki_sum     <= (mwi_sum >>> 2) + (spki_sum - (spki_sum >>> 2));
                        threshold_i1 <= npki_sum + (((mwi_sum >>> 2) + (spki_sum - (spki_sum >>> 2)) - npki_sum) >>> 2);
                        threshold_i2 <= (npki_sum + (((mwi_sum >>> 2) + (spki_sum - (spki_sum >>> 2)) - npki_sum) >>> 2)) >>> 1;

                        refractory_cnt    <= 6'd50;
                        samples_since_qrs <= 16'd0;
                    end else begin
                        npki_sum     <= (mwi_sum >>> 3) + (npki_sum - (npki_sum >>> 3));
                        threshold_i1 <= (npki_sum + (mwi_sum >>> 3) - (npki_sum >>> 3)) + ((spki_sum - npki_sum) >>> 2);
                        threshold_i2 <= ((npki_sum + (mwi_sum >>> 3) - (npki_sum >>> 3)) + ((spki_sum - npki_sum) >>> 2)) >>> 1;
                    end
                end

                if (samples_since_qrs > 16'd750) begin
                    hr_valid <= 1'b0;
                end
            end
        end
    end

endmodule
