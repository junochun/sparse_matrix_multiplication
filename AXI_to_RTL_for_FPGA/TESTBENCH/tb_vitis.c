/******************************************************************************
 * tb_vitis.c
 * Vitis Testbench for AXI-to-RTL Accelerator (dig_top)
 *
 * Register Map (offset from AXI_BASE_ADDR):
 *   0x00  CTRL        bit[0] = start (self-clearing after 1 cycle)
 *   0x04  STATUS      bit[0] = done, bit[1] = norm_done (read-only)
 *   0x08  SPI_A_WADDR Matrix A write address  (auto-increments on WDATA write)
 *   0x0C  SPI_A_WDATA Matrix A write data, 8-bit  (triggers spi_a_we)
 *   0x10  SPI_B_WADDR Matrix B write address  (auto-increments on WDATA write)
 *   0x14  SPI_B_WDATA Matrix B write data, 8-bit  (triggers spi_b_we)
 *   0x18  SPI_C_RADDR Matrix C read address
 *   0x1C  SPI_C_RDATA Matrix C read data, 16-bit (read-only)
 *   0x20  ACT_TYPE    Activation type [1:0]
 *   0x24  POOL_TYPE   Pooling   type  [1:0]
 *   0x28  QUANT_SHIFT Right-shift for re-quantization [4:0]
 *
 * Accelerator dimensions (match RTL parameters):
 *   A : M_SIZE x K_SIZE = 48 x 48, element width = 8-bit  (2304 elements)
 *   B : K_SIZE x N_SIZE = 48 x 48, element width = 8-bit  (2304 elements)
 *   C : M_SIZE x N_SIZE = 48 x 48, element width = 16-bit (2304 elements)
 *
 * Test pattern:
 *   A = all 1s, B = all 1s, ACT=0, POOL=0, QUANT_SHIFT=0
 *   Expected result: every C[i][j] == K_SIZE (= 48)
 *****************************************************************************/

#include <stdio.h>
#include "platform.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xil_io.h"
#include "sleep.h"

/* ─── AXI Peripheral Base Address ─────────────────────────────────────────
 * xparameters.h 에서 자동 생성된 매크로를 사용합니다.
 * IP 이름이 다를 경우 아래 심볼명을 수정하세요.
 * ─────────────────────────────────────────────────────────────────────── */
#ifdef XPAR_AXI_TO_RTL_0_BASEADDR
  #define AXI_BASE_ADDR         XPAR_AXI_TO_RTL_0_BASEADDR
#else
  #define AXI_BASE_ADDR         0x43C00000UL   /* fallback */
#endif

/* ─── Register Offsets ──────────────────────────────────────────────────── */
#define REG_CTRL                (AXI_BASE_ADDR + 0x00)
#define REG_STATUS              (AXI_BASE_ADDR + 0x04)
#define REG_SPI_A_WADDR         (AXI_BASE_ADDR + 0x08)
#define REG_SPI_A_WDATA         (AXI_BASE_ADDR + 0x0C)
#define REG_SPI_B_WADDR         (AXI_BASE_ADDR + 0x10)
#define REG_SPI_B_WDATA         (AXI_BASE_ADDR + 0x14)
#define REG_SPI_C_RADDR         (AXI_BASE_ADDR + 0x18)
#define REG_SPI_C_RDATA         (AXI_BASE_ADDR + 0x1C)
#define REG_ACT_TYPE            (AXI_BASE_ADDR + 0x20)
#define REG_POOL_TYPE           (AXI_BASE_ADDR + 0x24)
#define REG_QUANT_SHIFT         (AXI_BASE_ADDR + 0x28)

/* ─── STATUS Bit Masks ──────────────────────────────────────────────────── */
#define STATUS_DONE             (1u << 0)
#define STATUS_NORM_DONE        (1u << 1)

/* ─── ACT_TYPE Values ───────────────────────────────────────────────────── */
#define ACT_NONE                0u
#define ACT_RELU                1u
#define ACT_RELU6               2u

/* ─── POOL_TYPE Values ──────────────────────────────────────────────────── */
#define POOL_NONE               0u
#define POOL_MAX                1u
#define POOL_AVG                2u

/* ─── Matrix Dimensions (must match RTL parameters) ────────────────────── */
#define M_SIZE                  48
#define K_SIZE                  48
#define N_SIZE                  48
#define A_ELEMENTS              (M_SIZE * K_SIZE)   /* 2304 */
#define B_ELEMENTS              (K_SIZE * N_SIZE)   /* 2304 */
#define C_ELEMENTS              (M_SIZE * N_SIZE)   /* 2304 */

/* ─── Timeout for done-polling (microseconds) ───────────────────────────── */
#define POLL_TIMEOUT_US         5000000u    /* 5 seconds */
#define POLL_INTERVAL_US        100u

