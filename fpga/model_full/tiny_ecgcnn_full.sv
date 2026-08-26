`timescale 1ns/1ps

// Fixed-shape TinyECGCNN integer core.
//
// This core is intentionally explicit rather than a generic NPU: it mirrors
// the frozen PTB-XL model (12x1000 -> 16x1000 -> 16x500 -> 32x500 ->
// 32x250 -> 32x250 -> 32 -> 5) and exposes a byte load port so a board wrapper
// can source the parameters from SDRAM.  The arrays are also public to a
// self-checking testbench, which allows `$readmemh`-loaded model artifacts to
// be compared layer by layer before adding the SDRAM controller.
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
    // load_kind values used by the SDRAM/UART wrapper.
    localparam [3:0] LOAD_INPUT = 4'd0;
    localparam [3:0] LOAD_W1    = 4'd1;
    localparam [3:0] LOAD_B1    = 4'd2;
    localparam [3:0] LOAD_W2    = 4'd3;
    localparam [3:0] LOAD_B2    = 4'd4;
    localparam [3:0] LOAD_W3    = 4'd5;
    localparam [3:0] LOAD_B3    = 4'd6;
    localparam [3:0] LOAD_WH    = 4'd7;
    localparam [3:0] LOAD_BH    = 4'd8;

    // The private PTQ export is signed INT8 and follows PyTorch's contiguous
    // [out_channel, in_channel, kernel] / [out_channel, in_channel] order.
    reg signed [7:0] input_mem [0:11999];
    reg signed [7:0] buf1_mem   [0:15999];
    reg signed [7:0] pool1_mem  [0:7999];
    reg signed [7:0] buf2_mem   [0:15999];
    reg signed [7:0] pool2_mem  [0:7999];
    reg signed [7:0] buf3_mem   [0:7999];
    reg signed [7:0] gap_mem    [0:31];
`ifdef MODEL_DEBUG
    reg signed [7:0] conv1_raw_mem [0:15999];
    reg signed [7:0] conv2_raw_mem [0:15999];
    reg signed [7:0] conv3_raw_mem [0:7999];
