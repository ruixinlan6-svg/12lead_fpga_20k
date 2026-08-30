`timescale 1ns/1ps

module tb_scheme_b_top_accurate;

    reg clk;
    reg rst_btn;
    reg uart_rx;
    wire uart_tx;
    wire [5:0] led;

    qn88_scheme_b_top #(
        .CLK_HZ(1152000),
        .BAUD(115200)
    ) dut (
        .clk(clk),
        .rst_btn(rst_btn),
        .uart_rx(uart_rx),
        .uart_tx(uart_tx),
        .led(led)
    );

    always #5 clk = ~clk; // 10 ns clock period = 100 MHz (scale for fast sim)

    localparam integer CPB = 10;

    task send_byte(input [7:0] value);
        integer bit_no;
        begin
            uart_rx = 1'b0;
            repeat (CPB) @(posedge clk);
            for (bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
                uart_rx = value[bit_no];
                repeat (CPB) @(posedge clk);
            end
            uart_rx = 1'b1;
            repeat (CPB) @(posedge clk);
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
        repeat (10) @(posedge clk);
        rst_btn = 0;
        repeat (20) @(posedge clk);

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

        $display("[SIM] All bytes sent! Waiting for top-level inference to complete...");
        @(posedge dut.model_done);
        $display("[SIM] Model Done! Checking Output Logits:");
        $display("  L0 = %0d (hex: %02x, exp: 20)", dut.out_l0, (dut.out_l0 + 256) & 8'hFF);
        $display("  L1 = %0d (hex: %02x, exp: ea)", dut.out_l1, (dut.out_l1 + 256) & 8'hFF);
        $display("  L2 = %0d (hex: %02x, exp: eb)", dut.out_l2, (dut.out_l2 + 256) & 8'hFF);
        $display("  L3 = %0d (hex: %02x, exp: ed)", dut.out_l3, (dut.out_l3 + 256) & 8'hFF);
        $display("  L4 = %0d (hex: %02x, exp: eb)", dut.out_l4, (dut.out_l4 + 256) & 8'hFF);

        if (dut.out_l0 == 32 && dut.out_l1 == -22 && dut.out_l2 == -21 && dut.out_l3 == -19 && dut.out_l4 == -21) begin
            $display(">>> [PASS] End-to-End UART Top-Level Simulation Matches Golden Perfectly! <<<");
        end else begin
            $display(">>> [FAIL] Logit Mismatch in End-to-End UART Top-Level Simulation! <<<");
        end
        $finish;
    end

endmodule