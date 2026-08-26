`timescale 1ns/1ps

// Small synthesizable 8-N-1 transmitter used only for board observability.
// frame_data is little-endian by byte: byte 0 is frame_data[7:0].
module qn88_uart_frame_tx #(
    parameter integer CLK_HZ = 27000000,
    parameter integer BAUD = 115200
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         start,
    input  wire [255:0] frame_data,
    input  wire [5:0]   frame_len,
    output wire         tx,
    output reg          busy,
    output reg          done
);
    localparam integer CLKS_PER_BIT = (CLK_HZ + (BAUD / 2)) / BAUD;
    localparam [1:0] ST_IDLE = 2'd0, ST_START = 2'd1,
                     ST_DATA = 2'd2, ST_STOP = 2'd3;

    reg [1:0] state;
    reg [8:0] bit_count;
    reg [2:0] bit_index;
    reg [5:0] bytes_left;
    reg [255:0] shift_reg;
    reg [7:0] byte_reg;
    reg tx_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= ST_IDLE;
            bit_count  <= 9'd0;
            bit_index  <= 3'd0;
            bytes_left <= 6'd0;
            shift_reg  <= 256'd0;
            byte_reg   <= 8'hFF;
            tx_reg     <= 1'b1;
            busy       <= 1'b0;
            done       <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                ST_IDLE: begin
                    tx_reg <= 1'b1;
                    busy <= 1'b0;
                    if (start && (frame_len != 0)) begin
                        state      <= ST_START;
                        busy       <= 1'b1;
                        bit_count  <= 9'd0;
                        bit_index  <= 3'd0;
                        bytes_left <= frame_len;
                        shift_reg  <= frame_data;
                        byte_reg   <= frame_data[7:0];
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
                    tx_reg <= byte_reg[bit_index];
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
                        if (bytes_left <= 6'd1) begin
                            state <= ST_IDLE;
                            busy <= 1'b0;
                            done <= 1'b1;
                            bytes_left <= 6'd0;
                        end else begin
                            bytes_left <= bytes_left - 1'b1;
                            shift_reg <= shift_reg >> 8;
                            byte_reg <= shift_reg[15:8];
                            state <= ST_START;
                        end
                    end else begin
                        bit_count <= bit_count + 1'b1;
                    end
                end
                default: state <= ST_IDLE;
            endcase
        end
    end

    assign tx = tx_reg;
endmodule