`endif
    reg signed [7:0] w1_mem     [0:1343];
    reg signed [7:0] b1_mem     [0:15];
    reg signed [7:0] w2_mem     [0:3583];
    reg signed [7:0] b2_mem     [0:31];
    reg signed [7:0] w3_mem     [0:5119];
    reg signed [7:0] b3_mem     [0:31];
    reg signed [7:0] wh_mem     [0:159];
    reg signed [7:0] bh_mem     [0:4];

    // QSHIFT=31 fixed-point factors generated from the float32 PTQ contract.
    // A separate bias factor keeps the accumulator in input*weight units.
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
    localparam signed [127:0] GAP_DEN = 128'sd536870912000; // 250 * 2^31

    function automatic signed [7:0] clip8;
        input signed [127:0] value;
        begin
            if (value > 127)
                clip8 = 8'sd127;
            else if (value < -128)
                clip8 = -8'sd128;
            else
                clip8 = value[7:0];
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

    localparam [4:0] ST_IDLE  = 5'd0;
    localparam [4:0] ST_C1    = 5'd1;
    localparam [4:0] ST_R1    = 5'd2;
    localparam [4:0] ST_P1    = 5'd3;
    localparam [4:0] ST_C2    = 5'd4;
    localparam [4:0] ST_R2    = 5'd5;
    localparam [4:0] ST_P2    = 5'd6;
    localparam [4:0] ST_C3    = 5'd7;
    localparam [4:0] ST_R3    = 5'd8;
    localparam [4:0] ST_GAP   = 5'd9;
    localparam [4:0] ST_HEAD  = 5'd10;
    localparam [4:0] ST_DONE  = 5'd11;
    reg [4:0] state;

    reg [4:0]  c1_oc, r1_ch, p1_ch;
    reg [9:0]  c1_pos, r1_pos;
    reg [8:0]  p1_pos;
    reg [3:0]  c1_ic;
    reg [2:0]  c1_k;
    reg [5:0]  c2_oc, r2_ch, p2_ch;
    reg [8:0]  c2_pos, r2_pos;
    reg [7:0]  p2_pos;
    reg [4:0]  c2_ic;
    reg [2:0]  c2_k;
    reg [5:0]  c3_oc, r3_ch;
    reg [7:0]  c3_pos, r3_pos;
    reg [4:0]  c3_ic;
    reg [2:0]  c3_k;
    reg [5:0]  gap_ch;
    reg [8:0]  gap_pos;
    reg [2:0]  head_oc;
    reg [5:0]  head_ic;
    reg signed [63:0] accumulator;
    reg signed [63:0] gap_accumulator;

    reg signed [7:0] mac_a;
    reg signed [7:0] mac_w;
    reg signed [63:0] mac_product;
    integer address_tmp;

    // Combinational memory read side of the one-MAC-per-cycle engine.  The
    // registered state machine below performs all writes on the next clock.
    always @* begin
        mac_a = 8'sd0;
        mac_w = 8'sd0;
        address_tmp = 0;
        case (state)
            ST_C1: begin
                address_tmp = c1_pos + c1_k - 3;
                if ((c1_pos + c1_k) >= 3 && (c1_pos + c1_k) < 1003)
                    mac_a = input_mem[c1_ic * 1000 + address_tmp];
                mac_w = w1_mem[c1_oc * 84 + c1_ic * 7 + c1_k];
            end
            ST_C2: begin
                address_tmp = c2_pos + c2_k - 3;
                if ((c2_pos + c2_k) >= 3 && (c2_pos + c2_k) < 503)
                    mac_a = pool1_mem[c2_ic * 500 + address_tmp];
                mac_w = w2_mem[c2_oc * 112 + c2_ic * 7 + c2_k];
            end
            ST_C3: begin
                address_tmp = c3_pos + c3_k - 2;
                if ((c3_pos + c3_k) >= 2 && (c3_pos + c3_k) < 252)
                    mac_a = pool2_mem[c3_ic * 250 + address_tmp];
                mac_w = w3_mem[c3_oc * 160 + c3_ic * 5 + c3_k];
            end
            ST_HEAD: begin
                mac_a = gap_mem[head_ic];
                mac_w = wh_mem[head_oc * 32 + head_ic];
            end
            default: begin end
        endcase
        mac_product = $signed(mac_a) * $signed(mac_w);
    end

    always @(posedge clk or negedge rst_n) begin : core_fsm
        reg signed [63:0] next_acc;
        if (!rst_n) begin
            state <= ST_IDLE;
            busy <= 1'b0;
            done <= 1'b0;
            logit0 <= 0; logit1 <= 0; logit2 <= 0; logit3 <= 0; logit4 <= 0;
            c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
            r1_ch <= 0; r1_pos <= 0; p1_ch <= 0; p1_pos <= 0;
            c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0;
            r2_ch <= 0; r2_pos <= 0; p2_ch <= 0; p2_pos <= 0;
            c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0;
            r3_ch <= 0; r3_pos <= 0; gap_ch <= 0; gap_pos <= 0;
            head_oc <= 0; head_ic <= 0;
            accumulator <= 0;
            gap_accumulator <= 0;
        end else begin
            done <= 1'b0;

            if (load_we) begin
                case (load_kind)
                    LOAD_INPUT: input_mem[load_index] <= load_data;
                    LOAD_W1:    w1_mem[load_index] <= load_data;
                    LOAD_B1:    b1_mem[load_index] <= load_data;
                    LOAD_W2:    w2_mem[load_index] <= load_data;
                    LOAD_B2:    b2_mem[load_index] <= load_data;
                    LOAD_W3:    w3_mem[load_index] <= load_data;
                    LOAD_B3:    b3_mem[load_index] <= load_data;
                    LOAD_WH:    wh_mem[load_index] <= load_data;
                    LOAD_BH:    bh_mem[load_index] <= load_data;
                    default: begin end
                endcase
            end else begin
                case (state)
                    ST_IDLE: begin
                        if (start) begin
                            state <= ST_C1;
                            busy <= 1'b1;
                            c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0;
                            accumulator <= 0;
                        end
                    end
                    ST_C1: begin
                        next_acc = accumulator + mac_product;
                        if (c1_ic == 11 && c1_k == 6) begin
                            buf1_mem[c1_oc * 1000 + c1_pos] <= conv_quant(next_acc, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
`ifdef MODEL_DEBUG
                            conv1_raw_mem[c1_oc * 1000 + c1_pos] <= conv_quant(next_acc, b1_mem[c1_oc], C1_PRODUCT_M, C1_BIAS_M);
