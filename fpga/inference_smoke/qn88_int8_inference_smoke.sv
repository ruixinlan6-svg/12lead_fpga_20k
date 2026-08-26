`timescale 1ns/1ps

// QN88 SRAM-only arithmetic/inference smoke. This is intentionally a known
// vector, not a claim of full ECG model accuracy: it proves the frozen INT8
// MAC handshake and requantization path on the target device.
module qn88_int8_inference_smoke (
    input  wire       clk,
    input  wire       rst_btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [5:0] led
);
    localparam [2:0] ST_START  = 3'd0;
    localparam [2:0] ST_STREAM = 3'd1;
    localparam [2:0] ST_WAIT   = 3'd2;
    localparam [2:0] ST_DONE   = 3'd3;
    localparam [2:0] ST_FAIL   = 3'd4;

    wire rst_n = ~rst_btn;
    reg [2:0] state;
    reg [2:0] index;
    wire mac_start = (state == ST_START);
    wire in_valid = (state == ST_STREAM);
    wire in_last = (state == ST_STREAM) && (index == 3'd7);
    wire mac_busy;
    wire mac_done;
    wire signed [31:0] mac_result;
    reg signed [7:0] activation;
    reg signed [7:0] weight;
    wire signed [7:0] quantized;
    wire signed [31:0] zero_offset = 32'sd0;
    wire signed [31:0] unit_multiplier = 32'sd1;
    reg [23:0] uart_timer;
    reg uart_start_reg;
    reg [255:0] uart_frame;
    wire uart_busy;
    wire uart_done;

    function [7:0] hex_ascii;
        input [3:0] nibble;
        begin
            if (nibble < 4'd10)
                hex_ascii = "0" + nibble;
            else
                hex_ascii = "A" + (nibble - 4'd10);
        end
    endfunction

    always @* begin
        activation = 8'sd0;
        weight = 8'sd0;
        case (index)
            3'd0: begin activation = 8'sd1;  weight = 8'sd2;  end
            3'd1: begin activation = -8'sd2; weight = -8'sd3; end
            3'd2: begin activation = 8'sd3;  weight = 8'sd4;  end
            3'd3: begin activation = -8'sd4; weight = -8'sd5; end
            3'd4: begin activation = 8'sd5;  weight = 8'sd6;  end
            3'd5: begin activation = -8'sd6; weight = -8'sd7; end
            3'd6: begin activation = 8'sd7;  weight = 8'sd8;  end
            3'd7: begin activation = -8'sd8; weight = -8'sd9; end
            default: begin activation = 8'sd0; weight = 8'sd0; end
        endcase
    end

    conv1d_mac_int8_gowin #(.ACC_WIDTH(32)) mac (
        .clk(clk), .rst_n(rst_n), .start(mac_start),
        .in_valid(in_valid), .in_last(in_last),
        .activation(activation), .weight(weight),
        .busy(mac_busy), .done(mac_done), .result(mac_result)
    );

    requantize_clip_gowin #(.ACC_WIDTH(32), .MULT_WIDTH(32), .OUT_WIDTH(8)) rq (
        .acc(mac_result), .offset(zero_offset),
        .multiplier(unit_multiplier), .shift(6'd1), .result(quantized)
    );

    // Little-endian frame: "INFER D=00F0 Q=78 P=1\r\n" (23 bytes).
    always @* begin
        uart_frame = 256'd0;
        uart_frame[8*0 +: 8]  = "I";
        uart_frame[8*1 +: 8]  = "N";
        uart_frame[8*2 +: 8]  = "F";
        uart_frame[8*3 +: 8]  = "E";
        uart_frame[8*4 +: 8]  = "R";
        uart_frame[8*5 +: 8]  = " ";
        uart_frame[8*6 +: 8]  = "D";
        uart_frame[8*7 +: 8]  = "=";
        uart_frame[8*8 +: 8]  = hex_ascii(mac_result[15:12]);
        uart_frame[8*9 +: 8]  = hex_ascii(mac_result[11:8]);
        uart_frame[8*10 +: 8] = hex_ascii(mac_result[7:4]);
        uart_frame[8*11 +: 8] = hex_ascii(mac_result[3:0]);
        uart_frame[8*12 +: 8] = " ";
        uart_frame[8*13 +: 8] = "Q";
        uart_frame[8*14 +: 8] = "=";
        uart_frame[8*15 +: 8] = hex_ascii(quantized[7:4]);
        uart_frame[8*16 +: 8] = hex_ascii(quantized[3:0]);
        uart_frame[8*17 +: 8] = " ";
        uart_frame[8*18 +: 8] = "P";
        uart_frame[8*19 +: 8] = "=";
        uart_frame[8*20 +: 8] = (state == ST_DONE) ? "1" : "0";
        uart_frame[8*21 +: 8] = 8'h0D;
        uart_frame[8*22 +: 8] = 8'h0A;
    end

    qn88_uart_frame_tx uart_status_tx (
        .clk(clk), .rst_n(rst_n), .start(uart_start_reg),
        .frame_data(uart_frame), .frame_len(6'd23),
        .tx(uart_tx), .busy(uart_busy), .done(uart_done)
    );

    // Keep RX present for the documented BL616 return path; this smoke is
    // intentionally receive-inert and performs only passive reporting.
    wire uart_rx_unused = uart_rx;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_START;
            index <= 3'd0;
            uart_timer <= 24'd0;
            uart_start_reg <= 1'b0;
        end else begin
            uart_start_reg <= 1'b0;
            if ((uart_timer == 24'd6749999) && !uart_busy) begin
                uart_timer <= 24'd0;
                uart_start_reg <= 1'b1;
            end else if (!uart_busy) begin
                uart_timer <= uart_timer + 1'b1;
            end
            case (state)
                ST_START: begin
                    index <= 3'd0;
                    state <= ST_STREAM;
                end
                ST_STREAM: begin
                    if (index == 3'd7)
                        state <= ST_WAIT;
                    else
                        index <= index + 1'b1;
                end
                ST_WAIT: begin
                    if (mac_done) begin
                        if ((mac_result == 32'sd240) && (quantized == 8'sd120))
                            state <= ST_DONE;
                        else
                            state <= ST_FAIL;
                    end
                end
                default: state <= state;
            endcase
        end
    end

    // LEDs are active-low on Tang Nano 20K:
    // LED0 started, LED1 pass, LED2 fail, LED3 MAC busy, LED4 MAC done,
    // LED5 requantized result equals 120.
    assign led[0] = ~(state != ST_START);
    assign led[1] = ~(state == ST_DONE);
    assign led[2] = ~(state == ST_FAIL);
    assign led[3] = ~mac_busy;
    assign led[4] = ~mac_done;
    assign led[5] = ~(quantized == 8'sd120);
endmodule
