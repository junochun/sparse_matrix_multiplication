`timescale 1ns / 1ps
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
    parameter int SA_SIZE    = 16
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
                case (act_type)
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
