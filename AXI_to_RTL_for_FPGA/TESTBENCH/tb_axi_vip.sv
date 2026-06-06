`timescale 1ns / 1ps

// ---------------------------------------------------------------------------
// AXI VIP testbench for sparse systolic array (AXI_to_RTL + dig_top)
//
// Block design:  sparse_dig_top  (sparse_dig_top.bd)
// VIP instance:  sparse_dig_top_axi_vip_0_0
//
// If Vivado auto-generates a different wrapper name or clock port names,
// adjust: sparse_dig_top_wrapper  /  .aclk_0  /  .aresetn_0
// ---------------------------------------------------------------------------

import axi_vip_pkg::*;
import sparse_dig_top_axi_vip_0_0_pkg::*;

module tb_axi_vip;

  // ---------------------------------------------------------------------------
  // Clock / Reset
  // ---------------------------------------------------------------------------
  bit clk     = 0;
  bit aresetn = 0;

  always begin #5ns clk = ~clk; end  // 100 MHz

  // ---------------------------------------------------------------------------
  // Register map  (BASE = address Vivado assigns to AXI_to_RTL in address editor)
  // ---------------------------------------------------------------------------
  localparam xil_axi_ulong BASE          = 32'h44A0_0000;
  localparam xil_axi_ulong REG_CTRL      = BASE + 32'h00; // [0]=start (pulse)
  localparam xil_axi_ulong REG_STATUS    = BASE + 32'h04; // [0]=done, [1]=norm_done (read-only)
  localparam xil_axi_ulong REG_A_WADDR  = BASE + 32'h08; // spi_a_waddr (auto-inc on data write)
  localparam xil_axi_ulong REG_A_WDATA  = BASE + 32'h0C; // spi_a_wdata (pulses we, increments addr)
  localparam xil_axi_ulong REG_B_WADDR  = BASE + 32'h10; // spi_b_waddr
  localparam xil_axi_ulong REG_B_WDATA  = BASE + 32'h14; // spi_b_wdata
  localparam xil_axi_ulong REG_C_RADDR  = BASE + 32'h18; // spi_c_raddr
  localparam xil_axi_ulong REG_C_RDATA  = BASE + 32'h1C; // spi_c_rdata (read-only, OUT_WIDTH=16)
  localparam xil_axi_ulong REG_ACT_TYPE  = BASE + 32'h20; // act_type  [1:0]
  localparam xil_axi_ulong REG_POOL_TYPE = BASE + 32'h24; // pool_type [1:0]
  localparam xil_axi_ulong REG_QUANT_SH  = BASE + 32'h28; // quant_shift [4:0]

  // Matrix dimensions must match dig_top parameters
  localparam integer M_SIZE = 12;
  localparam integer K_SIZE = 12;
  localparam integer N_SIZE = 12;

  // ---------------------------------------------------------------------------
  // Block design instantiation
  // ---------------------------------------------------------------------------
  sparse_dig_top_wrapper sparse_dig_top_i (
    .aclk_0    (clk),
    .aresetn_0 (aresetn)
  );

  // AXI VIP master agent
  sparse_dig_top_axi_vip_0_0_mst_t master;

  // ---------------------------------------------------------------------------
  // Helper tasks
  // ---------------------------------------------------------------------------
  task automatic axil_write(input xil_axi_ulong addr, input bit [31:0] data);
    xil_axi_resp_t resp;
    master.AXI4LITE_WRITE_BURST(addr, 3'b000, data, resp);
  endtask

  task automatic axil_read(input xil_axi_ulong addr, output bit [31:0] data);
    xil_axi_resp_t resp;
    master.AXI4LITE_READ_BURST(addr, 3'b000, data, resp);
    $display("[%0t] READ  addr=0x%08h  data=0x%08h", $time, addr, data);
  endtask

  // Write a contiguous block of 8-bit matrix elements starting at flat_start.
  // Each write to REG_x_WDATA auto-increments the address inside the slave,
  // so only one REG_x_WADDR write is needed before the burst.
  task automatic write_matrix_block(
    input xil_axi_ulong  addr_reg,
    input xil_axi_ulong  data_reg,
    input int            flat_start,
    input bit [7:0]      vals[],
    input int            n
  );
    int k;
    axil_write(addr_reg, 32'(flat_start));
    for (k = 0; k < n; k++)
      axil_write(data_reg, {24'h0, vals[k]});
  endtask

  // Poll REG_STATUS[0] (done) with timeout
  task automatic wait_done(output bit ok);
    bit [31:0] status;
    int        cnt = 0;
    ok = 0;
    forever begin
      axil_read(REG_STATUS, status);
      if (status[0]) begin ok = 1; break; end
      cnt++;
      if (cnt > 200000) begin
        $display("[%0t] TIMEOUT waiting for done", $time);
        break;
      end
      repeat (10) @(posedge clk);
    end
  endtask

  // ---------------------------------------------------------------------------
  // Test sequence
  // ---------------------------------------------------------------------------
  // Test vectors:
  //   A[0][0]=2  A[0][1]=3  A[1][0]=6   (flat addrs 0, 1, K_SIZE=48)
  //   B[0][0]=4  B[0][1]=7  B[1][0]=5   (flat addrs 0, 1, N_SIZE=48)
  //
  // Expected C = A * B:
  //   C[0][0] = 2*4 + 3*5 = 23
  //   C[0][1] = 2*7 + 3*0 = 14
  //   C[1][0] = 6*4 + 0*5 = 24
  //   C[1][1] = 6*7        = 42
  //   C[0][2] = 0,  C[2][0] = 0,  C[47][47] = 0  (boundary zeros)
  // ---------------------------------------------------------------------------
  // Declare all test variables at module scope to avoid SV scoping warnings
  bit [7:0]  a_vals[2];
  bit        done_ok;
  bit [31:0] c_val;

  initial begin
    // Bind VIP agent
    master = new("master vip agent", sparse_dig_top_i.sparse_dig_top_i.axi_vip_0.inst.IF);
    master.start_master();

    // Reset (Xilinx AXI VIP requires >= 16 cycles)
    aresetn = 0;
    repeat (20) @(posedge clk);
    aresetn = 1;
    repeat (5)  @(posedge clk);

    // ------------------------------------------------------------------
    // 0. Configure computation parameters (act_type=0, pool_type=0, quant_shift=0)
    // ------------------------------------------------------------------
    axil_write(REG_ACT_TYPE,  32'd0);  // no activation
    axil_write(REG_POOL_TYPE, 32'd0);  // no pooling
    axil_write(REG_QUANT_SH,  32'd0);  // no requantization shift

    // ------------------------------------------------------------------
    // 1. Load Matrix A  — A[r][c] flat addr = r*K_SIZE + c
    //    A[0][0]=2 (flat 0), A[0][1]=3 (flat 1), A[1][0]=6 (flat K_SIZE=48)
    // ------------------------------------------------------------------
    a_vals[0] = 8'd2;
    a_vals[1] = 8'd3;
    write_matrix_block(REG_A_WADDR, REG_A_WDATA, 0, a_vals, 2);  // A[0][0..1]
    axil_write(REG_A_WADDR, 32'(K_SIZE));   // A[1][0] at flat 48
    axil_write(REG_A_WDATA, 32'd6);
    $display("[%0t] Matrix A loaded", $time);

    // ------------------------------------------------------------------
    // 2. Load Matrix B  — B[r][c] flat addr = r*N_SIZE + c
    //    B[0][0]=4 (flat 0), B[0][1]=7 (flat 1), B[1][0]=5 (flat N_SIZE=48)
    // ------------------------------------------------------------------
    axil_write(REG_B_WADDR, 32'd0);         // B[0][0] at flat 0
    axil_write(REG_B_WDATA, 32'd4);
    axil_write(REG_B_WADDR, 32'd1);         // B[0][1] at flat 1
    axil_write(REG_B_WDATA, 32'd7);
    axil_write(REG_B_WADDR, 32'(K_SIZE));   // B[1][0] at flat 48
    axil_write(REG_B_WDATA, 32'd5);
    $display("[%0t] Matrix B loaded", $time);

    // ------------------------------------------------------------------
    // 3. Start computation
    // ------------------------------------------------------------------
    axil_write(REG_CTRL, 32'h1);
    $display("[%0t] Computation started", $time);

    // ------------------------------------------------------------------
    // 4. Poll done
    // ------------------------------------------------------------------
    wait_done(done_ok);
    if (done_ok) $display("[%0t] Done received", $time);

    // ------------------------------------------------------------------
    // 5. Read C results  — C[r][c] flat addr = r*N_SIZE + c
    // ------------------------------------------------------------------
    // C[0][0] = 2*4 + 3*5 = 23
    axil_write(REG_C_RADDR, 32'd0);
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd23)
      $display("[PASS] C[0][0] = %0d  (expected 23)", c_val);
    else
      $display("[FAIL] C[0][0] = %0d  (expected 23)", c_val);

    // C[0][1] = 2*7 = 14
    axil_write(REG_C_RADDR, 32'd1);
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd14)
      $display("[PASS] C[0][1] = %0d  (expected 14)", c_val);
    else
      $display("[FAIL] C[0][1] = %0d  (expected 14)", c_val);

    // C[1][0] = 6*4 = 24
    axil_write(REG_C_RADDR, 32'(N_SIZE));
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd24)
      $display("[PASS] C[1][0] = %0d  (expected 24)", c_val);
    else
      $display("[FAIL] C[1][0] = %0d  (expected 24)", c_val);

    // C[1][1] = 6*7 = 42
    axil_write(REG_C_RADDR, 32'(N_SIZE + 1));
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd42)
      $display("[PASS] C[1][1] = %0d  (expected 42)", c_val);
    else
      $display("[FAIL] C[1][1] = %0d  (expected 42)", c_val);

    // C[0][2] = 0 (B column 2 is all zero)
    axil_write(REG_C_RADDR, 32'd2);
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd0)
      $display("[PASS] C[0][2] = %0d  (expected 0)", c_val);
    else
      $display("[FAIL] C[0][2] = %0d  (expected 0)", c_val);

    // C[2][0] = 0 (A row 2 is all zero)
    axil_write(REG_C_RADDR, 32'(2*N_SIZE));
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd0)
      $display("[PASS] C[2][0] = %0d  (expected 0)", c_val);
    else
      $display("[FAIL] C[2][0] = %0d  (expected 0)", c_val);

    // C[47][47] = 0 (corner boundary)
    axil_write(REG_C_RADDR, 32'(47*N_SIZE + 47));
    repeat (4) @(posedge clk);
    axil_read(REG_C_RDATA, c_val);
    if (c_val == 32'd0)
      $display("[PASS] C[47][47] = %0d  (expected 0)", c_val);
    else
      $display("[FAIL] C[47][47] = %0d  (expected 0)", c_val);

    #100ns;
    $finish;
  end

endmodule
