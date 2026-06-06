`timescale 1ns / 1ps
module dig_top #(
    parameter integer DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B, SPI write)
    parameter integer OUT_WIDTH  = 16,   // output element width (BRAM_C, SPI read)
    parameter integer ACC_WIDTH  = 24,
    parameter integer M_SIZE     = 48,   // rows of A, rows of C
    parameter integer K_SIZE     = 48,   // cols of A = rows of B (inner dimension)
    parameter integer N_SIZE     = 48,   // cols of B, cols of C
    parameter integer SA_SIZE    = 16
)(
    input  wire clk,
    input  wire rst_n,
    input  wire start,
    output wire done,

    input  wire [1:0] act_type,
    input  wire [1:0] pool_type,
    input  wire [4:0] quant_shift,  // arithmetic right-shift for requantization
    output wire       norm_done,

    // SPI-facing ports — input matrices (8-bit elements)
    input  wire [$clog2(M_SIZE*K_SIZE)-1:0] spi_a_waddr,
    input  wire [DATA_WIDTH-1:0]            spi_a_wdata,
    input  wire                             spi_a_we,

    input  wire [$clog2(K_SIZE*N_SIZE)-1:0] spi_b_waddr,
    input  wire [DATA_WIDTH-1:0]            spi_b_wdata,
    input  wire                             spi_b_we,

    // SPI-facing port — output matrix (OUT_WIDTH-bit elements)
    input  wire [$clog2(M_SIZE*N_SIZE)-1:0] spi_c_raddr,
    output wire [OUT_WIDTH-1:0]             spi_c_rdata
);
    // MAT A(M x K) x MAT B(K x N) = MAT C(M x N)
    localparam integer M_TILES   = (M_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam integer K_TILES   = (K_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam integer N_TILES   = (N_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam integer BRAM_A_AW = $clog2(SA_SIZE * M_TILES * K_TILES);
    localparam integer BRAM_B_AW = $clog2(SA_SIZE * K_TILES * N_TILES);
    localparam integer BRAM_C_AW = $clog2(SA_SIZE * M_TILES * N_TILES);

    // BRAM_A/B read wires (DATA_WIDTH per element)
    wire [BRAM_A_AW-1:0]          acc_a_raddr;
    wire [DATA_WIDTH*SA_SIZE-1:0]  acc_a_rdata;
    wire [SA_SIZE-1:0]             acc_a_rbv;

    wire [BRAM_B_AW-1:0]          acc_b_raddr;
    wire [DATA_WIDTH*SA_SIZE-1:0]  acc_b_rdata;
    wire [SA_SIZE-1:0]             acc_b_rbv;

    // BRAM_C write wires (OUT_WIDTH per element)
    wire [BRAM_C_AW-1:0]          acc_c_waddr;
    wire [OUT_WIDTH*SA_SIZE-1:0]   acc_c_wdata;
    wire                           acc_c_we;

    memory_top #(
        .DATA_WIDTH(DATA_WIDTH),
        .OUT_WIDTH (OUT_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .M_SIZE    (M_SIZE),
        .K_SIZE    (K_SIZE),
        .N_SIZE    (N_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_memory_top (
        .clk        (clk),
        .spi_a_waddr(spi_a_waddr),
        .spi_a_wdata(spi_a_wdata),
        .spi_a_we   (spi_a_we),
        .spi_b_waddr(spi_b_waddr),
        .spi_b_wdata(spi_b_wdata),
        .spi_b_we   (spi_b_we),
        .spi_c_raddr(spi_c_raddr),
        .spi_c_rdata(spi_c_rdata),
        .acc_a_raddr(acc_a_raddr),
        .acc_a_rdata(acc_a_rdata),
        .acc_a_rbv  (acc_a_rbv),
        .acc_b_raddr(acc_b_raddr),
        .acc_b_rdata(acc_b_rdata),
        .acc_b_rbv  (acc_b_rbv),
        .acc_c_waddr(acc_c_waddr),
        .acc_c_wdata(acc_c_wdata),
        .acc_c_we   (acc_c_we)
    );

    accelerator_top #(
        .DATA_WIDTH(DATA_WIDTH),
        .OUT_WIDTH (OUT_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .M_SIZE    (M_SIZE),
        .K_SIZE    (K_SIZE),
        .N_SIZE    (N_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_accelerator_top (
        .clk        (clk),
        .rst_n      (rst_n),
        .start      (start),
        .done       (done),
        .acc_a_raddr(acc_a_raddr),
        .acc_a_rdata(acc_a_rdata),
        .acc_a_rbv  (acc_a_rbv),
        .acc_b_raddr(acc_b_raddr),
        .acc_b_rdata(acc_b_rdata),
        .acc_b_rbv  (acc_b_rbv),
        .acc_c_waddr(acc_c_waddr),
        .acc_c_wdata(acc_c_wdata),
        .acc_c_we   (acc_c_we),
        .act_type   (act_type),
        .pool_type  (pool_type),
        .quant_shift(quant_shift),
        .norm_done  (norm_done)
    );


endmodule
