"""
run_network.py — Scale-Sim style network-level runner for the Sparse BV Systolic Array Simulator.

Reads a topology CSV file (one row per layer) and runs the cycle-accurate RTL
simulator for each layer in sequence, printing a scale-sim-style summary and
saving COMPUTE_REPORT.csv to the output directory.

Topology CSV format:
    Layer Name,M,K,N,Sparsity
    FC1,1,784,100,0.5
    FC2,1,100,10,0.1

    - M, K, N  : matrix dimensions for A(M×K) @ B(K×N) = C(M×N)
    - Sparsity : fraction of zeros in randomly generated input (0.0 – 1.0)
                 If a weights file is provided via -w, this column is ignored.

Usage:
    python run_network.py -t topologies/mnist_dnn.csv
    python run_network.py -t topologies/mnist_dnn.csv -p results/ -sa 32
    python run_network.py -t topologies/mnist_dnn.csv -w trained_dnn_weights.npz
"""

import argparse
import csv
import math
import os
import sys

import numpy as np

from core.sparse_RTL_simulator import run_simulation


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _ceildiv(a, b):
    return (a + b - 1) // b


def mapping_efficiency(m, n, sa):
    """
    Fraction of PE slots that are mapped to real output elements.
    = (M * N) / (ceil(M/SA)*SA * ceil(N/SA)*SA)
    """
    padded_m = _ceildiv(m, sa) * sa
    padded_n = _ceildiv(n, sa) * sa
    return (m * n) / (padded_m * padded_n) * 100.0


def parse_topology(csv_path):
    """Return list of dicts: {name, M, K, N, sparsity}."""
    layers = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['Layer Name'].strip()
            m    = int(row['M'].strip())
            k    = int(row['K'].strip())
            n    = int(row['N'].strip())
            sp   = float(row.get('Sparsity', '0.0').strip())
            layers.append({'name': name, 'M': m, 'K': k, 'N': n, 'sparsity': sp})
    return layers


def load_weights(npz_path):
    """Load W1, W2 from a .npz file produced by dnn_trainer.py."""
    d = np.load(npz_path)
    return {k: d[k] for k in d.files}


