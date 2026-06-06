"""
End-to-End Latency Breakdown — RTL Simulation on MNIST Test Images
===================================================================
Runs the cycle-accurate RTL simulator on N=100 MNIST test images
(first 100 in the test set) and reports per-layer cycle counts,
skip ratios, and per-digit distributions.

Inference pipeline mirrors interactive_demo.py exactly:
  input_vec = (image_0_127 > 64).astype(int32)      # (1, 784)
  Layer 1: run_simulation(m=1, k=784, n=100, sa=64)
  act1    = (clip(round(raw/(127²)×127), 0, 127) > 0) # (1, 100)
  Layer 2: run_simulation(m=1, k=100, n=10,  sa=64)

Usage:
    python latency_breakdown.py
"""

import os
import sys

import numpy as np
from matplotlib.gridspec import GridSpec

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_FILE_DIR)
_SRC = os.path.join(_ROOT, '..', 'DNN_from_git', 'src')
sys.path.insert(0, _SRC)
sys.path.insert(0, _ROOT)

import mnist_loader
from core.sparse_RTL_simulator import run_simulation

WEIGHT_PATH = os.path.join(_ROOT, 'training', 'trained_dnn_weights.npz')
N_IMAGES    = 100
SA_SIZE     = 64


# ═══════════════════════════════════════════════════════════════
# Step 1 — Load weights and MNIST test images
# ═══════════════════════════════════════════════════════════════
def load_data():
    if not os.path.exists(WEIGHT_PATH):
        raise FileNotFoundError(
            f"Weights not found: {WEIGHT_PATH}\n"
            "Run 'python dnn_trainer.py' first."
        )
    weights = np.load(WEIGHT_PATH)
    W1 = weights['W1']   # (100, 784) int32
    W2 = weights['W2']   # (10,  100) int32

    print("Loading MNIST test set...")
    _, _, test_data = mnist_loader.load_data_wrapper()
    images = test_data[:N_IMAGES]   # first 100
    return W1, W2, images


# ═══════════════════════════════════════════════════════════════
# Step 2 — Run RTL simulation for each image
# ═══════════════════════════════════════════════════════════════
def run_simulations(W1, W2, images):
    """
    Returns arrays of length N_IMAGES:
        cyc1, cyc2, total_cycs, skip1, skip2, labels
    """
    W1T = W1.T   # (784, 100)  val_b for Layer 1
    W2T = W2.T   # (100, 10)   val_b for Layer 2

    cyc1_list   = []
    cyc2_list   = []
    skip1_list  = []
    skip2_list  = []
    labels_list = []

    print(f"Running RTL simulation for {N_IMAGES} images (sa_size={SA_SIZE})...")
    for idx, (x, label) in enumerate(images):
        # ── Preprocess (mirrors interactive_demo.py) ──────────
        x_scaled  = np.round(x.reshape(1, 784) * 127).astype(np.int32)
        input_vec = (x_scaled > 64).astype(np.int32)          # (1, 784)

        # ── Layer 1: (1×784) @ (784×100) ──────────────────────
        r1 = run_simulation(
            m_size=1, k_size=784, n_size=100,
            sa_size=SA_SIZE,
            val_a=input_vec, val_b=W1T,
            verbose=False,
        )
        cyc1   = r1['total_cycles']
        skip1  = r1['skip_ratio']

        raw1 = input_vec.astype(np.int64) @ W1T.astype(np.int64)   # (1, 100)
        out1 = np.clip(
            np.round(raw1 / (127 * 127) * 127), 0, 127
        ).astype(np.int32)
        act1 = (out1 > 0).astype(np.int32)                          # (1, 100)

        # ── Layer 2: (1×100) @ (100×10) ───────────────────────
        r2 = run_simulation(
            m_size=1, k_size=100, n_size=10,
            sa_size=SA_SIZE,
            val_a=act1, val_b=W2T,
            verbose=False,
        )
        cyc2  = r2['total_cycles']
        skip2 = r2['skip_ratio']

        cyc1_list.append(cyc1)
        cyc2_list.append(cyc2)
        skip1_list.append(skip1)
        skip2_list.append(skip2)
        labels_list.append(int(label))

        if (idx + 1) % 20 == 0:
            print(f"  Processed {idx+1}/{N_IMAGES} images...")

    cyc1  = np.array(cyc1_list,  dtype=np.float64)
    cyc2  = np.array(cyc2_list,  dtype=np.float64)
    skip1 = np.array(skip1_list, dtype=np.float64)
    skip2 = np.array(skip2_list, dtype=np.float64)
    total = cyc1 + cyc2
    labels = np.array(labels_list, dtype=np.int32)

    return cyc1, cyc2, total, skip1, skip2, labels


