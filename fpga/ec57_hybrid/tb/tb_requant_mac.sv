`timescale 1ns / 1ps

// =============================================================================
// Testbench: tb_requant_mac
// Description: Comprehensive self-checking testbench for ecg_requant_mac module.
//
// Test Coverage:
//   1. Exact capture-edge E0 to registered-output-edge E1 relation and valid handshake.
//   2. Shift = 0 edge cases (identity scaling, dynamic saturation to int8).
//   3. Symmetric Round-Half-Away-From-Zero on positive values (+0.5, +1.5, +0.499, +0.501).
//   4. Symmetric Round-Half-Away-From-Zero on negative values (-0.5, -1.5, -0.499, -0.501).
//   5. Shift sweeps across range 0 to 31.
//   6. 32-bit extreme accumulator & multiplier limits (INT32_MIN, INT32_MAX, 64-bit bounds).
//   7. Clamping/Saturation upper bound (+127) and lower bound (-128).
//   8. Optional ReLU activation (clamping negative outputs to 0, positive unchanged).
//   9. Reset assertion & pipeline flush.
// =============================================================================

module tb_requant_mac;

    logic        clk;
    logic        rst_n;

    // Clock generation (10 ns clock period)
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Test counters
    int total_tests = 0;
    int pass_count  = 0;
    int fail_count  = 0;

    // DUT Signals
    logic               in_valid;
    logic signed [31:0] in_acc;
    logic signed [31:0] in_mult;
    logic        [4:0]  in_shift;
    logic               relu_en;

    logic               out_valid;
    logic signed [7:0]  out_data;

    // Instantiate DUT
    ecg_requant_mac #(
        .ACC_WIDTH   (32),
        .MULT_WIDTH  (32),
        .OUT_WIDTH   (8),
        .SHIFT_WIDTH (5)
    ) u_dut (
        .clk       (clk),
        .rst_n     (rst_n),
        .in_valid  (in_valid),
        .in_acc    (in_acc),
        .in_mult   (in_mult),
        .in_shift  (in_shift),
        .relu_en   (relu_en),
        .out_valid (out_valid),
        .out_data  (out_data)
    );

    // Golden Reference Function in SystemVerilog for verification
    function automatic logic signed [7:0] golden_requant(
        input logic signed [31:0] acc,
        input logic signed [31:0] mult,
        input logic        [4:0]  shift,
        input logic               relu
    );
        longint signed prod;
        longint signed round_term;
        longint signed prod_rounded;
        longint signed scaled;
        logic signed [7:0] res;

        prod = acc * mult;
        if (shift == 5'd0) begin
            round_term = 64'sd0;
        end else begin
            if (prod >= 0)
                round_term = (64'sd1 <<< (shift - 1));
            else
                round_term = (64'sd1 <<< (shift - 1)) - 64'sd1;
        end

        prod_rounded = prod + round_term;
        scaled       = prod_rounded >>> shift;

        if (relu && (scaled < 0)) begin
            res = 8'sd0;
        end else if (scaled > 64'sd127) begin
            res = 8'sd127;
        end else if (scaled < -64'sd128) begin
            res = -8'sd128;
        end else begin
            res = scaled[7:0];
        end

        return res;
    endfunction

    // The task drives immediately after one edge; the DUT accepts on the next
    // edge E0 and registers the result on E1, so the check occurs two observed
    // posedges after the testbench starts driving.
    task send_and_check(
        input string              test_name,
        input logic signed [31:0] acc,
        input logic signed [31:0] mult,
        input logic        [4:0]  shift,
        input logic               relu,
        input logic signed [7:0]  expected
    );
        @(posedge clk);
        in_valid <= 1'b1;
        in_acc   <= acc;
        in_mult  <= mult;
        in_shift <= shift;
        relu_en  <= relu;

        // E0: multiplier stage accepts the request
        @(posedge clk);
        in_valid <= 1'b0;

        // E1: output valid & data are registered
        @(posedge clk);
        #1; // Sample shortly after clock edge
        total_tests++;

        if (out_valid !== 1'b1) begin
            fail_count++;
            $display("[FAIL] %s: out_valid is NOT 1 (latency mismatch)! time=%0t", test_name, $time);
        end else if (out_data !== expected) begin
            fail_count++;
            $display("[FAIL] %s: acc=%0d mult=%0d shift=%0d relu=%0d => actual=%0d, expected=%0d at time=%0t",
                     test_name, acc, mult, shift, relu, out_data, expected, $time);
        end else begin
            pass_count++;
        end
    endtask

    // Main Test Stimulus
    initial begin
        logic signed [31:0] sweep_val;
        logic signed [7:0]  sweep_exp;

        $display("================================================================");
        $display("Starting Parameterized ECG Requant MAC Testbench");
        $display("================================================================");

        // Reset and initialization
        rst_n    = 0;
        in_valid = 0;
        in_acc   = 0;
        in_mult  = 0;
        in_shift = 0;
        relu_en  = 0;

        #20;
        rst_n = 1;
        #20;

        // ---------------------------------------------------------------------
        // TEST 1: Shift = 0 Edge Cases (Direct scaling & saturation)
        // ---------------------------------------------------------------------
        $display("[TEST 1] Shift = 0 Tests");
        send_and_check("Shift0 Zero",           32'sd0,    32'sd1, 5'd0, 1'b0, 8'sd0);
        send_and_check("Shift0 Pos Normal",     32'sd42,   32'sd1, 5'd0, 1'b0, 8'sd42);
        send_and_check("Shift0 Neg Normal",    -32'sd42,   32'sd1, 5'd0, 1'b0, -8'sd42);
        send_and_check("Shift0 Pos Bound",      32'sd127,  32'sd1, 5'd0, 1'b0, 8'sd127);
        send_and_check("Shift0 Neg Bound",     -32'sd128,  32'sd1, 5'd0, 1'b0, -8'sd128);
        send_and_check("Shift0 Pos Clamp",      32'sd128,  32'sd1, 5'd0, 1'b0, 8'sd127);
        send_and_check("Shift0 Neg Clamp",     -32'sd129,  32'sd1, 5'd0, 1'b0, -8'sd128);
        send_and_check("Shift0 Large Pos",      32'sd5000, 32'sd1, 5'd0, 1'b0, 8'sd127);
        send_and_check("Shift0 Large Neg",     -32'sd5000, 32'sd1, 5'd0, 1'b0, -8'sd128);

        // ---------------------------------------------------------------------
        // TEST 2: Positive Round-Half-Away-From-Zero (+0.5, +1.5, +0.499, +0.501)
        // ---------------------------------------------------------------------
        $display("[TEST 2] Positive Rounding Tests (Away-from-zero)");
        // Shift = 1 (half = 1)
        // 1 * 1 = 1 (+0.5) -> rounds to +1
        send_and_check("Shift1 Exact +0.5",     32'sd1, 32'sd1, 5'd1, 1'b0, 8'sd1);
        // 3 * 1 = 3 (+1.5) -> rounds to +2
        send_and_check("Shift1 Exact +1.5",     32'sd3, 32'sd1, 5'd1, 1'b0, 8'sd2);
        // 2 * 1 = 2 (+1.0) -> rounds to +1
        send_and_check("Shift1 Exact +1.0",     32'sd2, 32'sd1, 5'd1, 1'b0, 8'sd1);

        // Shift = 4 (divider = 16, half = 8)
        // 8 * 1 = 8 (+0.5) -> rounds to +1
        send_and_check("Shift4 Exact +0.5",     32'sd8,  32'sd1, 5'd4, 1'b0, 8'sd1);
        // 7 * 1 = 7 (+0.4375) -> rounds to 0
        send_and_check("Shift4 Below +0.5",     32'sd7,  32'sd1, 5'd4, 1'b0, 8'sd0);
        // 9 * 1 = 9 (+0.5625) -> rounds to +1
        send_and_check("Shift4 Above +0.5",     32'sd9,  32'sd1, 5'd4, 1'b0, 8'sd1);
        // 24 * 1 = 24 (+1.5) -> rounds to +2
        send_and_check("Shift4 Exact +1.5",     32'sd24, 32'sd1, 5'd4, 1'b0, 8'sd2);
        // 40 * 1 = 40 (+2.5) -> rounds to +3
        send_and_check("Shift4 Exact +2.5",     32'sd40, 32'sd1, 5'd4, 1'b0, 8'sd3);

        // Shift = 8 (divider = 256, half = 128)
        send_and_check("Shift8 Exact +0.5",   32'sd128, 32'sd1, 5'd8, 1'b0, 8'sd1);
        send_and_check("Shift8 Below +0.5",   32'sd127, 32'sd1, 5'd8, 1'b0, 8'sd0);
        send_and_check("Shift8 Above +0.5",   32'sd129, 32'sd1, 5'd8, 1'b0, 8'sd1);
        send_and_check("Shift8 Exact +1.5",   32'sd384, 32'sd1, 5'd8, 1'b0, 8'sd2);

        // ---------------------------------------------------------------------
        // TEST 3: Negative Round-Half-Away-From-Zero (-0.5, -1.5, -0.499, -0.501)
        // ---------------------------------------------------------------------
        $display("[TEST 3] Negative Rounding Tests (Away-from-zero)");
        // Shift = 1 (half = -1)
        // -1 * 1 = -1 (-0.5) -> rounds away from zero to -1
        send_and_check("Shift1 Exact -0.5",    -32'sd1, 32'sd1, 5'd1, 1'b0, -8'sd1);
        // -3 * 1 = -3 (-1.5) -> rounds away from zero to -2
        send_and_check("Shift1 Exact -1.5",    -32'sd3, 32'sd1, 5'd1, 1'b0, -8'sd2);
        // -2 * 1 = -2 (-1.0) -> rounds to -1
        send_and_check("Shift1 Exact -1.0",    -32'sd2, 32'sd1, 5'd1, 1'b0, -8'sd1);

        // Shift = 4 (divider = 16, half = -8)
        // -8 * 1 = -8 (-0.5) -> rounds away from zero to -1
        send_and_check("Shift4 Exact -0.5",    -32'sd8,  32'sd1, 5'd4, 1'b0, -8'sd1);
        // -7 * 1 = -7 (-0.4375, closer to 0) -> rounds towards 0 to 0
        send_and_check("Shift4 Below -0.5",    -32'sd7,  32'sd1, 5'd4, 1'b0, 8'sd0);
        // -9 * 1 = -9 (-0.5625, further from 0) -> rounds away from zero to -1
        send_and_check("Shift4 Above -0.5",    -32'sd9,  32'sd1, 5'd4, 1'b0, -8'sd1);
        // -24 * 1 = -24 (-1.5) -> rounds away from zero to -2
        send_and_check("Shift4 Exact -1.5",   -32'sd24, 32'sd1, 5'd4, 1'b0, -8'sd2);
        // -40 * 1 = -40 (-2.5) -> rounds away from zero to -3
        send_and_check("Shift4 Exact -2.5",   -32'sd40, 32'sd1, 5'd4, 1'b0, -8'sd3);

        // Shift = 8 (divider = 256, half = -128)
        send_and_check("Shift8 Exact -0.5",  -32'sd128, 32'sd1, 5'd8, 1'b0, -8'sd1);
        send_and_check("Shift8 Below -0.5",  -32'sd127, 32'sd1, 5'd8, 1'b0, 8'sd0);
        send_and_check("Shift8 Above -0.5",  -32'sd129, 32'sd1, 5'd8, 1'b0, -8'sd1);
        send_and_check("Shift8 Exact -1.5",  -32'sd384, 32'sd1, 5'd8, 1'b0, -8'sd2);

        // ---------------------------------------------------------------------
        // TEST 4: Max Shift = 31 Boundary Tests
        // ---------------------------------------------------------------------
        $display("[TEST 4] Shift = 31 Boundary Tests");
        // 2^30 = 1073741824 (+0.5 * 2^31) -> rounds to +1
        send_and_check("Shift31 Exact +0.5",  32'sd1073741824, 32'sd1, 5'd31, 1'b0, 8'sd1);
        // 2^30 - 1 = 1073741823 (+0.4999999) -> rounds to 0
        send_and_check("Shift31 Below +0.5",  32'sd1073741823, 32'sd1, 5'd31, 1'b0, 8'sd0);
        // -2^30 = -1073741824 (-0.5 * 2^31) -> rounds away from zero to -1
        send_and_check("Shift31 Exact -0.5", -32'sd1073741824, 32'sd1, 5'd31, 1'b0, -8'sd1);
        // -2^30 + 1 = -1073741823 (-0.4999999) -> rounds to 0
        send_and_check("Shift31 Below -0.5", -32'sd1073741823, 32'sd1, 5'd31, 1'b0, 8'sd0);

        // ---------------------------------------------------------------------
        // TEST 5: Accumulator & Multiplier Extreme Limits (INT32_MIN, INT32_MAX)
        // ---------------------------------------------------------------------
        $display("[TEST 5] 32-bit Extreme Limits & 64-bit Overflow Immunity");
        // INT32_MAX * 1
        send_and_check("Acc Max * 1",       32'sh7FFFFFFF, 32'sd1, 5'd0, 1'b0, 8'sd127);
        // INT32_MIN * 1
        send_and_check("Acc Min * 1",      -32'sd2147483648, 32'sd1, 5'd0, 1'b0, -8'sd128);
        // INT32_MAX * INT32_MAX (prod ~ +2^62), shift = 31 -> clamps to +127
        send_and_check("Max * Max Shift31", 32'sh7FFFFFFF, 32'sh7FFFFFFF, 5'd31, 1'b0, 8'sd127);
        // INT32_MIN * INT32_MAX (prod ~ -2^62), shift = 31 -> clamps to -128
        send_and_check("Min * Max Shift31", -32'sd2147483648, 32'sh7FFFFFFF, 5'd31, 1'b0, -8'sd128);
        // INT32_MIN * -1 with Shift = 0 -> +2147483648 -> clamps to +127
        send_and_check("Min * -1 Shift0",   -32'sd2147483648, -32'sd1, 5'd0, 1'b0, 8'sd127);
        // Independent signed-multiplier vectors (not generated by golden_requant).
        send_and_check("Min * Min Shift31", -32'sd2147483648, -32'sd2147483648, 5'd31, 1'b0, 8'sd127);
        send_and_check("Pos * Neg Shift1",    32'sd3,          -32'sd1,          5'd1,  1'b0, -8'sd2);
        send_and_check("Neg * Neg Shift1",   -32'sd3,          -32'sd1,          5'd1,  1'b0,  8'sd2);
        send_and_check("Max * Min Shift31",   32'sh7FFFFFFF,   -32'sd2147483648, 5'd31, 1'b0, -8'sd128);
        send_and_check("Min * Max Shift30",  -32'sd2147483648, 32'sh7FFFFFFF,   5'd30, 1'b0, -8'sd128);

        // ---------------------------------------------------------------------
        // TEST 6: Clamping / Saturation Transitions
        // ---------------------------------------------------------------------
        $display("[TEST 6] Clamping Transitions");
        // Producing exactly +126, +127, +128 (clamps to +127)
        send_and_check("Clamp +126", 32'sd126, 32'sd1, 5'd0, 1'b0, 8'sd126);
        send_and_check("Clamp +127", 32'sd127, 32'sd1, 5'd0, 1'b0, 8'sd127);
        send_and_check("Clamp +128", 32'sd128, 32'sd1, 5'd0, 1'b0, 8'sd127);
        send_and_check("Clamp +129", 32'sd129, 32'sd1, 5'd0, 1'b0, 8'sd127);

        // Producing exactly -127, -128, -129 (clamps to -128)
        send_and_check("Clamp -127", -32'sd127, 32'sd1, 5'd0, 1'b0, -8'sd127);
        send_and_check("Clamp -128", -32'sd128, 32'sd1, 5'd0, 1'b0, -8'sd128);
        send_and_check("Clamp -129", -32'sd129, 32'sd1, 5'd0, 1'b0, -8'sd128);
        send_and_check("Clamp -130", -32'sd130, 32'sd1, 5'd0, 1'b0, -8'sd128);

        // ---------------------------------------------------------------------
        // TEST 7: ReLU Activation Mode
        // ---------------------------------------------------------------------
        $display("[TEST 7] ReLU Activation Mode Tests");
        send_and_check("ReLU Pos Pass",        32'sd50,  32'sd1, 5'd0, 1'b1, 8'sd50);
        send_and_check("ReLU Zero Pass",       32'sd0,   32'sd1, 5'd0, 1'b1, 8'sd0);
        send_and_check("ReLU Neg Zeroed",     -32'sd50,  32'sd1, 5'd0, 1'b1, 8'sd0);
        send_and_check("ReLU Neg Bound Zero", -32'sd128, 32'sd1, 5'd0, 1'b1, 8'sd0);
        send_and_check("ReLU Large Neg Zero", -32'sd999, 32'sd1, 5'd0, 1'b1, 8'sd0);
        send_and_check("ReLU Pos Saturated",   32'sd200, 32'sd1, 5'd0, 1'b1, 8'sd127);

        // ---------------------------------------------------------------------
        // TEST 8: Shift Sweep Matrix (0 to 31) against Golden Function
        // ---------------------------------------------------------------------
        $display("[TEST 8] Comprehensive Shift Sweep (0 to 31)");
        for (int s = 0; s <= 31; s++) begin
            // Positive test
            sweep_val = (32'sd100 <<< (s > 20 ? 20 : s));
            sweep_exp = golden_requant(sweep_val, 32'sd1, s[4:0], 1'b0);
            send_and_check($sformatf("Sweep Pos shift=%0d", s), sweep_val, 32'sd1, s[4:0], 1'b0, sweep_exp);

            // Negative test
            sweep_val = -(32'sd100 <<< (s > 20 ? 20 : s));
            sweep_exp = golden_requant(sweep_val, 32'sd1, s[4:0], 1'b0);
            send_and_check($sformatf("Sweep Neg shift=%0d", s), sweep_val, 32'sd1, s[4:0], 1'b0, sweep_exp);
        end

        // ---------------------------------------------------------------------
        // TEST 9: Unambiguous Capture-to-Output Edge Relationship
        // ---------------------------------------------------------------------
        $display("[TEST 9] Capture Edge E0 -> Registered Output Edge E1");
        // Flush prior valid state, then drive one input before capture edge E0.
        @(negedge clk);
        in_valid = 1'b0;
        repeat (2) @(posedge clk);
        @(negedge clk);
        in_valid = 1'b1; in_acc = 32'sd77; in_mult = 32'sd1; in_shift = 5'd0; relu_en = 1'b0;
        @(posedge clk); // E0: stage 1 captures the request.
        #1;
        total_tests++;
        if (out_valid === 1'b0) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] out_valid asserted on capture edge E0");
        end
        @(negedge clk);
        in_valid = 1'b0;
        @(posedge clk); // E1: registered result is visible.
        #1;
        total_tests++;
        if (out_valid === 1'b1 && out_data === 8'sd77) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] result missing at E1: valid=%b data=%d", out_valid, out_data);
        end
        @(posedge clk); // E2: bubble propagates to output.
        #1;
        total_tests++;
        if (out_valid === 1'b0) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] out_valid did not clear at E2");
        end

        // ---------------------------------------------------------------------
        // TEST 10: Continuous Streaming / Pipeline Throughput Verification
        // ---------------------------------------------------------------------
        $display("[TEST 10] Continuous Streaming Throughput");
        @(posedge clk);
        in_valid <= 1'b1; in_acc <= 32'sd10; in_mult <= 32'sd1; in_shift <= 5'd0; relu_en <= 1'b0;
        @(posedge clk);
        in_valid <= 1'b1; in_acc <= 32'sd20; in_mult <= 32'sd1; in_shift <= 5'd0; relu_en <= 1'b0;
        @(posedge clk);
        in_valid <= 1'b1; in_acc <= 32'sd30; in_mult <= 32'sd1; in_shift <= 5'd0; relu_en <= 1'b0;
        // Check output 1 (should be 10)
        #1;
        total_tests++;
        if (out_valid === 1'b1 && out_data === 8'sd10) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] Streaming item 0 mismatch: valid=%b data=%d", out_valid, out_data);
        end

        @(posedge clk);
        in_valid <= 1'b0;
        // Check output 2 (should be 20)
        #1;
        total_tests++;
        if (out_valid === 1'b1 && out_data === 8'sd20) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] Streaming item 1 mismatch: valid=%b data=%d", out_valid, out_data);
        end

        @(posedge clk);
        // Check output 3 (should be 30)
        #1;
        total_tests++;
        if (out_valid === 1'b1 && out_data === 8'sd30) pass_count++;
        else begin
            fail_count++;
            $display("[FAIL] Streaming item 2 mismatch: valid=%b data=%d", out_valid, out_data);
        end

        // ---------------------------------------------------------------------
        // TEST 11: Reset Flush Test
        // ---------------------------------------------------------------------
        $display("[TEST 11] Reset Flush Test");
        @(posedge clk);
        in_valid <= 1'b1; in_acc <= 32'sd50; in_mult <= 32'sd1; in_shift <= 5'd0; relu_en <= 1'b0;
        @(posedge clk);
        rst_n <= 1'b0; // Assert reset during pipeline flight
        @(posedge clk);
        #1;
        total_tests++;
        if (out_valid === 1'b0 && out_data === 8'sd0) begin
            pass_count++;
        end else begin
            fail_count++;
            $display("[FAIL] Reset did not clear pipeline output: valid=%b data=%d", out_valid, out_data);
        end
        rst_n <= 1'b1;

        // ---------------------------------------------------------------------
        // Final Summary
        // ---------------------------------------------------------------------
        #20;
        $display("================================================================");
        $display("ECG Requant MAC Test Summary:");
        $display("  Total Tests: %0d", total_tests);
        $display("  Passed:      %0d", pass_count);
        $display("  Failed:      %0d", fail_count);
        if (fail_count == 0) begin
            $display("[ALL PASS] All ECG Requant MAC tests completed successfully!");
        end else begin
            $display("[FATAL ERROR] %0d ECG Requant MAC tests failed!", fail_count);
        end
        $display("================================================================");

        if (fail_count != 0)
            $fatal(1, "%0d ECG requant tests failed", fail_count);
        else
            $finish;
    end

endmodule
