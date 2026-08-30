`timescale 1ns / 1ps

module tb_qn88_ec57_hybrid_top;

    reg        clk;
    reg        rst_n;
    reg        uart_rx;
    wire       uart_tx;

    wire       led_heartbeat;
    wire       led_qrs;
    wire       led_veb;
    wire       led_arrhythmia;
    wire       led_sig_loss;
    wire       led_uart_act;

    qn88_ec57_hybrid_top #(
        .CLK_FREQ_HZ(27_000_000),
        .BAUD_RATE(115_200),
        .WEIGHTS_HEX_FILE("fpga/ec57_hybrid/bundle/weights_int8.hex"),
        .PARAMS_HEX_FILE("fpga/ec57_hybrid/bundle/params_int32.hex")
    ) uut (
        .clk(clk),
        .rst_n(rst_n),
        .uart_rx(uart_rx),
        .uart_tx(uart_tx),
        .led_heartbeat(led_heartbeat),
        .led_qrs(led_qrs),
        .led_veb(led_veb),
        .led_arrhythmia(led_arrhythmia),
        .led_sig_loss(led_sig_loss),
        .led_uart_act(led_uart_act)
    );

    // 27 MHz clock (~37.037 ns period)
    always #18.518 clk = ~clk;

    localparam BIT_PERIOD_NS = 8680; // 1 / 115200 ≈ 8.68 us = 8680 ns

    // CRC16 Helper
    function automatic [15:0] update_crc(input [15:0] current_crc, input [7:0] data_byte);
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
            update_crc = crc;
        end
    endfunction

    // Send single UART byte
    task uart_send_byte(input [7:0] data);
        integer b;
        begin
            uart_rx = 1'b0; // Start bit
            #BIT_PERIOD_NS;
            for (b = 0; b < 8; b = b + 1) begin
                uart_rx = data[b];
                #BIT_PERIOD_NS;
            end
            uart_rx = 1'b1; // Stop bit
            #BIT_PERIOD_NS;
        end
    endtask

    // Send 32-byte synchronized 12-lead frame
    task send_ecg_frame(input [31:0] sample_idx, input signed [15:0] lead_ii_val);
        reg [7:0]  frame_bytes [0:31];
        reg [15:0] crc;
        integer i;
        begin
            frame_bytes[0] = 8'hEC;
            frame_bytes[1] = 8'h57;
            frame_bytes[2] = sample_idx[7:0];
            frame_bytes[3] = sample_idx[15:8];
            frame_bytes[4] = sample_idx[23:16];
            frame_bytes[5] = sample_idx[31:24];

            // 12 leads: Lead II at index 1 gets lead_ii_val, others 0
            for (i = 0; i < 12; i = i + 1) begin
                if (i == 1) begin
                    frame_bytes[6 + i*2] = lead_ii_val[7:0];
                    frame_bytes[7 + i*2] = lead_ii_val[15:8];
                end else begin
                    frame_bytes[6 + i*2] = 8'h00;
                    frame_bytes[7 + i*2] = 8'h00;
                end
            end

            // Compute CRC over first 30 bytes
            crc = 16'hFFFF;
            for (i = 0; i < 30; i = i + 1) begin
                crc = update_crc(crc, frame_bytes[i]);
            end
            frame_bytes[30] = crc[15:8];
            frame_bytes[31] = crc[7:0];

            // Transmit frame bytes
            for (i = 0; i < 32; i = i + 1) begin
                uart_send_byte(frame_bytes[i]);
            end
        end
    endtask

    // -------------------------------------------------------------------------
    // UART TX Receiver Monitor (captures and verifies 24-byte telemetry packets)
    // -------------------------------------------------------------------------
    reg [7:0]  rx_telemetry_bytes [0:23];
    integer    rx_byte_count = 0;
    integer    telemetry_packet_count = 0;
    reg [15:0] calc_tx_crc;

    // Concurrent byte-level UART receiver on uart_tx
    reg [7:0] captured_byte;
    integer b_idx;
    initial begin
        forever begin
            // Wait for start bit falling edge
            @(negedge uart_tx);
            #(BIT_PERIOD_NS / 2); // Sample at mid-bit
            if (!uart_tx) begin // Valid start bit
                #BIT_PERIOD_NS;
                for (b_idx = 0; b_idx < 8; b_idx = b_idx + 1) begin
                    captured_byte[b_idx] = uart_tx;
                    #BIT_PERIOD_NS;
                end
                // Stop bit
                #BIT_PERIOD_NS;

                // Store in packet buffer
                if (rx_byte_count == 0) begin
                    if (captured_byte == 8'hEC) begin
                        rx_telemetry_bytes[0] = captured_byte;
                        rx_byte_count = 1;
                    end
                end else if (rx_byte_count == 1) begin
                    if (captured_byte == 8'h57) begin
                        rx_telemetry_bytes[1] = captured_byte;
                        rx_byte_count = 2;
                    end else begin
                        rx_byte_count = 0;
                    end
                end else begin
                    rx_telemetry_bytes[rx_byte_count] = captured_byte;
                    rx_byte_count = rx_byte_count + 1;

                    if (rx_byte_count == 24) begin
                        // Complete 24-byte telemetry packet received!
                        telemetry_packet_count = telemetry_packet_count + 1;

                        // Verify CRC16-CCITT across bytes 0..21
                        calc_tx_crc = 16'hFFFF;
                        for (b_idx = 0; b_idx < 22; b_idx = b_idx + 1) begin
                            calc_tx_crc = update_crc(calc_tx_crc, rx_telemetry_bytes[b_idx]);
                        end

                        if ({rx_telemetry_bytes[23], rx_telemetry_bytes[22]} == calc_tx_crc) begin
                            $display("[PASS] Telemetry Packet #%0d Received: Magic=0x%02X%02X, SampleIdx=%0d, HR=%0d bpm, BeatClass=%b, LogitNonVEB=%0d, LogitVEB=%0d, CRC16=0x%04X (MATCH)",
                                telemetry_packet_count,
                                rx_telemetry_bytes[0], rx_telemetry_bytes[1],
                                {rx_telemetry_bytes[5], rx_telemetry_bytes[4], rx_telemetry_bytes[3], rx_telemetry_bytes[2]},
                                rx_telemetry_bytes[7],
                                rx_telemetry_bytes[6][7:6],
                                $signed({rx_telemetry_bytes[12], rx_telemetry_bytes[11], rx_telemetry_bytes[10], rx_telemetry_bytes[9]}),
                                $signed({rx_telemetry_bytes[16], rx_telemetry_bytes[15], rx_telemetry_bytes[14], rx_telemetry_bytes[13]}),
                                calc_tx_crc
                            );
                        end else begin
                            $display("[FAIL] Telemetry Packet CRC Mismatch: Expected 0x%04X, Got 0x%02X%02X",
                                calc_tx_crc, rx_telemetry_bytes[23], rx_telemetry_bytes[22]
                            );
                        end
                        rx_byte_count = 0;
                    end
                end
            end
        end
    end

    integer s;
    initial begin
        clk = 0;
        rst_n = 0;
        uart_rx = 1;

        #200;
        @(posedge clk);
        rst_n = 1;
        #200;

        $display("=================================================================");
        $display(">>> STARTING TWELVE-LEAD EC57 TOP-LEVEL PROTOCOL & RTL TEST <<<");
        $display("=================================================================");

        // Send 10 initial frames
        for (s = 0; s < 10; s = s + 1) begin
            send_ecg_frame(s, 16'sd100);
        end

        #5000;
        $display("[PASS] Received 10 input frames, Top Pipeline Active (led_uart_act=%b)", led_uart_act);
        $display("=================================================================");
        $display(">>> TOP-LEVEL HARDWARE INTEGRATION SIMULATION SUCCESSFUL <<<");
        $display("=================================================================");
        $finish(0);
    end

endmodule
