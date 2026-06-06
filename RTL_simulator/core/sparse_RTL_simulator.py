import numpy as np
import math

"""
Cycle-accurate Python simulator for Sparse Systolic Array Accelerator.
Supports rectangular matrix multiplication: A(M×K) x B(K×N) = C(M×N)

Mirrors RTL hierarchy:
  single_PE -> SA_NxN -> SA_TOP -> sa_controller (Triple-FSM: Load/Compute/Save)
  memory_top -> accelerator_top -> dig_top

Design notes
------------
- SA compute is vectorized (NumPy) for speed; cycle cost is per-PE model.
- Triple-FSM state transitions are simulated clock-by-clock (exact cycle count).

Configurable Parameters
-----------------------
M_SIZE     : rows of A, rows of C
K_SIZE     : cols of A = rows of B (inner dimension)
N_SIZE     : cols of B, cols of C
SA_SIZE    : systolic array tile size (square)
DATA_WIDTH : element bit-width
ACC_WIDTH  : accumulator bit-width
POOL_TYPE  : 0=bypass  1=max-pool2x2  2=avg-pool2x2

Matrix input modes (FILE_A/FILE_B take priority over random generation):
FILE_A     : path to mat_a text file  (row-major, M_SIZE*K_SIZE values)
FILE_B     : path to mat_b text file  (row-major, K_SIZE*N_SIZE values)

ZERO_RATIO : sparsity for random generation (ignored when files are loaded)
SEED       : RNG seed for random generation (ignored when files are loaded)
"""

# ─────────────────────────────────────────────────────────────
# Parameters (Default Values)
# ─────────────────────────────────────────────────────────────
M_SIZE     = 35   # rows of A, rows of C
K_SIZE     = 45   # cols of A = rows of B
N_SIZE     = 32   # cols of B, cols of C
SA_SIZE    = 32
DATA_WIDTH = 8
ACC_WIDTH  = 32
POOL_TYPE  = 0
FILE_A     = ""
FILE_B     = ""
# Random generation fallback (used only when FILE_A/FILE_B are empty)
ZERO_RATIO = 0.5
SEED       = 42
# ─────────────────────────────────────────────────────────────

DMAX = (1 << DATA_WIDTH) - 1
AMAX = (1 << ACC_WIDTH) - 1


# ═══════════════════════════════════════════════════════════════
# Matrix helpers
# ═══════════════════════════════════════════════════════════════
def _ceildiv(a, b):
    return (a + b - 1) // b


def load_matrix_from_file(path: str, rows: int, cols: int) -> np.ndarray:
    """
    Load a matrix from a text file.
    One decimal integer per line, row-major order (rows*cols values).
    Matches the format used by tb_dig_top.sv.
    """
    with open(path, "r") as f:
        values = [int(v) for v in f.read().split()]
    expected = rows * cols
    if len(values) != expected:
        raise ValueError(
            f"{path}: expected {expected} values ({rows}x{cols}), got {len(values)}")
    return np.array(values, dtype=np.int32).reshape(rows, cols)


def make_matrix(rows, cols, zero_ratio, rng):
    mat = rng.integers(1, DMAX + 1, size=(rows, cols), dtype=np.int32)
    mat[rng.random((rows, cols)) < zero_ratio] = 0
    return mat


def row_bv(row):
    """Build a SA_SIZE-bit bitvector for a row (1 bit per non-zero element)."""
    bv = 0
    for i, v in enumerate(row):
        if v:
            bv |= 1 << i
    return bv


# ═══════════════════════════════════════════════════════════════
# SA tile compute  (vectorized result, exact cycle cost)
# ═══════════════════════════════════════════════════════════════
def sa_compute(tile_a, tile_b, bv_a, bv_b, sa_size, dense_mode=False):
    """
    Compute one SA_SIZE×SA_SIZE tile product and return the
    (result, worst_case_cycles, effective_macs) triple.
    The cycle model mirrors the RTL single_PE pipeline exactly.
    When dense_mode=True all bitvectors are forced to all-ones before
    the cycle loop, disabling BV zero-skip (SCALE-Sim dense baseline).
    """
    result = (tile_a.astype(np.int64) @ tile_b.astype(np.int64)) & AMAX

    if dense_mode:
        bv_a = [(1 << sa_size) - 1] * sa_size
        bv_b = [(1 << sa_size) - 1] * sa_size

    # Transpose bv_b to column-major bitvectors (RTL column matching)
    bv_b_col = [0] * sa_size
    for r in range(sa_size):
        for c in range(sa_size):
            if bv_b[r] & (1 << c):
                bv_b_col[c] |= (1 << r)

    worst = 0
    effective_macs = 0
    for i in range(sa_size):
        for j in range(sa_size):
            k = bin(bv_a[i] & bv_b_col[j]).count("1")
            effective_macs += k
            finish = i + j + k   # cycle when psum_valid_out goes high
            if finish > worst:
                worst = finish
    # +4 cycles derived mathematically from exact RTL single_PE pipeline
    return result.astype(np.int32), worst + 4, effective_macs


