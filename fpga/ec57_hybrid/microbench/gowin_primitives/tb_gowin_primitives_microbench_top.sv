`timescale 1ns / 1ps

// =============================================================================
// Testbench: tb_gowin_primitives_microbench_top
// Description: Comprehensive Cycle-Accurate Scoreboard Testbench for the
//              Gowin primitives microbenchmark top module.
//
// Key Checks:
//   1. Strict cycle-by-cycle scoreboard comparison for SP RAM, DP RAM, and Requant MAC.
//   2. Elimination of X/Z propagation (strict $isunknown assertions).
//   3. Verification of 1-cycle RAM latency and 2-cycle MAC latency.
//   4. Exact match of dynamic signature accumulator (dout_data) and status_flags.
//   5. Failure triggers $fatal(1) to return a nonzero process exit code on failure.
// =============================================================================

module tb_gowin_primitives_microbench_top;

    logic        clk;
    logic        rst_n;
    logic        din_valid;
    logic [7:0]  din_data;
    logic [1:0]  ctrl_mode;
    
    logic        dout_valid;
    logic [7:0]  dout_data;
    logic [3:0]  status_flags;

    // Clock generation (10 ns clock period for fast simulation)
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Instantiate Top DUT
    ecg_gowin_primitives_microbench_top u_top (
        .clk          (clk),
        .rst_n        (rst_n),
        .din_valid    (din_valid),
        .din_data     (din_data),
        .ctrl_mode    (ctrl_mode),
        .dout_valid   (dout_valid),
        .dout_data    (dout_data),
        .status_flags (status_flags)
    );

    // -------------------------------------------------------------------------
    // Golden Reference Models & Scoreboard State
    // -------------------------------------------------------------------------
    reg [7:0]  sb_sp_mem [0:2047];
    reg [7:0]  sb_dp_mem [0:2047];

    // Stimulus mirrors
    reg [10:0] sb_sp_addr;
    reg [7:0]  sb_sp_din;
    reg        sb_sp_en;
    reg        sb_sp_we;
    
    reg [10:0] sb_dp_wr_addr;
    reg [7:0]  sb_dp_wr_data;
    reg        sb_dp_wr_en;
    reg [10:0] sb_dp_rd_addr;
    reg        sb_dp_rd_en;
    
    reg signed [31:0] sb_mac_acc;
    reg signed [31:0] sb_mac_mult;
    reg        [4:0]  sb_mac_shift;
    reg               sb_mac_relu;
    reg               sb_mac_valid;

    reg [15:0] sb_lfsr;

    // Pipeline delay stages for golden outputs
    reg [7:0]  sb_sp_dout_q;
    reg        sb_sp_valid_q;
    
    reg [7:0]  sb_dp_rd_data_q;
    reg        sb_dp_valid_q;

    // MAC pipeline
    reg signed [63:0] sb_mac_prod_s1;
    reg        [4:0]  sb_mac_shift_s1;
    reg               sb_mac_relu_s1;
    reg               sb_mac_valid_s1;

    reg signed [7:0]  sb_mac_out_s2;
    reg               sb_mac_valid_s2;

    // Expected accumulator
    reg [7:0]  exp_dout_data;
    reg        exp_dout_valid;
    reg [3:0]  exp_status_flags;

    // Golden requantization function
    function automatic logic signed [7:0] calc_requant(
        input logic signed [63:0] prod,
        input logic        [4:0]  shift,
        input logic               relu
    );
        logic signed [63:0] round_term;
        logic signed [63:0] prod_rounded;
        logic signed [63:0] scaled;
        logic signed [7:0]  res;

        if (shift == 5'd0) begin
            round_term = 64'sd0;
        end else begin
            if (prod >= 64'sd0)
                round_term = (64'sd1 <<< (shift - 1));
            else
                round_term = (64'sd1 <<< (shift - 1)) - 64'sd1;
        end

        prod_rounded = prod + round_term;
        scaled       = prod_rounded >>> shift;

        if (relu && (scaled < 64'sd0)) begin
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

    // Initialize scoreboard memory
    initial begin
        for (int i = 0; i < 2048; i++) begin
            sb_sp_mem[i] = 8'd0;
            sb_dp_mem[i] = 8'd0;
        end
    end

    // Cycle-by-cycle scoreboard update
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sb_lfsr          <= 16'hACE1;
            sb_sp_addr       <= 11'd0;
            sb_sp_din        <= 8'd0;
            sb_sp_en         <= 1'b0;
            sb_sp_we         <= 1'b0;
            sb_dp_wr_addr    <= 11'd0;
            sb_dp_wr_data    <= 8'd0;
            sb_dp_wr_en      <= 1'b0;
            sb_dp_rd_addr    <= 11'd0;
            sb_dp_rd_en      <= 1'b0;
            sb_mac_acc       <= 32'sd0;
            sb_mac_mult      <= 32'sd0;
            sb_mac_shift     <= 5'd0;
            sb_mac_relu      <= 1'b0;
            sb_mac_valid     <= 1'b0;

            sb_sp_dout_q     <= 8'd0;
            sb_sp_valid_q    <= 1'b0;
            sb_dp_rd_data_q  <= 8'd0;
            sb_dp_valid_q    <= 1'b0;

            sb_mac_prod_s1   <= 64'sd0;
            sb_mac_shift_s1  <= 5'd0;
            sb_mac_relu_s1   <= 1'b0;
            sb_mac_valid_s1  <= 1'b0;

            sb_mac_out_s2    <= 8'sd0;
            sb_mac_valid_s2  <= 1'b0;

            exp_dout_data    <= 8'd0;
            exp_dout_valid   <= 1'b0;
            exp_status_flags <= 4'd0;
        end else begin
            // 1. Update LFSR
            sb_lfsr <= {sb_lfsr[14:0], sb_lfsr[15] ^ sb_lfsr[13] ^ sb_lfsr[12] ^ sb_lfsr[10]};

            // 2. Update stimulus registers
            if (din_valid) begin
                sb_mac_acc    <= {sb_mac_acc[23:0], din_data};
                sb_mac_mult   <= {sb_mac_mult[23:0], sb_mac_acc[31:24]};
                sb_mac_shift  <= din_data[4:0];
                sb_mac_relu   <= din_data[5];
                sb_mac_valid  <= 1'b1;

                sb_sp_addr    <= {sb_sp_addr[2:0], din_data};
                sb_sp_din     <= din_data ^ 8'hA5;
                sb_sp_en      <= 1'b1;
                sb_sp_we      <= din_data[0];

                sb_dp_wr_addr <= {sb_dp_wr_addr[2:0], din_data};
                sb_dp_wr_data <= din_data ^ 8'h5A;
                sb_dp_wr_en   <= din_data[1];
                sb_dp_rd_addr <= sb_dp_wr_addr ^ {3'b000, din_data};
                sb_dp_rd_en   <= 1'b1;
            end else if (ctrl_mode == 2'b01) begin
                sb_mac_acc    <= sb_mac_acc + { {16{sb_lfsr[15]}}, sb_lfsr };
                sb_mac_mult   <= {sb_mac_mult[30:0], sb_lfsr[0]} ^ 32'h00010001;
                sb_mac_shift  <= sb_lfsr[4:0];
                sb_mac_relu   <= sb_lfsr[6];
                sb_mac_valid  <= sb_lfsr[7];

                sb_sp_addr    <= sb_sp_addr + 11'd1;
                sb_sp_din     <= sb_lfsr[7:0];
                sb_sp_en      <= 1'b1;
                sb_sp_we      <= sb_lfsr[8];

                sb_dp_wr_addr <= sb_dp_wr_addr + 11'd1;
                sb_dp_wr_data <= sb_lfsr[15:8];
                sb_dp_wr_en   <= sb_lfsr[9];
                sb_dp_rd_addr <= sb_dp_rd_addr + 11'd3;
                sb_dp_rd_en   <= 1'b1;
            end else begin
                sb_mac_valid  <= 1'b0;
                sb_sp_en      <= 1'b0;
                sb_dp_wr_en   <= 1'b0;
                sb_dp_rd_en   <= 1'b0;
            end

            // 3. Update RAM models & 1-cycle reads
            if (sb_sp_en) begin
                if (sb_sp_we) sb_sp_mem[sb_sp_addr] <= sb_sp_din;
                sb_sp_dout_q <= sb_sp_mem[sb_sp_addr]; // read-first
            end
            sb_sp_valid_q <= sb_sp_en;

            if (sb_dp_wr_en) begin
                sb_dp_mem[sb_dp_wr_addr] <= sb_dp_wr_data;
            end
            if (sb_dp_rd_en) begin
                sb_dp_rd_data_q <= sb_dp_mem[sb_dp_rd_addr]; // read-first
            end
            sb_dp_valid_q <= sb_dp_rd_en;

            // 4. Update MAC Pipeline: Stage 1 -> Stage 2
            sb_mac_valid_s1 <= sb_mac_valid;
            if (sb_mac_valid) begin
                sb_mac_prod_s1  <= $signed(sb_mac_acc) * $signed(sb_mac_mult);
                sb_mac_shift_s1 <= sb_mac_shift;
                sb_mac_relu_s1  <= sb_mac_relu;
            end

            sb_mac_valid_s2 <= sb_mac_valid_s1;
            if (sb_mac_valid_s1) begin
                sb_mac_out_s2 <= calc_requant(sb_mac_prod_s1, sb_mac_shift_s1, sb_mac_relu_s1);
            end

            // 5. Update Signature Accumulator
            exp_dout_valid <= sb_sp_valid_q | sb_dp_valid_q | sb_mac_valid_s2;
            if (sb_sp_valid_q | sb_dp_valid_q | sb_mac_valid_s2) begin
                exp_dout_data <= exp_dout_data ^
                                 (sb_sp_valid_q   ? sb_sp_dout_q    : 8'd0) ^
                                 (sb_dp_valid_q   ? sb_dp_rd_data_q : 8'd0) ^
                                 (sb_mac_valid_s2 ? sb_mac_out_s2   : 8'd0);
            end

            exp_status_flags <= {
                sb_mac_valid_s2,
                sb_sp_valid_q,
                sb_dp_valid_q,
                (sb_mac_out_s2 == 8'sd127) | (sb_mac_out_s2 == -8'sd128)
            };
        end
    end

    // -------------------------------------------------------------------------
    // Test Control & Scoreboard Assertions
    // -------------------------------------------------------------------------
    int total_cycles_checked = 0;
    int pass_count           = 0;
    int fail_count           = 0;

    task check_scoreboard();
        #1; // Sample immediately after active NBA assignments have settled
        total_cycles_checked++;

        // 1. Assert no X/Z in outputs
        if ($isunknown(dout_data)) begin
            fail_count++;
            $display("[FAIL] Time %0t: dout_data contains X/Z (actual = 0x%02h)", $time, dout_data);
        end

        if ($isunknown(dout_valid)) begin
            fail_count++;
            $display("[FAIL] Time %0t: dout_valid is X/Z", $time);
        end

        // 2. Check dout_valid against scoreboard
        if (dout_valid !== exp_dout_valid) begin
            fail_count++;
            $display("[FAIL] Time %0t: dout_valid mismatch (actual=%b, exp=%b)", $time, dout_valid, exp_dout_valid);
        end

        // 3. Check dout_data against scoreboard
        if (dout_data !== exp_dout_data) begin
            fail_count++;
            $display("[FAIL] Time %0t: dout_data mismatch (actual=0x%02h, exp=0x%02h)", $time, dout_data, exp_dout_data);
        end else begin
            pass_count++;
        end

        // 4. Check status_flags against scoreboard
        if (status_flags !== exp_status_flags) begin
            fail_count++;
            $display("[FAIL] Time %0t: status_flags mismatch (actual=%b, exp=%b)", $time, status_flags, exp_status_flags);
        end
    endtask

    initial begin
        $display("================================================================");
        $display("Starting Cycle-Accurate Scoreboard Test for Gowin Microbench Top");
        $display("================================================================");

        rst_n     = 0;
        din_valid = 0;
        din_data  = 0;
        ctrl_mode = 0;

        #20;
        rst_n = 1;
        #20;

        // Phase 1: External stimulus loading (32 cycles)
        $display("[PHASE 1] Loading dynamic stimulus via din_valid (32 patterns)");
        for (int i = 0; i < 32; i++) begin
            @(posedge clk);
            din_valid <= 1'b1;
            din_data  <= (i * 17 + 5) & 8'hFF;
            ctrl_mode <= 2'b00;
            check_scoreboard();
        end

        @(posedge clk);
        din_valid <= 1'b0;
        check_scoreboard();

        // 10 settle cycles
        repeat(10) begin
            @(posedge clk);
            check_scoreboard();
        end

        // Phase 2: LFSR continuous dynamic streaming (100 cycles)
        $display("[PHASE 2] Running continuous LFSR streaming mode (ctrl_mode=01, 100 cycles)");
        @(posedge clk);
        ctrl_mode <= 2'b01;
        check_scoreboard();

        for (int c = 0; c < 100; c++) begin
            @(posedge clk);
            check_scoreboard();
        end

        @(posedge clk);
        ctrl_mode <= 2'b00;
        check_scoreboard();

        repeat(10) begin
            @(posedge clk);
            check_scoreboard();
        end

        $display("================================================================");
        $display("Cycle-Accurate Scoreboard Verification Summary:");
        $display("  Total Cycles Checked:  %0d", total_cycles_checked);
        $display("  Matching Cycles:       %0d", pass_count);
        $display("  Mismatches / X-errors: %0d", fail_count);
        $display("  Final Signature dout:  0x%02h (Expected: 0x%02h)", dout_data, exp_dout_data);
        $display("  Final Status Flags:    4'b%04b (Expected: 4'b%04b)", status_flags, exp_status_flags);
        $display("================================================================");

        if (fail_count == 0 && total_cycles_checked > 140) begin
            $display("[ALL PASS] Microbench top cycle-accurate scoreboard test PASSED 100%%!");
        end else begin
            $fatal(1, "[FATAL ERROR] %0d Scoreboard assertions failed in microbench top!", fail_count);
        end

        $finish;
    end

endmodule
