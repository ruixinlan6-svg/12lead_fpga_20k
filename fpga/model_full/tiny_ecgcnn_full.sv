`timescale 1ns/1ps

// Standalone synthesizable 10-layer PTB-XL CNN inference engine.
// Implements:
//   Conv1D (12 -> 16, k=7, pad=3)
//   ReLU1
//   MaxPool1D (k=2, s=2)
//   Conv1D (16 -> 32, k=7, pad=3)
//   ReLU2
//   MaxPool1D (k=2, s=2)
//   Conv1D (32 -> 32, k=5, pad=2)
//   ReLU3
//   GlobalAveragePooling1D (length 250 -> 1)
//   Dense / Head (32 -> 5)
module tiny_ecgcnn_full (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire        load_we,
    input  wire [3:0]  load_kind,
    input  wire [15:0] load_index,
    input  wire signed [7:0] load_data,
    output reg         busy,
    output reg         done,
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

    localparam integer QSHIFT = 31;

    // Intermediate activation / weight memories
    reg        input_wr_en;
    reg [13:0] input_wr_addr;
    reg        input_rd_en;
    reg [13:0] input_rd_addr;
    wire signed [7:0] input_rd_data;

    reg        mid_wr_en;
    reg [14:0] mid_wr_addr;
    reg signed [7:0] mid_wr_data;
    reg        mid_rd_en;
    reg [14:0] mid_rd_addr;
    wire signed [7:0] mid_rd_data;

    reg        pool1_wr_en;
    reg [12:0] pool1_wr_addr;
    reg signed [7:0] pool1_wr_data;
    reg        pool1_rd_en;
    reg [12:0] pool1_rd_addr;
    wire signed [7:0] pool1_rd_data;

    reg        pool2_wr_en;
    reg [12:0] pool2_wr_addr;
    reg signed [7:0] pool2_wr_data;
    reg        pool2_rd_en;
    reg [12:0] pool2_rd_addr;
    wire signed [7:0] pool2_rd_data;

    reg        buf3_wr_en;
    reg [12:0] buf3_wr_addr;
    reg signed [7:0] buf3_wr_data;
    reg        buf3_rd_en;
    reg [12:0] buf3_rd_addr;
    wire signed [7:0] buf3_rd_data;

    reg        gap_wr_en;
    reg [5:0]  gap_wr_addr;
    reg signed [7:0] gap_wr_data;
    reg        gap_rd_en;
    reg [5:0]  gap_rd_addr;
    wire signed [7:0] gap_rd_data;

    reg        w1_wr_en;
    reg [10:0] w1_wr_addr;
    reg        w1_rd_en;
    reg [10:0] w1_rd_addr;
    wire signed [7:0] w1_rd_data;

    reg        w2_wr_en;
    reg [11:0] w2_wr_addr;
    reg        w2_rd_en;
    reg [11:0] w2_rd_addr;
    wire signed [7:0] w2_rd_data;

    reg        w3_wr_en;
    reg [12:0] w3_wr_addr;
    reg        w3_rd_en;
    reg [12:0] w3_rd_addr;
    wire signed [7:0] w3_rd_data;

    reg signed [7:0] b1_mem [0:15];
    reg signed [7:0] b2_mem [0:31];
    reg signed [7:0] b3_mem [0:31];
    reg signed [7:0] bh_mem [0:4];
    reg signed [7:0] wh_mem [0:159];

    reg signed [7:0] wh_rd_latched;
    wire signed [7:0] wh_rd_data = wh_rd_latched;
    wire signed [7:0] buf1_rd_data = mid_rd_data;
    wire signed [7:0] buf2_rd_data = mid_rd_data;

`ifdef MODEL_DEBUG
    reg signed [7:0] conv1_raw_mem [0:15999];
    reg signed [7:0] conv2_raw_mem [0:15999];
    reg signed [7:0] conv3_raw_mem [0:7999];
    reg signed [7:0] relu1_shadow_mem [0:15999];
    reg signed [7:0] relu2_shadow_mem [0:15999];
