"""
Baseline Comparison Module — Sparse Systolic Array Accelerator
==============================================================
Produces quantitative metrics matching three reference papers:

  1. SCALE-Sim  (Samajdar et al., arXiv 1811.02883)
       Dense systolic array baseline: dense_mode=True in run_simulation()
  2. Sparse-TPU (He et al., ICS 2020)
       Speedup reporting format: dense_cycles / sparse_cycles
  3. VerSA      (Electronics 2024, DOI 10.3390/electronics13081500)
       Sparse SA speedup at 75% sparsity reported as 1.21x–1.60x range

Usage:
    python baseline_comparison.py
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

from core.sparse_RTL_simulator import run_simulation


# ═══════════════════════════════════════════════════════════════
# 3-1  Dense baseline  (SCALE-Sim equivalent)
# ═══════════════════════════════════════════════════════════════
def run_dense_baseline(mat_size, sa_size, zero_ratio, seed):
    """
    Run one dense-mode trial (dense_mode=True).
    This is the SCALE-Sim equivalent: BV zero-skip is fully disabled and
    every PE executes SA_SIZE MACs regardless of input sparsity.

    Returns the full dict from run_simulation.
    """
    return run_simulation(
        m_size=mat_size, k_size=mat_size, n_size=mat_size,
        sa_size=sa_size,
        zero_ratio=zero_ratio,
        dense_mode=True,
        seed=seed,
        verbose=False,
    )


# ═══════════════════════════════════════════════════════════════
# 3-2  Sparsity sweep with n_seeds averaging
# ═══════════════════════════════════════════════════════════════
def benchmark_sparsity_sweep(mat_size, sa_size, sparsity_list, n_seeds=5):
    """
    Sweep over sparsity_list, average each metric over n_seeds random seeds.

    For each sparsity value and each seed the same matrices (same seed +
    zero_ratio) are used for both the dense and sparse runs, so the only
    difference is whether BV zero-skip is active.

    Returns
    -------
    dict keyed by sparsity (int, 0-100) with fields:
        dense_cycles  : mean total_cycles  (dense_mode=True)  — SCALE-Sim ref
        sparse_cycles : mean total_cycles  (dense_mode=False) — this work
        speedup       : dense_cycles / sparse_cycles            — Sparse-TPU / VerSA fmt
        skip_ratio    : mean skip_ratio from sparse runs
        dense_norm    : 1.0  (normalised baseline)
        sparse_norm   : sparse_cycles / dense_cycles_at_0pct
    """
    raw = {}
    for s in sparsity_list:
        zero_ratio = s / 100.0
        dense_cyc_list  = []
        sparse_cyc_list = []
        skip_list       = []

        for seed in range(n_seeds):
            dr = run_simulation(
                m_size=mat_size, k_size=mat_size, n_size=mat_size,
                sa_size=sa_size, zero_ratio=zero_ratio,
                dense_mode=True,  seed=seed, verbose=False,
            )
            sr = run_simulation(
                m_size=mat_size, k_size=mat_size, n_size=mat_size,
                sa_size=sa_size, zero_ratio=zero_ratio,
                dense_mode=False, seed=seed, verbose=False,
            )
            dense_cyc_list.append(dr['total_cycles'])
            sparse_cyc_list.append(sr['total_cycles'])
            skip_list.append(sr['skip_ratio'])

        raw[s] = {
            'dense_cycles':  float(np.mean(dense_cyc_list)),
            'sparse_cycles': float(np.mean(sparse_cyc_list)),
            'skip_ratio':    float(np.mean(skip_list)),
        }

    # Normalisation baseline: dense_cycles at 0 % sparsity
    if 0 in raw:
        dense_0pct = raw[0]['dense_cycles']
    else:
        dense_0pct = raw[min(raw)]['dense_cycles']

    results = {}
    for s, v in raw.items():
        sc = v['sparse_cycles']
        dc = v['dense_cycles']
        speedup = dc / sc if sc > 0 else 1.0
        results[s] = {
            'dense_cycles':  dc,
            'sparse_cycles': sc,
            'speedup':       speedup,
            'skip_ratio':    v['skip_ratio'],
            'dense_norm':    1.0,
            'sparse_norm':   sc / dense_0pct if dense_0pct > 0 else 1.0,
        }

    return results


# ═══════════════════════════════════════════════════════════════
# 3-3  Table printing  (Sparse-TPU paper Table style)
# ═══════════════════════════════════════════════════════════════
def print_comparison_table(results):
    """
    Print a comparison table in Sparse-TPU paper Table style, followed by
    a summary block with peak speedup, breakeven sparsity, and a note vs
    VerSA's reported range at 75 % sparsity.
    """
    header = ("Sparsity | Dense cycles | BV cycles | Speedup | Skip ratio")
    sep    = ("---------+--------------+-----------+---------+-----------")

    print()
    print(header)
    print(sep)
    for s in sorted(results):
        r  = results[s]
        dc = round(r['dense_cycles'])
        sc = round(r['sparse_cycles'])
        print(
            f"{s:>6}%  "
            f"| {dc:>12,} "
            f"| {sc:>9,} "
            f"| {r['speedup']:>6.2f}x "
            f"| {r['skip_ratio'] * 100:>8.1f}%"
        )
    print(sep)

    # ── Summary block ─────────────────────────────────────────
    speedups  = {s: results[s]['speedup'] for s in results}
    peak_s    = max(speedups, key=speedups.get)
    peak_spup = speedups[peak_s]

    breakeven = None
    for s in sorted(results):
        if results[s]['speedup'] > 1.0:
            breakeven = s
            break

    dense_0      = round(results[0]['dense_cycles'] if 0 in results
                         else results[min(results)]['dense_cycles'])
    sparse_peak  = round(results[peak_s]['sparse_cycles'])

    print()
    print("  --- Self-contained Analysis ---")
    print(f"  Dense baseline (BV skip disabled) : {dense_0:,} cycles  @ 0% sparsity")
    print(f"  BV skip (this work)               : {sparse_peak:,} cycles  @ {peak_s}% sparsity")
    print(f"  Latency reduction                 : {peak_spup:.2f}×  at peak sparsity")
    if breakeven is not None:
        print(f"  Breakeven zero density            : {breakeven}%  (speedup > 1.0× from here)")
    else:
        print("  Breakeven zero density            : not reached within tested range")
    print()


# ═══════════════════════════════════════════════════════════════
# 3-4  Publication-quality figure
# ═══════════════════════════════════════════════════════════════
def plot_comparison(results, save_path='latency_reduction.png'):
    """
    Single-subplot publication figure: Latency Reduction vs. Input Sparsity.

    Style: light horizontal gridlines only, white background,
    legend inside plot, axis labels in English.
    """
    sparsity_vals = sorted(results)
    speedups      = [results[s]['speedup'] for s in sparsity_vals]

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor('white')

    ax.plot(sparsity_vals, [1.0] * len(sparsity_vals),
            linestyle='--', color='gray', linewidth=1.8,
            label='Dense baseline')
    ax.plot(sparsity_vals, speedups,
            'o-', color='steelblue', linewidth=2.0, markersize=6,
            label='BV zero-skip (This work)')

    # Text-only peak annotation (no arrow)
    peak_idx      = int(np.argmax(speedups))
    peak_x        = sparsity_vals[peak_idx]
    peak_y        = speedups[peak_idx]
    y_range       = max(speedups) - min(speedups) if max(speedups) != min(speedups) else 0.1
    text_y_offset = y_range * 0.12
    ax.text(peak_x, peak_y + text_y_offset,
            f"Peak: {peak_y:.2f}×  @  {peak_x}% zero density",
            ha='center', va='bottom', fontsize=9, color='steelblue',
            fontweight='semibold')

    ax.set_xlabel('Zero density (%)', fontsize=12)
    ax.set_ylabel('Normalized Latency Reduction  (Dense = 1.0×)', fontsize=12)
    ax.set_title('Latency Reduction vs. Input Sparsity', fontsize=13)
    ax.legend(loc='upper left', fontsize=10, framealpha=0.9)
    ax.set_xticks(sparsity_vals)
    ax.set_xlim(min(sparsity_vals) - 2, max(sparsity_vals) + 2)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)
    ax.set_facecolor('white')

    fig.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Plot saved to: {save_path}")


# ═══════════════════════════════════════════════════════════════
# 3-5  Main
# ═══════════════════════════════════════════════════════════════
def main():
    mat_size      = 64
    sa_size       = 32
    n_seeds       = 5
    sparsity_list = [0, 10, 20, 30, 40, 50, 60, 70, 75, 80, 90]

    print('=' * 60)
    print('  Baseline Comparison  —  Dense vs. BV Zero-Skip')
    print(f'  Matrix: {mat_size}x{mat_size}  SA_SIZE: {sa_size}  Seeds: {n_seeds}')
    print(f'  Sparsity levels: {sparsity_list}')
    print('=' * 60)

    print('\nRunning sparsity sweep (this may take a few minutes)...\n')
    results = benchmark_sparsity_sweep(mat_size, sa_size, sparsity_list, n_seeds)

    print_comparison_table(results)

    out_png = os.path.join(_FILE_DIR, 'latency_reduction.png')
    plot_comparison(results, save_path=out_png)

    print('Done.')


if __name__ == '__main__':
    main()
