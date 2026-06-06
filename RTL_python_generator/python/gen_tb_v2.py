# =============================================================
# gen_tb_v2.py — Testbench 생성 모듈
#
# ▶ sweep_main.py에서 import해서 사용:
#   from gen_tb_v2 import generate_tb, generate_tb_final
#
#   generate_tb(data_width, acc_width, mat_size, sa_size,
#               file_a, file_b, file_out)
#     → 정사각 행렬 (MAT_SIZE × MAT_SIZE) TB 문자열 반환
#
#   generate_tb_final(data_width, acc_width,
#                     m_size, k_size, n_size, sa_size,
#                     file_a, file_b, file_out)
#     → 직사각 행렬 A(M×K) × B(K×N) = C(M×N) TB 문자열 반환
#
# ▶ 단독 실행 (직사각 모드 only):
#   python gen_tb_v2.py <M_SIZE> <K_SIZE> <N_SIZE> <SA_SIZE> <ZERO_RATIO>
#
#   예시:
#     python gen_tb_v2.py 32 32 32 32 0    # 정사각 (M=K=N=SA=32)
#     python gen_tb_v2.py 35 38 40 32 40   # 직사각
#     python gen_tb_v2.py 16 24 12 8 50 --data-width 16 --acc-width 64
#
#   옵션:
#     --data-width N   입력 데이터 비트폭 (기본값: 8)
#     --acc-width  N   누산기 비트폭     (기본값: 32)
#
#   행렬 파일 이름 규칙 (gen_matrix.py M K N <ZERO_RATIOS> 로 생성):
#     matrix_a_MxK_<zr>_1.txt
#     matrix_b_KxN_<zr>_1.txt
#   출력 파일:
#     hw_result/output_matrix_MxKxN_<zr>.txt
# =============================================================


import os
import argparse

PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_TB = os.path.join(PYTHON_DIR, "../TESTBENCH/tb_dig_top.sv")

