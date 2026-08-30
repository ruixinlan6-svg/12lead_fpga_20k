`timescale 1ns/1ps

// Scheme B: Layer Weight DMA Controller (Cycle-Exact 1-cycle BSRAM Pipeline)
// Streams layer weights and biases from storage RAM into on-chip WeightBuf cache.

module sdram_layer_dma (
    input  wire        clk,
    input  wire        rst_n,

    // Command Interface
    input  wire        dma_start,
    input  wire [2:0]  dma_mode, // 1: L1(1344W+16B), 2: L2(3584W+32B), 3: L3(5120W+32B), 4: Head(160W+5B)
    output reg         dma_done,

    // Storage RAM Read Interface
    output reg         storage_rd_en,
    output reg  [13:0] storage_rd_addr,
    input  wire signed [7:0] storage_rd_data,

    // Core Memory Write Interface
    output reg         dma_w_en,
    output reg  [12:0] dma_w_addr,
    output wire signed [7:0] dma_w_data,
    output reg         dma_b_en,
    output reg  [5:0]  dma_b_addr,
    output wire signed [7:0] dma_b_data,
    output reg         dma_in_en,
    output reg  [13:0] dma_in_addr,
    output reg  signed [7:0] dma_in_data
);

    // Direct combinational data bus from synchronous read port
    assign dma_w_data = storage_rd_data;
    assign dma_b_data = storage_rd_data;

    // Exact byte base offsets
    localparam [13:0] L1_W_BASE = 14'd0;
    localparam [13:0] L1_B_BASE = 14'd1344;
    localparam [13:0] L2_W_BASE = 14'd1360;
    localparam [13:0] L2_B_BASE = 14'd4944;
    localparam [13:0] L3_W_BASE = 14'd4976;
    localparam [13:0] L3_B_BASE = 14'd10096;
    localparam [13:0] H_W_BASE  = 14'd10128;
    localparam [13:0] H_B_BASE  = 14'd10288;

    localparam [2:0]
        ST_IDLE   = 3'd0,
        ST_PIPE_W = 3'd1,
        ST_PIPE_B = 3'd2,
        ST_DONE   = 3'd3;

    reg [2:0]  state;
    reg [12:0] w_bytes_total;
    reg [12:0] w_rd_cnt;
    reg [12:0] w_wr_cnt;
    reg [5:0]  b_bytes_total;
    reg [5:0]  b_rd_cnt;
    reg [5:0]  b_wr_cnt;
    reg [13:0] base_w_addr;
    reg [13:0] base_b_addr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= ST_IDLE;
            dma_done        <= 1'b0;
            storage_rd_en   <= 1'b0;
            storage_rd_addr <= 14'd0;
            dma_w_en        <= 1'b0;
            dma_w_addr      <= 13'd0;
            dma_b_en        <= 1'b0;
            dma_b_addr      <= 6'd0;
            dma_in_en       <= 1'b0;
            dma_in_addr     <= 14'd0;
            dma_in_data     <= 8'd0;
            w_bytes_total   <= 13'd0;
            w_rd_cnt        <= 13'd0;
            w_wr_cnt        <= 13'd0;
            b_bytes_total   <= 6'd0;
            b_rd_cnt        <= 6'd0;
            b_wr_cnt        <= 6'd0;
            base_w_addr     <= 14'd0;
            base_b_addr     <= 14'd0;
        end else begin
            dma_done      <= 1'b0;
            dma_w_en      <= 1'b0;
            dma_b_en      <= 1'b0;
            storage_rd_en <= 1'b1;

            case (state)
                ST_IDLE: begin
                    storage_rd_en <= 1'b0;
                    if (dma_start) begin
                        storage_rd_en <= 1'b1;
                        w_rd_cnt      <= 13'd0;
                        w_wr_cnt      <= 13'd0;
                        b_rd_cnt      <= 6'd0;
                        b_wr_cnt      <= 6'd0;
                        case (dma_mode)
                            3'd1: begin
                                base_w_addr     <= L1_W_BASE;
                                base_b_addr     <= L1_B_BASE;
                                w_bytes_total   <= 13'd1344;
                                b_bytes_total   <= 6'd16;
                                storage_rd_addr <= L1_W_BASE;
                                state           <= ST_PIPE_W;
                            end
                            3'd2: begin
                                base_w_addr     <= L2_W_BASE;
                                base_b_addr     <= L2_B_BASE;
                                w_bytes_total   <= 13'd3584;
                                b_bytes_total   <= 6'd32;
                                storage_rd_addr <= L2_W_BASE;
                                state           <= ST_PIPE_W;
                            end
                            3'd3: begin
                                base_w_addr     <= L3_W_BASE;
                                base_b_addr     <= L3_B_BASE;
                                w_bytes_total   <= 13'd5120;
                                b_bytes_total   <= 6'd32;
                                storage_rd_addr <= L3_W_BASE;
                                state           <= ST_PIPE_W;
                            end
                            3'd4: begin
                                base_w_addr     <= H_W_BASE;
                                base_b_addr     <= H_B_BASE;
                                w_bytes_total   <= 13'd160;
                                b_bytes_total   <= 6'd5;
                                storage_rd_addr <= H_W_BASE;
                                state           <= ST_PIPE_W;
                            end
                            default: state <= ST_IDLE;
                        endcase
                    end
                end

                ST_PIPE_W: begin
                    // Read stage
                    if (w_rd_cnt + 1 < w_bytes_total) begin
                        w_rd_cnt        <= w_rd_cnt + 1'b1;
                        storage_rd_addr <= base_w_addr + w_rd_cnt + 1'b1;
                    end else begin
                        storage_rd_addr <= base_b_addr; // Prefetch first bias byte
                    end

                    // Write stage
                    dma_w_en   <= 1'b1;
                    dma_w_addr <= w_wr_cnt;
                    if (w_wr_cnt + 1 < w_bytes_total) begin
                        w_wr_cnt <= w_wr_cnt + 1'b1;
                    end else begin
                        b_rd_cnt <= 6'd0;
                        b_wr_cnt <= 6'd0;
                        state    <= ST_PIPE_B;
                    end
                end

                ST_PIPE_B: begin
                    // Read stage
                    if (b_rd_cnt + 1 < b_bytes_total) begin
                        b_rd_cnt        <= b_rd_cnt + 1'b1;
                        storage_rd_addr <= base_b_addr + b_rd_cnt + 1'b1;
                    end

                    // Write stage
                    dma_b_en   <= 1'b1;
                    dma_b_addr <= b_wr_cnt;
                    if (b_wr_cnt + 1 < b_bytes_total) begin
                        b_wr_cnt <= b_wr_cnt + 1'b1;
                    end else begin
                        state <= ST_DONE;
                    end
                end

                ST_DONE: begin
                    storage_rd_en <= 1'b0;
                    dma_done      <= 1'b1;
                    state         <= ST_IDLE;
                end
            endcase
        end
    end

endmodule