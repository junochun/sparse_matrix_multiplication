`timescale 1ns / 1ps
module SA_16x16_TOP #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int ROW_SIZE   = 16
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,

    input  logic [DATA_WIDTH-1:0] mat_a    [0:ROW_SIZE-1][0:ROW_SIZE-1],
    input  logic [DATA_WIDTH-1:0] mat_b    [0:ROW_SIZE-1][0:ROW_SIZE-1],
    input  logic [ROW_SIZE-1:0]   mat_a_bv [0:ROW_SIZE-1],
    input  logic [ROW_SIZE-1:0]   mat_b_bv [0:ROW_SIZE-1],
    output logic [ACC_WIDTH-1:0]  acc_result [0:ROW_SIZE-1][0:ROW_SIZE-1],
    output logic                  acc_valid  [0:ROW_SIZE-1][0:ROW_SIZE-1],
    input  logic                  acc_ready  [0:ROW_SIZE-1][0:ROW_SIZE-1]
);

    logic [DATA_WIDTH-1:0] a_nz [0:ROW_SIZE-1][0:ROW_SIZE-1];
    logic [ROW_SIZE-1:0]   a_bv [0:ROW_SIZE-1];
    logic                  a_valid [0:ROW_SIZE-1];
    logic                  a_ready [0:ROW_SIZE-1];

    logic [DATA_WIDTH-1:0] b_nz [0:ROW_SIZE-1][0:ROW_SIZE-1];
    logic [ROW_SIZE-1:0]   b_bv [0:ROW_SIZE-1];
    logic                  b_valid [0:ROW_SIZE-1];
    logic                  b_ready [0:ROW_SIZE-1];

    // A: a_bv[i] = mat_a_bv[i]  (direct)
    // B: b_bv[col][row] = mat_b_bv[row][col]  (transpose)
    always_comb begin
        for (int i = 0; i < ROW_SIZE; i++) begin
            a_bv[i] = '0;
            b_bv[i] = '0;
            for (int k = 0; k < ROW_SIZE; k++) begin
                a_nz[i][k] = '0;
                b_nz[i][k] = '0;
            end
        end

        for (int i = 0; i < ROW_SIZE; i++) begin
            automatic int p_a = 0;
            automatic int p_b = 0;

            for (int j = 0; j < ROW_SIZE; j++) begin
                a_bv[i][j] = mat_a_bv[i][j];
                if (mat_a_bv[i][j]) begin
                    a_nz[i][p_a] = mat_a[i][j];
                    p_a++;
                end
            end

            for (int j = 0; j < ROW_SIZE; j++) begin
                b_bv[i][j] = mat_b_bv[j][i];
                if (mat_b_bv[j][i]) begin
                    b_nz[i][p_b] = mat_b[j][i];
                    p_b++;
                end
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < ROW_SIZE; i++) begin
                a_valid[i] <= 1'b0;
                b_valid[i] <= 1'b0;
            end
        end else begin
            if (start) begin
                for (int i = 0; i < ROW_SIZE; i++) begin
                    a_valid[i] <= 1'b1;
                    b_valid[i] <= 1'b1;
                end
            end else begin
                for (int i = 0; i < ROW_SIZE; i++) begin
                    if (a_valid[i] && a_ready[i]) a_valid[i] <= 1'b0;
                    if (b_valid[i] && b_ready[i]) b_valid[i] <= 1'b0;
                end
            end
        end
    end

    SA_16x16 #(
        .DATA_WIDTH (DATA_WIDTH),
        .ACC_WIDTH  (ACC_WIDTH),
        .BV_WIDTH   (ROW_SIZE),
        .ROW_SIZE   (ROW_SIZE),
        .COL_SIZE   (ROW_SIZE)
    ) u_sa_core (
        .clk         (clk),
        .rst_n       (rst_n),
        .in_a_nz     (a_nz),
        .in_a_bv     (a_bv),
        .valid_in_a  (a_valid),
        .ready_out_a (a_ready),
        .in_b_nz     (b_nz),
        .in_b_bv     (b_bv),
        .valid_in_b  (b_valid),
        .ready_out_b (b_ready),
        .acc_result  (acc_result),
        .acc_valid   (acc_valid),
        .acc_ready   (acc_ready)
    );

endmodule
