`timescale 1ns / 1ps

module tb_nv_cnn_core;

    reg         clk;
    reg         rst_n;
    reg         start;
    wire        busy;
    wire        done;

    reg         wave_wr_valid;
    reg  [7:0]  wave_wr_addr;
    reg  signed [7:0] wave_wr_data;

    reg  signed [7:0] feat_pre_rr;
    reg  signed [7:0] feat_qrs_width;
    reg  signed [7:0] feat_peak_ratio;
    reg  signed [7:0] feat_sqi;

    wire signed [31:0] logit_non_veb;
    wire signed [31:0] logit_veb;
    wire [1:0]         beat_class;
    wire [31:0]        cycle_count;

    // Test vector memories (16 beats)
    reg [7:0]  tb_waves   [0:16*160 - 1];
    reg [7:0]  tb_feats   [0:16*4 - 1];
    reg [31:0] tb_logits  [0:16*2 - 1];
    reg [7:0]  tb_classes [0:15];

    integer beat_idx;
    integer t;
    integer err_count = 0;

    nv_cnn_core #(
        .WEIGHTS_HEX_FILE("fpga/ec57_hybrid/bundle/weights_int8.hex"),
        .PARAMS_HEX_FILE("fpga/ec57_hybrid/bundle/params_int32.hex")
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .busy(busy),
        .done(done),
        .wave_wr_valid(wave_wr_valid),
        .wave_wr_addr(wave_wr_addr),
        .wave_wr_data(wave_wr_data),
        .feat_pre_rr(feat_pre_rr),
        .feat_qrs_width(feat_qrs_width),
        .feat_peak_ratio(feat_peak_ratio),
        .feat_sqi(feat_sqi),
        .logit_non_veb(logit_non_veb),
        .logit_veb(logit_veb),
        .beat_class(beat_class),
        .cycle_count(cycle_count)
    );

    // 27 MHz clock (~37.037 ns period)
    always #18.518 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        start = 0;
        beat_idx = 0;
        wave_wr_valid = 0;
        wave_wr_addr = 0;
        wave_wr_data = 0;
        feat_pre_rr = 0;
        feat_qrs_width = 0;
        feat_peak_ratio = 0;
        feat_sqi = 0;

        // Load test vectors
        $readmemh("fpga/ec57_hybrid/tb/vectors/tb_waves.hex", tb_waves);
        $readmemh("fpga/ec57_hybrid/tb/vectors/tb_feats.hex", tb_feats);
        $readmemh("fpga/ec57_hybrid/tb/vectors/tb_logits.hex", tb_logits);
        $readmemh("fpga/ec57_hybrid/tb/vectors/tb_classes.hex", tb_classes);

        #100;
        @(posedge clk);
        rst_n = 1;
        #100;

        $display("=================================================================");
        $display(">>> STARTING INT8 CNN HARDWARE ACCELERATOR BIT-EXACT TEST <<<");
        $display("=================================================================");

        for (beat_idx = 0; beat_idx < 16; beat_idx = beat_idx + 1) begin
            feat_pre_rr     = $signed(tb_feats[beat_idx * 4 + 0]);
            feat_qrs_width  = $signed(tb_feats[beat_idx * 4 + 1]);
            feat_peak_ratio = $signed(tb_feats[beat_idx * 4 + 2]);
            feat_sqi        = $signed(tb_feats[beat_idx * 4 + 3]);

            // Stream 160 waveform samples
            for (t = 0; t < 160; t = t + 1) begin
                @(posedge clk);
                wave_wr_valid <= 1'b1;
                wave_wr_addr  <= t[7:0];
                wave_wr_data  <= $signed(tb_waves[beat_idx * 160 + t]);
            end

            @(posedge clk);
            wave_wr_valid <= 1'b0;
            start         <= 1'b1;
            @(posedge clk);
            start         <= 1'b0;

            // Wait for inference completion
            @(posedge done);
            #1;

            // Verify Logits & Class
            begin
                logic signed [31:0] exp_l0;
                logic signed [31:0] exp_l1;
                logic [1:0]         exp_cls;

                exp_l0 = $signed(tb_logits[beat_idx * 2 + 0]);
                exp_l1 = $signed(tb_logits[beat_idx * 2 + 1]);
                exp_cls = (tb_classes[beat_idx] == 8'd1) ? 2'b01 : 2'b00;

                if (logit_non_veb === exp_l0 && logit_veb === exp_l1 && beat_class === exp_cls) begin
                    $display("[PASS] Beat #%02d: Non-VEB=%d, VEB=%d, Class=%b, Cycles=%0d (Exact Match)",
                             beat_idx, logit_non_veb, logit_veb, beat_class, cycle_count);
                end else begin
                    $display("[FAIL] Beat #%02d Mismatch!", beat_idx);
                    $display("       Expected: Non-VEB=%d, VEB=%d, Class=%b", exp_l0, exp_l1, exp_cls);
                    $display("       Actual:   Non-VEB=%d, VEB=%d, Class=%b", logit_non_veb, logit_veb, beat_class);
                    err_count = err_count + 1;
                end
            end

            @(posedge clk);
        end

        $display("=================================================================");
        if (err_count == 0) begin
            $display(">>> ALL 16 GOLDEN BEATS PASSED (BIT-EXACT MATCH, 0 ERRORS) <<<");
            $display("=================================================================");
            $finish(0);
        end else begin
            $fatal(1, "CNN Core test failed with %0d errors!", err_count);
        end
    end

endmodule
