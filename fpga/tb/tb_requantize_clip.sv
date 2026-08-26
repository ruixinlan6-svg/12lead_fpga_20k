`timescale 1ns/1ps
module tb_requantize_clip;
    logic signed [31:0] acc, offset, multiplier;
    logic [5:0] shift;
    logic signed [7:0] result;
    integer failures;

    requantize_clip dut(.*);

    task automatic check(input integer a, input integer o, input integer m, input integer s, input integer expected);
        begin
            acc = a; offset = o; multiplier = m; shift = s;
            #1;
            if (result !== expected[7:0]) begin
                $display("FAIL acc=%0d off=%0d mult=%0d shift=%0d got=%0d expected=%0d", a,o,m,s,result,expected);
                failures = failures + 1;
            end
        end
    endtask

    initial begin
        failures = 0;
        check(10, 0, 1, 0, 10);
        check(7, 0, 1, 1, 4);
        check(-7, 0, 1, 1, -4);
        check(1000, 0, 1000, 0, 127);
        check(-1000, 0, 1000, 0, -128);
        check(10, -3, 2, 2, 4);
        if (failures != 0) $fatal(1, "requantize failures=%0d", failures);
        $display("[PASS] requantize_clip self-check");
        $finish;
    end
endmodule
