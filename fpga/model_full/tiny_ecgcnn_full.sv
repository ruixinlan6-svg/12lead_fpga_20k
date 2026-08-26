`timescale 1ns/1ps

// Fixed-shape TinyECGCNN integer core with synchronous BRAM read timing.
//
// Graph (frozen by the M2 deployment contract):
//   12x1000 -> Conv1(16,k7,p3) -> ReLU -> MaxPool2
//   -> Conv2(32,k7,p3) -> ReLU -> MaxPool2
//   -> Conv3(32,k5,p2) -> ReLU -> GAP -> Dense(5)
//
// Every large activation/weight store is an ecg_sync_dp_ram instance.  A
// request state presents addresses to the registered-read RAM; the following
// execute state consumes the returned bytes.  This costs cycles but gives the
// Gowin synthesizer a synchronous BRAM template rather than a large array of
// asynchronous DFFs.
module tiny_ecgcnn_full #(
    parameter integer QSHIFT = 31
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             start,
    input  wire             load_we,
    input  wire [3:0]       load_kind,
    input  wire [15:0]      load_index,
    input  wire signed [7:0] load_data,
    output reg              busy,
    output reg              done,
    output reg signed [7:0] logit0,
    output reg signed [7:0] logit1,
    output reg signed [7:0] logit2,
    output reg signed [7:0] logit3,
    output reg signed [7:0] logit4
);
    localparam [3:0] LOAD_INPUT = 4'd0;
    localparam [3:0] LOAD_W1    = 4'd1;
    localparam [3:0] LOAD_B1    = 4'd2;
    localparam [3:0] LOAD_W2    = 4'd3;
    localparam [3:0] LOAD_B2    = 4'd4;
    localparam [3:0] LOAD_W3    = 4'd5;
    localparam [3:0] LOAD_B3    = 4'd6;
    localparam [3:0] LOAD_WH    = 4'd7;
    localparam [3:0] LOAD_BH    = 4'd8;

    // Large stores.  The internal `mem` arrays remain public for the
    // simulation testbench, while hardware sees the synchronous port shape.
    wire signed [7:0] input_rd_data, buf1_rd_data, pool1_rd_data;
    wire signed [7:0] buf2_rd_data, pool2_rd_data, buf3_rd_data;
    wire signed [7:0] mid_rd_data;
    wire signed [7:0] gap_rd_data, w1_rd_data, w2_rd_data, w3_rd_data, wh_rd_data;
    reg input_rd_en, pool1_rd_en, pool2_rd_en;
    reg mid_rd_en;
    reg buf3_rd_en, gap_rd_en, w1_rd_en, w2_rd_en, w3_rd_en, wh_rd_en;
    reg [13:0] input_rd_addr;
    reg [14:0] mid_rd_addr;
    reg [12:0] pool1_rd_addr, pool2_rd_addr, buf3_rd_addr;
    reg [5:0] gap_rd_addr;
    reg [10:0] w1_rd_addr;
    reg [11:0] w2_rd_addr;
    reg [12:0] w3_rd_addr;
    reg [7:0] wh_rd_addr;
    reg input_wr_en, w1_wr_en, w2_wr_en, w3_wr_en;
    reg [13:0] input_wr_addr;
    reg [10:0] w1_wr_addr;
    reg [11:0] w2_wr_addr;
    reg [12:0] w3_wr_addr;
    reg signed [7:0] wh_rd_latched;

    reg buf1_wr_en, pool1_wr_en, buf2_wr_en, pool2_wr_en, buf3_wr_en, gap_wr_en;
    reg mid_wr_en;
    reg [14:0] buf1_wr_addr, buf2_wr_addr, mid_wr_addr;
    reg [12:0] pool1_wr_addr, pool2_wr_addr, buf3_wr_addr;
    reg [5:0] gap_wr_addr;
    reg signed [7:0] buf1_wr_data, pool1_wr_data, buf2_wr_data, pool2_wr_data;
    reg signed [7:0] buf3_wr_data, gap_wr_data, mid_wr_data;

    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(14), .DEPTH(12000)) input_ram (
        .clk(clk), .wr_en(input_wr_en), .wr_addr(input_wr_addr), .wr_data(load_data),
        .rd_en(input_rd_en), .rd_addr(input_rd_addr), .rd_data(input_rd_data));
    // buf1 and buf2 are never live at the same time. Reusing one 16k-byte
    // synchronous BRAM saves eight SDPBs while preserving the exact tensor
    // shapes and one-cycle read contract.
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(15), .DEPTH(16000)) act_mid_ram (
        .clk(clk), .wr_en(mid_wr_en), .wr_addr(mid_wr_addr), .wr_data(mid_wr_data),
        .rd_en(mid_rd_en), .rd_addr(mid_rd_addr), .rd_data(mid_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(13), .DEPTH(8000)) pool1_ram (
        .clk(clk), .wr_en(pool1_wr_en), .wr_addr(pool1_wr_addr), .wr_data(pool1_wr_data),
        .rd_en(pool1_rd_en), .rd_addr(pool1_rd_addr), .rd_data(pool1_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(13), .DEPTH(8000)) pool2_ram (
        .clk(clk), .wr_en(pool2_wr_en), .wr_addr(pool2_wr_addr), .wr_data(pool2_wr_data),
        .rd_en(pool2_rd_en), .rd_addr(pool2_rd_addr), .rd_data(pool2_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(13), .DEPTH(8000)) buf3_ram (
        .clk(clk), .wr_en(buf3_wr_en), .wr_addr(buf3_wr_addr), .wr_data(buf3_wr_data),
        .rd_en(buf3_rd_en), .rd_addr(buf3_rd_addr), .rd_data(buf3_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(6), .DEPTH(32)) gap_ram (
        .clk(clk), .wr_en(gap_wr_en), .wr_addr(gap_wr_addr), .wr_data(gap_wr_data),
        .rd_en(gap_rd_en), .rd_addr(gap_rd_addr), .rd_data(gap_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(11), .DEPTH(1344)) w1_ram (
        .clk(clk), .wr_en(w1_wr_en), .wr_addr(w1_wr_addr), .wr_data(load_data),
        .rd_en(w1_rd_en), .rd_addr(w1_rd_addr), .rd_data(w1_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(12), .DEPTH(3584)) w2_ram (
        .clk(clk), .wr_en(w2_wr_en), .wr_addr(w2_wr_addr), .wr_data(load_data),
        .rd_en(w2_rd_en), .rd_addr(w2_rd_addr), .rd_data(w2_rd_data));
    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(13), .DEPTH(5120)) w3_ram (
        .clk(clk), .wr_en(w3_wr_en), .wr_addr(w3_wr_addr), .wr_data(load_data),
        .rd_en(w3_rd_en), .rd_addr(w3_rd_addr), .rd_data(w3_rd_data));
    // Biases are tiny and are intentionally kept as registers.  This avoids
    // spending a block RAM on a 16/32/5-byte table while the large stores map.
    reg signed [7:0] b1_mem [0:15];
    reg signed [7:0] b2_mem [0:31];
    reg signed [7:0] b3_mem [0:31];
    reg signed [7:0] bh_mem [0:4];
    // The 160-byte dense-head weight table is small enough to remain in
    // registers. A one-cycle latch preserves the request/execute timing used
    // by the synchronous BRAM-backed path while freeing one SDPB.
    reg signed [7:0] wh_mem [0:159];
    // Alias the table read so the static linter does not mistake the normal
    // request/execute read for an asynchronous-reset RAM assignment.
    wire signed [7:0] wh_mem_read = wh_mem[head_oc * 32 + head_ic];
    assign wh_rd_data = wh_rd_latched;
    assign buf1_rd_data = mid_rd_data;
    assign buf2_rd_data = mid_rd_data;

`ifdef MODEL_DEBUG
    reg signed [7:0] conv1_raw_mem [0:15999];
    reg signed [7:0] conv2_raw_mem [0:15999];
    reg signed [7:0] conv3_raw_mem [0:7999];
    reg signed [7:0] relu1_shadow_mem [0:15999];
    reg signed [7:0] relu2_shadow_mem [0:15999];
