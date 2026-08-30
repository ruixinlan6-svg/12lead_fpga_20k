`timescale 1ns / 1ps

module tb_beat_window_buffer;

    localparam int INDEX_WIDTH    = 32;
    localparam int RAM_DEPTH      = 512;
    localparam int PENDING_DEPTH  = 4;
    localparam int COUNTER_WIDTH  = 32;

    logic clk;
    logic rst_n;

    logic signed [15:0] sample_data;
    logic [INDEX_WIDTH-1:0] sample_index;
    logic sample_valid;
    logic [INDEX_WIDTH-1:0] qrs_sample_index;
    logic qrs_valid;

    logic window_valid;
    logic signed [15:0] window_data;
    logic [7:0] window_point_index;
    logic [INDEX_WIDTH-1:0] window_sample_index;
    logic [INDEX_WIDTH-1:0] window_r_sample_index;
    logic window_start;
    logic window_center;
    logic window_done;

    logic missing_sample_sticky;
    logic duplicate_sample_sticky;
    logic out_of_order_sample_sticky;
    logic queue_overflow_sticky;
    logic stale_window_sticky;
    logic qrs_reference_error_sticky;
    logic [COUNTER_WIDTH-1:0] missing_sample_count;
    logic [COUNTER_WIDTH-1:0] duplicate_sample_count;
    logic [COUNTER_WIDTH-1:0] out_of_order_sample_count;
    logic [COUNTER_WIDTH-1:0] warmup_drop_count;
    logic [COUNTER_WIDTH-1:0] queue_overflow_count;
    logic [COUNTER_WIDTH-1:0] stale_window_count;
    logic [COUNTER_WIDTH-1:0] qrs_reference_error_count;
    logic [$clog2(PENDING_DEPTH + 1)-1:0] pending_count;

    int scenario_count;
    int completed_windows_total;
    int checked_points_total;
    int expected_window_count;
    int received_window_count;
    int next_expected_point;
    bit window_open;
    bit require_continuous_input;
    logic [INDEX_WIDTH-1:0] expected_r [0:7];

    beat_window_buffer #(
        .SAMPLE_WIDTH   (16),
        .INDEX_WIDTH    (INDEX_WIDTH),
        .RAM_DEPTH      (RAM_DEPTH),
        .PENDING_DEPTH  (PENDING_DEPTH),
        .COUNTER_WIDTH  (COUNTER_WIDTH)
    ) u_dut (
        .clk                        (clk),
        .rst_n                      (rst_n),
        .sample_data                (sample_data),
        .sample_index               (sample_index),
        .sample_valid               (sample_valid),
        .qrs_sample_index           (qrs_sample_index),
        .qrs_valid                  (qrs_valid),
        .window_valid               (window_valid),
        .window_data                (window_data),
        .window_point_index         (window_point_index),
        .window_sample_index        (window_sample_index),
        .window_r_sample_index      (window_r_sample_index),
        .window_start               (window_start),
        .window_center              (window_center),
        .window_done                (window_done),
        .missing_sample_sticky      (missing_sample_sticky),
        .duplicate_sample_sticky    (duplicate_sample_sticky),
        .out_of_order_sample_sticky (out_of_order_sample_sticky),
        .queue_overflow_sticky      (queue_overflow_sticky),
        .stale_window_sticky        (stale_window_sticky),
        .qrs_reference_error_sticky (qrs_reference_error_sticky),
        .missing_sample_count       (missing_sample_count),
        .duplicate_sample_count     (duplicate_sample_count),
        .out_of_order_sample_count  (out_of_order_sample_count),
        .warmup_drop_count          (warmup_drop_count),
        .queue_overflow_count       (queue_overflow_count),
        .stale_window_count         (stale_window_count),
        .qrs_reference_error_count  (qrs_reference_error_count),
        .pending_count              (pending_count)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    function automatic logic signed [15:0] sample_value(
        input logic [INDEX_WIDTH-1:0] idx
    );
        sample_value = $signed(idx[15:0] ^ 16'hA55A);
    endfunction

    task automatic require_true(input logic condition, input string message);
        if (condition !== 1'b1)
            $fatal(1, "[FAIL] %s at time %0t", message, $time);
    endtask

    task automatic prepare_expectations(input int count);
        require_true(window_open == 1'b0, "scoreboard must be idle before a scenario");
        expected_window_count = count;
        received_window_count = 0;
        next_expected_point = 0;
        require_continuous_input = 1'b0;
    endtask

    task automatic drive_sample_cycle(
        input logic [INDEX_WIDTH-1:0] idx,
        input logic emit_qrs,
        input logic [INDEX_WIDTH-1:0] r_idx
    );
        @(negedge clk);
        sample_valid = 1'b1;
        sample_index = idx;
        sample_data = sample_value(idx);
        qrs_valid = emit_qrs;
        qrs_sample_index = r_idx;
        @(posedge clk);
        #1;
    endtask

    task automatic drive_idle_cycle;
        @(negedge clk);
        sample_valid = 1'b0;
        qrs_valid = 1'b0;
        @(posedge clk);
        #1;
    endtask

    task automatic drive_qrs_idle_cycle(
        input logic [INDEX_WIDTH-1:0] r_idx
    );
        @(negedge clk);
        sample_valid = 1'b0;
        qrs_valid = 1'b1;
        qrs_sample_index = r_idx;
        @(posedge clk);
        #1;
        qrs_valid = 1'b0;
    endtask

    task automatic wait_for_expected_windows(input int timeout_cycles);
        int cycles;
        cycles = 0;
        @(negedge clk);
        sample_valid = 1'b0;
        qrs_valid = 1'b0;
        while ((received_window_count != expected_window_count) &&
               (cycles < timeout_cycles)) begin
            @(negedge clk);
            cycles++;
        end
        require_true(received_window_count == expected_window_count,
                     $sformatf("timeout: expected %0d windows, received %0d",
                               expected_window_count, received_window_count));
        require_true(window_open == 1'b0, "window stream ended mid-window");
    endtask

    task automatic assert_clean_counters;
        require_true(missing_sample_sticky === 1'b0, "unexpected missing-sample sticky");
        require_true(duplicate_sample_sticky === 1'b0, "unexpected duplicate-sample sticky");
        require_true(out_of_order_sample_sticky === 1'b0, "unexpected out-of-order sticky");
        require_true(queue_overflow_sticky === 1'b0, "unexpected queue-overflow sticky");
        require_true(stale_window_sticky === 1'b0, "unexpected stale-window sticky");
        require_true(qrs_reference_error_sticky === 1'b0, "unexpected QRS-reference sticky");
        require_true(missing_sample_count === 32'd0, "unexpected missing-sample count");
        require_true(duplicate_sample_count === 32'd0, "unexpected duplicate-sample count");
        require_true(out_of_order_sample_count === 32'd0, "unexpected out-of-order count");
        require_true(warmup_drop_count === 32'd0, "unexpected warm-up drop count");
        require_true(queue_overflow_count === 32'd0, "unexpected queue-overflow count");
        require_true(stale_window_count === 32'd0, "unexpected stale-window count");
        require_true(qrs_reference_error_count === 32'd0, "unexpected QRS-reference count");
    endtask

    task automatic apply_reset;
        @(negedge clk);
        rst_n = 1'b0;
        sample_valid = 1'b0;
        qrs_valid = 1'b0;
        repeat (3) begin
            @(posedge clk);
            #1;
            require_true(window_valid === 1'b0, "window_valid asserted during reset");
        end
        @(negedge clk);
        rst_n = 1'b1;
        @(posedge clk);
        #1;
        require_true(window_valid === 1'b0, "window_valid asserted immediately after reset");
        window_open = 1'b0;
        next_expected_point = 0;
    endtask

    // Cycle-exact scoreboard. Every valid point is checked; completion requires
    // exactly 160 consecutive points, not merely one successful comparison.
    always @(posedge clk) begin
        #1;
        if (rst_n && window_valid) begin
            if ($isunknown(window_data) || $isunknown(window_point_index) ||
                $isunknown(window_sample_index) || $isunknown(window_r_sample_index) ||
                $isunknown(window_start) || $isunknown(window_center) ||
                $isunknown(window_done))
                $display("[DIAG] data=%h/%0d point=%h/%0d sample=%h/%0d r=%h/%0d markers=%b%b%b/%0d%0d%0d",
                         window_data, $isunknown(window_data),
                         window_point_index, $isunknown(window_point_index),
                         window_sample_index, $isunknown(window_sample_index),
                         window_r_sample_index, $isunknown(window_r_sample_index),
                         window_start, window_center, window_done,
                         $isunknown(window_start), $isunknown(window_center), $isunknown(window_done));
            require_true(!$isunknown(window_data) && !$isunknown(window_point_index) &&
                         !$isunknown(window_sample_index) && !$isunknown(window_r_sample_index) &&
                         !$isunknown(window_start) && !$isunknown(window_center) &&
                         !$isunknown(window_done),
                         "window output contains X/Z");
            require_true(received_window_count < expected_window_count,
                         "unexpected extra output window");
            require_true(window_r_sample_index === expected_r[received_window_count],
                         "R sample index mismatch");
            require_true(window_point_index === next_expected_point[7:0],
                         "window point index is not consecutive");
            require_true(window_sample_index ===
                         (expected_r[received_window_count] - 32'd64 + next_expected_point),
                         "window source sample index mismatch");
            require_true(window_data === sample_value(window_sample_index),
                         "window sample data mismatch");
            require_true(window_start === (next_expected_point == 0),
                         "window_start marker mismatch");
            require_true(window_center === (next_expected_point == 64),
                         "window_center marker mismatch");
            require_true(window_done === (next_expected_point == 159),
                         "window_done marker mismatch");
            if (require_continuous_input)
                require_true(sample_valid === 1'b1,
                             "sample input was not continuous during synchronous read");

            if (next_expected_point == 0) begin
                require_true(window_open == 1'b0, "new window overlapped prior serial output");
                window_open = 1'b1;
            end

            checked_points_total++;
            if (next_expected_point == 159) begin
                window_open = 1'b0;
                next_expected_point = 0;
                received_window_count++;
                completed_windows_total++;
            end else begin
                next_expected_point++;
            end
        end else if (rst_n && window_open) begin
            $fatal(1, "[FAIL] bubble inside 160-point window at time %0t", $time);
        end
    end

    initial begin : run_tests
        int idx;

        rst_n = 1'b0;
        sample_data = '0;
        sample_index = '0;
        sample_valid = 1'b0;
        qrs_sample_index = '0;
        qrs_valid = 1'b0;
        scenario_count = 0;
        completed_windows_total = 0;
        checked_points_total = 0;
        expected_window_count = 0;
        received_window_count = 0;
        next_expected_point = 0;
        window_open = 1'b0;
        require_continuous_input = 1'b0;

        // 1. Exact one-window contract: [R-64,R+95], 160 points, center=64.
        $display("[SCENARIO 1] single exact 160-point window");
        apply_reset();
        prepare_expectations(1);
        expected_r[0] = 32'd64;
        for (idx = 0; idx <= 159; idx++)
            drive_sample_cycle(idx, idx == 64, 32'd64);
        wait_for_expected_windows(300);
        assert_clean_counters();
        require_true(pending_count === 0, "single-window queue did not drain");
        scenario_count++;

        // 2. Two QRS windows overlap in source time and remain ordered.
        $display("[SCENARIO 2] two overlapping QRS windows");
        apply_reset();
        prepare_expectations(2);
        expected_r[0] = 32'd200;
        expected_r[1] = 32'd268;
        for (idx = 0; idx <= 500; idx++)
            drive_sample_cycle(idx, (idx == 200) || (idx == 268), idx);
        wait_for_expected_windows(500);
        assert_clean_counters();
        require_true(pending_count === 0, "overlap queue did not drain");
        scenario_count++;

        // 3. R=500 makes [436,595] cross the 511->0 RAM address wrap.
        $display("[SCENARIO 3] circular BSRAM address wrap");
        apply_reset();
        prepare_expectations(1);
        expected_r[0] = 32'd500;
        for (idx = 0; idx <= 595; idx++)
            drive_sample_cycle(idx, idx == 500, 32'd500);
        wait_for_expected_windows(300);
        assert_clean_counters();
        scenario_count++;

        // 4. Absolute R<64 events are explicitly discarded and counted.
        $display("[SCENARIO 4] warm-up event rejection");
        apply_reset();
        prepare_expectations(0);
        for (idx = 0; idx <= 90; idx++)
            drive_sample_cycle(idx, (idx == 20) || (idx == 63), idx);
        repeat (200) drive_idle_cycle();
        require_true(received_window_count == 0, "warm-up event produced a window");
        require_true(warmup_drop_count === 32'd2, "warm-up drop count must be exactly two");
        require_true(pending_count === 0, "warm-up events entered pending queue");
        require_true(queue_overflow_count === 32'd0, "warm-up incorrectly counted as overflow");
        scenario_count++;

        // 5. Five not-yet-ready events against depth four: four retained, one
        // explicit sticky overflow with an exact counter increment.
        $display("[SCENARIO 5] pending queue overflow is explicit");
        apply_reset();
        prepare_expectations(4);
        expected_r[0] = 32'd64;
        expected_r[1] = 32'd65;
        expected_r[2] = 32'd66;
        expected_r[3] = 32'd67;
        for (idx = 0; idx <= 200; idx++) begin
            if ((idx >= 100) && (idx <= 104))
                drive_sample_cycle(idx, 1'b1, 32'd64 + (idx - 100));
            else
                drive_sample_cycle(idx, 1'b0, 32'd0);
        end
        wait_for_expected_windows(900);
        require_true(queue_overflow_sticky === 1'b1, "overflow sticky was not set");
        require_true(queue_overflow_count === 32'd1, "overflow count must be exactly one");
        require_true(pending_count === 0, "overflow scenario queue did not drain");
        require_true(missing_sample_count === 32'd0, "overflow scenario corrupted sequence count");
        scenario_count++;

        // 6. Missing, duplicate and out-of-order samples each set their own
        // sticky/counter and flush a pending window without later output.
        $display("[SCENARIO 6] malformed sample sequence flushes pending work");
        apply_reset();
        prepare_expectations(0);
        for (idx = 0; idx <= 100; idx++)
            drive_sample_cycle(idx, idx == 80, 32'd80);
        drive_sample_cycle(32'd102, 1'b0, 32'd0); // missing 101
        drive_sample_cycle(32'd102, 1'b0, 32'd0); // duplicate
        drive_sample_cycle(32'd101, 1'b0, 32'd0); // out of order
        repeat (250) drive_idle_cycle();
        require_true(received_window_count == 0, "flushed pending window still produced output");
        require_true(missing_sample_sticky === 1'b1, "missing sticky not set");
        require_true(duplicate_sample_sticky === 1'b1, "duplicate sticky not set");
        require_true(out_of_order_sample_sticky === 1'b1, "out-of-order sticky not set");
        require_true(missing_sample_count === 32'd1, "missing count must be exactly one");
        require_true(duplicate_sample_count === 32'd1, "duplicate count must be exactly one");
        require_true(out_of_order_sample_count === 32'd1, "out-of-order count must be exactly one");
        require_true(pending_count === 0, "sequence error did not flush pending queue");
        scenario_count++;

        // 7. Reset aborts a live stream, suppresses output while asserted, and
        // the first post-reset segment can produce a clean independent window.
        $display("[SCENARIO 7] reset during output and clean recovery");
        apply_reset();
        prepare_expectations(1);
        expected_r[0] = 32'd64;
        for (idx = 0; idx <= 159; idx++)
            drive_sample_cycle(idx, idx == 64, 32'd64);
        @(negedge clk);
        sample_valid = 1'b0;
        qrs_valid = 1'b0;
        while (next_expected_point < 21)
            @(negedge clk);
        require_true(window_open == 1'b1, "reset test never entered output stream");
        expected_window_count = 0;
        received_window_count = 0;
        window_open = 1'b0;
        next_expected_point = 0;
        // The loop exits on a negedge; assert reset immediately so no extra
        // valid point can escape before the reset-under-stream check.
        rst_n = 1'b0;
        sample_valid = 1'b0;
        qrs_valid = 1'b0;
        repeat (3) begin
            @(posedge clk);
            #1;
            require_true(window_valid === 1'b0, "window_valid asserted during stream reset");
        end
        @(negedge clk);
        rst_n = 1'b1;
        @(posedge clk);
        #1;
        require_true(window_valid === 1'b0, "window_valid asserted after stream reset");
        repeat (10) drive_idle_cycle();
        prepare_expectations(1);
        expected_r[0] = 32'd1064;
        for (idx = 1000; idx <= 1159; idx++)
            drive_sample_cycle(idx, idx == 1064, 32'd1064);
        wait_for_expected_windows(300);
        assert_clean_counters();
        scenario_count++;

        // 8. A complete output is checked while writes continue every clock;
        // this is the explicit one-cycle synchronous-read alignment stress.
        $display("[SCENARIO 8] continuous write plus synchronous read alignment");
        apply_reset();
        prepare_expectations(1);
        expected_r[0] = 32'd300;
        require_continuous_input = 1'b1;
        for (idx = 0; idx <= 600; idx++)
            drive_sample_cycle(idx, idx == 300, 32'd300);
        require_continuous_input = 1'b0;
        wait_for_expected_windows(300);
        assert_clean_counters();
        scenario_count++;

        // 9. A QRS on the first sample of a non-zero post-reset segment has no
        // 64-sample prehistory and must be counted as a warm-up drop.
        $display("[SCENARIO 9] segment-local warm-up on first sample");
        apply_reset();
        prepare_expectations(0);
        for (idx = 1000; idx <= 1100; idx++)
            drive_sample_cycle(idx, idx == 1000, 32'd1000);
        repeat (200) drive_idle_cycle();
        require_true(received_window_count == 0, "segment-first QRS produced a window");
        require_true(warmup_drop_count === 32'd1, "segment-first QRS was not a warm-up drop");
        require_true(qrs_reference_error_count === 32'd0, "segment-first QRS was misclassified as reference error");
        require_true(pending_count === 0, "segment-first QRS entered pending queue");
        scenario_count++;

        // 10. QRS decisions are allowed to arrive on an independent fabric
        // cycle after the referenced sample and its post-history are stored.
        // A future reference on the same idle interface must still fail closed.
        $display("[SCENARIO 10] delayed QRS handshake and future-reference rejection");
        apply_reset();
        prepare_expectations(1);
        expected_r[0] = 32'd2100;
        for (idx = 2000; idx <= 2200; idx++)
            drive_sample_cycle(idx, 1'b0, 32'd0);
        drive_qrs_idle_cycle(32'd2100);
        wait_for_expected_windows(300);
        require_true(qrs_reference_error_count === 32'd0,
                     "legal delayed QRS was classified as a reference error");
        require_true(pending_count === 0, "delayed-QRS queue did not drain");
        drive_qrs_idle_cycle(32'd2300);
        repeat (200) drive_idle_cycle();
        require_true(received_window_count == 1, "future QRS produced an output window");
        require_true(qrs_reference_error_sticky === 1'b1,
                     "future idle-cycle QRS did not set the reference-error sticky");
        require_true(qrs_reference_error_count === 32'd1,
                     "future idle-cycle QRS error count must be exactly one");
        require_true(missing_sample_count === 32'd0 &&
                     duplicate_sample_count === 32'd0 &&
                     out_of_order_sample_count === 32'd0 &&
                     warmup_drop_count === 32'd0 &&
                     queue_overflow_count === 32'd0 &&
                     stale_window_count === 32'd0,
                     "delayed-QRS scenario changed an unrelated error counter");
        scenario_count++;

        require_true(scenario_count == 10, "not all ten scenarios completed");
        require_true(completed_windows_total == 11,
                     "completed-window total must be exactly eleven");
        require_true(checked_points_total == 1781,
                     "checked-point total must be 11*160 plus 21 reset-aborted points");

        $display("BEAT_WINDOW_BUFFER_ALL_PASS scenarios=%0d completed_windows=%0d checked_points=%0d",
                 scenario_count, completed_windows_total, checked_points_total);
        $finish;
    end

    initial begin
        #200000;
        $display("[TIMEOUT DIAG] scenario=%0d next=%0d recv=%0d pending=%0d valid=%b active=%b pipe=%b last=%0d",
                 scenario_count, next_expected_point, received_window_count, pending_count,
                 window_valid, u_dut.read_active, u_dut.read_valid_q, u_dut.last_sample_index);
        $fatal(1, "[FAIL] global testbench timeout");
    end

endmodule
