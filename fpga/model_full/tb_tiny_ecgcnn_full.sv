`timescale 1ns/1ps

module tb_tiny_ecgcnn_full;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic load_we = 1'b0;
    logic [3:0] load_kind = 4'd0;
    logic [15:0] load_index = 16'd0;
    logic signed [7:0] load_data = 8'sd0;
    logic busy, done;
    logic signed [7:0] logit0, logit1, logit2, logit3, logit4;
    integer failures = 0;
    integer i;
    integer mismatch_conv1, mismatch_relu1, mismatch_pool1;
    integer mismatch_conv2, mismatch_relu2, mismatch_pool2;
    integer mismatch_conv3, mismatch_relu3, mismatch_gap, mismatch_logits;
    reg signed [7:0] exp_conv1 [0:15999];
    reg signed [7:0] exp_relu1 [0:15999];
    reg signed [7:0] exp_pool1 [0:7999];
    reg signed [7:0] exp_conv2 [0:15999];
    reg signed [7:0] exp_relu2 [0:15999];
    reg signed [7:0] exp_pool2 [0:7999];
    reg signed [7:0] exp_conv3 [0:7999];
    reg signed [7:0] exp_relu3 [0:7999];
    reg signed [7:0] exp_gap [0:31];
    reg signed [7:0] exp_logits [0:4];

    tiny_ecgcnn_full dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .load_we(load_we), .load_kind(load_kind), .load_index(load_index),
        .load_data(load_data), .busy(busy), .done(done),
        .logit0(logit0), .logit1(logit1), .logit2(logit2),
        .logit3(logit3), .logit4(logit4)
    );

    always #5 clk = ~clk;

    initial begin
        // Private model artifacts are intentionally outside Git.  The test
        // invocation may replace this directory by editing MEMDIR below.
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/input.hex", dut.input_ram.mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", dut.w1_ram.mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex", dut.b1_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", dut.w2_ram.mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex", dut.b2_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", dut.w3_ram.mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex", dut.b3_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex", dut.wh_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex", dut.bh_mem);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/conv1.hex", exp_conv1);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/relu1.hex", exp_relu1);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool1.hex", exp_pool1);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/conv2.hex", exp_conv2);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/relu2.hex", exp_relu2);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool2.hex", exp_pool2);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/conv3.hex", exp_conv3);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/relu3.hex", exp_relu3);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex", exp_gap);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/logits.hex", exp_logits);
        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        @(negedge clk);
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;

        fork : watchdog
            begin
                repeat (10000000) @(posedge clk);
                $fatal(1, "model core timeout");
            end
            begin
                @(posedge done);
                #1;
                mismatch_conv1 = 0; mismatch_relu1 = 0; mismatch_pool1 = 0;
                mismatch_conv2 = 0; mismatch_relu2 = 0; mismatch_pool2 = 0;
                mismatch_conv3 = 0; mismatch_relu3 = 0; mismatch_gap = 0; mismatch_logits = 0;
                for (i = 0; i < 16000; i = i + 1) begin
                    if (dut.conv1_raw_mem[i] !== exp_conv1[i]) begin
                        if (mismatch_conv1 < 60) $display("[TRACE] conv1 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.conv1_raw_mem[i], exp_conv1[i]);
                        mismatch_conv1 = mismatch_conv1 + 1;
                    end
                    if (dut.relu1_shadow_mem[i] !== exp_relu1[i]) begin
                        if (mismatch_relu1 < 20) $display("[TRACE] first relu1 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.relu1_shadow_mem[i], exp_relu1[i]);
                        mismatch_relu1 = mismatch_relu1 + 1;
                    end
                    if (dut.conv2_raw_mem[i] !== exp_conv2[i]) begin
                        if (mismatch_conv2 < 60) $display("[TRACE] conv2 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.conv2_raw_mem[i], exp_conv2[i]);
                        mismatch_conv2 = mismatch_conv2 + 1;
                    end
                    if (dut.relu2_shadow_mem[i] !== exp_relu2[i] && i < 16000) begin
                        if (mismatch_relu2 < 5) $display("[TRACE] first relu2 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.relu2_shadow_mem[i], exp_relu2[i]);
                        mismatch_relu2 = mismatch_relu2 + 1;
                    end
                end
                for (i = 0; i < 8000; i = i + 1) begin
                    if (dut.pool1_ram.mem[i] !== exp_pool1[i]) begin
                        if (mismatch_pool1 < 20) $display("[TRACE] first pool1 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.pool1_ram.mem[i], exp_pool1[i]);
                        mismatch_pool1 = mismatch_pool1 + 1;
                    end
                    if (dut.pool2_ram.mem[i] !== exp_pool2[i]) begin
                        if (mismatch_pool2 < 20) $display("[TRACE] first pool2 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.pool2_ram.mem[i], exp_pool2[i]);
                        mismatch_pool2 = mismatch_pool2 + 1;
                    end
                    if (dut.conv3_raw_mem[i] !== exp_conv3[i]) begin
                        if (mismatch_conv3 < 60) $display("[TRACE] conv3 mismatch idx=%0d rtl=%0d exp=%0d", i, dut.conv3_raw_mem[i], exp_conv3[i]);
                        mismatch_conv3 = mismatch_conv3 + 1;
                    end
                    if (dut.buf3_ram.mem[i] !== exp_relu3[i]) mismatch_relu3 = mismatch_relu3 + 1;
                end
                for (i = 0; i < 32; i = i + 1) if (dut.gap_ram.mem[i] !== exp_gap[i]) mismatch_gap = mismatch_gap + 1;
                if (logit0 !== exp_logits[0]) mismatch_logits = mismatch_logits + 1;
                if (logit1 !== exp_logits[1]) mismatch_logits = mismatch_logits + 1;
                if (logit2 !== exp_logits[2]) mismatch_logits = mismatch_logits + 1;
                if (logit3 !== exp_logits[3]) mismatch_logits = mismatch_logits + 1;
                if (logit4 !== exp_logits[4]) mismatch_logits = mismatch_logits + 1;
                $display("[TRACE] mismatches conv1=%0d relu1=%0d pool1=%0d conv2=%0d relu2=%0d pool2=%0d conv3=%0d relu3=%0d gap=%0d logits=%0d", mismatch_conv1, mismatch_relu1, mismatch_pool1, mismatch_conv2, mismatch_relu2, mismatch_pool2, mismatch_conv3, mismatch_relu3, mismatch_gap, mismatch_logits);
                if (!busy && logit0 === 8'sd32 && logit1 === -8'sd22 &&
                    logit2 === -8'sd21 && logit3 === -8'sd19 && logit4 === -8'sd21) begin
                    $display("[PASS] TinyECGCNN full integer RTL logits = {%0d,%0d,%0d,%0d,%0d}", logit0, logit1, logit2, logit3, logit4);
                end else begin
                    $display("[FAIL] logits = {%0d,%0d,%0d,%0d,%0d}, expected {32,-22,-21,-19,-21}", logit0, logit1, logit2, logit3, logit4);
                    failures = failures + 1;
                end
            end
        join_any
        disable watchdog;
        if (failures != 0)
            $fatal(1, "TinyECGCNN full RTL failures=%0d", failures);
        $finish;
    end
endmodule
