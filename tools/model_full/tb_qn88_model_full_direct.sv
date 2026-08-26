`timescale 1ns/1ps

// Reduced-divider UART integration test.  The DUT parameters make each bit
// ten simulation clocks, keeping this full-payload test practical while still
// exercising the real receiver; the hardware build remains 27 MHz/115200.
module tb_qn88_model_full_direct;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_btn = 1'b1;
    reg uart_rx = 1'b1;
    wire uart_tx;
    wire [5:0] led;
    wire O_sdram_clk, O_sdram_cke, O_sdram_cs_n, O_sdram_cas_n,
         O_sdram_ras_n, O_sdram_wen_n;
    wire [3:0] O_sdram_dqm;
    wire [10:0] O_sdram_addr;
    wire [1:0] O_sdram_ba;
    wire [31:0] IO_sdram_dq;
    qn88_model_full_top #(.CLK_HZ(1152000), .BAUD(115200)) dut (
        .clk(clk), .rst_btn(rst_btn), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .led(led), .O_sdram_clk(O_sdram_clk), .O_sdram_cke(O_sdram_cke),
        .O_sdram_cs_n(O_sdram_cs_n), .O_sdram_cas_n(O_sdram_cas_n),
        .O_sdram_ras_n(O_sdram_ras_n), .O_sdram_wen_n(O_sdram_wen_n),
        .O_sdram_dqm(O_sdram_dqm), .O_sdram_addr(O_sdram_addr),
        .O_sdram_ba(O_sdram_ba), .IO_sdram_dq(IO_sdram_dq)
    );

    reg [7:0] input_mem [0:11999];
    reg [7:0] w1_mem [0:1343], b1_mem [0:15];
    reg [7:0] w2_mem [0:3583], b2_mem [0:31];
    reg [7:0] w3_mem [0:5119], b3_mem [0:31];
    reg [7:0] wh_mem [0:159], bh_mem [0:4];
    integer i;

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

    initial begin
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/input.hex", input_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", w1_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex", b1_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", w2_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex", b2_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", w3_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex", b3_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex", wh_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex", bh_mem);
        repeat (16) @(posedge clk);
        rst_btn = 1'b0;
        repeat (70000) @(posedge clk);
        send_byte("E"); send_byte("C"); send_byte("G"); send_byte("0");
        for (i = 0; i < 12000; i = i + 1) send_byte(input_mem[i]);
        for (i = 0; i < 1344; i = i + 1) send_byte(w1_mem[i]);
        for (i = 0; i < 16; i = i + 1) send_byte(b1_mem[i]);
        for (i = 0; i < 3584; i = i + 1) send_byte(w2_mem[i]);
        for (i = 0; i < 32; i = i + 1) send_byte(b2_mem[i]);
        for (i = 0; i < 5120; i = i + 1) send_byte(w3_mem[i]);
        for (i = 0; i < 32; i = i + 1) send_byte(b3_mem[i]);
        for (i = 0; i < 160; i = i + 1) send_byte(wh_mem[i]);
        for (i = 0; i < 5; i = i + 1) send_byte(bh_mem[i]);
        repeat (60000000) @(posedge clk);
        $display("[FAIL] direct wrapper timeout state=%0d led=%b", dut.state, led);
        $finish;
    end

    always @(posedge clk) begin
        if (dut.state == 5'd13) begin
            $display("[FAIL] direct SDRAM state=%0d burst=%0d read=%0d first=%h expected=%h", dut.state, dut.burst_pos, dut.read_count, dut.first_read_data, dut.first_expected_data);
            $finish;
        end
        if (dut.model_done) begin
            $display("[PASS] direct wrapper logits=%0d,%0d,%0d,%0d,%0d", dut.logit0, dut.logit1, dut.logit2, dut.logit3, dut.logit4);
            $finish;
        end
    end
endmodule
