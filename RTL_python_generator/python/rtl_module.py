
def sa_mod_name(sa_size: int) -> str:
    return f"SA_{sa_size}x{sa_size}"

def sa_top_mod_name(sa_size: int) -> str:
    return f"SA_{sa_size}x{sa_size}_TOP"


def gen_dig_top(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module dig_top #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_a_waddr,
    input  logic [DATA_WIDTH-1:0]                spi_a_wdata,
    input  logic                                 spi_a_we,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_b_waddr,
    input  logic [DATA_WIDTH-1:0]                spi_b_wdata,
    input  logic                                 spi_b_we,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_c_raddr,
    output logic [ACC_WIDTH-1:0]                 spi_c_rdata
);

    localparam int BRAM_AW = $clog2(MAT_SIZE * (MAT_SIZE / SA_SIZE));

    logic [BRAM_AW-1:0]            acc_a_raddr;
    logic [DATA_WIDTH*SA_SIZE-1:0] acc_a_rdata;
    logic [BRAM_AW-1:0]            acc_b_raddr;
    logic [DATA_WIDTH*SA_SIZE-1:0] acc_b_rdata;
    logic [BRAM_AW-1:0]            acc_c_waddr;
    logic [ACC_WIDTH*SA_SIZE-1:0]  acc_c_wdata;
    logic                          acc_c_we;

    memory_top #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_memory_top (
        .clk         (clk),
        .spi_a_waddr (spi_a_waddr),
        .spi_a_wdata (spi_a_wdata),
        .spi_a_we    (spi_a_we),
        .spi_b_waddr (spi_b_waddr),
        .spi_b_wdata (spi_b_wdata),
        .spi_b_we    (spi_b_we),
        .spi_c_raddr (spi_c_raddr),
        .spi_c_rdata (spi_c_rdata),
        .acc_a_raddr (acc_a_raddr),
        .acc_a_rdata (acc_a_rdata),
        .acc_b_raddr (acc_b_raddr),
        .acc_b_rdata (acc_b_rdata),
        .acc_c_waddr (acc_c_waddr),
        .acc_c_wdata (acc_c_wdata),
        .acc_c_we    (acc_c_we)
    );
    
    accelerator_top #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_accelerator_top (
        .clk         (clk),
        .rst_n       (rst_n),
        .start       (start),
        .done        (done),
        .acc_a_raddr (acc_a_raddr),
        .acc_a_rdata (acc_a_rdata),
        .acc_b_raddr (acc_b_raddr),
        .acc_b_rdata (acc_b_rdata),
        .acc_c_waddr (acc_c_waddr),
        .acc_c_wdata (acc_c_wdata),
        .acc_c_we    (acc_c_we)
    );

endmodule
"""


def gen_dig_top_final(m_size: int, k_size: int, n_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module dig_top #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B, SPI write)
    parameter int OUT_WIDTH  = 16,   // output element width (BRAM_C, SPI read)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = {m_size},   // rows of A, rows of C
    parameter int K_SIZE     = {k_size},   // cols of A = rows of B (inner dimension)
    parameter int N_SIZE     = {n_size},   // cols of B, cols of C
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    input  logic [1:0] act_type,
    input  logic [1:0] pool_type,
    input  logic [4:0] quant_shift,  // arithmetic right-shift for requantization
    output logic       norm_done,

    // SPI-facing ports — input matrices (8-bit elements)
    input  logic [$clog2(M_SIZE*K_SIZE)-1:0] spi_a_waddr,
    input  logic [DATA_WIDTH-1:0]            spi_a_wdata,
    input  logic                             spi_a_we,

    input  logic [$clog2(K_SIZE*N_SIZE)-1:0] spi_b_waddr,
    input  logic [DATA_WIDTH-1:0]            spi_b_wdata,
    input  logic                             spi_b_we,

    // SPI-facing port — output matrix (OUT_WIDTH-bit elements)
    input  logic [$clog2(M_SIZE*N_SIZE)-1:0] spi_c_raddr,
    output logic [OUT_WIDTH-1:0]             spi_c_rdata
);
    // MAT A(M x K) x MAT B(K x N) = MAT C(M x N)
    localparam int M_TILES   = (M_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int K_TILES   = (K_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int N_TILES   = (N_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int BRAM_A_AW = $clog2(SA_SIZE * M_TILES * K_TILES);
    localparam int BRAM_B_AW = $clog2(SA_SIZE * K_TILES * N_TILES);
    localparam int BRAM_C_AW = $clog2(SA_SIZE * M_TILES * N_TILES);

    // BRAM_A/B read wires (DATA_WIDTH per element)
    logic [BRAM_A_AW-1:0]          acc_a_raddr;
    logic [DATA_WIDTH*SA_SIZE-1:0]  acc_a_rdata;
    logic [SA_SIZE-1:0]             acc_a_rbv;

    logic [BRAM_B_AW-1:0]          acc_b_raddr;
    logic [DATA_WIDTH*SA_SIZE-1:0]  acc_b_rdata;
    logic [SA_SIZE-1:0]             acc_b_rbv;

    // BRAM_C write wires (OUT_WIDTH per element)
    logic [BRAM_C_AW-1:0]          acc_c_waddr;
    logic [OUT_WIDTH*SA_SIZE-1:0]   acc_c_wdata;
    logic                           acc_c_we;

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
"""


def gen_memory_top(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module memory_top #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_a_waddr,
    input  logic [DATA_WIDTH-1:0]                spi_a_wdata,
    input  logic                                 spi_a_we,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_b_waddr,
    input  logic [DATA_WIDTH-1:0]                spi_b_wdata,
    input  logic                                 spi_b_we,

    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0] spi_c_raddr,
    output logic [ACC_WIDTH-1:0]                 spi_c_rdata,

    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_a_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_a_rdata,

    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_b_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_b_rdata,

    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_c_waddr,
    input  logic [ACC_WIDTH*SA_SIZE-1:0]                   acc_c_wdata,
    input  logic                                           acc_c_we
);

    BRAM_A #(
        .DATA_WIDTH(DATA_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_bram_a (
        .clk      (clk),
        .spi_we   (spi_a_we),
        .spi_waddr(spi_a_waddr),
        .spi_wdata(spi_a_wdata),
        .acc_raddr(acc_a_raddr),
        .acc_rdata(acc_a_rdata)
    );

    BRAM_B #(
        .DATA_WIDTH(DATA_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_bram_b (
        .clk      (clk),
        .spi_we   (spi_b_we),
        .spi_waddr(spi_b_waddr),
        .spi_wdata(spi_b_wdata),
        .acc_raddr(acc_b_raddr),
        .acc_rdata(acc_b_rdata)
    );

    BRAM_C #(
        .ACC_WIDTH(ACC_WIDTH),
        .MAT_SIZE (MAT_SIZE),
        .SA_SIZE  (SA_SIZE)
    ) u_bram_c (
        .clk      (clk),
        .acc_we   (acc_c_we),
        .acc_waddr(acc_c_waddr),
        .acc_wdata(acc_c_wdata),
        .spi_raddr(spi_c_raddr),
        .spi_rdata(spi_c_rdata)
    );

endmodule
"""

def gen_memory_top_final(m_size: int, k_size: int, n_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module memory_top #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (SRAM_AB)
    parameter int OUT_WIDTH  = 16,   // output element width (SRAM_C)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = {m_size},   // rows of A, rows of C
    parameter int K_SIZE     = {k_size},   // cols of A = rows of B
    parameter int N_SIZE     = {n_size},   // cols of B, cols of C
    parameter int SA_SIZE    = {sa_size}
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
"""


def gen_accelerator_top_non_sparse(mat_size: int, sa_size: int) -> str:
    sa_top_name = sa_top_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module accelerator_top #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_a_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_b_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_c_waddr,
    output logic [ACC_WIDTH*SA_SIZE-1:0]                   acc_c_wdata,
    output logic                                           acc_c_we
);

    logic                   sa_start;
    logic                   sa_core_rst_n;
    logic [DATA_WIDTH-1:0]  sa_mat_a      [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [DATA_WIDTH-1:0]  sa_mat_b      [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [ACC_WIDTH-1:0]   sa_acc_result [0:SA_SIZE-1][0:SA_SIZE-1];

    sa_controller #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_controller (
        .clk           (clk),
        .rst_n         (rst_n),
        .start         (start),
        .done          (done),
        .bram_a_raddr  (acc_a_raddr),
        .bram_a_rdata  (acc_a_rdata),
        .bram_b_raddr  (acc_b_raddr),
        .bram_b_rdata  (acc_b_rdata),
        .bram_c_waddr  (acc_c_waddr),
        .bram_c_wdata  (acc_c_wdata),
        .bram_c_we     (acc_c_we),
        .sa_start      (sa_start),
        .sa_core_rst_n (sa_core_rst_n),
        .sa_mat_a      (sa_mat_a),
        .sa_mat_b      (sa_mat_b),
        .sa_acc_result (sa_acc_result)
    );

    {sa_top_name} #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .ROW_SIZE  (SA_SIZE)
    ) u_sa_top (
        .clk        (clk),
        .rst_n      (sa_core_rst_n),
        .start      (sa_start),
        .mat_a      (sa_mat_a),
        .mat_b      (sa_mat_b),
        .acc_result (sa_acc_result)
    );

endmodule
"""


def gen_accelerator_top_sparse(mat_size: int, sa_size: int) -> str:
    sa_top = sa_top_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module accelerator_top #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_a_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_b_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_c_waddr,
    output logic [ACC_WIDTH*SA_SIZE-1:0]                   acc_c_wdata,
    output logic                                           acc_c_we
);

    logic                  sa_start;
    logic [DATA_WIDTH-1:0] sa_mat_a     [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [DATA_WIDTH-1:0] sa_mat_b     [0:SA_SIZE-1][0:SA_SIZE-1];
    logic [ACC_WIDTH-1:0]  sa_acc_result[0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  sa_acc_valid [0:SA_SIZE-1][0:SA_SIZE-1];
    logic                  sa_acc_ready [0:SA_SIZE-1][0:SA_SIZE-1];

    sa_controller #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .MAT_SIZE  (MAT_SIZE),
        .SA_SIZE   (SA_SIZE)
    ) u_controller (
        .clk          (clk),
        .rst_n        (rst_n),
        .start        (start),
        .done         (done),
        .bram_a_raddr (acc_a_raddr),
        .bram_a_rdata (acc_a_rdata),
        .bram_b_raddr (acc_b_raddr),
        .bram_b_rdata (acc_b_rdata),
        .bram_c_waddr (acc_c_waddr),
        .bram_c_wdata (acc_c_wdata),
        .bram_c_we    (acc_c_we),
        .sa_start     (sa_start),
        .sa_mat_a     (sa_mat_a),
        .sa_mat_b     (sa_mat_b),
        .sa_acc_result(sa_acc_result),
        .sa_acc_valid (sa_acc_valid),
        .sa_acc_ready (sa_acc_ready)
    );

    {sa_top} #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .ROW_SIZE  (SA_SIZE)
    ) u_sa_top (
        .clk       (clk),
        .rst_n     (rst_n),
        .start     (sa_start),
        .mat_a     (sa_mat_a),
        .mat_b     (sa_mat_b),
        .acc_result(sa_acc_result),
        .acc_valid (sa_acc_valid),
        .acc_ready (sa_acc_ready)
    );

endmodule
"""

def gen_accelerator_top_final(m_size: int, k_size: int, n_size: int, sa_size: int) -> str:
    sa_top = sa_top_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module accelerator_top #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B)
    parameter int OUT_WIDTH  = 16,   // output element width (activation → norm → BRAM_C)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = {m_size},   // rows of A, rows of C
    parameter int K_SIZE     = {k_size},   // cols of A = rows of B
    parameter int N_SIZE     = {n_size},   // cols of B, cols of C
    parameter int SA_SIZE    = {sa_size}
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
    {sa_top} #(
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
"""


def gen_bram_a(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps

module BRAM_A #(
    parameter int DATA_WIDTH = 8,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,

    // SPI write: element-wise
    input  logic                                            spi_we,
    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0]            spi_waddr,
    input  logic [DATA_WIDTH-1:0]                           spi_wdata,

    // Accelerator read: SA_SIZE elements per cycle
    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_rdata
);
    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int DEPTH     = MAT_SIZE * NUM_TILES;

    // 1D flat memory: each entry holds SA_SIZE elements (one tile row)
    logic [DATA_WIDTH*SA_SIZE-1:0] mem [0:DEPTH-1];

    // SPI write: unpack flat addr and write into correct tile-row entry
    always_ff @(posedge clk) begin
        if (spi_we) begin
            automatic int row      = int'(spi_waddr) / MAT_SIZE;
            automatic int col      = int'(spi_waddr) % MAT_SIZE;
            automatic int col_tile = col / SA_SIZE;
            automatic int col_pos  = col % SA_SIZE;
            automatic int idx      = row * NUM_TILES + col_tile;
            mem[idx][DATA_WIDTH*(col_pos+1)-1 -: DATA_WIDTH] <= spi_wdata;
        end
    end

    // Accelerator read: output full tile row in one cycle
    always_ff @(posedge clk)
        acc_rdata <= mem[acc_raddr];

endmodule
"""

def gen_bram_b(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps

module BRAM_B #(
    parameter int DATA_WIDTH = 8,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,

    // SPI write: element-wise
    input  logic                                            spi_we,
    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0]            spi_waddr,
    input  logic [DATA_WIDTH-1:0]                           spi_wdata,

    // Accelerator read: SA_SIZE elements per cycle
    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                  acc_rdata
);
    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int DEPTH     = MAT_SIZE * NUM_TILES;

    // 1D flat memory: each entry holds SA_SIZE elements (one tile row)
    logic [DATA_WIDTH*SA_SIZE-1:0] mem [0:DEPTH-1];

    // SPI write: row-major storage
    always_ff @(posedge clk) begin
        if (spi_we) begin
            automatic int row      = int'(spi_waddr) / MAT_SIZE;
            automatic int col      = int'(spi_waddr) % MAT_SIZE;
            automatic int col_tile = col / SA_SIZE;
            automatic int col_pos  = col % SA_SIZE;
            automatic int idx      = row * NUM_TILES + col_tile;
            mem[idx][DATA_WIDTH*(col_pos+1)-1 -: DATA_WIDTH] <= spi_wdata;
        end
    end

    // Accelerator read: output full tile row in one cycle
    always_ff @(posedge clk)
        acc_rdata <= mem[acc_raddr];