`endif
                            accumulator <= 0;
                            c1_ic <= 0; c1_k <= 0;
                            if (c1_pos == 999) begin
                                c1_pos <= 0; c1_oc <= c1_oc + 1'b1;
                                if (c1_oc == 15) begin
                                    state <= ST_R1; r1_ch <= 0; r1_pos <= 0;
                                end
                            end else begin
                                c1_pos <= c1_pos + 1'b1;
                            end
                        end else begin
                            accumulator <= next_acc;
                            if (c1_k == 6) begin c1_k <= 0; c1_ic <= c1_ic + 1'b1; end
                            else c1_k <= c1_k + 1'b1;
                        end
                    end
                    ST_R1: begin
                        if (buf1_mem[r1_ch * 1000 + r1_pos] < 0)
                            buf1_mem[r1_ch * 1000 + r1_pos] <= 0;
                        else
                            buf1_mem[r1_ch * 1000 + r1_pos] <= rescale8(buf1_mem[r1_ch * 1000 + r1_pos], R1_M);
                        if (r1_pos == 999) begin
                            r1_pos <= 0;
                            if (r1_ch == 15) begin state <= ST_P1; p1_ch <= 0; p1_pos <= 0; end
                            else r1_ch <= r1_ch + 1'b1;
                        end else r1_pos <= r1_pos + 1'b1;
                    end
                    ST_P1: begin
                        if (buf1_mem[p1_ch * 1000 + p1_pos * 2] > buf1_mem[p1_ch * 1000 + p1_pos * 2 + 1])
                            pool1_mem[p1_ch * 500 + p1_pos] <= rescale8(buf1_mem[p1_ch * 1000 + p1_pos * 2], P1_M);
                        else
                            pool1_mem[p1_ch * 500 + p1_pos] <= rescale8(buf1_mem[p1_ch * 1000 + p1_pos * 2 + 1], P1_M);
                        if (p1_pos == 499) begin
                            p1_pos <= 0;
                            if (p1_ch == 15) begin state <= ST_C2; c2_oc <= 0; c2_pos <= 0; c2_ic <= 0; c2_k <= 0; accumulator <= 0; end
                            else p1_ch <= p1_ch + 1'b1;
                        end else p1_pos <= p1_pos + 1'b1;
                    end
                    ST_C2: begin
                        next_acc = accumulator + mac_product;
                        if (c2_ic == 15 && c2_k == 6) begin
                            buf2_mem[c2_oc * 500 + c2_pos] <= conv_quant(next_acc, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
`ifdef MODEL_DEBUG
                            conv2_raw_mem[c2_oc * 500 + c2_pos] <= conv_quant(next_acc, b2_mem[c2_oc], C2_PRODUCT_M, C2_BIAS_M);
