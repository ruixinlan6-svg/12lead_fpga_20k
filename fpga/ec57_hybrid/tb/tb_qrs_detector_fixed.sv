`timescale 1ns / 1ps

module tb_qrs_detector_fixed;

    reg         clk;
    reg         rst_n;
    reg         sample_valid;
    reg  signed [15:0] filt_sample;
    reg  [31:0] sample_time_ms;

    wire        qrs_valid;
    wire [31:0] qrs_time_ms;
    wire [15:0] rr_interval_ms;
    wire [7:0]  hr_bpm;
    wire        hr_valid;

    integer qrs_count = 0;
    integer s;

    qrs_detector_fixed uut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .filt_sample(filt_sample),
        .sample_time_ms(sample_time_ms),
        .qrs_valid(qrs_valid),
        .qrs_time_ms(qrs_time_ms),
        .rr_interval_ms(rr_interval_ms),
        .hr_bpm(hr_bpm),
        .hr_valid(hr_valid)
    );

    // 27 MHz clock
    always #18.5 clk = ~clk;

    // Asynchronous QRS monitor
    always @(posedge clk) begin
        if (qrs_valid) begin
            qrs_count <= qrs_count + 1;
            $display("[QRS DETECTED] #%0d at %0d ms, RR=%0d ms, HR=%0d bpm", qrs_count + 1, qrs_time_ms, rr_interval_ms, hr_bpm);
        end
    end

    task send_sample(input signed [15:0] s_in, input [31:0] t_ms);
    begin
        @(posedge clk);
        sample_valid   <= 1'b1;
        filt_sample    <= s_in;
        sample_time_ms <= t_ms;
        @(posedge clk);
        sample_valid   <= 1'b0;
        repeat (4) @(posedge clk); // Allow pipeline to process
    end
    endtask

    initial begin
        clk = 0;
        rst_n = 0;
        sample_valid = 0;
        filt_sample = 0;
        sample_time_ms = 0;

        #100;
        @(posedge clk);
        rst_n = 1;
        #100;

        $display("=== Generating Synthetic ECG Stream with 5 QRS Pulses (every 800 ms = 75 bpm) ===");

        for (s = 0; s < 1250; s = s + 1) begin
            integer t_ms;
            integer val;

            t_ms = s * 4; // 4 ms per sample
            val = 0;

            if (t_ms >= 980 && t_ms <= 1020)
                val = 2000 - (t_ms > 1000 ? (t_ms - 1000) * 100 : (1000 - t_ms) * 100);
            else if (t_ms >= 1780 && t_ms <= 1820)
                val = 2000 - (t_ms > 1800 ? (t_ms - 1800) * 100 : (1800 - t_ms) * 100);
            else if (t_ms >= 2580 && t_ms <= 2620)
                val = 2000 - (t_ms > 2600 ? (t_ms - 2600) * 100 : (2600 - t_ms) * 100);
            else if (t_ms >= 3380 && t_ms <= 3420)
                val = 2000 - (t_ms > 3400 ? (t_ms - 3400) * 100 : (3400 - t_ms) * 100);
            else if (t_ms >= 4180 && t_ms <= 4220)
                val = 2000 - (t_ms > 4200 ? (t_ms - 4200) * 100 : (4200 - t_ms) * 100);

            send_sample(val[15:0], t_ms[31:0]);
        end

        #200;
        if (qrs_count >= 4) begin
            $display("=================================================");
            $display(">>> ALL QRS DETECTOR TESTS PASSED (%0d QRS) <<<", qrs_count);
            $display("=================================================");
            $finish(0);
        end else begin
            $fatal(1, "QRS Detector failed to detect expected QRS complexes! Count = %0d", qrs_count);
        end
    end

endmodule