endmodule
"""

def gen_bram_c(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps

module BRAM_C #(
    parameter int ACC_WIDTH = 32,
    parameter int MAT_SIZE  = {mat_size},
    parameter int SA_SIZE   = {sa_size}
)(
    input  logic clk,

    // Accelerator write: SA_SIZE elements per cycle
    input  logic                                            acc_we,
    input  logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] acc_waddr,
    input  logic [ACC_WIDTH*SA_SIZE-1:0]                   acc_wdata,

    // SPI read: element-wise
    input  logic [$clog2(MAT_SIZE*MAT_SIZE)-1:0]            spi_raddr,
    output logic [ACC_WIDTH-1:0]                           spi_rdata
);
    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int DEPTH     = MAT_SIZE * NUM_TILES;

    // 1D flat memory: each entry holds SA_SIZE results (one tile row)
    logic [ACC_WIDTH*SA_SIZE-1:0] mem [0:DEPTH-1];

    // Accelerator write
    always_ff @(posedge clk)
        if (acc_we) mem[acc_waddr] <= acc_wdata;

    // SPI read: unpack flat addr and extract single element
    always_ff @(posedge clk) begin
        automatic int row      = int'(spi_raddr) / MAT_SIZE;
        automatic int col      = int'(spi_raddr) % MAT_SIZE;
        automatic int col_tile = col / SA_SIZE;
        automatic int col_pos  = col % SA_SIZE;
        spi_rdata <= mem[row * NUM_TILES + col_tile][ACC_WIDTH*(col_pos+1)-1 -: ACC_WIDTH];
    end

endmodule
"""

