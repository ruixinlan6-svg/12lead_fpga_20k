`timescale 1ns / 1ps

// =============================================================================
// Module: rhythm_engine
// Description: Pure-integer deterministic ECG rhythm event state machine for
//              QN88 Twelve-Lead FPGA.
//
// Complies with:
//   - docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md (Section 1.4)
//   - train/ec57/rhythm_engine.py
//
// Implements:
//   1. Bradycardia Candidate (HR < 50 bpm for >= 10 s; cleared if HR >= 55 for >= 5 s)
//   2. Tachycardia Candidate (HR > 100 bpm for >= 10 s; cleared if HR <= 95 for >= 5 s)
//   3. Asystole Candidate (No valid QRS for >= 3.0 s while valid_leads > 0)
//   4. PVC Couplet (Exactly 2 consecutive VEBs)
//   5. Ventricular Run (>= 3 consecutive VEBs)
//   6. VT Candidate (Ventricular Run with median V-V RR <= 600 ms / >= 100 bpm)
//   7. Bigeminy Candidate (nonV, V pattern x3 = 6 beats; cleared after 2 consecutive violations)
//   8. Trigeminy Candidate (nonV, nonV, V pattern x3 = 9 beats; cleared after 2 violations)
//   9. Signal Loss (valid_lead_count == 0)
// =============================================================================

module rhythm_engine (
    input  wire        clk,
    input  wire        rst_n,
    
    // Sample / Strobe Interface
    input  wire        sample_valid,        // Strobe indicating new sample / timestamp
    input  wire [31:0] sample_time_ms,      // Current integer millisecond timestamp
    input  wire [3:0]  valid_lead_count,    // Number of active leads (0..12)
    input  wire        hr_valid,            // HR valid flag
    input  wire [7:0]  hr_bpm,              // Current HR in bpm (30..220)
    
    // Beat Interface (Synchronous with QRS occurrence)
    input  wire        qrs_valid,           // Pulse asserted when a QRS beat is detected
    input  wire [1:0]  beat_class,          // 2'b00: non-VEB ('nonV'), 2'b01: VEB ('V'), 2'b10: Unclassified
    
    // Point Events (1-cycle pulse upon event detection)
    output reg         point_signal_loss,
    output reg         point_brady,
    output reg         point_tachy,
    output reg         point_asystole,
    output reg         point_pvc_couplet,
    output reg         point_ventricular_run,
    output reg         point_vt_candidate,
    output reg         point_bigeminy,
    output reg         point_trigeminy,
    
    // Active State Levels (Continuous status)
    output reg         active_signal_loss,
    output reg         active_brady,
    output reg         active_tachy,
    output reg         active_asystole,
    output reg         active_ventricular_run,
    output reg         active_vt,
    output reg         active_bigeminy,
    output reg         active_trigeminy,
    
    // Status Output
    output reg         status_ok
);

    localparam [31:0] BRADY_ASSERT_MS    = 32'd10000;
    localparam [31:0] BRADY_CLEAR_MS     = 32'd5000;
    localparam [31:0] TACHY_ASSERT_MS    = 32'd10000;
    localparam [31:0] TACHY_CLEAR_MS     = 32'd5000;
    localparam [31:0] ASYSTOLE_ASSERT_MS = 32'd3000;
    localparam [31:0] VT_LIMIT_RR_MS     = 32'd600;

    // -------------------------------------------------------------------------
    // Internal State Registers
    // -------------------------------------------------------------------------
    reg        valid_leads_active;
    reg [31:0] valid_leads_since_ms;
    reg [31:0] last_qrs_time_ms;
    reg        last_qrs_valid;

    // HR Brady / Tachy Timers & Has-Since flags
    reg [31:0] brady_assert_since_ms;
    reg        brady_assert_has_since;
    reg [31:0] brady_clear_since_ms;
    reg        brady_clear_has_since;

    reg [31:0] tachy_assert_since_ms;
    reg        tachy_assert_has_since;
    reg [31:0] tachy_clear_since_ms;
    reg        tachy_clear_has_since;

    // Ventricular event tracking
    reg [3:0]  consecutive_v;
    reg [31:0] v_time_0, v_time_1, v_time_2, v_time_3, v_time_4, v_time_5;

    // Periodic Patterns (Shift register of recent 9 beats: 1=V, 0=nonV/unclassified)
    reg [8:0]  recent_beats;
    reg [2:0]  bigeminy_phase;
    reg [1:0]  bigeminy_violations;
    reg [3:0]  trigeminy_phase;
    reg [1:0]  trigeminy_violations;

    // -------------------------------------------------------------------------
    // Pattern Definitions
    // -------------------------------------------------------------------------
    // Bigeminy: nonV, V, nonV, V, nonV, V -> bit pattern {0, 1, 0, 1, 0, 1} = 6'b010101
    // In shift reg (MSB oldest, LSB newest): 6'b010101
    localparam [5:0] BIGEMINY_TARGET  = 6'b010101;
    // Trigeminy: nonV, nonV, V, nonV, nonV, V, nonV, nonV, V -> {0,0,1, 0,0,1, 0,0,1} = 9'b001001001
    localparam [8:0] TRIGEMINY_TARGET = 9'b001001001;

    // Expected next beat for active pattern phase
    function automatic logic exp_bigeminy_beat(input [2:0] phase);
        // Phase: 0:nonV(0), 1:V(1), 2:nonV(0), 3:V(1), 4:nonV(0), 5:V(1)
        return phase[0];
    endfunction

    function automatic logic exp_trigeminy_beat(input [3:0] phase);
        // Phase: 0:nonV(0), 1:nonV(0), 2:V(1), 3:nonV(0), 4:nonV(0), 5:V(1), 6:nonV(0), 7:nonV(0), 8:V(1)
        return (phase == 4'd2 || phase == 4'd5 || phase == 4'd8);
    endfunction

    // Median V-V interval check for runs
    function automatic logic check_vt_qualify(
        input [3:0]  count,
        input [31:0] t0, t1, t2, t3
    );
        logic [31:0] rr0, rr1, rr2;
        logic [31:0] med_rr;
        begin
            if (count < 4'd3) begin
                check_vt_qualify = 1'b0;
            end else if (count == 4'd3) begin
                // 2 intervals: (t0-t1) and (t1-t2). Even count=2 -> sum <= 2*600
                rr0 = t0 - t1;
                rr1 = t1 - t2;
                check_vt_qualify = ((rr0 + rr1) <= (2 * VT_LIMIT_RR_MS));
            end else begin
                // >= 4 beats -> at least 3 intervals: rr0, rr1, rr2
                rr0 = t0 - t1;
                rr1 = t1 - t2;
                rr2 = t2 - t3;
                // Median of 3 values
                if ((rr0 <= rr1 && rr1 <= rr2) || (rr2 <= rr1 && rr1 <= rr0))
                    med_rr = rr1;
                else if ((rr1 <= rr0 && rr0 <= rr2) || (rr2 <= rr0 && rr0 <= rr1))
                    med_rr = rr0;
                else
                    med_rr = rr2;
                check_vt_qualify = (med_rr <= VT_LIMIT_RR_MS);
            end
        end
    endfunction

    // -------------------------------------------------------------------------
    // Main Sequential State Machine
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset outputs
            point_signal_loss      <= 1'b0;
            point_brady            <= 1'b0;
            point_tachy            <= 1'b0;
            point_asystole         <= 1'b0;
            point_pvc_couplet      <= 1'b0;
            point_ventricular_run  <= 1'b0;
            point_vt_candidate     <= 1'b0;
            point_bigeminy         <= 1'b0;
            point_trigeminy        <= 1'b0;

            active_signal_loss     <= 1'b0;
            active_brady           <= 1'b0;
            active_tachy           <= 1'b0;
            active_asystole        <= 1'b0;
            active_ventricular_run <= 1'b0;
            active_vt              <= 1'b0;
            active_bigeminy        <= 1'b0;
            active_trigeminy       <= 1'b0;

            status_ok              <= 1'b1;

            // Reset internal state
            valid_leads_active     <= 1'b0;
            valid_leads_since_ms   <= 32'd0;
            last_qrs_time_ms       <= 32'd0;
            last_qrs_valid         <= 1'b0;

            brady_assert_since_ms  <= 32'd0;
            brady_assert_has_since <= 1'b0;
            brady_clear_since_ms   <= 32'd0;
            brady_clear_has_since  <= 1'b0;

            tachy_assert_since_ms  <= 32'd0;
            tachy_assert_has_since <= 1'b0;
            tachy_clear_since_ms   <= 32'd0;
            tachy_clear_has_since  <= 1'b0;

            consecutive_v          <= 4'd0;
            v_time_0               <= 32'd0;
            v_time_1               <= 32'd0;
            v_time_2               <= 32'd0;
            v_time_3               <= 32'd0;
            v_time_4               <= 32'd0;
            v_time_5               <= 32'd0;

            recent_beats           <= 9'd0;
            bigeminy_phase         <= 3'd0;
            bigeminy_violations    <= 2'd0;
            trigeminy_phase        <= 4'd0;
            trigeminy_violations   <= 2'd0;
        end else begin
            // Clear single-cycle point event pulses by default every clock cycle
            point_signal_loss     <= 1'b0;
            point_brady           <= 1'b0;
            point_tachy           <= 1'b0;
            point_asystole        <= 1'b0;
            point_pvc_couplet     <= 1'b0;
            point_ventricular_run <= 1'b0;
            point_vt_candidate    <= 1'b0;
            point_bigeminy        <= 1'b0;
            point_trigeminy       <= 1'b0;

            // -----------------------------------------------------------------
            // 1. Sample / Continuous Time-driven Processing
            // -----------------------------------------------------------------
            if (sample_valid) begin
                if (valid_lead_count == 4'd0) begin
                    if (!active_signal_loss) begin
                        point_signal_loss <= 1'b1;
                    end
                    active_signal_loss     <= 1'b1;
                    valid_leads_active     <= 1'b0;
                    status_ok              <= 1'b0;

                    // Clear all active temporal arrhythmia states on signal loss
                    active_brady           <= 1'b0;
                    active_tachy           <= 1'b0;
                    active_asystole        <= 1'b0;
                    active_ventricular_run <= 1'b0;
                    active_vt              <= 1'b0;
                    active_bigeminy        <= 1'b0;
                    active_trigeminy       <= 1'b0;

                    brady_assert_has_since <= 1'b0;
                    brady_clear_has_since  <= 1'b0;
                    tachy_assert_has_since <= 1'b0;
                    tachy_clear_has_since  <= 1'b0;

                    consecutive_v          <= 4'd0;
                    recent_beats           <= 9'd0;
                    last_qrs_valid         <= 1'b0;
                end else begin
                    // Signal is present (valid_lead_count >= 1)
                    active_signal_loss <= 1'b0;
                    status_ok          <= 1'b1;

                    if (!valid_leads_active) begin
                        valid_leads_active   <= 1'b1;
                        valid_leads_since_ms <= sample_time_ms;
                    end

                    // ---------------------------------------------------------
                    // 2. Heart Rate Processing (Bradycardia & Tachycardia)
                    // ---------------------------------------------------------
                    if (hr_valid && (hr_bpm >= 8'd30 && hr_bpm <= 8'd220)) begin
                        // --- Bradycardia FSM ---
                        if (!active_brady) begin
                            brady_clear_has_since <= 1'b0;
                            if (hr_bpm < 8'd50) begin
                                if (!brady_assert_has_since) begin
                                    brady_assert_since_ms  <= sample_time_ms;
                                    brady_assert_has_since <= 1'b1;
                                end else if (sample_time_ms - brady_assert_since_ms >= BRADY_ASSERT_MS) begin
                                    active_brady           <= 1'b1;
                                    point_brady            <= 1'b1;
                                    brady_assert_has_since <= 1'b0;
                                end
                            end else begin
                                brady_assert_has_since <= 1'b0;
                            end
                        end else begin
                            // Active Bradycardia: clear when HR >= 55 for >= 5 s
                            brady_assert_has_since <= 1'b0;
                            if (hr_bpm >= 8'd55) begin
                                if (!brady_clear_has_since) begin
                                    brady_clear_since_ms  <= sample_time_ms;
                                    brady_clear_has_since <= 1'b1;
                                end else if (sample_time_ms - brady_clear_since_ms >= BRADY_CLEAR_MS) begin
                                    active_brady          <= 1'b0;
                                    brady_clear_has_since <= 1'b0;
                                end
                            end else begin
                                brady_clear_has_since <= 1'b0;
                            end
                        end

                        // --- Tachycardia FSM ---
                        if (!active_tachy) begin
                            tachy_clear_has_since <= 1'b0;
                            if (hr_bpm > 8'd100) begin
                                if (!tachy_assert_has_since) begin
                                    tachy_assert_since_ms  <= sample_time_ms;
                                    tachy_assert_has_since <= 1'b1;
                                end else if (sample_time_ms - tachy_assert_since_ms >= TACHY_ASSERT_MS) begin
                                    active_tachy           <= 1'b1;
                                    point_tachy            <= 1'b1;
                                    tachy_assert_has_since <= 1'b0;
                                end
                            end else begin
                                tachy_assert_has_since <= 1'b0;
                            end
                        end else begin
                            // Active Tachycardia: clear when HR <= 95 for >= 5 s
                            tachy_assert_has_since <= 1'b0;
                            if (hr_bpm <= 8'd95) begin
                                if (!tachy_clear_has_since) begin
                                    tachy_clear_since_ms  <= sample_time_ms;
                                    tachy_clear_has_since <= 1'b1;
                                end else if (sample_time_ms - tachy_clear_since_ms >= TACHY_CLEAR_MS) begin
                                    active_tachy          <= 1'b0;
                                    tachy_clear_has_since <= 1'b0;
                                end
                            end else begin
                                tachy_clear_has_since <= 1'b0;
                            end
                        end
                    end else begin
                        // HR is invalid: clear pending assertion/clearing timers
                        brady_assert_has_since <= 1'b0;
                        brady_clear_has_since  <= 1'b0;
                        tachy_assert_has_since <= 1'b0;
                        tachy_clear_has_since  <= 1'b0;
                    end

                    // ---------------------------------------------------------
                    // 3. Asystole Check (>= 3.0 s without QRS)
                    // ---------------------------------------------------------
                    if (!active_asystole) begin
                        if (last_qrs_valid) begin
                            if (sample_time_ms - last_qrs_time_ms >= ASYSTOLE_ASSERT_MS) begin
                                active_asystole <= 1'b1;
                                point_asystole  <= 1'b1;
                            end
                        end else if (valid_leads_active) begin
                            if (sample_time_ms - valid_leads_since_ms >= ASYSTOLE_ASSERT_MS) begin
                                active_asystole <= 1'b1;
                                point_asystole  <= 1'b1;
                            end
                        end
                    end
                end
            end

            // -----------------------------------------------------------------
            // 4. Beat Processing (QRS Events & Ectopic Patterns)
            //    Evaluated whenever qrs_valid pulses, regardless of sample_valid cycle
            // -----------------------------------------------------------------
            if (qrs_valid && !active_signal_loss) begin
                last_qrs_time_ms <= sample_time_ms;
                last_qrs_valid   <= 1'b1;
                active_asystole  <= 1'b0;

                // Classify beat
                if (beat_class == 2'b01) begin
                    // --- VEB ('V') ---
                    v_time_5 <= v_time_4;
                    v_time_4 <= v_time_3;
                    v_time_3 <= v_time_2;
                    v_time_2 <= v_time_1;
                    v_time_1 <= v_time_0;
                    v_time_0 <= sample_time_ms;

                    if (consecutive_v < 4'd15)
                        consecutive_v <= consecutive_v + 4'd1;

                    if (consecutive_v == 4'd1) begin
                        // Exactly 2 consecutive VEBs -> PVC Couplet
                        point_pvc_couplet <= 1'b1;
                    end else if (consecutive_v >= 4'd2) begin
                        // >= 3 consecutive VEBs -> Ventricular Run
                        if (!active_ventricular_run) begin
                            point_ventricular_run <= 1'b1;
                        end
                        active_ventricular_run <= 1'b1;

                        // VT candidate qualification (median RR <= 600 ms)
                        if (check_vt_qualify(consecutive_v + 4'd1, sample_time_ms, v_time_0, v_time_1, v_time_2)) begin
                            if (!active_vt) point_vt_candidate <= 1'b1;
                            active_vt <= 1'b1;
                        end else begin
                            active_vt <= 1'b0;
                        end
                    end
                end else begin
                    // --- Non-VEB or Unclassified ('nonV' / 'N') ---
                    consecutive_v          <= 4'd0;
                    active_ventricular_run <= 1'b0;
                    active_vt              <= 1'b0;
                end

                // Update periodic patterns shift register
                recent_beats <= {recent_beats[7:0], (beat_class == 2'b01)};

                // --- Bigeminy State Tracking ---
                if (active_bigeminy) begin
                    if ((beat_class == 2'b01) == exp_bigeminy_beat(bigeminy_phase)) begin
                        bigeminy_violations <= 2'd0;
                        bigeminy_phase      <= (bigeminy_phase == 3'd5) ? 3'd0 : bigeminy_phase + 3'd1;
                    end else begin
                        if (bigeminy_violations >= 2'd1) begin
                            active_bigeminy     <= 1'b0;
                            bigeminy_phase      <= 3'd0;
                            bigeminy_violations <= 2'd0;
                        end else begin
                            bigeminy_violations <= 2'd1;
                            bigeminy_phase      <= (bigeminy_phase == 3'd5) ? 3'd0 : bigeminy_phase + 3'd1;
                        end
                    end
                end else begin
                    // Check if newest 6 beats match Bigeminy: {recent_beats[4:0], is_v} == BIGEMINY_TARGET
                    if ({recent_beats[4:0], (beat_class == 2'b01)} == BIGEMINY_TARGET) begin
                        active_bigeminy     <= 1'b1;
                        bigeminy_phase      <= 3'd0;
                        bigeminy_violations <= 2'd0;
                        point_bigeminy      <= 1'b1;
                    end
                end

                // --- Trigeminy State Tracking ---
                if (active_trigeminy) begin
                    if ((beat_class == 2'b01) == exp_trigeminy_beat(trigeminy_phase)) begin
                        trigeminy_violations <= 2'd0;
                        trigeminy_phase      <= (trigeminy_phase == 4'd8) ? 4'd0 : trigeminy_phase + 4'd1;
                    end else begin
                        if (trigeminy_violations >= 2'd1) begin
                            active_trigeminy     <= 1'b0;
                            trigeminy_phase      <= 4'd0;
                            trigeminy_violations <= 2'd0;
                        end else begin
                            trigeminy_violations <= 2'd1;
                            trigeminy_phase      <= (trigeminy_phase == 4'd8) ? 4'd0 : trigeminy_phase + 4'd1;
                        end
                    end
                end else begin
                    // Check if newest 9 beats match Trigeminy: {recent_beats[7:0], is_v} == TRIGEMINY_TARGET
                    if ({recent_beats[7:0], (beat_class == 2'b01)} == TRIGEMINY_TARGET) begin
                        active_trigeminy     <= 1'b1;
                        trigeminy_phase      <= 4'd0;
                        trigeminy_violations <= 2'd0;
                        point_trigeminy      <= 1'b1;
                    end
                end
            end
        end
    end

endmodule
