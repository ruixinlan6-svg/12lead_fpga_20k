module qn88_sdram_controller (
    output wire O_sdram_clk,
    output wire O_sdram_cke,
    output wire O_sdram_cs_n,
    output wire O_sdram_cas_n,
    output wire O_sdram_ras_n,
    output wire O_sdram_wen_n,
    output wire [1:0] O_sdram_dqm,
    output wire [10:0] O_sdram_addr,
    output wire [1:0] O_sdram_ba,
    inout  wire [31:0] IO_sdram_dq,
    input  wire I_sdrc_rst_n,
    input  wire I_sdrc_clk,
    input  wire I_sdram_clk,
    input  wire I_sdrc_selfrefresh,
    input  wire I_sdrc_power_down,
    input  wire I_sdrc_wr_n,
    input  wire I_sdrc_rd_n,
    input  wire [20:0] I_sdrc_addr,
    input  wire [7:0] I_sdrc_data_len,
    input  wire [3:0] I_sdrc_dqm,
    input  wire [31:0] I_sdrc_data,
    output wire [31:0] O_sdrc_data,
    output wire O_sdrc_init_done,
    output wire O_sdrc_busy_n,
    output wire O_sdrc_rd_valid,
    output wire O_sdrc_wrd_ack
);
    assign O_sdrc_init_done = 1'b1;
    assign O_sdrc_busy_n = 1'b1;
    assign O_sdrc_rd_valid = 1'b0;
    assign O_sdrc_wrd_ack = 1'b0;
    assign O_sdrc_data = 32'd0;
endmodule