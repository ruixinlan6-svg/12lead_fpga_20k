`timescale 1ns/1ps

// Scheme B: TinyECGCNN Stream Core with Ping-Pong BRAMs
// Computes layer-by-layer forward inference using dynamically loaded layer weights.

module tiny_ecgcnn_stream_core (
    input  wire        clk,
    input  wire        rst_n,

    // Execution trigger
    input  wire        layer_start,
    input  wire [2:0]  layer_id, // 1: L1, 2: L2, 3: L3, 4: GAP, 5: Head
    output reg         layer_done,

    // Dynamic Layer Weight & Bias Write Interface (from DMA)
    input  wire        dma_w_en,
    input  wire [12:0] dma_w_addr,
    input  wire [7:0]  dma_w_data,
    input  wire        dma_b_en,
    input  wire [4:0]  dma_b_addr,
    input  wire [7:0]  dma_b_data,

    // Input waveform direct write to ActBuf_A
    input  wire        dma_in_en,
    input  wire [13:0] dma_in_addr,
    input  wire [7:0]  dma_in_data,

    // Final Logits Output (5 classes)
    output reg signed [7:0] out_l0,
    output reg signed [7:0] out_l1,
    output reg signed [7:0] out_l2,
    output reg signed [7:0] out_l3,
    output reg signed [7:0] out_l4
);

    localparam QSHIFT = 31;

    localparam signed [63:0] C1_PRODUCT_M = 64'sd1866162;
    localparam signed [63:0] C1_BIAS_M    = 64'sd96620514;
    localparam signed [63:0] R1_M         = 64'sd2673984300;

    localparam signed [63:0] C2_PRODUCT_M = 64'sd4606622;
    localparam signed [63:0] C2_BIAS_M    = 64'sd27912751;
    localparam signed [63:0] R2_M         = 64'sd2147483648;

    localparam signed [63:0] C3_PRODUCT_M = 64'sd2850107;
    localparam signed [63:0] C3_BIAS_M    = 64'sd5207031;
    localparam signed [63:0] R3_M         = 64'sd3101789594;

    localparam signed [63:0] GAP_M_EFF    = 64'sd32422936;
    localparam signed [63:0] H_PRODUCT_M  = 64'sd12529589;
    localparam signed [63:0] H_BIAS_M     = 64'sd37360384;

    function automatic signed [7:0] conv_quant;
        input signed [31:0] acc_in;
        input signed [7:0]  bias_in;
        input signed [63:0] product_mult;
        input signed [63:0] bias_mult;
        reg signed [63:0] term_prod;
        reg signed [63:0] term_bias;
        reg signed [63:0] numerator;
        reg signed [63:0] rounded;
        reg signed [63:0] scaled;
        begin
            term_prod = $signed(acc_in) * $signed(product_mult);
            term_bias = $signed(bias_in) * $signed(bias_mult);
            numerator = term_prod + term_bias;
            if (numerator < 0) begin
                rounded = (-numerator) + (64'sd1 <<< (QSHIFT - 1));
                scaled = -(rounded >>> QSHIFT);
            end else begin
                rounded = numerator + (64'sd1 <<< (QSHIFT - 1));
                scaled = rounded >>> QSHIFT;
            end
            if (scaled > 127) conv_quant = 8'sd127;
            else if (scaled < -128) conv_quant = -8'sd128;
            else conv_quant = scaled[7:0];
        end
    endfunction

    function automatic signed [7:0] rescale8;
        input signed [7:0]  value;
        input signed [63:0] multiplier;
        reg signed [63:0] numerator;
        reg signed [63:0] rounded;
        reg signed [63:0] scaled;
        begin
            numerator = $signed(value) * $signed(multiplier);
            if (numerator < 0) begin
                rounded = (-numerator) + (64'sd1 <<< (QSHIFT - 1));
                scaled = -(rounded >>> QSHIFT);
            end else begin
                rounded = numerator + (64'sd1 <<< (QSHIFT - 1));
                scaled = rounded >>> QSHIFT;
            end
            if (scaled > 127) rescale8 = 8'sd127;
            else if (scaled < -128) rescale8 = -8'sd128;
            else rescale8 = scaled[7:0];
        end
    endfunction

    function automatic signed [7:0] gap_quant;
        input signed [31:0] sum_in;
        reg signed [63:0] numerator;
        reg signed [63:0] rounded;
        reg signed [63:0] scaled;
        begin
            numerator = $signed(sum_in) * GAP_M_EFF;
            if (numerator < 0) begin
                rounded = (-numerator) + (64'sd1 <<< (QSHIFT - 1));
                scaled = -(rounded >>> QSHIFT);
            end else begin
                rounded = numerator + (64'sd1 <<< (QSHIFT - 1));
                scaled = rounded >>> QSHIFT;
            end
            if (scaled > 127) gap_quant = 8'sd127;
            else if (scaled < -128) gap_quant = -8'sd128;
            else gap_quant = scaled[7:0];
        end
    endfunction

    // Ping-Pong Activation Buffers (16 KB each)
    reg  [13:0] act_a_raddr;
    reg  [13:0] act_a_waddr;
    reg signed [7:0] act_a_din;
    wire signed [7:0] act_a_dout;
    reg         act_a_we;

    wire        act_a_wr_en   = dma_in_en ? 1'b1 : act_a_we;
    wire [13:0] act_a_wr_addr = dma_in_en ? dma_in_addr : act_a_waddr;
    wire signed [7:0] act_a_wr_data = dma_in_en ? dma_in_data : act_a_din;

    ecg_sync_dp_ram #(.ADDR_WIDTH(14), .DEPTH(16384)) act_buf_a (
        .clk(clk),
        .wr_addr(act_a_wr_addr),
        .wr_en(act_a_wr_en),
        .wr_data(act_a_wr_data),
        .rd_en(1'b1),
        .rd_addr(act_a_raddr),
        .rd_data(act_a_dout)
    );

    reg  [13:0] act_b_raddr;
    reg  [13:0] act_b_waddr;
    reg signed [7:0] act_b_din;
    wire signed [7:0] act_b_dout;
    reg         act_b_we;

    ecg_sync_dp_ram #(.ADDR_WIDTH(14), .DEPTH(16384)) act_buf_b (
        .clk(clk),
        .wr_addr(act_b_waddr),
        .wr_en(act_b_we),
        .wr_data(act_b_din),
        .rd_en(1'b1),
        .rd_addr(act_b_raddr),
        .rd_data(act_b_dout)
    );

    // Dynamic Layer Weight Buffer (8 KB)
    reg  [12:0] w_raddr;
    wire signed [7:0] w_dout;

    wire        w_wr_en   = dma_w_en ? 1'b1 : 1'b0;
    wire [12:0] w_wr_addr = dma_w_addr;
    wire signed [7:0] w_wr_data = dma_w_data;

    ecg_sync_dp_ram #(.ADDR_WIDTH(13), .DEPTH(8192)) weight_buf (
        .clk(clk),
        .wr_addr(w_wr_addr),
        .wr_en(w_wr_en),
        .wr_data(w_wr_data),
        .rd_en(1'b1),
        .rd_addr(w_raddr),
        .rd_data(w_dout)
    );

    // Bias Buffer (32 bytes)
    reg signed [7:0] bias_mem [0:31];
    always @(posedge clk) begin
        if (dma_b_en) bias_mem[dma_b_addr] <= dma_b_data;
    end

    // Global Average Pooling Result Buffer (32 bytes)
    reg signed [7:0] gap_mem [0:31];

    // Execution FSM States
    localparam [4:0]
        ST_IDLE             = 5'd0,
        ST_L1_READ_PREPARE  = 5'd1,
        ST_L1_EXEC          = 5'd2,
        ST_L1_WRITE         = 5'd3,
        ST_L2_READ_PREPARE  = 5'd4,
        ST_L2_EXEC          = 5'd5,
        ST_L2_WRITE         = 5'd6,
        ST_L3_READ_PREPARE  = 5'd7,
        ST_L3_EXEC          = 5'd8,
        ST_L3_WRITE         = 5'd9,
        ST_GAP_READ_PREPARE = 5'd10,
        ST_GAP_EXEC         = 5'd11,
        ST_GAP_WRITE        = 5'd12,
        ST_H_READ_PREPARE   = 5'd13,
        ST_H_EXEC           = 5'd14,
        ST_H_WRITE          = 5'd15,
        ST_DONE             = 5'd16;

    reg [4:0] state;

    // Loop counters
    reg [9:0] t_idx;
    reg [5:0] oc_idx;
    reg [4:0] ic_idx;
    reg [2:0] k_idx;
    reg [1:0] pool_sub;
    reg signed [7:0] pool_max;

    // Accumulators
    reg signed [31:0] acc;

    // Pre-calculate address offsets (Combinational)
    wire signed [11:0] l1_in_t = $signed({2'b00, t_idx}) + $signed({8'd0, k_idx}) - 12'sd3;
    wire l1_valid_pad = (l1_in_t >= 0 && l1_in_t < 1000);
    wire [13:0] l1_in_addr = l1_valid_pad ? (ic_idx * 14'd1000 + l1_in_t[9:0]) : 14'd0;
    wire [12:0] l1_w_addr  = oc_idx * 13'd84 + ic_idx * 13'd7 + k_idx;

    wire signed [11:0] l2_in_t = $signed({2'b00, t_idx}) + $signed({8'd0, k_idx}) - 12'sd3;
    wire l2_valid_pad = (l2_in_t >= 0 && l2_in_t < 500);
    wire [13:0] l2_in_addr = l2_valid_pad ? (ic_idx * 14'd500 + l2_in_t[8:0]) : 14'd0;
    wire [12:0] l2_w_addr  = oc_idx * 13'd112 + ic_idx * 13'd7 + k_idx;

    wire signed [11:0] l3_in_t = $signed({2'b00, t_idx}) + $signed({8'd0, k_idx}) - 12'sd2;
    wire l3_valid_pad = (l3_in_t >= 0 && l3_in_t < 250);
    wire [13:0] l3_in_addr = l3_valid_pad ? (ic_idx * 14'd250 + l3_in_t[7:0]) : 14'd0;
    wire [12:0] l3_w_addr  = oc_idx * 13'd160 + ic_idx * 13'd5 + k_idx;

    // Combinational Read Address Routing directly to BRAM ports
    always @* begin
        act_a_raddr = 14'd0;
        act_b_raddr = 14'd0;
        w_raddr     = 13'd0;
        case (state)
            ST_L1_READ_PREPARE, ST_L1_EXEC: begin
                act_a_raddr = l1_in_addr;
                w_raddr     = l1_w_addr;
            end
            ST_L2_READ_PREPARE, ST_L2_EXEC: begin
                act_b_raddr = l2_in_addr;
                w_raddr     = l2_w_addr;
            end
            ST_L3_READ_PREPARE, ST_L3_EXEC: begin
                act_a_raddr = l3_in_addr;
                w_raddr     = l3_w_addr;
            end
            ST_GAP_READ_PREPARE, ST_GAP_EXEC: begin
                act_b_raddr = oc_idx * 14'd250 + t_idx;
            end
            ST_H_READ_PREPARE, ST_H_EXEC: begin
                w_raddr     = oc_idx * 13'd32 + ic_idx;
            end
            default: begin end
        endcase
    end

    reg signed [7:0] conv_val_tmp;
    reg signed [7:0] relu_val_tmp;
    reg signed [7:0] final_pool_tmp;
    reg signed [7:0] logit_val_tmp;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_IDLE;
            layer_done <= 1'b0;
            act_a_we <= 1'b0;
            act_b_we <= 1'b0;
            t_idx    <= 0;
            oc_idx   <= 0;
            ic_idx   <= 0;
            k_idx    <= 0;
            pool_sub <= 0;
            pool_max <= -8'sd128;
            acc      <= 0;
            out_l0 <= 0; out_l1 <= 0; out_l2 <= 0; out_l3 <= 0; out_l4 <= 0;
        end else begin
            layer_done <= 1'b0;
            act_a_we   <= 1'b0;
            act_b_we   <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (layer_start) begin
                        t_idx    <= 0;
                        oc_idx   <= 0;
                        ic_idx   <= 0;
                        k_idx    <= 0;
                        pool_sub <= 0;
                        pool_max <= -8'sd128;
                        acc      <= 0;
                        case (layer_id)
                            3'd1: state <= ST_L1_READ_PREPARE;
                            3'd2: state <= ST_L2_READ_PREPARE;
                            3'd3: state <= ST_L3_READ_PREPARE;
                            3'd4: state <= ST_GAP_READ_PREPARE;
                            3'd5: state <= ST_H_READ_PREPARE;
                            default: state <= ST_IDLE;
                        endcase
                    end
                end

                // ==========================================
                // LAYER 1: Conv1D (12->16, K=7) + ReLU + Pool
                // Inputs: ActBuf_A, Outputs: ActBuf_B
                // ==========================================
                ST_L1_READ_PREPARE: begin
                    state <= ST_L1_EXEC;
                end

                ST_L1_EXEC: begin
                    if (l1_valid_pad) begin
                        acc <= acc + ($signed(act_a_dout) * $signed(w_dout));
                    end
                    if (k_idx < 6) begin
                        k_idx <= k_idx + 1;
                        state <= ST_L1_READ_PREPARE;
                    end else if (ic_idx < 11) begin
                        k_idx <= 0;
                        ic_idx <= ic_idx + 1;
                        state <= ST_L1_READ_PREPARE;
                    end else begin
                        state <= ST_L1_WRITE;
                    end
                end

                ST_L1_WRITE: begin
                    conv_val_tmp = conv_quant(acc, $signed(bias_mem[oc_idx]), C1_PRODUCT_M, C1_BIAS_M);
                    relu_val_tmp = (conv_val_tmp > 0) ? rescale8(conv_val_tmp, R1_M) : 8'sd0;

                    if (pool_sub == 0) begin
                        pool_max <= relu_val_tmp;
                        pool_sub <= 1;
                        t_idx    <= t_idx + 1;
                        ic_idx   <= 0;
                        k_idx    <= 0;
                        acc      <= 0;
                        state    <= ST_L1_READ_PREPARE;
                    end else begin
                        final_pool_tmp = (relu_val_tmp > pool_max) ? relu_val_tmp : pool_max;
                        act_b_waddr <= oc_idx * 14'd500 + (t_idx >> 1);
                        act_b_din   <= final_pool_tmp;
                        act_b_we    <= 1'b1;
                        pool_sub    <= 0;
                        pool_max    <= -8'sd128;

                        if (t_idx < 999) begin
                            t_idx  <= t_idx + 1;
                            ic_idx <= 0;
                            k_idx  <= 0;
                            acc    <= 0;
                            state  <= ST_L1_READ_PREPARE;
                        end else if (oc_idx < 15) begin
                            oc_idx <= oc_idx + 1;
                            t_idx  <= 0;
                            ic_idx <= 0;
                            k_idx  <= 0;
                            acc    <= 0;
                            state  <= ST_L1_READ_PREPARE;
                        end else begin
                            state <= ST_DONE;
                        end
                    end
                end

                // ==========================================
                // LAYER 2: Conv1D (16->32, K=7) + ReLU + Pool
                // Inputs: ActBuf_B, Outputs: ActBuf_A
                // ==========================================
                ST_L2_READ_PREPARE: begin
                    state <= ST_L2_EXEC;
                end

                ST_L2_EXEC: begin
                    if (l2_valid_pad) begin
                        acc <= acc + ($signed(act_b_dout) * $signed(w_dout));
                    end
                    if (k_idx < 6) begin
                        k_idx <= k_idx + 1;
                        state <= ST_L2_READ_PREPARE;
                    end else if (ic_idx < 15) begin
                        k_idx <= 0;
                        ic_idx <= ic_idx + 1;
                        state <= ST_L2_READ_PREPARE;
                    end else begin
                        state <= ST_L2_WRITE;
                    end
                end

                ST_L2_WRITE: begin
                    conv_val_tmp = conv_quant(acc, $signed(bias_mem[oc_idx]), C2_PRODUCT_M, C2_BIAS_M);
                    relu_val_tmp = (conv_val_tmp > 0) ? rescale8(conv_val_tmp, R2_M) : 8'sd0;

                    if (pool_sub == 0) begin
                        pool_max <= relu_val_tmp;
                        pool_sub <= 1;
                        t_idx    <= t_idx + 1;
                        ic_idx   <= 0;
                        k_idx    <= 0;
                        acc      <= 0;
                        state    <= ST_L2_READ_PREPARE;
                    end else begin
                        final_pool_tmp = (relu_val_tmp > pool_max) ? relu_val_tmp : pool_max;
                        act_a_waddr <= oc_idx * 14'd250 + (t_idx >> 1);
                        act_a_din   <= final_pool_tmp;
                        act_a_we    <= 1'b1;
                        pool_sub    <= 0;
                        pool_max    <= -8'sd128;

                        if (t_idx < 499) begin
                            t_idx  <= t_idx + 1;
                            ic_idx <= 0;
                            k_idx  <= 0;
                            acc    <= 0;
                            state  <= ST_L2_READ_PREPARE;
                        end else if (oc_idx < 31) begin
                            oc_idx <= oc_idx + 1;
                            t_idx  <= 0;
                            ic_idx <= 0;
                            k_idx  <= 0;
                            acc    <= 0;
                            state  <= ST_L2_READ_PREPARE;
                        end else begin
                            state <= ST_DONE;
                        end
                    end
                end

                // ==========================================
                // LAYER 3: Conv1D (32->32, K=5) + ReLU
                // Inputs: ActBuf_A, Outputs: ActBuf_B
                // ==========================================
                ST_L3_READ_PREPARE: begin
                    state <= ST_L3_EXEC;
                end

                ST_L3_EXEC: begin
                    if (l3_valid_pad) begin
                        acc <= acc + ($signed(act_a_dout) * $signed(w_dout));
                    end
                    if (k_idx < 4) begin
                        k_idx <= k_idx + 1;
                        state <= ST_L3_READ_PREPARE;
                    end else if (ic_idx < 31) begin
                        k_idx <= 0;
                        ic_idx <= ic_idx + 1;
                        state <= ST_L3_READ_PREPARE;
                    end else begin
                        state <= ST_L3_WRITE;
                    end
                end

                ST_L3_WRITE: begin
                    conv_val_tmp = conv_quant(acc, $signed(bias_mem[oc_idx]), C3_PRODUCT_M, C3_BIAS_M);
                    relu_val_tmp = (conv_val_tmp > 0) ? rescale8(conv_val_tmp, R3_M) : 8'sd0;

                    act_b_waddr <= oc_idx * 14'd250 + t_idx;
                    act_b_din   <= relu_val_tmp;
                    act_b_we    <= 1'b1;

                    if (t_idx < 249) begin
                        t_idx  <= t_idx + 1;
                        ic_idx <= 0;
                        k_idx  <= 0;
                        acc    <= 0;
                        state  <= ST_L3_READ_PREPARE;
                    end else if (oc_idx < 31) begin
                        oc_idx <= oc_idx + 1;
                        t_idx  <= 0;
                        ic_idx <= 0;
                        k_idx  <= 0;
                        acc    <= 0;
                        state  <= ST_L3_READ_PREPARE;
                    end else begin
                        state <= ST_DONE;
                    end
                end

                // ==========================================
                // LAYER 4: Global Average Pooling (32 ch x 250)
                // Inputs: ActBuf_B, Outputs: gap_mem
                // ==========================================
                ST_GAP_READ_PREPARE: begin
                    state <= ST_GAP_EXEC;
                end

                ST_GAP_EXEC: begin
                    acc <= acc + $signed(act_b_dout);
                    if (t_idx < 249) begin
                        t_idx <= t_idx + 1;
                        state <= ST_GAP_READ_PREPARE;
                    end else begin
                        state <= ST_GAP_WRITE;
                    end
                end

                ST_GAP_WRITE: begin
                    gap_mem[oc_idx] <= gap_quant(acc);
                    if (oc_idx < 31) begin
                        oc_idx <= oc_idx + 1;
                        t_idx  <= 0;
                        acc    <= 0;
                        state  <= ST_GAP_READ_PREPARE;
                    end else begin
                        state <= ST_DONE;
                    end
                end

                // ==========================================
                // LAYER 5: Dense Head (32 in -> 5 logits)
                // Inputs: gap_mem, Outputs: out_l0..l4
                // ==========================================
                ST_H_READ_PREPARE: begin
                    state <= ST_H_EXEC;
                end

                ST_H_EXEC: begin
                    acc <= acc + ($signed(gap_mem[ic_idx]) * $signed(w_dout));
                    if (ic_idx < 31) begin
                        ic_idx <= ic_idx + 1;
                        state  <= ST_H_READ_PREPARE;
                    end else begin
                        state <= ST_H_WRITE;
                    end
                end

                ST_H_WRITE: begin
                    logit_val_tmp = conv_quant(acc, $signed(bias_mem[oc_idx]), H_PRODUCT_M, H_BIAS_M);
                    case (oc_idx)
                        6'd0: out_l0 <= logit_val_tmp;
                        6'd1: out_l1 <= logit_val_tmp;
                        6'd2: out_l2 <= logit_val_tmp;
                        6'd3: out_l3 <= logit_val_tmp;
                        6'd4: out_l4 <= logit_val_tmp;
                    endcase

                    if (oc_idx < 4) begin
                        oc_idx <= oc_idx + 1;
                        ic_idx <= 0;
                        acc    <= 0;
                        state  <= ST_H_READ_PREPARE;
                    end else begin
                        state <= ST_DONE;
                    end
                end

                ST_DONE: begin
                    layer_done <= 1'b1;
                    state      <= ST_IDLE;
                end
            endcase
        end
    end

endmodule