`timescale 1ns / 1ps
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
    parameter int M_SIZE     = 48,   // rows of A
    parameter int K_SIZE     = 48,   // cols of A (inner dimension)
    parameter int N_SIZE     = 48,
    parameter int SA_SIZE    = 16
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
            automatic int row      = int'(spi_a_waddr) / K_SIZE;
            automatic int col      = int'(spi_a_waddr) % K_SIZE;
            automatic int col_tile = col / SA_SIZE;
            automatic int col_pos  = col % SA_SIZE;
            automatic int idx      = row * K_TILES + col_tile;   // within A region

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
            automatic int row      = int'(spi_b_waddr) / N_SIZE;
            automatic int col      = int'(spi_b_waddr) % N_SIZE;
            automatic int col_tile = col / SA_SIZE;
            automatic int col_pos  = col % SA_SIZE;
            automatic int idx      = DEPTH_A + row * N_TILES + col_tile;

            sram[idx][DATA_WIDTH*(col_pos+1)-1 -: DATA_WIDTH] <= spi_b_wdata;
            sram[idx][DATA_W + col_pos]                        <= (spi_b_wdata != '0);
        end
    end

    always_ff @(posedge clk) begin
        acc_b_rdata    <= sram[ADDR_W'(DEPTH_A + int'(acc_b_raddr))][DATA_W-1:0];
        acc_b_bv_rdata <= sram[ADDR_W'(DEPTH_A + int'(acc_b_raddr))][WORD_W-1:DATA_W];
    end

endmodule
