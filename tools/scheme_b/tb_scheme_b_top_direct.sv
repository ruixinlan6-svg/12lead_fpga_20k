`timescale 1ns/1ps

module tb_scheme_b_top_direct;

    reg clk;
    reg rst_btn;
    reg uart_rx;
    wire uart_tx;
    wire [5:0] led;

    // Inject directly into top module internals
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

    task feed_byte(input [7:0] data);
        begin
            @(posedge clk);
            dut.uart_rx_i.byte_data <= data;
            dut.uart_rx_i.byte_valid <= 1'b1;
            @(posedge clk);
            dut.uart_rx_i.byte_valid <= 1'b0;
            // 2 wait cycles between bytes
            @(posedge clk);
            @(posedge clk);
        end
    endtask

    task feed_file(input string filepath, input integer count);
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
                feed_byte(val);
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

        $display("[SIM] 1. Feeding ECG0 Header...");
        feed_byte("E");
        feed_byte("C");
        feed_byte("G");
        feed_byte("0");

        $display("[SIM] 2. Feeding 12,000 Input Waveform bytes...");
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/input.hex", 12000);

        $display("[SIM] 3. Feeding 10,293 Parameter bytes...");
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", 1344);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex",   16);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", 3584);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex",   32);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", 5120);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex",   32);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex",       160);
        feed_file("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex",         5);

        $display("[SIM] All bytes fed! Waiting for inference completion...");
        wait(dut.model_done == 1'b1);
        @(posedge clk);
        #100;

        $display("[RESULT] Direct Feed Top-Level Logits:");
        $display("  L0 (NORM): %0d (hex: %02x)", dut.u_core.out_l0, dut.u_core.out_l0[7:0]);
        $display("  L1 (MI):   %0d (hex: %02x)", dut.u_core.out_l1, dut.u_core.out_l1[7:0]);
        $display("  L2 (STTC): %0d (hex: %02x)", dut.u_core.out_l2, dut.u_core.out_l2[7:0]);
        $display("  L3 (CD):   %0d (hex: %02x)", dut.u_core.out_l3, dut.u_core.out_l3[7:0]);
        $display("  L4 (HYP):  %0d (hex: %02x)", dut.u_core.out_l4, dut.u_core.out_l4[7:0]);

        if (dut.u_core.out_l0 === 8'sd32 && dut.u_core.out_l1 === -8'sd22 &&
            dut.u_core.out_l2 === -8'sd21 && dut.u_core.out_l3 === -8'sd19 &&
            dut.u_core.out_l4 === -8'sd21) begin
            $display(">>> [PASS] Direct Feed Top-Level is 100%% Bit-Exact! <<<");
        end else begin
            $display(">>> [FAIL] Direct Feed Top-Level Mismatch! <<<");
        end

        #200;
        $finish;
    end

endmodule