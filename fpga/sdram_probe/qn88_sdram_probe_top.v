`timescale 1ns/1ps

// Volatile QN88 embedded-SDRAM probe.  The vendor SDRC_EMB IP is supplied by
// the local Gowin installation at build time; no vendor-encrypted source is
// copied into this repository.
module qn88_sdram_probe (
    input  wire       clk,
    input  wire       rst_btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [5:0] led
);
    localparam integer DATA_WIDTH = 32;
    localparam integer BANK_WIDTH = 2;
    localparam integer ROW_WIDTH = 11;
    localparam integer COL_WIDTH = 8;
    localparam integer USER_ADDR_WIDTH = BANK_WIDTH + ROW_WIDTH + COL_WIDTH;
    // GW2AR's local vendor testbench uses data_len=25 for the 32-bit
    // embedded-SDRAM interface; that corresponds to 26 user data beats.
    localparam integer BURST_WORDS = 26;
    localparam integer BURSTS = 4;

    wire rst_n = ~rst_btn;
    wire [DATA_WIDTH-1:0] sdrc_data_out;
    wire [DATA_WIDTH-1:0] sdrc_data_in;
    wire [USER_ADDR_WIDTH-1:0] sdrc_addr;
    wire [COL_WIDTH-1:0] sdrc_data_len;
    wire [DATA_WIDTH/8-1:0] sdrc_dqm;
    wire sdrc_wr_n, sdrc_rd_n;
    wire sdrc_selfrefresh = 1'b0;
    wire sdrc_power_down = 1'b0;
    wire sdrc_init_done;
    wire sdrc_busy_n;
    wire sdrc_rd_valid;
    wire sdrc_wrd_ack;

    wire sdram_clk;
    wire sdram_cke;
    wire sdram_cs_n;
    wire sdram_cas_n;
    wire sdram_ras_n;
    wire sdram_wen_n;
    wire [DATA_WIDTH/8-1:0] sdram_dqm;
    wire [ROW_WIDTH-1:0] sdram_addr;
    wire [BANK_WIDTH-1:0] sdram_ba;
    wire [DATA_WIDTH-1:0] sdram_dq;

    assign sdram_dq = {DATA_WIDTH{1'bz}};

    // The generated SDRC_EMB module name comes from sdrc_defines.v.
    qn88_sdram_controller sdram_ctrl (
        .O_sdram_clk(sdram_clk),
        .O_sdram_cke(sdram_cke),
        .O_sdram_cs_n(sdram_cs_n),
        .O_sdram_cas_n(sdram_cas_n),
        .O_sdram_ras_n(sdram_ras_n),
        .O_sdram_wen_n(sdram_wen_n),
        .O_sdram_dqm(sdram_dqm),
        .O_sdram_addr(sdram_addr),
        .O_sdram_ba(sdram_ba),
        .IO_sdram_dq(sdram_dq),
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

    reg [2:0] state;
    localparam ST_IDLE = 3'd0;
    localparam ST_WRITE_WAIT = 3'd1;
    localparam ST_WRITE = 3'd2;
    localparam ST_READ_WAIT = 3'd3;
    localparam ST_READ = 3'd4;
    localparam ST_DONE = 3'd5;
    localparam ST_FAIL = 3'd6;

    reg [COL_WIDTH-1:0] column;
    reg [2:0] burst;
    reg [COL_WIDTH-1:0] write_count;
    reg [COL_WIDTH-1:0] read_count;
    reg [DATA_WIDTH-1:0] write_data;
    reg [DATA_WIDTH-1:0] expected_data;
    reg [DATA_WIDTH-1:0] user_data;
    reg user_wr_n;
    reg user_rd_n;
    reg error_seen;
    reg [27:0] watchdog;
    reg [23:0] heartbeat;
    reg [23:0] uart_timer;
    reg uart_start_reg;
    reg [255:0] uart_frame;
    wire uart_busy;
    wire uart_done;
    reg [DATA_WIDTH-1:0] first_read_data;
    reg [DATA_WIDTH-1:0] first_expected_data;
    reg mismatch_latched;

    function [7:0] hex_ascii;
        input [3:0] nibble;
        begin
            if (nibble < 4'd10)
                hex_ascii = "0" + nibble;
            else
                hex_ascii = "A" + (nibble - 4'd10);
        end
    endfunction

    // Little-endian frame: "SDRAM I0 P0 E0 D=xxxx X=xxxx\r\n" (30 bytes).
    always @* begin
        uart_frame = 256'd0;
        uart_frame[8*0 +: 8]  = "S";
        uart_frame[8*1 +: 8]  = "D";
        uart_frame[8*2 +: 8]  = "R";
        uart_frame[8*3 +: 8]  = "A";
        uart_frame[8*4 +: 8]  = "M";
        uart_frame[8*5 +: 8]  = " ";
        uart_frame[8*6 +: 8]  = "I";
        uart_frame[8*7 +: 8]  = sdrc_init_done ? "1" : "0";
        uart_frame[8*8 +: 8]  = " ";
        uart_frame[8*9 +: 8]  = "P";
        uart_frame[8*10 +: 8] = (state == ST_DONE) ? "1" : "0";
        uart_frame[8*11 +: 8] = " ";
        uart_frame[8*12 +: 8] = "E";
        uart_frame[8*13 +: 8] = error_seen ? "1" : "0";
        uart_frame[8*14 +: 8] = " ";
        uart_frame[8*15 +: 8] = "D";
        uart_frame[8*16 +: 8] = "=";
        uart_frame[8*17 +: 8] = hex_ascii(first_read_data[31:28]);
        uart_frame[8*18 +: 8] = hex_ascii(first_read_data[27:24]);
        uart_frame[8*19 +: 8] = hex_ascii(first_read_data[23:20]);
        uart_frame[8*20 +: 8] = hex_ascii(first_read_data[19:16]);
        uart_frame[8*21 +: 8] = " ";
        uart_frame[8*22 +: 8] = "X";
        uart_frame[8*23 +: 8] = "=";
        uart_frame[8*24 +: 8] = hex_ascii(first_expected_data[31:28]);
        uart_frame[8*25 +: 8] = hex_ascii(first_expected_data[27:24]);
        uart_frame[8*26 +: 8] = hex_ascii(first_expected_data[23:20]);
        uart_frame[8*27 +: 8] = hex_ascii(first_expected_data[19:16]);
        uart_frame[8*28 +: 8] = 8'h0D;
        uart_frame[8*29 +: 8] = 8'h0A;
    end

    qn88_uart_frame_tx uart_status_tx (
        .clk(clk), .rst_n(rst_n), .start(uart_start_reg),
        .frame_data(uart_frame), .frame_len(6'd30),
        .tx(uart_tx), .busy(uart_busy), .done(uart_done)
    );

    // Keep RX present for the documented BL616 return path; this read-only
    // probe intentionally does not interpret or act on incoming bytes.
    wire uart_rx_unused = uart_rx;

    // Match the vendor GW2AR example's non-zero bank/row starting point.
    assign sdrc_addr = {2'd2, 11'd2, column};
    assign sdrc_data_len = BURST_WORDS - 1;
    assign sdrc_dqm = 4'b0000;
    assign sdrc_data_in = user_data;
    assign sdrc_wr_n = user_wr_n;
    assign sdrc_rd_n = user_rd_n;

    // LEDs are active-low on Tang Nano 20K.  LED0 indicates initialization,
    // LED1 pass, LED2 error, LED3 controller busy, LED4/5 burst index.
    assign led[0] = ~sdrc_init_done;
    assign led[1] = ~(state == ST_DONE);
    assign led[2] = ~error_seen;
    assign led[3] = ~sdrc_busy_n;
    assign led[4] = ~burst[0];
    assign led[5] = ~burst[1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_IDLE;
            column <= 8'd5;
            burst <= 0;
            write_count <= 0;
            read_count <= 0;
            write_data <= 32'hA5A5_0000;
            expected_data <= 32'hA5A5_0000;
            user_data <= 32'hA5A5_0000;
            user_wr_n <= 1'b1;
            user_rd_n <= 1'b1;
            error_seen <= 1'b0;
            watchdog <= 0;
            heartbeat <= 0;
            uart_timer <= 0;
            uart_start_reg <= 1'b0;
            first_read_data <= 0;
            first_expected_data <= 0;
            mismatch_latched <= 1'b0;
        end else begin
            heartbeat <= heartbeat + 1'b1;
            uart_start_reg <= 1'b0;
            if ((uart_timer == 24'd6749999) && !uart_busy) begin
                uart_timer <= 24'd0;
                uart_start_reg <= 1'b1;
            end else if (!uart_busy) begin
                uart_timer <= uart_timer + 1'b1;
            end
            if (state != ST_DONE && state != ST_FAIL)
                watchdog <= watchdog + 1'b1;
            if (watchdog == {28{1'b1}}) begin
                error_seen <= 1'b1;
                state <= ST_FAIL;
            end

            case (state)
                ST_IDLE: begin
                    user_wr_n <= 1'b1;
                    user_rd_n <= 1'b1;
                    if (sdrc_init_done && sdrc_busy_n) begin
                        state <= ST_WRITE_WAIT;
                        write_count <= 0;
                        write_data <= 32'hA5A5_0000 + (burst * 32'h0000_0100);
                        user_data <= 32'hA5A5_0000 + (burst * 32'h0000_0100);
                        watchdog <= 0;
                    end
                end
                ST_WRITE_WAIT: begin
                    if (sdrc_busy_n) begin
                        user_wr_n <= 1'b0;
                        state <= ST_WRITE;
                        write_count <= 0;
                    end
                end
                ST_WRITE: begin
                    user_wr_n <= 1'b1;
                    user_data <= write_data + 1'b1;
                    write_data <= write_data + 1'b1;
                    if (write_count == BURST_WORDS + 2) begin
                        state <= ST_READ_WAIT;
                        read_count <= 0;
                        expected_data <= 32'hA5A5_0000 + (burst * 32'h0000_0100);
                    end else begin
                        write_count <= write_count + 1'b1;
                    end
                end
                ST_READ_WAIT: begin
                    if (sdrc_busy_n) begin
                        user_rd_n <= 1'b0;
                        state <= ST_READ;
                        read_count <= 0;
                    end
                end
                ST_READ: begin
                    user_rd_n <= 1'b1;
                    if (sdrc_rd_valid) begin
                        if (sdrc_data_out !== expected_data) begin
                            error_seen <= 1'b1;
                            if (!mismatch_latched) begin
                                first_read_data <= sdrc_data_out;
                                first_expected_data <= expected_data;
                                mismatch_latched <= 1'b1;
                            end
                        end
                        expected_data <= expected_data + 1'b1;
                        read_count <= read_count + 1'b1;
                    end
                    if (read_count >= BURST_WORDS) begin
                        if (error_seen)
                            state <= ST_FAIL;
                        else if (burst == BURSTS - 1)
                            state <= ST_DONE;
                        else begin
                            burst <= burst + 1'b1;
                            column <= column + BURST_WORDS;
                            state <= ST_WRITE_WAIT;
                            write_count <= 0;
                        end
                        watchdog <= 0;
                    end
                end
                ST_DONE: begin
                    user_wr_n <= 1'b1;
                    user_rd_n <= 1'b1;
                end
                ST_FAIL: begin
                    user_wr_n <= 1'b1;
                    user_rd_n <= 1'b1;
                end
                default: state <= ST_FAIL;
            endcase
        end
    end
endmodule
