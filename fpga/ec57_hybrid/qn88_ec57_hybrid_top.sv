`timescale 1ns / 1ps

// =============================================================================
// Top-Level Module: qn88_ec57_hybrid_top
// Description: Twelve-Lead ECG EC57 Hybrid AI & DSP Processing Pipeline for
//              Sipeed Tang Nano 20K (Gowin GW2AR-LV18QN88C8/I7).
//
// Pipeline Architecture:
//   1. UART Rx Protocol: Receives 250 Hz 12-lead synchronized ECG frames (32 bytes).
//   2. SQI & Lead Selector: Monitors 12 leads, ranks signal quality, detects flatline/rail/noise.
//   3. Time-Shared Biquad Filters: 0.5-40 Hz morphology & 5-25 Hz QRS bandpass.
//   4. QRS & HR Detector: Pan-Tompkins MWI, dual adaptive thresholds, 200 ms refractory.
//   5. Beat Window Buffer: Synchronous 512x16 BSRAM ring storing 160-point beat windows.
//   6. INT8 CNN Core: 1.6k parameter NN executing Conv1->Conv2->Conv3->GAP->FC.
//   7. Rhythm Engine: Real-time deterministic state machine (Brady, Tachy, Asystole, VT, Bigeminy).
//   8. UART Tx Telemetry: Transmits diagnostic packets to host PC.
// =============================================================================

module qn88_ec57_hybrid_top #(
    parameter CLK_FREQ_HZ      = 27_000_000,
    parameter BAUD_RATE        = 115_200,
    parameter WEIGHTS_HEX_FILE = "weights_int8.hex",
    parameter PARAMS_HEX_FILE  = "params_int32.hex"
)(
    input  wire        clk,        // Pin 4 (27 MHz onboard oscillator)
    input  wire        rst_n,      // Pin 88 (Active-low reset key)

    // COM10 UART Interface (115200 8-N-1)
    input  wire        uart_rx,    // Pin 70 (FPGA RX from host)
    output wire        uart_tx,    // Pin 69 (FPGA TX to host)

    // Board Status Diagnostic LEDs
    output reg         led_heartbeat,  // Toggles every second
    output reg         led_qrs,        // Flashes on QRS detection
    output reg         led_veb,        // Flashes on VEB beat
    output reg         led_arrhythmia, // Lights up on active arrhythmia event
    output reg         led_sig_loss,   // Lights up on signal loss
    output reg         led_uart_act    // Flashes on UART frame reception
);

    // -------------------------------------------------------------------------
    // 1. UART Protocol Module
    // -------------------------------------------------------------------------
    wire        rx_sample_valid;
    wire [31:0] rx_sample_index;
    wire [31:0] rx_sample_time_ms;
    wire signed [15:0] rx_lead_samples [0:11];

    reg         tx_telemetry_valid;
    reg  [31:0] tx_sample_index;
    reg  [31:0] tx_timestamp_ms;
    reg  [3:0]  tx_valid_leads;
    reg  [7:0]  tx_hr_bpm;
    reg         tx_hr_valid;
    reg         tx_qrs_valid;
    reg  [1:0]  tx_beat_class;
    reg  signed [31:0] tx_logit_non_veb;
    reg  signed [31:0] tx_logit_veb;
    reg  [7:0]  tx_active_rhythms;
    reg  [15:0] tx_crc_err_count;
    wire        tx_busy;

    ec57_uart_protocol #(
        .CLK_FREQ_HZ(CLK_FREQ_HZ),
        .BAUD_RATE(BAUD_RATE)
    ) u_uart (
        .clk(clk),
        .rst_n(rst_n),
        .uart_rx(uart_rx),
        .uart_tx(uart_tx),
        .rx_sample_valid(rx_sample_valid),
        .rx_sample_index(rx_sample_index),
        .rx_sample_time_ms(rx_sample_time_ms),
        .rx_lead_samples(rx_lead_samples),
        .tx_telemetry_valid(tx_telemetry_valid),
        .tx_sample_index(tx_sample_index),
        .tx_timestamp_ms(tx_timestamp_ms),
        .tx_valid_leads(tx_valid_leads),
        .tx_hr_bpm(tx_hr_bpm),
        .tx_hr_valid(tx_hr_valid),
        .tx_qrs_valid(tx_qrs_valid),
        .tx_beat_class(tx_beat_class),
        .tx_logit_non_veb(tx_logit_non_veb),
        .tx_logit_veb(tx_logit_veb),
        .tx_active_rhythms(tx_active_rhythms),
        .tx_crc_err_count(tx_crc_err_count),
        .tx_busy(tx_busy)
    );

    // -------------------------------------------------------------------------
    // 2. Multi-Lead SQI Selection
    // -------------------------------------------------------------------------
    wire        sqi_updated;
    wire [3:0]  sqi_valid_leads;
    wire [3:0]  sel_lead_0, sel_lead_1, sel_lead_2;
    wire        sqi_degraded_one;
    wire        sqi_signal_loss;

    // Sequential channel feeder for SQI evaluator
    reg [3:0]   sqi_feed_ch;
    reg         sqi_feed_valid;
    reg signed [15:0] sqi_feed_sample;

    lead_sqi_select u_sqi (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sqi_feed_valid),
        .channel_idx(sqi_feed_ch),
        .sample_in(sqi_feed_sample),
        .window_updated(sqi_updated),
        .valid_leads_count(sqi_valid_leads),
        .lead_idx_0(sel_lead_0),
        .lead_idx_1(sel_lead_1),
        .lead_idx_2(sel_lead_2),
        .degraded_one_lead(sqi_degraded_one),
        .signal_loss(sqi_signal_loss)
    );

    // -------------------------------------------------------------------------
    // 3. Time-Shared Biquad Filters (QRS 5-25 Hz Bandpass)
    // -------------------------------------------------------------------------
    // Standard Butterworth 5-25 Hz Biquad Coefficients @ 250 Hz in Q2.14
    localparam signed [15:0] QRS_S1_B0 = 16'sh0A5B;
    localparam signed [15:0] QRS_S1_B1 = 16'sh0000;
    localparam signed [15:0] QRS_S1_B2 = -16'sh0A5B;
    localparam signed [15:0] QRS_S1_A1 = -16'sh3521;
    localparam signed [15:0] QRS_S1_A2 = 16'sh1640;

    localparam signed [15:0] QRS_S2_B0 = 16'sh4000;
    localparam signed [15:0] QRS_S2_B1 = 16'sh0000;
    localparam signed [15:0] QRS_S2_B2 = -16'sh4000;
    localparam signed [15:0] QRS_S2_A1 = -16'sh38A2;
    localparam signed [15:0] QRS_S2_A2 = 16'sh1CD8;

    wire        filt_out_valid;
    wire [3:0]  filt_out_ch;
    wire signed [15:0] filt_out_sample;

    ecg_biquad_timeshare #(
        .NUM_CHANNELS(12),
        .S1_B0(QRS_S1_B0), .S1_B1(QRS_S1_B1), .S1_B2(QRS_S1_B2), .S1_A1(QRS_S1_A1), .S1_A2(QRS_S1_A2),
        .S2_B0(QRS_S2_B0), .S2_B1(QRS_S2_B1), .S2_B2(QRS_S2_B2), .S2_A1(QRS_S2_A1), .S2_A2(QRS_S2_A2)
    ) u_biquad (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sqi_feed_valid),
        .channel_idx(sqi_feed_ch),
        .sample_in(sqi_feed_sample),
        .sample_out_valid(filt_out_valid),
        .sample_out_channel(filt_out_ch),
        .sample_out(filt_out_sample)
    );

    // -------------------------------------------------------------------------
    // 4. Fixed-Point QRS Detector
    // -------------------------------------------------------------------------
    wire        qrs_detected;
    wire [31:0] qrs_peak_time_ms;
    wire [15:0] det_rr_interval_ms;
    wire [7:0]  det_hr_bpm;
    wire        det_hr_valid;

    qrs_detector_fixed u_qrs_det (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(filt_out_valid && (filt_out_ch == sel_lead_0)),
        .filt_sample(filt_out_sample),
        .sample_time_ms(rx_sample_time_ms),
        .qrs_valid(qrs_detected),
        .qrs_time_ms(qrs_peak_time_ms),
        .rr_interval_ms(det_rr_interval_ms),
        .hr_bpm(det_hr_bpm),
        .hr_valid(det_hr_valid)
    );

    // -------------------------------------------------------------------------
    // 5. Beat Window Buffer (512-sample synchronous ring buffer)
    // -------------------------------------------------------------------------
    wire        window_valid;
    wire signed [15:0] window_data;
    wire [7:0]  window_point_idx;
    wire        window_done;

    // Normalization from signed 16-bit to signed 8-bit
    wire signed [7:0] cnn_wave_in = (window_data > 16'sd127) ? 8'sd127 : ((window_data < -16'sd128) ? -8'sd128 : window_data[7:0]);

    beat_window_buffer #(
        .SAMPLE_WIDTH(16),
        .INDEX_WIDTH(32),
        .RAM_DEPTH(512),
        .PENDING_DEPTH(4)
    ) u_beat_buf (
        .clk(clk),
        .rst_n(rst_n),
        .sample_data(rx_lead_samples[sel_lead_0]),
        .sample_index(rx_sample_index),
        .sample_valid(rx_sample_valid),
        .qrs_sample_index(rx_sample_index),
        .qrs_valid(qrs_detected),
        .window_valid(window_valid),
        .window_data(window_data),
        .window_point_index(window_point_idx),
        .window_sample_index(),
        .window_r_sample_index(),
        .window_start(),
        .window_center(),
        .window_done(window_done),
        .missing_sample_sticky(),
        .duplicate_sample_sticky(),
        .out_of_order_sample_sticky(),
        .queue_overflow_sticky(),
        .stale_window_sticky(),
        .qrs_reference_error_sticky(),
        .missing_sample_count(),
        .duplicate_sample_count(),
        .out_of_order_sample_count(),
        .warmup_drop_count(),
        .queue_overflow_count(),
        .stale_window_count(),
        .qrs_reference_error_count(),
        .pending_count()
    );

    // -------------------------------------------------------------------------
    // 6. INT8 CNN Inference Accelerator Core
    // -------------------------------------------------------------------------
    wire        cnn_busy;
    wire        cnn_done;
    wire signed [31:0] cnn_logit_non_veb;
    wire signed [31:0] cnn_logit_veb;
    wire [1:0]  cnn_beat_class;
    wire [31:0] cnn_cycles;

    nv_cnn_core #(
        .WEIGHTS_HEX_FILE(WEIGHTS_HEX_FILE),
        .PARAMS_HEX_FILE(PARAMS_HEX_FILE)
    ) u_cnn (
        .clk(clk),
        .rst_n(rst_n),
        .start(window_done),
        .busy(cnn_busy),
        .done(cnn_done),
        .wave_wr_valid(window_valid),
        .wave_wr_addr(window_point_idx),
        .wave_wr_data(cnn_wave_in),
        .feat_pre_rr(8'sd0),       // Default normalized features
        .feat_qrs_width(8'sd0),
        .feat_peak_ratio(8'sd0),
        .feat_sqi(8'sd30),
        .logit_non_veb(cnn_logit_non_veb),
        .logit_veb(cnn_logit_veb),
        .beat_class(cnn_beat_class),
        .cycle_count(cnn_cycles)
    );

    // -------------------------------------------------------------------------
    // 7. Deterministic Rhythm Event State Machine
    // -------------------------------------------------------------------------
    wire point_sig_loss, point_brady, point_tachy, point_asystole;
    wire point_couplet, point_vrun, point_vt, point_bigeminy, point_trigeminy;
    wire act_sig_loss, act_brady, act_tachy, act_asystole;
    wire act_vrun, act_vt, act_bigeminy, act_trigeminy;
    wire rhythm_ok;

    rhythm_engine u_rhythm (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(rx_sample_valid),
        .sample_time_ms(rx_sample_time_ms),
        .valid_lead_count(sqi_valid_leads),
        .hr_valid(det_hr_valid),
        .hr_bpm(det_hr_bpm),
        .qrs_valid(cnn_done),       // Synchronized with classified beat
        .beat_class(cnn_beat_class),
        .point_signal_loss(point_sig_loss),
        .point_brady(point_brady),
        .point_tachy(point_tachy),
        .point_asystole(point_asystole),
        .point_pvc_couplet(point_couplet),
        .point_ventricular_run(point_vrun),
        .point_vt_candidate(point_vt),
        .point_bigeminy(point_bigeminy),
        .point_trigeminy(point_trigeminy),
        .active_signal_loss(act_sig_loss),
        .active_brady(act_brady),
        .active_tachy(act_tachy),
        .active_asystole(act_asystole),
        .active_ventricular_run(act_vrun),
        .active_vt(act_vt),
        .active_bigeminy(act_bigeminy),
        .active_trigeminy(act_trigeminy),
        .status_ok(rhythm_ok)
    );

    // -------------------------------------------------------------------------
    // Sequential Channel Feeding Logic (Feeds 12 leads to SQI/Filter on RX)
    // -------------------------------------------------------------------------
    reg [3:0] feed_counter;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            feed_counter      <= 4'd0;
            sqi_feed_valid    <= 1'b0;
            sqi_feed_ch       <= 4'd0;
            sqi_feed_sample   <= 16'sd0;
            tx_telemetry_valid<= 1'b0;
        end else begin
            sqi_feed_valid     <= 1'b0;
            tx_telemetry_valid <= 1'b0;

            if (rx_sample_valid) begin
                feed_counter <= 4'd1;
                sqi_feed_ch     <= 4'd0;
                sqi_feed_sample <= rx_lead_samples[0];
                sqi_feed_valid  <= 1'b1;
            end else if (feed_counter > 4'd0 && feed_counter <= 4'd11) begin
                sqi_feed_ch     <= feed_counter;
                sqi_feed_sample <= rx_lead_samples[feed_counter];
                sqi_feed_valid  <= 1'b1;
                feed_counter    <= feed_counter + 4'd1;
            end else if (feed_counter == 4'd12) begin
                feed_counter <= 4'd0;
            end

            // Trigger Telemetry TX on CNN classification or QRS
            if (cnn_done && !tx_busy) begin
                tx_telemetry_valid <= 1'b1;
                tx_sample_index    <= rx_sample_index;
                tx_timestamp_ms    <= rx_sample_time_ms;
                tx_valid_leads     <= sqi_valid_leads;
                tx_hr_bpm          <= det_hr_bpm;
                tx_hr_valid        <= det_hr_valid;
                tx_qrs_valid       <= 1'b1;
                tx_beat_class      <= cnn_beat_class;
                tx_logit_non_veb   <= cnn_logit_non_veb;
                tx_logit_veb       <= cnn_logit_veb;
                tx_active_rhythms  <= {act_trigeminy, act_bigeminy, act_vt, act_vrun, act_asystole, act_tachy, act_brady, act_sig_loss};
                tx_crc_err_count   <= 16'd0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Diagnostic LEDs
    // -------------------------------------------------------------------------
    reg [24:0] hb_counter;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hb_counter     <= 25'd0;
            led_heartbeat  <= 1'b0;
            led_qrs        <= 1'b0;
            led_veb        <= 1'b0;
            led_arrhythmia <= 1'b0;
            led_sig_loss   <= 1'b0;
            led_uart_act   <= 1'b0;
        end else begin
            // 1 Hz Heartbeat toggle (27,000,000 / 2 = 13,500,000)
            if (hb_counter == 25'd13_500_000) begin
                hb_counter    <= 25'd0;
                led_heartbeat <= ~led_heartbeat;
            end else begin
                hb_counter <= hb_counter + 25'd1;
            end

            if (qrs_detected) led_qrs <= 1'b1;
            else if (hb_counter[18:0] == 19'd0) led_qrs <= 1'b0;

            if (cnn_done && cnn_beat_class == 2'b01) led_veb <= 1'b1;
            else if (hb_counter[18:0] == 19'd0) led_veb <= 1'b0;

            led_arrhythmia <= act_brady | act_tachy | act_asystole | act_vrun | act_vt | act_bigeminy | act_trigeminy;
            led_sig_loss   <= act_sig_loss;

            if (rx_sample_valid) led_uart_act <= 1'b1;
            else if (hb_counter[16:0] == 17'd0) led_uart_act <= 1'b0;
        end
    end

endmodule