`endif

    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(14), .DEPTH(12000)) input_ram (
        .clk(clk), .wr_en(input_wr_en), .wr_addr(input_wr_addr), .wr_data(load_data),
        .rd_en(input_rd_en), .rd_addr(input_rd_addr), .rd_data(input_rd_data));

    ecg_sync_dp_ram #(.DATA_WIDTH(8), .ADDR_WIDTH(15), .DEPTH(16000)) mid_ram (
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
    localparam signed [63:0] GAP_M_EFF    = 64'sd32422936;
    localparam signed [63:0] H_PRODUCT_M  = 64'sd12529589;
    localparam signed [63:0] H_BIAS_M     = 64'sd37360384;
    localparam signed [63:0] GAP_DEN      = 64'sd536870912000;

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

    localparam [4:0] ST_IDLE     = 5'd0;
    localparam [4:0] ST_C1_REQ   = 5'd1;
    localparam [4:0] ST_C1_EXEC  = 5'd2;
    localparam [4:0] ST_C1_WRITE = 5'd3;
    localparam [4:0] ST_R1_REQ   = 5'd4;
    localparam [4:0] ST_R1_EXEC  = 5'd5;
    localparam [4:0] ST_P1_REQ0  = 5'd6;
    localparam [4:0] ST_P1_REQ1  = 5'd7;
    localparam [4:0] ST_P1_EXEC  = 5'd8;
    localparam [4:0] ST_C2_REQ   = 5'd9;
    localparam [4:0] ST_C2_EXEC  = 5'd10;
    localparam [4:0] ST_C2_WRITE = 5'd11;
    localparam [4:0] ST_R2_REQ   = 5'd12;
    localparam [4:0] ST_R2_EXEC  = 5'd13;
    localparam [4:0] ST_P2_REQ0  = 5'd14;
    localparam [4:0] ST_P2_REQ1  = 5'd15;
    localparam [4:0] ST_P2_EXEC  = 5'd16;
    localparam [4:0] ST_C3_REQ   = 5'd17;
    localparam [4:0] ST_C3_EXEC  = 5'd18;
    localparam [4:0] ST_C3_WRITE = 5'd19;
    localparam [4:0] ST_R3_REQ   = 5'd20;
    localparam [4:0] ST_R3_EXEC  = 5'd21;
    localparam [4:0] ST_GAP_REQ  = 5'd22;
    localparam [4:0] ST_GAP_EXEC = 5'd23;
    localparam [4:0] ST_GAP_WRITE= 5'd24;
    localparam [4:0] ST_H_REQ    = 5'd25;
    localparam [4:0] ST_H_EXEC   = 5'd26;
    localparam [4:0] ST_H_WRITE  = 5'd27;
    localparam [4:0] ST_DONE     = 5'd28;

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

    reg signed [31:0] accumulator;
    reg signed [31:0] gap_accumulator;
    reg signed [7:0]  pool_left;

    reg signed [15:0] mac_product;

    always @* begin
        input_rd_en = 0; mid_rd_en = 0; pool1_rd_en = 0; pool2_rd_en = 0;
        buf3_rd_en = 0; gap_rd_en = 0;
        w1_rd_en = 0; w2_rd_en = 0; w3_rd_en = 0;
        input_rd_addr = 0; mid_rd_addr = 0; pool1_rd_addr = 0;
        pool2_rd_addr = 0; buf3_rd_addr = 0; gap_rd_addr = 0;
        w1_rd_addr = 0; w2_rd_addr = 0; w3_rd_addr = 0;

        case (state)
            ST_C1_REQ: begin
                input_rd_en = 1;
                input_rd_addr = c1_ic * 1000 + (c1_pos + c1_k - 3);
                w1_rd_en = 1;
                w1_rd_addr = c1_oc * (12 * 7) + c1_ic * 7 + c1_k;
            end
            ST_R1_REQ: begin
                mid_rd_en = 1;
                mid_rd_addr = r1_ch * 1000 + r1_pos;
            end
            ST_P1_REQ0: begin
                mid_rd_en = 1;
                mid_rd_addr = p1_ch * 1000 + (p1_pos * 2);
            end
            ST_P1_REQ1: begin
                mid_rd_en = 1;
                mid_rd_addr = p1_ch * 1000 + (p1_pos * 2 + 1);
            end
            ST_C2_REQ: begin
                pool1_rd_en = 1;
                pool1_rd_addr = c2_ic * 500 + (c2_pos + c2_k - 3);
                w2_rd_en = 1;
                w2_rd_addr = c2_oc * (16 * 7) + c2_ic * 7 + c2_k;
            end
            ST_R2_REQ: begin
                mid_rd_en = 1;
                mid_rd_addr = r2_ch * 500 + r2_pos;
            end
            ST_P2_REQ0: begin
                mid_rd_en = 1;
                mid_rd_addr = p2_ch * 500 + (p2_pos * 2);
            end
            ST_P2_REQ1: begin
                mid_rd_en = 1;
                mid_rd_addr = p2_ch * 500 + (p2_pos * 2 + 1);
            end
            ST_C3_REQ: begin
                pool2_rd_en = 1;
                pool2_rd_addr = c3_ic * 250 + (c3_pos + c3_k - 2);
                w3_rd_en = 1;
                w3_rd_addr = c3_oc * (32 * 5) + c3_ic * 5 + c3_k;
            end
            ST_R3_REQ: begin
                buf3_rd_en = 1;
                buf3_rd_addr = r3_ch * 250 + r3_pos;
            end
            ST_GAP_REQ: begin
                buf3_rd_en = 1;
                buf3_rd_addr = gap_ch * 250 + gap_pos;
            end
            ST_H_REQ: begin
                gap_rd_en = 1;
                gap_rd_addr = head_ic;
            end
            default: begin end
        endcase

        input_wr_en = load_we && (load_kind == LOAD_INPUT);
        input_wr_addr = load_index[13:0];
        w1_wr_en = load_we && (load_kind == LOAD_W1);
        w1_wr_addr = load_index[10:0];
        w2_wr_en = load_we && (load_kind == LOAD_W2);
        w2_wr_addr = load_index[11:0];
        w3_wr_en = load_we && (load_kind == LOAD_W3);
        w3_wr_addr = load_index[12:0];

        mid_wr_en = 0; pool1_wr_en = 0; pool2_wr_en = 0;
        buf3_wr_en = 0; gap_wr_en = 0;
        mid_wr_addr = 0; pool1_wr_addr = 0; pool2_wr_addr = 0;
        buf3_wr_addr = 0; gap_wr_addr = 0;
        mid_wr_data = 0; pool1_wr_data = 0; pool2_wr_data = 0;
        buf3_wr_data = 0; gap_wr_data = 0;

        if (!load_we) begin
            if (state == ST_C1_WRITE) begin
                mid_wr_en = 1;
                mid_wr_addr = c1_oc * 1000 + c1_pos;
                mid_wr_data = conv_quant(accumulator, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
            end else if (state == ST_R1_EXEC) begin
                mid_wr_en = 1;
                mid_wr_addr = r1_ch * 1000 + r1_pos;
                if (buf1_rd_data < 0) mid_wr_data = 0;
                else mid_wr_data = rescale8(buf1_rd_data, R1_M);
            end else if (state == ST_P1_EXEC) begin
                pool1_wr_en = 1;
                pool1_wr_addr = p1_ch * 500 + p1_pos;
                if (pool_left > buf1_rd_data) pool1_wr_data = rescale8(pool_left, P1_M);
                else pool1_wr_data = rescale8(buf1_rd_data, P1_M);
            end else if (state == ST_C2_WRITE) begin
                mid_wr_en = 1;
                mid_wr_addr = c2_oc * 500 + c2_pos;
                mid_wr_data = conv_quant(accumulator, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
            end else if (state == ST_R2_EXEC) begin
                mid_wr_en = 1;
                mid_wr_addr = r2_ch * 500 + r2_pos;
                if (buf2_rd_data < 0) mid_wr_data = 0;
                else mid_wr_data = rescale8(buf2_rd_data, R2_M);
            end else if (state == ST_P2_EXEC) begin
                pool2_wr_en = 1;
                pool2_wr_addr = p2_ch * 250 + p2_pos;
                if (pool_left > buf2_rd_data) pool2_wr_data = rescale8(pool_left, P2_M);
                else pool2_wr_data = rescale8(buf2_rd_data, P2_M);
            end else if (state == ST_C3_WRITE) begin
                buf3_wr_en = 1;
                buf3_wr_addr = c3_oc * 250 + c3_pos;
                buf3_wr_data = conv_quant(accumulator, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
            end else if (state == ST_R3_EXEC) begin
                buf3_wr_en = 1;
                buf3_wr_addr = r3_ch * 250 + r3_pos;
                if (buf3_rd_data < 0) buf3_wr_data = 0;
                else buf3_wr_data = rescale8(buf3_rd_data, R3_M);
            end else if (state == ST_GAP_WRITE) begin
                gap_wr_en = 1;
                gap_wr_addr = gap_ch;
                gap_wr_data = gap_quant(gap_accumulator);
            end
        end
    end

    always @* begin
        mac_product = 16'sd0;
        case (state)
            ST_C1_EXEC: begin
                if ((c1_pos + c1_k) >= 3 && (c1_pos + c1_k) < 1003)
                    mac_product = $signed(input_rd_data) * $signed(w1_rd_data);
            end
            ST_C2_EXEC: begin
                if ((c2_pos + c2_k) >= 3 && (c2_pos + c2_k) < 503)
                    mac_product = $signed(pool1_rd_data) * $signed(w2_rd_data);
            end
            ST_C3_EXEC: begin
                if ((c3_pos + c3_k) >= 2 && (c3_pos + c3_k) < 252)
                    mac_product = $signed(pool2_rd_data) * $signed(w3_rd_data);
            end
            ST_H_EXEC: begin
                mac_product = $signed(gap_rd_data) * $signed(wh_rd_data);
            end
            default: begin end
        endcase
    end

    wire [7:0] wh_addr_direct = head_oc * 32 + head_ic;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= ST_IDLE;
            busy <= 0;
            done <= 0;
            logit0 <= 0; logit1 <= 0; logit2 <= 0; logit3 <= 0; logit4 <= 0;
            c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
            c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0;
            c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0;
            r1_ch <= 0; r1_pos <= 0;
            r2_ch <= 0; r2_pos <= 0;
            r3_ch <= 0; r3_pos <= 0;
            p1_ch <= 0; p1_pos <= 0;
            p2_ch <= 0; p2_pos <= 0;
            gap_ch <= 0; gap_pos <= 0;
            head_oc <= 0; head_ic <= 0;
            accumulator <= 0;
            gap_accumulator <= 0;
            pool_left <= 0;
            wh_rd_latched <= 0;
        end else begin
            done <= 0;
            if (load_we) begin
                if (load_kind == LOAD_B1) b1_mem[load_index[3:0]] <= load_data;
                else if (load_kind == LOAD_B2) b2_mem[load_index[4:0]] <= load_data;
                else if (load_kind == LOAD_B3) b3_mem[load_index[4:0]] <= load_data;
                else if (load_kind == LOAD_BH) bh_mem[load_index[2:0]] <= load_data;
                else if (load_kind == LOAD_WH) wh_mem[load_index[7:0]] <= load_data;
            end else begin
                case (state)
                    ST_IDLE: if (start) begin
                        state <= ST_C1_REQ;
                        busy <= 1;
                        c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
                        accumulator <= 0;
                    end

                    ST_C1_REQ: state <= ST_C1_EXEC;

                    ST_C1_EXEC: begin
                        if (c1_ic == 11 && c1_k == 6) begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C1_WRITE;
                        end else begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C1_REQ;
                            if (c1_k == 6) begin
                                c1_k <= 0;
                                c1_ic <= c1_ic + 1'b1;
                            end else begin
                                c1_k <= c1_k + 1'b1;
                            end
                        end
                    end

                    ST_C1_WRITE: begin
`ifdef MODEL_DEBUG
                        conv1_raw_mem[c1_oc * 1000 + c1_pos] <= conv_quant(accumulator, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
`endif
                        accumulator <= 0;
                        c1_ic <= 0;
                        c1_k <= 0;
                        if (c1_pos == 999) begin
                            c1_pos <= 0;
                            if (c1_oc == 15) begin
                                state <= ST_R1_REQ;
                                r1_ch <= 0;
                                r1_pos <= 0;
                            end else begin
                                c1_oc <= c1_oc + 1'b1;
                                state <= ST_C1_REQ;
                            end
                        end else begin
                            c1_pos <= c1_pos + 1'b1;
                            state <= ST_C1_REQ;
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
                            if (r1_ch == 15) begin
                                state <= ST_P1_REQ0;
                                p1_ch <= 0;
                                p1_pos <= 0;
                            end else begin
                                r1_ch <= r1_ch + 1'b1;
                                state <= ST_R1_REQ;
                            end
                        end else begin
                            r1_pos <= r1_pos + 1'b1;
                            state <= ST_R1_REQ;
                        end
                    end

                    ST_P1_REQ0: state <= ST_P1_REQ1;

                    ST_P1_REQ1: begin
                        pool_left <= buf1_rd_data;
                        state <= ST_P1_EXEC;
                    end

                    ST_P1_EXEC: begin
                        if (p1_pos == 499) begin
                            p1_pos <= 0;
                            if (p1_ch == 15) begin
                                state <= ST_C2_REQ;
                                c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0;
                                accumulator <= 0;
                            end else begin
                                p1_ch <= p1_ch + 1'b1;
                                state <= ST_P1_REQ0;
                            end
                        end else begin
                            p1_pos <= p1_pos + 1'b1;
                            state <= ST_P1_REQ0;
                        end
                    end

                    ST_C2_REQ: state <= ST_C2_EXEC;

                    ST_C2_EXEC: begin
                        if (c2_ic == 15 && c2_k == 6) begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C2_WRITE;
                        end else begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C2_REQ;
                            if (c2_k == 6) begin
                                c2_k <= 0;
                                c2_ic <= c2_ic + 1'b1;
                            end else begin
                                c2_k <= c2_k + 1'b1;
                            end
                        end
                    end

                    ST_C2_WRITE: begin
`ifdef MODEL_DEBUG
                        conv2_raw_mem[c2_oc * 500 + c2_pos] <= conv_quant(accumulator, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
`endif
                        accumulator <= 0;
                        c2_ic <= 0;
                        c2_k <= 0;
                        if (c2_pos == 499) begin
                            c2_pos <= 0;
                            if (c2_oc == 31) begin
                                state <= ST_R2_REQ;
                                r2_ch <= 0;
                                r2_pos <= 0;
                            end else begin
                                c2_oc <= c2_oc + 1'b1;
                                state <= ST_C2_REQ;
                            end
                        end else begin
                            c2_pos <= c2_pos + 1'b1;
                            state <= ST_C2_REQ;
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
                            if (r2_ch == 31) begin
                                state <= ST_P2_REQ0;
                                p2_ch <= 0;
                                p2_pos <= 0;
                            end else begin
                                r2_ch <= r2_ch + 1'b1;
                                state <= ST_R2_REQ;
                            end
                        end else begin
                            r2_pos <= r2_pos + 1'b1;
                            state <= ST_R2_REQ;
                        end
                    end

                    ST_P2_REQ0: state <= ST_P2_REQ1;

                    ST_P2_REQ1: begin
                        pool_left <= buf2_rd_data;
                        state <= ST_P2_EXEC;
                    end

                    ST_P2_EXEC: begin
                        if (p2_pos == 249) begin
                            p2_pos <= 0;
                            if (p2_ch == 31) begin
                                state <= ST_C3_REQ;
                                c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0;
                                accumulator <= 0;
                            end else begin
                                p2_ch <= p2_ch + 1'b1;
                                state <= ST_P2_REQ0;
                            end
                        end else begin
                            p2_pos <= p2_pos + 1'b1;
                            state <= ST_P2_REQ0;
                        end
                    end

                    ST_C3_REQ: state <= ST_C3_EXEC;

                    ST_C3_EXEC: begin
                        if (c3_ic == 31 && c3_k == 4) begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C3_WRITE;
                        end else begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_C3_REQ;
                            if (c3_k == 4) begin
                                c3_k <= 0;
                                c3_ic <= c3_ic + 1'b1;
                            end else begin
                                c3_k <= c3_k + 1'b1;
                            end
                        end
                    end

                    ST_C3_WRITE: begin
`ifdef MODEL_DEBUG
                        conv3_raw_mem[c3_oc * 250 + c3_pos] <= conv_quant(accumulator, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
`endif
                        accumulator <= 0;
                        c3_ic <= 0;
                        c3_k <= 0;
                        if (c3_pos == 249) begin
                            c3_pos <= 0;
                            if (c3_oc == 31) begin
                                state <= ST_R3_REQ;
                                r3_ch <= 0;
                                r3_pos <= 0;
                            end else begin
                                c3_oc <= c3_oc + 1'b1;
                                state <= ST_C3_REQ;
                            end
                        end else begin
                            c3_pos <= c3_pos + 1'b1;
                            state <= ST_C3_REQ;
                        end
                    end

                    ST_R3_REQ: state <= ST_R3_EXEC;

                    ST_R3_EXEC: begin
                        if (r3_pos == 249) begin
                            r3_pos <= 0;
                            if (r3_ch == 31) begin
                                state <= ST_GAP_REQ;
                                gap_ch <= 0;
                                gap_pos <= 0;
                                gap_accumulator <= 0;
                            end else begin
                                r3_ch <= r3_ch + 1'b1;
                                state <= ST_R3_REQ;
                            end
                        end else begin
                            r3_pos <= r3_pos + 1'b1;
                            state <= ST_R3_REQ;
                        end
                    end

                    ST_GAP_REQ: state <= ST_GAP_EXEC;

                    ST_GAP_EXEC: begin
                        if (gap_pos == 249) begin
                            gap_accumulator <= gap_accumulator + buf3_rd_data;
                            state <= ST_GAP_WRITE;
                        end else begin
                            gap_accumulator <= gap_accumulator + buf3_rd_data;
                            gap_pos <= gap_pos + 1'b1;
                            state <= ST_GAP_REQ;
                        end
                    end

                    ST_GAP_WRITE: begin
                        gap_accumulator <= 0;
                        gap_pos <= 0;
                        if (gap_ch == 31) begin
                            state <= ST_H_REQ;
                            head_oc <= 0;
                            head_ic <= 0;
                            accumulator <= 0;
                        end else begin
                            gap_ch <= gap_ch + 1'b1;
                            state <= ST_GAP_REQ;
                        end
                    end

                    ST_H_REQ: begin
                        wh_rd_latched <= wh_mem[wh_addr_direct];
                        state <= ST_H_EXEC;
                    end

                    ST_H_EXEC: begin
                        if (head_ic == 31) begin
                            accumulator <= accumulator + mac_product;
                            state <= ST_H_WRITE;
                        end else begin
                            accumulator <= accumulator + mac_product;
                            head_ic <= head_ic + 1'b1;
                            state <= ST_H_REQ;
                        end
                    end

                    ST_H_WRITE: begin
                        case (head_oc)
                            3'd0: logit0 <= conv_quant(accumulator, bh_mem[0], H_PRODUCT_M, H_BIAS_M);
                            3'd1: logit1 <= conv_quant(accumulator, bh_mem[1], H_PRODUCT_M, H_BIAS_M);
                            3'd2: logit2 <= conv_quant(accumulator, bh_mem[2], H_PRODUCT_M, H_BIAS_M);
                            3'd3: logit3 <= conv_quant(accumulator, bh_mem[3], H_PRODUCT_M, H_BIAS_M);
                            default: logit4 <= conv_quant(accumulator, bh_mem[4], H_PRODUCT_M, H_BIAS_M);
                        endcase
                        accumulator <= 0;
                        head_ic <= 0;
                        if (head_oc == 3'd4) begin
                            state <= ST_DONE;
                            busy <= 0;
                            done <= 1;
                        end else begin
                            head_oc <= head_oc + 1'b1;
                            state <= ST_H_REQ;
                        end
                    end

                    ST_DONE: begin
                        if (start) begin
                            state <= ST_C1_REQ;
                            busy <= 1;
                            c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
                            accumulator <= 0;
                        end
                    end

                    default: begin
                        state <= ST_IDLE;
                        busy <= 0;
                    end
                endcase
            end
        end
    end
endmodule