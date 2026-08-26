`timescale 1ns / 1ps

module tb_led_flow_blink2;

    localparam TEST_HALF_CYCLES = 10;
    localparam TEST_NUM_LEDS    = 6;
    localparam TEST_BLINKS      = 2;

    reg                       clk;
    reg                       rst_btn;
    wire [TEST_NUM_LEDS-1:0]  led;

    // Instantiate DUT with fast parameters for simulation
    led_flow_blink2 #(
        .CLK_FREQ_HZ(1000),
        .HALF_PERIOD_MS(10),
        .BLINK_TIMES(TEST_BLINKS),
        .NUM_LEDS(TEST_NUM_LEDS),
        .HALF_PERIOD_CYCLES(TEST_HALF_CYCLES)
    ) dut (
        .clk(clk),
        .rst_btn(rst_btn),
        .led(led)
    );

    // Clock generation: 20ns period (50 MHz sim clock)
    always #10 clk = ~clk;

    integer current_led, blink_num, err_count;

    initial begin
        $dumpfile("tb_led_flow_blink2.vcd");
        $dumpvars(0, tb_led_flow_blink2);

        clk = 0;
        rst_btn = 1; // Assert S1 reset initially
        err_count = 0;

        $display("=========================================================");
        $display("   Level 1 Testbench: Auto-Run & S1 Reset Verification    ");
        $display("=========================================================");

        // Wait during reset
        repeat (300) @(posedge clk);
        #1;
        if (led !== 6'b111111) begin
            $display("[FAIL] Reset state mismatch! Expected 6'b111111, got %b", led);
            err_count = err_count + 1;
        end else begin
            $display("[PASS] Reset state verified: all LEDs OFF (%b)", led);
        end

        // Release S1 button (rst_btn = 0)
        @(posedge clk);
        #1 rst_btn = 0;

        // Test 2 full rounds of 6 LEDs
        repeat (2) begin
            for (current_led = 0; current_led < TEST_NUM_LEDS; current_led = current_led + 1) begin
                for (blink_num = 0; blink_num < TEST_BLINKS; blink_num = blink_num + 1) begin
                    // Phase ON: middle of half-period
                    repeat (TEST_HALF_CYCLES / 2) @(posedge clk);
                    #1;
                    if (led[current_led] !== 1'b0 || (led | (1 << current_led)) !== 6'b111111) begin
                        $display("[FAIL] LED %0d Blink %0d ON phase mismatch! led = %b", current_led, blink_num, led);
                        err_count = err_count + 1;
                    end else begin
                        $display("[INFO] LED %0d Blink %0d ON  phase OK: led = %b", current_led, blink_num, led);
                    end
                    repeat (TEST_HALF_CYCLES / 2) @(posedge clk);

                    // Phase OFF: middle of half-period
                    repeat (TEST_HALF_CYCLES / 2) @(posedge clk);
                    #1;
                    if (led !== 6'b111111) begin
                        $display("[FAIL] LED %0d Blink %0d OFF phase mismatch! led = %b", current_led, blink_num, led);
                        err_count = err_count + 1;
                    end else begin
                        $display("[INFO] LED %0d Blink %0d OFF phase OK: led = %b", current_led, blink_num, led);
                    end
                    repeat (TEST_HALF_CYCLES / 2) @(posedge clk);
                end
            end
        end

        // Test manual press of S1 (rst_btn = 1)
        @(posedge clk);
        #1 rst_btn = 1;
        #50;
        if (led !== 6'b111111) begin
            $display("[FAIL] S1 press reset mismatch! Expected 6'b111111, got %b", led);
            err_count = err_count + 1;
        end else begin
            $display("[PASS] S1 press reset verified: all LEDs OFF (%b)", led);
        end
        @(posedge clk);
        #1 rst_btn = 0;

        #200;
        $display("---------------------------------------------------------");
        if (err_count == 0) begin
            $display("[SUCCESS] Auto-run & S1 button test cases PASSED!");
        end else begin
            $display("[FAILED] Testbench encountered %0d errors!", err_count);
        end
        $display("=========================================================");
        $finish;
    end

endmodule
