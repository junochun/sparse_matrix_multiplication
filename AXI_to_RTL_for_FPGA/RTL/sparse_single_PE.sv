`timescale 1ns / 1ps

// `define FPGA_TARGET
// If targeting FPGA, uncomment the above line and adjust the code below for clock gating.
module sparse_single_PE #(
    parameter int DATA_WIDTH = 8,
    parameter int ACC_WIDTH  = 24,
    parameter int BV_WIDTH   = 16,
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

    typedef enum logic [1:0] {IDLE, CALC} state_t;
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

