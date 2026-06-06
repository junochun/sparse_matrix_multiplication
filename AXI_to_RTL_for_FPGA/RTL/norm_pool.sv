`timescale 1ns / 1ps
// Normalize/Pool Unit — 1-cycle pipeline.
// pool_type encoding:
//   2'b00 = bypass         : register input as-is
//   2'b01 = max pool 2x2   : stride 2, output SA_SIZE/2 x SA_SIZE/2 zero-padded to SA_SIZE x SA_SIZE
//   2'b10 = average pool 2x2: stride 2, (sum >> 2) per window, same output shape
//   2'b11 = reserved       : same as bypass
module norm_pool #(
    parameter int OUT_WIDTH = 16,
    parameter int SA_SIZE    = 16
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

        case (pool_type)
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
