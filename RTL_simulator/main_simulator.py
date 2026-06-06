"""
main.py — Entry point for the rectangular sparse SA accelerator Python simulator.

Prompts for M_SIZE, K_SIZE, N_SIZE (the three matrix dimensions) and sparsity
levels, then runs a performance sweep via sweep_sim.py.
"""
from core import sparse_RTL_simulator as sim
import matplotlib.pyplot as plt
import os

def sweep_file_sparsity(m_size=None, k_size=None, n_size=None,
                        sa_size=32, ratios=None, pool_type=0):
    """
    Sweep over sparsity levels using pre-generated matrix files.
    Files are named: matrix_a_<M>x<K>_<sparsity>_1.txt
                     matrix_b_<K>x<N>_<sparsity>_1.txt
    Falls back to random matrices if files are not found.
    """
    print("==========================================")
    print("=== Starting File-Based Sparsity Sweep ===")
    print("From sweep_sim.py & Function name: sweep_file_sparsity")
    print("==========================================")

    M_SIZE    = m_size
    K_SIZE    = k_size
    N_SIZE    = n_size
    SA_SIZE   = sa_size
    POOL_TYPE = pool_type
    BASE_DIR  = "./input_matrix"

    if ratios is not None:
        sparsity_levels = [int(r * 100) for r in ratios]
    else:
        sparsity_levels = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]

    results = []
    valid_sparsity = []

    print(f"{'='*70}")
    print(f"  File-Based Sparsity Sweep | A:{M_SIZE}x{K_SIZE}  B:{K_SIZE}x{N_SIZE}  SA:{SA_SIZE}x{SA_SIZE}")
    print(f"{'='*70}")
    print(f"{'Sparsity %':>12} | {'Total Cycles':>15} | {'File Status':>15}")
    print(f"{'-'*70}")

    for s in sparsity_levels:
        # Convention: matrix_a_<M>x<K>_<sparsity>_1.txt
        file_a = os.path.join(BASE_DIR, f"matrix_a_{M_SIZE}x{K_SIZE}_{s}_1.txt")
        file_b = os.path.join(BASE_DIR, f"matrix_b_{K_SIZE}x{N_SIZE}_{s}_1.txt")

        if not (os.path.exists(file_a) and os.path.exists(file_b)):
            file_a = None
            file_b = None
            status_text = "RANDOM MATRIX (MISSING FILES)"
        else:
            status_text = "FILE OK (USED)"

        res = sim.run_simulation(
            m_size=M_SIZE,
            k_size=K_SIZE,
            n_size=N_SIZE,
            sa_size=SA_SIZE,
            zero_ratio=s / 100.0,
            pool_type=POOL_TYPE,
            seed=42,
            verbose=False,
            file_a=file_a,
            file_b=file_b
        )

        if res['done']:
            cycles = res['total_cycles']
            results.append(cycles)
            valid_sparsity.append(s)
            print(f"{s:>11}% | {cycles:>15,d} | {status_text}")
        else:
            print(f"{s:>11}% | {'TIMEOUT':>15} | ERROR")

    return valid_sparsity, results