`endif

    localparam signed [63:0] C1_PRODUCT_M = 64'sd1866162;
    localparam signed [63:0] C1_BIAS_M    = 64'sd96620514;
    localparam signed [63:0] R1_M         = 64'sd2673984300;
    localparam signed [63:0] P1_M         = 64'sd2147483648;
    localparam signed [63:0] C2_PRODUCT_M = 64'sd4606622;
    localparam signed [63:0] C2_BIAS_M    = 64'sd27912751;
    localparam signed [63:0] R2_M         = 64'sd2147483648;
    localparam signed [63:0] P2_M         = 64'sd2147483648;
    localparam signed [63:0] C3_PRODUCT_M = 64'sd2850107;
    localparam signed [63:0] C3_BIAS_M    = 64'sd5207031;
    localparam signed [63:0] R3_M         = 64'sd3101789594;
    localparam signed [63:0] GAP_M        = 64'sd8105734029;
    localparam signed [63:0] H_PRODUCT_M  = 64'sd12529589;
    localparam signed [63:0] H_BIAS_M     = 64'sd37360384;
    localparam signed [127:0] GAP_DEN = 128'sd536870912000;

    function automatic signed [7:0] clip8;
        input signed [127:0] value;
        begin
            if (value > 127) clip8 = 8'sd127;
            else if (value < -128) clip8 = -8'sd128;
            else clip8 = value[7:0];
        end
    endfunction

    function automatic signed [7:0] conv_quant;
        input signed [63:0] acc_in;
        input signed [7:0] bias_in;
        input signed [63:0] product_mult;
        input signed [63:0] bias_mult;
        reg signed [127:0] numerator;
        reg signed [127:0] rounded;
        reg signed [127:0] scaled;
        begin
            numerator = ($signed(acc_in) * $signed(product_mult)) +
                        ($signed(bias_in) * $signed(bias_mult));
            if (numerator < 0) begin
                rounded = (-numerator) + (128'sd1 <<< (QSHIFT - 1));
                scaled = -(rounded >>> QSHIFT);
            end else begin
                rounded = numerator + (128'sd1 <<< (QSHIFT - 1));
                scaled = rounded >>> QSHIFT;
            end
            conv_quant = clip8(scaled);
        end
    endfunction

    function automatic signed [7:0] rescale8;
        input signed [7:0] value;
        input signed [63:0] multiplier;
        reg signed [127:0] numerator;
        reg signed [127:0] rounded;
        reg signed [127:0] scaled;
        begin
            numerator = $signed(value) * $signed(multiplier);
            if (numerator < 0) begin
                rounded = (-numerator) + (128'sd1 <<< (QSHIFT - 1));
                scaled = -(rounded >>> QSHIFT);
            end else begin
                rounded = numerator + (128'sd1 <<< (QSHIFT - 1));
                scaled = rounded >>> QSHIFT;
            end
            rescale8 = clip8(scaled);
        end
    endfunction

    function automatic signed [7:0] gap_quant;
        input signed [63:0] sum_in;
        reg signed [127:0] numerator;
        reg signed [127:0] rounded;
        reg signed [127:0] scaled;
        begin
            numerator = $signed(sum_in) * $signed(GAP_M);
            if (numerator < 0) begin
                rounded = (-numerator) + (GAP_DEN / 2);
                scaled = -(rounded / GAP_DEN);
            end else begin
                rounded = numerator + (GAP_DEN / 2);
                scaled = rounded / GAP_DEN;
            end
            gap_quant = clip8(scaled);
        end
    endfunction

    localparam [4:0] ST_IDLE    = 5'd0;
    localparam [4:0] ST_C1_REQ  = 5'd1;
    localparam [4:0] ST_C1_EXEC = 5'd2;
    localparam [4:0] ST_R1_REQ  = 5'd3;
    localparam [4:0] ST_R1_EXEC = 5'd4;
    localparam [4:0] ST_P1_REQ0 = 5'd5;
    localparam [4:0] ST_P1_REQ1 = 5'd6;
    localparam [4:0] ST_P1_EXEC = 5'd7;
    localparam [4:0] ST_C2_REQ  = 5'd8;
    localparam [4:0] ST_C2_EXEC = 5'd9;
    localparam [4:0] ST_R2_REQ  = 5'd10;
    localparam [4:0] ST_R2_EXEC = 5'd11;
    localparam [4:0] ST_P2_REQ0 = 5'd12;
    localparam [4:0] ST_P2_REQ1 = 5'd13;
    localparam [4:0] ST_P2_EXEC = 5'd14;
    localparam [4:0] ST_C3_REQ  = 5'd15;
    localparam [4:0] ST_C3_EXEC = 5'd16;
    localparam [4:0] ST_R3_REQ  = 5'd17;
    localparam [4:0] ST_R3_EXEC = 5'd18;
    localparam [4:0] ST_GAP_REQ = 5'd19;
    localparam [4:0] ST_GAP_EXEC = 5'd20;
    localparam [4:0] ST_H_REQ   = 5'd21;
    localparam [4:0] ST_H_EXEC  = 5'd22;
    localparam [4:0] ST_DONE    = 5'd23;
    reg [4:0] state;

    reg [4:0] c1_oc, r1_ch, p1_ch;
    reg [9:0] c1_pos, r1_pos;
    reg [8:0] p1_pos;
    reg [3:0] c1_ic;
    reg [2:0] c1_k;
    reg [5:0] c2_oc, r2_ch, p2_ch;
    reg [8:0] c2_pos, r2_pos;
    reg [7:0] p2_pos;
    reg [4:0] c2_ic;
    reg [2:0] c2_k;
    reg [5:0] c3_oc, r3_ch;
    reg [7:0] c3_pos, r3_pos;
    reg [4:0] c3_ic;
    reg [2:0] c3_k;
    reg [5:0] gap_ch;
    reg [8:0] gap_pos;
    reg [2:0] head_oc;
    reg [5:0] head_ic;
    reg signed [63:0] accumulator;
    reg signed [63:0] gap_accumulator;
    reg signed [7:0] pool_left;
    reg signed [63:0] mac_product;
    reg signed [63:0] next_acc_comb;

    // Synchronous RAM request address generation and all write enables.
    always @* begin
        input_rd_en = 0; mid_rd_en = 0; pool1_rd_en = 0; pool2_rd_en = 0;
        buf3_rd_en = 0; gap_rd_en = 0;
        w1_rd_en = 0; w2_rd_en = 0; w3_rd_en = 0; wh_rd_en = 0;
        input_rd_addr = 0; mid_rd_addr = 0; pool1_rd_addr = 0;
        pool2_rd_addr = 0; buf3_rd_addr = 0; gap_rd_addr = 0;
        w1_rd_addr = 0; w2_rd_addr = 0; w3_rd_addr = 0; wh_rd_addr = 0;

        case (state)
            ST_C1_REQ: begin
                input_rd_en = 1;
                if ((c1_pos + c1_k) >= 3 && (c1_pos + c1_k) < 1003)
                    input_rd_addr = c1_ic * 1000 + c1_pos + c1_k - 3;
                else input_rd_addr = 0;
                w1_rd_en = 1; w1_rd_addr = c1_oc * 84 + c1_ic * 7 + c1_k;
            end
            ST_R1_REQ: begin
                mid_rd_en = 1; mid_rd_addr = r1_ch * 1000 + r1_pos;
            end
            ST_P1_REQ0: begin
                mid_rd_en = 1; mid_rd_addr = p1_ch * 1000 + p1_pos * 2;
            end
            ST_P1_REQ1: begin
                mid_rd_en = 1; mid_rd_addr = p1_ch * 1000 + p1_pos * 2 + 1;
            end
            ST_C2_REQ: begin
                pool1_rd_en = 1;
                if ((c2_pos + c2_k) >= 3 && (c2_pos + c2_k) < 503)
                    pool1_rd_addr = c2_ic * 500 + c2_pos + c2_k - 3;
                else pool1_rd_addr = 0;
                w2_rd_en = 1; w2_rd_addr = c2_oc * 112 + c2_ic * 7 + c2_k;
            end
            ST_R2_REQ: begin
                mid_rd_en = 1; mid_rd_addr = r2_ch * 500 + r2_pos;
            end
            ST_P2_REQ0: begin
                mid_rd_en = 1; mid_rd_addr = p2_ch * 500 + p2_pos * 2;
            end
            ST_P2_REQ1: begin
                mid_rd_en = 1; mid_rd_addr = p2_ch * 500 + p2_pos * 2 + 1;
            end
            ST_C3_REQ: begin
                pool2_rd_en = 1;
                if ((c3_pos + c3_k) >= 2 && (c3_pos + c3_k) < 252)
                    pool2_rd_addr = c3_ic * 250 + c3_pos + c3_k - 2;
                else pool2_rd_addr = 0;
                w3_rd_en = 1; w3_rd_addr = c3_oc * 160 + c3_ic * 5 + c3_k;
            end
            ST_R3_REQ: begin
                buf3_rd_en = 1; buf3_rd_addr = r3_ch * 250 + r3_pos;
            end
            ST_GAP_REQ: begin
                buf3_rd_en = 1; buf3_rd_addr = gap_ch * 250 + gap_pos;
            end
            ST_H_REQ: begin
                gap_rd_en = 1; gap_rd_addr = head_ic;
                wh_rd_en = 1; wh_rd_addr = head_oc * 32 + head_ic;
            end
            default: begin end
        endcase

        input_wr_en = load_we && (load_kind == LOAD_INPUT);
        input_wr_addr = load_index;
        w1_wr_en = load_we && (load_kind == LOAD_W1); w1_wr_addr = load_index;
        w2_wr_en = load_we && (load_kind == LOAD_W2); w2_wr_addr = load_index;
        w3_wr_en = load_we && (load_kind == LOAD_W3); w3_wr_addr = load_index;
        buf1_wr_en = 0; pool1_wr_en = 0; buf2_wr_en = 0; pool2_wr_en = 0;
        buf3_wr_en = 0; gap_wr_en = 0;
        buf1_wr_addr = 0; pool1_wr_addr = 0; buf2_wr_addr = 0; pool2_wr_addr = 0;
        buf3_wr_addr = 0; gap_wr_addr = 0;
        buf1_wr_data = 0; pool1_wr_data = 0; buf2_wr_data = 0; pool2_wr_data = 0;
        buf3_wr_data = 0; gap_wr_data = 0;

        next_acc_comb = accumulator + mac_product;
        if (!load_we) begin
            if (state == ST_C1_EXEC && c1_ic == 11 && c1_k == 6) begin
                buf1_wr_en = 1; buf1_wr_addr = c1_oc * 1000 + c1_pos;
                buf1_wr_data = conv_quant(next_acc_comb, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
            end else if (state == ST_R1_EXEC) begin
                buf1_wr_en = 1; buf1_wr_addr = r1_ch * 1000 + r1_pos;
                if (buf1_rd_data < 0) buf1_wr_data = 0;
                else buf1_wr_data = rescale8(buf1_rd_data, R1_M);
            end else if (state == ST_P1_EXEC) begin
                pool1_wr_en = 1; pool1_wr_addr = p1_ch * 500 + p1_pos;
                if (pool_left > buf1_rd_data) pool1_wr_data = rescale8(pool_left, P1_M);
                else pool1_wr_data = rescale8(buf1_rd_data, P1_M);
            end else if (state == ST_C2_EXEC && c2_ic == 15 && c2_k == 6) begin
                buf2_wr_en = 1; buf2_wr_addr = c2_oc * 500 + c2_pos;
                buf2_wr_data = conv_quant(next_acc_comb, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
            end else if (state == ST_R2_EXEC) begin
                buf2_wr_en = 1; buf2_wr_addr = r2_ch * 500 + r2_pos;
                if (buf2_rd_data < 0) buf2_wr_data = 0;
                else buf2_wr_data = rescale8(buf2_rd_data, R2_M);
            end else if (state == ST_P2_EXEC) begin
                pool2_wr_en = 1; pool2_wr_addr = p2_ch * 250 + p2_pos;
                if (pool_left > buf2_rd_data) pool2_wr_data = rescale8(pool_left, P2_M);
                else pool2_wr_data = rescale8(buf2_rd_data, P2_M);
            end else if (state == ST_C3_EXEC && c3_ic == 31 && c3_k == 4) begin
                buf3_wr_en = 1; buf3_wr_addr = c3_oc * 250 + c3_pos;
                buf3_wr_data = conv_quant(next_acc_comb, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
            end else if (state == ST_R3_EXEC) begin
                buf3_wr_en = 1; buf3_wr_addr = r3_ch * 250 + r3_pos;
                if (buf3_rd_data < 0) buf3_wr_data = 0;
                else buf3_wr_data = rescale8(buf3_rd_data, R3_M);
            end else if (state == ST_GAP_EXEC && gap_pos == 249) begin
                gap_wr_en = 1; gap_wr_addr = gap_ch;
                gap_wr_data = gap_quant(gap_accumulator + buf3_rd_data);
            end
        end
        mid_wr_en = buf1_wr_en || buf2_wr_en;
        if (buf1_wr_en) begin
            mid_wr_addr = buf1_wr_addr;
            mid_wr_data = buf1_wr_data;
        end else begin
            mid_wr_addr = buf2_wr_addr;
            mid_wr_data = buf2_wr_data;
        end
    end

    always @* begin
        mac_product = $signed(8'sd0) * $signed(8'sd0);
        case (state)
            ST_C1_EXEC: begin
                if ((c1_pos + c1_k) >= 3 && (c1_pos + c1_k) < 1003)
                    mac_product = $signed(input_rd_data) * $signed(w1_rd_data);
                else mac_product = 0;
            end
            ST_C2_EXEC: begin
                if ((c2_pos + c2_k) >= 3 && (c2_pos + c2_k) < 503)
                    mac_product = $signed(pool1_rd_data) * $signed(w2_rd_data);
                else mac_product = 0;
            end
            ST_C3_EXEC: begin
                if ((c3_pos + c3_k) >= 2 && (c3_pos + c3_k) < 252)
                    mac_product = $signed(pool2_rd_data) * $signed(w3_rd_data);
                else mac_product = 0;
            end
            ST_H_EXEC:  mac_product = $signed(gap_rd_data) * $signed(wh_rd_data);
            default: begin end
        endcase
    end

    always @(posedge clk or negedge rst_n) begin : core_fsm
        reg signed [63:0] next_acc;
        if (!rst_n) begin
            state <= ST_IDLE; busy <= 0; done <= 0;
            logit0 <= 0; logit1 <= 0; logit2 <= 0; logit3 <= 0; logit4 <= 0;
            c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
            r1_ch <= 0; r1_pos <= 0; p1_ch <= 0; p1_pos <= 0;
            c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0;
            r2_ch <= 0; r2_pos <= 0; p2_ch <= 0; p2_pos <= 0;
            c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0;
            r3_ch <= 0; r3_pos <= 0; gap_ch <= 0; gap_pos <= 0;
            head_oc <= 0; head_ic <= 0; accumulator <= 0; gap_accumulator <= 0;
            pool_left <= 0;
            wh_rd_latched <= 0;
        end else begin
            done <= 0;
            if (load_we) begin
                if (load_kind == LOAD_B1) b1_mem[load_index] <= load_data;
                else if (load_kind == LOAD_B2) b2_mem[load_index] <= load_data;
                else if (load_kind == LOAD_B3) b3_mem[load_index] <= load_data;
                else if (load_kind == LOAD_BH) bh_mem[load_index] <= load_data;
                else if (load_kind == LOAD_WH) wh_mem[load_index] <= load_data;
            end else begin
                case (state)
                    ST_IDLE: if (start) begin
                        state <= ST_C1_REQ; busy <= 1; c1_oc <= 0; c1_pos <= 0;
                        c1_ic <= 0; c1_k <= 0; accumulator <= 0;
                    end
                    ST_C1_REQ: state <= ST_C1_EXEC;
                    ST_C1_EXEC: begin
                        next_acc = accumulator + mac_product;
                        if (c1_ic == 11 && c1_k == 6) begin
`ifdef MODEL_DEBUG
                            conv1_raw_mem[c1_oc * 1000 + c1_pos] <= conv_quant(next_acc, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
`endif
                            accumulator <= 0; c1_ic <= 0; c1_k <= 0;
                            if (c1_pos == 999) begin
                                c1_pos <= 0;
                                if (c1_oc == 15) begin state <= ST_R1_REQ; r1_ch <= 0; r1_pos <= 0; end
                                else begin c1_oc <= c1_oc + 1'b1; state <= ST_C1_REQ; end
                            end else begin c1_pos <= c1_pos + 1'b1; state <= ST_C1_REQ; end
                        end else begin
                            accumulator <= next_acc; state <= ST_C1_REQ;
                            if (c1_k == 6) begin c1_k <= 0; c1_ic <= c1_ic + 1'b1; end
                            else c1_k <= c1_k + 1'b1;
                        end
                    end
                    ST_R1_REQ: state <= ST_R1_EXEC;
                    ST_R1_EXEC: begin
`ifdef MODEL_DEBUG
                        if (buf1_rd_data < 0)
                            relu1_shadow_mem[r1_ch * 1000 + r1_pos] <= 0;
                        else
                            relu1_shadow_mem[r1_ch * 1000 + r1_pos] <= rescale8(buf1_rd_data, R1_M);
`endif
                        if (r1_pos == 999) begin
                            r1_pos <= 0;
                            if (r1_ch == 15) begin state <= ST_P1_REQ0; p1_ch <= 0; p1_pos <= 0; end
                            else begin r1_ch <= r1_ch + 1'b1; state <= ST_R1_REQ; end
                        end else begin r1_pos <= r1_pos + 1'b1; state <= ST_R1_REQ; end
                    end
                    ST_P1_REQ0: state <= ST_P1_REQ1;
                    ST_P1_REQ1: begin pool_left <= buf1_rd_data; state <= ST_P1_EXEC; end
                    ST_P1_EXEC: begin
                        if (p1_pos == 499) begin
                            p1_pos <= 0;
                            if (p1_ch == 15) begin state <= ST_C2_REQ; c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0; accumulator <= 0; end
                            else begin p1_ch <= p1_ch + 1'b1; state <= ST_P1_REQ0; end
                        end else begin p1_pos <= p1_pos + 1'b1; state <= ST_P1_REQ0; end
                    end
                    ST_C2_REQ: state <= ST_C2_EXEC;
                    ST_C2_EXEC: begin
                        next_acc = accumulator + mac_product;
                        if (c2_ic == 15 && c2_k == 6) begin
`ifdef MODEL_DEBUG
                            conv2_raw_mem[c2_oc * 500 + c2_pos] <= conv_quant(next_acc, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
`endif
                            accumulator <= 0; c2_ic <= 0; c2_k <= 0;
                            if (c2_pos == 499) begin
                                c2_pos <= 0;
                                if (c2_oc == 31) begin state <= ST_R2_REQ; r2_ch <= 0; r2_pos <= 0; end
                                else begin c2_oc <= c2_oc + 1'b1; state <= ST_C2_REQ; end
                            end else begin c2_pos <= c2_pos + 1'b1; state <= ST_C2_REQ; end
                        end else begin
                            accumulator <= next_acc; state <= ST_C2_REQ;
                            if (c2_k == 6) begin c2_k <= 0; c2_ic <= c2_ic + 1'b1; end
                            else c2_k <= c2_k + 1'b1;
                        end
                    end
                    ST_R2_REQ: state <= ST_R2_EXEC;
                    ST_R2_EXEC: begin
`ifdef MODEL_DEBUG
                        if (buf2_rd_data < 0)
                            relu2_shadow_mem[r2_ch * 500 + r2_pos] <= 0;
                        else
                            relu2_shadow_mem[r2_ch * 500 + r2_pos] <= rescale8(buf2_rd_data, R2_M);
`endif
                        if (r2_pos == 499) begin
                            r2_pos <= 0;
                            if (r2_ch == 31) begin state <= ST_P2_REQ0; p2_ch <= 0; p2_pos <= 0; end
                            else begin r2_ch <= r2_ch + 1'b1; state <= ST_R2_REQ; end
                        end else begin r2_pos <= r2_pos + 1'b1; state <= ST_R2_REQ; end
                    end
                    ST_P2_REQ0: state <= ST_P2_REQ1;
                    ST_P2_REQ1: begin pool_left <= buf2_rd_data; state <= ST_P2_EXEC; end
                    ST_P2_EXEC: begin
                        if (p2_pos == 249) begin
                            p2_pos <= 0;
                            if (p2_ch == 31) begin state <= ST_C3_REQ; c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0; accumulator <= 0; end
                            else begin p2_ch <= p2_ch + 1'b1; state <= ST_P2_REQ0; end
                        end else begin p2_pos <= p2_pos + 1'b1; state <= ST_P2_REQ0; end
                    end
                    ST_C3_REQ: state <= ST_C3_EXEC;
                    ST_C3_EXEC: begin
                        next_acc = accumulator + mac_product;
                        if (c3_ic == 31 && c3_k == 4) begin
`ifdef MODEL_DEBUG
                            conv3_raw_mem[c3_oc * 250 + c3_pos] <= conv_quant(next_acc, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
`endif
                            accumulator <= 0; c3_ic <= 0; c3_k <= 0;
                            if (c3_pos == 249) begin
                                c3_pos <= 0;
                                if (c3_oc == 31) begin state <= ST_R3_REQ; r3_ch <= 0; r3_pos <= 0; end
                                else begin c3_oc <= c3_oc + 1'b1; state <= ST_C3_REQ; end
                            end else begin c3_pos <= c3_pos + 1'b1; state <= ST_C3_REQ; end
                        end else begin
                            accumulator <= next_acc; state <= ST_C3_REQ;
                            if (c3_k == 4) begin c3_k <= 0; c3_ic <= c3_ic + 1'b1; end
                            else c3_k <= c3_k + 1'b1;
                        end
                    end
                    ST_R3_REQ: state <= ST_R3_EXEC;
                    ST_R3_EXEC: begin
                        if (r3_pos == 249) begin
                            r3_pos <= 0;
                            if (r3_ch == 31) begin state <= ST_GAP_REQ; gap_ch <= 0; gap_pos <= 0; gap_accumulator <= 0; end
                            else begin r3_ch <= r3_ch + 1'b1; state <= ST_R3_REQ; end
                        end else begin r3_pos <= r3_pos + 1'b1; state <= ST_R3_REQ; end
                    end
                    ST_GAP_REQ: state <= ST_GAP_EXEC;
                    ST_GAP_EXEC: begin
                        if (gap_pos == 249) begin
                            gap_accumulator <= 0; gap_pos <= 0;
                            if (gap_ch == 31) begin state <= ST_H_REQ; head_oc <= 0; head_ic <= 0; accumulator <= 0; end
                            else begin gap_ch <= gap_ch + 1'b1; state <= ST_GAP_REQ; end
                        end else begin
                            gap_accumulator <= gap_accumulator + buf3_rd_data;
                            gap_pos <= gap_pos + 1'b1; state <= ST_GAP_REQ;
                        end
                    end
                    ST_H_REQ: begin
                        wh_rd_latched <= wh_mem_read;
                        state <= ST_H_EXEC;
                    end
                    ST_H_EXEC: begin
                        next_acc = accumulator + mac_product;
                        if (head_ic == 31) begin
                            case (head_oc)
                                0: logit0 <= conv_quant(next_acc, bh_mem[0], H_PRODUCT_M, H_BIAS_M);
                                1: logit1 <= conv_quant(next_acc, bh_mem[1], H_PRODUCT_M, H_BIAS_M);
                                2: logit2 <= conv_quant(next_acc, bh_mem[2], H_PRODUCT_M, H_BIAS_M);
                                3: logit3 <= conv_quant(next_acc, bh_mem[3], H_PRODUCT_M, H_BIAS_M);
                                default: logit4 <= conv_quant(next_acc, bh_mem[4], H_PRODUCT_M, H_BIAS_M);
                            endcase
                            accumulator <= 0; head_ic <= 0;
                            if (head_oc == 4) begin state <= ST_DONE; busy <= 0; done <= 1; end
                            else begin head_oc <= head_oc + 1'b1; state <= ST_H_REQ; end
                        end else begin accumulator <= next_acc; head_ic <= head_ic + 1'b1; state <= ST_H_REQ; end
                    end
                    ST_DONE: begin
                        if (start) begin state <= ST_C1_REQ; busy <= 1; c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0; accumulator <= 0; end
                    end
                    default: begin state <= ST_IDLE; busy <= 0; end
                endcase
            end
        end
    end
endmodule
