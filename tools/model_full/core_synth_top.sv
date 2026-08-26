module core_synth_top (
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire load_we,
    input wire [3:0] load_kind,
    input wire [15:0] load_index,
    input wire signed [7:0] load_data,
    output wire done,
    output wire signed [7:0] logit0,
    output wire signed [7:0] logit1,
    output wire signed [7:0] logit2,
    output wire signed [7:0] logit3,
    output wire signed [7:0] logit4
);
    wire busy;
    tiny_ecgcnn_full u_core (
        .clk(clk), .rst_n(rst_n), .start(start), .load_we(load_we),
        .load_kind(load_kind), .load_index(load_index), .load_data(load_data),
        .busy(busy), .done(done), .logit0(logit0), .logit1(logit1), .logit2(logit2),
        .logit3(logit3), .logit4(logit4)
    );
endmodule
