`timescale 1ns / 1ps

// Narrow-I/O synthesis top.  It keeps the circular buffer, queue and serial
// read path observable without creating an unsafe board application.
module beat_window_buffer_microbench_top (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output reg        output_pulse,
    output reg [7:0]  signature,
    output wire [7:0] status
);

    reg [31:0] generated_index;
    wire signed [15:0] generated_sample = $signed(generated_index[15:0] ^ 16'hA55A);
    wire generated_qrs = enable && (generated_index[7:0] == 8'd64);

    wire window_valid;
    wire signed [15:0] window_data;
    wire [7:0] window_point_index;
    wire [31:0] window_sample_index;
    wire [31:0] window_r_sample_index;
    wire window_start;
    wire window_center;
    wire window_done;
    wire missing_sticky;
    wire duplicate_sticky;
    wire out_of_order_sticky;
    wire overflow_sticky;
    wire stale_sticky;
    wire qrs_error_sticky;
    wire [2:0] pending_count;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            generated_index <= 32'd0;
            output_pulse <= 1'b0;
            signature <= 8'd0;
        end else begin
            output_pulse <= window_done;
            if (enable)
                generated_index <= generated_index + 1'b1;
            if (window_valid) begin
                signature <= signature ^ window_data[7:0] ^ window_point_index ^
                             window_sample_index[7:0] ^ window_r_sample_index[7:0] ^
                             {5'd0, window_start, window_center, window_done};
            end
        end
    end

    assign status = {
        qrs_error_sticky,
        stale_sticky,
        overflow_sticky,
        out_of_order_sticky,
        duplicate_sticky,
        missing_sticky,
        (pending_count != 0),
        window_valid
    };

    beat_window_buffer #(
        .SAMPLE_WIDTH  (16),
        .INDEX_WIDTH   (32),
        .RAM_DEPTH     (512),
        .PENDING_DEPTH (4),
        .COUNTER_WIDTH (32)
    ) u_window_buffer (
        .clk                        (clk),
        .rst_n                      (rst_n),
        .sample_data                (generated_sample),
        .sample_index               (generated_index),
        .sample_valid               (enable),
        .qrs_sample_index           (generated_index),
        .qrs_valid                  (generated_qrs),
        .window_valid               (window_valid),
        .window_data                (window_data),
        .window_point_index         (window_point_index),
        .window_sample_index        (window_sample_index),
        .window_r_sample_index      (window_r_sample_index),
        .window_start               (window_start),
        .window_center              (window_center),
        .window_done                (window_done),
        .missing_sample_sticky      (missing_sticky),
        .duplicate_sample_sticky    (duplicate_sticky),
        .out_of_order_sample_sticky (out_of_order_sticky),
        .queue_overflow_sticky      (overflow_sticky),
        .stale_window_sticky        (stale_sticky),
        .qrs_reference_error_sticky (qrs_error_sticky),
        .missing_sample_count       (),
        .duplicate_sample_count     (),
        .out_of_order_sample_count  (),
        .warmup_drop_count          (),
        .queue_overflow_count       (),
        .stale_window_count         (),
        .qrs_reference_error_count  (),
        .pending_count              (pending_count)
    );

endmodule
