`timescale 1ns/1ps

// QN88 model-level integration.
//
// Host protocol (115200 8-N-1, volatile SRAM configuration only):
//   "ECG0" magic, 12,000 signed-INT8 input bytes, then 10,293 signed-INT8
//   parameter bytes in the order W1/B1/W2/B2/W3/B3/WH/BH.
//   The board executes the 10-layer TinyECGCNN forward inference and returns:
//   ECG P[0|1] S[0|1] D[0|1] <five signed INT8 logits as hex>\r\n
module qn88_model_full_top #(
    parameter integer CLK_HZ = 27000000,
    parameter integer BAUD = 115200
) (
    input  wire       clk,
    input  wire       rst_btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [5:0] led,
    output wire       O_sdram_clk,
    output wire       O_sdram_cke,
    output wire       O_sdram_cs_n,
    output wire       O_sdram_cas_n,
    output wire       O_sdram_ras_n,
    output wire       O_sdram_wen_n,
    output wire [3:0] O_sdram_dqm,
    output wire [10:0] O_sdram_addr,
    output wire [1:0] O_sdram_ba,
    inout  wire [31:0] IO_sdram_dq
);
    localparam integer DATA_WIDTH = 32;
    localparam integer USER_ADDR_WIDTH = 21;
    localparam integer WEIGHT_BYTES = 10293;

    localparam [3:0] LOAD_INPUT = 4'd0;
    localparam [3:0] LOAD_W1    = 4'd1;
    localparam [3:0] LOAD_B1    = 4'd2;
    localparam [3:0] LOAD_W2    = 4'd3;
    localparam [3:0] LOAD_B2    = 4'd4;
    localparam [3:0] LOAD_W3    = 4'd5;
    localparam [3:0] LOAD_B3    = 4'd6;
    localparam [3:0] LOAD_WH    = 4'd7;
    localparam [3:0] LOAD_BH    = 4'd8;

    wire button_rst_n = ~rst_btn;
    reg [15:0] por_cnt = 16'd0;
    wire por_done = &por_cnt;
    wire rst_n = button_rst_n && por_done;

    always @(posedge clk or negedge button_rst_n) begin
        if (!button_rst_n)
            por_cnt <= 16'd0;
        else if (!por_done)
            por_cnt <= por_cnt + 1'b1;
    end

    wire rx_byte_valid;
    wire [7:0] rx_byte;
    wire rx_framing_error;
    qn88_uart_byte_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) uart_rx_i (
        .clk(clk), .rst_n(rst_n), .rx(uart_rx),
        .byte_valid(rx_byte_valid), .byte_data(rx_byte),
        .framing_error(rx_framing_error)
    );

    wire [DATA_WIDTH-1:0] sdrc_data_out;
    wire [DATA_WIDTH-1:0] sdrc_data_in = 32'd0;
    wire [USER_ADDR_WIDTH-1:0] sdrc_addr = {2'd2, 11'd2, 8'd5};
    wire [7:0] sdrc_data_len = 8'd25;
    wire [DATA_WIDTH/8-1:0] sdrc_dqm = 4'b0000;
    wire sdrc_wr_n = 1'b1;
    wire sdrc_rd_n = 1'b1;
    wire sdrc_selfrefresh = 1'b0;
    wire sdrc_power_down = 1'b0;
    wire sdrc_init_done;
    wire sdrc_busy_n;
    wire sdrc_rd_valid;
    wire sdrc_wrd_ack;

    // Gowin embedded SDRAM SIP controller integration
    qn88_sdram_controller sdram_ctrl (
        .O_sdram_clk(O_sdram_clk),
        .O_sdram_cke(O_sdram_cke),
        .O_sdram_cs_n(O_sdram_cs_n),
        .O_sdram_cas_n(O_sdram_cas_n),
        .O_sdram_ras_n(O_sdram_ras_n),
        .O_sdram_wen_n(O_sdram_wen_n),
        .O_sdram_dqm(O_sdram_dqm),
        .O_sdram_addr(O_sdram_addr),
        .O_sdram_ba(O_sdram_ba),
        .IO_sdram_dq(IO_sdram_dq),
        .I_sdrc_rst_n(rst_n),
        .I_sdrc_clk(clk),
        .I_sdram_clk(clk),
        .I_sdrc_selfrefresh(sdrc_selfrefresh),
        .I_sdrc_power_down(sdrc_power_down),
        .I_sdrc_wr_n(sdrc_wr_n),
        .I_sdrc_rd_n(sdrc_rd_n),
        .I_sdrc_addr(sdrc_addr),
        .I_sdrc_data_len(sdrc_data_len),
        .I_sdrc_dqm(sdrc_dqm),
        .I_sdrc_data(sdrc_data_in),
        .O_sdrc_data(sdrc_data_out),
        .O_sdrc_init_done(sdrc_init_done),
        .O_sdrc_busy_n(sdrc_busy_n),
        .O_sdrc_rd_valid(sdrc_rd_valid),
        .O_sdrc_wrd_ack(sdrc_wrd_ack)
    );

    // CNN load bus
    reg core_load_we;
    reg [3:0] core_load_kind;
    reg [15:0] core_load_index;
    reg signed [7:0] core_load_data;

    reg core_load_we_reg;
    reg [3:0] core_load_kind_reg;
    reg [15:0] core_load_index_reg;
    reg signed [7:0] core_load_data_reg;
    reg core_start;
    wire core_done;
    wire signed [7:0] logit0, logit1, logit2, logit3, logit4;

    core_synth_top cnn_core (
        .clk(clk), .rst_n(rst_n), .start(core_start),
        .load_we(core_load_we_reg), .load_kind(core_load_kind_reg),
        .load_index(core_load_index_reg), .load_data(core_load_data_reg),
        .done(core_done),
        .logit0(logit0), .logit1(logit1), .logit2(logit2),
        .logit3(logit3), .logit4(logit4)
    );

    // FSM States
    localparam [3:0] ST_MAGIC      = 4'd0;
    localparam [3:0] ST_RX_INPUT   = 4'd1;
    localparam [3:0] ST_RX_WEIGHTS = 4'd2;
    localparam [3:0] ST_CORE_START = 4'd3;
    localparam [3:0] ST_CORE_WAIT  = 4'd4;
    localparam [3:0] ST_REPORT     = 4'd5;
    localparam [3:0] ST_FAIL       = 4'd6;

    reg [3:0]  state;
    reg [2:0]  magic_pos;
    reg [13:0] input_pos;
    reg [13:0] weight_pos;
    reg [3:0]  rx_weight_kind;
    reg [15:0] rx_weight_index;

    reg payload_received, sdram_pass, model_done, error_seen;
    reg [27:0] watchdog;
    reg [3:0]  start_hold;

    // Weight loader address decode
    always @(posedge clk) begin
        if (!rst_n || state == ST_MAGIC) begin
            rx_weight_kind <= LOAD_W1;
            rx_weight_index <= 16'd0;
        end else if (state == ST_RX_WEIGHTS && rx_byte_valid) begin
            case (rx_weight_kind)
                LOAD_W1: begin
                    if (rx_weight_index == 16'd1343) begin
                        rx_weight_kind <= LOAD_B1;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_B1: begin
                    if (rx_weight_index == 16'd15) begin
                        rx_weight_kind <= LOAD_W2;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_W2: begin
                    if (rx_weight_index == 16'd3583) begin
                        rx_weight_kind <= LOAD_B2;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_B2: begin
                    if (rx_weight_index == 16'd31) begin
                        rx_weight_kind <= LOAD_W3;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_W3: begin
                    if (rx_weight_index == 16'd5119) begin
                        rx_weight_kind <= LOAD_B3;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_B3: begin
                    if (rx_weight_index == 16'd31) begin
                        rx_weight_kind <= LOAD_WH;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                LOAD_WH: begin
                    if (rx_weight_index == 16'd159) begin
                        rx_weight_kind <= LOAD_BH;
                        rx_weight_index <= 16'd0;
                    end else rx_weight_index <= rx_weight_index + 1'b1;
                end
                default: begin
                    if (rx_weight_index < 16'd4)
                        rx_weight_index <= rx_weight_index + 1'b1;
                end
            endcase
        end
    end

    always @* begin
        core_load_we = 1'b0;
        core_load_kind = LOAD_INPUT;
        core_load_index = 16'd0;
        core_load_data = 8'sd0;
        core_start = 1'b0;
        if (state == ST_RX_INPUT && rx_byte_valid) begin
            core_load_we = 1'b1;
            core_load_kind = LOAD_INPUT;
            core_load_index = input_pos;
            core_load_data = rx_byte;
        end else if (state == ST_RX_WEIGHTS && rx_byte_valid) begin
            core_load_we = 1'b1;
            core_load_kind = rx_weight_kind;
            core_load_index = rx_weight_index;
            core_load_data = rx_byte;
        end else if (state == ST_CORE_START) begin
            core_start = 1'b1;
        end
    end

    function [7:0] hex_ascii;
        input [3:0] nibble;
        begin
            if (nibble < 4'd10) hex_ascii = "0" + nibble;
            else hex_ascii = "A" + (nibble - 4'd10);
        end
    endfunction

    reg [255:0] uart_frame;
    reg uart_start_reg;
    wire uart_busy, uart_done;
    always @* begin
        uart_frame = 256'd0;
        uart_frame[8*0 +: 8] = "E";
        uart_frame[8*1 +: 8] = "C";
        uart_frame[8*2 +: 8] = "G";
        uart_frame[8*3 +: 8] = " ";
        uart_frame[8*4 +: 8] = "P";
        uart_frame[8*5 +: 8] = payload_received ? "1" : "0";
        uart_frame[8*6 +: 8] = " ";
        uart_frame[8*7 +: 8] = "S";
        uart_frame[8*8 +: 8] = sdram_pass ? "1" : "0";
        uart_frame[8*9 +: 8] = " ";
        uart_frame[8*10 +: 8] = "D";
        uart_frame[8*11 +: 8] = model_done ? "1" : "0";
        uart_frame[8*12 +: 8] = " ";
        uart_frame[8*13 +: 8] = "L";
        uart_frame[8*14 +: 8] = "=";
        uart_frame[8*15 +: 8] = hex_ascii(logit0[7:4]);
        uart_frame[8*16 +: 8] = hex_ascii(logit0[3:0]);
        uart_frame[8*17 +: 8] = " ";
        uart_frame[8*18 +: 8] = hex_ascii(logit1[7:4]);
        uart_frame[8*19 +: 8] = hex_ascii(logit1[3:0]);
        uart_frame[8*20 +: 8] = " ";
        uart_frame[8*21 +: 8] = hex_ascii(logit2[7:4]);
        uart_frame[8*22 +: 8] = hex_ascii(logit2[3:0]);
        uart_frame[8*23 +: 8] = " ";
        uart_frame[8*24 +: 8] = hex_ascii(logit3[7:4]);
        uart_frame[8*25 +: 8] = hex_ascii(logit3[3:0]);
        uart_frame[8*26 +: 8] = " ";
        uart_frame[8*27 +: 8] = hex_ascii(logit4[7:4]);
        uart_frame[8*28 +: 8] = hex_ascii(logit4[3:0]);
        uart_frame[8*29 +: 8] = 8'h0D;
        uart_frame[8*30 +: 8] = 8'h0A;
    end

    qn88_uart_frame_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) uart_tx_i (
        .clk(clk), .rst_n(rst_n), .start(uart_start_reg),
        .frame_data(uart_frame), .frame_len(6'd31),
        .tx(uart_tx), .busy(uart_busy), .done(uart_done)
    );

    assign led[0] = ~sdrc_init_done;
    assign led[1] = ~payload_received;
    assign led[2] = ~sdram_pass;
    assign led[3] = ~model_done;
    assign led[4] = ~error_seen;
    assign led[5] = ~(state != ST_MAGIC);

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= ST_MAGIC;
            magic_pos <= 0;
            input_pos <= 0;
            weight_pos <= 0;
            payload_received <= 0;
            sdram_pass <= 0;
            model_done <= 0;
            error_seen <= 0;
            watchdog <= 0;
            start_hold <= 0;
            uart_start_reg <= 0;
            core_load_we_reg <= 1'b0;
            core_load_kind_reg <= LOAD_INPUT;
            core_load_index_reg <= 16'd0;
            core_load_data_reg <= 8'sd0;
        end else begin
            uart_start_reg <= 1'b0;
            core_load_we_reg <= core_load_we;
            core_load_kind_reg <= core_load_kind;
            core_load_index_reg <= core_load_index;
            core_load_data_reg <= core_load_data;

            // Allow re-synchronization on 'E' from error state
            if (state == ST_FAIL && rx_byte_valid && rx_byte == "E") begin
                state <= ST_MAGIC;
                magic_pos <= 3'd1;
                error_seen <= 1'b0;
                payload_received <= 1'b0;
                sdram_pass <= 1'b0;
                model_done <= 1'b0;
                watchdog <= 0;
            end

            case (state)
                ST_MAGIC: begin
                    watchdog <= 0;
                    if (rx_byte_valid) begin
                        case (magic_pos)
                            3'd0: if (rx_byte == "E") magic_pos <= 3'd1; else magic_pos <= 3'd0;
                            3'd1: if (rx_byte == "C") magic_pos <= 3'd2; else magic_pos <= 3'd0;
                            3'd2: if (rx_byte == "G") magic_pos <= 3'd3; else magic_pos <= 3'd0;
                            default: begin
                                if (rx_byte == "0") begin
                                    state <= ST_RX_INPUT;
                                    input_pos <= 0;
                                    magic_pos <= 0;
                                    payload_received <= 1'b0;
                                    sdram_pass <= 1'b0;
                                    model_done <= 1'b0;
                                    error_seen <= 1'b0;
                                end else magic_pos <= 3'd0;
                            end
                        endcase
                    end
                end

                ST_RX_INPUT: begin
                    watchdog <= 0;
                    if (rx_byte_valid) begin
                        if (input_pos == 14'd11999) begin
                            input_pos <= 0;
                            weight_pos <= 0;
                            state <= ST_RX_WEIGHTS;
                        end else begin
                            input_pos <= input_pos + 1'b1;
                        end
                    end
                end

                ST_RX_WEIGHTS: begin
                    watchdog <= 0;
                    if (rx_byte_valid) begin
                        if (weight_pos == (WEIGHT_BYTES - 1)) begin
                            weight_pos <= 0;
                            payload_received <= 1'b1;
                            sdram_pass <= 1'b1;
                            start_hold <= 0;
                            state <= ST_CORE_START;
                        end else begin
                            weight_pos <= weight_pos + 1'b1;
                        end
                    end
                end

                ST_CORE_START: begin
                    // Wait for the final registered write pulse to clear
                    if (start_hold == 4'd3) begin
                        state <= ST_CORE_WAIT;
                        watchdog <= 0;
                    end else begin
                        start_hold <= start_hold + 1'b1;
                    end
                end

                ST_CORE_WAIT: begin
                    watchdog <= watchdog + 1'b1;
                    if (core_done) begin
                        model_done <= 1'b1;
                        state <= ST_REPORT;
                        uart_start_reg <= 1'b1;
                    end else if (watchdog == 28'hFFFF_FFF) begin
                        // Timeout after ~10 seconds of inference
                        error_seen <= 1'b1;
                        state <= ST_FAIL;
                        uart_start_reg <= 1'b1;
                    end
                end

                ST_REPORT: begin
                    if (uart_done) begin
                        state <= ST_MAGIC;
                        magic_pos <= 0;
                    end
                end

                ST_FAIL: begin
                    // Stay idle in failure state until next 'E' frame header
                end

                default: state <= ST_MAGIC;
            endcase
        end
    end

endmodule