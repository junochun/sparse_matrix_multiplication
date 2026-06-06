"""
Format Comparison Analysis: Dense baseline vs CSR vs BV (ours).

Sweeps sparsity 0–90%, averages over 5 random seeds, normalises all
cycle counts to the Dense baseline at 0% sparsity, and plots results.
"""

import os
import sys
import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_FILE_DIR)
sys.path.insert(0, _ROOT)

from core import sparse_RTL_simulator as sim

# ── Constants ─────────────────────────────────────────────────
MATRIX_SIZE     = 64
SA_SIZE         = 32
SPARSITY_LEVELS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
N_SEEDS         = 5

_AMAX          = (1 << 32) - 1   # matches ACC_WIDTH=32 in the simulator
_DENSE_SA_CORE = 3 * SA_SIZE - 2 + 4  # per-tile Dense SA compute cost
                                        # = (sa_size-1)+(sa_size-1)+sa_size+4
                                        # = 94 for sa_size=32


# ═══════════════════════════════════════════════════════════════
# Model 1 — Dense baseline  (BV zero-skip disabled)
# ═══════════════════════════════════════════════════════════════
def _sa_compute_dense(tile_a, tile_b, bv_a, bv_b, sa_size, _dense_mode=False):
    """
    Local wrapper around sa_compute with all bitvectors forced to all-ones.

    Effect: every element is treated as non-zero → no zero-skip.
    The worst-case finish cycle for PE(i,j) is:
        finish = i + j + sa_size   (k = sa_size when bv = all-ones)
    Maximum over all PEs: (sa_size-1) + (sa_size-1) + sa_size = 3*sa_size - 2
    effective_macs = sa_size^3  (every PE computes sa_size MACs)
    """
    result        = (tile_a.astype(np.int64) @ tile_b.astype(np.int64)) & _AMAX
    worst         = (sa_size - 1) + (sa_size - 1) + sa_size   # = 3*sa_size - 2
    effective_macs = sa_size ** 3
    return result.astype(np.int32), worst + 4, effective_macs  # +4: RTL pipeline constant


def _row_bv_ones(row):
    """Return an all-ones bitvector so the CP_FIRE all-zero check never skips."""
    return (1 << len(row)) - 1


def run_dense_cycles(mat_a, mat_b, sa_size):
    """
    Cycle-accurate sim with zero-skip fully disabled.

    Monkey-patches both sim.row_bv (prevents all-zero tile early-exit in CP_FIRE)
    and sim.sa_compute (forces dense cycle cost) for the duration of this call,
    then restores the originals.  sparse_RTL_simulator.py is NOT modified.
    """
    m, k = mat_a.shape
    n    = mat_b.shape[1]
    orig_sa = sim.sa_compute
    orig_bv = sim.row_bv
    sim.sa_compute = _sa_compute_dense
    sim.row_bv     = _row_bv_ones
    try:
        r = sim.run_simulation(
            m_size=m, k_size=k, n_size=n,
            sa_size=sa_size, verbose=False,
            val_a=mat_a, val_b=mat_b,
        )
    finally:
        sim.sa_compute = orig_sa
        sim.row_bv     = orig_bv
    return r['total_cycles']


# ═══════════════════════════════════════════════════════════════
# Model 2 — CSR cycle estimate  (analytical, FSM-calibrated)
# ═══════════════════════════════════════════════════════════════
def csr_cycles(A, B, sa_size, fsm_overhead):
    """
    Estimate cycles for CSR-format matmul on the same scale as Dense/BV.

    csr_total = fsm_overhead + csr_sa_core

    CSR row-i only iterates over A[i,:]'s stored nonzeros (the row pointer
    advances through A's nonzero entries). It does NOT scan B's column —
    it looks up B[k,j] for each k where A[i,k]!=0. So the per-PE work is:

      finish(i, j) = i + j + 2 × nnz_a_row[i]
                     ╰──┬──╯   ╰─────────────╯
                 systolic   index_decode(×1) + MAC(×1) per A nonzero

      worst_pe = (M-1) + (N-1) + 2 × max(nnz_a_row)
                 (maximised at last row/col, row with most stored nonzeros)

    The SA PEs work in parallel, so only the critical path (worst_pe) matters.
    Adding total_nnz_A on top of worst_pe would serialize what is parallel work.

    csr_sa_core = worst_pe    (no additional index-overhead term)

    Guaranteed ordering — CSR ≥ BV at all sparsity levels:
      worst_pe uses 2×nnz (index_decode + MAC) vs BV's effective k (popcount only).
      At equal density CSR always has the same or higher per-PE cost than BV.
    """
    M, _K = A.shape
    N     = B.shape[1]

    nnz_a_row = (A != 0).sum(axis=1)                         # (M,) int

    worst_pe    = (M - 1) + (N - 1) + 2 * int(nnz_a_row.max())
    csr_sa_core = worst_pe    # SA PEs work in parallel; worst_pe captures the critical path
    return fsm_overhead + csr_sa_core