def gen_sram_ab_final(m_size: int, k_size: int, n_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
// Dual-port behavioral SRAM model for matrices A and B.
// Port 0 (A-side): SPI write or accelerator read for matrix A
// Port 1 (B-side): SPI write or accelerator read for matrix B
//
// Word layout (WORD_W bits):
//   [WORD_W-1 : DATA_WIDTH*SA_SIZE]  = BV  (SA_SIZE bits)
//   [DATA_WIDTH*SA_SIZE-1 : 0]       = DATA (DATA_WIDTH*SA_SIZE bits)
//
// Address map (unified flat array):
//   [0 .. DEPTH_A-1]           = matrix A tiles
//   [DEPTH_A .. DEPTH_TOT-1]   = matrix B tiles
//
// SPI writes perform a Read-Modify-Write to update the target element
// and the corresponding BV bit within the packed word.
//

module SRAM_AB #(
    parameter int DATA_WIDTH = 8,
    parameter int M_SIZE     = {m_size},   // rows of A
    parameter int K_SIZE     = {k_size},   // cols of A (inner dimension)
    parameter int N_SIZE     = {n_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,

    // ---- Port 0 : matrix A ------------------------------------------------
    // SPI write (element-level)
    input  logic                                                         spi_a_we,
    input  logic [$clog2(M_SIZE*K_SIZE)-1:0]                            spi_a_waddr,
    input  logic [DATA_WIDTH-1:0]                                        spi_a_wdata,
    // Accelerator read (tile-row-level, registered 1-cycle latency)
    input  logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((K_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_a_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                                acc_a_rdata,
    output logic [SA_SIZE-1:0]                                           acc_a_bv_rdata,

    // ---- Port 1 : matrix B ------------------------------------------------
    // SPI write (element-level)
    input  logic                                                         spi_b_we,
    input  logic [$clog2(K_SIZE*N_SIZE)-1:0]                            spi_b_waddr,
    input  logic [DATA_WIDTH-1:0]                                        spi_b_wdata,
    // Accelerator read (tile-row-level, registered 1-cycle latency)
    input  logic [$clog2(SA_SIZE*((K_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_b_raddr,
    output logic [DATA_WIDTH*SA_SIZE-1:0]                                acc_b_rdata,
    output logic [SA_SIZE-1:0]                                           acc_b_bv_rdata
);
    // -----------------------------------------------------------------------
    // Tile counts and depths
    // -----------------------------------------------------------------------
    localparam int M_TILES  = (M_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int K_TILES  = (K_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int N_TILES  = (N_SIZE + SA_SIZE - 1) / SA_SIZE;

    localparam int DEPTH_A  = SA_SIZE * M_TILES * K_TILES;
    localparam int DEPTH_B  = SA_SIZE * K_TILES * N_TILES;
    localparam int DEPTH_TOT = DEPTH_A + DEPTH_B;

    localparam int ADDR_W   = $clog2(DEPTH_TOT);
    localparam int DATA_W   = DATA_WIDTH * SA_SIZE;   // 256 bits for default params
    localparam int WORD_W   = DATA_W + SA_SIZE;        // 288 bits (data + BV)

    // -----------------------------------------------------------------------
    // Unified SRAM array
    // -----------------------------------------------------------------------
    logic [WORD_W-1:0] sram [0:DEPTH_TOT-1];

    initial begin
        for (int i = 0; i < DEPTH_TOT; i++)
            sram[i] = '0;
    end


    // -----------------------------------------------------------------------
    // Port 0 — matrix A
    // -----------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (spi_a_we) begin
            // Decode flat element address → tile index + position
            automatic int unsigned row      = $unsigned(spi_a_waddr) / K_SIZE;
            automatic int unsigned col      = $unsigned(spi_a_waddr) % K_SIZE;
            automatic int unsigned col_tile = col / SA_SIZE;
            automatic int unsigned col_pos  = col % SA_SIZE;
            automatic int unsigned idx      = row * K_TILES + col_tile;   // within A region

            // Read-Modify-Write: update one element and its BV bit
            sram[idx][DATA_WIDTH*(col_pos+1)-1 -: DATA_WIDTH] <= spi_a_wdata;
            sram[idx][DATA_W + col_pos]                        <= (spi_a_wdata != '0);
        end
    end

    // Registered read (1-cycle latency)
    always_ff @(posedge clk) begin
        acc_a_rdata    <= sram[ADDR_W'(acc_a_raddr)][DATA_W-1:0];
        acc_a_bv_rdata <= sram[ADDR_W'(acc_a_raddr)][WORD_W-1:DATA_W];
    end

    // -----------------------------------------------------------------------
    // Port 1 — matrix B  (address offset by DEPTH_A)
    // -----------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (spi_b_we) begin
            automatic int unsigned row      = $unsigned(spi_b_waddr) / N_SIZE;
            automatic int unsigned col      = $unsigned(spi_b_waddr) % N_SIZE;
            automatic int unsigned col_tile = col / SA_SIZE;
            automatic int unsigned col_pos  = col % SA_SIZE;
            automatic int unsigned idx      = DEPTH_A + row * N_TILES + col_tile;

            sram[idx][DATA_WIDTH*(col_pos+1)-1 -: DATA_WIDTH] <= spi_b_wdata;
            sram[idx][DATA_W + col_pos]                        <= (spi_b_wdata != '0);
        end
    end

    always_ff @(posedge clk) begin
        acc_b_rdata    <= sram[ADDR_W'(DEPTH_A + $unsigned(acc_b_raddr))][DATA_W-1:0];
        acc_b_bv_rdata <= sram[ADDR_W'(DEPTH_A + $unsigned(acc_b_raddr))][WORD_W-1:DATA_W];
    end

endmodule
"""

def gen_sram_c_final(m_size: int, n_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
// Single-port behavioral SRAM model for output matrix C.
//
// Word layout: OUT_WIDTH * SA_SIZE bits (one full tile-row).
//   e.g. 16 * 32 = 512 bits per word
//
// Two non-overlapping access modes (time-separated by design):
//   ACC write : full tile-row write (one word per cycle)
//   SPI read  : element-level read (registered 1-cycle latency,
//               with within-word mux)
//
module SRAM_C #(
    parameter int OUT_WIDTH = 16,
    parameter int ACC_WIDTH = 24,
    parameter int M_SIZE     = {m_size},   // rows of C
    parameter int N_SIZE     = {n_size},   // cols of C
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,

    // ---- Accelerator write (tile-row granularity) -------------------------
    input  logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] acc_waddr,
    input  logic [OUT_WIDTH*SA_SIZE-1:0]  acc_wdata,
    input  logic                          acc_we,

    // ---- SPI read (element granularity, 1-cycle registered latency) ------
    input  logic [$clog2(M_SIZE*N_SIZE)-1:0] spi_raddr,
    output logic [OUT_WIDTH-1:0]             spi_rdata
);
    // -----------------------------------------------------------------------
    // Tile counts and depth
    // -----------------------------------------------------------------------
    localparam int M_TILES = (M_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int N_TILES = (N_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int DEPTH   = SA_SIZE * M_TILES * N_TILES;

    localparam int WORD_W  = OUT_WIDTH * SA_SIZE;   // 512 bits for default params

    // -----------------------------------------------------------------------
    // SRAM array
    // -----------------------------------------------------------------------
    logic [WORD_W-1:0] sram [0:DEPTH-1];

    initial begin
        for (int i = 0; i < DEPTH; i++)
            sram[i] = '0;
    end

    // -----------------------------------------------------------------------
    // Accelerator write — full tile-row at once
    // -----------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (acc_we)
            sram[acc_waddr] <= acc_wdata;
    end

    // -----------------------------------------------------------------------
    // SPI element read — decode flat address → tile index + col position
    // -----------------------------------------------------------------------
    logic [WORD_W-1:0] spi_rword;   // registered full word

    always_ff @(posedge clk) begin
        automatic int unsigned row      = $unsigned(spi_raddr) / N_SIZE;
        automatic int unsigned col      = $unsigned(spi_raddr) % N_SIZE;
        automatic int unsigned col_tile = col / SA_SIZE;
        automatic int unsigned col_pos  = col % SA_SIZE;
        automatic int unsigned idx      = row * N_TILES + col_tile;

        spi_rword <= sram[idx];
        // latch col_pos so the mux sees a registered value
        // (col_pos is a simple combinational decode; register the whole word
        //  and extract the element in the same registered stage)
        spi_rdata <= sram[idx][OUT_WIDTH*(col_pos+1)-1 -: OUT_WIDTH];
    end

endmodule
"""


def gen_sa_controller_non_sparse(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module sa_controller #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    // BRAM_A read
    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_a_rdata,

    // BRAM_B read
    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_b_rdata,

    // BRAM_C write
    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_c_waddr,
    output logic [ACC_WIDTH*SA_SIZE-1:0]                   bram_c_wdata,
    output logic                                           bram_c_we,

    // SA core interface
    output logic                  sa_start,
    output logic                  sa_core_rst_n,
    output logic [DATA_WIDTH-1:0] sa_mat_a     [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [DATA_WIDTH-1:0] sa_mat_b     [0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic [ACC_WIDTH-1:0]  sa_acc_result[0:SA_SIZE-1][0:SA_SIZE-1]
);

    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int BRAM_AW   = $clog2(MAT_SIZE * NUM_TILES);
    localparam int SA_LATENCY = SA_SIZE * 3;

    typedef enum logic [3:0] {{
        IDLE,
        RST_SA,       
        RST_SA_REL,   
        LOAD_ADDR,    
        LOAD_SA,      
        CALC_START,   
        CALC_FIRE,    
        WAIT_SA,      
        NEXT_PART,    
        SAVE_TILE,    
        NEXT_TILE,    
        DONE_STATE
    }} state_t;

    state_t state;

    int blk_r, blk_c, part_idx;
    int row_offset, col_offset, part_offset;

    always_comb begin
        row_offset  = blk_r   * SA_SIZE;
        col_offset  = blk_c   * SA_SIZE;
        part_offset = part_idx * SA_SIZE;
    end

    int row_cnt;
    logic row_done;
    assign row_done = (row_cnt == SA_SIZE - 1);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            row_cnt <= 0;
        else if (state == LOAD_SA || state == SAVE_TILE)
            row_cnt <= row_done ? 0 : row_cnt + 1;
        else
            row_cnt <= 0;
    end

    int wait_cnt;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            wait_cnt <= 0;
        else if (state == WAIT_SA)
            wait_cnt <= wait_cnt + 1;
        else
            wait_cnt <= 0;
    end

    always_comb begin
        if (state == LOAD_SA && !row_done) begin
            bram_a_raddr = BRAM_AW'((row_offset  + row_cnt + 1) * NUM_TILES + part_idx);
            bram_b_raddr = BRAM_AW'((part_offset + row_cnt + 1) * NUM_TILES
                                    + (col_offset / SA_SIZE));
        end else begin
            bram_a_raddr = BRAM_AW'((row_offset  + row_cnt) * NUM_TILES + part_idx);
            bram_b_raddr = BRAM_AW'((part_offset + row_cnt) * NUM_TILES
                                    + (col_offset / SA_SIZE));
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= '0;
                    sa_mat_b[i][j] <= '0;
                end
        end else if (state == LOAD_SA && !row_done) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_mat_a[row_cnt][k] <= bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_mat_b[row_cnt][k] <= bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end else if (state == CALC_START) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_mat_a[SA_SIZE-1][k] <= bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_mat_b[SA_SIZE-1][k] <= bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end
    end

    always_comb begin
        bram_c_we    = (state == SAVE_TILE);
        bram_c_waddr = BRAM_AW'((row_offset + row_cnt) * NUM_TILES
                                + (col_offset / SA_SIZE));
        for (int k = 0; k < SA_SIZE; k++)
            bram_c_wdata[ACC_WIDTH*(k+1)-1 -: ACC_WIDTH] = sa_acc_result[row_cnt][k];
    end

    always_comb begin
        sa_core_rst_n = rst_n && (state != RST_SA);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            blk_r    <= 0;
            blk_c    <= 0;
            part_idx <= 0;
            sa_start <= 1'b0;
            done     <= 1'b0;
        end else begin
            sa_start <= 1'b0;
            case (state)
                IDLE: begin
                    blk_r    <= 0;
                    blk_c    <= 0;
                    part_idx <= 0;
                    done     <= 1'b0;
                    if (start) state <= RST_SA;
                end
                RST_SA: state <= RST_SA_REL;
                RST_SA_REL: state <= LOAD_ADDR;
                LOAD_ADDR: state <= LOAD_SA;
                LOAD_SA: if (row_done) state <= CALC_START;
                CALC_START: state <= CALC_FIRE;
                CALC_FIRE: begin
                    sa_start <= 1'b1;
                    state    <= WAIT_SA;
                end
                WAIT_SA: begin
                    if (wait_cnt >= SA_LATENCY - 1) begin
                        if (part_idx == NUM_TILES - 1) state <= SAVE_TILE;
                        else begin
                            part_idx <= part_idx + 1;
                            state    <= NEXT_PART;
                        end
                    end
                end
                NEXT_PART: state <= LOAD_ADDR;
                SAVE_TILE: if (row_done) state <= NEXT_TILE;
                NEXT_TILE: begin
                    part_idx <= 0;
                    if (blk_c == NUM_TILES - 1) begin
                        blk_c <= 0;
                        if (blk_r == NUM_TILES - 1) state <= DONE_STATE;
                        else begin
                            blk_r <= blk_r + 1;
                            state <= RST_SA;
                        end
                    end else begin
                        blk_c <= blk_c + 1;
                        state <= RST_SA;
                    end
                end
                DONE_STATE: done <= 1'b1;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
"""

def gen_sa_controller_sparse(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module sa_controller #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_a_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_b_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_c_waddr,
    output logic [ACC_WIDTH*SA_SIZE-1:0]                   bram_c_wdata,
    output logic                                           bram_c_we,

    output logic                  sa_start,
    output logic [DATA_WIDTH-1:0] sa_mat_a     [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [DATA_WIDTH-1:0] sa_mat_b     [0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic [ACC_WIDTH-1:0]  sa_acc_result[0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic                  sa_acc_valid [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                  sa_acc_ready [0:SA_SIZE-1][0:SA_SIZE-1]
);

    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int BRAM_AW   = $clog2(MAT_SIZE * NUM_TILES);

    typedef enum logic [3:0] {{
        IDLE,
        LOAD_ADDR,
        LOAD_SA,
        CALC_START,
        CALC_FIRE,
        WAIT_SA,
        ACCUMULATE,
        SAVE_TILE,
        NEXT_PART,
        NEXT_TILE,
        DONE_STATE
    }} state_t;

    state_t state;

    int blk_r, blk_c, part_idx;
    int row_offset, col_offset, part_offset;

    always_comb begin
        row_offset  = blk_r   * SA_SIZE;
        col_offset  = blk_c   * SA_SIZE;
        part_offset = part_idx * SA_SIZE;
    end

    function automatic logic all_valid();
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                if (!sa_acc_valid[i][j]) return 0;
        return 1;
    endfunction

    logic [ACC_WIDTH-1:0] acc_buf [0:SA_SIZE-1][0:SA_SIZE-1];

    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                sa_acc_ready[i][j] = (state == ACCUMULATE)
                                   || (state == IDLE)
                                   || (state == DONE_STATE);
    end

    int row_cnt;
    logic row_done;
    assign row_done = (row_cnt == SA_SIZE - 1);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            row_cnt <= 0;
        else if (state == LOAD_SA || state == SAVE_TILE)
            row_cnt <= row_done ? 0 : row_cnt + 1;
        else
            row_cnt <= 0;
    end

    always_comb begin
        if (state == LOAD_SA && !row_done) begin
            bram_a_raddr = BRAM_AW'((row_offset  + row_cnt + 1) * NUM_TILES + part_idx);
            bram_b_raddr = BRAM_AW'((part_offset + row_cnt + 1) * NUM_TILES
                                    + (col_offset / SA_SIZE));
        end else begin
            bram_a_raddr = BRAM_AW'((row_offset  + row_cnt) * NUM_TILES + part_idx);
            bram_b_raddr = BRAM_AW'((part_offset + row_cnt) * NUM_TILES
                                    + (col_offset / SA_SIZE));
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= '0;
                    sa_mat_b[i][j] <= '0;
                end
        end else if (state == LOAD_SA && !row_done) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_mat_a[row_cnt][k] <= bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_mat_b[row_cnt][k] <= bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end else if (state == CALC_START) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_mat_a[SA_SIZE-1][k] <= bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_mat_b[SA_SIZE-1][k] <= bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end
    end

    always_comb begin
        bram_c_we    = (state == SAVE_TILE);
        bram_c_waddr = BRAM_AW'((row_offset + row_cnt) * NUM_TILES
                                + (col_offset / SA_SIZE));
        for (int k = 0; k < SA_SIZE; k++)
            bram_c_wdata[ACC_WIDTH*(k+1)-1 -: ACC_WIDTH] = acc_buf[row_cnt][k];
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            blk_r    <= 0;
            blk_c    <= 0;
            part_idx <= 0;
            sa_start <= 1'b0;
            done     <= 1'b0;
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++)
                    acc_buf[i][j] <= '0;
        end else begin
            sa_start <= 1'b0;

            case (state)
                IDLE: begin
                    blk_r    <= 0;
                    blk_c    <= 0;
                    part_idx <= 0;
                    done     <= 1'b0;
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++)
                            acc_buf[i][j] <= '0;
                    if (start)
                        state <= LOAD_ADDR;
                end

                LOAD_ADDR: state <= LOAD_SA;

                LOAD_SA: begin
                    if (row_done)
                        state <= CALC_START;
                end

                CALC_START: state <= CALC_FIRE;

                CALC_FIRE: begin
                    sa_start <= 1'b1;
                    state    <= WAIT_SA;
                end

                WAIT_SA: begin
                    if (all_valid())
                        state <= ACCUMULATE;
                end

                ACCUMULATE: begin
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++)
                            acc_buf[i][j] <= acc_buf[i][j] + sa_acc_result[i][j];

                    if (part_idx == NUM_TILES - 1)
                        state <= SAVE_TILE;
                    else begin
                        part_idx <= part_idx + 1;
                        state    <= NEXT_PART;
                    end
                end

                SAVE_TILE: begin
                    if (row_done)
                        state <= NEXT_TILE;
                end

                NEXT_PART: state <= LOAD_ADDR;

                NEXT_TILE: begin
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++)
                            acc_buf[i][j] <= '0;
                    part_idx <= 0;

                    if (blk_c == NUM_TILES - 1) begin
                        blk_c <= 0;
                        if (blk_r == NUM_TILES - 1)
                            state <= DONE_STATE;
                        else begin
                            blk_r <= blk_r + 1;
                            state <= LOAD_ADDR;
                        end
                    end else begin
                        blk_c <= blk_c + 1;
                        state <= LOAD_ADDR;
                    end
                end

                DONE_STATE: begin
                    done <= 1'b1;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
"""

def gen_sa_controller_sparse_3FSM(mat_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module sa_controller #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int MAT_SIZE   = {mat_size},
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_a_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0]                  bram_b_rdata,

    output logic [$clog2(MAT_SIZE*(MAT_SIZE/SA_SIZE))-1:0] bram_c_waddr,
    output logic [ACC_WIDTH*SA_SIZE-1:0]                   bram_c_wdata,
    output logic                                           bram_c_we,

    output logic                  sa_start,
    output logic [DATA_WIDTH-1:0] sa_mat_a     [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [DATA_WIDTH-1:0] sa_mat_b     [0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic [ACC_WIDTH-1:0]  sa_acc_result[0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic                  sa_acc_valid [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                  sa_acc_ready [0:SA_SIZE-1][0:SA_SIZE-1]
);

    localparam int NUM_TILES = MAT_SIZE / SA_SIZE;
    localparam int BRAM_AW   = $clog2(MAT_SIZE * NUM_TILES);

    typedef enum logic [2:0] {{
        LD_IDLE,
        LD_ADDR,
        LD_LOAD,
        LD_LAST_ROW,
        LD_WAIT_BUF,
        LD_DONE
    }} ld_state_t;

    typedef enum logic [2:0] {{
        CP_IDLE,
        CP_LATCH,      
        CP_FIRE,       
        CP_WAIT_SA,
        CP_ACCUMULATE,
        CP_NEXT,
        CP_DONE
    }} cp_state_t;

    typedef enum logic [1:0] {{
        S_IDLE,
        S_SAVE_TILE
    }} sstate_t;

    ld_state_t ld_state;
    cp_state_t cp_state;
    sstate_t   sstate;

    logic [DATA_WIDTH-1:0] sa_buf_a [0:1][0:SA_SIZE-1][0:SA_SIZE-1];
    logic [DATA_WIDTH-1:0] sa_buf_b [0:1][0:SA_SIZE-1][0:SA_SIZE-1];

    logic [ACC_WIDTH-1:0] acc_buf [0:1][0:SA_SIZE-1][0:SA_SIZE-1];
    logic acc_buf_sel;

    logic load_buf_sel;
    logic buf_ready [0:1];
    logic buf_consume;
    logic buf_consume_sel;

    int ld_blk_r, ld_blk_c, ld_part_idx;
    int ld_row_offset, ld_col_offset, ld_part_offset;

    always_comb begin
        ld_row_offset  = ld_blk_r    * SA_SIZE;
        ld_col_offset  = ld_blk_c    * SA_SIZE;
        ld_part_offset = ld_part_idx * SA_SIZE;
    end

    logic       cp_buf_sel;
    int         cp_tile_blk_r, cp_tile_blk_c, cp_part_idx;
    logic       cp_is_last_part;

    logic acc_valid;
    int   save_blk_r, save_blk_c;
    logic save_buf_sel;

    function automatic logic all_sa_valid();
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                if (!sa_acc_valid[i][j]) return 0;
        return 1;
    endfunction

    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                sa_acc_ready[i][j] = (cp_state == CP_ACCUMULATE)
                                   || (cp_state == CP_IDLE)
                                   || (cp_state == CP_DONE);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= '0;
                    sa_mat_b[i][j] <= '0;
                end
        end else if (cp_state == CP_LATCH) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= sa_buf_a[cp_buf_sel][i][j];
                    sa_mat_b[i][j] <= sa_buf_b[cp_buf_sel][i][j];
                end
        end
    end

    int   load_row_cnt;
    logic load_row_done;
    assign load_row_done = (load_row_cnt == SA_SIZE - 1);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            load_row_cnt <= 0;
        else if (ld_state == LD_LOAD)
            load_row_cnt <= load_row_done ? 0 : load_row_cnt + 1;
        else
            load_row_cnt <= 0;
    end

    int   save_row_cnt;
    logic save_row_done;
    assign save_row_done = (save_row_cnt == SA_SIZE - 1);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            save_row_cnt <= 0;
        else if (sstate == S_SAVE_TILE)
            save_row_cnt <= save_row_done ? 0 : save_row_cnt + 1;
        else
            save_row_cnt <= 0;
    end

    always_comb begin
        if (ld_state == LD_LOAD && !load_row_done) begin
            bram_a_raddr = BRAM_AW'((ld_row_offset  + load_row_cnt + 1) * NUM_TILES + ld_part_idx);
            bram_b_raddr = BRAM_AW'((ld_part_offset + load_row_cnt + 1) * NUM_TILES
                                    + (ld_col_offset / SA_SIZE));
        end else begin
            bram_a_raddr = BRAM_AW'((ld_row_offset  + load_row_cnt) * NUM_TILES + ld_part_idx);
            bram_b_raddr = BRAM_AW'((ld_part_offset + load_row_cnt) * NUM_TILES
                                    + (ld_col_offset / SA_SIZE));
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int b = 0; b < 2; b++)
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++) begin
                        sa_buf_a[b][i][j] <= '0;
                        sa_buf_b[b][i][j] <= '0;
                    end
        end else if (ld_state == LD_LOAD && !load_row_done) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_buf_a[load_buf_sel][load_row_cnt][k] <=
                    bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_buf_b[load_buf_sel][load_row_cnt][k] <=
                    bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end else if (ld_state == LD_LAST_ROW) begin
            for (int k = 0; k < SA_SIZE; k++) begin
                sa_buf_a[load_buf_sel][SA_SIZE-1][k] <=
                    bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
                sa_buf_b[load_buf_sel][SA_SIZE-1][k] <=
                    bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            end
        end
    end

    always_comb begin
        bram_c_we    = (sstate == S_SAVE_TILE);
        bram_c_waddr = BRAM_AW'((save_blk_r * SA_SIZE + save_row_cnt) * NUM_TILES
                                + save_blk_c);
        for (int k = 0; k < SA_SIZE; k++)
            bram_c_wdata[ACC_WIDTH*(k+1)-1 -: ACC_WIDTH] =
                acc_buf[save_buf_sel][save_row_cnt][k];
    end

    int   next_ld_blk_r, next_ld_blk_c, next_ld_part_idx;
    logic next_ld_is_done;

    always_comb begin
        next_ld_blk_r    = ld_blk_r;
        next_ld_blk_c    = ld_blk_c;
        next_ld_part_idx = ld_part_idx + 1;
        next_ld_is_done  = 1'b0;

        if (ld_part_idx == NUM_TILES - 1) begin
            next_ld_part_idx = 0;
            if (ld_blk_c == NUM_TILES - 1) begin
                next_ld_blk_c = 0;
                if (ld_blk_r == NUM_TILES - 1)
                    next_ld_is_done = 1'b1;
                else
                    next_ld_blk_r = ld_blk_r + 1;
            end else begin
                next_ld_blk_c = ld_blk_c + 1;
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ld_state     <= LD_IDLE;
            ld_blk_r     <= 0;
            ld_blk_c     <= 0;
            ld_part_idx  <= 0;
            load_buf_sel <= 1'b0;
            buf_ready[0] <= 1'b0;
            buf_ready[1] <= 1'b0;
        end else begin

            if (buf_consume)
                buf_ready[buf_consume_sel] <= 1'b0;

            case (ld_state)
                LD_IDLE: begin
                    ld_blk_r     <= 0;
                    ld_blk_c     <= 0;
                    ld_part_idx  <= 0;
                    load_buf_sel <= 1'b0;
                    buf_ready[0] <= 1'b0;
                    buf_ready[1] <= 1'b0;
                    if (start)
                        ld_state <= LD_ADDR;
                end

                LD_ADDR:
                    ld_state <= LD_LOAD;

                LD_LOAD:
                    if (load_row_done)
                        ld_state <= LD_LAST_ROW;

                LD_LAST_ROW: begin
                    buf_ready[load_buf_sel] <= 1'b1;

                    ld_part_idx <= next_ld_part_idx;
                    ld_blk_r    <= next_ld_blk_r;
                    ld_blk_c    <= next_ld_blk_c;

                    if (next_ld_is_done) begin
                        ld_state <= LD_DONE;
                    end else begin
                        load_buf_sel <= ~load_buf_sel;
                        if (!buf_ready[~load_buf_sel]
                            || (buf_consume && buf_consume_sel == ~load_buf_sel))
                            ld_state <= LD_ADDR;
                        else
                            ld_state <= LD_WAIT_BUF;
                    end
                end

                LD_WAIT_BUF: begin
                    if (!buf_ready[load_buf_sel]
                        || (buf_consume && buf_consume_sel == load_buf_sel))
                        ld_state <= LD_ADDR;
                end

                LD_DONE: begin
                end

                default: ld_state <= LD_IDLE;
            endcase
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cp_state        <= CP_IDLE;
            cp_buf_sel      <= 1'b0;
            cp_tile_blk_r   <= 0;
            cp_tile_blk_c   <= 0;
            cp_part_idx     <= 0;
            cp_is_last_part <= 1'b0;
            sa_start        <= 1'b0;
            acc_valid       <= 1'b0;
            done            <= 1'b0;
            acc_buf_sel     <= 1'b0;
            save_buf_sel    <= 1'b0;
            save_blk_r      <= 0;
            save_blk_c      <= 0;
            buf_consume     <= 1'b0;
            buf_consume_sel <= 1'b0;
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    acc_buf[0][i][j] <= '0;
                    acc_buf[1][i][j] <= '0;
                end
        end else begin
            sa_start    <= 1'b0;
            acc_valid   <= 1'b0;
            buf_consume <= 1'b0;

            case (cp_state)
                CP_IDLE: begin
                    cp_tile_blk_r <= 0;
                    cp_tile_blk_c <= 0;
                    cp_part_idx   <= 0;
                    cp_buf_sel    <= 1'b0;
                    acc_buf_sel   <= 1'b0;
                    done          <= 1'b0;
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++) begin
                            acc_buf[0][i][j] <= '0;
                            acc_buf[1][i][j] <= '0;
                        end
                    if (buf_ready[0])
                        cp_state <= CP_LATCH;
                end

                CP_LATCH: begin
                    buf_consume     <= 1'b1;
                    buf_consume_sel <= cp_buf_sel;
                    cp_is_last_part <= (cp_part_idx == NUM_TILES - 1);
                    cp_state        <= CP_FIRE;
                end

                CP_FIRE: begin
                    sa_start <= 1'b1;
                    cp_state <= CP_WAIT_SA;
                end

                CP_WAIT_SA: begin
                    if (all_sa_valid())
                        cp_state <= CP_ACCUMULATE;
                end

                CP_ACCUMULATE: begin
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++)
                            acc_buf[acc_buf_sel][i][j] <=
                                acc_buf[acc_buf_sel][i][j] + sa_acc_result[i][j];

                    if (cp_is_last_part) begin
                        acc_valid    <= 1'b1;
                        save_buf_sel <= acc_buf_sel;
                        save_blk_r   <= cp_tile_blk_r;
                        save_blk_c   <= cp_tile_blk_c;
                        acc_buf_sel  <= ~acc_buf_sel;
                    end

                    cp_buf_sel <= ~cp_buf_sel;
                    cp_state   <= CP_NEXT;
                end

                CP_NEXT: begin
                    if (cp_is_last_part) begin
                        for (int i = 0; i < SA_SIZE; i++)
                            for (int j = 0; j < SA_SIZE; j++)
                                acc_buf[acc_buf_sel][i][j] <= '0;

                        cp_part_idx <= 0;

                        if (cp_tile_blk_c == NUM_TILES - 1) begin
                            cp_tile_blk_c <= 0;
                            if (cp_tile_blk_r == NUM_TILES - 1) begin
                                cp_state <= CP_DONE;
                            end else begin
                                cp_tile_blk_r <= cp_tile_blk_r + 1;
                                if (buf_ready[cp_buf_sel])
                                    cp_state <= CP_LATCH;
                            end
                        end else begin
                            cp_tile_blk_c <= cp_tile_blk_c + 1;
                            if (buf_ready[cp_buf_sel])
                                cp_state <= CP_LATCH;
                        end
                    end else begin
                        cp_part_idx <= cp_part_idx + 1;
                        if (buf_ready[cp_buf_sel])
                            cp_state <= CP_LATCH;
                    end
                end

                CP_DONE: begin
                    if (sstate == S_IDLE)
                        done <= 1'b1;
                end

                default: cp_state <= CP_IDLE;
            endcase
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sstate <= S_IDLE;
        end else begin
            case (sstate)
                S_IDLE:
                    if (acc_valid)
                        sstate <= S_SAVE_TILE;

                S_SAVE_TILE:
                    if (save_row_done)
                        sstate <= S_IDLE;

                default: sstate <= S_IDLE;
            endcase
        end
    end

endmodule
"""

def gen_sa_controller_final(m_size: int, k_size: int, n_size: int, sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module sa_controller #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B)
    parameter int OUT_WIDTH  = 16,   // output element width (BRAM_C / norm_data)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = {m_size},   // rows of A, rows of C
    parameter int K_SIZE     = {k_size},   // cols of A = rows of B (inner dimension)
    parameter int N_SIZE     = {n_size},   // cols of B, cols of C
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic done,

    // BRAM_A read  (M_SIZE x K_SIZE, tiled)
    output logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((K_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] bram_a_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0] bram_a_rdata,
    input  logic [SA_SIZE-1:0]            bram_a_rbv,

    // BRAM_B read  (K_SIZE x N_SIZE, tiled)
    output logic [$clog2(SA_SIZE*((K_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] bram_b_raddr,
    input  logic [DATA_WIDTH*SA_SIZE-1:0] bram_b_rdata,
    input  logic [SA_SIZE-1:0]            bram_b_rbv,

    // BRAM_C write  (M_SIZE x N_SIZE, tiled, OUT_WIDTH per element)
    output logic [$clog2(SA_SIZE*((M_SIZE+SA_SIZE-1)/SA_SIZE)*((N_SIZE+SA_SIZE-1)/SA_SIZE))-1:0] bram_c_waddr,
    output logic [OUT_WIDTH*SA_SIZE-1:0]  bram_c_wdata,
    output logic                          bram_c_we,

    // activation_unit / norm_pool interface
    output logic                 accum_valid_out,
    input  logic                 norm_done,
    input  logic [OUT_WIDTH-1:0] norm_data      [0:SA_SIZE-1][0:SA_SIZE-1],

    // Accumulator bank
    output logic                 accum_wr_en,
    output logic                 accum_wr_sel,
    output logic [ACC_WIDTH-1:0] accum_wr_data[0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                 accum_clr_en,
    output logic                 accum_clr_sel,
    input  logic [ACC_WIDTH-1:0] accum_rd_data[0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                 accum_rd_sel,

    // SA array
    output logic                  sa_start,
    output logic [DATA_WIDTH-1:0] sa_mat_a     [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [DATA_WIDTH-1:0] sa_mat_b     [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [   SA_SIZE-1:0] sa_mat_a_bv  [0:SA_SIZE-1],
    output logic [   SA_SIZE-1:0] sa_mat_b_bv  [0:SA_SIZE-1],
    input  logic [ ACC_WIDTH-1:0] sa_acc_result[0:SA_SIZE-1][0:SA_SIZE-1],
    input  logic                  sa_acc_valid [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                  sa_acc_ready [0:SA_SIZE-1][0:SA_SIZE-1]
);

    // =========================================================
    // Tile counts and address widths
    // =========================================================
    localparam int M_TILES = (M_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int K_TILES = (K_SIZE + SA_SIZE - 1) / SA_SIZE;
    localparam int N_TILES = (N_SIZE + SA_SIZE - 1) / SA_SIZE;

    localparam int BRAM_A_AW = $clog2(SA_SIZE * M_TILES * K_TILES);
    localparam int BRAM_B_AW = $clog2(SA_SIZE * K_TILES * N_TILES);
    localparam int BRAM_C_AW = $clog2(SA_SIZE * M_TILES * N_TILES);

    // Counter widths per dimension (at least 1 bit)
    localparam int M_TILE_W = (M_TILES > 1) ? $clog2(M_TILES) : 1;
    localparam int K_TILE_W = (K_TILES > 1) ? $clog2(K_TILES) : 1;
    localparam int N_TILE_W = (N_TILES > 1) ? $clog2(N_TILES) : 1;

    // =========================================================
    // FSM state types
    // =========================================================
    typedef enum logic [2:0] {{
        LD_IDLE, LD_ADDR, LD_LOAD, LD_LAST_ROW, LD_WAIT_BUF, LD_DONE
    }} ld_state_t;

    typedef enum logic [2:0] {{
        CP_IDLE, CP_LATCH, CP_FIRE, CP_WAIT_SA,
        CP_ACCUMULATE, CP_NEXT, CP_DONE
    }} cp_state_t;

    typedef enum logic [1:0] {{
        S_IDLE, S_WAIT_NORM, S_SAVE_TILE
    }} sstate_t;

    ld_state_t ld_state;
    cp_state_t cp_state;
    sstate_t   sstate;

    // =========================================================
    // Ping-pong input buffers
    // =========================================================
    logic [DATA_WIDTH-1:0] sa_buf_a    [0:1][0:SA_SIZE-1][0:SA_SIZE-1];
    logic [DATA_WIDTH-1:0] sa_buf_b    [0:1][0:SA_SIZE-1][0:SA_SIZE-1];
    logic [SA_SIZE-1:0]    sa_buf_a_bv [0:1][0:SA_SIZE-1];
    logic [SA_SIZE-1:0]    sa_buf_b_bv [0:1][0:SA_SIZE-1];

    logic load_buf_sel;
    logic buf_ready     [0:1];
    logic buf_consume;
    logic buf_consume_sel;

    // =========================================================
    // Tile counters (separate widths per dimension)
    // =========================================================
    logic [M_TILE_W-1:0] ld_blk_r;
    logic [N_TILE_W-1:0] ld_blk_c;
    logic [K_TILE_W-1:0] ld_part_idx;

    logic [M_TILE_W-1:0] cp_tile_blk_r;
    logic [N_TILE_W-1:0] cp_tile_blk_c;
    logic [K_TILE_W-1:0] cp_part_idx;

    logic [M_TILE_W-1:0] save_blk_r;
    logic [N_TILE_W-1:0] save_blk_c;

    logic [$clog2(SA_SIZE)-1:0] load_row_cnt;
    logic [$clog2(SA_SIZE)-1:0] save_row_cnt;

    logic load_row_done, save_row_done;
    assign load_row_done = (load_row_cnt == $clog2(SA_SIZE)'(SA_SIZE - 1));
    assign save_row_done = (save_row_cnt == $clog2(SA_SIZE)'(SA_SIZE - 1));

    logic cp_buf_sel, cp_is_last_part;
    logic acc_valid_pulse;
    logic save_buf_sel, acc_buf_sel;

    logic cp_next_advanced;

    // =========================================================
    // [Method 2] Tile-level zero-skip
    // =========================================================
    logic any_a_nz, any_b_nz;
    always_comb begin
        any_a_nz = 1'b0; any_b_nz = 1'b0;
        for (int i = 0; i < SA_SIZE; i++) begin
            any_a_nz |= |sa_mat_a_bv[i];
            any_b_nz |= |sa_mat_b_bv[i];
        end
    end

    function automatic logic all_sa_valid();
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                if (sa_acc_valid[i][j] !== 1'b1) return 0;
        return 1;
    endfunction

    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                sa_acc_ready[i][j] = (cp_state == CP_ACCUMULATE)
                                   || (cp_state == CP_IDLE)
                                   || (cp_state == CP_DONE);
    end

    // =========================================================
    // Latch SA inputs in CP_LATCH
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= '0; sa_mat_b[i][j] <= '0;
                end
            for (int i = 0; i < SA_SIZE; i++) begin
                sa_mat_a_bv[i] <= '0; sa_mat_b_bv[i] <= '0;
            end
        end else if (cp_state == CP_LATCH) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) begin
                    sa_mat_a[i][j] <= sa_buf_a[cp_buf_sel][i][j];
                    sa_mat_b[i][j] <= sa_buf_b[cp_buf_sel][i][j];
                end
            for (int i = 0; i < SA_SIZE; i++) begin
                sa_mat_a_bv[i] <= sa_buf_a_bv[cp_buf_sel][i];
                sa_mat_b_bv[i] <= sa_buf_b_bv[cp_buf_sel][i];
            end
        end
    end

    // =========================================================
    // Row counters
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) load_row_cnt <= '0;
        else if (ld_state == LD_LOAD) load_row_cnt <= load_row_done ? '0 : load_row_cnt + 1;
        else load_row_cnt <= '0;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) save_row_cnt <= '0;
        else if (sstate == S_SAVE_TILE) save_row_cnt <= save_row_done ? '0 : save_row_cnt + 1;
        else save_row_cnt <= '0;
    end

    // =========================================================
    // BRAM read addresses (look-ahead by 1 for 1-cycle latency)
    //
    // BRAM_A: addr = (ld_blk_r * SA_SIZE + row) * K_TILES + ld_part_idx
    // BRAM_B: addr = (ld_part_idx * SA_SIZE + row) * N_TILES + ld_blk_c
    // =========================================================
    always_comb begin
        if (ld_state == LD_LOAD && !load_row_done) begin
            bram_a_raddr = BRAM_A_AW'((BRAM_A_AW'(ld_blk_r)   * BRAM_A_AW'(SA_SIZE) + BRAM_A_AW'(load_row_cnt) + BRAM_A_AW'(1)) * BRAM_A_AW'(K_TILES) + BRAM_A_AW'(ld_part_idx));
            bram_b_raddr = BRAM_B_AW'((BRAM_B_AW'(ld_part_idx) * BRAM_B_AW'(SA_SIZE) + BRAM_B_AW'(load_row_cnt) + BRAM_B_AW'(1)) * BRAM_B_AW'(N_TILES) + BRAM_B_AW'(ld_blk_c));
        end else begin
            bram_a_raddr = BRAM_A_AW'((BRAM_A_AW'(ld_blk_r)   * BRAM_A_AW'(SA_SIZE) + BRAM_A_AW'(load_row_cnt)) * BRAM_A_AW'(K_TILES) + BRAM_A_AW'(ld_part_idx));
            bram_b_raddr = BRAM_B_AW'((BRAM_B_AW'(ld_part_idx) * BRAM_B_AW'(SA_SIZE) + BRAM_B_AW'(load_row_cnt)) * BRAM_B_AW'(N_TILES) + BRAM_B_AW'(ld_blk_c));
        end
    end

    // =========================================================
    // Ping-pong buffer fill
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int b = 0; b < 2; b++)
                for (int i = 0; i < SA_SIZE; i++) begin
                    for (int j = 0; j < SA_SIZE; j++) begin
                        sa_buf_a[b][i][j] <= '0; sa_buf_b[b][i][j] <= '0;
                    end
                    sa_buf_a_bv[b][i] <= '0; sa_buf_b_bv[b][i] <= '0;
                end
        end else if (ld_state == LD_LOAD && !load_row_done) begin
            if (bram_a_rbv == '0)
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_a[load_buf_sel][load_row_cnt][k] <= '0;
            else
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_a[load_buf_sel][load_row_cnt][k] <=
                        bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            sa_buf_a_bv[load_buf_sel][load_row_cnt] <= bram_a_rbv;

            if (bram_b_rbv == '0)
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_b[load_buf_sel][load_row_cnt][k] <= '0;
            else
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_b[load_buf_sel][load_row_cnt][k] <=
                        bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            sa_buf_b_bv[load_buf_sel][load_row_cnt] <= bram_b_rbv;

        end else if (ld_state == LD_LAST_ROW) begin
            if (bram_a_rbv == '0)
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_a[load_buf_sel][SA_SIZE-1][k] <= '0;
            else
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_a[load_buf_sel][SA_SIZE-1][k] <=
                        bram_a_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            sa_buf_a_bv[load_buf_sel][SA_SIZE-1] <= bram_a_rbv;

            if (bram_b_rbv == '0)
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_b[load_buf_sel][SA_SIZE-1][k] <= '0;
            else
                for (int k = 0; k < SA_SIZE; k++)
                    sa_buf_b[load_buf_sel][SA_SIZE-1][k] <=
                        bram_b_rdata[DATA_WIDTH*(k+1)-1 -: DATA_WIDTH];
            sa_buf_b_bv[load_buf_sel][SA_SIZE-1] <= bram_b_rbv;
        end
    end

    // =========================================================
    // Next-tile address (combinational)
    // Iteration order: ld_part_idx (K) -> ld_blk_c (N) -> ld_blk_r (M)
    // =========================================================
    logic [M_TILE_W-1:0] next_ld_blk_r;
    logic [N_TILE_W-1:0] next_ld_blk_c;
    logic [K_TILE_W-1:0] next_ld_part_idx;
    logic                next_ld_is_done;

    always_comb begin
        next_ld_blk_r    = ld_blk_r;
        next_ld_blk_c    = ld_blk_c;
        next_ld_part_idx = ld_part_idx + 1;
        next_ld_is_done  = 1'b0;

        if (ld_part_idx == K_TILE_W'(K_TILES - 1)) begin
            next_ld_part_idx = '0;
            if (ld_blk_c == N_TILE_W'(N_TILES - 1)) begin
                next_ld_blk_c = '0;
                if (ld_blk_r == M_TILE_W'(M_TILES - 1))
                    next_ld_is_done = 1'b1;
                else
                    next_ld_blk_r = ld_blk_r + 1;
            end else
                next_ld_blk_c = ld_blk_c + 1;
        end
    end

    // =========================================================
    // Load FSM
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ld_state     <= LD_IDLE;
            ld_blk_r     <= '0; ld_blk_c <= '0; ld_part_idx <= '0;
            load_buf_sel <= 1'b0;
            buf_ready[0] <= 1'b0; buf_ready[1] <= 1'b0;
        end else begin
            if (buf_consume) buf_ready[buf_consume_sel] <= 1'b0;

            case (ld_state)
                LD_IDLE: begin
                    ld_blk_r <= '0; ld_blk_c <= '0; ld_part_idx <= '0;
                    load_buf_sel <= 1'b0;
                    buf_ready[0] <= 1'b0; buf_ready[1] <= 1'b0;
                    if (start) ld_state <= LD_ADDR;
                end
                LD_ADDR:  ld_state <= LD_LOAD;
                LD_LOAD:  if (load_row_done) ld_state <= LD_LAST_ROW;
                LD_LAST_ROW: begin
                    buf_ready[load_buf_sel] <= 1'b1;
                    ld_part_idx <= next_ld_part_idx;
                    ld_blk_r    <= next_ld_blk_r;
                    ld_blk_c    <= next_ld_blk_c;
                    if (next_ld_is_done) begin
                        ld_state <= LD_DONE;
                    end else begin
                        load_buf_sel <= ~load_buf_sel;
                        if (!buf_ready[~load_buf_sel]
                            || (buf_consume && buf_consume_sel == ~load_buf_sel))
                            ld_state <= LD_ADDR;
                        else
                            ld_state <= LD_WAIT_BUF;
                    end
                end
                LD_WAIT_BUF:
                    if (!buf_ready[load_buf_sel]
                        || (buf_consume && buf_consume_sel == load_buf_sel))
                        ld_state <= LD_ADDR;
                LD_DONE: begin end
                default: ld_state <= LD_IDLE;
            endcase
        end
    end

    // =========================================================
    // Compute FSM
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cp_state <= CP_IDLE; cp_buf_sel <= 1'b0;
            cp_tile_blk_r <= '0; cp_tile_blk_c <= '0; cp_part_idx <= '0;
            cp_is_last_part <= 1'b0;
            sa_start <= 1'b0; acc_valid_pulse <= 1'b0; done <= 1'b0;
            acc_buf_sel <= 1'b0; save_buf_sel <= 1'b0;
            save_blk_r <= '0; save_blk_c <= '0;
            buf_consume <= 1'b0; buf_consume_sel <= 1'b0;
            accum_wr_en <= 1'b0; accum_clr_en <= 1'b0;
            accum_wr_sel <= 1'b0; accum_clr_sel <= 1'b0;
            cp_next_advanced <= 1'b0;
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++) accum_wr_data[i][j] <= '0;
        end else begin
            sa_start <= 1'b0; acc_valid_pulse <= 1'b0;
            buf_consume <= 1'b0;
            accum_wr_en <= 1'b0; accum_clr_en <= 1'b0;

            case (cp_state)
                CP_IDLE: begin
                    cp_tile_blk_r <= '0; cp_tile_blk_c <= '0; cp_part_idx <= '0;
                    cp_buf_sel <= 1'b0; acc_buf_sel <= 1'b0; done <= 1'b0;
                    if (buf_ready[0]) cp_state <= CP_LATCH;
                end
                CP_LATCH: begin
                    buf_consume <= 1'b1; buf_consume_sel <= cp_buf_sel;
                    cp_is_last_part <= (cp_part_idx == K_TILE_W'(K_TILES - 1));
                    cp_state <= CP_FIRE;
                end
                CP_FIRE: begin
                    if (!any_a_nz || !any_b_nz) begin
                        if (cp_is_last_part) begin
                            acc_valid_pulse <= 1'b1;
                            save_buf_sel <= acc_buf_sel;
                            save_blk_r   <= cp_tile_blk_r;
                            save_blk_c   <= cp_tile_blk_c;
                            acc_buf_sel  <= ~acc_buf_sel;
                        end
                        cp_buf_sel <= ~cp_buf_sel;
                        cp_next_advanced <= 1'b0;
                        cp_state <= CP_NEXT;
                    end else begin
                        sa_start <= 1'b1; cp_state <= CP_WAIT_SA;
                    end
                end
                CP_WAIT_SA: if (all_sa_valid()) cp_state <= CP_ACCUMULATE;
                CP_ACCUMULATE: begin
                    accum_wr_en <= 1'b1; accum_wr_sel <= acc_buf_sel;
                    for (int i = 0; i < SA_SIZE; i++)
                        for (int j = 0; j < SA_SIZE; j++)
                            accum_wr_data[i][j] <= sa_acc_result[i][j];
                    if (cp_is_last_part) begin
                        acc_valid_pulse <= 1'b1;
                        save_buf_sel <= acc_buf_sel;
                        save_blk_r   <= cp_tile_blk_r;
                        save_blk_c   <= cp_tile_blk_c;
                        acc_buf_sel  <= ~acc_buf_sel;
                    end
                    cp_buf_sel <= ~cp_buf_sel;
                    cp_next_advanced <= 1'b0;
                    cp_state <= CP_NEXT;
                end
                CP_NEXT: begin
                    // CP_NEXT may need to wait for loader (buf_ready).
                    // Advance part/tile counters exactly once per part.
                    if (!cp_next_advanced) begin
                        cp_next_advanced <= 1'b1;

                        if (cp_is_last_part) begin
                            accum_clr_en <= 1'b1; accum_clr_sel <= save_buf_sel;
                            cp_part_idx  <= '0;
                            if (cp_tile_blk_c == N_TILE_W'(N_TILES - 1)) begin
                                cp_tile_blk_c <= '0;
                                if (cp_tile_blk_r == M_TILE_W'(M_TILES - 1)) begin
                                    cp_state <= CP_DONE;
                                end else begin
                                    cp_tile_blk_r <= cp_tile_blk_r + 1;
                                    if (buf_ready[cp_buf_sel]) begin
                                        cp_next_advanced <= 1'b0;
                                        cp_state <= CP_LATCH;
                                    end
                                end
                            end else begin
                                cp_tile_blk_c <= cp_tile_blk_c + 1;
                                if (buf_ready[cp_buf_sel]) begin
                                    cp_next_advanced <= 1'b0;
                                    cp_state <= CP_LATCH;
                                end
                            end
                        end else begin
                            cp_part_idx <= cp_part_idx + 1;
                            if (buf_ready[cp_buf_sel]) begin
                                cp_next_advanced <= 1'b0;
                                cp_state <= CP_LATCH;
                            end
                        end
                    end else begin
                        if (buf_ready[cp_buf_sel]) begin
                            cp_next_advanced <= 1'b0;
                            cp_state <= CP_LATCH;
                        end
                    end
                end
                CP_DONE: if (sstate == S_IDLE) done <= 1'b1;
                default: cp_state <= CP_IDLE;
            endcase
        end
    end

    assign accum_rd_sel = save_buf_sel;

    // =========================================================
    // Save FSM
    // S_IDLE      : wait for acc_valid_pulse
    // S_WAIT_NORM : pulse accum_valid_out -> wait norm_done
    // S_SAVE_TILE : write norm_data row-by-row to BRAM_C
    // =========================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sstate          <= S_IDLE;
            accum_valid_out <= 1'b0;
        end else begin
            accum_valid_out <= 1'b0;
            case (sstate)
                S_IDLE:
                    if (acc_valid_pulse) begin
                        accum_valid_out <= 1'b1;
                        sstate          <= S_WAIT_NORM;
                    end
                S_WAIT_NORM:
                    if (norm_done) sstate <= S_SAVE_TILE;
                S_SAVE_TILE:
                    if (save_row_done) sstate <= S_IDLE;
                default: sstate <= S_IDLE;
            endcase
        end
    end
    // BRAM_C write address: (save_blk_r * SA_SIZE + save_row_cnt) * N_TILES + save_blk_c
    always_comb begin
        bram_c_we    = (sstate == S_SAVE_TILE);
        bram_c_waddr = BRAM_C_AW'(
                           (BRAM_C_AW'(save_blk_r) * BRAM_C_AW'(SA_SIZE) + BRAM_C_AW'(save_row_cnt))
                           * BRAM_C_AW'(N_TILES)
                           + BRAM_C_AW'(save_blk_c)
                       );
        for (int k = 0; k < SA_SIZE; k++)
            bram_c_wdata[OUT_WIDTH*(k+1)-1 -: OUT_WIDTH] = norm_data[save_row_cnt][k];
    end

endmodule
"""


def gen_single_pe_non_sparse() -> str:
    return f"""`timescale 1ns / 1ps
module single_PE #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32 //이거 20비트면 될거같은데 부호 추가되면 또 달라져서 걍 넉넉하게 32비트 잡아놓음 나중에 최적화하자(윤한)
)(
    input  logic                   clk,
    input  logic                   rst_n,

    input  logic [DATA_WIDTH-1:0]  in_a,
    input  logic [DATA_WIDTH-1:0]  in_b,
    input  logic                   valid_in, //valid 0이면 그냥 값 다음 PE로 넘기는데 다음 PE가 알아서 valid 0인거 보고 버려버림 

    output logic [DATA_WIDTH-1:0]  out_a, //input a넘기는 레지스터
    output logic [DATA_WIDTH-1:0]  out_b, //input b넘기는 레지스터
    output logic [ACC_WIDTH-1:0]   acc_out, //누산기
    output logic                   valid_out //valid 신호 valid_in그대로 넘기기 
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_a     <= '0;
            out_b     <= '0;
            acc_out   <= '0;
            valid_out <= 1'b0;
        end else begin
            out_a     <= in_a;
            out_b     <= in_b;
            valid_out <= valid_in;

            if (valid_in) begin
                acc_out <= acc_out + (in_a * in_b);
            end
        end
    end

endmodule
"""

def gen_single_pe_sparse(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
module sparse_single_PE #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int BV_WIDTH   = {sa_size},
    parameter int FIFO_DEPTH = 2
)(
    input  logic clk,
    input  logic rst_n,

    input  logic [DATA_WIDTH-1:0] act_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   act_bv_in,
    input  logic                  act_valid,
    output logic                  act_ready,

    output logic [DATA_WIDTH-1:0] act_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   act_bv_out,
    output logic                  act_valid_out,
    input  logic                  act_ready_in,

    input  logic [DATA_WIDTH-1:0] wgt_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   wgt_bv_in,
    input  logic                  wgt_valid,
    output logic                  wgt_ready,

    output logic [DATA_WIDTH-1:0] wgt_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   wgt_bv_out,
    output logic                  wgt_valid_out,
    input  logic                  wgt_ready_in,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    input  logic                  psum_valid_in,
    output logic                  psum_ready_out,

    output logic [ACC_WIDTH-1:0]  psum_out,
    output logic                  psum_valid_out,
    input  logic                  psum_ready_in
);

    typedef enum logic [1:0] {{IDLE, CALC}} state_t;
    state_t state;

    logic [DATA_WIDTH-1:0] act_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   act_bv_buf;
    logic [DATA_WIDTH-1:0] wgt_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   wgt_bv_buf;

    logic [BV_WIDTH-1:0]   match_remain;
    logic [ACC_WIDTH-1:0]  acc_reg;

    localparam int BV_IDX_W = $clog2(BV_WIDTH);

    function automatic logic [BV_IDX_W-1:0] find_lsb(input logic [BV_WIDTH-1:0] bv);
        for (int i = 0; i < BV_WIDTH; i++)
            if (bv[i]) return BV_IDX_W'(i);
        return '0;
    endfunction

    function automatic logic [BV_IDX_W-1:0] popcount_below(input logic [BV_WIDTH-1:0] bv, input logic [BV_IDX_W-1:0] pos);
        logic [BV_IDX_W-1:0] cnt;
        cnt = 0;
        for (int i = 0; i < BV_WIDTH; i++)
            if (BV_IDX_W'(i) < pos && bv[i]) cnt = cnt + 1;
        return cnt;
    endfunction

    logic [BV_IDX_W-1:0] cur_bit;
    logic [BV_IDX_W-1:0] act_idx, wgt_idx;
    logic [BV_WIDTH-1:0] cur_bit_mask;
    logic [BV_WIDTH-1:0] next_match;

    assign cur_bit      = find_lsb(match_remain);
    assign act_idx      = popcount_below(act_bv_buf, cur_bit);
    assign wgt_idx      = popcount_below(wgt_bv_buf, cur_bit);
    assign cur_bit_mask = BV_WIDTH'(1) << cur_bit;
    assign next_match   = match_remain & ~cur_bit_mask;

    localparam int FIFO_PTR_W = $clog2(FIFO_DEPTH);

    logic [ACC_WIDTH-1:0]    fifo_mem   [0:FIFO_DEPTH-1];
    logic [FIFO_PTR_W:0]     fifo_count;
    logic [FIFO_PTR_W-1:0]   fifo_wr_ptr, fifo_rd_ptr;
    logic                    fifo_full, fifo_empty;
    logic                    fifo_wr_en;
    logic [ACC_WIDTH-1:0]    fifo_wr_data;

    assign fifo_full  = (fifo_count == (FIFO_PTR_W+1)'(FIFO_DEPTH));
    assign fifo_empty = (fifo_count == '0);

    assign psum_out       = fifo_mem[fifo_rd_ptr];
    assign psum_valid_out = !fifo_empty;

    wire fifo_do_push = fifo_wr_en && !fifo_full;
    wire fifo_do_pop  = psum_ready_in && !fifo_empty;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fifo_count  <= '0;
            fifo_wr_ptr <= '0;
            fifo_rd_ptr <= '0;
            for (int i = 0; i < FIFO_DEPTH; i++)
                fifo_mem[i] <= '0;
        end else begin
            if (fifo_do_push) begin
                fifo_mem[fifo_wr_ptr] <= fifo_wr_data;
                fifo_wr_ptr           <= fifo_wr_ptr + 1;
            end
            if (fifo_do_pop)
                fifo_rd_ptr <= fifo_rd_ptr + 1;

            if      (fifo_do_push && !fifo_do_pop) fifo_count <= fifo_count + 1;
            else if (!fifo_do_push && fifo_do_pop) fifo_count <= fifo_count - 1;
        end
    end

    wire can_accept = (state == IDLE)
                   && act_valid && wgt_valid && psum_valid_in
                   && !fifo_full
                   && !act_valid_out && !wgt_valid_out;

    assign act_ready      = can_accept;
    assign wgt_ready      = can_accept;
    assign psum_ready_out = can_accept;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            acc_reg       <= '0;
            match_remain  <= '0;
            fifo_wr_en    <= 1'b0;
            fifo_wr_data  <= '0;
            act_valid_out <= 1'b0;
            wgt_valid_out <= 1'b0;
            act_bv_buf    <= '0;
            wgt_bv_buf    <= '0;
            act_bv_out    <= '0;
            wgt_bv_out    <= '0;
            for (int i = 0; i < BV_WIDTH; i++) begin
                act_buf[i]    <= '0;
                wgt_buf[i]    <= '0;
                act_nz_out[i] <= '0;
                wgt_nz_out[i] <= '0;
            end
        end else begin
            fifo_wr_en <= 1'b0;

            if (act_valid_out && act_ready_in) act_valid_out <= 1'b0;
            if (wgt_valid_out && wgt_ready_in) wgt_valid_out <= 1'b0;

            case (state)
                IDLE: begin
                    if (can_accept) begin
                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_buf[i] <= act_nz_in[i];
                            wgt_buf[i] <= wgt_nz_in[i];
                        end
                        act_bv_buf <= act_bv_in;
                        wgt_bv_buf <= wgt_bv_in;
                        acc_reg    <= psum_in;

                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_nz_out[i] <= act_nz_in[i];
                            wgt_nz_out[i] <= wgt_nz_in[i];
                        end
                        act_bv_out    <= act_bv_in;
                        wgt_bv_out    <= wgt_bv_in;
                        act_valid_out <= 1'b1;
                        wgt_valid_out <= 1'b1;

                        if ((act_bv_in & wgt_bv_in) == '0) begin
                            fifo_wr_en   <= 1'b1;
                            fifo_wr_data <= psum_in;
                        end else begin
                            match_remain <= act_bv_in & wgt_bv_in;
                            state        <= CALC;
                        end
                    end
                end

                CALC: begin
                    acc_reg      <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                    match_remain <= next_match;

                    if (next_match == '0) begin
                        fifo_wr_en   <= 1'b1;
                        fifo_wr_data <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                        state        <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
"""


def gen_single_pe_sparse_clock_gating(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps

// `define FPGA_TARGET
// If targeting FPGA, uncomment the above line and adjust the code below for clock gating.
module sparse_single_PE #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int BV_WIDTH   = {sa_size},
    parameter int FIFO_DEPTH = 2
)(
    input  logic clk,
    input  logic rst_n,

    input  logic [DATA_WIDTH-1:0] act_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   act_bv_in,
    input  logic                  act_valid,
    output logic                  act_ready,

    output logic [DATA_WIDTH-1:0] act_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   act_bv_out,
    output logic                  act_valid_out,
    input  logic                  act_ready_in,

    input  logic [DATA_WIDTH-1:0] wgt_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   wgt_bv_in,
    input  logic                  wgt_valid,
    output logic                  wgt_ready,

    output logic [DATA_WIDTH-1:0] wgt_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   wgt_bv_out,
    output logic                  wgt_valid_out,
    input  logic                  wgt_ready_in,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    input  logic                  psum_valid_in,
    output logic                  psum_ready_out,

    output logic [ACC_WIDTH-1:0]  psum_out,
    output logic                  psum_valid_out,
    input  logic                  psum_ready_in
);

    typedef enum logic [1:0] {{IDLE, CALC}} state_t;
    state_t state;

    // Internal buffered copies
    logic [DATA_WIDTH-1:0] act_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   act_bv_buf;
    logic [DATA_WIDTH-1:0] wgt_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   wgt_bv_buf;

    logic [BV_WIDTH-1:0]   match_remain;
    logic [ACC_WIDTH-1:0]  acc_reg;

    localparam int BV_IDX_W = $clog2(BV_WIDTH);

    // Find lowest set bit position
    function automatic logic [BV_IDX_W-1:0] find_lsb(input logic [BV_WIDTH-1:0] bv);
        for (int i = 0; i < BV_WIDTH; i++)
            if (bv[i]) return BV_IDX_W'(i);
        return '0;
    endfunction

    // Count set bits below position 'pos' in bitvector
    function automatic logic [BV_IDX_W-1:0] popcount_below(input logic [BV_WIDTH-1:0] bv, input logic [BV_IDX_W-1:0] pos);
        logic [BV_IDX_W-1:0] cnt;
        cnt = 0;
        for (int i = 0; i < BV_WIDTH; i++)
            if (BV_IDX_W'(i) < pos && bv[i]) cnt = cnt + 1;
        return cnt;
    endfunction

    logic [BV_IDX_W-1:0] cur_bit;
    logic [BV_IDX_W-1:0] act_idx, wgt_idx;
    logic [BV_WIDTH-1:0] cur_bit_mask;
    logic [BV_WIDTH-1:0] next_match;

    // Combinational datapath
    assign cur_bit      = find_lsb(match_remain);
    assign act_idx      = popcount_below(act_bv_buf, cur_bit);
    assign wgt_idx      = popcount_below(wgt_bv_buf, cur_bit);
    assign cur_bit_mask = BV_WIDTH'(1) << cur_bit;
    assign next_match   = match_remain & ~cur_bit_mask;

    // =========================================================
    // FIFO Signals & Logic
    // =========================================================
    localparam int FIFO_PTR_W = $clog2(FIFO_DEPTH);

    logic [ACC_WIDTH-1:0]    fifo_mem   [0:FIFO_DEPTH-1];
    logic [FIFO_PTR_W:0]     fifo_count;
    logic [FIFO_PTR_W-1:0]   fifo_wr_ptr, fifo_rd_ptr;
    logic                    fifo_full, fifo_empty;
    logic                    fifo_wr_en;
    logic [ACC_WIDTH-1:0]    fifo_wr_data;

    assign fifo_full  = (fifo_count == (FIFO_PTR_W+1)'(FIFO_DEPTH));
    assign fifo_empty = (fifo_count == '0);

    // FWFT read port: data valid whenever FIFO non-empty
    assign psum_out       = fifo_mem[fifo_rd_ptr];
    assign psum_valid_out = !fifo_empty;

    wire fifo_do_push = fifo_wr_en && !fifo_full;
    wire fifo_do_pop  = psum_ready_in && !fifo_empty;

    // =========================================================
    // can_accept Condition
    // =========================================================
    wire can_accept = (state == IDLE)
                   && act_valid && wgt_valid && psum_valid_in
                   && !fifo_full
                   && !act_valid_out && !wgt_valid_out;

    assign act_ready      = can_accept;
    assign wgt_ready      = can_accept;
    assign psum_ready_out = can_accept;

    // =========================================================
    // Clock Gating Logic (ASIC vs FPGA)
    // =========================================================
    logic gclk;

    wire pe_active = (state == CALC)
                  || can_accept
                  || (act_valid_out && act_ready_in)
                  || (wgt_valid_out && wgt_ready_in)
                  || fifo_do_pop
                  || fifo_wr_en
                  || !rst_n;

`ifdef FPGA_TARGET
    // [FPGA 타겟] Xilinx 등 FPGA 전용 클럭 버퍼 사용
    // 일반 로직이 클럭 트리를 타게 하여 Skew를 방지함
    // (Xilinx가 아닌 다른 벤더 툴을 쓴다면 해당 벤더의 Clock Enable Buffer로 변경)
    BUFGCE u_cg_buf (
        .O  (gclk),
        .I  (clk),
        .CE (pe_active)
    );
`else
    // [ASIC 타겟] Glitch-free Latch 기반 ICG 
    // Synopsys Design Compiler 등이 이 패턴을 인식하여 전용 ICG Cell로 합성함
    logic cg_en_latched;

    always_latch begin
        if (!clk) begin
            cg_en_latched = pe_active;
        end
    end

    assign gclk = clk & cg_en_latched;
`endif

    // =========================================================
    // PSUM FIFO (Gated Clock)
    // =========================================================
    always_ff @(posedge gclk or negedge rst_n) begin
        if (!rst_n) begin
            fifo_count  <= '0;
            fifo_wr_ptr <= '0;
            fifo_rd_ptr <= '0;
            for (int i = 0; i < FIFO_DEPTH; i++)
                fifo_mem[i] <= '0;
        end else begin
            if (fifo_do_push) begin
                fifo_mem[fifo_wr_ptr] <= fifo_wr_data;
                fifo_wr_ptr           <= fifo_wr_ptr + 1;
            end
            if (fifo_do_pop)
                fifo_rd_ptr <= fifo_rd_ptr + 1;

            if      (fifo_do_push && !fifo_do_pop) fifo_count <= fifo_count + 1;
            else if (!fifo_do_push && fifo_do_pop) fifo_count <= fifo_count - 1;
        end
    end

    // =========================================================
    // Main state machine (Gated Clock)
    // =========================================================
    always_ff @(posedge gclk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            acc_reg       <= '0;
            match_remain  <= '0;
            fifo_wr_en    <= 1'b0;
            fifo_wr_data  <= '0;
            act_valid_out <= 1'b0;
            wgt_valid_out <= 1'b0;
            act_bv_buf    <= '0;
            wgt_bv_buf    <= '0;
            act_bv_out    <= '0;
            wgt_bv_out    <= '0;
            for (int i = 0; i < BV_WIDTH; i++) begin
                act_buf[i]    <= '0;
                wgt_buf[i]    <= '0;
                act_nz_out[i] <= '0;
                wgt_nz_out[i] <= '0;
            end
        end else begin
            fifo_wr_en <= 1'b0;

            if (act_valid_out && act_ready_in) act_valid_out <= 1'b0;
            if (wgt_valid_out && wgt_ready_in) wgt_valid_out <= 1'b0;

            case (state)
                IDLE: begin
                    if (can_accept) begin
                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_buf[i] <= act_nz_in[i];
                            wgt_buf[i] <= wgt_nz_in[i];
                        end
                        act_bv_buf <= act_bv_in;
                        wgt_bv_buf <= wgt_bv_in;
                        acc_reg    <= psum_in;

                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_nz_out[i] <= act_nz_in[i];
                            wgt_nz_out[i] <= wgt_nz_in[i];
                        end
                        act_bv_out    <= act_bv_in;
                        wgt_bv_out    <= wgt_bv_in;
                        act_valid_out <= 1'b1;
                        wgt_valid_out <= 1'b1;

                        if ((act_bv_in & wgt_bv_in) == '0) begin
                            fifo_wr_en   <= 1'b1;
                            fifo_wr_data <= psum_in;
                        end else begin
                            match_remain <= act_bv_in & wgt_bv_in;
                            state        <= CALC;
                        end
                    end
                end

                CALC: begin
                    acc_reg      <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                    match_remain <= next_match;

                    if (next_match == '0) begin
                        fifo_wr_en   <= 1'b1;
                        fifo_wr_data <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                        state        <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

"""

def gen_single_pe_final(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps

// `define FPGA_TARGET
// If targeting FPGA, uncomment the above line and adjust the code below for clock gating.
module sparse_single_PE #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int BV_WIDTH   = {sa_size},
    parameter int FIFO_DEPTH = 2
)(
    input  logic clk,
    input  logic rst_n,

    input  logic [DATA_WIDTH-1:0] act_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   act_bv_in,
    input  logic                  act_valid,
    output logic                  act_ready,

    output logic [DATA_WIDTH-1:0] act_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   act_bv_out,
    output logic                  act_valid_out,
    input  logic                  act_ready_in,

    input  logic [DATA_WIDTH-1:0] wgt_nz_in  [0:BV_WIDTH-1],
    input  logic [BV_WIDTH-1:0]   wgt_bv_in,
    input  logic                  wgt_valid,
    output logic                  wgt_ready,

    output logic [DATA_WIDTH-1:0] wgt_nz_out [0:BV_WIDTH-1],
    output logic [BV_WIDTH-1:0]   wgt_bv_out,
    output logic                  wgt_valid_out,
    input  logic                  wgt_ready_in,

    input  logic [ACC_WIDTH-1:0]  psum_in,
    input  logic                  psum_valid_in,
    output logic                  psum_ready_out,

    output logic [ACC_WIDTH-1:0]  psum_out,
    output logic                  psum_valid_out,
    input  logic                  psum_ready_in
);

    typedef enum logic [1:0] {{IDLE, CALC}} state_t;
    state_t state;

    // Internal buffered copies
    logic [DATA_WIDTH-1:0] act_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   act_bv_buf;
    logic [DATA_WIDTH-1:0] wgt_buf [0:BV_WIDTH-1];
    logic [BV_WIDTH-1:0]   wgt_bv_buf;

    logic [BV_WIDTH-1:0]   match_remain;
    logic [ACC_WIDTH-1:0]  acc_reg;

    localparam int BV_IDX_W = $clog2(BV_WIDTH);

    // Find lowest set bit position
    function automatic logic [BV_IDX_W-1:0] find_lsb(input logic [BV_WIDTH-1:0] bv);
        for (int i = 0; i < BV_WIDTH; i++)
            if (bv[i]) return BV_IDX_W'(i);
        return '0;
    endfunction

    // Count set bits below position 'pos' in bitvector
    function automatic logic [BV_IDX_W-1:0] popcount_below(input logic [BV_WIDTH-1:0] bv, input logic [BV_IDX_W-1:0] pos);
        logic [BV_IDX_W-1:0] cnt;
        cnt = 0;
        for (int i = 0; i < BV_WIDTH; i++)
            if (BV_IDX_W'(i) < pos && bv[i]) cnt = cnt + 1;
        return cnt;
    endfunction

    logic [BV_IDX_W-1:0] cur_bit;
    logic [BV_IDX_W-1:0] act_idx, wgt_idx;
    logic [BV_WIDTH-1:0] cur_bit_mask;
    logic [BV_WIDTH-1:0] next_match;

    // Combinational datapath
    assign cur_bit      = find_lsb(match_remain);
    assign act_idx      = popcount_below(act_bv_buf, cur_bit);
    assign wgt_idx      = popcount_below(wgt_bv_buf, cur_bit);
    assign cur_bit_mask = BV_WIDTH'(1) << cur_bit;
    assign next_match   = match_remain & ~cur_bit_mask;

    // =========================================================
    // FIFO Signals & Logic
    // =========================================================
    localparam int FIFO_PTR_W = $clog2(FIFO_DEPTH);

    logic [ACC_WIDTH-1:0]    fifo_mem   [0:FIFO_DEPTH-1];
    logic [FIFO_PTR_W:0]     fifo_count;
    logic [FIFO_PTR_W-1:0]   fifo_wr_ptr, fifo_rd_ptr;
    logic                    fifo_full, fifo_empty;
    logic                    fifo_wr_en;
    logic [ACC_WIDTH-1:0]    fifo_wr_data;

    assign fifo_full  = (fifo_count == (FIFO_PTR_W+1)'(FIFO_DEPTH));
    assign fifo_empty = (fifo_count == '0);

    // FWFT read port: data valid whenever FIFO non-empty
    assign psum_out       = fifo_mem[fifo_rd_ptr];
    assign psum_valid_out = !fifo_empty;

    wire fifo_do_push = fifo_wr_en && !fifo_full;
    wire fifo_do_pop  = psum_ready_in && !fifo_empty;

    // =========================================================
    // can_accept Condition
    // =========================================================
    wire can_accept = (state == IDLE)
                   && act_valid && wgt_valid && psum_valid_in
                   && !fifo_full
                   && !act_valid_out && !wgt_valid_out;

    assign act_ready      = can_accept;
    assign wgt_ready      = can_accept;
    assign psum_ready_out = can_accept;

    // =========================================================
    // Clock Gating Logic (ASIC vs FPGA)
    // =========================================================
    logic gclk;

    wire pe_active = (state == CALC)
                  || can_accept
                  || (act_valid_out && act_ready_in)
                  || (wgt_valid_out && wgt_ready_in)
                  || fifo_do_pop
                  || fifo_wr_en
                  || !rst_n;

`ifdef FPGA_TARGET
    // [FPGA 타겟] Xilinx 등 FPGA 전용 클럭 버퍼 사용
    // 일반 로직이 클럭 트리를 타게 하여 Skew를 방지함
    // (Xilinx가 아닌 다른 벤더 툴을 쓴다면 해당 벤더의 Clock Enable Buffer로 변경)
    BUFGCE u_cg_buf (
        .O  (gclk),
        .I  (clk),
        .CE (pe_active)
    );
`else
    // [ASIC 타겟] Glitch-free Latch 기반 ICG 
    // Synopsys Design Compiler 등이 이 패턴을 인식하여 전용 ICG Cell로 합성함
    logic cg_en_latched;

    always_latch begin
        if (!clk) begin
            cg_en_latched = pe_active;
        end
    end

    assign gclk = clk & cg_en_latched;
`endif

    // =========================================================
    // PSUM FIFO (Gated Clock)
    // =========================================================
    always_ff @(posedge gclk or negedge rst_n) begin
        if (!rst_n) begin
            fifo_count  <= '0;
            fifo_wr_ptr <= '0;
            fifo_rd_ptr <= '0;
            for (int i = 0; i < FIFO_DEPTH; i++)
                fifo_mem[i] <= '0;
        end else begin
            if (fifo_do_push) begin
                fifo_mem[fifo_wr_ptr] <= fifo_wr_data;
                fifo_wr_ptr           <= fifo_wr_ptr + 1;
            end
            if (fifo_do_pop)
                fifo_rd_ptr <= fifo_rd_ptr + 1;

            if      (fifo_do_push && !fifo_do_pop) fifo_count <= fifo_count + 1;
            else if (!fifo_do_push && fifo_do_pop) fifo_count <= fifo_count - 1;
        end
    end

    // =========================================================
    // Main state machine (Gated Clock)
    // =========================================================
    always_ff @(posedge gclk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            acc_reg       <= '0;
            match_remain  <= '0;
            fifo_wr_en    <= 1'b0;
            fifo_wr_data  <= '0;
            act_valid_out <= 1'b0;
            wgt_valid_out <= 1'b0;
            act_bv_buf    <= '0;
            wgt_bv_buf    <= '0;
            act_bv_out    <= '0;
            wgt_bv_out    <= '0;
            for (int i = 0; i < BV_WIDTH; i++) begin
                act_buf[i]    <= '0;
                wgt_buf[i]    <= '0;
                act_nz_out[i] <= '0;
                wgt_nz_out[i] <= '0;
            end
        end else begin
            fifo_wr_en <= 1'b0;

            if (act_valid_out && act_ready_in) act_valid_out <= 1'b0;
            if (wgt_valid_out && wgt_ready_in) wgt_valid_out <= 1'b0;

            case (state)
                IDLE: begin
                    if (can_accept) begin
                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_buf[i] <= act_nz_in[i];
                            wgt_buf[i] <= wgt_nz_in[i];
                        end
                        act_bv_buf <= act_bv_in;
                        wgt_bv_buf <= wgt_bv_in;
                        acc_reg    <= psum_in;

                        for (int i = 0; i < BV_WIDTH; i++) begin
                            act_nz_out[i] <= act_nz_in[i];
                            wgt_nz_out[i] <= wgt_nz_in[i];
                        end
                        act_bv_out    <= act_bv_in;
                        wgt_bv_out    <= wgt_bv_in;
                        act_valid_out <= 1'b1;
                        wgt_valid_out <= 1'b1;

                        if ((act_bv_in & wgt_bv_in) == '0) begin
                            fifo_wr_en   <= 1'b1;
                            fifo_wr_data <= psum_in;
                        end else begin
                            match_remain <= act_bv_in & wgt_bv_in;
                            state        <= CALC;
                        end
                    end
                end

                CALC: begin
                    acc_reg      <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                    match_remain <= next_match;

                    if (next_match == '0) begin
                        fifo_wr_en   <= 1'b1;
                        fifo_wr_data <= acc_reg + act_buf[act_idx] * wgt_buf[wgt_idx];
                        state        <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

"""



def gen_sa_top_non_sparse(sa_size: int) -> str:
    sa_top_name = sa_top_mod_name(sa_size)
    sa_core_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {sa_top_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int ROW_SIZE   = {sa_size}
)(
    input logic clk,
    input logic rst_n,
    input logic start,

    input logic [DATA_WIDTH-1:0] mat_a[0:ROW_SIZE-1][0:ROW_SIZE-1],
    input logic [DATA_WIDTH-1:0] mat_b[0:ROW_SIZE-1][0:ROW_SIZE-1],

    output logic [ACC_WIDTH-1:0] acc_result[0:ROW_SIZE-1][0:ROW_SIZE-1]
);

    logic [$clog2(ROW_SIZE):0] count;
    logic                      running;
    logic                      valid_row;
    logic [DATA_WIDTH-1:0]     row_a [0:ROW_SIZE-1];
    logic [DATA_WIDTH-1:0]     row_b [0:ROW_SIZE-1];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count     <= 0;
            running   <= 0;
            valid_row <= 0;
        end else begin
            if (start) begin
                running <= 1;
                count   <= 0;
            end

            if (running) begin
                if (count < ROW_SIZE) begin
                    for (int i = 0; i < ROW_SIZE; i++) begin
                        row_a[i] <= mat_a[i][count];
                        row_b[i] <= mat_b[count][i];
                    end
                    valid_row <= 1;
                    count     <= count + 1;
                end else begin
                    running   <= 0;
                    count     <= 0;
                    valid_row <= 0;
                end
            end else begin
                valid_row <= 0;
            end
        end
    end

    logic [DATA_WIDTH-1:0] a_skewed[0:ROW_SIZE-1];
    logic [DATA_WIDTH-1:0] b_skewed[0:ROW_SIZE-1];
    logic                  v_skewed[0:ROW_SIZE-1];

    genvar i, k;
    generate
        for (i = 0; i < ROW_SIZE; i++) begin : SKEW_GEN
            logic [DATA_WIDTH-1:0] a_delay[0:i];
            logic [DATA_WIDTH-1:0] b_delay[0:i];
            logic                  v_delay[0:i];

            assign a_delay[0] = row_a[i];
            assign b_delay[0] = row_b[i];
            assign v_delay[0] = valid_row;

            for (k = 0; k < i; k++) begin : FF_CHAIN
                always_ff @(posedge clk or negedge rst_n) begin
                    if (!rst_n) begin
                        a_delay[k+1] <= 0;
                        b_delay[k+1] <= 0;
                        v_delay[k+1] <= 0;
                    end else begin
                        a_delay[k+1] <= a_delay[k];
                        b_delay[k+1] <= b_delay[k];
                        v_delay[k+1] <= v_delay[k];
                    end
                end
            end

            assign a_skewed[i] = a_delay[i];
            assign b_skewed[i] = b_delay[i];
            assign v_skewed[i] = v_delay[i];
        end
    endgenerate

    {sa_core_name} #(
        .DATA_WIDTH(DATA_WIDTH),
        .ACC_WIDTH (ACC_WIDTH),
        .ROW_SIZE  (ROW_SIZE)
    ) u_sa_core (
        .clk(clk),
        .rst_n(rst_n),
        .in_a(a_skewed),
        .in_b(b_skewed),
        .valid_in_a(v_skewed),
        .valid_in_b(),
        .acc_result(acc_result)
    );

endmodule
"""

def gen_sa_core_non_sparse(sa_size: int) -> str:
    mod_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {mod_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int ROW_SIZE   = {sa_size},
    parameter int COL_SIZE   = {sa_size}
)(
    input  logic                   clk,
    input  logic                   rst_n,

    input  logic [DATA_WIDTH-1:0]  in_a [0:ROW_SIZE-1],
    input  logic [DATA_WIDTH-1:0]  in_b [0:COL_SIZE-1],
    
    input  logic                   valid_in_a [0:ROW_SIZE-1], 
    input  logic                   valid_in_b [0:COL_SIZE-1],

    output logic [ACC_WIDTH-1:0]   acc_result [0:ROW_SIZE-1][0:COL_SIZE-1]
);

    logic [DATA_WIDTH-1:0] wire_a [0:ROW_SIZE-1][0:COL_SIZE];
    logic [DATA_WIDTH-1:0] wire_b [0:ROW_SIZE][0:COL_SIZE-1];
    logic                  wire_valid [0:ROW_SIZE-1][0:COL_SIZE];

    genvar i, j;
    generate
        for (i = 0; i < ROW_SIZE; i++) begin : ROW_GEN
            for (j = 0; j < COL_SIZE; j++) begin : COL_GEN
                single_PE #(
                    .DATA_WIDTH (DATA_WIDTH),
                    .ACC_WIDTH  (ACC_WIDTH)
                ) u_pe (
                    .clk       (clk),
                    .rst_n     (rst_n),

                    .in_a      ( (j == 0) ? in_a[i]    : wire_a[i][j]   ),
                    .out_a     ( wire_a[i][j+1]                         ),

                    .in_b      ( (i == 0) ? in_b[j]    : wire_b[i][j]   ),
                    .out_b     ( wire_b[i+1][j]                         ),

                    .valid_in  ( (j == 0) ? valid_in_a[i]  : wire_valid[i][j]   ),
                    .valid_out ( wire_valid[i][j+1]                         ),

                    .acc_out   ( acc_result[i][j]                          )
                );
            end
        end
    endgenerate
endmodule
"""

def gen_sa_top_sparse(sa_size: int) -> str:
    sa_top_name = sa_top_mod_name(sa_size)
    sa_core_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {sa_top_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int ROW_SIZE   = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,
    input  logic start,

    input  logic [DATA_WIDTH-1:0] mat_a [0:ROW_SIZE-1][0:ROW_SIZE-1],
    input  logic [DATA_WIDTH-1:0] mat_b [0:ROW_SIZE-1][0:ROW_SIZE-1],
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
                if (mat_a[i][j] != '0) begin
                    a_bv[i][j]   = 1'b1;
                    a_nz[i][p_a] = mat_a[i][j];
                    p_a++;
                end
            end

            for (int j = 0; j < ROW_SIZE; j++) begin
                if (mat_b[j][i] != '0) begin
                    b_bv[i][j]   = 1'b1;
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

    {sa_core_name} #(
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
"""

def gen_sa_top_final(sa_size: int) -> str:
    top_name = sa_top_mod_name(sa_size)
    core_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {top_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int ROW_SIZE   = {sa_size}
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

    {core_name} #(
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
"""

def gen_sa_core_sparse(sa_size: int) -> str:
    core_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {core_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 32,
    parameter int BV_WIDTH   = {sa_size},
    parameter int ROW_SIZE   = {sa_size},
    parameter int COL_SIZE   = {sa_size}
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
"""

def gen_sa_core_final(sa_size: int) -> str:
    core_name = sa_mod_name(sa_size)
    return f"""`timescale 1ns / 1ps
module {core_name} #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int BV_WIDTH   = {sa_size},
    parameter int ROW_SIZE   = {sa_size},
    parameter int COL_SIZE   = {sa_size}
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
"""


def gen_accumulator_bank(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
// Dual ping-pong accumulator bank; accumulates (+=) on wr_en, clears on clr_en.
// Combinational read port for save FSM.
module accumulator_bank #(
    parameter int ACC_WIDTH = 24,
    parameter int SA_SIZE   = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,

    // Write (accumulate +=)
    input  logic                  wr_en,
    input  logic                  wr_sel,
    input  logic [ACC_WIDTH-1:0]  wr_data [0:SA_SIZE-1][0:SA_SIZE-1],

    // Clear (zero selected buffer)
    input  logic                  clr_en,
    input  logic                  clr_sel,

    // Read (combinational)
    input  logic                  rd_sel,
    output logic [ACC_WIDTH-1:0]  rd_data [0:SA_SIZE-1][0:SA_SIZE-1]
);

    // Renamed buf -> abuf to avoid conflict with SV primitive keyword 'buf'
    logic [ACC_WIDTH-1:0] abuf [0:1][0:SA_SIZE-1][0:SA_SIZE-1];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int b = 0; b < 2; b++)
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++)
                        abuf[b][i][j] <= '0;
        end else begin
            if (clr_en) begin
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++)
                        abuf[clr_sel][i][j] <= '0;
            end
            if (wr_en) begin
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++)
                        abuf[wr_sel][i][j] <= abuf[wr_sel][i][j] + wr_data[i][j];
            end
        end
    end

    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                rd_data[i][j] = abuf[rd_sel][i][j];
    end

endmodule
"""


def gen_activation_unit(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
// Activation Unit — pure combinational.
// Applies arithmetic right-shift (quantization) then activation function.
// act_type encoding:
//   2'b00 = bypass  : shift + signed-saturate to OUT_WIDTH
//   2'b01 = ReLU    : shift + saturate + zero if negative
//   2'b10 = ReLU6   : shift + saturate + clamp to [0, 6]
//   2'b11 = reserved: same as bypass
//
// quant_shift: arithmetic right-shift applied to 32-bit accumulator before output.
//   e.g. quant_shift=0 → no scaling (full precision, saturated to OUT_WIDTH)
//        quant_shift=8  → divide by 256 (typical for int8 x int8 → int16)
module activation_unit #(
    parameter int ACC_WIDTH  = 24,
    parameter int OUT_WIDTH  = 16,
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic [1:0]           act_type,
    input  logic [4:0]           quant_shift,           // 0-31: arithmetic right-shift before output
    input  logic [ACC_WIDTH-1:0]  in_data  [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [OUT_WIDTH-1:0] out_data [0:SA_SIZE-1][0:SA_SIZE-1]
);

    // Signed saturation bounds for OUT_WIDTH-bit output
    // SAT_MAX =  2^(OUT_WIDTH-1) - 1  (e.g. 32767 for OUT_WIDTH=16)
    // SAT_MIN = -2^(OUT_WIDTH-1)      (e.g. -32768 for OUT_WIDTH=16)
    localparam logic signed [ACC_WIDTH-1:0] SAT_MAX =  (ACC_WIDTH'(1) << (OUT_WIDTH-1)) - 1;
    localparam logic signed [ACC_WIDTH-1:0] SAT_MIN = -(ACC_WIDTH'(1) << (OUT_WIDTH-1));

    // Step 1 result: arithmetic right-shifted accumulator
    logic signed [ACC_WIDTH-1:0] shifted [0:SA_SIZE-1][0:SA_SIZE-1];

    // Step 2 result: saturated to OUT_WIDTH
    logic [OUT_WIDTH-1:0] sat_val [0:SA_SIZE-1][0:SA_SIZE-1];

    // Step 1: arithmetic right-shift (requantization)
    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                shifted[i][j] = $signed(in_data[i][j]) >>> quant_shift;
    end

    // Step 2: signed saturation to OUT_WIDTH
    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++) begin
                if (shifted[i][j] > SAT_MAX)
                    sat_val[i][j] = SAT_MAX[OUT_WIDTH-1:0];
                else if (shifted[i][j] < SAT_MIN)
                    sat_val[i][j] = SAT_MIN[OUT_WIDTH-1:0];
                else
                    sat_val[i][j] = shifted[i][j][OUT_WIDTH-1:0];
            end
    end

    // Step 3: activation function applied to saturated value
    always_comb begin
        for (int i = 0; i < SA_SIZE; i++) begin
            for (int j = 0; j < SA_SIZE; j++) begin
                unique case (act_type)
                    2'b00,
                    2'b11: begin    // bypass / reserved
                        out_data[i][j] = sat_val[i][j];
                    end

                    2'b01: begin    // ReLU: zero if negative (MSB set)
                        out_data[i][j] = sat_val[i][j][OUT_WIDTH-1] ? '0 : sat_val[i][j];
                    end

                    2'b10: begin    // ReLU6: clamp to [0, 6]
                        if (sat_val[i][j][OUT_WIDTH-1])
                            out_data[i][j] = '0;
                        else if (sat_val[i][j] > OUT_WIDTH'(6))
                            out_data[i][j] = OUT_WIDTH'(6);
                        else
                            out_data[i][j] = sat_val[i][j];
                    end
                endcase
            end
        end
    end

endmodule
"""


def gen_norm_pool(sa_size: int) -> str:
    return f"""`timescale 1ns / 1ps
// Normalize/Pool Unit — 1-cycle pipeline.
// pool_type encoding:
//   2'b00 = bypass         : register input as-is
//   2'b01 = max pool 2x2   : stride 2, output SA_SIZE/2 x SA_SIZE/2 zero-padded to SA_SIZE x SA_SIZE
//   2'b10 = average pool 2x2: stride 2, (sum >> 2) per window, same output shape
//   2'b11 = reserved       : same as bypass
module norm_pool #(
    parameter int OUT_WIDTH = 16,
    parameter int SA_SIZE    = {sa_size}
)(
    input  logic clk,
    input  logic rst_n,

    input  logic [1:0]            pool_type,
    input  logic                  in_valid,
    input  logic [OUT_WIDTH-1:0] in_data  [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic [OUT_WIDTH-1:0] out_data [0:SA_SIZE-1][0:SA_SIZE-1],
    output logic                  norm_done
);

    localparam int HALF  = SA_SIZE / 2;
    localparam int SUM_W = OUT_WIDTH + 2;   // 2 extra bits for 4-element sum

    logic [OUT_WIDTH-1:0] win_max [0:HALF-1][0:HALF-1];
    logic [SUM_W-1:0]      win_sum [0:HALF-1][0:HALF-1];

    logic [OUT_WIDTH-1:0] pool_result [0:SA_SIZE-1][0:SA_SIZE-1];

    // Step 1: per-window max and sum
    always_comb begin
        for (int bi = 0; bi < HALF; bi++) begin
            for (int bj = 0; bj < HALF; bj++) begin
                win_max[bi][bj] = in_data[2*bi][2*bj];
                if (in_data[2*bi  ][2*bj+1] > win_max[bi][bj])
                    win_max[bi][bj] = in_data[2*bi  ][2*bj+1];
                if (in_data[2*bi+1][2*bj  ] > win_max[bi][bj])
                    win_max[bi][bj] = in_data[2*bi+1][2*bj  ];
                if (in_data[2*bi+1][2*bj+1] > win_max[bi][bj])
                    win_max[bi][bj] = in_data[2*bi+1][2*bj+1];

                win_sum[bi][bj] = SUM_W'(in_data[2*bi  ][2*bj  ])
                                + SUM_W'(in_data[2*bi  ][2*bj+1])
                                + SUM_W'(in_data[2*bi+1][2*bj  ])
                                + SUM_W'(in_data[2*bi+1][2*bj+1]);
            end
        end
    end

    // Step 2: assemble full SA_SIZE x SA_SIZE output
    always_comb begin
        for (int i = 0; i < SA_SIZE; i++)
            for (int j = 0; j < SA_SIZE; j++)
                pool_result[i][j] = '0;

        unique case (pool_type)
            2'b00,
            2'b11: begin
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++)
                        pool_result[i][j] = in_data[i][j];
            end

            2'b01: begin
                for (int bi = 0; bi < HALF; bi++)
                    for (int bj = 0; bj < HALF; bj++)
                        pool_result[bi][bj] = win_max[bi][bj];
            end

            2'b10: begin
                for (int bi = 0; bi < HALF; bi++)
                    for (int bj = 0; bj < HALF; bj++)
                        pool_result[bi][bj] = OUT_WIDTH'(win_sum[bi][bj] >> 2);
            end
        endcase
    end

    // 1-cycle pipeline register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < SA_SIZE; i++)
                for (int j = 0; j < SA_SIZE; j++)
                    out_data[i][j] <= '0;
            norm_done <= 1'b0;
        end else begin
            norm_done <= 1'b0;
            if (in_valid) begin
                for (int i = 0; i < SA_SIZE; i++)
                    for (int j = 0; j < SA_SIZE; j++)
                        out_data[i][j] <= pool_result[i][j];
                norm_done <= 1'b1;
            end
        end
    end

endmodule
"""