# ─────────────────────────────────────────────────────────────
# Visualization logic
# ─────────────────────────────────────────────────────────────
def plot_sweep(sparsity, cycles, mat_size):
    fig, ax1 = plt.subplots(figsize=(10, 6))
    print("==========================================")
    print("========= Starting Plotting Graph ========")
    print("From latency_visualization.py & Function name: plot_sweep")
    print("==========================================")

    # Primary Axis: Clock Cycles
    color_cycles = '#2c3e50'
    ax1.set_xlabel("Sparsity Level (%)", fontsize=11)
    ax1.set_ylabel("Clock Cycles", color=color_cycles, fontsize=11, fontweight='bold')
    line1 = ax1.plot(sparsity, cycles, marker='s', markersize=8, 
                     linestyle='-', color=color_cycles, linewidth=2, label="Clock Cycles")
    ax1.tick_params(axis='y', labelcolor=color_cycles)
    ax1.grid(True, alpha=0.3)

    # Annotate cycle values on the dots
    for i, txt in enumerate(cycles):
        ax1.annotate(f"{txt:,}", (sparsity[i], cycles[i]), 
                     textcoords="offset points", xytext=(0, 12), 
                     ha='center', fontsize=9, color=color_cycles)

    # Secondary Axis: Speedup
    ax2 = ax1.twinx()
    color_speedup = '#e67e22'
    dense_val = cycles[0]
    speedups = [dense_val / c for c in cycles]
    
    ax2.set_ylabel("Relative Speedup (vs Dense)", color=color_speedup, fontsize=11, fontweight='bold')
    line2 = ax2.plot(sparsity, speedups, marker='o', linestyle='--', 
                     color=color_speedup, alpha=0.7, label="Speedup")
    ax2.tick_params(axis='y', labelcolor=color_speedup)
    
    # Titles and layout
    plt.title(f"Accelerator Performance vs. Sparsity ({mat_size})",
              fontsize=14, pad=20)
    plt.xticks(sparsity)
    
    # Combined Legend
    lns = line1 + line2
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc='upper left')

    plt.tight_layout()
    plt.show()


def main():
    # ─────────────────────────────────────────────────────────────
    # 1. Configuration
    # ─────────────────────────────────────────────────────────────
    try:
        m_in = input(f"Enter M_SIZE (rows of A, rows of C) [default {sim.M_SIZE}]: ").strip()
        M_SIZE = int(m_in) if m_in else sim.M_SIZE

        k_in = input(f"Enter K_SIZE (cols of A = rows of B) [default {sim.K_SIZE}]: ").strip()
        K_SIZE = int(k_in) if k_in else sim.K_SIZE

        n_in = input(f"Enter N_SIZE (cols of B, cols of C) [default {sim.N_SIZE}]: ").strip()
        N_SIZE = int(n_in) if n_in else sim.N_SIZE

        sa_in = input(f"Enter SA_SIZE (tile size)          [default {sim.SA_SIZE}]: ").strip()
        SA_SIZE = int(sa_in) if sa_in else sim.SA_SIZE

        ratios_in = input(
            "Enter Sparsity % to test (e.g. 50, 70) or type 'all' for ALL: "
        ).strip().lower()
        if ratios_in == 'all':
            RATIOS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
            do_plot = True
        else:
            RATIOS = [float(x.strip()) / 100.0 for x in ratios_in.split(",")]
            do_plot = False
    except ValueError:
        print("[ERROR] Invalid input. Please enter numbers.")
        return

    print(f"\n=== Starting Accelerator Performance Sweep ===")
    print(f"Configuration: A({M_SIZE}x{K_SIZE}) x B({K_SIZE}x{N_SIZE}) | SA tile: {SA_SIZE}x{SA_SIZE}")

    # ─────────────────────────────────────────────────────────────
    # 2. Execute Sparsity Sweep
    # ─────────────────────────────────────────────────────────────
    print("\n[INFO] Starting File-Based Sparsity Sweep...")
    sparsity_data, cycle_data = sweep_file_sparsity(
        m_size=M_SIZE,
        k_size=K_SIZE,
        n_size=N_SIZE,
        sa_size=SA_SIZE,
        ratios=RATIOS,
        pool_type=sim.POOL_TYPE,
    )

    # ─────────────────────────────────────────────────────────────
    # 3. Generate Visualization
    # ─────────────────────────────────────────────────────────────
    if not cycle_data:
        print("\n[ERROR] No cycle data was returned from the simulation.")
    elif do_plot:
        print("\n[INFO] Plotting results...")
        # Pass a descriptive label instead of a single mat_size integer
        label = f"A({M_SIZE}x{K_SIZE}) x B({K_SIZE}x{N_SIZE})"
        plot_sweep(sparsity_data, cycle_data, label)
    else:
        print("\n[INFO] Skipping plot for specific custom runs.")


if __name__ == "__main__":
    main()