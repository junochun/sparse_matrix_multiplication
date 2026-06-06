`timescale 1ns / 1ps
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
    parameter int M_SIZE     = 48,   // rows of C
    parameter int N_SIZE     = 48,   // cols of C
    parameter int SA_SIZE    = 16
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
        automatic int row      = int'(spi_raddr) / N_SIZE;
        automatic int col      = int'(spi_raddr) % N_SIZE;
        automatic int col_tile = col / SA_SIZE;
        automatic int col_pos  = col % SA_SIZE;
        automatic int idx      = row * N_TILES + col_tile;

        spi_rword <= sram[idx];
        // latch col_pos so the mux sees a registered value
        // (col_pos is a simple combinational decode; register the whole word
        //  and extract the element in the same registered stage)
        spi_rdata <= sram[idx][OUT_WIDTH*(col_pos+1)-1 -: OUT_WIDTH];
    end

endmodule