`endif
                            accumulator <= 0; c2_ic <= 0; c2_k <= 0;
                            if (c2_pos == 499) begin
                                c2_pos <= 0; c2_oc <= c2_oc + 1'b1;
                                if (c2_oc == 31) begin state <= ST_R2; r2_ch <= 0; r2_pos <= 0; end
                            end else c2_pos <= c2_pos + 1'b1;
                        end else begin
                            accumulator <= next_acc;
                            if (c2_k == 6) begin c2_k <= 0; c2_ic <= c2_ic + 1'b1; end
                            else c2_k <= c2_k + 1'b1;
                        end
                    end
                    ST_R2: begin
                        if (buf2_mem[r2_ch * 500 + r2_pos] < 0)
                            buf2_mem[r2_ch * 500 + r2_pos] <= 0;
                        else
                            buf2_mem[r2_ch * 500 + r2_pos] <= rescale8(buf2_mem[r2_ch * 500 + r2_pos], R2_M);
                        if (r2_pos == 499) begin
                            r2_pos <= 0;
                            if (r2_ch == 31) begin state <= ST_P2; p2_ch <= 0; p2_pos <= 0; end
                            else r2_ch <= r2_ch + 1'b1;
                        end else r2_pos <= r2_pos + 1'b1;
                    end
                    ST_P2: begin
                        if (buf2_mem[p2_ch * 500 + p2_pos * 2] > buf2_mem[p2_ch * 500 + p2_pos * 2 + 1])
                            pool2_mem[p2_ch * 250 + p2_pos] <= rescale8(buf2_mem[p2_ch * 500 + p2_pos * 2], P2_M);
                        else
                            pool2_mem[p2_ch * 250 + p2_pos] <= rescale8(buf2_mem[p2_ch * 500 + p2_pos * 2 + 1], P2_M);
                        if (p2_pos == 249) begin
                            p2_pos <= 0;
                            if (p2_ch == 31) begin state <= ST_C3; c3_oc <= 0; c3_pos <= 0; c3_ic <= 0; c3_k <= 0; accumulator <= 0; end
                            else p2_ch <= p2_ch + 1'b1;
                        end else p2_pos <= p2_pos + 1'b1;
                    end
                    ST_C3: begin
                        next_acc = accumulator + mac_product;
                        if (c3_ic == 31 && c3_k == 4) begin
                            buf3_mem[c3_oc * 250 + c3_pos] <= conv_quant(next_acc, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
`ifdef MODEL_DEBUG
                            conv3_raw_mem[c3_oc * 250 + c3_pos] <= conv_quant(next_acc, b3_mem[c3_oc], C3_PRODUCT_M, C3_BIAS_M);
`endif
                            accumulator <= 0; c3_ic <= 0; c3_k <= 0;
                            if (c3_pos == 249) begin
                                c3_pos <= 0; c3_oc <= c3_oc + 1'b1;
                                if (c3_oc == 31) begin state <= ST_R3; r3_ch <= 0; r3_pos <= 0; end
                            end else c3_pos <= c3_pos + 1'b1;
                        end else begin
                            accumulator <= next_acc;
                            if (c3_k == 4) begin c3_k <= 0; c3_ic <= c3_ic + 1'b1; end
                            else c3_k <= c3_k + 1'b1;
                        end
                    end
                    ST_R3: begin
                        if (buf3_mem[r3_ch * 250 + r3_pos] < 0)
                            buf3_mem[r3_ch * 250 + r3_pos] <= 0;
                        else
                            buf3_mem[r3_ch * 250 + r3_pos] <= rescale8(buf3_mem[r3_ch * 250 + r3_pos], R3_M);
                        if (r3_pos == 249) begin
                            r3_pos <= 0;
                            if (r3_ch == 31) begin state <= ST_GAP; gap_ch <= 0; gap_pos <= 0; gap_accumulator <= 0; end
                            else r3_ch <= r3_ch + 1'b1;
                        end else r3_pos <= r3_pos + 1'b1;
                    end
                    ST_GAP: begin
                        if (gap_pos == 249) begin
                            gap_mem[gap_ch] <= gap_quant(gap_accumulator + buf3_mem[gap_ch * 250 + gap_pos]);
                            gap_accumulator <= 0; gap_pos <= 0;
                            if (gap_ch == 31) begin state <= ST_HEAD; head_oc <= 0; head_ic <= 0; accumulator <= 0; end
                            else gap_ch <= gap_ch + 1'b1;
                        end else begin
                            gap_accumulator <= gap_accumulator + buf3_mem[gap_ch * 250 + gap_pos];
                            gap_pos <= gap_pos + 1'b1;
                        end
                    end
                    ST_HEAD: begin
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
                            if (head_oc == 4) begin state <= ST_DONE; busy <= 1'b0; done <= 1'b1; end
                            else head_oc <= head_oc + 1'b1;
                        end else begin
                            accumulator <= next_acc;
                            head_ic <= head_ic + 1'b1;
                        end
                    end
                    ST_DONE: begin
                        // Hold logits until the next start; done is a pulse.
                        if (start) begin state <= ST_C1; busy <= 1'b1; c1_oc <= 0; c1_pos <= 0; c1_ic <= 0; c1_k <= 0; accumulator <= 0; end
                    end
                    default: begin state <= ST_IDLE; busy <= 1'b0; end
                endcase
            end
        end
    end
endmodule
