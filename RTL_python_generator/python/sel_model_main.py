import sys
import platform

def os_detection():
    # ── OS detection ──────────────────────────────────────────────
    IS_WINDOWS = platform.system() == "Windows"
    PYTHON     = "python" if IS_WINDOWS else "python3"

    if IS_WINDOWS:
        print("This PC is running Windows OS.")
    else:
        print(f"This PC is running macOS (detected: {platform.system()}).")

    answer = input("Proceed? (Y/N): ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    return IS_WINDOWS, PYTHON

def model_selection():

    # ── Model selection ───────────────────────────────────────────
    print("\nSelect model to run:")
    print("  1. run non_sparse only")
    print("  2. run sparse only")
    print("  3. run sparse3FSM only")
    print("  4. run all models (non_sparse, sparse, sparse3FSM)")
    print("  5. run sparse3FSM for final")

    choice = input("\nEnter choice (1-5): ").strip()
    if choice not in ("1", "2", "3", "4", "5"):
        print("Invalid choice. Aborting.")
        sys.exit(1)

    # ── Input parameters ──────────────────────────────────────────
    if choice == "5":
        # Rectangular matrix: A(M×K) × B(K×N) = C(M×N)
        print("You have selected to run sparse3FSM for final.")
        print("This is a rectangular matrix multiplication.")
        m_size  = int(input("Enter M_SIZE (rows of A, e.g. 32): ").strip())
        k_size  = int(input("Enter K_SIZE (cols of A = rows of B, e.g. 32): ").strip())
        n_size  = int(input("Enter N_SIZE (cols of B, e.g. 32): ").strip())
        sa_size = int(input("Enter SA_SIZE (e.g. 32): ").strip())
        mat_size = None   # not used for choice 6
    else:
        mat_size = int(input("Enter MAT_SIZE (e.g. 32): ").strip())
        sa_size  = int(input("Enter SA_SIZE  (e.g. 8): ").strip())
        m_size = k_size = n_size = mat_size

    ratios_input = input("Enter ZERO_RATIOS as floats (e.g. 0.0,0.1,0.8,0.9): ").strip()

    float_ratios     = [float(x) for x in ratios_input.strip("[]").split(",")]
    int_ratios       = [int(r * 100) for r in float_ratios]
    ratios_float_str = ",".join(str(r) for r in float_ratios)
    ratios_int_str   = ",".join(str(r) for r in int_ratios)

    model_labels = {"1": "non_sparse only", "2": "sparse only",
                    "3": "sparse3FSM only", "4": "all",
                    "5": "sparse3FSM for final"}
    print("\n[Confirm your inputs]")
    print(f"  Model     : {model_labels[choice]}")
    if choice == "5":
        print(f"  M_SIZE    : {m_size}")
        print(f"  K_SIZE    : {k_size}")
        print(f"  N_SIZE    : {n_size}")
    else:
        print(f"  MAT_SIZE  : {mat_size}")
    print(f"  SA_SIZE   : {sa_size}")
    print(f"  ZERO_RATIOS (float): {ratios_float_str}")
    print(f"  ZERO_RATIOS (int%) : {ratios_int_str}")

    answer = input("\nProceed? (Y/N): ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    return (choice, mat_size, sa_size, m_size, k_size, n_size,
            float_ratios, int_ratios, ratios_float_str, ratios_int_str)