def generate_tb(data_width, acc_width, mat_size, sa_size, file_a, file_b, file_out):
    return f"""`timescale 1ns / 1ps

module tb_dig_top;

  parameter int DATA_WIDTH = {data_width};
  parameter int ACC_WIDTH  = {acc_width};
  parameter int MAT_SIZE   = {mat_size};
  parameter int SA_SIZE    = {sa_size};

  localparam int ADDR_W = $clog2(MAT_SIZE * MAT_SIZE);

  logic clk;
  logic rst_n;
  logic start;
  logic done;

  // BRAM_A write (SPI side)
  logic [ADDR_W-1:0]     spi_a_waddr;
  logic [DATA_WIDTH-1:0] spi_a_wdata;
  logic                  spi_a_we;

  // BRAM_B write (SPI side)
  logic [ADDR_W-1:0]     spi_b_waddr;
  logic [DATA_WIDTH-1:0] spi_b_wdata;
  logic                  spi_b_we;

  // BRAM_C read (SPI side)
  logic [ADDR_W-1:0]     spi_c_raddr;
  logic [ACC_WIDTH-1:0]  spi_c_rdata;

  // Local matrices for golden model
  logic [DATA_WIDTH-1:0] mat_a [0:MAT_SIZE-1][0:MAT_SIZE-1];
  logic [DATA_WIDTH-1:0] mat_b [0:MAT_SIZE-1][0:MAT_SIZE-1];
  logic [ACC_WIDTH-1:0]  mat_c [0:MAT_SIZE-1][0:MAT_SIZE-1];
  logic [ACC_WIDTH-1:0]  expected_c [0:MAT_SIZE-1][0:MAT_SIZE-1];

  int error_cnt;
  realtime t_start, t_end;

  string file_a = "{file_a}";
  string file_b = "{file_b}";

  // DUT: dig_top (memory_top + accelerator_top)
  dig_top #(
      .DATA_WIDTH(DATA_WIDTH),
      .ACC_WIDTH (ACC_WIDTH),
      .MAT_SIZE  (MAT_SIZE),
      .SA_SIZE   (SA_SIZE)
  ) dut (
      .clk        (clk),
      .rst_n      (rst_n),
      .start      (start),
      .done       (done),
      .spi_a_waddr(spi_a_waddr),
      .spi_a_wdata(spi_a_wdata),
      .spi_a_we   (spi_a_we),
      .spi_b_waddr(spi_b_waddr),
      .spi_b_wdata(spi_b_wdata),
      .spi_b_we   (spi_b_we),
      .spi_c_raddr(spi_c_raddr),
      .spi_c_rdata(spi_c_rdata)
  );

  // Clock generation
  initial clk = 0;
  always #5 clk = ~clk;

  // Load matrix from file
  task automatic load_matrix_from_file(
      string filename,
      ref logic [DATA_WIDTH-1:0] matrix [0:MAT_SIZE-1][0:MAT_SIZE-1]
  );
    int fd, value;
    fd = $fopen(filename, "r");
    if (fd == 0) begin
      $display("[ERROR] Cannot open file: %s", filename);
      $finish;
    end
    $display("[INFO] Loading matrix from: %s", filename);
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++) begin
        if ($fscanf(fd, "%d", value) != 1) begin
          $display("[ERROR] Failed to read [%0d][%0d]", i, j);
          $fclose(fd);
          $finish;
        end
        matrix[i][j] = value[DATA_WIDTH-1:0];
      end
    $fclose(fd);
    $display("[INFO] Matrix loaded successfully");
  endtask

  // Write matrix to BRAM via SPI-like sequential write
  task automatic write_bram_a(
      ref logic [DATA_WIDTH-1:0] matrix [0:MAT_SIZE-1][0:MAT_SIZE-1]
  );
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++) begin
        @(posedge clk);
        spi_a_waddr = ADDR_W'(i * MAT_SIZE + j);
        spi_a_wdata = matrix[i][j];
        spi_a_we    = 1'b1;
      end
    @(posedge clk);
    spi_a_we = 1'b0;
  endtask

  task automatic write_bram_b(
      ref logic [DATA_WIDTH-1:0] matrix [0:MAT_SIZE-1][0:MAT_SIZE-1]
  );
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++) begin
        @(posedge clk);
        spi_b_waddr = ADDR_W'(i * MAT_SIZE + j);
        spi_b_wdata = matrix[i][j];
        spi_b_we    = 1'b1;
      end
    @(posedge clk);
    spi_b_we = 1'b0;
  endtask

  // Read result from BRAM_C
  task automatic read_bram_c(
      ref logic [ACC_WIDTH-1:0] matrix [0:MAT_SIZE-1][0:MAT_SIZE-1]
  );
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++) begin
        @(posedge clk);
        spi_c_raddr = ADDR_W'(i * MAT_SIZE + j);
        @(posedge clk); // 1-cycle BRAM read latency
        matrix[i][j] = spi_c_rdata;
      end
  endtask

  // Write output matrix to file
  task automatic write_output_to_file(
      string filename,
      ref logic [ACC_WIDTH-1:0] matrix [0:MAT_SIZE-1][0:MAT_SIZE-1]
  );
    int fd;
    fd = $fopen(filename, "w");
    if (fd == 0) begin
      $display("[ERROR] Cannot open output file: %s", filename);
      return;
    end
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++)
        $fwrite(fd, "%0d\\n", matrix[i][j]);
    $fclose(fd);
    $display("[INFO] HW result written to: %s", filename);
  endtask

  // Test scenario
  initial begin
    rst_n       = 0;
    start       = 0;
    spi_a_we    = 0;
    spi_b_we    = 0;
    spi_a_waddr = '0;
    spi_b_waddr = '0;
    spi_c_raddr = '0;
    spi_a_wdata = '0;
    spi_b_wdata = '0;
    error_cnt   = 0;

    // Load matrices
    load_matrix_from_file(file_a, mat_a);
    load_matrix_from_file(file_b, mat_b);

    // Golden model
    $display("[INFO] Calculating golden model...");
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++) begin
        expected_c[i][j] = 0;
        for (int k = 0; k < MAT_SIZE; k++)
          expected_c[i][j] += ACC_WIDTH'(mat_a[i][k]) * ACC_WIDTH'(mat_b[k][j]);
      end

    #25 rst_n = 1;
    @(posedge clk);

    // Write mat_a, mat_b to BRAM
    $display("============================================");
    $display("[INFO] Writing mat_a to BRAM_A...");
    write_bram_a(mat_a);
    $display("[INFO] Done writing BRAM_A (time=%0t, cycle=%0d)", $realtime, int'($realtime/10));
    $display("============================================");
    $display("[INFO] Writing mat_b to BRAM_B...");
    write_bram_b(mat_b);
    $display("[INFO] Done writing BRAM_B (time=%0t, cycle=%0d)", $realtime, int'($realtime/10));
    $display("============================================");

    @(posedge clk);

    // Start
    start = 1;
    @(posedge clk);
    start   = 0;
    t_start = $realtime;

    $display("============================================");
    $display("[INFO] %0dx%0d Matrix Multiplication Started! (time=%0t, cycle=%0d)",
             MAT_SIZE, MAT_SIZE, $realtime, int'($realtime/10));
    $display("[INFO] Input files: %s, %s", file_a, file_b);
    $display("============================================");

    fork
      begin
        wait (done == 1'b1);
        t_end = $realtime;
        $display("[INFO] Operation Finished at %0t (time=%0t, cycle=%0d)", t_end, $realtime, int'($realtime/10));
        $display("[INFO] Latency: %0t (%0d clock cycles)", t_end - t_start,
                 int'((t_end - t_start) / 10));
      end
      begin
        repeat (1000000) @(posedge clk);
        $display("[ERROR] Timeout!");
        $finish;
      end
    join_any
    disable fork;

    // Read result from BRAM_C
    $display("[INFO] Reading mat_c from BRAM_C...");
    read_bram_c(mat_c);

    // Dump HW output to file for external verification
    write_output_to_file("{file_out}", mat_c);

    // Verification
    $display("======= Matrix Multiplication Verification =======");
    for (int i = 0; i < MAT_SIZE; i++)
      for (int j = 0; j < MAT_SIZE; j++)
        if (mat_c[i][j] !== expected_c[i][j]) begin
          $display("[FAIL] Mismatch at [%2d][%2d]: Expected %4d, Got %4d",
                   i, j, expected_c[i][j], mat_c[i][j]);
          error_cnt++;
        end

    $display("============================================");
    if (error_cnt == 0)
      $display("[PASS] All %0d elements match!", MAT_SIZE * MAT_SIZE);
    else
      $display("[FAIL] Total %0d errors found.", error_cnt);
    $display("============================================");

    #50 $finish;
  end

endmodule
"""


