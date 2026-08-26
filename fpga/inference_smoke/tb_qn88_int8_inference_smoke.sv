`timescale 1ns/1ps

module tb_qn88_int8_inference_smoke;
    reg clk = 1'b0;
    reg rst_btn = 1'b1;
    wire [5:0] led;

    qn88_int8_inference_smoke dut (
        .clk(clk), .rst_btn(rst_btn), .led(led)
    );

    always #5 clk = ~clk;

    initial begin
        #20;
        rst_btn = 1'b0;
        repeat (100) @(posedge clk);
        if (led[1] !== 1'b0 || led[2] !== 1'b1) begin
            $display("FAIL: led=%b state=%0d mac_result=%0d quantized=%0d", led, dut.state, dut.mac_result, dut.quantized);
            $fatal(1);
        end
        $display("PASS: known vector dot=240 requantized=120 led=%b", led);
        $finish;
    end
endmodule
