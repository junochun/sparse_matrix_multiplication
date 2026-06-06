`timescale 1ns / 1ps
// Dual ping-pong accumulator bank; accumulates (+=) on wr_en, clears on clr_en.
// Combinational read port for save FSM.
module accumulator_bank #(
    parameter int ACC_WIDTH = 24,
    parameter int SA_SIZE   = 16
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