# ═══════════════════════════════════════════════════════════════
# norm_pool  (1-cycle pipeline)
# ═══════════════════════════════════════════════════════════════
def norm_pool(data, pool_type, sa_size):
    n = sa_size; h = n // 2
    out = np.zeros((n, n), dtype=np.int32)
    if pool_type in (0, 3):
        out = data.copy() & DMAX
    elif pool_type == 1:
        for bi in range(h):
            for bj in range(h):
                out[bi, bj] = max(data[2*bi, 2*bj],   data[2*bi, 2*bj+1],
                                  data[2*bi+1, 2*bj], data[2*bi+1, 2*bj+1])
    elif pool_type == 2:
        for bi in range(h):
            for bj in range(h):
                s = (int(data[2*bi, 2*bj])   + int(data[2*bi, 2*bj+1]) +
                     int(data[2*bi+1, 2*bj]) + int(data[2*bi+1, 2*bj+1]))
                out[bi, bj] = (s >> 2) & DMAX
    return out


# ═══════════════════════════════════════════════════════════════
# BRAM layout  (exact RTL addressing)
# ═══════════════════════════════════════════════════════════════
def build_bram_a(mat, m_size, k_size, sa_size):
    """
    BRAM_A address: (blk_r * SA_SIZE + row) * K_TILES + part_idx
    mat shape: (M_SIZE, K_SIZE) — stored row-by-row with K tiling.
    Tiles are SA_SIZE × SA_SIZE; rows/cols beyond the tile boundary
    are zero-padded in the RTL hardware (handled by BRAM_A.sv), so
    the Python dict only needs valid tile entries.
    """
    m_tiles = _ceildiv(m_size, sa_size)
    k_tiles = _ceildiv(k_size, sa_size)
    b = {}
    for br in range(m_tiles):
        for r in range(sa_size):
            real_r = br * sa_size + r        # actual row index in mat_a
            for pt in range(k_tiles):
                addr = (br * sa_size + r) * k_tiles + pt
                row_vec = np.zeros(sa_size, dtype=np.int32)
                if real_r < m_size:
                    for c in range(sa_size):
                        real_c = pt * sa_size + c
                        if real_c < k_size:
                            row_vec[c] = mat[real_r, real_c]
                b[addr] = row_vec
    return b

def build_bram_b(mat, k_size, n_size, sa_size):
    """
    BRAM_B address: (part_idx * SA_SIZE + row) * N_TILES + blk_c
    mat shape: (K_SIZE, N_SIZE) — stored with K tiling on rows, N tiling on cols.
    """
    k_tiles = _ceildiv(k_size, sa_size)
    n_tiles = _ceildiv(n_size, sa_size)
    b = {}
    for pt in range(k_tiles):
        for r in range(sa_size):
            real_r = pt * sa_size + r        # actual row index in mat_b (i.e., k-index)
            for bc in range(n_tiles):
                addr = (pt * sa_size + r) * n_tiles + bc
                row_vec = np.zeros(sa_size, dtype=np.int32)
                if real_r < k_size:
                    for c in range(sa_size):
                        real_c = bc * sa_size + c
                        if real_c < n_size:
                            row_vec[c] = mat[real_r, real_c]
                b[addr] = row_vec
    return b

def read_bram_c(bc, m_size, n_size, sa_size):
    """Reconstruct the M_SIZE×N_SIZE output matrix from BRAM_C entries."""
    m_tiles = _ceildiv(m_size, sa_size)
    n_tiles = _ceildiv(n_size, sa_size)
    out = np.zeros((m_size, n_size), dtype=np.int32)
    for br in range(m_tiles):
        for r in range(sa_size):
            real_r = br * sa_size + r
            if real_r >= m_size:
                continue
            for bcc in range(n_tiles):
                a = (br * sa_size + r) * n_tiles + bcc
                if a in bc:
                    row_data = bc[a]
                    for c in range(sa_size):
                        real_c = bcc * sa_size + c
                        if real_c < n_size:
                            out[real_r, real_c] = row_data[c]
    return out

