`timescale 1ns / 1ps

// Circular selected-lead sample buffer and deterministic 160-point beat window
// extractor.  Sample storage uses the project's pure synchronous SDPB wrapper;
// only the small pending-R control queue is implemented as registers.
module beat_window_buffer #(
    parameter int SAMPLE_WIDTH  = 16,
    parameter int INDEX_WIDTH   = 32,
    parameter int RAM_DEPTH     = 512,
    parameter int PENDING_DEPTH = 4,
    parameter int COUNTER_WIDTH = 32,
    parameter int RAM_ADDR_WIDTH = (RAM_DEPTH > 1) ? $clog2(RAM_DEPTH) : 1,
    parameter int PENDING_PTR_WIDTH = (PENDING_DEPTH > 1) ? $clog2(PENDING_DEPTH) : 1,
    parameter int PENDING_COUNT_WIDTH = $clog2(PENDING_DEPTH + 1)
)(
    input  wire                           clk,
    input  wire                           rst_n,
    input  wire signed [SAMPLE_WIDTH-1:0] sample_data,
    input  wire        [INDEX_WIDTH-1:0]  sample_index,
    input  wire                           sample_valid,
    input  wire        [INDEX_WIDTH-1:0]  qrs_sample_index,
    input  wire                           qrs_valid,

    output reg                            window_valid,
    output reg signed [SAMPLE_WIDTH-1:0]  window_data,
    output reg         [7:0]              window_point_index,
    output reg         [INDEX_WIDTH-1:0]  window_sample_index,
    output reg         [INDEX_WIDTH-1:0]  window_r_sample_index,
    output reg                            window_start,
    output reg                            window_center,
    output reg                            window_done,

    output reg missing_sample_sticky,
    output reg duplicate_sample_sticky,
    output reg out_of_order_sample_sticky,
    output reg queue_overflow_sticky,
    output reg stale_window_sticky,
    output reg qrs_reference_error_sticky,
    output reg [COUNTER_WIDTH-1:0] missing_sample_count,
    output reg [COUNTER_WIDTH-1:0] duplicate_sample_count,
    output reg [COUNTER_WIDTH-1:0] out_of_order_sample_count,
    output reg [COUNTER_WIDTH-1:0] warmup_drop_count,
    output reg [COUNTER_WIDTH-1:0] queue_overflow_count,
    output reg [COUNTER_WIDTH-1:0] stale_window_count,
    output reg [COUNTER_WIDTH-1:0] qrs_reference_error_count,
    output reg [PENDING_COUNT_WIDTH-1:0] pending_count
);

    localparam [INDEX_WIDTH-1:0] PRE_SAMPLES  = 64;
    localparam [INDEX_WIDTH-1:0] POST_SAMPLES = 95;
    localparam [INDEX_WIDTH-1:0] LAST_POINT   = 159;

    // synthesis translate_off
    initial begin
        if (RAM_DEPTH < 256 || (RAM_DEPTH & (RAM_DEPTH - 1)) != 0)
            $fatal(1, "RAM_DEPTH must be a power of two and at least 256");
        if (PENDING_DEPTH < 4)
            $fatal(1, "PENDING_DEPTH must be at least four");
    end
    // synthesis translate_on

    function automatic [PENDING_PTR_WIDTH-1:0] next_pending_ptr(
        input [PENDING_PTR_WIDTH-1:0] pointer
    );
        if (pointer == PENDING_DEPTH - 1)
            next_pending_ptr = '0;
        else
            next_pending_ptr = pointer + 1'b1;
    endfunction

    reg [INDEX_WIDTH-1:0] pending_r [0:PENDING_DEPTH-1];
    reg [PENDING_PTR_WIDTH-1:0] pending_head;
    reg [PENDING_PTR_WIDTH-1:0] pending_tail;

    reg have_previous_sample;
    reg [INDEX_WIDTH-1:0] last_sample_index;
    reg [INDEX_WIDTH-1:0] segment_start_index;

    reg read_active;
    reg [7:0] issue_point;
    reg [INDEX_WIDTH-1:0] active_r_index;
    reg read_valid_q;
    reg [7:0] read_point_q;
    reg [INDEX_WIDTH-1:0] read_sample_index_q;
    reg [INDEX_WIDTH-1:0] read_r_index_q;

    wire [RAM_ADDR_WIDTH-1:0] ram_wr_addr = sample_index[RAM_ADDR_WIDTH-1:0];
    wire [INDEX_WIDTH-1:0] ram_rd_index = active_r_index - PRE_SAMPLES + issue_point;
    wire [RAM_ADDR_WIDTH-1:0] ram_rd_addr = ram_rd_index[RAM_ADDR_WIDTH-1:0];
    wire signed [SAMPLE_WIDTH-1:0] ram_rd_data;

    ecg_sync_dp_ram #(
        .DATA_WIDTH (SAMPLE_WIDTH),
        .DEPTH      (RAM_DEPTH),
        .ADDR_WIDTH (RAM_ADDR_WIDTH)
    ) u_sample_ring (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (sample_valid),
        .wr_addr (ram_wr_addr),
        .wr_data (sample_data),
        .rd_en   (read_active),
        .rd_addr (ram_rd_addr),
        .rd_data (ram_rd_data)
    );

    wire sequence_duplicate = sample_valid && have_previous_sample &&
                              (sample_index == last_sample_index);
    wire sequence_out_of_order = sample_valid && have_previous_sample &&
                                 (sample_index < last_sample_index);
    wire sequence_missing = sample_valid && have_previous_sample &&
                            (sample_index > last_sample_index + 1'b1);
    wire sequence_error = sequence_duplicate | sequence_out_of_order | sequence_missing;

    wire [INDEX_WIDTH-1:0] latest_sample_index =
        sample_valid ? sample_index : last_sample_index;
    wire history_available = have_previous_sample | sample_valid;
    wire [INDEX_WIDTH-1:0] latest_segment_start_index =
        have_previous_sample ? segment_start_index : sample_index;
    wire head_present = (pending_count != 0);
    wire [INDEX_WIDTH-1:0] head_r_index = pending_r[pending_head];
    wire head_ready = head_present && have_previous_sample &&
                      (latest_sample_index >= head_r_index + POST_SAMPLES);
    wire head_stale = head_ready &&
                      ((latest_sample_index - (head_r_index - PRE_SAMPLES)) >= RAM_DEPTH);
    wire output_pipeline_busy = read_active | read_valid_q;
    wire drop_stale_head = !sequence_error && !output_pipeline_busy && head_stale;
    wire start_head = !sequence_error && !output_pipeline_busy && head_ready && !head_stale;
    wire pop_head = drop_stale_head | start_head;

    wire qrs_after_current = qrs_valid &&
                             (!history_available ||
                              (qrs_sample_index > latest_sample_index));
    wire qrs_before_segment = qrs_valid && history_available &&
                              (qrs_sample_index < latest_segment_start_index);
    wire qrs_warmup = qrs_valid && !qrs_after_current && !qrs_before_segment &&
                       ((qrs_sample_index < PRE_SAMPLES) ||
                        (qrs_sample_index - latest_segment_start_index < PRE_SAMPLES));
    wire qrs_too_old = qrs_valid && !qrs_after_current && !qrs_before_segment &&
                       !qrs_warmup && history_available &&
                       ((latest_sample_index - (qrs_sample_index - PRE_SAMPLES)) >= RAM_DEPTH);
    wire enqueue_candidate = qrs_valid && history_available && !sequence_error &&
                              !qrs_after_current && !qrs_before_segment &&
                              !qrs_warmup && !qrs_too_old;
    wire queue_has_room = (pending_count < PENDING_DEPTH) || pop_head;
    wire enqueue_qrs = enqueue_candidate && queue_has_room;
    wire overflow_qrs = enqueue_candidate && !queue_has_room;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_head <= '0;
            pending_tail <= '0;
            pending_count <= '0;
            have_previous_sample <= 1'b0;
            last_sample_index <= '0;
            segment_start_index <= '0;

            read_active <= 1'b0;
            issue_point <= 8'd0;
            active_r_index <= '0;
            read_valid_q <= 1'b0;
            read_point_q <= 8'd0;
            read_sample_index_q <= '0;
            read_r_index_q <= '0;

            window_valid <= 1'b0;
            window_data <= '0;
            window_point_index <= 8'd0;
            window_sample_index <= '0;
            window_r_sample_index <= '0;
            window_start <= 1'b0;
            window_center <= 1'b0;
            window_done <= 1'b0;

            missing_sample_sticky <= 1'b0;
            duplicate_sample_sticky <= 1'b0;
            out_of_order_sample_sticky <= 1'b0;
            queue_overflow_sticky <= 1'b0;
            stale_window_sticky <= 1'b0;
            qrs_reference_error_sticky <= 1'b0;
            missing_sample_count <= '0;
            duplicate_sample_count <= '0;
            out_of_order_sample_count <= '0;
            warmup_drop_count <= '0;
            queue_overflow_count <= '0;
            stale_window_count <= '0;
            qrs_reference_error_count <= '0;
        end else begin
            window_valid <= read_valid_q;
            window_start <= 1'b0;
            window_center <= 1'b0;
            window_done <= 1'b0;
            if (read_valid_q) begin
                window_data <= ram_rd_data;
                window_point_index <= read_point_q;
                window_sample_index <= read_sample_index_q;
                window_r_sample_index <= read_r_index_q;
                window_start <= (read_point_q == 8'd0);
                window_center <= (read_point_q == 8'd64);
                window_done <= (read_point_q == 8'd159);
            end

            read_valid_q <= read_active;
            if (read_active) begin
                read_point_q <= issue_point;
                read_sample_index_q <= active_r_index - PRE_SAMPLES + issue_point;
                read_r_index_q <= active_r_index;
                if (issue_point == LAST_POINT[7:0]) begin
                    read_active <= 1'b0;
                    issue_point <= 8'd0;
                end else begin
                    issue_point <= issue_point + 1'b1;
                end
            end

            if (sample_valid) begin
                if (!have_previous_sample) begin
                    have_previous_sample <= 1'b1;
                    segment_start_index <= sample_index;
                end else if (sequence_error) begin
                    segment_start_index <= sample_index;
                end
                last_sample_index <= sample_index;
            end

            if (sequence_error) begin
                if (sequence_missing) begin
                    missing_sample_sticky <= 1'b1;
                    missing_sample_count <= missing_sample_count + 1'b1;
                end
                if (sequence_duplicate) begin
                    duplicate_sample_sticky <= 1'b1;
                    duplicate_sample_count <= duplicate_sample_count + 1'b1;
                end
                if (sequence_out_of_order) begin
                    out_of_order_sample_sticky <= 1'b1;
                    out_of_order_sample_count <= out_of_order_sample_count + 1'b1;
                end
                pending_head <= '0;
                pending_tail <= '0;
                pending_count <= '0;
                read_active <= 1'b0;
                read_valid_q <= 1'b0;
                issue_point <= 8'd0;
                window_valid <= 1'b0;
                window_start <= 1'b0;
                window_center <= 1'b0;
                window_done <= 1'b0;
            end else begin
                if (qrs_after_current || qrs_before_segment) begin
                    qrs_reference_error_sticky <= 1'b1;
                    qrs_reference_error_count <= qrs_reference_error_count + 1'b1;
                end else if (qrs_warmup) begin
                    warmup_drop_count <= warmup_drop_count + 1'b1;
                end else if (qrs_too_old) begin
                    stale_window_sticky <= 1'b1;
                    stale_window_count <= stale_window_count + 1'b1;
                end else if (overflow_qrs) begin
                    queue_overflow_sticky <= 1'b1;
                    queue_overflow_count <= queue_overflow_count + 1'b1;
                end

                if (pop_head) begin
                    pending_head <= next_pending_ptr(pending_head);
                    if (start_head) begin
                        active_r_index <= head_r_index;
                        issue_point <= 8'd0;
                        read_active <= 1'b1;
                    end
                    if (drop_stale_head) begin
                        stale_window_sticky <= 1'b1;
                        stale_window_count <= stale_window_count + 1'b1;
                    end
                end
                if (enqueue_qrs) begin
                    pending_r[pending_tail] <= qrs_sample_index;
                    pending_tail <= next_pending_ptr(pending_tail);
                end
                case ({enqueue_qrs, pop_head})
                    2'b10: pending_count <= pending_count + 1'b1;
                    2'b01: pending_count <= pending_count - 1'b1;
                    default: pending_count <= pending_count;
                endcase
            end
        end
    end

endmodule
