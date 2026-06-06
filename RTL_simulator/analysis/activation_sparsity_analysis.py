"""
Activation Sparsity Analysis — MNIST Test Set
==============================================
Measures natural activation sparsity produced by the trained QAT DNN
on the full MNIST test set (10,000 images), using the same preprocessing
and integer forward-pass pipeline as interactive_demo.py.

No RTL simulation is performed; this is a pure-numpy measurement pass.

Usage:
    python activation_sparsity_analysis.py
"""

import os
import sys

import numpy as np

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_FILE_DIR)
_SRC = os.path.join(_ROOT, '..', 'DNN_from_git', 'src')
sys.path.insert(0, _SRC)

import mnist_loader

WEIGHT_PATH = os.path.join(_ROOT, 'training', 'trained_dnn_weights.npz')


# ═══════════════════════════════════════════════════════════════
# Step 1 — Load weights
# ═══════════════════════════════════════════════════════════════
def load_weights():
    if not os.path.exists(WEIGHT_PATH):
        raise FileNotFoundError(
            f"Weights not found: {WEIGHT_PATH}\n"
            "Run 'python dnn_trainer.py' first."
        )
    data = np.load(WEIGHT_PATH)
    W1 = data['W1']  # (100, 784) int32
    W2 = data['W2']  # (10, 100)  int32
    return W1, W2


# ═══════════════════════════════════════════════════════════════
# Step 2 — Measure sparsity over full test set
# ═══════════════════════════════════════════════════════════════
def run_analysis():
    """
    Returns
    -------
    input_sparsities : np.ndarray  shape (10000,)  zero-ratio per image
    act1_sparsities  : np.ndarray  shape (10000,)  Layer 1 activation sparsity
    labels           : np.ndarray  shape (10000,)  digit class 0-9
    per_digit        : dict  digit → mean act1_sparsity (float, 0-1)
    """
    print("Loading MNIST test set...")
    _, _, test_data = mnist_loader.load_data_wrapper()

    print("Loading weights...")
    W1, _ = load_weights()   # W1: (100, 784)

    n = len(test_data)
    input_sparsities = np.empty(n, dtype=np.float64)
    act1_sparsities  = np.empty(n, dtype=np.float64)
    labels           = np.empty(n, dtype=np.int32)

    print(f"Measuring activation sparsity over {n} images...")
    for i, (x, label) in enumerate(test_data):
        # ── Preprocess: scale [0,1] → [0,127], binarize >64 ──
        x_scaled  = np.round(x.reshape(1, 784) * 127).astype(np.int32)
        input_vec = (x_scaled > 64).astype(np.int32)           # (1, 784)

        # ── Layer 1 forward (numpy, mirrors interactive_demo.py) ──
        raw1 = input_vec @ W1.T                                 # (1, 100)
        out1 = np.clip(
            np.round(raw1 / (127 * 127) * 127), 0, 127
        ).astype(np.int32)
        act1 = (out1 > 0).astype(np.int32)                     # binarized (1, 100)

        input_sparsities[i] = np.mean(input_vec == 0)
        act1_sparsities[i]  = np.mean(act1 == 0)
        labels[i]           = int(label)

    per_digit = {
        d: float(np.mean(act1_sparsities[labels == d]))
        for d in range(10)
    }
    return input_sparsities, act1_sparsities, labels, per_digit


