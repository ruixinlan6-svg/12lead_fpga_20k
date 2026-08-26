`timescale 1ns/1ps
module tb_conv1d_mac_int8;
    logic clk, rst_n, start, in_valid, in_last;
    logic signed [7:0] activation, weight;
    logic busy, done;
    logic signed [31:0] result;
    integer failures;

    conv1d_mac_int8 dut(.*);

    always #5 clk = ~clk;

    task automatic send_pair(input integer a, input integer w, input bit last);
        begin
            @(negedge clk);
            activation = a; weight = w; in_last = last; in_valid = 1'b1;
            @(negedge clk);
            in_valid = 1'b0; in_last = 1'b0;
        end
    endtask

    initial begin
        clk = 0; rst_n = 0; start = 0; in_valid = 0; in_last = 0; activation = 0; weight = 0; failures = 0;
        repeat (2) @(negedge clk);
        rst_n = 1;
        @(negedge clk); start = 1;
        @(negedge clk); start = 0;
        send_pair(3, 4, 1'b0);
        send_pair(-2, 5, 1'b0);
        send_pair(7, -1, 1'b1);
        @(posedge clk);
        if (!done || result !== -5) begin
            $display("FAIL done=%b result=%0d expected=-5", done, result);
            failures = failures + 1;
        end
        @(negedge clk);
        if (busy) begin
            $display("FAIL busy remained asserted");
            failures = failures + 1;
        end
        if (failures != 0) $fatal(1, "conv1d failures=%0d", failures);
        $display("[PASS] conv1d_mac_int8 self-check");
        $finish;
    end
endmodule
