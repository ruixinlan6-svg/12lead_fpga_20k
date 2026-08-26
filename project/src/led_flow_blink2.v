// =============================================================================
// Project     : Tang Nano 20K LED Flow Blink Twice
// Module      : led_flow_blink2
// Description : Controls 6 onboard LEDs to blink alternately twice in turn.
//               Each LED blinks ON-OFF-ON-OFF before shifting to the next LED.
// Target FPGA : Gowin GW2AR-18C (Tang Nano 20K)
// Clock       : 27 MHz onboard active crystal oscillator
// Polarity    : LEDs are active-low (0 = ON, 1 = OFF).
//               S1 button on Tang Nano 20K is active-high (0 = Released, 1 = Pressed).
// =============================================================================

`timescale 1ns / 1ps

module led_flow_blink2 #(
    parameter CLK_FREQ_HZ         = 27_000_000, // 27 MHz system clock
    parameter HALF_PERIOD_MS      = 200,        // 200 ms per half-blink (ON/OFF duration)
    parameter BLINK_TIMES         = 2,          // Number of blinks per LED (2 times)
    parameter NUM_LEDS            = 6,          // 6 user LEDs on Tang Nano 20K
    // Parameter calculation: number of clock cycles per half period
    parameter HALF_PERIOD_CYCLES  = (CLK_FREQ_HZ / 1000) * HALF_PERIOD_MS
)(
    input  wire                  clk,     // 27 MHz system clock (Pin 4)
    input  wire                  rst_btn, // S1 button (Pin 88, 0=Released/Normal, 1=Pressed/Reset)
    output reg  [NUM_LEDS-1:0]   led      // 6 active-low LEDs (Pin 15..20, 0=ON, 1=OFF)
);

    // Total half-periods per LED = BLINK_TIMES * 2 (e.g. 2 blinks = 4 half-periods: ON, OFF, ON, OFF)
    localparam TOTAL_STEPS_PER_LED = BLINK_TIMES * 2;

    // Width of step counter
    localparam STEP_CNT_WIDTH = 4;
    localparam LED_IDX_WIDTH  = 3;

    // Power-on auto reset counter (holds reset for the first 255 cycles after power-up)
    reg [7:0] por_cnt = 8'd0;
    wire sys_rst = (por_cnt < 8'd255) || (rst_btn == 1'b1);

    always @(posedge clk) begin
        if (por_cnt < 8'd255) begin
            por_cnt <= por_cnt + 1'b1;
        end
    end

    // Clock divider counter
    reg [31:0] clk_cnt;

    // Current step within a single LED's blink cycle (0 = 1st ON, 1 = 1st OFF, 2 = 2nd ON, 3 = 2nd OFF)
    reg [STEP_CNT_WIDTH-1:0] step_cnt;

    // Index of current active LED (0 to NUM_LEDS - 1)
    reg [LED_IDX_WIDTH-1:0]  led_idx;

    // -------------------------------------------------------------------------
    // Main Timing and Sequencing FSM
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (sys_rst) begin
            clk_cnt  <= 32'd0;
            step_cnt <= {STEP_CNT_WIDTH{1'b0}};
            led_idx  <= {LED_IDX_WIDTH{1'b0}};
        end else begin
            if (clk_cnt >= (HALF_PERIOD_CYCLES - 1)) begin
                clk_cnt <= 32'd0;

                // Advance blink step
                if (step_cnt >= (TOTAL_STEPS_PER_LED - 1)) begin
                    step_cnt <= {STEP_CNT_WIDTH{1'b0}};
                    // Advance LED index in round-robin fashion
                    if (led_idx >= (NUM_LEDS - 1)) begin
                        led_idx <= {LED_IDX_WIDTH{1'b0}};
                    end else begin
                        led_idx <= led_idx + 1'b1;
                    end
                end else begin
                    step_cnt <= step_cnt + 1'b1;
                end
            end else begin
                clk_cnt <= clk_cnt + 1'b1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Output Generation (Active-Low)
    // -------------------------------------------------------------------------
    // When step_cnt[0] == 0: ON state (steps 0, 2, ...) -> targeted LED drives '0' (lit)
    // When step_cnt[0] == 1: OFF state (steps 1, 3, ...) -> all LEDs drive '1' (extinguished)
    integer i;
    always @(*) begin
        if (sys_rst) begin
            led = {NUM_LEDS{1'b1}}; // All LEDs OFF during reset
        end else begin
            for (i = 0; i < NUM_LEDS; i = i + 1) begin
                if ((i == led_idx) && (step_cnt[0] == 1'b0)) begin
                    led[i] = 1'b0; // Active-Low ON
                end else begin
                    led[i] = 1'b1; // OFF
                end
            end
        end
    end

endmodule
