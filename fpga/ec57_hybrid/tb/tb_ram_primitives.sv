`timescale 1ns / 1ps

// =============================================================================
// Testbench: tb_ram_primitives
// Description: Comprehensive self-checking testbench for ecg_sync_sp_ram and
//              ecg_sync_dp_ram primitives.
//
// Test Coverage:
//   1. Normal write and read cycles across depths.
//   2. Read-First address collision on SP RAM (same addr write + read).
//   3. Read-First address collision on DP RAM (wr_addr == rd_addr, wr_en & rd_en).
//   4. Boundary address testing (addr = 0, DEPTH-1, DEPTH/2).
//   5. First legal read immediately after reset release; RAM contents retained.
//   6. Continuous no-bubble reads and 32-cycle concurrent DP read/write.
//   7. Enable bubbles hold the prior output and recover on the next legal read.
//   8. Parameterization matrix: 8-bit, 16-bit, 32-bit data widths.
// =============================================================================

module tb_ram_primitives;

    logic clk;
    logic rst_n;

    // Clock generation (10 ns clock period)
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Error and test counters
    int total_tests = 0;
    int pass_count  = 0;
    int fail_count  = 0;
    logic [7:0] sp1_hold_expected;
    logic [7:0] dp1_hold_expected;

    // -------------------------------------------------------------------------
    // DUT 1: Single-Port RAM (8-bit, 256 Depth)
    // -------------------------------------------------------------------------
    localparam int SP1_WIDTH = 8;
    localparam int SP1_DEPTH = 256;
    localparam int SP1_AW    = $clog2(SP1_DEPTH);

    logic                  sp1_en;
    logic                  sp1_we;
    logic [SP1_AW-1:0]     sp1_addr;
    logic [SP1_WIDTH-1:0]  sp1_din;
    logic [SP1_WIDTH-1:0]  sp1_dout;

    ecg_sync_sp_ram #(
        .DATA_WIDTH (SP1_WIDTH),
        .DEPTH      (SP1_DEPTH)
    ) u_sp_ram_8b (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (sp1_en),
        .we    (sp1_we),
        .addr  (sp1_addr),
        .din   (sp1_din),
        .dout  (sp1_dout)
    );

    // -------------------------------------------------------------------------
    // DUT 2: Single-Port RAM (16-bit, 32 Depth) - Parameterization Test
    // -------------------------------------------------------------------------
    localparam int SP2_WIDTH = 16;
    localparam int SP2_DEPTH = 32;
    localparam int SP2_AW    = $clog2(SP2_DEPTH);

    logic                  sp2_en;
    logic                  sp2_we;
    logic [SP2_AW-1:0]     sp2_addr;
    logic [SP2_WIDTH-1:0]  sp2_din;
    logic [SP2_WIDTH-1:0]  sp2_dout;

    ecg_sync_sp_ram #(
        .DATA_WIDTH (SP2_WIDTH),
        .DEPTH      (SP2_DEPTH)
    ) u_sp_ram_16b (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (sp2_en),
        .we    (sp2_we),
        .addr  (sp2_addr),
        .din   (sp2_din),
        .dout  (sp2_dout)
    );

    // -------------------------------------------------------------------------
    // DUT 3: Simple Dual-Port RAM (8-bit, 256 Depth)
    // -------------------------------------------------------------------------
    localparam int DP1_WIDTH = 8;
    localparam int DP1_DEPTH = 256;
    localparam int DP1_AW    = $clog2(DP1_DEPTH);

    logic                  dp1_wr_en;
    logic [DP1_AW-1:0]     dp1_wr_addr;
    logic [DP1_WIDTH-1:0]  dp1_wr_data;
    logic                  dp1_rd_en;
    logic [DP1_AW-1:0]     dp1_rd_addr;
    logic [DP1_WIDTH-1:0]  dp1_rd_data;

    ecg_sync_dp_ram #(
        .DATA_WIDTH (DP1_WIDTH),
        .DEPTH      (DP1_DEPTH)
    ) u_dp_ram_8b (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (dp1_wr_en),
        .wr_addr (dp1_wr_addr),
        .wr_data (dp1_wr_data),
        .rd_en   (dp1_rd_en),
        .rd_addr (dp1_rd_addr),
        .rd_data (dp1_rd_data)
    );

    // -------------------------------------------------------------------------
    // DUT 4: Simple Dual-Port RAM (32-bit, 64 Depth) - Parameterization Test
    // -------------------------------------------------------------------------
    localparam int DP2_WIDTH = 32;
    localparam int DP2_DEPTH = 64;
    localparam int DP2_AW    = $clog2(DP2_DEPTH);

    logic                  dp2_wr_en;
    logic [DP2_AW-1:0]     dp2_wr_addr;
    logic [DP2_WIDTH-1:0]  dp2_wr_data;
    logic                  dp2_rd_en;
    logic [DP2_AW-1:0]     dp2_rd_addr;
    logic [DP2_WIDTH-1:0]  dp2_rd_data;

    ecg_sync_dp_ram #(
        .DATA_WIDTH (DP2_WIDTH),
        .DEPTH      (DP2_DEPTH)
    ) u_dp_ram_32b (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (dp2_wr_en),
        .wr_addr (dp2_wr_addr),
        .wr_data (dp2_wr_data),
        .rd_en   (dp2_rd_en),
        .rd_addr (dp2_rd_addr),
        .rd_data (dp2_rd_data)
    );

    // Task for assertion check
    task check_val(input string tag, input logic [31:0] actual, input logic [31:0] expected);
        total_tests++;
        if (actual === expected) begin
            pass_count++;
        end else begin
            fail_count++;
            $display("[FAIL] %s: actual=0x%0h expected=0x%0h at time %0t", tag, actual, expected, $time);
        end
    endtask

    // Main Test Stimulus
    initial begin
        $display("================================================================");
        $display("Starting RAM Primitives Testbench (SP & DP Synchronous RAM)");
        $display("================================================================");

        // Initial signal states
        rst_n       = 0;
        sp1_en      = 0;
        sp1_we      = 0;
        sp1_addr    = 0;
        sp1_din     = 0;
        sp2_en      = 0;
        sp2_we      = 0;
        sp2_addr    = 0;
        sp2_din     = 0;
        dp1_wr_en   = 0;
        dp1_wr_addr = 0;
        dp1_wr_data = 0;
        dp1_rd_en   = 0;
        dp1_rd_addr = 0;
        dp2_wr_en   = 0;
        dp2_wr_addr = 0;
        dp2_wr_data = 0;
        dp2_rd_en   = 0;
        dp2_rd_addr = 0;

        // Reset pulse
        #20;
        rst_n = 1;
        #20;

        // ---------------------------------------------------------------------
        // TEST 1: SP RAM 8-bit Normal Write and Sequential Read
        // ---------------------------------------------------------------------
        $display("[TEST 1] SP RAM 8-bit: Sequential Write and Read");
        for (int a = 0; a < SP1_DEPTH; a++) begin
            @(posedge clk);
            sp1_en   <= 1'b1;
            sp1_we   <= 1'b1;
            sp1_addr <= a[SP1_AW-1:0];
            sp1_din  <= (a ^ 8'hA5);
        end
        @(posedge clk);
        sp1_we <= 1'b0;

        for (int a = 0; a < SP1_DEPTH; a++) begin
            @(posedge clk);
            sp1_en   <= 1'b1;
            sp1_we   <= 1'b0;
            sp1_addr <= a[SP1_AW-1:0];
            @(posedge clk); // 1-cycle read latency
            #1;
            check_val($sformatf("SP1 Read addr %0d", a), sp1_dout, (a ^ 8'hA5));
        end

        // ---------------------------------------------------------------------
        // TEST 2: SP RAM Read-First Collision Semantics
        // ---------------------------------------------------------------------
        $display("[TEST 2] SP RAM 8-bit: Read-First Collision (we=1, reading same addr)");
        // Write initial known value at address 42
        @(posedge clk);
        sp1_en   <= 1'b1;
        sp1_we   <= 1'b1;
        sp1_addr <= 8'd42;
        sp1_din  <= 8'h55; // Initial value
        @(posedge clk);
        sp1_we   <= 1'b0;

        // Now perform simultaneous write 8'hAA and read at addr 42
        @(posedge clk);
        sp1_en   <= 1'b1;
        sp1_we   <= 1'b1;
        sp1_addr <= 8'd42;
        sp1_din  <= 8'hAA; // New value written

        // At next clock edge, dout MUST be the OLD value (8'h55)
        @(posedge clk);
        #1;
        sp1_we   <= 1'b0;
        check_val("SP1 Read-First Collision: should return old value 0x55", sp1_dout, 8'h55);

        // In subsequent read, dout MUST be the NEW value (8'hAA)
        @(posedge clk);
        #1;
        check_val("SP1 Read After Collision: should return new value 0xAA", sp1_dout, 8'hAA);

        // ---------------------------------------------------------------------
        // TEST 3: SP RAM Boundary Addresses
        // ---------------------------------------------------------------------
        $display("[TEST 3] SP RAM 8-bit: Boundary Addresses (0, 128, 255)");
        // Write boundary addresses
        @(posedge clk);
        sp1_en   <= 1'b1; sp1_we <= 1'b1; sp1_addr <= 8'd0;   sp1_din <= 8'h11;
        @(posedge clk);
        sp1_en   <= 1'b1; sp1_we <= 1'b1; sp1_addr <= 8'd128; sp1_din <= 8'h22;
        @(posedge clk);
        sp1_en   <= 1'b1; sp1_we <= 1'b1; sp1_addr <= 8'd255; sp1_din <= 8'h33;
        @(posedge clk);
        sp1_we <= 1'b0;

        @(posedge clk); sp1_addr <= 8'd0;
        @(posedge clk); #1; check_val("SP1 Boundary addr 0", sp1_dout, 8'h11);
        sp1_addr <= 8'd128;
        @(posedge clk); #1; check_val("SP1 Boundary addr 128", sp1_dout, 8'h22);
        sp1_addr <= 8'd255;
        @(posedge clk); #1; check_val("SP1 Boundary addr 255", sp1_dout, 8'h33);

        // ---------------------------------------------------------------------
        // TEST 4: SP RAM 16-bit Parameterization Test
        // ---------------------------------------------------------------------
        $display("[TEST 4] SP RAM 16-bit: Parameterization & Boundary Check");
        for (int a = 0; a < SP2_DEPTH; a++) begin
            @(posedge clk);
            sp2_en   <= 1'b1;
            sp2_we   <= 1'b1;
            sp2_addr <= a[SP2_AW-1:0];
            sp2_din  <= (16'h5A00 + a);
        end
        @(posedge clk);
        sp2_we <= 1'b0;

        for (int a = 0; a < SP2_DEPTH; a++) begin
            @(posedge clk);
            sp2_en   <= 1'b1;
            sp2_we   <= 1'b0;
            sp2_addr <= a[SP2_AW-1:0];
            @(posedge clk);
            #1;
            check_val($sformatf("SP2 16-bit Read addr %0d", a), sp2_dout, (16'h5A00 + a));
        end

        // ---------------------------------------------------------------------
        // TEST 5: DP RAM 8-bit Normal Independent Write & Read
        // ---------------------------------------------------------------------
        $display("[TEST 5] DP RAM 8-bit: Independent Write and Read Ports");
        for (int a = 0; a < DP1_DEPTH; a++) begin
            @(posedge clk);
            dp1_wr_en   <= 1'b1;
            dp1_wr_addr <= a[DP1_AW-1:0];
            dp1_wr_data <= ((a * 3 + 7) & 8'hFF);
        end
        @(posedge clk);
        dp1_wr_en <= 1'b0;

        for (int a = 0; a < DP1_DEPTH; a++) begin
            @(posedge clk);
            dp1_rd_en   <= 1'b1;
            dp1_rd_addr <= a[DP1_AW-1:0];
            @(posedge clk);
            #1;
            check_val($sformatf("DP1 Read addr %0d", a), dp1_rd_data, ((a * 3 + 7) & 8'hFF));
        end

        // ---------------------------------------------------------------------
        // TEST 6: DP RAM Same-Address Collision (Read-First Semantics)
        // ---------------------------------------------------------------------
        $display("[TEST 6] DP RAM 8-bit: Same-Address Collision (wr_addr == rd_addr)");
        // Write initial known value at address 100
        @(posedge clk);
        dp1_wr_en   <= 1'b1;
        dp1_wr_addr <= 8'd100;
        dp1_wr_data <= 8'h3C;
        @(posedge clk);
        dp1_wr_en   <= 1'b0;

        // Perform simultaneous write 8'hC3 to addr 100 and read from addr 100
        @(posedge clk);
        dp1_wr_en   <= 1'b1;
        dp1_wr_addr <= 8'd100;
        dp1_wr_data <= 8'hC3; // New value written
        dp1_rd_en   <= 1'b1;
        dp1_rd_addr <= 8'd100; // Same address read

        // At next clock edge, rd_data MUST receive the OLD value (8'h3C)
        @(posedge clk);
        #1;
        dp1_wr_en   <= 1'b0;
        check_val("DP1 Collision: read-first returns old value 0x3C", dp1_rd_data, 8'h3C);

        // In subsequent cycle, reading addr 100 returns the updated value (8'hC3)
        @(posedge clk);
        #1;
        check_val("DP1 Next Cycle: returns updated value 0xC3", dp1_rd_data, 8'hC3);

        // ---------------------------------------------------------------------
        // TEST 7: DP RAM Simultaneous R/W to Different Addresses
        // ---------------------------------------------------------------------
        $display("[TEST 7] DP RAM 8-bit: Simultaneous R/W to Different Addresses");
        @(posedge clk);
        dp1_wr_en   <= 1'b1;
        dp1_wr_addr <= 8'd10;
        dp1_wr_data <= 8'h77;
        dp1_rd_en   <= 1'b1;
        dp1_rd_addr <= 8'd100; // Reading previously written 0xC3
        @(posedge clk);
        #1;
        check_val("DP1 Simultaneous: read addr 100 while writing addr 10", dp1_rd_data, 8'hC3);
        dp1_wr_en   <= 1'b0;
        dp1_rd_en   <= 1'b1;
        dp1_rd_addr <= 8'd10;  // Now read addr 10
        @(posedge clk);
        #1;
        check_val("DP1 Read newly written addr 10", dp1_rd_data, 8'h77);

        // ---------------------------------------------------------------------
        // TEST 8: DP RAM 32-bit Parameterization & Boundary
        // ---------------------------------------------------------------------
        $display("[TEST 8] DP RAM 32-bit: Parameterization & Boundary");
        @(posedge clk);
        dp2_wr_en   <= 1'b1; dp2_wr_addr <= 6'd0;  dp2_wr_data <= 32'hDEADBEEF;
        @(posedge clk);
        dp2_wr_en   <= 1'b1; dp2_wr_addr <= 6'd63; dp2_wr_data <= 32'hCAFE1234;
        @(posedge clk);
        dp2_wr_en   <= 1'b0;

        @(posedge clk);
        dp2_rd_en   <= 1'b1; dp2_rd_addr <= 6'd0;
        @(posedge clk);
        #1;
        check_val("DP2 Boundary addr 0", dp2_rd_data, 32'hDEADBEEF);
        dp2_rd_addr <= 6'd63;
        @(posedge clk);
        #1;
        check_val("DP2 Boundary addr 63", dp2_rd_data, 32'hCAFE1234);

        // ---------------------------------------------------------------------
        // TEST 9: No-Bubble Continuous DP Read/Write and Enable Hold
        // ---------------------------------------------------------------------
        $display("[TEST 9] DP RAM: 32-Cycle No-Bubble Concurrent R/W and Enable Hold");

        // Seed DP2 addresses 0..31. Inputs are driven on the falling edge so
        // they are stable before each DUT sampling edge.
        for (int a = 0; a < 32; a++) begin
            @(negedge clk);
            dp2_wr_en   = 1'b1;
            dp2_wr_addr = a[DP2_AW-1:0];
            dp2_wr_data = 32'h1000_0000 + a;
            dp2_rd_en   = 1'b0;
            @(posedge clk);
        end

        // For 32 consecutive cycles, read the seeded half while writing the
        // upper half. There is no idle cycle between accepted reads.
        for (int a = 0; a < 32; a++) begin
            @(negedge clk);
            dp2_wr_en   = 1'b1;
            dp2_wr_addr = (a + 32);
            dp2_wr_data = 32'h2000_0000 + a;
            dp2_rd_en   = 1'b1;
            dp2_rd_addr = a[DP2_AW-1:0];
            @(posedge clk);
            #1;
            check_val($sformatf("DP2 Continuous old-half read addr %0d", a),
                      dp2_rd_data, 32'h1000_0000 + a);
        end

        // Read the newly written upper half with one accepted read per cycle.
        for (int a = 0; a < 32; a++) begin
            @(negedge clk);
            dp2_wr_en   = 1'b0;
            dp2_rd_en   = 1'b1;
            dp2_rd_addr = (a + 32);
            @(posedge clk);
            #1;
            check_val($sformatf("DP2 Continuous new-half read addr %0d", a + 32),
                      dp2_rd_data, 32'h2000_0000 + a);
        end

        // A disabled read must hold the prior output even if addresses change.
        @(negedge clk);
        sp1_hold_expected = sp1_dout;
        dp1_hold_expected = dp1_rd_data;
        sp1_en      = 1'b0;
        sp1_we      = 1'b0;
        sp1_addr    = 8'd0;
        dp1_rd_en   = 1'b0;
        dp1_rd_addr = 8'd0;
        dp2_rd_en   = 1'b0;
        repeat (2) @(posedge clk);
        #1;
        check_val("SP1 output holds across enable bubble", sp1_dout, sp1_hold_expected);
        check_val("DP1 output holds across enable bubble", dp1_rd_data, dp1_hold_expected);

        // The first read after the bubble must return the newly requested data.
        @(negedge clk);
        sp1_en      = 1'b1;
        sp1_we      = 1'b0;
        sp1_addr    = 8'd42;
        dp1_rd_en   = 1'b1;
        dp1_rd_addr = 8'd10;
        @(posedge clk);
        #1;
        check_val("SP1 recovery immediately after enable bubble", sp1_dout, 8'hAA);
        check_val("DP1 recovery immediately after enable bubble", dp1_rd_data, 8'h77);

        // ---------------------------------------------------------------------
        // TEST 10: Reset Assertion and First Legal Read after Release
        // ---------------------------------------------------------------------
        $display("[TEST 10] Reset Contract: First Legal Read after Release");
        // RAM rst_n is intentionally not part of the data path. The caller
        // holds enables low during reset, then presents the first legal request.
        @(negedge clk);
        rst_n       = 1'b0;
        sp1_en      = 1'b0;
        dp1_rd_en   = 1'b0;
        repeat(5) @(posedge clk);

        @(negedge clk);
        rst_n       = 1'b1;
        sp1_en      = 1'b1;
        sp1_we      = 1'b0;
        sp1_addr    = 8'd42;
        dp1_rd_en   = 1'b1;
        dp1_rd_addr = 8'd10;
        @(posedge clk);
        #1;
        check_val("SP1 first read after reset release", sp1_dout, 8'hAA);
        check_val("DP1 first read after reset release", dp1_rd_data, 8'h77);

        // ---------------------------------------------------------------------
        // Final Summary
        // ---------------------------------------------------------------------
        #20;
        $display("================================================================");
        $display("RAM Primitives Test Summary:");
        $display("  Total Tests: %0d", total_tests);
        $display("  Passed:      %0d", pass_count);
        $display("  Failed:      %0d", fail_count);
        if (fail_count == 0) begin
            $display("[ALL PASS] All RAM Primitive tests completed successfully!");
        end else begin
            $display("[FATAL ERROR] %0d RAM Primitive tests failed!", fail_count);
        end
        $display("================================================================");

        if (fail_count != 0)
            $fatal(1, "%0d RAM primitive tests failed", fail_count);
        else
            $finish;
    end

endmodule