# ═══════════════════════════════════════════════════════════════
# Step 3 — Print results
# ═══════════════════════════════════════════════════════════════
def print_results(cyc1, cyc2, total, skip1, skip2, labels):
    n = len(total)
    l1_share = float(np.mean(cyc1 / total)) * 100
    l2_share = float(np.mean(cyc2 / total)) * 100

    print()
    print(f"  === End-to-End Latency Breakdown (N={n} MNIST test images) ===")
    print()
    print("  Layer 1 (784\u2192100):")
    print(f"    Cycles:     mean={np.mean(cyc1):.0f}"
          f"  std={np.std(cyc1):.1f}"
          f"  min={np.min(cyc1):.0f}"
          f"  max={np.max(cyc1):.0f}")
    print(f"    Skip ratio: mean={np.mean(skip1)*100:.1f}%")
    print()
    print("  Layer 2 (100\u219210):")
    print(f"    Cycles:     mean={np.mean(cyc2):.0f}"
          f"  std={np.std(cyc2):.1f}"
          f"  min={np.min(cyc2):.0f}"
          f"  max={np.max(cyc2):.0f}")
    print(f"    Skip ratio: mean={np.mean(skip2)*100:.1f}%")
    print()
    print("  Total inference:")
    print(f"    Cycles:     mean={np.mean(total):.0f}"
          f"  std={np.std(total):.1f}"
          f"  min={np.min(total):.0f}"
          f"  max={np.max(total):.0f}")
    print(f"    Layer 1 share: {l1_share:.1f}%")
    print(f"    Layer 2 share: {l2_share:.1f}%")
    print()
    print("  Per-digit mean total cycles:")
    parts = []
    for d in range(10):
        mask = labels == d
        mean_d = np.mean(total[mask]) if mask.any() else float('nan')
        parts.append(f"    Digit {d}: {mean_d:.0f}")
    # print two digits per line for readability
    for i in range(0, 10, 2):
        print(f"  {parts[i]}   {parts[i+1]}")
    print()


# ═══════════════════════════════════════════════════════════════
# Step 4 — Plot
# ═══════════════════════════════════════════════════════════════
def plot_results(cyc1, cyc2, total, skip1, skip2, labels,
                 save_path='latency_breakdown.png'):
    """
    Three-panel figure:
      Panel 1 (top-left):  stacked bar chart — mean cycles per digit
      Panel 2 (top-right): scatter — Layer1 skip ratio vs total cycles
      Panel 3 (bottom):    box plot — total cycle distribution per digit
    """
    digits = list(range(10))
    tab10  = plt.get_cmap('tab10')

    fig = plt.figure(figsize=(12, 8))
    fig.patch.set_facecolor('white')
    gs  = GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[0, 1])
    ax3 = fig.add_subplot(gs[1, :])

    # ── Panel 1: Stacked bar chart ─────────────────────────────
    mean_c1 = np.array([np.mean(cyc1[labels == d]) if (labels == d).any() else 0.0
                         for d in digits])
    mean_c2 = np.array([np.mean(cyc2[labels == d]) if (labels == d).any() else 0.0
                         for d in digits])
    x = np.arange(len(digits))

    ax1.bar(x, mean_c1, label='Layer 1', color='steelblue',  alpha=0.88)
    ax1.bar(x, mean_c2, bottom=mean_c1, label='Layer 2',
            color='darkorange', alpha=0.88)
    ax1.set_xlabel('Digit', fontsize=11)
    ax1.set_ylabel('Mean Cycles', fontsize=11)
    ax1.set_title('Mean Cycles per Digit', fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(digits)
    ax1.legend(fontsize=9, loc='upper right')
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_axisbelow(True)
    ax1.set_facecolor('white')

    # ── Panel 2: Scatter — skip ratio vs total cycles ──────────
    skip1_pct = skip1 * 100
    for d in digits:
        mask = labels == d
        if mask.any():
            ax2.scatter(skip1_pct[mask], total[mask],
                        color=tab10(d), s=28, alpha=0.80,
                        label=str(d), zorder=3)

    # Regression line
    if len(skip1_pct) > 1:
        z = np.polyfit(skip1_pct, total, 1)
        p = np.poly1d(z)
        x_fit = np.linspace(skip1_pct.min(), skip1_pct.max(), 200)
        ax2.plot(x_fit, p(x_fit), 'k--', linewidth=1.4,
                 alpha=0.65, label='Fit', zorder=2)

    ax2.set_xlabel('Layer 1 Skip Ratio (%)', fontsize=11)
    ax2.set_ylabel('Total Cycles', fontsize=11)
    ax2.set_title('Skip Ratio vs. Total Cycles', fontsize=12)
    ax2.legend(title='Digit', fontsize=7, title_fontsize=8,
               loc='upper right', ncol=2, framealpha=0.85)
    ax2.grid(axis='y', alpha=0.3)
    ax2.set_axisbelow(True)
    ax2.set_facecolor('white')

    # ── Panel 3: Box plot — cycle distribution per digit ───────
    box_data = [total[labels == d].tolist() if (labels == d).any() else [0]
                for d in digits]
    bp = ax3.boxplot(box_data, positions=digits, patch_artist=True,
                     widths=0.55, showfliers=True,
                     flierprops=dict(marker='o', markersize=4,
                                     markerfacecolor='gray', alpha=0.5))
    for patch, d in zip(bp['boxes'], digits):
        patch.set_facecolor(tab10(d))
        patch.set_alpha(0.75)

    ax3.set_xlabel('Digit', fontsize=11)
    ax3.set_ylabel('Total Cycles', fontsize=11)
    ax3.set_title('Cycle Distribution per Digit', fontsize=12)
    ax3.set_xticks(digits)
    ax3.grid(axis='y', alpha=0.3)
    ax3.set_axisbelow(True)
    ax3.set_facecolor('white')

    out = os.path.join(_FILE_DIR, save_path)
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Plot saved to: {out}")


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    W1, W2, images = load_data()
    cyc1, cyc2, total, skip1, skip2, labels = run_simulations(W1, W2, images)
    print_results(cyc1, cyc2, total, skip1, skip2, labels)
    plot_results(cyc1, cyc2, total, skip1, skip2, labels)
