`timescale 1ns / 1ps
module accelerator_top #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B)
    parameter int OUT_WIDTH  = 16,   // output element width (activation → norm → BRAM_C)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = 48,   // rows of A, rows of C
    parameter int K_SIZE     = 48,   // cols of A = rows of B
    parameter int N_SIZE     = 48,   // cols of B, cols of C
    parameter int SA_SIZE    = 16
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    // BRAM_A read
    output logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((K_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0] acc_a_rdata,
    input  logic [SA_SIZE-1:0]            acc_a_rbv,

    // BRAM_B read
    output logic [$clog2(SA_SIZE*((K_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0] acc_b_rdata,
    input  logic [SA_SIZE-1:0]            acc_b_rbv,

    // BRAM_C write (OUT_WIDTH-wide per element)
    output logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_c_waddr,
    output logic [OUT_WIDTH*SA_SIZE-1:0]  acc_c_wdata,
    output logic                          acc_c_we,

    // Activation / pool control
    input  logic [1:0] act_type,
    input  logic [1:0] pool_type,
    input  logic [4:0] quant_shift,  // arithmetic right-shift for requantization (0 = bypass)
    output logic       norm_done
);

    // ---------------------------------------------------------------
    // SA controller <-> SA array
    // ---------------------------------------------------------------
    logic                  sa_start;
    logic [DATA_WIDTH-1:0] sa_mat_a      [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [DATA_WIDTH-1:0] sa_mat_b      [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [SA_SIZE-1:0]    sa_mat_a_bv   [0:SA_SIZE-1];
    logic [SA_SIZE-1:0]    sa_mat_b_bv   [0:SA_SIZE-1];
    logic [ACC_WIDTH-1:0]  sa_acc_result [0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  sa_acc_valid  [0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  sa_acc_ready  [0:SA_SIZE-1][0:SA_SIZE-1];

    // ---------------------------------------------------------------
    // SA controller <-> accumulator_bank
    // ---------------------------------------------------------------
    logic                  accum_wr_en,  accum_wr_sel;
    logic [ACC_WIDTH-1:0]  accum_wr_data [0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  accum_clr_en, accum_clr_sel;
    logic [ACC_WIDTH-1:0]  accum_rd_data [0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  accum_rd_sel;

    // ---------------------------------------------------------------
    // Save pipeline (OUT_WIDTH-wide)
    // ---------------------------------------------------------------
    logic                 accum_valid_out;
    logic [OUT_WIDTH-1:0] act_out  [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [OUT_WIDTH-1:0] pool_out [0:SA_SIZE-1][0:SA_SIZE-1];

    // ---------------------------------------------------------------
    // sa_controller
    // ---------------------------------------------------------------
    sa_controller #(
        .DATA_WIDTH(DATA_WIDTH),
        .OUT_WIDTH (OUT_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .M_SIZE    (M_SIZE),
        .K_SIZE    (K_SIZE),
        .N_SIZE    (N_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_controller (
        .clk            (clk),
        .rst_n          (rst_n),
        .start          (start),
        .done           (done),

        .bram_a_raddr   (acc_a_raddr),
        .bram_a_rdata   (acc_a_rdata),
        .bram_a_rbv     (acc_a_rbv),

        .bram_b_raddr   (acc_b_raddr),
        .bram_b_rdata   (acc_b_rdata),
        .bram_b_rbv     (acc_b_rbv),

        .bram_c_waddr   (acc_c_waddr),
        .bram_c_wdata   (acc_c_wdata),
        .bram_c_we      (acc_c_we),

        .accum_valid_out(accum_valid_out),
        .norm_done      (norm_done),
        .norm_data      (pool_out),

        .accum_wr_en    (accum_wr_en),
        .accum_wr_sel   (accum_wr_sel),
        .accum_wr_data  (accum_wr_data),
        .accum_clr_en   (accum_clr_en),
        .accum_clr_sel  (accum_clr_sel),
        .accum_rd_data  (accum_rd_data),
        .accum_rd_sel   (accum_rd_sel),

        .sa_start       (sa_start),
        .sa_mat_a       (sa_mat_a),
        .sa_mat_b       (sa_mat_b),
        .sa_mat_a_bv    (sa_mat_a_bv),
        .sa_mat_b_bv    (sa_mat_b_bv),
        .sa_acc_result  (sa_acc_result),
        .sa_acc_valid   (sa_acc_valid),
        .sa_acc_ready   (sa_acc_ready)
    );

    // ---------------------------------------------------------------
    // SA array
    // ---------------------------------------------------------------
    SA_16x16_TOP #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .ROW_SIZE  (SA_SIZE)
    ) u_sa_top (
        .clk       (clk),
        .rst_n     (rst_n),
        .start     (sa_start),
        .mat_a     (sa_mat_a),
        .mat_b     (sa_mat_b),
        .mat_a_bv  (sa_mat_a_bv),
        .mat_b_bv  (sa_mat_b_bv),
        .acc_result(sa_acc_result),
        .acc_valid (sa_acc_valid),
        .acc_ready (sa_acc_ready)
    );

    // ---------------------------------------------------------------
    // Accumulator bank
    // ---------------------------------------------------------------
    accumulator_bank #(
        .ACC_WIDTH(ACC_WIDTH),
        .SA_SIZE  (SA_SIZE)
    ) u_accum (
        .clk    (clk),
        .rst_n  (rst_n),
        .wr_en  (accum_wr_en),
        .wr_sel (accum_wr_sel),
        .wr_data(accum_wr_data),
        .clr_en (accum_clr_en),
        .clr_sel(accum_clr_sel),
        .rd_sel (accum_rd_sel),
        .rd_data(accum_rd_data)
    );

    // ---------------------------------------------------------------
    // Activation unit (combinational, 32-bit ACC → OUT_WIDTH output)
    // ---------------------------------------------------------------
    activation_unit #(
        .ACC_WIDTH (ACC_WIDTH),
        .OUT_WIDTH (OUT_WIDTH),
        .SA_SIZE   (SA_SIZE)
    ) u_act (
        .act_type   (act_type),
        .quant_shift(quant_shift),
        .in_data    (accum_rd_data),
        .out_data   (act_out)
    );

    // ---------------------------------------------------------------
    // Norm/Pool (1-cycle pipeline, OUT_WIDTH)
    // ---------------------------------------------------------------
    norm_pool #(
        .OUT_WIDTH(OUT_WIDTH),
        .SA_SIZE  (SA_SIZE)
    ) u_pool (
        .clk      (clk),
        .rst_n    (rst_n),
        .pool_type(pool_type),
        .in_valid (accum_valid_out),
        .in_data  (act_out),
        .out_data (pool_out),
        .norm_done(norm_done)
    );

endmodule
