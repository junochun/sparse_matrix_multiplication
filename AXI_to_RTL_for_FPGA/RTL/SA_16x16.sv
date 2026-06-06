`timescale 1ns / 1ps
module SA_16x16 #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int BV_WIDTH   = 16,
    parameter int ROW_SIZE   = 16,
    parameter int COL_SIZE   = 16
)(
    input  logic clk,
    input  logic rst_n,

    input  logic [DATA_WIDTH-1:0] in_a_nz    [0:ROW_SIZE-1][0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   in_a_bv    [0:ROW_SIZE-1],
    input  logic                  valid_in_a [0:ROW_SIZE-1],
    output logic                  ready_out_a[0:ROW_SIZE-1],

    input  logic [DATA_WIDTH-1:0] in_b_nz    [0:COL_SIZE-1][0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   in_b_bv    [0:COL_SIZE-1],
    input  logic                  valid_in_b [0:COL_SIZE-1],
    output logic                  ready_out_b[0:COL_SIZE-1],

    output logic [ACC_WIDTH-1:0]  acc_result [0:ROW_SIZE-1][0:COL_SIZE-1],
    output logic                  acc_valid  [0:ROW_SIZE-1][0:COL_SIZE-1],
    input  logic                  acc_ready  [0:ROW_SIZE-1][0:COL_SIZE-1]
);

    logic [DATA_WIDTH-1:0] h_nz [0:ROW_SIZE-1][0:COL_SIZE][0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   h_bv [0:ROW_SIZE-1][0:COL_SIZE];
    logic                  h_v  [0:ROW_SIZE-1][0:COL_SIZE];
    logic                  h_r  [0:ROW_SIZE-1][0:COL_SIZE];

    logic [DATA_WIDTH-1:0] v_nz [0:ROW_SIZE][0:COL_SIZE-1][0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   v_bv [0:ROW_SIZE][0:COL_SIZE-1];
    logic                  v_v  [0:ROW_SIZE][0:COL_SIZE-1];
    logic                  v_r  [0:ROW_SIZE][0:COL_SIZE-1];

    generate
        for (genvar r = 0; r < ROW_SIZE; r++) begin : ACT_IN
            for (genvar k = 0; k < BV_WIDTH; k++) begin : ACT_NZ
                assign h_nz[r][0][k] = in_a_nz[r][k];
            end
            assign h_bv[r][0] = in_a_bv[r];
            assign h_v[r][0]  = valid_in_a[r];
            assign ready_out_a[r] = h_r[r][0];
        end

        for (genvar c = 0; c < COL_SIZE; c++) begin : WGT_IN
            for (genvar k = 0; k < BV_WIDTH; k++) begin : WGT_NZ
                assign v_nz[0][c][k] = in_b_nz[c][k];
            end
            assign v_bv[0][c] = in_b_bv[c];
            assign v_v[0][c]  = valid_in_b[c];
            assign ready_out_b[c] = v_r[0][c];
        end
    endgenerate

    generate
        for (genvar r = 0; r < ROW_SIZE; r++) begin : TERM_RIGHT
            assign h_r[r][COL_SIZE] = 1'b1;
        end
        for (genvar c = 0; c < COL_SIZE; c++) begin : TERM_BOTTOM
            assign v_r[ROW_SIZE][c] = 1'b1;
        end
    endgenerate

    generate
        for (genvar i = 0; i < ROW_SIZE; i++) begin : ROW_GEN
            for (genvar j = 0; j < COL_SIZE; j++) begin : COL_GEN
                sparse_single_PE #(
                    .DATA_WIDTH(DATA_WIDTH),
                    .ACC_WIDTH (ACC_WIDTH),
                    .BV_WIDTH  (BV_WIDTH)
                ) u_pe (
                    .clk   (clk),
                    .rst_n (rst_n),

                    .act_nz_in    (h_nz[i][j]),
                    .act_bv_in    (h_bv[i][j]),
                    .act_valid    (h_v[i][j]),
                    .act_ready    (h_r[i][j]),
                    .act_nz_out   (h_nz[i][j+1]),
                    .act_bv_out   (h_bv[i][j+1]),
                    .act_valid_out(h_v[i][j+1]),
                    .act_ready_in (h_r[i][j+1]),

                    .wgt_nz_in    (v_nz[i][j]),
                    .wgt_bv_in    (v_bv[i][j]),
                    .wgt_valid    (v_v[i][j]),
                    .wgt_ready    (v_r[i][j]),
                    .wgt_nz_out   (v_nz[i+1][j]),
                    .wgt_bv_out   (v_bv[i+1][j]),
                    .wgt_valid_out(v_v[i+1][j]),
                    .wgt_ready_in (v_r[i+1][j]),

                    .psum_in       ('0),
                    .psum_valid_in (1'b1),
                    .psum_ready_out(),
                    .psum_out      (acc_result[i][j]),
                    .psum_valid_out(acc_valid[i][j]),
                    .psum_ready_in (acc_ready[i][j])
                );
            end
        end
    endgenerate

endmodule
