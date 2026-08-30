`timescale 1ns/1ps

module tb_scheme_b_top_uart;

    reg clk;
    reg rst_btn;
    reg uart_rx;
    wire uart_tx;
    wire [5:0] led;

    qn88_scheme_b_top #(
        .CLK_HZ(27_000_000),
        .BAUD(115200)
    ) dut (
        .clk(clk),
        .rst_btn(rst_btn),
        .uart_rx(uart_rx),
        .uart_tx(uart_tx),
        .led(led)
    );

    always #18.518 clk = ~clk;

    localparam BIT_PERIOD = 8680.55; // 1 / 115200 s = 8.68055 us = 8680.55 ns

    task send_byte(input [7:0] data);
        integer b;
        begin
            uart_rx = 0; // Start bit
            #BIT_PERIOD;
            for (b = 0; b < 8; b = b + 1) begin
                uart_rx = data[b];
                #BIT_PERIOD;
            end
            uart_rx = 1; // Stop bit
            #BIT_PERIOD;
        end
    endtask

    task send_file_bytes(input string filepath, input integer count);
        integer f, r, i;
        reg [7:0] val;
        begin
            f = $fopen(filepath, "r");
            if (f == 0) begin
                $display("[ERROR] Cannot open %s", filepath);
                $finish;
            end
            for (i = 0; i < count; i = i + 1) begin
                r = $fscanf(f, "%x\n", val);
                send_byte(val);
            end
            $fclose(f);
        end
    endtask

    initial begin
        clk = 0;
        rst_btn = 1;
        uart_rx = 1;
        #200;
        rst_btn = 0;
        #500;

        $display("[SIM] 1. Sending ECG0 Header...");
        send_byte("E");
        send_byte("C");
        send_byte("G");
        send_byte("0");

        $display("[SIM] 2. Sending 12,000 Input Waveform bytes...");
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/input.hex", 12000);

        $display("[SIM] 3. Sending 10,293 Parameter bytes...");
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", 1344);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex",   16);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", 3584);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex",   32);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", 5120);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex",   32);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex",       160);
        send_file_bytes("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex",         5);

        $display("[SIM] All bytes sent! Waiting for inference and UART TX output...");
        #500000;
        $display("[SIM] Done waiting!");
        $finish;
    end

endmodule