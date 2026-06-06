`timescale 1ns / 1ps
module sa_controller #(
    parameter int DATA_WIDTH = 8,    // input matrix element width (BRAM_A/B)
    parameter int OUT_WIDTH  = 16,   // output element width (BRAM_C / norm_data)
    parameter int ACC_WIDTH  = 24,
    parameter int M_SIZE     = 48,   // rows of A, rows of C
    parameter int K_SIZE     = 48,   // cols of A = rows of B (inner dimension)
    parameter int N_SIZE     = 48,   // cols of B, cols of C
    parameter int SA_SIZE    = 16
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
    typedef enum logic [2:0] {
        LD_IDLE, LD_ADDR, LD_LOAD, LD_LAST_ROW, LD_WAIT_BUF, LD_DONE
    } ld_state_t;

    typedef enum logic [2:0] {
        CP_IDLE, CP_LATCH, CP_FIRE, CP_WAIT_SA,
        CP_ACCUMULATE, CP_NEXT, CP_DONE
    } cp_state_t;

    typedef enum logic [1:0] {
        S_IDLE, S_WAIT_NORM, S_SAVE_TILE
    } sstate_t;

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
                        cp_buf_sel <= ~cp_buf_sel; cp_state <= CP_NEXT;
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
                    cp_buf_sel <= ~cp_buf_sel; cp_state <= CP_NEXT;
                end
                CP_NEXT: begin
                    if (cp_is_last_part) begin
                        accum_clr_en <= 1'b1; accum_clr_sel <= save_buf_sel;
                        cp_part_idx  <= '0;
                        if (cp_tile_blk_c == N_TILE_W'(N_TILES - 1)) begin
                            cp_tile_blk_c <= '0;
                            if (cp_tile_blk_r == M_TILE_W'(M_TILES - 1))
                                cp_state <= CP_DONE;
                            else begin
                                cp_tile_blk_r <= cp_tile_blk_r + 1;
                                if (buf_ready[cp_buf_sel]) cp_state <= CP_LATCH;
                            end
                        end else begin
                            cp_tile_blk_c <= cp_tile_blk_c + 1;
                            if (buf_ready[cp_buf_sel]) cp_state <= CP_LATCH;
                        end
                    end else begin
                        cp_part_idx <= cp_part_idx + 1;
                        if (buf_ready[cp_buf_sel]) cp_state <= CP_LATCH;
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
