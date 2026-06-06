`timescale 1ns / 1ps
module memory_top #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (SRAM_AB)
    parameter int OUT_WIDTH  = 16,   // output element width (SRAM_C)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = 48,   // rows of A, rows of C
    parameter int K_SIZE     = 48,   // cols of A = rows of B
    parameter int N_SIZE     = 48,   // cols of B, cols of C
    parameter int SA_SIZE    = 16
)(
    input  logic clk,

    // SPI write: mat_a  (M_SIZE x K_SIZE elements, DATA_WIDTH-bit)
    input  logic [$clog2(M_SIZE*K_SIZE)-1:0] spi_a_waddr,
    input  logic [DATA_WIDTH-1:0]            spi_a_wdata,
    input  logic                             spi_a_we,

    // SPI write: mat_b  (K_SIZE x N_SIZE elements, DATA_WIDTH-bit)
    input  logic [$clog2(K_SIZE*N_SIZE)-1:0] spi_b_waddr,
    input  logic [DATA_WIDTH-1:0]            spi_b_wdata,
    input  logic                             spi_b_we,

    // SPI read: mat_c  (M_SIZE x N_SIZE elements, OUT_WIDTH-bit)
    input  logic [$clog2(M_SIZE*N_SIZE)-1:0] spi_c_raddr,
    output logic [OUT_WIDTH-1:0]             spi_c_rdata,

    // Accelerator read: mat_a (DATA_WIDTH per element)
    input  logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((K_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_a_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0] acc_a_rdata,
    output logic [SA_SIZE-1:0]            acc_a_rbv,

    // Accelerator read: mat_b (DATA_WIDTH per element)
    input  logic [$clog2(SA_SIZE*((K_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_b_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0] acc_b_rdata,
    output logic [SA_SIZE-1:0]            acc_b_rbv,

    // Accelerator write: mat_c (OUT_WIDTH per element)
    input  logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_c_waddr,
    input  logic [OUT_WIDTH*SA_SIZE-1:0]  acc_c_wdata,
    input  logic                          acc_c_we
);

    // -----------------------------------------------------------------------
    // Dual-port SRAM for matrices A and B
    // -----------------------------------------------------------------------
    SRAM_AB #(
        .DATA_WIDTH(DATA_WIDTH),
        .M_SIZE    (M_SIZE),
        .K_SIZE    (K_SIZE),
        .N_SIZE    (N_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_sram_ab (
        .clk           (clk),
        // Port 0 — matrix A
        .spi_a_we      (spi_a_we),
        .spi_a_waddr   (spi_a_waddr),
        .spi_a_wdata   (spi_a_wdata),
        .acc_a_raddr   (acc_a_raddr),
        .acc_a_rdata   (acc_a_rdata),
        .acc_a_bv_rdata(acc_a_rbv),
        // Port 1 — matrix B
        .spi_b_we      (spi_b_we),
        .spi_b_waddr   (spi_b_waddr),
        .spi_b_wdata   (spi_b_wdata),
        .acc_b_raddr   (acc_b_raddr),
        .acc_b_rdata   (acc_b_rdata),
        .acc_b_bv_rdata(acc_b_rbv)
    );

    // -----------------------------------------------------------------------
    // Single-port SRAM for output matrix C
    // -----------------------------------------------------------------------
    SRAM_C #(
        .OUT_WIDTH(OUT_WIDTH),
        .ACC_WIDTH(ACC_WIDTH),
        .M_SIZE   (M_SIZE),
        .N_SIZE   (N_SIZE),
        .SA_SIZE  (SA_SIZE)
    ) u_sram_c (
        .clk      (clk),
        .acc_waddr(acc_c_waddr),
        .acc_wdata(acc_c_wdata),
        .acc_we   (acc_c_we),
        .spi_raddr(spi_c_raddr),
        .spi_rdata(spi_c_rdata)
    );

endmodule
