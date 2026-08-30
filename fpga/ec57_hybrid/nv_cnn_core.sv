`timescale 1ns / 1ps

// =============================================================================
// Module: nv_cnn_core
// Description: High-throughput INT8 CNN inference core for Twelve-Lead EC57
//              classification on Gowin GW2AR-18C.
// =============================================================================

module nv_cnn_core #(
    parameter WEIGHTS_HEX_FILE = "weights_int8.hex",
    parameter PARAMS_HEX_FILE  = "params_int32.hex"
)(
    input  wire        clk,
    input  wire        rst_n,

    // Control Interface
    input  wire        start,
    output reg         busy,
    output reg         done,

    // Beat Window Input Stream Interface (160 bytes)
    input  wire        wave_wr_valid,
    input  wire [7:0]  wave_wr_addr,
    input  wire signed [7:0] wave_wr_data,

    // 4 Scalar Auxiliary Features Input
    input  wire signed [7:0] feat_pre_rr,
    input  wire signed [7:0] feat_qrs_width,
    input  wire signed [7:0] feat_peak_ratio,
    input  wire signed [7:0] feat_sqi,

    // Inference Outputs
    output reg  signed [31:0] logit_non_veb,
    output reg  signed [31:0] logit_veb,
    output reg  [1:0]         beat_class,   // 2'b00: non-VEB, 2'b01: VEB
    output reg  [31:0]        cycle_count
);

    // -------------------------------------------------------------------------
    // Requantization Helper Function
    // -------------------------------------------------------------------------
    function automatic logic signed [7:0] requant_relu(
        input signed [31:0] acc,
        input signed [31:0] mult,
        input [4:0]         shift,
        input               relu_en
    );
        logic signed [63:0] prod;
        logic signed [63:0] round_term;
        logic signed [63:0] prod_rounded;
        logic signed [63:0] scaled;
        begin
            prod = acc * mult;
            if (shift > 0) begin
                round_term = (64'sd1 <<< (shift - 1));
                if (prod >= 0)
                    prod_rounded = prod + round_term;
                else
                    prod_rounded = prod + round_term - 64'sd1;
                scaled = prod_rounded >>> shift;
            end else begin
                scaled = prod;
            end

            if (relu_en && scaled < 0)
                requant_relu = 8'sd0;
            else if (scaled > 64'sd127)
                requant_relu = 8'sd127;
            else if (scaled < -64'sd128)
                requant_relu = -8'sd128;
            else
                requant_relu = scaled[7:0];
        end
    endfunction

    // -------------------------------------------------------------------------
    // Weight & Parameter Storage
    // -------------------------------------------------------------------------
    (* ram_style = "block" *) reg signed [7:0] rom_weights [0:1503];
    reg [31:0]       rom_params  [0:121];

    reg signed [31:0] conv1_bias  [0:7];
    reg signed [31:0] conv1_mult  [0:7];
    reg [4:0]         conv1_shift [0:7];

    reg signed [31:0] conv2_bias  [0:15];
    reg signed [31:0] conv2_mult  [0:15];
    reg [4:0]         conv2_shift [0:15];

    reg signed [31:0] conv3_bias  [0:15];
    reg signed [31:0] conv3_mult  [0:15];
    reg [4:0]         conv3_shift [0:15];

    reg signed [31:0] fc_bias     [0:1];

    integer p_idx;
    initial begin
        $readmemh(WEIGHTS_HEX_FILE, rom_weights);
        $readmemh(PARAMS_HEX_FILE, rom_params);

        for (p_idx = 0; p_idx < 8; p_idx = p_idx + 1) begin
            conv1_bias[p_idx]  = rom_params[p_idx * 3 + 0];
            conv1_mult[p_idx]  = rom_params[p_idx * 3 + 1];
            conv1_shift[p_idx] = rom_params[p_idx * 3 + 2][4:0];
        end

        for (p_idx = 0; p_idx < 16; p_idx = p_idx + 1) begin
            conv2_bias[p_idx]  = rom_params[24 + p_idx * 3 + 0];
            conv2_mult[p_idx]  = rom_params[24 + p_idx * 3 + 1];
            conv2_shift[p_idx] = rom_params[24 + p_idx * 3 + 2][4:0];
        end

        for (p_idx = 0; p_idx < 16; p_idx = p_idx + 1) begin
            conv3_bias[p_idx]  = rom_params[72 + p_idx * 3 + 0];
            conv3_mult[p_idx]  = rom_params[72 + p_idx * 3 + 1];
            conv3_shift[p_idx] = rom_params[72 + p_idx * 3 + 2][4:0];
        end

        fc_bias[0] = rom_params[120];
        fc_bias[1] = rom_params[121];
    end

    localparam W_OFF_CONV1 = 11'd0;    // 8 * 1 * 7 = 56
    localparam W_OFF_CONV2 = 11'd56;   // 16 * 8 * 5 = 640
    localparam W_OFF_CONV3 = 11'd696;  // 16 * 16 * 3 = 768
    localparam W_OFF_FC    = 11'd1464; // 2 * 20 = 40

    // Activation RAM Buffers
    (* ram_style = "block" *) reg signed [7:0] buf_a [0:639];
    (* ram_style = "block" *) reg signed [7:0] buf_b [0:639];
    (* ram_style = "block" *) reg signed [7:0] wave_cache [0:159];

    reg signed [7:0] gap_features [0:15];

    // FSM States
    typedef enum logic [3:0] {
        ST_IDLE,
        ST_L1_CALC,
        ST_L1_POOL,
        ST_L2_CALC,
        ST_L2_POOL,
        ST_L3_CALC,
        ST_L3_GAP,
        ST_L3_AVG,
        ST_FC_CALC,
        ST_DONE
    } state_t;

    state_t state;
    reg [4:0]  oc_idx;
    reg [6:0]  t_idx;
    reg [4:0]  ic_idx;
    reg [3:0]  k_idx;
    reg [1:0]  sub_t;

    reg signed [31:0] mac_acc;
    reg signed [7:0]  act_sub0;
    reg signed [31:0] gap_accum;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= ST_IDLE;
            busy          <= 1'b0;
            done          <= 1'b0;
            logit_non_veb <= 32'd0;
            logit_veb     <= 32'd0;
            beat_class    <= 2'b00;
            cycle_count   <= 32'd0;
            oc_idx        <= 5'd0;
            t_idx         <= 7'd0;
            ic_idx        <= 5'd0;
            k_idx         <= 4'd0;
            sub_t         <= 2'd0;
            mac_acc       <= 32'd0;
            act_sub0      <= 8'd0;
            gap_accum     <= 32'd0;
        end else begin
            if (wave_wr_valid) begin
                wave_cache[wave_wr_addr] <= wave_wr_data;
            end

            case (state)
                ST_IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        busy        <= 1'b1;
                        cycle_count <= 32'd0;
                        oc_idx      <= 5'd0;
                        t_idx       <= 7'd0;
                        sub_t       <= 2'd0;
                        k_idx       <= 4'd0;
                        mac_acc     <= conv1_bias[0];
                        state       <= ST_L1_CALC;
                    end
                end

                // Layer 1: Conv1D(1->8, k=7, p=3) -> ReLU -> MaxPool(2)
                ST_L1_CALC: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic signed [8:0] pos;
                        logic signed [7:0] in_val;
                        logic signed [7:0] w_val;
                        pos = $signed({2'b0, t_idx, 1'b0}) + $signed({7'b0, sub_t}) + $signed({5'b0, k_idx}) - 9'sd3;

                        if (pos < 0 || pos >= 160)
                            in_val = 8'sd0;
                        else
                            in_val = wave_cache[pos[7:0]];

                        w_val = rom_weights[W_OFF_CONV1 + oc_idx * 7 + k_idx];
                        mac_acc <= mac_acc + (in_val * w_val);

                        if (k_idx == 4'd6) begin
                            k_idx <= 4'd0;
                            state <= ST_L1_POOL;
                        end else begin
                            k_idx <= k_idx + 4'd1;
                        end
                    end
                end

                ST_L1_POOL: begin
                    cycle_count <= cycle_count + 32'd1;
                    if (sub_t == 2'd0) begin
                        act_sub0 <= requant_relu(mac_acc, conv1_mult[oc_idx], conv1_shift[oc_idx], 1'b1);
                        sub_t    <= 2'd1;
                        k_idx    <= 4'd0;
                        mac_acc  <= conv1_bias[oc_idx];
                        state    <= ST_L1_CALC;
                    end else begin
                        begin
                            logic signed [7:0] act1;
                            logic signed [7:0] max_val;
                            act1    = requant_relu(mac_acc, conv1_mult[oc_idx], conv1_shift[oc_idx], 1'b1);
                            max_val = (act1 > act_sub0) ? act1 : act_sub0;
                            buf_a[oc_idx * 80 + t_idx] <= max_val;

                            sub_t <= 2'd0;
                            k_idx <= 4'd0;
                            if (t_idx == 7'd79) begin
                                t_idx <= 7'd0;
                                if (oc_idx == 5'd7) begin
                                    oc_idx  <= 5'd0;
                                    ic_idx  <= 5'd0;
                                    mac_acc <= conv2_bias[0];
                                    state   <= ST_L2_CALC;
                                end else begin
                                    oc_idx  <= oc_idx + 5'd1;
                                    mac_acc <= conv1_bias[oc_idx + 1];
                                    state   <= ST_L1_CALC;
                                end
                            end else begin
                                t_idx   <= t_idx + 7'd1;
                                mac_acc <= conv1_bias[oc_idx];
                                state   <= ST_L1_CALC;
                            end
                        end
                    end
                end

                // Layer 2: Conv1D(8->16, k=5, p=2) -> ReLU -> MaxPool(2)
                ST_L2_CALC: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic signed [7:0] pos;
                        logic signed [7:0] in_val;
                        logic signed [7:0] w_val;
                        pos = $signed({1'b0, t_idx, 1'b0}) + $signed({6'b0, sub_t}) + $signed({4'b0, k_idx}) - 8'sd2;

                        if (pos < 0 || pos >= 80)
                            in_val = 8'sd0;
                        else
                            in_val = buf_a[ic_idx * 80 + pos];

                        w_val = rom_weights[W_OFF_CONV2 + oc_idx * 40 + ic_idx * 5 + k_idx];
                        mac_acc <= mac_acc + (in_val * w_val);

                        if (k_idx == 4'd4) begin
                            k_idx <= 4'd0;
                            if (ic_idx == 5'd7) begin
                                ic_idx <= 5'd0;
                                state  <= ST_L2_POOL;
                            end else begin
                                ic_idx <= ic_idx + 5'd1;
                            end
                        end else begin
                            k_idx <= k_idx + 4'd1;
                        end
                    end
                end

                ST_L2_POOL: begin
                    cycle_count <= cycle_count + 32'd1;
                    if (sub_t == 2'd0) begin
                        act_sub0 <= requant_relu(mac_acc, conv2_mult[oc_idx], conv2_shift[oc_idx], 1'b1);
                        sub_t    <= 2'd1;
                        ic_idx   <= 5'd0;
                        k_idx    <= 4'd0;
                        mac_acc  <= conv2_bias[oc_idx];
                        state    <= ST_L2_CALC;
                    end else begin
                        begin
                            logic signed [7:0] act1;
                            logic signed [7:0] max_val;
                            act1    = requant_relu(mac_acc, conv2_mult[oc_idx], conv2_shift[oc_idx], 1'b1);
                            max_val = (act1 > act_sub0) ? act1 : act_sub0;
                            buf_b[oc_idx * 40 + t_idx] <= max_val;

                            sub_t  <= 2'd0;
                            ic_idx <= 5'd0;
                            k_idx  <= 4'd0;
                            if (t_idx == 7'd39) begin
                                t_idx <= 7'd0;
                                if (oc_idx == 5'd15) begin
                                    oc_idx    <= 5'd0;
                                    gap_accum <= 32'd0;
                                    mac_acc   <= conv3_bias[0];
                                    state     <= ST_L3_CALC;
                                end else begin
                                    oc_idx  <= oc_idx + 5'd1;
                                    mac_acc <= conv2_bias[oc_idx + 1];
                                    state   <= ST_L2_CALC;
                                end
                            end else begin
                                t_idx   <= t_idx + 7'd1;
                                mac_acc <= conv2_bias[oc_idx];
                                state   <= ST_L2_CALC;
                            end
                        end
                    end
                end

                // Layer 3: Conv1D(16->16, k=3, p=1) -> ReLU -> GAP
                ST_L3_CALC: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic signed [6:0] pos;
                        logic signed [7:0] in_val;
                        logic signed [7:0] w_val;
                        pos = $signed({1'b0, t_idx}) + $signed({3'b0, k_idx}) - 7'sd1;

                        if (pos < 0 || pos >= 40)
                            in_val = 8'sd0;
                        else
                            in_val = buf_b[ic_idx * 40 + pos];

                        w_val = rom_weights[W_OFF_CONV3 + oc_idx * 48 + ic_idx * 3 + k_idx];
                        mac_acc <= mac_acc + (in_val * w_val);

                        if (k_idx == 4'd2) begin
                            k_idx <= 4'd0;
                            if (ic_idx == 5'd15) begin
                                ic_idx <= 5'd0;
                                state  <= ST_L3_GAP;
                            end else begin
                                ic_idx <= ic_idx + 5'd1;
                            end
                        end else begin
                            k_idx <= k_idx + 4'd1;
                        end
                    end
                end

                ST_L3_GAP: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic signed [7:0] act;
                        act = requant_relu(mac_acc, conv3_mult[oc_idx], conv3_shift[oc_idx], 1'b1);
                        gap_accum <= gap_accum + act;

                        if (t_idx == 7'd39) begin
                            t_idx <= 7'd0;
                            state <= ST_L3_AVG;
                        end else begin
                            t_idx   <= t_idx + 7'd1;
                            mac_acc <= conv3_bias[oc_idx];
                            state   <= ST_L3_CALC;
                        end
                    end
                end

                ST_L3_AVG: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic [31:0] avg;
                        avg = (gap_accum * 32'd52429 + 32'd1048576) >> 21;
                        gap_features[oc_idx] <= avg[7:0];
                        gap_accum <= 32'd0;

                        if (oc_idx == 5'd15) begin
                            oc_idx  <= 5'd0;
                            ic_idx  <= 5'd0;
                            mac_acc <= fc_bias[0];
                            state   <= ST_FC_CALC;
                        end else begin
                            oc_idx  <= oc_idx + 5'd1;
                            mac_acc <= conv3_bias[oc_idx + 1];
                            state   <= ST_L3_CALC;
                        end
                    end
                end

                // FC Linear: Linear(20 -> 2)
                ST_FC_CALC: begin
                    cycle_count <= cycle_count + 32'd1;
                    begin
                        logic signed [7:0] in_feat;
                        logic signed [7:0] w_val;
                        if (ic_idx < 5'd16)
                            in_feat = gap_features[ic_idx];
                        else if (ic_idx == 5'd16)
                            in_feat = feat_pre_rr;
                        else if (ic_idx == 5'd17)
                            in_feat = feat_qrs_width;
                        else if (ic_idx == 5'd18)
                            in_feat = feat_peak_ratio;
                        else
                            in_feat = feat_sqi;

                        w_val = rom_weights[W_OFF_FC + oc_idx * 20 + ic_idx];
                        mac_acc <= mac_acc + (in_feat * w_val);

                        if (ic_idx == 5'd19) begin
                            ic_idx <= 5'd0;
                            if (oc_idx == 5'd0) begin
                                logit_non_veb <= mac_acc + (in_feat * w_val);
                                oc_idx        <= 5'd1;
                                mac_acc       <= fc_bias[1];
                            end else begin
                                logit_veb <= mac_acc + (in_feat * w_val);
                                state     <= ST_DONE;
                            end
                        end else begin
                            ic_idx <= ic_idx + 5'd1;
                        end
                    end
                end

                ST_DONE: begin
                    busy       <= 1'b0;
                    done       <= 1'b1;
                    beat_class <= (logit_veb > logit_non_veb) ? 2'b01 : 2'b00;
                    state      <= ST_IDLE;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

endmodule