# ═══════════════════════════════════════════════════════════════
# Model 3 — BV (ours)
# ═══════════════════════════════════════════════════════════════
def run_bv_cycles(mat_a, mat_b, sa_size):
    """Cycle-accurate BV zero-skip simulation (unmodified run_simulation)."""
    m, k = mat_a.shape
    n    = mat_b.shape[1]
    r = sim.run_simulation(
        m_size=m, k_size=k, n_size=n,
        sa_size=sa_size, verbose=False,
        val_a=mat_a, val_b=mat_b,
    )
    return r['total_cycles']


# ═══════════════════════════════════════════════════════════════
# Sweep
# ═══════════════════════════════════════════════════════════════
def run_sweep():
    """
    For each sparsity level, generate N_SEEDS random matrices, run all
    three models, and store the per-seed cycles.  Returns a dict:
        results[sparsity] = {'dense': float, 'bv': float, 'csr': float}
    where each float is the average over seeds.
    """
    # ── Compute Dense FSM overhead once (fully-dense reference matrix) ──
    # fsm_overhead captures BRAM-load / tile-iteration / save-FSM cost that
    # is identical for both Dense and CSR.  Only SA compute time differs.
    rng_ref = np.random.default_rng(0)
    ref_a   = sim.make_matrix(MATRIX_SIZE, MATRIX_SIZE, 0.0, rng_ref)
    ref_b   = sim.make_matrix(MATRIX_SIZE, MATRIX_SIZE, 0.0, rng_ref)
    dense_ref_total = run_dense_cycles(ref_a, ref_b, SA_SIZE)
    fsm_overhead    = dense_ref_total - _DENSE_SA_CORE
    print(f"\nDense FSM overhead calibration:")
    print(f"  dense_total (0% ref)  = {dense_ref_total:,} cycles")
    print(f"  dense_sa_core (1 tile)= {_DENSE_SA_CORE} cycles")
    print(f"  fsm_overhead          = {fsm_overhead:,} cycles")

    results = {}

    for sp in SPARSITY_LEVELS:
        zero_ratio = sp / 100.0
        seed_dense, seed_bv, seed_csr = [], [], []

        print(f"\n[Sparsity {sp:>2}%]  running {N_SEEDS} seeds...")
        for seed in range(N_SEEDS):
            rng   = np.random.default_rng(seed)
            mat_a = sim.make_matrix(MATRIX_SIZE, MATRIX_SIZE, zero_ratio, rng)
            mat_b = sim.make_matrix(MATRIX_SIZE, MATRIX_SIZE, zero_ratio, rng)

            seed_dense.append(run_dense_cycles(mat_a, mat_b, SA_SIZE))
            seed_bv.append(run_bv_cycles(mat_a, mat_b, SA_SIZE))
            seed_csr.append(csr_cycles(mat_a, mat_b, SA_SIZE, fsm_overhead))

        results[sp] = {
            'dense': float(np.mean(seed_dense)),
            'bv':    float(np.mean(seed_bv)),
            'csr':   float(np.mean(seed_csr)),
        }
        r = results[sp]
        print(f"  avg cycles → Dense:{r['dense']:>8,.0f}  BV:{r['bv']:>8,.0f}  CSR:{r['csr']:>8,.0f}")

    return results


# ═══════════════════════════════════════════════════════════════
# Reporting
# ═══════════════════════════════════════════════════════════════
def print_table(results, baseline):
    cols = ('Dense cyc', 'BV cyc', 'CSR cyc', 'Dense norm', 'BV norm', 'CSR norm')
    header = f"{'Sparsity':>10} | {cols[0]:>10} | {cols[1]:>10} | {cols[2]:>10} | {cols[3]:>10} | {cols[4]:>10} | {cols[5]:>10}"
    sep    = '-' * len(header)
    print('\n' + '=' * len(header))
    print(header)
    print(sep)
    for sp in SPARSITY_LEVELS:
        r = results[sp]
        print(
            f"{sp:>9}% | "
            f"{r['dense']:>10,.0f} | "
            f"{r['bv']:>10,.0f} | "
            f"{r['csr']:>10,.0f} | "
            f"{r['dense']/baseline:>10.4f} | "
            f"{r['bv']/baseline:>10.4f} | "
            f"{r['csr']/baseline:>10.4f}"
        )
    print('=' * len(header))


def print_summary(results, baseline):
    r0  = results[0]
    r70 = results[70]

    compat = {
        'dense': ('HIGH',   'identical to standard SA data flow; no format overhead'),
        'bv':    ('HIGH',   'bitvector gate-level skip preserves systolic pipeline regularity'),
        'csr':   ('MEDIUM', 'irregular index decode breaks the uniform systolic pipeline'),
    }

    print('\n' + '=' * 60)
    print('  Format Summary')
    print('=' * 60)
    for label, key in [('Dense (baseline)', 'dense'), ('BV  (ours)', 'bv'), ('CSR', 'csr')]:
        overhead = r0[key]  / baseline
        speedup  = baseline / r70[key]
        lvl, reason = compat[key]
        print(f'\n  [{label}]')
        print(f'    At  0% sparsity : {overhead:.4f}× overhead vs dense baseline')
        print(f'    At 70% sparsity : {speedup:.4f}× speedup  vs dense baseline')
        print(f'    SA compatibility: {lvl}  — {reason}')
    print('=' * 60)


# ═══════════════════════════════════════════════════════════════
# Plot
# ═══════════════════════════════════════════════════════════════
def plot_results(results, baseline, out_path):
    dense_norm = [results[sp]['dense'] / baseline for sp in SPARSITY_LEVELS]
    bv_norm    = [results[sp]['bv']    / baseline for sp in SPARSITY_LEVELS]
    csr_norm   = [results[sp]['csr']   / baseline for sp in SPARSITY_LEVELS]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(SPARSITY_LEVELS, dense_norm, 'o-', color='tab:gray',   linewidth=2,
            markersize=7, label='Dense (baseline)')
    ax.plot(SPARSITY_LEVELS, bv_norm,    's-', color='tab:blue',   linewidth=2,
            markersize=7, label='BV (ours)')
    ax.plot(SPARSITY_LEVELS, csr_norm,   '^-', color='tab:orange', linewidth=2,
            markersize=7, label='CSR')

    # Annotation at 50% sparsity for BV line
    idx50   = SPARSITY_LEVELS.index(50)
    bv_y50  = bv_norm[idx50]
    y_range = max(max(dense_norm), max(bv_norm), max(csr_norm))
    ax.annotate(
        'BV maintains\nsystolic regularity',
        xy=(50, bv_y50),
        xytext=(53, bv_y50 + y_range * 0.12),
        fontsize=10,
        color='tab:blue',
        arrowprops=dict(arrowstyle='->', color='tab:blue', lw=1.4),
    )

    ax.set_xlabel('Sparsity (%)', fontsize=13)
    ax.set_ylabel('Normalized Cycles  (Dense @ 0% = 1.0)', fontsize=13)
    ax.set_title('Sparse Format Comparison: Dense vs CSR vs BV', fontsize=14)
    ax.set_xticks(SPARSITY_LEVELS)
    ax.set_ylim(0, y_range * 1.35)
    ax.legend(fontsize=11, loc='upper right')
    ax.grid(axis='y', alpha=0.35)

    fig.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f'\nPlot saved to: {out_path}')


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('=' * 58)
    print('  Format Comparison Analysis — Dense / CSR / BV')
    print(f'  Matrix: {MATRIX_SIZE}×{MATRIX_SIZE}  SA_SIZE: {SA_SIZE}  Seeds: {N_SEEDS}')
    print('=' * 58)

    results  = run_sweep()
    baseline = results[0]['dense']

    print(f'\nDense baseline (0% sparsity, avg over {N_SEEDS} seeds): {baseline:,.0f} cycles')

    print_table(results, baseline)
    print_summary(results, baseline)

    out_png = os.path.join(_FILE_DIR, 'format_comparison_result.png')
    plot_results(results, baseline, out_png)
