`timescale 1ns/1ps

module tb_scheme_b_top_fast;

    reg clk;
    reg rst_btn;
    wire uart_tx;
    wire [5:0] led;

    // Direct injection into top-level RX signals
    reg [7:0] test_input [0:11999];
    reg [7:0] test_weights [0:10292];
    reg [7:0] exp_logits [0:4];

    // Instantiate Top Module
    qn88_scheme_b_top #(
        .CLK_HZ(27_000_000),
        .BAUD(115200)
    ) dut (
        .clk(clk),
        .rst_btn(rst_btn),
        .uart_rx(1'b1), // Unused in direct test
        .uart_tx(uart_tx),
        .led(led)
    );

    // Clock generation (27 MHz -> ~37.037 ns period)
    always #18.518 clk = ~clk;

    task send_byte(input [7:0] b);
    begin
        @(posedge clk);
        // Direct injection into top-level RX port
        dut.uart_rx_i.byte_data = b;
        dut.uart_rx_i.byte_valid = 1'b1;
        @(posedge clk);
        dut.uart_rx_i.byte_valid = 1'b0;
    end
    endtask

    integer i;

    initial begin
        clk = 0;
        rst_btn = 1; // Assert reset (active high button -> rst_n = 0)
        
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/input.hex", test_input);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/logits.hex", exp_logits);

        // Load all weights in sequential order
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", test_weights, 0, 1343);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex",   test_weights, 1344, 1359);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", test_weights, 1360, 4943);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex",   test_weights, 4944, 4975);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", test_weights, 4976, 10095);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex",   test_weights, 10096, 10127);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex",       test_weights, 10128, 10287);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex",         test_weights, 10288, 10292);

        #100;
        rst_btn = 0; // Deassert reset
        #100;

        $display("[SIM] 1. Sending Magic Header 'ECG0'...");
        send_byte("E");
        send_byte("C");
        send_byte("G");
        send_byte("0");

        $display("[SIM] 2. Sending 12,000 Input Bytes...");
        for (i = 0; i < 12000; i = i + 1) begin
            send_byte(test_input[i]);
        end

        $display("[SIM] 3. Sending 10,293 Weight Bytes...");
        for (i = 0; i < 10293; i = i + 1) begin
            send_byte(test_weights[i]);
        end

        $display("[SIM] 4. Payload Transmitted! Waiting for inference to complete...");
        wait(dut.model_done == 1'b1);
        $display("[SIM] Inference Finished!");

        $display("[RESULT] Top-Level Logits:");
        $display("  L0: %0d (hex: %02x, exp: %02x)", $signed(dut.out_l0), dut.out_l0, exp_logits[0]);
        $display("  L1: %0d (hex: %02x, exp: %02x)", $signed(dut.out_l1), dut.out_l1, exp_logits[1]);
        $display("  L2: %0d (hex: %02x, exp: %02x)", $signed(dut.out_l2), dut.out_l2, exp_logits[2]);
        $display("  L3: %0d (hex: %02x, exp: %02x)", $signed(dut.out_l3), dut.out_l3, exp_logits[3]);
        $display("  L4: %0d (hex: %02x, exp: %02x)", $signed(dut.out_l4), dut.out_l4, exp_logits[4]);

        if (dut.out_l0 === exp_logits[0] &&
            dut.out_l1 === exp_logits[1] &&
            dut.out_l2 === exp_logits[2] &&
            dut.out_l3 === exp_logits[3] &&
            dut.out_l4 === exp_logits[4]) begin
            $display(">>> [PASS] End-to-End Top-Level Simulation Matches Golden Perfectly! <<<");
        end else begin
            $display(">>> [FAIL] Logit Mismatch in Top-Level Simulation! <<<");
        end

        #200;
        $finish;
    end

endmodule