/* ─── AXI Access Helpers ────────────────────────────────────────────────── */
#define AXI_WRITE(addr, val)    Xil_Out32((UINTPTR)(addr), (u32)(val))
#define AXI_READ(addr)          Xil_In32 ((UINTPTR)(addr))

/* ─── Buffers ───────────────────────────────────────────────────────────── */
static u8  mat_a[A_ELEMENTS];
static u8  mat_b[B_ELEMENTS];
static u16 mat_c[C_ELEMENTS];

/* ─── Prototypes ────────────────────────────────────────────────────────── */
static void init_test_data   (void);
static void write_matrix_a   (void);
static void write_matrix_b   (void);
static int  start_and_poll   (void);
static void read_matrix_c    (void);
static int  verify_results   (void);
static void print_c_partial  (u32 rows, u32 cols);

/* ═══════════════════════════════════════════════════════════════════════════
 *  main
 * ═══════════════════════════════════════════════════════════════════════════ */
int main(void)
{
    int status;

    init_platform();

    xil_printf("\r\n=========================================\r\n");
    xil_printf("  AXI Accelerator Testbench  (Vitis)\r\n");
    xil_printf("  A(%dx%d) x B(%dx%d) = C(%dx%d)\r\n",
               M_SIZE, K_SIZE, K_SIZE, N_SIZE, M_SIZE, N_SIZE);
    xil_printf("=========================================\r\n\r\n");

    /* ── Step 1: Prepare input data ───────────────────────────────────── */
    xil_printf("[1] Initializing test data (A=1, B=1)...\r\n");
    init_test_data();

    /* ── Step 2: Configure accelerator ───────────────────────────────── */
    xil_printf("[2] Writing configuration registers...\r\n");
    AXI_WRITE(REG_ACT_TYPE,    ACT_NONE);
    AXI_WRITE(REG_POOL_TYPE,   POOL_NONE);
    AXI_WRITE(REG_QUANT_SHIFT, 0);

    xil_printf("    ACT_TYPE    = 0x%08X\r\n", AXI_READ(REG_ACT_TYPE));
    xil_printf("    POOL_TYPE   = 0x%08X\r\n", AXI_READ(REG_POOL_TYPE));
    xil_printf("    QUANT_SHIFT = 0x%08X\r\n", AXI_READ(REG_QUANT_SHIFT));

    /* ── Step 3: Load Matrix A ────────────────────────────────────────── */
    xil_printf("[3] Writing Matrix A (%u elements, 8-bit)...\r\n",
               (u32)A_ELEMENTS);
    write_matrix_a();
    xil_printf("    Done.\r\n");

    /* ── Step 4: Load Matrix B ────────────────────────────────────────── */
    xil_printf("[4] Writing Matrix B (%u elements, 8-bit)...\r\n",
               (u32)B_ELEMENTS);
    write_matrix_b();
    xil_printf("    Done.\r\n");

    /* ── Step 5: Start computation ────────────────────────────────────── */
    xil_printf("[5] Starting accelerator (CTRL[0] = 1)...\r\n");
    status = start_and_poll();
    if (status != 0) {
        xil_printf("ERROR: Timeout waiting for done signal!\r\n");
        cleanup_platform();
        return -1;
    }
    xil_printf("    done = 1 received.\r\n");

    /* ── Step 6: Read back Matrix C ──────────────────────────────────── */
    xil_printf("[6] Reading Matrix C (%u elements, 16-bit)...\r\n",
               (u32)C_ELEMENTS);
    read_matrix_c();
    xil_printf("    Done.\r\n");

    /* ── Step 7: Verify ───────────────────────────────────────────────── */
    xil_printf("[7] Verifying (expected C[i][j] = %u)...\r\n", (u32)K_SIZE);
    status = verify_results();

    if (status == 0) {
        xil_printf("\r\n>>> TEST PASSED <<<\r\n");
    } else {
        xil_printf("\r\n>>> TEST FAILED  (mismatch count = %d) <<<\r\n", status);
    }

    /* ── Step 8: Print corner of C ────────────────────────────────────── */
    xil_printf("\r\n[8] Matrix C top-left 4x4:\r\n");
    print_c_partial(4, 4);

    xil_printf("\r\n=========================================\r\n");
    xil_printf("  Testbench Complete\r\n");
    xil_printf("=========================================\r\n");

    cleanup_platform();
    return (status == 0) ? 0 : -1;
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  init_test_data
 *    Fill A and B with all-ones so C[i][j] == K_SIZE (= 48) is expected.
 * ═══════════════════════════════════════════════════════════════════════════ */
static void init_test_data(void)
{
    u32 i;
    for (i = 0; i < A_ELEMENTS; i++) mat_a[i] = 1u;
    for (i = 0; i < B_ELEMENTS; i++) mat_b[i] = 1u;
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  write_matrix_a
 *    Set SPI_A_WADDR = 0 once; hardware auto-increments after each
 *    SPI_A_WDATA write, so we just stream elements sequentially.
 * ═══════════════════════════════════════════════════════════════════════════ */
static void write_matrix_a(void)
{
    u32 i;
    AXI_WRITE(REG_SPI_A_WADDR, 0);
    for (i = 0; i < A_ELEMENTS; i++) {
        AXI_WRITE(REG_SPI_A_WDATA, (u32)mat_a[i]);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  write_matrix_b
 * ═══════════════════════════════════════════════════════════════════════════ */
static void write_matrix_b(void)
{
    u32 i;
    AXI_WRITE(REG_SPI_B_WADDR, 0);
    for (i = 0; i < B_ELEMENTS; i++) {
        AXI_WRITE(REG_SPI_B_WDATA, (u32)mat_b[i]);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  start_and_poll
 *    Pulses CTRL[0] = 1 (hardware self-clears it next cycle), then polls
 *    STATUS[0] (done) every POLL_INTERVAL_US until set or timeout.
 *    Returns 0 on success, -1 on timeout.
 * ═══════════════════════════════════════════════════════════════════════════ */
static int start_and_poll(void)
{
    u32 elapsed_us = 0u;

    AXI_WRITE(REG_CTRL, 1u);    /* assert start */

    while (elapsed_us < POLL_TIMEOUT_US) {
        if (AXI_READ(REG_STATUS) & STATUS_DONE) {
            return 0;
        }
        usleep(POLL_INTERVAL_US);
        elapsed_us += POLL_INTERVAL_US;
    }
    return -1;
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  read_matrix_c
 *    SRAM_C has 1-cycle registered read latency (always_ff, see SRAM_C.sv).
 *    Pipeline: pre-load addr[i+1] BEFORE reading data[i] so the AXI write
 *    overhead gives the SRAM the 1 clock cycle it needs to update spi_rdata.
 *
 *    Timeline:
 *      [before loop] AXI_WRITE(addr 0)  ← SRAM starts reading addr 0
 *      [i=0]         AXI_WRITE(addr 1)  ← provides delay; SRAM addr-0 data ready
 *                    AXI_READ  → data[0] ✓
 *      [i=1]         AXI_WRITE(addr 2)  ← provides delay; SRAM addr-1 data ready
 *                    AXI_READ  → data[1] ✓
 *      ...
 *      [i=N-1]       no next write needed; AXI_READ overhead is sufficient
 *                    AXI_READ  → data[N-1] ✓
 * ═══════════════════════════════════════════════════════════════════════════ */
static void read_matrix_c(void)
{
    u32 i;

    /* Pre-load address 0 — SRAM begins registered read */
    AXI_WRITE(REG_SPI_C_RADDR, 0);

    for (i = 0; i < C_ELEMENTS; i++) {
        /* Write next address (acts as 1-cycle pipeline delay for addr i) */
        if (i + 1 < C_ELEMENTS) {
            AXI_WRITE(REG_SPI_C_RADDR, i + 1);
        } else {
            /* Last element: dummy STATUS read provides the required delay */
            (void)AXI_READ(REG_STATUS);
        }
        mat_c[i] = (u16)(AXI_READ(REG_SPI_C_RDATA) & 0xFFFFu);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  verify_results
 *    Checks every element against the SW golden value.
 *    Golden: A=1, B=1, shift=0, no act/pool  → C[i][j] = K_SIZE
 *    Returns number of mismatches (0 = PASS).
 * ═══════════════════════════════════════════════════════════════════════════ */
static int verify_results(void)
{
    u32 i;
    int mismatches = 0;
    u16 expected   = (u16)K_SIZE;

    for (i = 0; i < C_ELEMENTS; i++) {
        if (mat_c[i] != expected) {
            if (mismatches < 10) {      /* print up to 10 mismatches */
                xil_printf("  MISMATCH C[%4u]: expected %5u, got %5u\r\n",
                           i, (u32)expected, (u32)mat_c[i]);
            }
            mismatches++;
        }
    }

    if (mismatches >= 10) {
        xil_printf("  ... (%d total mismatches)\r\n", mismatches);
    }
    return mismatches;
}

/* ═══════════════════════════════════════════════════════════════════════════
 *  print_c_partial
 *    Prints the top-left (rows x cols) sub-matrix of C.
 * ═══════════════════════════════════════════════════════════════════════════ */
static void print_c_partial(u32 rows, u32 cols)
{
    u32 r, c;
    for (r = 0; r < rows && r < (u32)M_SIZE; r++) {
        for (c = 0; c < cols && c < (u32)N_SIZE; c++) {
            xil_printf("  %5u", (u32)mat_c[r * N_SIZE + c]);
        }
        xil_printf("\r\n");
    }
}
