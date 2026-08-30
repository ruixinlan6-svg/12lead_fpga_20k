`timescale 1ns/1ps

module qn88_scheme_b_top #(
    parameter integer CLK_HZ = 27_000_000,
    parameter integer BAUD   = 115_200
) (
    input  wire       clk,
    input  wire       rst_btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [5:0] led
);
    localparam integer DATA_WIDTH = 32;
    localparam integer USER_ADDR_WIDTH = 21;
    localparam [13:0] INPUT_BYTES  = 14'd12000;
    localparam [13:0] WEIGHT_BYTES = 14'd10293;

    wire rst_n = ~rst_btn;

    // Gowin Embedded SDRAM Controller IP Core Instance
    wire O_sdram_clk;
    wire O_sdram_cke;
    wire O_sdram_cs_n;
    wire O_sdram_cas_n;
    wire O_sdram_ras_n;
    wire O_sdram_wen_n;
    wire [1:0] O_sdram_dqm;
    wire [10:0] O_sdram_addr;
    wire [1:0] O_sdram_ba;
    wire [31:0] IO_sdram_dq;

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

    // UART Receiver
    wire [7:0] rx_byte;
    wire       rx_byte_valid;
    wire       rx_framing_error;

    qn88_uart_byte_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) uart_rx_i (
        .clk(clk),
        .rst_n(rst_n),
        .rx(uart_rx),
        .byte_data(rx_byte),
        .byte_valid(rx_byte_valid),
        .framing_error(rx_framing_error)
    );

    // Dynamic Parameter Storage RAM (16 KB True BSRAM, Dual-Port Sync)
    wire        storage_rd_en;
    wire [13:0] storage_rd_addr;
    wire signed [7:0] storage_rd_data;

    reg               storage_wr_en_reg;
    reg  [13:0]       storage_wr_addr_reg;
    reg  signed [7:0] storage_wr_data_reg;

    ecg_sync_dp_ram #(.ADDR_WIDTH(14), .DEPTH(16384)) u_weight_storage (
        .clk(clk),
        .wr_en(storage_wr_en_reg),
        .wr_addr(storage_wr_addr_reg),
        .wr_data(storage_wr_data_reg),
        .rd_en(storage_rd_en),
        .rd_addr(storage_rd_addr),
        .rd_data(storage_rd_data)
    );

    // Layer Weight DMA Streaming Controller
    reg        dma_start;
    reg [2:0]  dma_mode;
    wire       dma_done;
    wire       dma_w_en;
    wire [12:0] dma_w_addr;
    wire signed [7:0] dma_w_data;
    wire       dma_b_en;
    wire [5:0] dma_b_addr;
    wire signed [7:0] dma_b_data;
    wire       dma_in_en;
    wire [13:0] dma_in_addr;
    wire signed [7:0] dma_in_data;

    sdram_layer_dma u_dma (
        .clk(clk),
        .rst_n(rst_n),
        .dma_start(dma_start),
        .dma_mode(dma_mode),
        .dma_done(dma_done),
        .storage_rd_en(storage_rd_en),
        .storage_rd_addr(storage_rd_addr),
        .storage_rd_data(storage_rd_data),
        .dma_w_en(dma_w_en),
        .dma_w_addr(dma_w_addr),
        .dma_w_data(dma_w_data),
        .dma_b_en(dma_b_en),
        .dma_b_addr(dma_b_addr),
        .dma_b_data(dma_b_data),
        .dma_in_en(dma_in_en),
        .dma_in_addr(dma_in_addr),
        .dma_in_data(dma_in_data)
    );

    // Scheme B Stream Core Interface
    reg        layer_start;
    reg [2:0]  layer_id;
    wire       layer_done;

    wire signed [7:0] out_l0, out_l1, out_l2, out_l3, out_l4;

    // Registered UART input buffer
    reg               uart_in_en_reg;
    reg  [13:0]       uart_in_addr_reg;
    reg  signed [7:0] uart_in_data_reg;

    wire        core_in_en   = uart_in_en_reg ? 1'b1 : dma_in_en;
    wire [13:0] core_in_addr = uart_in_en_reg ? uart_in_addr_reg : dma_in_addr;
    wire signed [7:0] core_in_data = uart_in_en_reg ? uart_in_data_reg : dma_in_data;

    tiny_ecgcnn_stream_core u_core (
        .clk(clk),
        .rst_n(rst_n),
        .layer_start(layer_start),
        .layer_id(layer_id),
        .layer_done(layer_done),
        .dma_w_en(dma_w_en),
        .dma_w_addr(dma_w_addr),
        .dma_w_data(dma_w_data),
        .dma_b_en(dma_b_en),
        .dma_b_addr(dma_b_addr[4:0]),
        .dma_b_data(dma_b_data),
        .dma_in_en(core_in_en),
        .dma_in_addr(core_in_addr),
        .dma_in_data(core_in_data),
        .out_l0(out_l0),
        .out_l1(out_l1),
        .out_l2(out_l2),
        .out_l3(out_l3),
        .out_l4(out_l4)
    );

    reg payload_received, sdram_pass, model_done, error_seen;
    reg [27:0] watchdog;
    reg [3:0]  start_hold;

    // Top Controller FSM
    localparam [3:0] ST_MAGIC        = 4'd0;
    localparam [3:0] ST_RX_INPUT     = 4'd1;
    localparam [3:0] ST_RX_WEIGHTS   = 4'd2;
    localparam [3:0] ST_START_HOLD   = 4'd3;
    localparam [3:0] ST_RUN_L1_DMA   = 4'd4;
    localparam [3:0] ST_RUN_L1_CORE  = 4'd5;
    localparam [3:0] ST_RUN_L2_DMA   = 4'd6;
    localparam [3:0] ST_RUN_L2_CORE  = 4'd7;
    localparam [3:0] ST_RUN_L3_DMA   = 4'd8;
    localparam [3:0] ST_RUN_L3_CORE  = 4'd9;
    localparam [3:0] ST_RUN_GAP_CORE = 4'd10;
    localparam [3:0] ST_RUN_HEAD_DMA = 4'd11;
    localparam [3:0] ST_RUN_HEAD_CORE= 4'd12;
    localparam [3:0] ST_REPORT       = 4'd13;
    localparam [3:0] ST_FAIL         = 4'd14;

    reg [3:0] state;
    reg [2:0] magic_pos;
    reg [13:0] input_pos;
    reg [13:0] weight_pos;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state               <= ST_MAGIC;
            magic_pos           <= 0;
            input_pos           <= 0;
            weight_pos          <= 0;
            dma_start           <= 1'b0;
            dma_mode            <= 3'd0;
            layer_start         <= 1'b0;
            layer_id            <= 3'd0;
            payload_received    <= 1'b0;
            sdram_pass          <= 1'b0;
            model_done          <= 1'b0;
            error_seen          <= 1'b0;
            watchdog            <= 0;
            start_hold          <= 0;
            storage_wr_en_reg   <= 1'b0;
            storage_wr_addr_reg <= 14'd0;
            storage_wr_data_reg <= 8'sd0;
            uart_in_en_reg      <= 1'b0;
            uart_in_addr_reg    <= 14'd0;
            uart_in_data_reg    <= 8'sd0;
        end else begin
            dma_start   <= 1'b0;
            layer_start <= 1'b0;

            // 1-stage registered write pipelines for clean BSRAM timing
            storage_wr_en_reg   <= (state == ST_RX_WEIGHTS) && rx_byte_valid;
            storage_wr_addr_reg <= weight_pos;
            storage_wr_data_reg <= rx_byte;

            uart_in_en_reg      <= (state == ST_RX_INPUT) && rx_byte_valid;
            uart_in_addr_reg    <= input_pos;
            uart_in_data_reg    <= rx_byte;

            if (rx_framing_error) error_seen <= 1'b1;

            case (state)
                ST_MAGIC: begin
                    if (rx_byte_valid) begin
                        if (rx_byte == "E") begin
                            magic_pos <= 3'd1;
                        end else if (magic_pos == 3'd1 && rx_byte == "C") begin
                            magic_pos <= 3'd2;
                        end else if (magic_pos == 3'd2 && rx_byte == "G") begin
                            magic_pos <= 3'd3;
                        end else if (magic_pos == 3'd3 && rx_byte == "0") begin
                            state            <= ST_RX_INPUT;
                            input_pos        <= 0;
                            weight_pos       <= 0;
                            magic_pos        <= 0;
                            payload_received <= 1'b0;
                            sdram_pass       <= 1'b0;
                            model_done       <= 1'b0;
                            error_seen       <= 1'b0;
                        end else begin
                            magic_pos <= 3'd0;
                        end
                    end
                end

                ST_RX_INPUT: begin
                    if (rx_byte_valid) begin
                        if (input_pos == 14'd11999) begin
                            state      <= ST_RX_WEIGHTS;
                            weight_pos <= 0;
                        end else begin
                            input_pos <= input_pos + 1'b1;
                        end
                    end
                end

                ST_RX_WEIGHTS: begin
                    if (rx_byte_valid) begin
                        if (weight_pos == (WEIGHT_BYTES - 1)) begin
                            payload_received <= 1'b1;
                            sdram_pass       <= sdrc_init_done;
                            start_hold       <= 4'd0;
                            state            <= ST_START_HOLD;
                        end else begin
                            weight_pos <= weight_pos + 1'b1;
                        end
                    end
                end

                ST_START_HOLD: begin
                    if (start_hold == 4'd4) begin
                        state     <= ST_RUN_L1_DMA;
                        dma_mode  <= 3'd1; // L1 weights
                        dma_start <= 1'b1;
                    end else begin
                        start_hold <= start_hold + 1'b1;
                    end
                end

                // Layer 1 Execution
                ST_RUN_L1_DMA: begin
                    if (dma_done) begin
                        state       <= ST_RUN_L1_CORE;
                        layer_id    <= 3'd1;
                        layer_start <= 1'b1;
                    end
                end

                ST_RUN_L1_CORE: begin
                    if (layer_done) begin
                        state     <= ST_RUN_L2_DMA;
                        dma_mode  <= 3'd2; // L2 weights
                        dma_start <= 1'b1;
                    end
                end

                // Layer 2 Execution
                ST_RUN_L2_DMA: begin
                    if (dma_done) begin
                        state       <= ST_RUN_L2_CORE;
                        layer_id    <= 3'd2;
                        layer_start <= 1'b1;
                    end
                end

                ST_RUN_L2_CORE: begin
                    if (layer_done) begin
                        state     <= ST_RUN_L3_DMA;
                        dma_mode  <= 3'd3; // L3 weights
                        dma_start <= 1'b1;
                    end
                end

                // Layer 3 Execution
                ST_RUN_L3_DMA: begin
                    if (dma_done) begin
                        state       <= ST_RUN_L3_CORE;
                        layer_id    <= 3'd3;
                        layer_start <= 1'b1;
                    end
                end

                ST_RUN_L3_CORE: begin
                    if (layer_done) begin
                        state       <= ST_RUN_GAP_CORE;
                        layer_id    <= 3'd4;
                        layer_start <= 1'b1;
                    end
                end

                // Layer 4 (GAP) Execution
                ST_RUN_GAP_CORE: begin
                    if (layer_done) begin
                        state     <= ST_RUN_HEAD_DMA;
                        dma_mode  <= 3'd4; // Head weights
                        dma_start <= 1'b1;
                    end
                end

                // Layer 5 (Head) Execution
                ST_RUN_HEAD_DMA: begin
                    if (dma_done) begin
                        state       <= ST_RUN_HEAD_CORE;
                        layer_id    <= 3'd5;
                        layer_start <= 1'b1;
                    end
                end

                ST_RUN_HEAD_CORE: begin
                    if (layer_done) begin
                        model_done <= 1'b1;
                        state      <= ST_REPORT;
                    end
                end

                ST_REPORT: begin
                    if (rx_byte_valid && rx_byte == "E") begin
                        state            <= ST_MAGIC;
                        magic_pos        <= 3'd1;
                        payload_received <= 1'b0;
                        model_done       <= 1'b0;
                    end
                end

                ST_FAIL: begin
                    error_seen <= 1'b1;
                    if (rx_byte_valid && rx_byte == "E") begin
                        state            <= ST_MAGIC;
                        magic_pos        <= 3'd1;
                        error_seen       <= 1'b0;
                        payload_received <= 1'b0;
                        model_done       <= 1'b0;
                    end
                end

                default: state <= ST_MAGIC;
            endcase
        end
    end

    // UART Frame Transmitter (10 Hz periodic report)
    reg [23:0] uart_timer;
    reg        uart_start_reg;
    reg [255:0] uart_frame;
    wire       uart_busy;
    wire       uart_done;

    function [7:0] hex_ascii;
        input [3:0] nibble;
        begin
            if (nibble < 4'd10) hex_ascii = "0" + nibble;
            else hex_ascii = "A" + (nibble - 4'd10);
        end
    endfunction

    always @* begin
        uart_frame = 256'd0;
        uart_frame[8*0  +: 8] = "E";
        uart_frame[8*1  +: 8] = "C";
        uart_frame[8*2  +: 8] = "G";
        uart_frame[8*3  +: 8] = " ";
        uart_frame[8*4  +: 8] = "P";
        uart_frame[8*5  +: 8] = payload_received ? "1" : "0";
        uart_frame[8*6  +: 8] = " ";
        uart_frame[8*7  +: 8] = "S";
        uart_frame[8*8  +: 8] = sdram_pass ? "1" : "0";
        uart_frame[8*9  +: 8] = " ";
        uart_frame[8*10 +: 8] = "D";
        uart_frame[8*11 +: 8] = model_done ? "1" : "0";
        uart_frame[8*12 +: 8] = " ";
        uart_frame[8*13 +: 8] = "L";
        uart_frame[8*14 +: 8] = "=";
        uart_frame[8*15 +: 8] = hex_ascii(out_l0[7:4]);
        uart_frame[8*16 +: 8] = hex_ascii(out_l0[3:0]);
        uart_frame[8*17 +: 8] = " ";
        uart_frame[8*18 +: 8] = hex_ascii(out_l1[7:4]);
        uart_frame[8*19 +: 8] = hex_ascii(out_l1[3:0]);
        uart_frame[8*20 +: 8] = " ";
        uart_frame[8*21 +: 8] = hex_ascii(out_l2[7:4]);
        uart_frame[8*22 +: 8] = hex_ascii(out_l2[3:0]);
        uart_frame[8*23 +: 8] = " ";
        uart_frame[8*24 +: 8] = hex_ascii(out_l3[7:4]);
        uart_frame[8*25 +: 8] = hex_ascii(out_l3[3:0]);
        uart_frame[8*26 +: 8] = " ";
        uart_frame[8*27 +: 8] = hex_ascii(out_l4[7:4]);
        uart_frame[8*28 +: 8] = hex_ascii(out_l4[3:0]);
        uart_frame[8*29 +: 8] = 8'h0D;
        uart_frame[8*30 +: 8] = 8'h0A;
    end

    qn88_uart_frame_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) uart_tx_i (
        .clk(clk),
        .rst_n(rst_n),
        .start(uart_start_reg),
        .frame_data(uart_frame),
        .frame_len(6'd31),
        .tx(uart_tx),
        .busy(uart_busy),
        .done(uart_done)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            uart_timer     <= 24'd0;
            uart_start_reg <= 1'b0;
        end else begin
            uart_start_reg <= 1'b0;
            if (uart_timer == (CLK_HZ / 10 - 1)) begin
                uart_timer     <= 24'd0;
                uart_start_reg <= 1'b1;
            end else begin
                uart_timer <= uart_timer + 1'b1;
            end
        end
    end

    assign led[0] = ~sdrc_init_done;
    assign led[1] = ~payload_received;
    assign led[2] = ~sdram_pass;
    assign led[3] = ~model_done;
    assign led[4] = ~error_seen;
    assign led[5] = ~(state != ST_MAGIC);

endmodule