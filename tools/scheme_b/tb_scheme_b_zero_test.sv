`timescale 1ns/1ps

module tb_scheme_b_zero_test;

    reg clk;
    reg rst_n;

    // DMA interface
    reg        dma_start;
    reg [2:0]  dma_mode;
    wire       dma_done;

    // Storage RAM interface
    reg         storage_wr_en;
    reg  [13:0] storage_wr_addr;
    reg  [7:0]  storage_wr_data;
    wire        storage_rd_en;
    wire [13:0] storage_rd_addr;
    wire [7:0]  storage_rd_data;

    // Core interconnect wires
    wire        dma_w_en;
    wire [12:0] dma_w_addr;
    wire [7:0]  dma_w_data;
    wire        dma_b_en;
    wire [5:0]  dma_b_addr;
    wire [7:0]  dma_b_data;
    wire        dma_in_en;
    wire [13:0] dma_in_addr;
    wire [7:0]  dma_in_data;

    // Core execution interface
    reg        layer_start;
    reg [2:0]  layer_id;
    wire       layer_done;

    wire signed [7:0] out_l0, out_l1, out_l2, out_l3, out_l4;

    // Expected Golden Buffers
    reg signed [7:0] exp_pool1 [0:7999];
    reg signed [7:0] exp_pool2 [0:7999];
    reg signed [7:0] exp_relu3 [0:7999];
    reg signed [7:0] exp_gap   [0:31];
    reg signed [7:0] exp_logits[0:4];

    // Instantiate Weight Storage RAM
    ecg_sync_dp_ram #(.ADDR_WIDTH(14), .DEPTH(16384)) u_storage (
        .clk(clk),
        .wr_en(storage_wr_en),
        .wr_addr(storage_wr_addr),
        .wr_data(storage_wr_data),
        .rd_en(storage_rd_en),
        .rd_addr(storage_rd_addr),
        .rd_data(storage_rd_data)
    );

    // Instantiate DMA controller
    sdram_layer_dma u_dma (
        .clk(clk),
        .rst_n(rst_n),
        .dma_start(dma_start),
        .dma_mode(dma_mode),
        .dma_done(dma_done),
        .storage_rd_en(storage_rd_en),
        .storage_rd_addr(storage_rd_addr),
        .storage_rd_data(storage_rd_data),
        .dma_w_en(dma_w_en),
        .dma_w_addr(dma_w_addr),
        .dma_w_data(dma_w_data),
        .dma_b_en(dma_b_en),
        .dma_b_addr(dma_b_addr),
        .dma_b_data(dma_b_data),
        .dma_in_en(dma_in_en),
        .dma_in_addr(dma_in_addr),
        .dma_in_data(dma_in_data)
    );

    // Instantiate Scheme B Stream Core
    tiny_ecgcnn_stream_core u_core (
        .clk(clk),
        .rst_n(rst_n),
        .layer_start(layer_start),
        .layer_id(layer_id),
        .layer_done(layer_done),
        .dma_w_en(dma_w_en),
        .dma_w_addr(dma_w_addr),
        .dma_w_data(dma_w_data),
        .dma_b_en(dma_b_en),
        .dma_b_addr(dma_b_addr[4:0]),
        .dma_b_data(dma_b_data),
        .dma_in_en(dma_in_en),
        .dma_in_addr(dma_in_addr),
        .dma_in_data(dma_in_data),
        .out_l0(out_l0),
        .out_l1(out_l1),
        .out_l2(out_l2),
        .out_l3(out_l3),
        .out_l4(out_l4)
    );

    // Clock generation (27 MHz -> 37.037 ns period)
    always #18.518 clk = ~clk;

    task load_file_to_storage(input string filepath, input integer base_addr, input integer byte_count);
        integer f, r, i;
        reg [7:0] byte_val;
        begin
            f = $fopen(filepath, "r");
            if (f == 0) begin
                $display("[ERROR] Cannot open %s", filepath);
                $finish;
            end
            for (i = 0; i < byte_count; i = i + 1) begin
                r = $fscanf(f, "%x\n", byte_val);
                u_storage.mem[base_addr + i] = byte_val;
            end
            $fclose(f);
        end
    endtask

    integer i;
    integer err_p1, err_p2, err_r3, err_gap;

    initial begin
        clk = 0;
        rst_n = 0;
        dma_start = 0;
        dma_mode = 0;
        layer_start = 0;
        layer_id = 0;
        storage_wr_en = 0;
        storage_wr_addr = 0;
        storage_wr_data = 0;

        $display("[SIM] Loading Storage Memory and Golden files...");
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_0_weight.hex", 0, 1344);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_0_bias.hex",   1344, 16);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_3_weight.hex", 1360, 3584);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_3_bias.hex",   4944, 32);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_6_weight.hex", 4976, 5120);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/features_6_bias.hex",   10096, 32);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/head_weight.hex",       10128, 160);
        load_file_to_storage("runs/20260826-1929-m2-input-quant-contract/hex/head_bias.hex",         10288, 5);

        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool1.hex", exp_pool1);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/pool2.hex", exp_pool2);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/relu3.hex", exp_relu3);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/gap.hex", exp_gap);
        $readmemh("runs/20260826-1929-m2-input-quant-contract/expected_hex/logits.hex", exp_logits);

        #100;
        rst_n = 1;
        #100;

        // 1. Load Input Waveform
        $display("[SIM] 1. Loading Input Waveform directly into ActBuf_A...");
        // No input loaded (all zeros)
        $display("[SIM] Input Waveform Loaded!");

        // 2. Layer 1 (Conv1D + ReLU + MaxPool)
        $display("[SIM] 2. Executing Layer 1 (Conv1D 12->16 + ReLU1 + MaxPool)...");
        @(posedge clk);
        dma_mode = 3'd1;
        dma_start = 1'b1;
        @(posedge clk);
        dma_start = 1'b0;
                @(posedge dma_done);
        $display("[DEBUG DMA] First 5 weights loaded in WeightBuf: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.weight_buf.mem[0]), $signed(u_core.weight_buf.mem[1]),
                 $signed(u_core.weight_buf.mem[2]), $signed(u_core.weight_buf.mem[3]),
                 $signed(u_core.weight_buf.mem[4]));
        $display("[DEBUG DMA] First 5 biases loaded in bias_mem: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.bias_mem[0]), $signed(u_core.bias_mem[1]),
                 $signed(u_core.bias_mem[2]), $signed(u_core.bias_mem[3]),
                 $signed(u_core.bias_mem[4]));
        @(posedge clk);
        layer_id = 3'd1;
        layer_start = 1'b1;
        @(posedge clk);
        layer_start = 1'b0;
        @(posedge layer_done);
        $display("[SIM] Layer 1 Finished!");

        err_p1 = 0;
        for (i = 0; i < 8000; i = i + 1) begin
            if (u_core.act_buf_b.mem[i] !== exp_pool1[i]) begin
                if (err_p1 < 5) $display("[CHECK P1] mismatch at %0d: rtl=%0d exp=%0d", i, $signed(u_core.act_buf_b.mem[i]), exp_pool1[i]);
                err_p1 = err_p1 + 1;
            end
        end
        $display("[CHECK P1] Total Mismatches: %0d / 8000", err_p1);

        // 3. Layer 2 (Conv1D + ReLU + MaxPool)
        $display("[SIM] 3. Executing Layer 2 (Conv1D 16->32 + ReLU2 + MaxPool)...");
        @(posedge clk);
        dma_mode = 3'd2;
        dma_start = 1'b1;
        @(posedge clk);
        dma_start = 1'b0;
                @(posedge dma_done);
        $display("[DEBUG DMA] First 5 weights loaded in WeightBuf: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.weight_buf.mem[0]), $signed(u_core.weight_buf.mem[1]),
                 $signed(u_core.weight_buf.mem[2]), $signed(u_core.weight_buf.mem[3]),
                 $signed(u_core.weight_buf.mem[4]));
        $display("[DEBUG DMA] First 5 biases loaded in bias_mem: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.bias_mem[0]), $signed(u_core.bias_mem[1]),
                 $signed(u_core.bias_mem[2]), $signed(u_core.bias_mem[3]),
                 $signed(u_core.bias_mem[4]));
        @(posedge clk);
        layer_id = 3'd2;
        layer_start = 1'b1;
        @(posedge clk);
        layer_start = 1'b0;
        @(posedge layer_done);
        $display("[SIM] Layer 2 Finished!");

        err_p2 = 0;
        for (i = 0; i < 8000; i = i + 1) begin
            if (u_core.act_buf_a.mem[i] !== exp_pool2[i]) begin
                if (err_p2 < 5) $display("[CHECK P2] mismatch at %0d: rtl=%0d exp=%0d", i, $signed(u_core.act_buf_a.mem[i]), exp_pool2[i]);
                err_p2 = err_p2 + 1;
            end
        end
        $display("[CHECK P2] Total Mismatches: %0d / 8000", err_p2);

        // 4. Layer 3 (Conv1D + ReLU)
        $display("[SIM] 4. Executing Layer 3 (Conv1D 32->32 + ReLU3)...");
        @(posedge clk);
        dma_mode = 3'd3;
        dma_start = 1'b1;
        @(posedge clk);
        dma_start = 1'b0;
                @(posedge dma_done);
        $display("[DEBUG DMA] First 5 weights loaded in WeightBuf: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.weight_buf.mem[0]), $signed(u_core.weight_buf.mem[1]),
                 $signed(u_core.weight_buf.mem[2]), $signed(u_core.weight_buf.mem[3]),
                 $signed(u_core.weight_buf.mem[4]));
        $display("[DEBUG DMA] First 5 biases loaded in bias_mem: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.bias_mem[0]), $signed(u_core.bias_mem[1]),
                 $signed(u_core.bias_mem[2]), $signed(u_core.bias_mem[3]),
                 $signed(u_core.bias_mem[4]));
        @(posedge clk);
        layer_id = 3'd3;
        layer_start = 1'b1;
        @(posedge clk);
        layer_start = 1'b0;
        @(posedge layer_done);
        $display("[SIM] Layer 3 Finished!");

        err_r3 = 0;
        for (i = 0; i < 8000; i = i + 1) begin
            if (u_core.act_buf_b.mem[i] !== exp_relu3[i]) begin
                if (err_r3 < 5) $display("[CHECK R3] mismatch at %0d: rtl=%0d exp=%0d", i, $signed(u_core.act_buf_b.mem[i]), exp_relu3[i]);
                err_r3 = err_r3 + 1;
            end
        end
        $display("[CHECK R3] Total Mismatches: %0d / 8000", err_r3);

        // 5. Layer 4 (Global Average Pooling)
        $display("[SIM] 5. Executing Layer 4 (Global Average Pooling)...");
        @(posedge clk);
        layer_id = 3'd4;
        layer_start = 1'b1;
        @(posedge clk);
        layer_start = 1'b0;
        @(posedge layer_done);
        $display("[SIM] Layer 4 Finished!");

        err_gap = 0;
        for (i = 0; i < 32; i = i + 1) begin
            if (u_core.gap_mem[i] !== exp_gap[i]) begin
                if (err_gap < 5) $display("[CHECK GAP] mismatch at %0d: rtl=%0d exp=%0d", i, $signed(u_core.gap_mem[i]), exp_gap[i]);
                err_gap = err_gap + 1;
            end
        end
        $display("[CHECK GAP] Total Mismatches: %0d / 32", err_gap);

        // 6. Layer 5 (Dense Head 32->5)
        $display("[SIM] 6. Executing Layer 5 (Dense Head 32->5)...");
        @(posedge clk);
        dma_mode = 3'd4;
        dma_start = 1'b1;
        @(posedge clk);
        dma_start = 1'b0;
                @(posedge dma_done);
        $display("[DEBUG DMA] First 5 weights loaded in WeightBuf: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.weight_buf.mem[0]), $signed(u_core.weight_buf.mem[1]),
                 $signed(u_core.weight_buf.mem[2]), $signed(u_core.weight_buf.mem[3]),
                 $signed(u_core.weight_buf.mem[4]));
        $display("[DEBUG DMA] First 5 biases loaded in bias_mem: %0d, %0d, %0d, %0d, %0d",
                 $signed(u_core.bias_mem[0]), $signed(u_core.bias_mem[1]),
                 $signed(u_core.bias_mem[2]), $signed(u_core.bias_mem[3]),
                 $signed(u_core.bias_mem[4]));
        @(posedge clk);
        layer_id = 3'd5;
        layer_start = 1'b1;
        @(posedge clk);
        layer_start = 1'b0;
        @(posedge layer_done);
        $display("[SIM] Layer 5 Finished!");

        $display("[RESULT] Scheme B Simulated Logits:");
        $display("  L0 (NORM): %0d (hex: %02x)", out_l0, out_l0[7:0]);
        $display("  L1 (MI):   %0d (hex: %02x)", out_l1, out_l1[7:0]);
        $display("  L2 (STTC): %0d (hex: %02x)", out_l2, out_l2[7:0]);
        $display("  L3 (CD):   %0d (hex: %02x)", out_l3, out_l3[7:0]);
        $display("  L4 (HYP):  %0d (hex: %02x)", out_l4, out_l4[7:0]);

        if (err_p1 == 0 && err_p2 == 0 && err_r3 == 0 && err_gap == 0 &&
            out_l0 === exp_logits[0] && out_l1 === exp_logits[1] &&
            out_l2 === exp_logits[2] && out_l3 === exp_logits[3] &&
            out_l4 === exp_logits[4]) begin
            $display(">>> [PASS] Scheme B Stream Core is 100% Bit-Exact to Golden! <<<");
        end else begin
            $display(">>> [FAIL] Scheme B Output Mismatch Detected! <<<");
        end

        #100;
        $finish;
    end

endmodule