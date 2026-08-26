`timescale 1ns/1ps

// QN88 model-level integration.
//
// Host protocol (115200 8-N-1, volatile SRAM configuration only):
//   "ECG0" magic, 12,000 signed-INT8 input bytes, then 10,293 signed-INT8
//   parameter bytes in the order W1/B1/W2/B2/W3/B3/WH/BH. Parameters are
//   assembled into 32-bit little-endian words in 100-byte chunks, written/read
//   through the embedded SDRAM controller, and only then copied into the CNN
//   core. The host must leave a short inter-chunk pause while SDRAM is checked.
//   The board returns one ASCII frame:
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
    localparam integer BURST_WORDS = 26;
    localparam integer BURST_DATA_WORDS = BURST_WORDS - 1;
    localparam integer WEIGHT_BYTES = 10293;
    localparam integer WEIGHT_WORDS = (WEIGHT_BYTES + 3) / 4;
    localparam integer BURSTS = (WEIGHT_WORDS + BURST_DATA_WORDS - 1) /
                                BURST_DATA_WORDS;

    localparam [3:0] LOAD_INPUT = 4'd0;
    localparam [3:0] LOAD_W1 = 4'd1;
    localparam [3:0] LOAD_B1 = 4'd2;
    localparam [3:0] LOAD_W2 = 4'd3;
    localparam [3:0] LOAD_B2 = 4'd4;
    localparam [3:0] LOAD_W3 = 4'd5;
    localparam [3:0] LOAD_B3 = 4'd6;
    localparam [3:0] LOAD_WH = 4'd7;
    localparam [3:0] LOAD_BH = 4'd8;

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
    reg  [DATA_WIDTH-1:0] sdrc_data_in;
    reg  [USER_ADDR_WIDTH-1:0] sdrc_addr_reg;
    wire [USER_ADDR_WIDTH-1:0] sdrc_addr = sdrc_addr_reg;
    wire [7:0] sdrc_data_len = BURST_WORDS - 1;
    wire [DATA_WIDTH/8-1:0] sdrc_dqm = 4'b0000;
    reg sdrc_wr_n, sdrc_rd_n;
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

    // Only the active 25-word SDRAM burst is buffered on chip.  UART bytes
    // are assembled directly into this FIFO, so the design does not duplicate
    // the full 10,293-byte parameter payload before writing external SDRAM.
    // Small FF burst buffer. Keeping this 800-bit staging area out of the
    // block-RAM inference leaves the SDPB budget for the CNN activations and
    // the SDRAM controller itself. An unpacked word array keeps byte lanes
    // local and avoids a wide variable part-select mux in the full top.
    reg [31:0] write_fifo [0:BURST_DATA_WORDS-1];
    // The same FIFO is reused for readback: each returned word is compared
    // against the pre-write value and then replaces it for CNN draining. This
    // avoids spending a second small block RAM on a duplicate burst buffer.

    // CNN load bus: input arrives directly from UART; weights are loaded only
    // from the SDRAM readback FIFO after every burst has compared cleanly.
    reg core_load_we;
    reg [3:0] core_load_kind;
    reg [15:0] core_load_index;
    reg signed [7:0] core_load_data;
    // Register the load bundle before it enters the CNN.  A one-cycle
    // registered write strobe keeps each inferred synchronous RAM's write
    // enable local and avoids a large combinational fanout from the UART/
    // SDRAM state machine into every parameter memory.
    reg core_load_we_reg;
    reg [3:0] core_load_kind_reg;
    reg [15:0] core_load_index_reg;
    reg signed [7:0] core_load_data_reg;
    reg core_start;
    wire core_done;
    wire signed [7:0] logit0, logit1, logit2, logit3, logit4;

    // The CNN is linked from the independently synthesized SDPB netlist.
    // Keeping the RAM-rich core as a netlist boundary prevents the Gowin
    // top-level optimizer from duplicating its byte-load decode into the
    // SDRAM/UART controller while preserving all runtime load ports.
    core_synth_top cnn_core (
        .clk(clk), .rst_n(rst_n), .start(core_start),
        .load_we(core_load_we_reg), .load_kind(core_load_kind_reg),
        .load_index(core_load_index_reg), .load_data(core_load_data_reg),
        .done(core_done),
        .logit0(logit0), .logit1(logit1), .logit2(logit2),
        .logit3(logit3), .logit4(logit4)
    );

    // Loader and SDRAM transaction state.
    localparam [4:0] ST_MAGIC = 5'd0;
    localparam [4:0] ST_RX_INPUT = 5'd1;
    localparam [4:0] ST_RX_WEIGHTS = 5'd2;
    localparam [4:0] ST_SDRAM_WAIT = 5'd3;
    localparam [4:0] ST_SDRAM_WRITE_WAIT = 5'd4;
    localparam [4:0] ST_SDRAM_WRITE = 5'd5;
    localparam [4:0] ST_SDRAM_READ_WAIT = 5'd6;
    localparam [4:0] ST_SDRAM_READ = 5'd7;
    localparam [4:0] ST_DRAIN_WEIGHTS = 5'd8;
    localparam [4:0] ST_CORE_START = 5'd9;
    localparam [4:0] ST_CORE_WAIT = 5'd10;
    localparam [4:0] ST_REPORT = 5'd11;
    localparam [4:0] ST_FAIL = 5'd12;

    reg [4:0] state;
    reg [2:0] magic_pos;
    reg [13:0] input_pos;
    reg [13:0] weight_pos;
    reg [6:0] burst_pos;
    reg [5:0] write_count;
    reg [5:0] read_count;
    reg [5:0] drain_word;
    reg [1:0] drain_byte;
    reg [6:0] burst_byte_count;
    reg [5:0] burst_word_idx;
    reg [1:0] burst_byte_lane;
    reg [13:0] burst_byte_base;
    reg [13:0] drain_param_offset;
    reg [11:0] burst_word_base;
    reg [3:0] drain_kind_reg;
    reg [15:0] drain_index_reg;
    reg [31:0] write_data_reg;
    reg [20:0] sdram_addr_linear;
    reg payload_received, sdram_pass, model_done, error_seen;
    reg [31:0] watchdog;
    reg [31:0] first_read_data, first_expected_data;
    integer fifo_i;

    // The registered write data stream is advanced in the sequential FSM. The
    // request edge carries one pad word; following beats carry payload words.
    always @* begin
        sdrc_data_in = write_data_reg;
    end

    // Translate the UART/readback streams into the CNN's individual tensor
    // memories. SDRAM readback is word-wide so it can keep pace with a burst
    // without a second full-size buffer.
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
        end else if (state == ST_DRAIN_WEIGHTS && drain_param_offset < WEIGHT_BYTES) begin
            core_load_we = 1'b1;
            core_load_kind = drain_kind_reg;
            core_load_index = drain_index_reg;
            case (drain_byte)
                2'd0: core_load_data = write_fifo[drain_word][7:0];
                2'd1: core_load_data = write_fifo[drain_word][15:8];
                2'd2: core_load_data = write_fifo[drain_word][23:16];
                default: core_load_data = write_fifo[drain_word][31:24];
            endcase
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
    assign led[5] = ~(state != ST_MAGIC && state != ST_RX_INPUT &&
                       state != ST_RX_WEIGHTS);

    // The loader reset is sampled synchronously. POR holds rst_n low for more
    // than 2 ms, so every state and staging word still sees a clean reset
    // while the small burst buffer remains outside the BRAM inference path.
    always @(posedge clk) begin
        if (!rst_n) begin
            state <= ST_MAGIC;
            magic_pos <= 0;
            input_pos <= 0;
            weight_pos <= 0;
            burst_pos <= 0;
            write_count <= 0;
            read_count <= 0;
            drain_word <= 0;
            drain_byte <= 0;
            burst_byte_count <= 0;
            burst_word_idx <= 0;
            burst_byte_lane <= 0;
            burst_byte_base <= 0;
            drain_param_offset <= 0;
            burst_word_base <= 0;
            drain_kind_reg <= LOAD_W1;
            drain_index_reg <= 16'd0;
            for (fifo_i = 0; fifo_i < BURST_DATA_WORDS; fifo_i = fifo_i + 1)
                write_fifo[fifo_i] <= 32'd0;
            write_data_reg <= 0;
            sdrc_wr_n <= 1'b1;
            sdrc_rd_n <= 1'b1;
            sdram_addr_linear <= {2'd2, 11'd2, 8'd5};
            payload_received <= 0;
            sdram_pass <= 0;
            model_done <= 0;
            error_seen <= 0;
            watchdog <= 0;
            first_read_data <= 0;
            first_expected_data <= 0;
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
            if (rx_framing_error)
                error_seen <= 1'b1;
            if (state != ST_CORE_WAIT && state != ST_REPORT && state != ST_FAIL)
                watchdog <= watchdog + 1'b1;
            if (watchdog == 32'hFFFF_FFFF) begin
                error_seen <= 1'b1;
                state <= ST_FAIL;
            end

            case (state)
                ST_MAGIC: begin
                    if (rx_byte_valid) begin
                        case (magic_pos)
                            0: if (rx_byte == "E") magic_pos <= 1; else magic_pos <= 0;
                            1: if (rx_byte == "C") magic_pos <= 2; else magic_pos <= 0;
                            2: if (rx_byte == "G") magic_pos <= 3; else magic_pos <= 0;
                            default: begin
                                if (rx_byte == "0") begin
                                    state <= ST_RX_INPUT;
                                    input_pos <= 0;
                                    magic_pos <= 0;
                                end else magic_pos <= 0;
                            end
                        endcase
                    end
                end
                ST_RX_INPUT: begin
                    if (rx_byte_valid) begin
                        if (input_pos == 11999) begin
                            input_pos <= 0;
                            weight_pos <= 0;
                            burst_pos <= 0;
                            burst_byte_count <= 0;
                            burst_word_idx <= 0;
                            burst_byte_lane <= 0;
                            burst_byte_base <= 0;
                            drain_param_offset <= 0;
                            burst_word_base <= 0;
                            drain_kind_reg <= LOAD_W1;
                            drain_index_reg <= 16'd0;
                            state <= ST_RX_WEIGHTS;
                        end else begin
                            input_pos <= input_pos + 1'b1;
                        end
                    end
                end
                ST_RX_WEIGHTS: begin
                    if (rx_byte_valid) begin
                        case (burst_byte_lane)
                            2'd0: write_fifo[burst_word_idx][7:0] <= rx_byte;
                            2'd1: write_fifo[burst_word_idx][15:8] <= rx_byte;
                            2'd2: write_fifo[burst_word_idx][23:16] <= rx_byte;
                            default: write_fifo[burst_word_idx][31:24] <= rx_byte;
                        endcase
                        weight_pos <= weight_pos + 1'b1;
                        if (burst_byte_lane == 2'd3) begin
                            burst_byte_lane <= 0;
                            if (burst_word_idx < BURST_DATA_WORDS - 1)
                                burst_word_idx <= burst_word_idx + 1'b1;
                        end else begin
                            burst_byte_lane <= burst_byte_lane + 1'b1;
                        end
                        if (burst_byte_count == BURST_DATA_WORDS * 4 - 1 ||
                            weight_pos == WEIGHT_BYTES - 1) begin
                            if (weight_pos == WEIGHT_BYTES - 1)
                                payload_received <= 1'b1;
                            state <= ST_SDRAM_WAIT;
                            watchdog <= 0;
                            burst_byte_count <= 0;
                            burst_word_idx <= 0;
                            burst_byte_lane <= 0;
                        end else begin
                            burst_byte_count <= burst_byte_count + 1'b1;
                        end
                    end
                end
                ST_SDRAM_WAIT: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    sdrc_addr_reg <= sdram_addr_linear;
                    if (sdrc_init_done && sdrc_busy_n) begin
                        write_count <= 0;
                        write_data_reg <= 0; // pad beat on request edge
                        state <= ST_SDRAM_WRITE_WAIT;
                        watchdog <= 0;
                    end
                end
                ST_SDRAM_WRITE_WAIT: begin
                    sdrc_wr_n <= 1'b0;
                    sdrc_rd_n <= 1'b1;
                    if (sdrc_busy_n) begin
                        write_count <= 0;
                        write_data_reg <= 0;
                        state <= ST_SDRAM_WRITE;
                    end
                end
                ST_SDRAM_WRITE: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    // Keep the first request beat as pad, then advance the
                    // registered stream so the controller sees payload word 0
                    // on the following beat (the GW2AR data_len=25 contract).
                    if (write_count < BURST_DATA_WORDS) begin
                        write_data_reg <= write_fifo[write_count];
                    end else begin
                        write_data_reg <= 0;
                    end
                    if (write_count == BURST_WORDS + 2) begin
                        read_count <= 0;
                        state <= ST_SDRAM_READ_WAIT;
                    end else begin
                        write_count <= write_count + 1'b1;
                    end
                end
                ST_SDRAM_READ_WAIT: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b0;
                    sdrc_addr_reg <= sdram_addr_linear;
                    if (sdrc_busy_n) begin
                        read_count <= 0;
                        state <= ST_SDRAM_READ;
                    end
                end
                ST_SDRAM_READ: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    if (sdrc_rd_valid) begin
                        if (read_count < BURST_DATA_WORDS)
                            write_fifo[read_count] <= sdrc_data_out;
                        if ((burst_word_base + read_count) < WEIGHT_WORDS &&
                            sdrc_data_out !== write_fifo[read_count]) begin
                            error_seen <= 1'b1;
                            if (first_read_data == 0) begin
                                first_read_data <= sdrc_data_out;
                                first_expected_data <= write_fifo[read_count];
                            end
                        end
                        if (read_count == BURST_DATA_WORDS - 1) begin
                            if (error_seen ||
                                ((burst_word_base + read_count) < WEIGHT_WORDS &&
                                 sdrc_data_out !== write_fifo[read_count])) begin
                                state <= ST_FAIL;
                            end else if (burst_pos == BURSTS - 1) begin
                                sdram_pass <= 1'b1;
                                drain_word <= 0;
                                drain_byte <= 0;
                                drain_param_offset <= burst_byte_base;
                                state <= ST_DRAIN_WEIGHTS;
                            end else begin
                                drain_word <= 0;
                                drain_byte <= 0;
                                drain_param_offset <= burst_byte_base;
                                state <= ST_DRAIN_WEIGHTS;
                            end
                            read_count <= 0;
                        end else begin
                            read_count <= read_count + 1'b1;
                        end
                    end
                end
                ST_DRAIN_WEIGHTS: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    if (drain_byte == 3) begin
                        drain_byte <= 0;
                        if (drain_word == BURST_DATA_WORDS - 1) begin
                            drain_word <= 0;
                            if (burst_pos == BURSTS - 1) begin
                                state <= ST_CORE_START;
                            end else begin
                                burst_pos <= burst_pos + 1'b1;
                                burst_byte_base <= burst_byte_base + 14'd100;
                                burst_word_base <= burst_word_base + 12'd25;
                                sdram_addr_linear <= sdram_addr_linear + BURST_WORDS;
                                burst_byte_count <= 0;
                                burst_word_idx <= 0;
                                burst_byte_lane <= 0;
                                for (fifo_i = 0; fifo_i < BURST_DATA_WORDS; fifo_i = fifo_i + 1)
                                    write_fifo[fifo_i] <= 32'd0;
                                state <= ST_RX_WEIGHTS;
                                write_count <= 0;
                                write_data_reg <= 0;
                            end
                        end else drain_word <= drain_word + 1'b1;
                    end else begin
                        drain_byte <= drain_byte + 1'b1;
                    end
                    if (drain_param_offset < WEIGHT_BYTES)
                        drain_param_offset <= drain_param_offset + 1'b1;
                    if (drain_param_offset < WEIGHT_BYTES) begin
                        case (drain_kind_reg)
                            LOAD_W1: begin
                                if (drain_index_reg == 16'd1343) begin drain_kind_reg <= LOAD_B1; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_B1: begin
                                if (drain_index_reg == 16'd15) begin drain_kind_reg <= LOAD_W2; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_W2: begin
                                if (drain_index_reg == 16'd3583) begin drain_kind_reg <= LOAD_B2; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_B2: begin
                                if (drain_index_reg == 16'd31) begin drain_kind_reg <= LOAD_W3; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_W3: begin
                                if (drain_index_reg == 16'd5119) begin drain_kind_reg <= LOAD_B3; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_B3: begin
                                if (drain_index_reg == 16'd31) begin drain_kind_reg <= LOAD_WH; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            LOAD_WH: begin
                                if (drain_index_reg == 16'd159) begin drain_kind_reg <= LOAD_BH; drain_index_reg <= 0; end
                                else drain_index_reg <= drain_index_reg + 1'b1;
                            end
                            default: begin
                                if (drain_index_reg < 16'd4) drain_index_reg <= drain_index_reg + 1'b1;
                            end
                        endcase
                    end
                end
                ST_CORE_START: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    // The final registered parameter byte is consumed by the
                    // CNN one cycle after the drain FSM reaches this state.
                    // Hold the start state until that write pulse has cleared.
                    if (!core_load_we_reg) begin
                        state <= ST_CORE_WAIT;
                        watchdog <= 0;
                    end
                end
                ST_CORE_WAIT: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    if (core_done) begin
                        model_done <= 1'b1;
                        state <= ST_REPORT;
                        uart_start_reg <= 1'b1;
                    end
                end
                ST_REPORT: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    if (!uart_busy)
                        state <= ST_REPORT;
                end
                ST_FAIL: begin
                    sdrc_wr_n <= 1'b1;
                    sdrc_rd_n <= 1'b1;
                    if (!uart_busy && !uart_start_reg)
                        uart_start_reg <= 1'b1;
                end
                default: state <= ST_FAIL;
            endcase
        end
    end
endmodule