def save_compute_report(rows, out_dir):
    """Save COMPUTE_REPORT.csv to out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'COMPUTE_REPORT.csv')
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'LayerID', 'Layer Name', 'M', 'K', 'N',
            'Compute Cycles', 'Skip Ratio %',
            'Effective MACs', 'Total MACs',
            'Mapping Efficiency %',
            'Avg BRAM_A BW (words/cyc)', 'Avg BRAM_B BW (words/cyc)', 'Avg BRAM_C BW (words/cyc)',
            'DRAM Stall Cycles', 'Total Cycles (w/DRAM)', 'Min DRAM BW Needed (words/cyc)',
        ])
        total_cycles = 0
        for r in rows:
            writer.writerow([
                r['id'], r['name'], r['M'], r['K'], r['N'],
                r['total_cycles'],
                f"{r['skip_ratio']*100:.2f}",
                r['effective_macs'], r['total_macs'],
                f"{r['map_eff']:.2f}",
                f"{r['bw_a']:.3f}", f"{r['bw_b']:.3f}", f"{r['bw_c']:.3f}",
                r['dram_stall'], r['total_w_dram'], f"{r['min_dram_bw']:.3f}",
            ])
            total_cycles += r['total_cycles']
        # Summary row
        writer.writerow(['TOTAL', '', '', '', '', total_cycles, '', '', '', '', '', '', '', '', '', ''])
    return path


# ─────────────────────────────────────────────────────────────
# Weight matching: try to assign weights from npz to each layer
# ─────────────────────────────────────────────────────────────
def _get_weight_pair(layer_idx, layer, weights):
    """
    Heuristic: match layers in order to weight keys sorted by name.
    Returns (val_a, val_b) numpy arrays or (None, None).
    val_a is a random activation matching the layer's M×K shape.
    val_b is the weight matrix transposed to K×N.
    """
    keys = sorted(weights.keys())
    if layer_idx >= len(keys):
        return None, None
    W = weights[keys[layer_idx]]           # e.g. (100, 784) or (10, 100)
    # W shape is (out, in) → transpose to (in, out) = (K, N)
    Wt = W.T.astype(np.int32)
    k_actual, n_actual = Wt.shape
    if k_actual != layer['K'] or n_actual != layer['N']:
        print(f"  [WARN] Weight shape {W.shape} does not match "
              f"K={layer['K']}, N={layer['N']}. Using random input.")
        return None, Wt
    # Random binary activation (simulates binarized input)
    rng = np.random.default_rng(42)
    val_a = rng.integers(0, 2, size=(layer['M'], layer['K']), dtype=np.int32)
    return val_a, Wt


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog='run_network.py',
        description=(
            '========================================================\n'
            '   Sparse BV Systolic Array Simulator  —  Network Runner\n'
            '========================================================\n'
            '\n'
            'Runs cycle-accurate RTL simulation for each layer defined in a\n'
            'topology CSV file, then prints a scale-sim style per-layer report\n'
            'and saves COMPUTE_REPORT.csv to the output directory.\n'
            '\n'
            'Topology CSV format (one row per layer):\n'
            '  Layer Name, M, K, N, Sparsity\n'
            '  FC1, 1, 784, 100, 0.5\n'
            '  FC2, 1, 100,  10, 0.1\n'
            '\n'
            '  M, K, N   : matrix dimensions  A(M×K) @ B(K×N) = C(M×N)\n'
            '  Sparsity  : zero fraction for random input generation (0.0–1.0)\n'
            '              (ignored when -w weights file is provided)\n'
        ),
        epilog=(
            '----------------------------------------\n'
            'Examples:\n'
            '  # Basic run with random matrices\n'
            '  python run_network.py -t topologies/mnist_dnn.csv\n'
            '\n'
            '  # Use trained weights instead of random matrices\n'
            '  python run_network.py -t topologies/mnist_dnn.csv \\\n'
            '                        -w trained_dnn_weights.npz\n'
            '\n'
            '  # Change SA tile size and output directory\n'
            '  python run_network.py -t topologies/mnist_dnn.csv \\\n'
            '                        -sa 64 -p results/sa64/\n'
            '\n'
            '  # Model off-chip DRAM bandwidth (computes stall cycles)\n'
            '  python run_network.py -t topologies/mnist_dnn.csv -d 64\n'
            '\n'
            '  # Full example\n'
            '  python run_network.py -t topologies/mnist_dnn.csv \\\n'
            '                        -w trained_dnn_weights.npz  \\\n'
            '                        -sa 32 -d 16 -p results/full/\n'
            '----------------------------------------\n'
            'Output files:\n'
            '  <output>/COMPUTE_REPORT.csv  —  per-layer metrics table\n'
            '\n'
            'DRAM BW reference values (8-bit words at 1 GHz):\n'
            '  LPDDR4-3200  : ~400 words/cycle   (32-bit bus)\n'
            '  DDR4-3200    : ~400 words/cycle   (64-bit bus → 800)\n'
            '  Typical edge : 8–32 words/cycle\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-t', '--topology',
                        default='./topologies/mnist_dnn.csv',
                        metavar='FILE',
                        help='Path to topology CSV file  (default: ./topologies/mnist_dnn.csv)')
    parser.add_argument('-p', '--output',
                        default='./results/',
                        metavar='DIR',
                        help='Output directory for COMPUTE_REPORT.csv  (default: ./results/)')
    parser.add_argument('-sa', '--sa-size',
                        type=int, default=32,
                        metavar='N',
                        help='Systolic array tile size N×N  (default: 32)')
    parser.add_argument('-w', '--weights',
                        default=None,
                        metavar='FILE',
                        help='.npz weights file from dnn_trainer.py  (default: use random matrices)')
    parser.add_argument('-s', '--seed',
                        type=int, default=42,
                        metavar='N',
                        help='RNG seed for random matrix generation  (default: 42)')
    parser.add_argument('-d', '--dram-bw',
                        type=float, default=None,
                        metavar='BW',
                        help=('Off-chip DRAM bandwidth in words/cycle  (default: disabled)\n'
                              'When set, adds DRAM stall analysis to each layer.\n'
                              'stall = max(0, ceil((M*K+K*N+M*N)/BW) - compute_cycles)'))
    args = parser.parse_args()

    SA_SIZE  = args.sa_size
    DRAM_BW  = args.dram_bw

    # ── Header ────────────────────────────────────────────────
    print("=" * 52)
    print("****** Sparse BV Systolic Array Simulator *******")
    print("=" * 52)
    print(f"Array Size:      {SA_SIZE}x{SA_SIZE}")
    print(f"Topology file:   {args.topology}")
    print(f"Output dir:      {args.output}")
    if args.weights:
        print(f"Weights file:    {args.weights}")
    if DRAM_BW is not None:
        print(f"DRAM Bandwidth:  {DRAM_BW} words/cycle")
    else:
        print(f"DRAM Bandwidth:  (not modelled)")
    print("=" * 52)
    print()

    # ── Load topology ─────────────────────────────────────────
    if not os.path.exists(args.topology):
        print(f"[ERROR] Topology file not found: {args.topology}")
        sys.exit(1)
    layers = parse_topology(args.topology)

    # ── Load weights (optional) ───────────────────────────────
    weights = None
    if args.weights:
        if not os.path.exists(args.weights):
            print(f"[WARN] Weights file not found: {args.weights}. Using random matrices.")
        else:
            weights = load_weights(args.weights)

    # ── Run each layer ────────────────────────────────────────
    report_rows = []

    for idx, layer in enumerate(layers):
        name = layer['name']
        M, K, N = layer['M'], layer['K'], layer['N']
        sparsity = layer['sparsity']

        print(f"Running Layer {idx} ({name})")
        print(f"  Matrix: A({M}x{K}) @ B({K}x{N})")

        # Determine input matrices
        val_a, val_b = None, None
        if weights is not None:
            val_a, val_b = _get_weight_pair(idx, layer, weights)

        res = run_simulation(
            m_size=M,
            k_size=K,
            n_size=N,
            sa_size=SA_SIZE,
            zero_ratio=sparsity,
            seed=args.seed,
            verbose=False,
            val_a=val_a,
            val_b=val_b,
            dram_bw=DRAM_BW,
        )

        if not res['done']:
            print(f"  [ERROR] Simulation did not complete for layer {idx}.")
            continue

        total_cyc        = res['total_cycles']
        skip_ratio       = res['skip_ratio']
        eff_macs         = res['effective_macs']
        total_macs       = res['total_ops'] // 2
        map_eff          = mapping_efficiency(M, N, SA_SIZE)
        bw_a             = res['avg_bram_a_bw']
        bw_b             = res['avg_bram_b_bw']
        bw_c             = res['avg_bram_c_bw']
        dram_stall       = res['dram_stall_cycles']
        total_w_dram     = res['total_cycles_w_dram']
        min_dram_bw      = res['min_dram_bw_needed']
        dram_words       = res['dram_total_words']

        print(f"  Compute cycles:        {total_cyc:,}")
        print(f"  Skip ratio:            {skip_ratio*100:.2f}%")
        print(f"  Effective MACs:        {eff_macs:,} / {total_macs:,}")
        print(f"  Mapping efficiency:    {map_eff:.2f}%")
        print(f"  Avg BRAM_A (IFMAP) BW: {bw_a:.3f} words/cycle")
        print(f"  Avg BRAM_B (Filter) BW:{bw_b:.3f} words/cycle")
        print(f"  Avg BRAM_C (OFMAP) BW: {bw_c:.3f} words/cycle")
        if DRAM_BW is not None:
            bottleneck = "  *** MEMORY BOUND ***" if dram_stall > 0 else "  (compute bound)"
            print(f"  ── DRAM Analysis (BW={DRAM_BW} words/cycle) ──────────")
            print(f"  DRAM total data:       {dram_words:,} words  "
                  f"(A:{M*K:,} + B:{K*N:,} + C:{M*N:,})")
            print(f"  Min DRAM BW needed:    {min_dram_bw:.3f} words/cycle")
            print(f"  DRAM stall cycles:     {dram_stall:,}{bottleneck}")
            print(f"  Total cycles (w/DRAM): {total_w_dram:,}")
        print()

        report_rows.append({
            'id': idx, 'name': name,
            'M': M, 'K': K, 'N': N,
            'total_cycles': total_cyc,
            'skip_ratio': skip_ratio,
            'effective_macs': eff_macs,
            'total_macs': total_macs,
            'map_eff': map_eff,
            'bw_a': bw_a, 'bw_b': bw_b, 'bw_c': bw_c,
            'dram_stall': dram_stall,
            'total_w_dram': total_w_dram,
            'min_dram_bw': min_dram_bw,
        })

    # ── Summary ───────────────────────────────────────────────
    if report_rows:
        total_net_cycles  = sum(r['total_cycles']  for r in report_rows)
        total_dram_cycles = sum(r['total_w_dram']  for r in report_rows)
        total_dram_stall  = sum(r['dram_stall']    for r in report_rows)
        print("=" * 52)
        print(f"Total compute cycles:    {total_net_cycles:,}")
        if DRAM_BW is not None:
            print(f"Total DRAM stall cycles: {total_dram_stall:,}")
            print(f"Total cycles (w/DRAM):   {total_dram_cycles:,}")

        # Save CSV
        csv_path = save_compute_report(report_rows, args.output)
        print(f"Saved COMPUTE_REPORT.csv: {csv_path}")

    print("****** Sparse BV SA Sim Run Complete ************")
    print("=" * 52)


if __name__ == '__main__':
    main()