# ═══════════════════════════════════════════════════════════════
# Next-tile index helper  (mirrors RTL LD_LAST_ROW advance logic)
# Iteration order: pt (K_TILES) -> bc (N_TILES) -> br (M_TILES)
# ═══════════════════════════════════════════════════════════════
def _next_tile(br, bc, pt, m_tiles, k_tiles, n_tiles):
    """Return (next_br, next_bc, next_pt, is_done)."""
    npt = pt + 1
    nbr = br; nbc = bc; fin = False
    if npt >= k_tiles:
        npt = 0
        if nbc >= n_tiles - 1:
            nbc = 0
            fin = (nbr >= m_tiles - 1)
            if not fin:
                nbr += 1
        else:
            nbc += 1
    return nbr, nbc, npt, fin


# ═══════════════════════════════════════════════════════════════
# Main simulation — cycle-accurate Triple-FSM
# ═══════════════════════════════════════════════════════════════
def run_simulation(m_size=M_SIZE, k_size=K_SIZE, n_size=N_SIZE,
                   sa_size=SA_SIZE,
                   zero_ratio=ZERO_RATIO, pool_type=POOL_TYPE,
                   seed=SEED, verbose=True,
                   file_a=FILE_A, file_b=FILE_B,
                   val_a=None, val_b=None,
                   dense_mode=False,
                   dram_bw=None):
    """
    Run a cycle-accurate simulation of A(m_size×k_size) × B(k_size×n_size).

    dram_bw : float or None
        Off-chip DRAM bandwidth in words/cycle.
        When set, computes DRAM stall cycles assuming DRAM must supply all of
        matrix A (m×k words) and B (k×n words) and drain matrix C (m×n words).
        stall_cycles = max(0, ceil((m*k + k*n + m*n) / dram_bw) - compute_cycles)
        When None, DRAM stall is not modelled (ideal infinite bandwidth).

    Returns a dict:
        total_cycles : int
        result       : np.ndarray  (m_size × n_size, DATA_WIDTH-clamped)
        golden       : np.ndarray  (m_size × n_size, DATA_WIDTH-clamped)
        done         : bool
    """
    m_tiles = _ceildiv(m_size, sa_size)
    k_tiles = _ceildiv(k_size, sa_size)
    n_tiles = _ceildiv(n_size, sa_size)

    # ── Load matrices ─────────────────────────────────────────
    if val_a is not None and val_b is not None:
        mat_a = val_a
        mat_b = val_b
        src_a = "Direct Numpy Array"
        src_b = "Direct Numpy Array"
    elif file_a and file_b:
        mat_a = load_matrix_from_file(file_a, m_size, k_size)
        mat_b = load_matrix_from_file(file_b, k_size, n_size)
        src_a = file_a
        src_b = file_b
    else:
        rng   = np.random.default_rng(seed)
        mat_a = make_matrix(m_size, k_size, zero_ratio, rng)
        mat_b = make_matrix(k_size, n_size, zero_ratio, rng)
        src_a = f"random (seed={seed}, zero={zero_ratio:.0%})"
        src_b = src_a

    if verbose:
        az = np.mean(mat_a == 0); bz = np.mean(mat_b == 0)
        pool_names = {0: "bypass", 1: "max-pool2x2", 2: "avg-pool2x2"}
        print(f"\n{'='*60}")
        print("  Sparse SA Accelerator – Python Cycle-Accurate Simulator")
        print(f"{'='*60}")
        print(f"  Matrix A   : {m_size}x{k_size}  |  Matrix B : {k_size}x{n_size}")
        print(f"  SA_SIZE    : {sa_size}x{sa_size}")
        print(f"  Tiles(MxKxN): {m_tiles}x{k_tiles}x{n_tiles}")
        print(f"  DATA_WIDTH : {DATA_WIDTH}-bit  |  ACC_WIDTH : {ACC_WIDTH}-bit")
        print(f"  FILE_A     : {src_a}")
        print(f"  FILE_B     : {src_b}")
        print(f"  Sparsity   : A={az:.1%} zeros, B={bz:.1%} zeros")
        print(f"  POOL_TYPE  : {pool_names.get(pool_type, '?')}")
        print(f"{'='*60}")

    # ── Build BRAMs ───────────────────────────────────────────
    bram_a = build_bram_a(mat_a, m_size, k_size, sa_size)
    bram_b = build_bram_b(mat_b, k_size, n_size, sa_size)
    bram_c: dict = {}

    # ── Ping-pong input buffers [sel=0/1] ─────────────────────
    pp_ta  = [np.zeros((sa_size, sa_size), np.int32) for _ in range(2)]
    pp_tb  = [np.zeros((sa_size, sa_size), np.int32) for _ in range(2)]
    pp_bva = [[0] * sa_size for _ in range(2)]
    pp_bvb = [[0] * sa_size for _ in range(2)]
    pp_rdy = [False, False]

    # ── Dual accumulator bank ─────────────────────────────────
    acc_buf = [np.zeros((sa_size, sa_size), np.int64) for _ in range(2)]

    # ── Load FSM ──────────────────────────────────────────────
    ld_s      = "LD_IDLE"
    ld_br = ld_bc = ld_pt = 0
    ld_row    = 0
    ld_buf    = 0

    # ── Compute FSM ───────────────────────────────────────────
    cp_s      = "CP_IDLE"
    cp_buf    = 0
    acc_sel   = 0
    cp_br = cp_bc = cp_pt = 0
    cp_last   = False
    sv_reg    = dict(buf=0, br=0, bc=0, snap=None)
    bc_cons = False; bc_cons_nxt = False; bc_cs = 0
    pp_rdy_nxt = [False, False]
    av_pulse = False; av_pulse_nxt = False
    np_pend = False; np_pend_nxt = False
    sv_s_reg = "S_IDLE"

    # ── SA compute state ──────────────────────────────────────
    sa_ta  = np.zeros((sa_size, sa_size), np.int32)
    sa_tb  = np.zeros((sa_size, sa_size), np.int32)
    sa_bva = [0] * sa_size; sa_bvb = [0] * sa_size
    sa_pend = False; sa_cl = 0; sa_res = None

    # ── Save FSM ──────────────────────────────────────────────
    sv_s      = "S_IDLE"
    sv_row    = 0
    sv_br     = 0; sv_bc_s = 0
    sv_norm   = None
    np_pend   = False

    # Ancillary CP state (registered across cycles)
    save_buf_sel = 0; save_blk_r = 0; save_blk_c = 0

    done  = False
    cycle = 0
    total_tiles = m_tiles * k_tiles * n_tiles
    MAX_CYCLES = total_tiles * (sa_size * 6 + 60) * 8 + 4000
    total_effective_macs = 0

    # ── BRAM access counters (row accesses; 1 row = sa_size words) ────
    bram_a_row_reads  = 0   # incremented each LD_LOAD cycle (BRAM_A)
    bram_b_row_reads  = 0   # incremented each LD_LOAD cycle (BRAM_B)
    bram_c_row_writes = 0   # incremented each S_SAVE_TILE cycle (BRAM_C)

    while not done and cycle < MAX_CYCLES:
        cycle += 1
        start = (cycle == 1)

        # ── Non-blocking (flip-flop) updates ──────────────────
        pp_rdy      = pp_rdy_nxt[:]
        bc_cons     = bc_cons_nxt
        bc_cons_nxt = False
        av_pulse     = av_pulse_nxt
        av_pulse_nxt = False
        np_pend      = np_pend_nxt
        np_pend_nxt  = False
        sv_s_reg     = sv_s

        # Registered buf_consume clears ready flag
        if bc_cons:
            pp_rdy_nxt[bc_cs] = False
        bc_cons = False

        # ── SA countdown ──────────────────────────────────────
        if sa_pend:
            sa_cl -= 1
            if sa_cl == 0:
                sa_pend = False

        # ── Load FSM ──────────────────────────────────────────
        ld_s_reg = ld_s
        if ld_s_reg == "LD_IDLE":
            if start:
                ld_br = ld_bc = ld_pt = 0
                ld_buf = 0; ld_row = 0
                pp_rdy_nxt[0] = pp_rdy_nxt[1] = False
                ld_s = "LD_ADDR"

        elif ld_s_reg == "LD_ADDR":
            ld_row = 0
            ld_s = "LD_LOAD"

        elif ld_s_reg == "LD_LOAD":
            r  = ld_row
            # BRAM_A: addr = (ld_br * SA_SIZE + r) * K_TILES + ld_pt
            aa = (ld_br * sa_size + r) * k_tiles + ld_pt
            # BRAM_B: addr = (ld_pt * SA_SIZE + r) * N_TILES + ld_bc
            ba = (ld_pt * sa_size + r) * n_tiles + ld_bc
            pp_ta[ld_buf][r]  = bram_a[aa]
            pp_tb[ld_buf][r]  = bram_b[ba]
            pp_bva[ld_buf][r] = row_bv(bram_a[aa])
            pp_bvb[ld_buf][r] = row_bv(bram_b[ba])
            bram_a_row_reads += 1
            bram_b_row_reads += 1
            if ld_row < sa_size - 1:
                ld_row += 1
            else:
                ld_s = "LD_LAST_ROW"

        elif ld_s_reg == "LD_LAST_ROW":
            pp_rdy_nxt[ld_buf] = True
            nbr, nbc, npt, fin = _next_tile(ld_br, ld_bc, ld_pt,
                                             m_tiles, k_tiles, n_tiles)
            ld_br = nbr; ld_bc = nbc; ld_pt = npt
            if fin:
                ld_s = "LD_DONE"
            else:
                ld_buf ^= 1
                if not pp_rdy[ld_buf]:
                    ld_row = 0; ld_s = "LD_ADDR"
                else:
                    ld_s = "LD_WAIT_BUF"

        elif ld_s_reg == "LD_WAIT_BUF":
            if not pp_rdy[ld_buf]:
                ld_row = 0; ld_s = "LD_ADDR"
        # LD_DONE: no-op

        # ── Compute FSM ───────────────────────────────────────
        wr_en   = False; wr_sel  = 0; wr_data = None
        clr_en  = False; clr_sel = 0

        cp_s_reg = cp_s
        if cp_s_reg == "CP_IDLE":
            cp_br = cp_bc = cp_pt = 0; cp_buf = 0
            acc_sel = 0; save_buf_sel = 0; save_blk_r = 0; save_blk_c = 0
            done = False
            if pp_rdy[0]:
                cp_s = "CP_LATCH"

        elif cp_s_reg == "CP_LATCH":
            bc_cons_nxt = True; bc_cs = cp_buf
            cp_last = (cp_pt == k_tiles - 1)
            lb = cp_buf
            sa_ta  = pp_ta[lb].copy(); sa_tb  = pp_tb[lb].copy()
            sa_bva = pp_bva[lb][:];   sa_bvb = pp_bvb[lb][:]
            cp_s = "CP_FIRE"

        elif cp_s_reg == "CP_FIRE":
            any_a = any(v != 0 for v in sa_bva)
            any_b = any(v != 0 for v in sa_bvb)
            if dense_mode:
                any_a = any_b = True   # disable whole-tile BV zero-skip
            if not any_a or not any_b:
                sa_res = np.zeros((sa_size, sa_size), np.int32)
                tile_macs = 0
            else:
                sa_res, sa_cyc, tile_macs = sa_compute(
                    sa_ta, sa_tb, sa_bva, sa_bvb, sa_size, dense_mode)
                sa_pend = True; sa_cl = sa_cyc
            total_effective_macs += tile_macs
            cp_s = "CP_WAIT_SA" if (any_a and any_b) else "CP_ACCUMULATE"

        elif cp_s_reg == "CP_WAIT_SA":
            if not sa_pend:
                cp_s = "CP_ACCUMULATE"

        elif cp_s_reg == "CP_ACCUMULATE":
            wr_en = True; wr_sel = acc_sel
            wr_data = sa_res.astype(np.int64)
            if cp_last:
                av_pulse_nxt = True
                save_buf_sel = acc_sel
                save_blk_r   = cp_br
                save_blk_c   = cp_bc
                acc_sel ^= 1
            cp_s = "CP_NEXT"

        elif cp_s_reg == "CP_NEXT":
            if cp_last:
                clr_en = True; clr_sel = save_buf_sel

            next_buf = cp_buf ^ 1
            # All output tiles exhausted → CP_DONE
            if cp_last and cp_br >= m_tiles - 1 and cp_bc >= n_tiles - 1:
                cp_s = "CP_DONE"
            elif pp_rdy[next_buf]:
                if cp_last:
                    cp_pt = 0
                    if cp_bc >= n_tiles - 1:
                        cp_bc = 0
                        cp_br += 1
                        cp_buf = next_buf; cp_s = "CP_LATCH"
                    else:
                        cp_bc += 1
                        cp_buf = next_buf; cp_s = "CP_LATCH"
                else:
                    cp_pt += 1
                    cp_buf = next_buf; cp_s = "CP_LATCH"

        elif cp_s_reg == "CP_DONE":
            if sv_s_reg == "S_IDLE":
                done = True

        # ── Save FSM ──────────────────────────────────────────
        # norm_pool 1-cycle pipeline
        if np_pend:
            sv_s   = "S_SAVE_TILE"
            sv_row = 0
            np_pend = False

        if sv_s_reg == "S_IDLE":
            if av_pulse:
                sv_br  = save_blk_r; sv_bc_s = save_blk_c
                raw    = acc_buf[save_buf_sel].astype(np.int32) & DMAX
                sv_norm = norm_pool(raw, pool_type, sa_size)
                np_pend_nxt = True
                sv_s = "S_WAIT_NORM"

        elif sv_s_reg == "S_WAIT_NORM":
            pass   # resolved by np_pend above

        elif sv_s_reg == "S_SAVE_TILE":
            # BRAM_C address: (sv_br * SA_SIZE + sv_row) * N_TILES + sv_bc_s
            addr = (sv_br * sa_size + sv_row) * n_tiles + sv_bc_s
            bram_c[addr] = sv_norm[sv_row].copy()
            bram_c_row_writes += 1
            if sv_row >= sa_size - 1:
                sv_s = "S_IDLE"
            else:
                sv_row += 1

        # ── Apply accumulator write ────────────────────────────
        if wr_en and wr_data is not None:
            acc_buf[wr_sel] = (acc_buf[wr_sel] + wr_data) & AMAX
        if clr_en:
            acc_buf[clr_sel][:] = 0

    cycle -= 1  # RTL t_start is recorded 1 cycle after Python start=True

    # ── Collect result ────────────────────────────────────────
    result = read_bram_c(bram_c, m_size, n_size, sa_size)
    golden = (mat_a.astype(np.int64) @ mat_b.astype(np.int64)) & DMAX

    if verbose:
        print(f"\n  Simulation : {'DONE' if done else 'TIMEOUT'}")
        print(f"  Total cycles     : {cycle:,}")
        if pool_type == 0:
            ok = np.array_equal(result, golden)
            print(f"  Calc. Correct?   : {'PASS' if ok else 'FAIL'}")
            if not ok:
                diff = np.abs(result.astype(np.int64) - golden)
                print(f"  Max diff={diff.max()},  Mismatches={np.sum(diff > 0)}")
        else:
            print(f"  (Pool type {pool_type}: direct equality check skipped)")

    total_ops  = 2 * m_size * k_size * n_size
    skip_ratio = (1.0 - total_effective_macs / (total_ops / 2)
                  ) if total_ops > 0 else 0.0

    # ── BRAM bandwidth (words/cycle) ──────────────────────────
    # Each row access transfers sa_size words (DATA_WIDTH-bit elements)
    cyc = cycle if cycle > 0 else 1
    avg_bram_a_bw = bram_a_row_reads  * sa_size / cyc
    avg_bram_b_bw = bram_b_row_reads  * sa_size / cyc
    avg_bram_c_bw = bram_c_row_writes * sa_size / cyc

    # ── DRAM stall model (Method 1) ───────────────────────────
    # Total data that must cross the off-chip DRAM interface:
    #   Load : matrix A (m×k) + matrix B (k×n)
    #   Store: matrix C (m×n)
    dram_total_words   = m_size * k_size + k_size * n_size + m_size * n_size
    min_dram_bw_needed = dram_total_words / cyc   # words/cycle for zero stall

    if dram_bw is not None and dram_bw > 0:
        dram_required_cycles = math.ceil(dram_total_words / dram_bw)
        dram_stall_cycles    = max(0, dram_required_cycles - cycle)
        total_cycles_w_dram  = cycle + dram_stall_cycles
    else:
        dram_stall_cycles   = 0
        total_cycles_w_dram = cycle

    return dict(total_cycles=cycle, result=result, golden=golden, done=done,
                effective_macs=total_effective_macs,
                total_ops=total_ops,
                skip_ratio=skip_ratio,
                avg_bram_a_bw=avg_bram_a_bw,
                avg_bram_b_bw=avg_bram_b_bw,
                avg_bram_c_bw=avg_bram_c_bw,
                bram_a_row_reads=bram_a_row_reads,
                bram_b_row_reads=bram_b_row_reads,
                bram_c_row_writes=bram_c_row_writes,
                dram_stall_cycles=dram_stall_cycles,
                total_cycles_w_dram=total_cycles_w_dram,
                min_dram_bw_needed=min_dram_bw_needed,
                dram_total_words=dram_total_words)

# End of simulator logic.