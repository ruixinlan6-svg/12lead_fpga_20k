`timescale 1ns/1ps

module qn88_uart_byte_rx #(
    parameter integer CLK_HZ = 27000000,
    parameter integer BAUD = 115200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rx,
    output reg        byte_valid,
    output reg [7:0]  byte_data,
    output reg        framing_error
);
    localparam integer CLKS_PER_BIT = (CLK_HZ + (BAUD / 2)) / BAUD;
    localparam integer HALF_BIT = CLKS_PER_BIT / 2;
    localparam [1:0] ST_IDLE = 2'd0, ST_START = 2'd1,
                     ST_DATA = 2'd2, ST_STOP = 2'd3;

    reg [1:0] state;
    reg [8:0] tick;
    reg [2:0] bit_index;
    reg [7:0] shift_reg;
    reg rx_meta, rx_sync;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_IDLE;
            tick <= 0;
            bit_index <= 0;
            shift_reg <= 0;
            rx_meta <= 1'b1;
            rx_sync <= 1'b1;
            byte_valid <= 1'b0;
            byte_data <= 0;
            framing_error <= 1'b0;
        end else begin
            rx_meta <= rx;
            rx_sync <= rx_meta;
            byte_valid <= 1'b0;
            framing_error <= 1'b0;
            case (state)
                ST_IDLE: begin
                    tick <= 0;
                    if (!rx_sync) begin
                        state <= ST_START;
                        tick <= 0;
                    end
                end
                ST_START: begin
                    if (tick == HALF_BIT - 1) begin
                        tick <= 0;
                        if (!rx_sync) begin
                            bit_index <= 0;
                            state <= ST_DATA;
                        end else begin
                            state <= ST_IDLE;
                        end
                    end else begin
                        tick <= tick + 1'b1;
                    end
                end
                ST_DATA: begin
                    if (tick == CLKS_PER_BIT - 1) begin
                        tick <= 0;
                        shift_reg[bit_index] <= rx_sync;
                        if (bit_index == 3'd7)
                            state <= ST_STOP;
                        else
                            bit_index <= bit_index + 1'b1;
                    end else begin
                        tick <= tick + 1'b1;
                    end
                end
                ST_STOP: begin
                    if (tick == CLKS_PER_BIT - 1) begin
                        tick <= 0;
                        state <= ST_IDLE;
                        if (rx_sync) begin
                            byte_data <= shift_reg;
                            byte_valid <= 1'b1;
                        end else begin
                            framing_error <= 1'b1;
                        end
                    end else begin
                        tick <= tick + 1'b1;
                    end
                end
                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule