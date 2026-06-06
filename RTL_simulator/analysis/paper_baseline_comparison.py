"""
Paper Baseline Comparison — Per-Paper SA Core Latency
======================================================
Three independent experiments, each using the SA size of the reference paper.
Our design is parametric and runs at any SA size.

  Exp 1: vs TPU v1 Dense       (ISCA 2017) — SA 256×256, Mat 512×512
  Exp 2: vs Eyeriss Act-Gating (ISCA 2016) — SA 14×14,  Mat 56×56
  Exp 3: BV vs Structured Block Skip — Sensitivity Analysis
         SA 128×128, Mat 256×256, block_size ∈ [1,2,4,8,16,32]

SCOPE: SA compute cycles only. FSM/BRAM overhead identical across baselines.
Full-chip memory hierarchy, DRAM, and control overhead are NOT modelled.

Eyeriss note: Original PE array is 14×12 (non-square). Modelled as 14×14
(conservative — slightly disadvantages our design, making the speedup claim stronger).

Exp 3 note: BV AND is fine-grained (bit-level) skip; structured block skip rounds
k up to the nearest block_size multiple. block_size=1 is equivalent to BV (validation).
block_size sweep shows increasing overhead as granularity coarsens.

Usage:
    python analysis/paper_baseline_comparison.py
"""

import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.patches import Patch

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_FILE_DIR)
sys.path.insert(0, _ROOT)

from core import sparse_RTL_simulator as sim

_AMAX      = (1 << 32) - 1  # matches ACC_WIDTH=32 in the simulator
BLOCK_SIZES = [1, 2, 4, 8, 16, 32]

# VerSA reference constants (Electronics 2024)
VERSA_SPARSITY  = 75
VERSA_NORM_LOW  = 1.0 / 1.60   # ≈ 0.625  (best-case, highest speedup)
VERSA_NORM_HIGH = 1.0 / 1.21   # ≈ 0.826  (worst-case, lowest speedup)


# ═══════════════════════════════════════════════════════════════
# Baseline SA compute functions  (used for monkey-patching)
# ═══════════════════════════════════════════════════════════════

def _sa_compute_eyeriss(tile_a, tile_b, bv_a, bv_b, sa_size, dense_mode=False):
    """
    Eyeriss row-stationary dataflow: activation (A) sparsity only.
    k = popcount(bv_a[i]) for every column j — bv_b is ignored.
    Weight (B) is treated as always non-zero (pre-loaded, no column gating).
    Guaranteed: eyeriss_cycles >= our_bv_cycles, since popcount(bv_a[i])
    >= popcount(bv_a[i] & bv_b_col[j]) for any j.
    """
    result = (tile_a.astype(np.int64) @ tile_b.astype(np.int64)) & _AMAX
    worst = 0
    effective_macs = 0
    for i in range(sa_size):
        k = bin(bv_a[i]).count("1")
        for j in range(sa_size):
            effective_macs += k
            finish = i + j + k
            if finish > worst:
                worst = finish
    return result.astype(np.int32), worst + 4, effective_macs


def _make_sa_compute_sparse_tpu(block_size):
    """Return a Sparse-TPU sa_compute closure for the given block_size."""
    def _fn(tile_a, tile_b, bv_a, bv_b, sa_size, dense_mode=False):
        """
        Structured block skip: k = ceil(popcount(AND) / block_size) * block_size.
        Minimum k = block_size (always execute at least one block).
        Guaranteed: sparse_tpu_cycles >= our_bv_cycles since block rounding
        never reduces k below the raw popcount.
        """
        result = (tile_a.astype(np.int64) @ tile_b.astype(np.int64)) & _AMAX
        bv_b_col = [0] * sa_size
        for r in range(sa_size):
            for c in range(sa_size):
                if bv_b[r] & (1 << c):
                    bv_b_col[c] |= (1 << r)
        worst = 0
        effective_macs = 0
        for i in range(sa_size):
            for j in range(sa_size):
                k_raw = bin(bv_a[i] & bv_b_col[j]).count("1")
                if k_raw == 0:
                    k = 0  # both vectors have no common non-zeros → skip
                else:
                    k = math.ceil(k_raw / block_size) * block_size
                effective_macs += k
                finish = i + j + k
                if finish > worst:
                    worst = finish
        return result.astype(np.int32), worst + 4, effective_macs
    return _fn


# ═══════════════════════════════════════════════════════════════
# Per-seed cycle runners  (monkey-patch with guaranteed restore)
# ═══════════════════════════════════════════════════════════════

def _run_tpu_v1(mat_a, mat_b, sa_size):
    """TPU v1 Dense: dense_mode=True disables all BV zero-skip."""
    m, k = mat_a.shape
    n = mat_b.shape[1]
    r = sim.run_simulation(
        m_size=m, k_size=k, n_size=n, sa_size=sa_size,
        dense_mode=True, verbose=False, val_a=mat_a, val_b=mat_b,
    )
    return r['total_cycles']


def _run_eyeriss(mat_a, mat_b, sa_size):
    """Eyeriss: patch sa_compute for activation-only gating."""
    m, k = mat_a.shape
    n = mat_b.shape[1]
    orig_sa = sim.sa_compute
    sim.sa_compute = _sa_compute_eyeriss
    try:
        r = sim.run_simulation(
            m_size=m, k_size=k, n_size=n, sa_size=sa_size,
            verbose=False, val_a=mat_a, val_b=mat_b,
        )
    finally:
        sim.sa_compute = orig_sa
    return r['total_cycles']


def _run_sparse_tpu(mat_a, mat_b, sa_size, sa_compute_fn):
    """Sparse-TPU: patch sa_compute for block-rounded skip."""
    m, k = mat_a.shape
    n = mat_b.shape[1]
    orig_sa = sim.sa_compute
    sim.sa_compute = sa_compute_fn
    try:
        r = sim.run_simulation(
            m_size=m, k_size=k, n_size=n, sa_size=sa_size,
            verbose=False, val_a=mat_a, val_b=mat_b,
        )
    finally:
        sim.sa_compute = orig_sa
    return r['total_cycles']


def _run_our_bv(mat_a, mat_b, sa_size):
    """Our BV zero-skip: unmodified run_simulation with dense_mode=False."""
    m, k = mat_a.shape
    n = mat_b.shape[1]
    r = sim.run_simulation(
        m_size=m, k_size=k, n_size=n, sa_size=sa_size,
        dense_mode=False, verbose=False, val_a=mat_a, val_b=mat_b,
    )
    return r['total_cycles']


# ═══════════════════════════════════════════════════════════════
# Experiment 1: vs TPU v1 Dense  (SA 256×256, Mat 512×512)
# ═══════════════════════════════════════════════════════════════

def sweep_vs_tpu_v1(sparsity_list, n_seeds):
    """
    SA_SIZE=256, MAT=512×512.
    Baseline: dense_mode=True (k=sa_size always, no zero-skip).
    Ours    : BV AND zero-skip (dense_mode=False).

    Returns dict[sparsity] = {'tpu_v1': float, 'our_bv': float}
    """
    SA_SIZE  = 256
    MAT_SIZE = 512
    results  = {}

    print(f"\nExperiment 1: vs TPU v1 Dense — SA {SA_SIZE}×{SA_SIZE}, Mat {MAT_SIZE}×{MAT_SIZE}")
    for sp in sparsity_list:
        zero_ratio = sp / 100.0
        tpu_cyc, bv_cyc = [], []
        print(f"  Sparsity {sp:>2}%  ({n_seeds} seeds)...", flush=True)
        for seed in range(n_seeds):
            rng   = np.random.default_rng(seed)
            mat_a = sim.make_matrix(MAT_SIZE, MAT_SIZE, zero_ratio, rng)
            mat_b = sim.make_matrix(MAT_SIZE, MAT_SIZE, zero_ratio, rng)
            tpu_cyc.append(_run_tpu_v1(mat_a, mat_b, SA_SIZE))
            bv_cyc.append(_run_our_bv(mat_a, mat_b, SA_SIZE))

        results[sp] = {
            'tpu_v1': float(np.mean(tpu_cyc)),
            'our_bv': float(np.mean(bv_cyc)),
        }
        r = results[sp]
        if r['tpu_v1'] < r['our_bv'] - 0.5:
            print(f"  [WARN] ordering violation at {sp}%: our_bv ({r['our_bv']:.0f}) > tpu_v1 ({r['tpu_v1']:.0f})")

    return results


# ═══════════════════════════════════════════════════════════════
# Experiment 2: vs Eyeriss Act-Gating  (SA 14×14, Mat 56×56)
# ═══════════════════════════════════════════════════════════════

def sweep_vs_eyeriss(sparsity_list, n_seeds):
    """
    SA_SIZE=14, MAT=56×56.
    Baseline: Eyeriss activation-only gating (bv_a used, bv_b ignored).
    Ours    : BV AND zero-skip.

    Ordering guarantee: eyeriss_cycles >= our_bv_cycles always holds
    since popcount(bv_a) >= popcount(bv_a & bv_b_col) for any column.

    Returns dict[sparsity] = {'eyeriss': float, 'our_bv': float}
    """
    SA_SIZE  = 14
    MAT_SIZE = 56
    results  = {}

    print(f"\nExperiment 2: vs Eyeriss Act-Gating — SA {SA_SIZE}×{SA_SIZE}, Mat {MAT_SIZE}×{MAT_SIZE}")
    for sp in sparsity_list:
        zero_ratio = sp / 100.0
        eye_cyc, bv_cyc = [], []
        print(f"  Sparsity {sp:>2}%  ({n_seeds} seeds)...", flush=True)
        for seed in range(n_seeds):
            rng   = np.random.default_rng(seed)
            mat_a = sim.make_matrix(MAT_SIZE, MAT_SIZE, zero_ratio, rng)
            mat_b = sim.make_matrix(MAT_SIZE, MAT_SIZE, zero_ratio, rng)
            eye_cyc.append(_run_eyeriss(mat_a, mat_b, SA_SIZE))
            bv_cyc.append(_run_our_bv(mat_a, mat_b, SA_SIZE))

        results[sp] = {
            'eyeriss': float(np.mean(eye_cyc)),
            'our_bv':  float(np.mean(bv_cyc)),
        }
        r = results[sp]
        if r['eyeriss'] < r['our_bv'] - 0.5:
            print(f"  [WARN] ordering violation at {sp}%: our_bv ({r['our_bv']:.0f}) > eyeriss ({r['eyeriss']:.0f})")

    return results


# ═══════════════════════════════════════════════════════════════
# Experiment 3: BV vs Structured Block Skip — Sensitivity
#               (SA 128×128, Mat 256×256)
# ═══════════════════════════════════════════════════════════════

def sweep_block_sensitivity(sparsity_list, n_seeds,
                             block_sizes=None, sa_size=128, mat_size=256):
    """
    BV vs Structured Block Skip — Sensitivity Analysis.
    SA_SIZE=128, MAT=256×256.

    For each (sparsity, block_size) pair, measures structured block skip cycles.
    BV cycles measured once per sparsity (block_size-independent baseline).

    block_size=1 → ceil(k/1)*1 = k → identical to BV (validation: should match).
    block_size>1 → rounding overhead increases with block_size.

    Returns dict[sparsity] = {
        'our_bv':    float,
        'block_{b}': float  for b in block_sizes
    }
    """
    if block_sizes is None:
        block_sizes = BLOCK_SIZES

    results = {}

    print(f"\nExperiment 3: BV vs Block Skip Sensitivity — SA {sa_size}×{sa_size}, Mat {mat_size}×{mat_size}")
    print(f"  Block sizes: {block_sizes}")

    # Pre-build sa_compute closures once per block_size
    sa_fns = {b: _make_sa_compute_sparse_tpu(b) for b in block_sizes}

    for sp in sparsity_list:
        zero_ratio = sp / 100.0
        print(f"  Sparsity {sp:>2}%  ({n_seeds} seeds)...", flush=True)

        bv_list    = []
        block_lists = {b: [] for b in block_sizes}

        for seed in range(n_seeds):
            rng   = np.random.default_rng(seed)
            mat_a = sim.make_matrix(mat_size, mat_size, zero_ratio, rng)
            mat_b = sim.make_matrix(mat_size, mat_size, zero_ratio, rng)

            bv_list.append(_run_our_bv(mat_a, mat_b, sa_size))
            for b in block_sizes:
                block_lists[b].append(_run_sparse_tpu(mat_a, mat_b, sa_size, sa_fns[b]))

        row = {'our_bv': float(np.mean(bv_list))}
        for b in block_sizes:
            row[f'block_{b}'] = float(np.mean(block_lists[b]))
        results[sp] = row

        # Validate: block_size=1 must match BV (±1 cycle)
        if 1 in block_sizes and abs(results[sp]['block_1'] - results[sp]['our_bv']) > 1.0:
            print(f"  [WARN] block_1 ({results[sp]['block_1']:.0f}) != our_bv "
                  f"({results[sp]['our_bv']:.0f}) at {sp}% — check implementation")
        # Ordering: all block_X >= our_bv
        for b in block_sizes:
            if results[sp][f'block_{b}'] < results[sp]['our_bv'] - 0.5:
                print(f"  [WARN] block_{b} ({results[sp][f'block_{b}']:.0f}) < "
                      f"our_bv ({results[sp]['our_bv']:.0f}) at {sp}%")

    return results


# ═══════════════════════════════════════════════════════════════
# Table printers
# ═══════════════════════════════════════════════════════════════

def print_table_tpu_v1(results, sparsity_list, n_seeds=3):
    sep = "---------+--------------+---------+---------------------"
    print()
    print("=" * 57)
    print("  Experiment 1: vs TPU v1 Dense (ISCA 2017)")
    print(f"  SA size: 256×256 | Matrix: 512×512 | Seeds: {n_seeds}")
    print("  Baseline: Dense MAC (no zero-skip)")
    print("=" * 57)
    print(f"{'Sparsity':>8} | {'TPU v1 Dense':>12} | {'Our BV':>7} | {'Speedup (Ours/Dense)':>20}")
    print(sep)

    speedups = {}
    for sp in sparsity_list:
        r  = results[sp]
        su = r['tpu_v1'] / r['our_bv'] if r['our_bv'] > 0 else 1.0
        speedups[sp] = su
        print(f"{sp:>7}% | {round(r['tpu_v1']):>12,} | {round(r['our_bv']):>7,} | {su:>20.2f}x")

    print(sep)
    pk = max(speedups, key=speedups.get)
    print(f"  Peak speedup: {speedups[pk]:.2f}x @ {pk}% sparsity")
    print()


def print_table_eyeriss(results, sparsity_list, n_seeds=5):
    sep = "---------+-------------+---------+---------"
    print()
    print("=" * 57)
    print("  Experiment 2: vs Eyeriss Act-Gating (ISCA 2016)")
    print(f"  SA size: 14×14 | Matrix: 56×56 | Seeds: {n_seeds}")
    print("  Note: Eyeriss uses 14×12 PE array; modelled as 14×14 (conservative)")
    print("  Baseline: Activation-only gating (A sparse, B treated as dense)")
    print("=" * 57)
    print(f"{'Sparsity':>8} | {'Eyeriss':>11} | {'Our BV':>7} | {'Speedup':>7}")
    print(sep)

    speedups = {}
    for sp in sparsity_list:
        r  = results[sp]
        su = r['eyeriss'] / r['our_bv'] if r['our_bv'] > 0 else 1.0
        speedups[sp] = su
        print(f"{sp:>7}% | {round(r['eyeriss']):>11,} | {round(r['our_bv']):>7,} | {su:>7.2f}x")

    print(sep)
    pk = max(speedups, key=speedups.get)
    print(f"  Peak speedup: {speedups[pk]:.2f}x @ {pk}% sparsity")
    if VERSA_SPARSITY in results:
        su75 = results[VERSA_SPARSITY]['eyeriss'] / results[VERSA_SPARSITY]['our_bv']
        print(f"  Our BV at {VERSA_SPARSITY}%: {su75:.2f}x  (VerSA reported: 1.21x–1.60x)")
    print()


def print_table_block_sensitivity(results, sparsity_list,
                                   block_sizes=None, n_seeds=3):
    """
    Print block sensitivity table.
    Rows: sparsity levels. Columns: BV | block_1 | block_2 | ...
    Values: normalized cycles (BV @ 0% = 1.0).
    Overhead summary at peak sparsity shows how much slower each block_size is vs BV.
    """
    if block_sizes is None:
        block_sizes = BLOCK_SIZES

    col_w = 9
    header_parts  = [f"{'Sparsity':>8}"]
    header_parts += [f"{'Our BV':>{col_w}}"]
    for b in block_sizes:
        header_parts += [f"{'blk='+str(b):>{col_w}}"]
    header = " | ".join(header_parts)
    sep    = "-" * len(header)

    print()
    print("=" * len(header))
    print("  Experiment 3: BV vs Structured Block Skip — Sensitivity")
    print(f"  SA size: 128×128 | Matrix: 256×256 | Seeds: {n_seeds}")
    print(f"  Block sizes: {block_sizes}")
    print("  Values: normalized cycles (BV @ 0% = 1.0)")
    print("  Overhead = block_X_cycles / BV_cycles  (>1.0 means block skip is slower)")
    print("=" * len(header))
    print(header)
    print(sep)

    baseline_0 = results[sparsity_list[0]]['our_bv']

    for sp in sparsity_list:
        r      = results[sp]
        bv_n   = r['our_bv'] / baseline_0
        parts  = [f"{sp:>7}%"]
        parts += [f"{bv_n:>{col_w}.4f}"]
        for b in block_sizes:
            parts += [f"{r[f'block_{b}'] / baseline_0:>{col_w}.4f}"]
        print(" | ".join(parts))

    print(sep)

    sp_peak = sparsity_list[-1]
    r_peak  = results[sp_peak]
    print(f"\n  Overhead vs BV at {sp_peak}% sparsity:")
    for b in block_sizes:
        overhead = r_peak[f'block_{b}'] / r_peak['our_bv']
        label    = "(= BV)" if b == 1 else f"{overhead:.3f}x slower"
        print(f"    block_size={b:>2}: {label}")
    print()


# ═══════════════════════════════════════════════════════════════
# Unified 3-subplot publication figure
# ═══════════════════════════════════════════════════════════════

def plot_all(results_tpu, results_eyeriss, results_block,
             sparsity_tpu, sparsity_eyeriss, sparsity_block,
             save_path, block_sizes=None):
    """
    3-subplot (1×3) figure.
    Subplot 1: BV vs TPU v1 Dense   — normalized cycles
    Subplot 2: BV vs Eyeriss        — normalized cycles + VerSA band
    Subplot 3: BV vs Block Sizes    — sensitivity curves (Reds colormap)
    """
    if block_sizes is None:
        block_sizes = BLOCK_SIZES

    def _normalize(results, sparsity_list, baseline_key):
        b0        = results[sparsity_list[0]][baseline_key]
        base_norm = [results[s][baseline_key] / b0 for s in sparsity_list]
        bv_norm   = [results[s]['our_bv']      / b0 for s in sparsity_list]
        return base_norm, bv_norm

    def _annotate_peak(ax, sparsity_list, bv_norm, results, baseline_key):
        peak_idx  = int(np.argmin(bv_norm))
        peak_x    = sparsity_list[peak_idx]
        peak_y    = bv_norm[peak_idx]
        peak_spup = results[peak_x][baseline_key] / results[peak_x]['our_bv']
        ax.text(peak_x, peak_y + 0.025,
                f"Peak: {peak_spup:.2f}x @ {peak_x}%",
                ha='center', va='bottom', fontsize=8.5,
                color='tab:blue', fontweight='semibold')

    def _style_ax(ax, sparsity_list, all_norms, title, y_hi=1.05):
        ax.set_xlabel('Sparsity (%)', fontsize=11)
        ax.set_ylabel('Normalized Cycles  (Baseline @ 0% = 1.0)', fontsize=10)
        ax.set_title(title, fontsize=11)
        ax.set_xticks(sparsity_list)
        ax.set_xlim(min(sparsity_list) - 2, max(sparsity_list) + 2)
        y_min_data = min(v for norm in all_norms for v in norm)
        y_lo = min(0.5, y_min_data - 0.03)
        ax.set_ylim(y_lo, y_hi)
        ax.legend(loc='upper right', fontsize=9)
        ax.grid(axis='y', alpha=0.3)
        ax.set_axisbelow(True)
        ax.set_facecolor('white')

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor('white')

    # ── Subplot 1: vs TPU v1 ─────────────────────────────────
    ax1 = axes[0]
    base_norm1, bv_norm1 = _normalize(results_tpu, sparsity_tpu, 'tpu_v1')
    ax1.plot(sparsity_tpu, base_norm1, 's--', color='gray', linewidth=1.8, markersize=6,
             label="TPU v1 Dense (ISCA'17)")
    ax1.plot(sparsity_tpu, bv_norm1,   'o-',  color='tab:blue', linewidth=2.5, markersize=7,
             label='Ours (BV Zero-Skip)')
    _annotate_peak(ax1, sparsity_tpu, bv_norm1, results_tpu, 'tpu_v1')
    _style_ax(ax1, sparsity_tpu, [base_norm1, bv_norm1],
              'vs TPU v1 Dense\n(SA 256×256, Mat 512×512)')

    # ── Subplot 2: vs Eyeriss ─────────────────────────────────
    ax2 = axes[1]
    base_norm2, bv_norm2 = _normalize(results_eyeriss, sparsity_eyeriss, 'eyeriss')
    ax2.plot(sparsity_eyeriss, base_norm2, '^-', color='tab:orange', linewidth=1.8, markersize=6,
             label="Eyeriss Act-Gating (ISCA'16)")
    ax2.plot(sparsity_eyeriss, bv_norm2,   'o-', color='tab:blue',   linewidth=2.5, markersize=7,
             label='Ours (BV Zero-Skip)')
    ax2.axvspan(73, 77, alpha=0.25, color='gold')
    # VerSA text below the x-band to avoid overlapping with BV line
    ax2.text(63, VERSA_NORM_LOW - 0.05,
             "VerSA range: 1.21x–1.60x", fontsize=7.5, color='goldenrod',
             va='top', ha='left')
    # Peak annotation — manual position to avoid VerSA band overlap
    peak_sp2   = max(sparsity_eyeriss,
                     key=lambda s: results_eyeriss[s]['eyeriss'] / results_eyeriss[s]['our_bv'])
    peak_spup2 = results_eyeriss[peak_sp2]['eyeriss'] / results_eyeriss[peak_sp2]['our_bv']
    b0_ey      = results_eyeriss[sparsity_eyeriss[0]]['eyeriss']
    peak_bv_norm2 = results_eyeriss[peak_sp2]['our_bv'] / b0_ey
    ax2.text(peak_sp2 - 18, peak_bv_norm2 - 0.04,
             f"Peak: {peak_spup2:.2f}x @ {peak_sp2}%",
             ha='center', va='top', fontsize=8.5,
             color='tab:blue', fontweight='semibold')
    _style_ax(ax2, sparsity_eyeriss, [base_norm2, bv_norm2],
              'vs Eyeriss Act-Gating\n(SA 14×14, Mat 56×56)')
    # Restore VerSA legend entry (axhspan removed, so add manually)
    versa_patch = Patch(facecolor='gold', alpha=0.5,
                        label="VerSA range (Elec.'24): 1.21x–1.60x")
    h2, l2 = ax2.get_legend_handles_labels()
    ax2.legend(h2 + [versa_patch], l2 + ["VerSA range (Elec.'24): 1.21x–1.60x"],
               loc='upper right', fontsize=9)

    # ── Subplot 3: Block Sensitivity ──────────────────────────
    ax3 = axes[2]
    baseline_0 = results_block[sparsity_block[0]]['our_bv']

    bv_norm3 = [results_block[s]['our_bv'] / baseline_0 for s in sparsity_block]

    # block=1 excluded from plot (identical to BV, only clutters legend)
    plot_block_sizes = [b for b in block_sizes if b != 1]
    colors   = cm.Reds(np.linspace(0.3, 0.85, len(plot_block_sizes)))
    all_vals = list(bv_norm3)
    for idx, b in enumerate(plot_block_sizes):
        norm_vals = [results_block[s][f'block_{b}'] / baseline_0 for s in sparsity_block]
        all_vals += norm_vals
        ax3.plot(sparsity_block, norm_vals,
                 linestyle='-', linewidth=1.6, marker='.', markersize=5,
                 color=colors[idx], label=f'Block={b}', alpha=0.85)

    # BV drawn last so it sits on top (zorder=5); placed first in legend manually
    ax3.plot(sparsity_block, bv_norm3, 'o-', color='tab:blue',
             linewidth=2.5, markersize=7, zorder=5, label='Ours (BV Zero-Skip)')

    ax3.set_xlabel('Sparsity (%)', fontsize=11)
    ax3.set_ylabel('Normalized Cycles  (BV @ 0% = 1.0)', fontsize=10)
    ax3.set_title('BV vs Structured Block Skip\n(SA 128×128, Mat 256×256, Sensitivity)',
                  fontsize=11)
    ax3.set_xticks(sparsity_block)
    ax3.set_xlim(min(sparsity_block) - 2, max(sparsity_block) + 2)
    y_lo3 = min(0.5, min(all_vals) - 0.03)
    y_hi3 = max(1.05, max(all_vals) + 0.05)
    ax3.set_ylim(y_lo3, y_hi3)
    # Reorder legend: BV first, then block lines
    handles, labels = ax3.get_legend_handles_labels()
    ax3.legend([handles[-1]] + handles[:-1], [labels[-1]] + labels[:-1],
               loc='upper right', fontsize=8.5, ncol=1)
    ax3.grid(axis='y', alpha=0.3)
    ax3.set_axisbelow(True)
    ax3.set_facecolor('white')

    # Annotate BV as always-optimal (fixed x position to avoid block lines)
    ax3.text(45, bv_norm3[-1] - 0.05,
             'BV: always optimal\n(fine-grained skip)',
             ha='center', va='top', fontsize=8,
             color='tab:blue', fontweight='semibold')

    fig.suptitle(
        "SA Core Latency Comparison vs. Published Baselines\n"
        "(Each experiment uses the same SA size as the reference paper)",
        fontsize=13, y=1.02,
    )

    fig.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Plot saved to: {save_path}")


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

def main():
    # Experiment 1: vs TPU v1
    SP_TPU  = [0, 20, 40, 60, 80, 90]
    res_tpu = sweep_vs_tpu_v1(SP_TPU, n_seeds=3)
    print_table_tpu_v1(res_tpu, SP_TPU, n_seeds=3)

    # Experiment 2: vs Eyeriss
    SP_EY  = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    res_ey = sweep_vs_eyeriss(SP_EY, n_seeds=5)
    print_table_eyeriss(res_ey, SP_EY, n_seeds=5)

    # Experiment 3: Block Sensitivity
    SP_BLOCK  = [0, 20, 40, 60, 80, 90]
    res_block = sweep_block_sensitivity(SP_BLOCK, n_seeds=3, block_sizes=BLOCK_SIZES)
    print_table_block_sensitivity(res_block, SP_BLOCK, block_sizes=BLOCK_SIZES, n_seeds=3)

    # Unified 3-subplot figure
    out_png = os.path.join(_FILE_DIR, 'paper_baseline_comparison.png')
    plot_all(res_tpu, res_ey, res_block,
             SP_TPU, SP_EY, SP_BLOCK,
             save_path=out_png, block_sizes=BLOCK_SIZES)

    print('Done.')


if __name__ == '__main__':
    main()
