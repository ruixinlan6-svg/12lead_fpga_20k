`timescale 1ns/1ps

module weight_init_rom (
    input  wire        clk,
    input  wire [11:0] addr,
    output reg  [31:0] dout
);
    reg [31:0] mem [0:2573];

    initial begin
        $readmemh("D:/project/gowin_project/0_fpga_test/test3/fpga/scheme_b/sdram_weights_init.hex", mem);
    end

    always @(posedge clk) begin
        dout <= mem[addr];
    end
endmodule