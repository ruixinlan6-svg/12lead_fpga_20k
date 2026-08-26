`timescale 1ns/1ps

// QN88 UART observability probe.  It emits a periodic known frame so the
// onboard BL616/USB bridge and host serial-channel mapping can be tested
// without touching QSPI Flash or SDRAM contents.
module qn88_uart_probe (
    input  wire       clk,
    input  wire       rst_btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [5:0] led
);
    localparam integer CLK_HZ = 27000000;
    localparam integer BAUD = 115200;
    localparam integer CLKS_PER_BIT = (CLK_HZ + (BAUD / 2)) / BAUD;
    localparam integer FRAME_INTERVAL = 6750000; // 250 ms at 27 MHz
    localparam [3:0] LAST_BYTE = 4'd13;

    localparam [1:0] ST_IDLE  = 2'd0;
    localparam [1:0] ST_START = 2'd1;
    localparam [1:0] ST_DATA  = 2'd2;
    localparam [1:0] ST_STOP  = 2'd3;

    wire rst_n = ~rst_btn;
    reg [1:0] state;
    reg [23:0] interval_count;
    reg [8:0] bit_count;
    reg [2:0] bit_index;
    reg [3:0] byte_index;
    reg [7:0] tx_byte;
    reg tx_reg;
    reg frame_active;
    reg frame_toggle;

    // The message is deliberately short, printable, and stable across builds.
    function [7:0] message_byte;
        input [3:0] index;
        begin
            case (index)
                4'd0:  message_byte = "Q";
                4'd1:  message_byte = "N";
                4'd2:  message_byte = "8";
                4'd3:  message_byte = "8";
                4'd4:  message_byte = " ";
                4'd5:  message_byte = "U";
                4'd6:  message_byte = "A";
                4'd7:  message_byte = "R";
                4'd8:  message_byte = "T";
                4'd9:  message_byte = " ";
                4'd10: message_byte = "O";
                4'd11: message_byte = "K";
                4'd12: message_byte = 8'h0D;
                4'd13: message_byte = 8'h0A;
                default: message_byte = 8'h00;
            endcase
        end
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state          <= ST_IDLE;
            interval_count <= 24'd0;
            bit_count      <= 9'd0;
            bit_index      <= 3'd0;
            byte_index     <= 4'd0;
            tx_byte        <= 8'hFF;
            tx_reg         <= 1'b1;
            frame_active   <= 1'b0;
            frame_toggle   <= 1'b0;
        end else begin
            case (state)
                ST_IDLE: begin
                    tx_reg       <= 1'b1;
                    frame_active <= 1'b0;
                    if (interval_count == FRAME_INTERVAL - 1) begin
                        interval_count <= 24'd0;
                        byte_index     <= 4'd0;
                        tx_byte        <= message_byte(4'd0);
                        bit_count      <= 9'd0;
                        bit_index      <= 3'd0;
                        frame_active   <= 1'b1;
                        state          <= ST_START;
                    end else begin
                        interval_count <= interval_count + 1'b1;
                    end
                end
                ST_START: begin
                    tx_reg <= 1'b0;
                    if (bit_count == CLKS_PER_BIT - 1) begin
                        bit_count <= 9'd0;
                        bit_index <= 3'd0;
                        state <= ST_DATA;
                    end else begin
                        bit_count <= bit_count + 1'b1;
                    end
                end
                ST_DATA: begin
                    tx_reg <= tx_byte[bit_index];
                    if (bit_count == CLKS_PER_BIT - 1) begin
                        bit_count <= 9'd0;
                        if (bit_index == 3'd7) begin
                            state <= ST_STOP;
                        end else begin
                            bit_index <= bit_index + 1'b1;
                        end
                    end else begin
                        bit_count <= bit_count + 1'b1;
                    end
                end
                ST_STOP: begin
                    tx_reg <= 1'b1;
                    if (bit_count == CLKS_PER_BIT - 1) begin
                        bit_count <= 9'd0;
                        if (byte_index == LAST_BYTE) begin
                            state        <= ST_IDLE;
                            frame_active <= 1'b0;
                            frame_toggle <= ~frame_toggle;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                            tx_byte    <= message_byte(byte_index + 1'b1);
                            state      <= ST_START;
                        end
                    end else begin
                        bit_count <= bit_count + 1'b1;
                    end
                end
                default: state <= ST_IDLE;
            endcase
        end
    end

    assign uart_tx = tx_reg;
    // Keep RX as a real FPGA input so the pin can be used for a future command
    // path; this probe intentionally never transmits data back to the board.
    assign led[0] = ~frame_active;
    assign led[1] = ~frame_toggle;
    assign led[2] = ~uart_rx;
    assign led[3] = ~(state == ST_START);
    assign led[4] = ~(state == ST_DATA);
    assign led[5] = ~(state == ST_STOP);
endmodule
