`timescale 1ns / 1ps

// =============================================================================
// Testbench: tb_gowin_primitives_netlist
// Description: Gate-level post-synthesis netlist verification with Gowin prim_sim.
// =============================================================================

module tb_gowin_primitives_netlist;

    // Gowin Global Set/Reset primitive instance
    GSR GSR (.GSRI(1'b1));

    logic        clk;
    logic        rst_n;
    logic        din_valid;
    logic [7:0]  din_data;
    logic [1:0]  ctrl_mode;
    
    logic        dout_valid;
    logic [7:0]  dout_data;
    logic [3:0]  status_flags;

    // Clock generation (27 MHz ~ 37.037 ns period / 10 ns clock for fast sim)
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Instantiate Gate-Level Netlist Top
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

    int test_count = 0;
    int pass_count = 0;

    initial begin
        $display("================================================================");
        $display("Starting Gowin Post-Synthesis Gate Netlist Verification");
        $display("================================================================");

        rst_n     = 0;
        din_valid = 0;
        din_data  = 0;
        ctrl_mode = 0;

        #100;
        rst_n = 1;
        #100;

        // Phase 1: External stimulus loading
        $display("[PHASE 1] Loading dynamic stimulus via din_valid");
        for (int i = 0; i < 32; i++) begin
            @(posedge clk);
            din_valid <= 1'b1;
            din_data  <= (i * 17 + 5) & 8'hFF;
            ctrl_mode <= 2'b00;
        end
        @(posedge clk);
        din_valid <= 1'b0;

        repeat(10) @(posedge clk);

        // Phase 2: LFSR continuous dynamic streaming
        $display("[PHASE 2] Running continuous LFSR streaming mode (ctrl_mode=01)");
        @(posedge clk);
        ctrl_mode <= 2'b01;

        for (int c = 0; c < 100; c++) begin
            @(posedge clk);
            test_count++;
            if (dout_valid === 1'b1) pass_count++;
        end

        @(posedge clk);
        ctrl_mode <= 2'b00;
        repeat(10) @(posedge clk);

        $display("================================================================");
        $display("Gowin Gate Netlist Verification Summary:");
        $display("  Cycles Monitored:     %0d", test_count);
        $display("  Valid Cycles:         %0d", pass_count);
        $display("  Final Signature dout: 0x%02h", dout_data);
        $display("  Final Status Flags:   4'b%04b", status_flags);
        $display("================================================================");

        if (pass_count > 0) begin
            $display("[ALL PASS] Gowin gate-level netlist simulation completed successfully!");
        end else begin
            $fatal(1, "[FAIL] Gowin gate netlist simulation produced no valid activity!");
        end

        $finish;
    end

endmodule
