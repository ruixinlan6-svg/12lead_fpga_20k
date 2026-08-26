// Behavioral SDRAM user-interface model for QN88 wrapper simulation.
// It emulates the accepted data_len=25 contract: a low write/read request
// edge is followed by 25 payload beats/valid read pulses.
module qn88_sdram_controller (
    output wire O_sdram_clk, output wire O_sdram_cke,
    output wire O_sdram_cs_n, output wire O_sdram_cas_n,
    output wire O_sdram_ras_n, output wire O_sdram_wen_n,
    output wire [3:0] O_sdram_dqm, output wire [10:0] O_sdram_addr,
    output wire [1:0] O_sdram_ba, inout wire [31:0] IO_sdram_dq,
    input wire I_sdrc_rst_n, input wire I_sdrc_clk, input wire I_sdram_clk,
    input wire I_sdrc_selfrefresh, input wire I_sdrc_power_down,
    input wire I_sdrc_wr_n, input wire I_sdrc_rd_n,
    input wire [20:0] I_sdrc_addr, input wire [7:0] I_sdrc_data_len,
    input wire [3:0] I_sdrc_dqm, input wire [31:0] I_sdrc_data,
    output wire [31:0] O_sdrc_data, output wire O_sdrc_init_done,
    output wire O_sdrc_busy_n, output wire O_sdrc_rd_valid,
    output wire O_sdrc_wrd_ack
);
    reg [31:0] mem [0:2573];
    reg write_active, read_active;
    reg [5:0] write_count, read_count;
    reg [12:0] next_base, active_base, read_base;

    always @(posedge I_sdrc_clk or negedge I_sdrc_rst_n) begin
        if (!I_sdrc_rst_n) begin
            write_active <= 1'b0;
            read_active <= 1'b0;
            write_count <= 0;
            read_count <= 0;
            next_base <= 0;
            active_base <= 0;
            read_base <= 0;
        end else begin
            if (!write_active && !read_active) begin
                if (!I_sdrc_wr_n) begin
                    write_active <= 1'b1;
                    write_count <= 0;
                    active_base <= next_base;
                end else if (!I_sdrc_rd_n) begin
                    read_active <= 1'b1;
                    read_count <= 0;
                end
            end else if (write_active) begin
                if (write_count < 25) begin
                    mem[active_base + write_count] <= I_sdrc_data;
                    write_count <= write_count + 1'b1;
                end else begin
                    write_active <= 1'b0;
                    next_base <= next_base + 25;
                    read_base <= active_base;
                end
            end else if (read_active) begin
                if (read_count < 25)
                    read_count <= read_count + 1'b1;
                else
                    read_active <= 1'b0;
            end
        end
    end

    assign O_sdram_clk = I_sdram_clk;
    assign O_sdram_cke = 1'b1;
    assign O_sdram_cs_n = 1'b1;
    assign O_sdram_cas_n = 1'b1;
    assign O_sdram_ras_n = 1'b1;
    assign O_sdram_wen_n = 1'b1;
    assign O_sdram_dqm = 4'd0;
    assign O_sdram_addr = 11'd0;
    assign O_sdram_ba = 2'd0;
    assign IO_sdram_dq = 32'bz;
    assign O_sdrc_init_done = I_sdrc_rst_n;
    assign O_sdrc_busy_n = !(write_active || read_active);
    assign O_sdrc_rd_valid = read_active && (read_count < 25);
    assign O_sdrc_data = mem[read_base + read_count];
    assign O_sdrc_wrd_ack = write_active && (write_count < 25);
endmodule