# ═══════════════════════════════════════════════════════════════
# Step 3 — Print results
# ═══════════════════════════════════════════════════════════════
def print_results(input_sparsities, act1_sparsities, labels, per_digit):
    n = len(input_sparsities)
    i_mean = np.mean(input_sparsities) * 100
    i_std  = np.std(input_sparsities)  * 100
    i_min  = np.min(input_sparsities)  * 100
    i_max  = np.max(input_sparsities)  * 100

    a_mean = np.mean(act1_sparsities) * 100
    a_std  = np.std(act1_sparsities)  * 100
    a_min  = np.min(act1_sparsities)  * 100
    a_max  = np.max(act1_sparsities)  * 100

    print()
    print(f"  === Activation Sparsity Analysis (MNIST test set, N={n}) ===")
    print()
    print("  Layer 0 Input Sparsity (after binarize >64):")
    print(f"    Mean: {i_mean:.1f}% \u00b1 {i_std:.1f}%"
          f"   Min: {i_min:.1f}%   Max: {i_max:.1f}%")
    print()
    print("  Layer 1 Output Sparsity (after ReLU + binarize >0):")
    print(f"    Mean: {a_mean:.1f}% \u00b1 {a_std:.1f}%"
          f"   Min: {a_min:.1f}%   Max: {a_max:.1f}%")
    print()
    print("  Per-digit breakdown (Layer 1 output sparsity):")
    for d in range(10):
        print(f"    Digit {d}: {per_digit[d]*100:.1f}%")
    print()
    print(f"  Key insight: BV zero-skip exploits {a_mean:.1f}% natural activation sparsity")
    print(f"               without any weight pruning.")
    print()


# ═══════════════════════════════════════════════════════════════
# Step 4 — Plot
# ═══════════════════════════════════════════════════════════════
def plot_results(input_sparsities, act1_sparsities, labels, per_digit,
                 save_path='activation_sparsity.png'):
    """
    Two-panel figure:
      Panel 1 (left):  grouped bar chart per digit
      Panel 2 (right): histogram of act1_sparsity distribution
    """
    digits = list(range(10))
    per_digit_input = [float(np.mean(input_sparsities[labels == d])) * 100
                       for d in digits]
    per_digit_act1  = [per_digit[d] * 100 for d in digits]
    mean_act1 = float(np.mean(act1_sparsities)) * 100

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor('white')
    fig.suptitle("Activation Sparsity Distribution \u2014 MNIST Test Set",
                 fontsize=14, fontweight='semibold')

    # ── Panel 1: grouped bar chart ─────────────────────────────
    x     = np.arange(len(digits))
    width = 0.38
    ax1.bar(x - width / 2, per_digit_input, width,
            label='Input (Layer 0)', color='steelblue', alpha=0.85)
    ax1.bar(x + width / 2, per_digit_act1, width,
            label='Activation (Layer 1)', color='darkorange', alpha=0.85)

    ax1.axhline(mean_act1, color='darkorange', linestyle='--',
                linewidth=1.5, alpha=0.9)
    ax1.text(digits[-1] + 0.5, mean_act1 + 0.8,
             f"Mean: {mean_act1:.1f}%",
             ha='right', va='bottom', color='darkorange', fontsize=9)

    ax1.set_xlabel('Digit', fontsize=12)
    ax1.set_ylabel('Mean Sparsity (%)', fontsize=12)
    ax1.set_title('Per-Digit Sparsity', fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(digits)
    ax1.set_ylim(0, 108)
    ax1.legend(fontsize=10, loc='lower right')
    ax1.grid(axis='y', alpha=0.3)
    ax1.set_axisbelow(True)
    ax1.set_facecolor('white')

    # ── Panel 2: histogram ────────────────────────────────────
    ax2.hist(act1_sparsities * 100, bins=30,
             color='darkorange', alpha=0.7, edgecolor='none')
    ax2.axvline(mean_act1, color='darkorange', linestyle='--', linewidth=1.5)
    ymax = ax2.get_ylim()[1]
    ax2.text(mean_act1 + 0.5, ymax * 0.95,
             f"Mean: {mean_act1:.1f}%",
             va='top', color='darkorange', fontsize=9)

    ax2.set_xlabel('Sparsity (%)', fontsize=12)
    ax2.set_ylabel('Count', fontsize=12)
    ax2.set_title('Distribution of Layer 1 Activation Sparsity', fontsize=12)
    ax2.grid(axis='y', alpha=0.3)
    ax2.set_axisbelow(True)
    ax2.set_facecolor('white')

    fig.tight_layout()
    out = os.path.join(_FILE_DIR, save_path)
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"  Plot saved to: {out}")


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    input_sparsities, act1_sparsities, labels, per_digit = run_analysis()
    print_results(input_sparsities, act1_sparsities, labels, per_digit)
    plot_results(input_sparsities, act1_sparsities, labels, per_digit)
