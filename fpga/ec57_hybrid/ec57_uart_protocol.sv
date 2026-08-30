`timescale 1ns / 1ps

// =============================================================================
// Module: ec57_uart_protocol
// Description: Robust UART frame parser and telemetry packet serializer for
//              Twelve-Lead EC57 FPGA.
//
// Complies with:
//   - docs/superpowers/plans/2026-08-27-qn88-ec57-hybrid-implementation.md
//   - Baud Rate: 115,200 bps @ 27.000 MHz (Clock Divisor = 234.375 -> 234)
//   - Frame Magic: 0xEC57
//   - Full CRC16 CCITT (0x1021) verification and generation.
// =============================================================================

module ec57_uart_protocol #(
    parameter CLK_FREQ_HZ = 27_000_000,
    parameter BAUD_RATE   = 115_200
)(
    input  wire        clk,
    input  wire        rst_n,

    // Physical UART Pins
    input  wire        uart_rx,             // Pin 70
    output reg         uart_tx,             // Pin 69

    // Demodulated Sample Stream to FPGA Pipeline
    output reg         rx_sample_valid,
    output reg  [31:0] rx_sample_index,
    output reg  [31:0] rx_sample_time_ms,
    output reg  signed [15:0] rx_lead_samples [0:11],

    // Telemetry from FPGA Pipeline to UART TX
    input  wire        tx_telemetry_valid,
    input  wire [31:0] tx_sample_index,
    input  wire [31:0] tx_timestamp_ms,
    input  wire [3:0]  tx_valid_leads,
    input  wire [7:0]  tx_hr_bpm,
    input  wire        tx_hr_valid,
    input  wire        tx_qrs_valid,
    input  wire [1:0]  tx_beat_class,       // 00=nonV, 01=V
    input  wire signed [31:0] tx_logit_non_veb,
    input  wire signed [31:0] tx_logit_veb,
    input  wire [7:0]  tx_active_rhythms,   // [0:loss, 1:brady, 2:tachy, 3:asystole, 4:run, 5:vt, 6:bigeminy, 7:trigeminy]
    input  wire [15:0] tx_crc_err_count,

    output reg         tx_busy
);

    localparam CLK_PER_BIT = CLK_FREQ_HZ / BAUD_RATE; // 234 cycles

    // -------------------------------------------------------------------------
    // CRC16-CCITT (Polynomial 0x1021, init 0xFFFF)
    // -------------------------------------------------------------------------
    function automatic [15:0] update_crc16(input [15:0] current_crc, input [7:0] data_byte);
        logic [15:0] crc;
        logic [7:0]  d;
        integer b;
        begin
            crc = current_crc;
            d = data_byte;
            for (b = 0; b < 8; b = b + 1) begin
                if ((crc[15] ^ d[7]) == 1'b1)
                    crc = ((crc << 1) ^ 16'h1021);
                else
                    crc = (crc << 1);
                d = d << 1;
            end
            update_crc16 = crc;
        end
    endfunction

    // -------------------------------------------------------------------------
    // UART Byte Receiver (RX)
    // -------------------------------------------------------------------------
    reg [2:0]  rx_sync;
    wire       rx_in = rx_sync[2];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) rx_sync <= 3'b111;
        else rx_sync <= {rx_sync[1:0], uart_rx};
    end

    reg [1:0]  rx_fsm;
    reg [15:0] rx_clk_cnt;
    reg [3:0]  rx_bit_idx;
    reg [7:0]  rx_byte_shift;
    reg        rx_byte_valid;
    reg [7:0]  rx_byte;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_fsm        <= 2'd0;
            rx_clk_cnt    <= 16'd0;
            rx_bit_idx    <= 4'd0;
            rx_byte_shift <= 8'd0;
            rx_byte_valid <= 1'b0;
            rx_byte       <= 8'd0;
        end else begin
            rx_byte_valid <= 1'b0;
            case (rx_fsm)
                2'd0: begin // Wait for start bit (low)
                    if (!rx_in) begin
                        if (rx_clk_cnt == (CLK_PER_BIT / 2)) begin
                            rx_clk_cnt <= 16'd0;
                            rx_bit_idx <= 4'd0;
                            rx_fsm     <= 2'd1;
                        end else begin
                            rx_clk_cnt <= rx_clk_cnt + 16'd1;
                        end
                    end else begin
                        rx_clk_cnt <= 16'd0;
                    end
                end

                2'd1: begin // Receive 8 data bits
                    if (rx_clk_cnt == CLK_PER_BIT - 1) begin
                        rx_clk_cnt    <= 16'd0;
                        rx_byte_shift <= {rx_in, rx_byte_shift[7:1]};
                        if (rx_bit_idx == 4'd7) begin
                            rx_fsm <= 2'd2;
                        end else begin
                            rx_bit_idx <= rx_bit_idx + 4'd1;
                        end
                    end else begin
                        rx_clk_cnt <= rx_clk_cnt + 16'd1;
                    end
                end

                2'd2: begin // Stop bit
                    if (rx_clk_cnt == CLK_PER_BIT - 1) begin
                        rx_clk_cnt    <= 16'd0;
                        rx_byte       <= rx_byte_shift;
                        rx_byte_valid <= 1'b1;
                        rx_fsm        <= 2'd0;
                    end else begin
                        rx_clk_cnt <= rx_clk_cnt + 16'd1;
                    end
                end
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // RX Frame Parser FSM
    // Payload format:
    //   Magic: 0xEC, 0x57 (2 bytes)
    //   Sample Index: 4 bytes (little-endian)
    //   12 Leads x 2 bytes int16: 24 bytes (little-endian)
    //   CRC16: 2 bytes
    // Total Frame: 32 bytes
    // -------------------------------------------------------------------------
    reg [4:0]  parse_byte_idx;
    reg [15:0] parse_crc;
    reg [7:0]  frame_buf [0:31];

    integer l;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            parse_byte_idx  <= 5'd0;
            parse_crc       <= 16'hFFFF;
            rx_sample_valid <= 1'b0;
            rx_sample_index <= 32'd0;
            rx_sample_time_ms <= 32'd0;
            for (l = 0; l < 12; l = l + 1) rx_lead_samples[l] <= 16'sd0;
        end else begin
            rx_sample_valid <= 1'b0;

            if (rx_byte_valid) begin
                frame_buf[parse_byte_idx] <= rx_byte;

                if (parse_byte_idx == 5'd0) begin
                    if (rx_byte == 8'hEC) begin
                        parse_crc <= update_crc16(16'hFFFF, rx_byte);
                        parse_byte_idx <= 5'd1;
                    end
                end else if (parse_byte_idx == 5'd1) begin
                    if (rx_byte == 8'h57) begin
                        parse_crc <= update_crc16(parse_crc, rx_byte);
                        parse_byte_idx <= 5'd2;
                    end else begin
                        parse_byte_idx <= 5'd0;
                    end
                end else if (parse_byte_idx < 5'd30) begin
                    parse_crc <= update_crc16(parse_crc, rx_byte);
                    parse_byte_idx <= parse_byte_idx + 5'd1;
                end else if (parse_byte_idx == 5'd30) begin
                    parse_byte_idx <= 5'd31;
                end else begin
                    // Byte 31: Frame complete, check CRC
                    logic [15:0] exp_crc;
                    exp_crc = {frame_buf[30], rx_byte};
                    if (parse_crc == exp_crc) begin
                        // Valid frame! Extract sample data
                        rx_sample_valid   <= 1'b1;
                        rx_sample_index   <= {frame_buf[5], frame_buf[4], frame_buf[3], frame_buf[2]};
                        rx_sample_time_ms <= {frame_buf[5], frame_buf[4], frame_buf[3], frame_buf[2]} * 32'd4; // 4ms per sample

                        for (l = 0; l < 12; l = l + 1) begin
                            rx_lead_samples[l] <= $signed({frame_buf[7 + l*2], frame_buf[6 + l*2]});
                        end
                    end
                    parse_byte_idx <= 5'd0;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // UART Telemetry Packet Transmitter (TX)
    // Packet Format (24 bytes):
    //   Byte 0..1:   Magic: 0xEC, 0x57 (2 bytes)
    //   Byte 2..5:   Sample Index: 4 bytes (little-endian)
    //   Byte 6:      Flags: beat_class [7:6], qrs_valid [5], hr_valid [4], valid_leads [3:0] (1 byte)
    //   Byte 7:      HR (bpm): 1 byte
    //   Byte 8:      Active Rhythms: 1 byte
    //   Byte 9..12:  Logits Non-VEB: 4 bytes (signed int32, little-endian)
    //   Byte 13..16: Logits VEB: 4 bytes (signed int32, little-endian)
    //   Byte 17:     CRC Error Count: 1 byte
    //   Byte 18..21: Timestamp ms: 4 bytes (little-endian)
    //   Byte 22..23: CRC16-CCITT: 2 bytes (little-endian)
    // -------------------------------------------------------------------------
    reg [7:0]  tx_packet [0:21];
    reg [4:0]  tx_byte_idx;
    reg [1:0]  tx_fsm;
    reg [15:0] tx_clk_cnt;
    reg [3:0]  tx_bit_idx;
    reg [7:0]  tx_byte_shift;
    reg [15:0] tx_crc;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            uart_tx       <= 1'b1;
            tx_busy       <= 1'b0;
            tx_fsm        <= 2'd0;
            tx_byte_idx   <= 5'd0;
            tx_clk_cnt    <= 16'd0;
            tx_bit_idx    <= 4'd0;
            tx_byte_shift <= 8'd0;
            tx_crc        <= 16'hFFFF;
        end else begin
            case (tx_fsm)
                2'd0: begin // Idle: wait for telemetry packet request
                    if (tx_telemetry_valid && !tx_busy) begin
                        tx_busy <= 1'b1;

                        // Assemble payload (bytes 0..21)
                        tx_packet[0]  <= 8'hEC;
                        tx_packet[1]  <= 8'h57;
                        tx_packet[2]  <= tx_sample_index[7:0];
                        tx_packet[3]  <= tx_sample_index[15:8];
                        tx_packet[4]  <= tx_sample_index[23:16];
                        tx_packet[5]  <= tx_sample_index[31:24];
                        tx_packet[6]  <= {tx_beat_class, tx_qrs_valid, tx_hr_valid, tx_valid_leads};
                        tx_packet[7]  <= tx_hr_bpm;
                        tx_packet[8]  <= tx_active_rhythms;
                        tx_packet[9]  <= tx_logit_non_veb[7:0];
                        tx_packet[10] <= tx_logit_non_veb[15:8];
                        tx_packet[11] <= tx_logit_non_veb[23:16];
                        tx_packet[12] <= tx_logit_non_veb[31:24];
                        tx_packet[13] <= tx_logit_veb[7:0];
                        tx_packet[14] <= tx_logit_veb[15:8];
                        tx_packet[15] <= tx_logit_veb[23:16];
                        tx_packet[16] <= tx_logit_veb[31:24];
                        tx_packet[17] <= tx_crc_err_count[7:0];
                        tx_packet[18] <= tx_timestamp_ms[7:0];
                        tx_packet[19] <= tx_timestamp_ms[15:8];
                        tx_packet[20] <= tx_timestamp_ms[23:16];
                        tx_packet[21] <= tx_timestamp_ms[31:24];

                        tx_byte_idx   <= 5'd0;
                        tx_clk_cnt    <= 16'd0;
                        tx_bit_idx    <= 4'd0;
                        tx_byte_shift <= 8'hEC; // First byte (Magic 0xEC)
                        tx_crc        <= update_crc16(16'hFFFF, 8'hEC);
                        uart_tx       <= 1'b0;  // Start bit
                        tx_fsm        <= 2'd1;
                    end
                end

                2'd1: begin // Transmitting 8 data bits
                    if (tx_clk_cnt == CLK_PER_BIT - 1) begin
                        tx_clk_cnt <= 16'd0;
                        uart_tx    <= tx_byte_shift[0];
                        tx_byte_shift <= {1'b1, tx_byte_shift[7:1]};
                        if (tx_bit_idx == 4'd7) begin
                            tx_fsm <= 2'd2;
                        end else begin
                            tx_bit_idx <= tx_bit_idx + 4'd1;
                        end
                    end else begin
                        tx_clk_cnt <= tx_clk_cnt + 16'd1;
                    end
                end

                2'd2: begin // Transmitting Stop bit
                    if (tx_clk_cnt == CLK_PER_BIT - 1) begin
                        tx_clk_cnt <= 16'd0;
                        uart_tx    <= 1'b1; // Stop bit high
                        if (tx_byte_idx == 5'd23) begin
                            tx_busy <= 1'b0;
                            tx_fsm  <= 2'd0;
                        end else begin
                            tx_byte_idx <= tx_byte_idx + 5'd1;
                            tx_bit_idx  <= 4'd0;
                            uart_tx     <= 1'b0; // Next start bit
                            tx_fsm      <= 2'd1;

                            if (tx_byte_idx < 5'd21) begin
                                tx_byte_shift <= tx_packet[tx_byte_idx + 1];
                                tx_crc        <= update_crc16(tx_crc, tx_packet[tx_byte_idx + 1]);
                            end else if (tx_byte_idx == 5'd21) begin
                                tx_byte_shift <= tx_crc[7:0];  // CRC16 Low Byte
                            end else if (tx_byte_idx == 5'd22) begin
                                tx_byte_shift <= tx_crc[15:8]; // CRC16 High Byte
                            end
                        end
                    end else begin
                        tx_clk_cnt <= tx_clk_cnt + 16'd1;
                    end
                end
            endcase
        end
    end

endmodule