def generate_tb_final(data_width, acc_width, m_size, k_size, n_size, sa_size,
                file_a, file_b, file_out, out_width=16):
    return f"""`timescale 1ns / 1ps

module tb_dig_top;

  parameter int DATA_WIDTH = {data_width};
  parameter int ACC_WIDTH  = {acc_width};
  parameter int OUT_WIDTH  = {out_width};   // output element width after activation+pool
  parameter int M_SIZE     = {m_size};   // rows of A, rows of C
  parameter int K_SIZE     = {k_size};   // cols of A = rows of B
  parameter int N_SIZE     = {n_size};   // cols of B, cols of C
  parameter int SA_SIZE    = {sa_size};

  localparam int ADDR_A_W  = $clog2(M_SIZE * K_SIZE);
  localparam int ADDR_B_W  = $clog2(K_SIZE * N_SIZE);
  localparam int ADDR_C_W  = $clog2(M_SIZE * N_SIZE);
  localparam int OUT_SAT_MAX =  (1 << (OUT_WIDTH-1)) - 1;
  localparam int OUT_SAT_MIN = -(1 << (OUT_WIDTH-1));

  logic clk, rst_n, start, done;

  // ============================================================
  // 여기만 수정하면 golden model이 자동으로 바뀜
  logic [1:0] act_type   = 2'b00;  // 00=bypass 01=ReLU 10=ReLU6 11=bypass
  logic [1:0] pool_type  = 2'b00;  // 00=bypass 01=maxpool2x2 10=avgpool2x2 11=bypass
  logic [4:0] quant_shift = 5'd0;  // arithmetic right-shift (0=no shift)
  // ============================================================

  logic norm_done;

  // BRAM_A write (SPI side) — M x K
  logic [ADDR_A_W-1:0]   spi_a_waddr;
  logic [DATA_WIDTH-1:0] spi_a_wdata;
  logic                  spi_a_we;

  // BRAM_B write (SPI side) — K x N
  logic [ADDR_B_W-1:0]   spi_b_waddr;
  logic [DATA_WIDTH-1:0] spi_b_wdata;
  logic                  spi_b_we;

  // BRAM_C read (SPI side) — M x N, OUT_WIDTH after activation+pool
  logic [ADDR_C_W-1:0]   spi_c_raddr;
  logic [OUT_WIDTH-1:0]  spi_c_rdata;

  logic [DATA_WIDTH-1:0] mat_a      [0:M_SIZE-1][0:K_SIZE-1];
  logic [DATA_WIDTH-1:0] mat_b      [0:K_SIZE-1][0:N_SIZE-1];
  logic [OUT_WIDTH-1:0]  mat_c      [0:M_SIZE-1][0:N_SIZE-1];
  logic [OUT_WIDTH-1:0]  expected_c [0:M_SIZE-1][0:N_SIZE-1];

  // Module-level temps (avoids XSim variable-in-begin error)
  logic [ACC_WIDTH-1:0]        golden_tmp;
  logic signed [ACC_WIDTH-1:0] shifted_tmp;
  logic [OUT_WIDTH-1:0]        sat_tmp;
  logic [OUT_WIDTH-1:0]        after_act [0:M_SIZE-1][0:N_SIZE-1];
  logic [OUT_WIDTH+1:0]        pool_sum;   // +2 bits for 4-element avg sum

  int error_cnt;
  realtime t_start, t_end;

  string file_a = "{file_a}";
  string file_b = "{file_b}";

  // DUT
  dig_top #(
      .DATA_WIDTH (DATA_WIDTH),
      .OUT_WIDTH  (OUT_WIDTH),
      .ACC_WIDTH  (ACC_WIDTH),
      .M_SIZE     (M_SIZE),
      .K_SIZE     (K_SIZE),
      .N_SIZE     (N_SIZE),
      .SA_SIZE    (SA_SIZE)
  ) dut (
      .clk         (clk),
      .rst_n       (rst_n),
      .start       (start),
      .done        (done),
      .act_type    (act_type),
      .pool_type   (pool_type),
      .quant_shift (quant_shift),
      .norm_done   (norm_done),
      .spi_a_waddr (spi_a_waddr),
      .spi_a_wdata (spi_a_wdata),
      .spi_a_we    (spi_a_we),
      .spi_b_waddr (spi_b_waddr),
      .spi_b_wdata (spi_b_wdata),
      .spi_b_we    (spi_b_we),
      .spi_c_raddr (spi_c_raddr),
      .spi_c_rdata (spi_c_rdata)
  );

  // Clock
  initial clk = 0;
  always #5 clk = ~clk;

  // ---------------------------------------------------------------
  // File load tasks (A: M×K, B: K×N)
  // ---------------------------------------------------------------
  task automatic load_mat_a(string filename);
    int fd, value;
    fd = $fopen(filename, "r");
    if (fd == 0) begin $display("[ERROR] Cannot open: %s", filename); $finish; end
    $display("[INFO] Loading A (%0dx%0d): %s", M_SIZE, K_SIZE, filename);
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < K_SIZE; j++) begin
        if ($fscanf(fd, "%d", value) != 1) begin
          $display("[ERROR] Read failed A[%0d][%0d]", i, j); $fclose(fd); $finish;
        end
        mat_a[i][j] = value[DATA_WIDTH-1:0];
      end
    $fclose(fd);
  endtask

  task automatic load_mat_b(string filename);
    int fd, value;
    fd = $fopen(filename, "r");
    if (fd == 0) begin $display("[ERROR] Cannot open: %s", filename); $finish; end
    $display("[INFO] Loading B (%0dx%0d): %s", K_SIZE, N_SIZE, filename);
    for (int i = 0; i < K_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++) begin
        if ($fscanf(fd, "%d", value) != 1) begin
          $display("[ERROR] Read failed B[%0d][%0d]", i, j); $fclose(fd); $finish;
        end
        mat_b[i][j] = value[DATA_WIDTH-1:0];
      end
    $fclose(fd);
  endtask

  // ---------------------------------------------------------------
  // BRAM write / read tasks
  // ---------------------------------------------------------------
  task automatic write_bram_a();
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < K_SIZE; j++) begin
        @(posedge clk);
        spi_a_waddr = ADDR_A_W'(i * K_SIZE + j);
        spi_a_wdata = mat_a[i][j];
        spi_a_we    = 1'b1;
      end
    @(posedge clk); spi_a_we = 1'b0;
  endtask

  task automatic write_bram_b();
    for (int i = 0; i < K_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++) begin
        @(posedge clk);
        spi_b_waddr = ADDR_B_W'(i * N_SIZE + j);
        spi_b_wdata = mat_b[i][j];
        spi_b_we    = 1'b1;
      end
    @(posedge clk); spi_b_we = 1'b0;
  endtask

  task automatic read_bram_c();
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++) begin
        @(posedge clk);
        spi_c_raddr = ADDR_C_W'(i * N_SIZE + j);
        @(posedge clk);
        mat_c[i][j] = spi_c_rdata;
      end
  endtask

  // ---------------------------------------------------------------
  // Write HW output to file
  // ---------------------------------------------------------------
  task automatic write_output_to_file(string filename);
    int fd;
    fd = $fopen(filename, "w");
    if (fd == 0) begin $display("[ERROR] Cannot open output: %s", filename); return; end
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++)
        $fwrite(fd, "%0d\\n", $signed(mat_c[i][j]));
    $fclose(fd);
    $display("[INFO] HW result written to: %s", filename);
  endtask

  // ---------------------------------------------------------------
  // Golden model — matches DUT: matmul → quant_shift → saturate → activate → pool
  // ---------------------------------------------------------------
  task automatic build_golden_model();

    // Step 1 & 2: matmul + shift + saturate + activate
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++) begin
        golden_tmp = '0;
        for (int k = 0; k < K_SIZE; k++)
          golden_tmp += ACC_WIDTH'(mat_a[i][k]) * ACC_WIDTH'(mat_b[k][j]);

        // Arithmetic right-shift (requantization)
        shifted_tmp = $signed(golden_tmp) >>> quant_shift;

        // Signed saturation to OUT_WIDTH
        if (shifted_tmp > $signed(ACC_WIDTH'(OUT_SAT_MAX)))
          sat_tmp = OUT_WIDTH'(OUT_SAT_MAX);
        else if (shifted_tmp < $signed(ACC_WIDTH'(OUT_SAT_MIN)))
          sat_tmp = OUT_WIDTH'(OUT_SAT_MIN);
        else
          sat_tmp = shifted_tmp[OUT_WIDTH-1:0];

        // Activation function
        case (act_type)
          2'b01: begin  // ReLU: zero if negative
            after_act[i][j] = sat_tmp[OUT_WIDTH-1] ? '0 : sat_tmp;
          end
          2'b10: begin  // ReLU6: clamp to [0, 6]
            if (sat_tmp[OUT_WIDTH-1])
              after_act[i][j] = '0;
            else if (sat_tmp > OUT_WIDTH'(6))
              after_act[i][j] = OUT_WIDTH'(6);
            else
              after_act[i][j] = sat_tmp;
          end
          default: begin  // 2'b00 / 2'b11: bypass (shift+saturate only)
            after_act[i][j] = sat_tmp;
          end
        endcase
      end

    // Step 3: pool (operates on M×N output)
    case (pool_type)
      2'b01: begin  // max pool 2x2 stride 2
        for (int i = 0; i < M_SIZE; i++)
          for (int j = 0; j < N_SIZE; j++)
            expected_c[i][j] = '0;

        for (int bi = 0; bi < M_SIZE/2; bi++)
          for (int bj = 0; bj < N_SIZE/2; bj++) begin
            expected_c[bi][bj] = after_act[2*bi][2*bj];
            if (after_act[2*bi  ][2*bj+1] > expected_c[bi][bj])
              expected_c[bi][bj] = after_act[2*bi  ][2*bj+1];
            if (after_act[2*bi+1][2*bj  ] > expected_c[bi][bj])
              expected_c[bi][bj] = after_act[2*bi+1][2*bj  ];
            if (after_act[2*bi+1][2*bj+1] > expected_c[bi][bj])
              expected_c[bi][bj] = after_act[2*bi+1][2*bj+1];
          end
      end

      2'b10: begin  // avg pool 2x2 stride 2
        for (int i = 0; i < M_SIZE; i++)
          for (int j = 0; j < N_SIZE; j++)
            expected_c[i][j] = '0;

        for (int bi = 0; bi < M_SIZE/2; bi++)
          for (int bj = 0; bj < N_SIZE/2; bj++) begin
            pool_sum = (OUT_WIDTH+2)'(after_act[2*bi  ][2*bj  ])
                     + (OUT_WIDTH+2)'(after_act[2*bi  ][2*bj+1])
                     + (OUT_WIDTH+2)'(after_act[2*bi+1][2*bj  ])
                     + (OUT_WIDTH+2)'(after_act[2*bi+1][2*bj+1]);
            expected_c[bi][bj] = OUT_WIDTH'(pool_sum >> 2);
          end
      end

      default: begin  // 2'b00 / 2'b11: bypass
        for (int i = 0; i < M_SIZE; i++)
          for (int j = 0; j < N_SIZE; j++)
            expected_c[i][j] = after_act[i][j];
      end
    endcase

  endtask

  // ---------------------------------------------------------------
  // Test scenario
  // ---------------------------------------------------------------
  initial begin
    rst_n = 0; start = 0;
    spi_a_we = 0; spi_b_we = 0;
    spi_a_waddr = '0; spi_b_waddr = '0; spi_c_raddr = '0;
    spi_a_wdata = '0; spi_b_wdata = '0;
    error_cnt = 0;

    // Load matrices
    load_mat_a(file_a);
    load_mat_b(file_b);

    $display("[INFO] Building golden model (act=%0b pool=%0b quant_shift=%0d)...",
             act_type, pool_type, quant_shift);
    build_golden_model();
    $display("[INFO] Golden model done");

    #25 rst_n = 1;
    @(posedge clk);

    // Write mat_a, mat_b to BRAM
    $display("============================================");
    $display("[INFO] Writing mat_a (%0dx%0d) to BRAM_A...", M_SIZE, K_SIZE);
    write_bram_a();
    $display("[INFO] Done (time=%0t, cycle=%0d)", $realtime, int'($realtime/10));
    $display("[INFO] Writing mat_b (%0dx%0d) to BRAM_B...", K_SIZE, N_SIZE);
    write_bram_b();
    $display("[INFO] Done (time=%0t, cycle=%0d)", $realtime, int'($realtime/10));
    $display("============================================");

    @(posedge clk);
    start = 1; @(posedge clk); start = 0;
    t_start = $realtime;

    $display("[INFO] (%0dx%0d) x (%0dx%0d) MatMul started (act=%0b pool=%0b shift=%0d)",
             M_SIZE, K_SIZE, K_SIZE, N_SIZE, act_type, pool_type, quant_shift);
    $display("[INFO] Files: %s, %s", file_a, file_b);
    $display("============================================");

    fork
      begin
        wait (done == 1'b1);
        t_end = $realtime;
        $display("[INFO] Finished at %0t (cycle=%0d)", t_end, int'($realtime/10));
        $display("[INFO] Latency: %0t (%0d clock cycles)", t_end - t_start,
                 int'((t_end - t_start) / 10));
      end
      begin
        repeat (1000000) @(posedge clk);
        $display("[ERROR] Timeout!"); $finish;
      end
    join_any
    disable fork;

    // Read result from BRAM_C
    $display("[INFO] Reading result from BRAM_C...");
    read_bram_c();
    write_output_to_file("{file_out}");

    // Verification
    $display("======= Verification =======");
    for (int i = 0; i < M_SIZE; i++)
      for (int j = 0; j < N_SIZE; j++)
        if (mat_c[i][j] !== expected_c[i][j]) begin
          $display("[FAIL] [%2d][%2d]: expected %0d got %0d",
                   i, j, $signed(expected_c[i][j]), $signed(mat_c[i][j]));
          error_cnt++;
        end

    $display("============================================");
    if (error_cnt == 0)
      $display("[PASS] All %0d elements match!", M_SIZE * N_SIZE);
    else
      $display("[FAIL] %0d errors.", error_cnt);
    $display("============================================");

    #50 $finish;
  end

endmodule
"""


