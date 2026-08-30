`timescale 1ns / 1ps

module tb_rhythm_engine;

    reg        clk;
    reg        rst_n;
    reg        sample_valid;
    reg [31:0] sample_time_ms;
    reg [3:0]  valid_lead_count;
    reg        hr_valid;
    reg [7:0]  hr_bpm;
    reg        qrs_valid;
    reg [1:0]  beat_class;

    wire       point_signal_loss;
    wire       point_brady;
    wire       point_tachy;
    wire       point_asystole;
    wire       point_pvc_couplet;
    wire       point_ventricular_run;
    wire       point_vt_candidate;
    wire       point_bigeminy;
    wire       point_trigeminy;

    wire       active_signal_loss;
    wire       active_brady;
    wire       active_tachy;
    wire       active_asystole;
    wire       active_ventricular_run;
    wire       active_vt;
    wire       active_bigeminy;
    wire       active_trigeminy;
    wire       status_ok;

    integer err_count = 0;

    rhythm_engine uut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .sample_time_ms(sample_time_ms),
        .valid_lead_count(valid_lead_count),
        .hr_valid(hr_valid),
        .hr_bpm(hr_bpm),
        .qrs_valid(qrs_valid),
        .beat_class(beat_class),
        .point_signal_loss(point_signal_loss),
        .point_brady(point_brady),
        .point_tachy(point_tachy),
        .point_asystole(point_asystole),
        .point_pvc_couplet(point_pvc_couplet),
        .point_ventricular_run(point_ventricular_run),
        .point_vt_candidate(point_vt_candidate),
        .point_bigeminy(point_bigeminy),
        .point_trigeminy(point_trigeminy),
        .active_signal_loss(active_signal_loss),
        .active_brady(active_brady),
        .active_tachy(active_tachy),
        .active_asystole(active_asystole),
        .active_ventricular_run(active_ventricular_run),
        .active_vt(active_vt),
        .active_bigeminy(active_bigeminy),
        .active_trigeminy(active_trigeminy),
        .status_ok(status_ok)
    );

    // Clock generator (27 MHz: ~37 ns period)
    always #18.5 clk = ~clk;

    task step_sample(
        input [31:0] t_ms,
        input [3:0]  leads,
        input        h_val,
        input [7:0]  hr,
        input        q_val,
        input [1:0]  b_cls
    );
    begin
        @(posedge clk);
        sample_valid     <= 1'b1;
        sample_time_ms   <= t_ms;
        valid_lead_count <= leads;
        hr_valid         <= h_val;
        hr_bpm           <= hr;
        qrs_valid        <= q_val;
        beat_class       <= b_cls;
        @(posedge clk);
        sample_valid     <= 1'b0;
        qrs_valid        <= 1'b0;
        #1;
    end
    endtask

    initial begin
        clk = 0;
        rst_n = 0;
        sample_valid = 0;
        sample_time_ms = 0;
        valid_lead_count = 12;
        hr_valid = 0;
        hr_bpm = 0;
        qrs_valid = 0;
        beat_class = 2'b00;

        #100;
        @(posedge clk);
        rst_n = 1;
        #100;

        $display("=== Starting Test 1: Bradycardia (HR < 50 for 10s, clear at >=55 for 5s) ===");
        // t=0 to 9999 ms with HR 45 (should not assert yet)
        step_sample(32'd0, 4'd12, 1'b1, 8'd45, 1'b0, 2'b00);
        step_sample(32'd9999, 4'd12, 1'b1, 8'd45, 1'b0, 2'b00);
        if (active_brady !== 1'b0) begin
            $display("[FAIL] Brady asserted early at 9999 ms");
            err_count = err_count + 1;
        end

        // t=10000 ms with HR 45 -> should assert
        step_sample(32'd10000, 4'd12, 1'b1, 8'd45, 1'b0, 2'b00);
        if (active_brady !== 1'b1 || point_brady !== 1'b1) begin
            $display("[FAIL] Brady failed to assert at 10000 ms");
            err_count = err_count + 1;
        end

        // t=14999 ms with HR 55 -> should not clear yet
        step_sample(32'd10001, 4'd12, 1'b1, 8'd55, 1'b0, 2'b00);
        step_sample(32'd15000, 4'd12, 1'b1, 8'd55, 1'b0, 2'b00);
        if (active_brady !== 1'b1) begin
            $display("[FAIL] Brady cleared prematurely before 5000 ms duration");
            err_count = err_count + 1;
        end

        // t=15001 ms -> cleared
        step_sample(32'd15001, 4'd12, 1'b1, 8'd55, 1'b0, 2'b00);
        if (active_brady !== 1'b0) begin
            $display("[FAIL] Brady failed to clear at 15001 ms");
            err_count = err_count + 1;
        end

        $display("=== Starting Test 2: Asystole (>= 3000 ms without QRS) ===");
        // QRS at t=20000 ms
        step_sample(32'd20000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00);
        step_sample(32'd22999, 4'd12, 1'b1, 8'd75, 1'b0, 2'b00);
        if (active_asystole !== 1'b0) begin
            $display("[FAIL] Asystole asserted early at 2999 ms");
            err_count = err_count + 1;
        end

        step_sample(32'd23000, 4'd12, 1'b1, 8'd75, 1'b0, 2'b00);
        if (active_asystole !== 1'b1 || point_asystole !== 1'b1) begin
            $display("[FAIL] Asystole failed to assert at 3000 ms gap");
            err_count = err_count + 1;
        end

        // Next QRS at 24000 ms clears asystole
        step_sample(32'd24000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00);
        if (active_asystole !== 1'b0) begin
            $display("[FAIL] Asystole failed to clear upon next QRS");
            err_count = err_count + 1;
        end

        $display("=== Starting Test 3: PVC Couplet, Ventricular Run & VT ===");
        // Beat 1: V at 30000 ms
        step_sample(32'd30000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01);
        if (point_pvc_couplet !== 1'b0 || active_ventricular_run !== 1'b0) begin
            $display("[FAIL] Couplet asserted on 1st V");
            err_count = err_count + 1;
        end

        // Beat 2: V at 30500 ms (RR = 500 ms) -> PVC Couplet!
        step_sample(32'd30500, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01);
        if (point_pvc_couplet !== 1'b1 || active_ventricular_run !== 1'b0) begin
            $display("[FAIL] Couplet failed on 2nd V");
            err_count = err_count + 1;
        end

        // Beat 3: V at 31000 ms (RR = 500 ms) -> Ventricular Run & VT (RR <= 600ms)!
        step_sample(32'd31000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01);
        if (active_ventricular_run !== 1'b1 || point_ventricular_run !== 1'b1 || active_vt !== 1'b1) begin
            $display("[FAIL] Ventricular Run / VT failed on 3rd V (active_vrun=%b, active_vt=%b)", active_ventricular_run, active_vt);
            err_count = err_count + 1;
        end

        // Beat 4: nonV at 32000 ms -> Clears Run and VT
        step_sample(32'd32000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00);
        if (active_ventricular_run !== 1'b0 || active_vt !== 1'b0) begin
            $display("[FAIL] Ventricular Run / VT failed to clear on nonV");
            err_count = err_count + 1;
        end

        $display("=== Starting Test 4: Bigeminy (nonV, V, nonV, V, nonV, V = 6 beats) ===");
        // Sequence: N, V, N, V, N, V
        step_sample(32'd40000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00); // N (1)
        step_sample(32'd40800, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01); // V (2)
        step_sample(32'd41600, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00); // N (3)
        step_sample(32'd42400, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01); // V (4)
        step_sample(32'd43200, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00); // N (5)
        if (active_bigeminy !== 1'b0) begin
            $display("[FAIL] Bigeminy asserted early at 5 beats");
            err_count = err_count + 1;
        end

        step_sample(32'd44000, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01); // V (6) -> Assert!
        if (active_bigeminy !== 1'b1 || point_bigeminy !== 1'b1) begin
            $display("[FAIL] Bigeminy failed to assert on 6th beat");
            err_count = err_count + 1;
        end

        // Next beat: N (correct, phase continues)
        step_sample(32'd44800, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00);
        if (active_bigeminy !== 1'b1) begin
            $display("[FAIL] Bigeminy dropped on valid pattern beat");
            err_count = err_count + 1;
        end

        // 1st violation: N instead of V (should tolerate 1 violation)
        step_sample(32'd45600, 4'd12, 1'b1, 8'd75, 1'b1, 2'b00);
        if (active_bigeminy !== 1'b1) begin
            $display("[FAIL] Bigeminy failed to tolerate 1st violation");
            err_count = err_count + 1;
        end

        // 2nd consecutive violation: V instead of N -> Clears bigeminy
        step_sample(32'd46400, 4'd12, 1'b1, 8'd75, 1'b1, 2'b01);
        if (active_bigeminy !== 1'b0) begin
            $display("[FAIL] Bigeminy failed to clear after 2 consecutive violations");
            err_count = err_count + 1;
        end

        $display("=== Starting Test 5: Signal Loss (valid_lead_count == 0) ===");
        step_sample(32'd50000, 4'd0, 1'b0, 8'd0, 1'b0, 2'b00);
        if (active_signal_loss !== 1'b1 || point_signal_loss !== 1'b1 || status_ok !== 1'b0) begin
            $display("[FAIL] Signal loss failed to assert on 0 leads");
            err_count = err_count + 1;
        end

        #100;
        if (err_count == 0) begin
            $display("=================================================");
            $display(">>> ALL RHYTHM ENGINE TESTS PASSED (0 ERRORS) <<<");
            $display("=================================================");
            $finish(0);
        end else begin
            $fatal(1, "Rhythm engine test failed with %0d errors!", err_count);
        end
    end

endmodule