if __name__ == "__main__":
    import sys as _sys

    # Usage: python gen_tb_v2.py <M> <K> <N> <SA> <ZR> [--data-width N] [--acc-width N]
    parser = argparse.ArgumentParser(description="Generate tb_dig_top.sv (rectangular)")
    parser.add_argument("m_size",       type=int)
    parser.add_argument("k_size",       type=int)
    parser.add_argument("n_size",       type=int)
    parser.add_argument("sa_size",      type=int)
    parser.add_argument("zero_ratio",   type=int)
    parser.add_argument("--data-width", type=int, default=8)
    parser.add_argument("--acc-width",  type=int, default=24)
    parser.add_argument("--out-width",  type=int, default=16)
    args = parser.parse_args()

    m_size     = args.m_size
    k_size     = args.k_size
    n_size     = args.n_size
    sa_size    = args.sa_size
    data_width = args.data_width
    acc_width  = args.acc_width
    out_width  = args.out_width
    zr         = args.zero_ratio
    label      = f"{m_size}x{k_size}x{n_size}"

    os.makedirs(os.path.join(PYTHON_DIR, "hw_result"), exist_ok=True)

    file_a   = f"./../python/input_matrix/matrix_a_{m_size}x{k_size}_{zr}_1.txt"
    file_b   = f"./../python/input_matrix/matrix_b_{k_size}x{n_size}_{zr}_1.txt"
    file_out = f"./../python/hw_result/output_matrix_{label}_{zr}.txt"

    content = generate_tb_final(
        data_width=data_width,
        acc_width=acc_width,
        m_size=m_size,
        k_size=k_size,
        n_size=n_size,
        sa_size=sa_size,
        file_a=file_a,
        file_b=file_b,
        file_out=file_out,
        out_width=out_width,
    )

    os.makedirs(os.path.dirname(OUT_TB), exist_ok=True)
    with open(OUT_TB, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[OK] Generated: {OUT_TB}")
    print(f"     DATA_WIDTH={data_width}, ACC_WIDTH={acc_width}, OUT_WIDTH={out_width}")
    print(f"     M={m_size}, K={k_size}, N={n_size}, SA={sa_size}, ZR={zr}")
    print(f"     file_a  = {file_a}")
    print(f"     file_b  = {file_b}")
    print(f"     file_out= {file_out}")
