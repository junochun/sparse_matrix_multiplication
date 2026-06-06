import sys
import numpy as np
from pathlib import Path

# =========================
# Usage:
#   정사각: python3 gen_matrix.py <N> <ZERO_RATIOS>
#   직사각: python3 gen_matrix.py <M> <K> <N> <ZERO_RATIOS>
#
# Example:
#   python3 gen_matrix.py 32 0.0,0.1,0.8,0.9
#   python3 gen_matrix.py 14 12 10 0.0,0.5,0.9
#
# 출력 파일:
#   정사각: matrix_{N}_{zr}_{id}.txt
#   직사각: matrix_a_{M}x{K}_{zr}_{id}.txt, matrix_b_{K}x{N}_{zr}_{id}.txt
# =========================

PYTHON_DIR = Path(__file__).parent
OUT_DIR = PYTHON_DIR / "input_matrix"
OUT_DIR.mkdir(exist_ok=True)

NUM_SETS_PER_RATIO = 2


def generate_matrix(rows, cols, zero_ratio):
    total     = rows * cols
    num_zeros = int(total * zero_ratio)
    mat  = np.random.randint(1, 10, size=(rows, cols))
    flat = mat.flatten()
    idx  = np.random.choice(total, num_zeros, replace=False)
    flat[idx] = 0
    return flat.reshape(rows, cols)


def save_flat(matrix, path):
    np.savetxt(path, matrix.flatten(), fmt='%d')


# ── 인자 수로 정사각/직사각 자동 감지 ─────────────────────────
# 정사각: <N> <ZERO_RATIOS>          → argv 길이 3
# 직사각: <M> <K> <N> <ZERO_RATIOS> → argv 길이 5

if len(sys.argv) == 3:
    # ── 정사각 모드 ───────────────────────────────────────────
    N           = int(sys.argv[1])
    zero_ratios = [float(x) for x in sys.argv[2].strip("[]").split(",")]

    for ratio in zero_ratios:
        zr_int = int(ratio * 100)
        for i in range(NUM_SETS_PER_RATIO):
            mat      = generate_matrix(N, N, ratio)
            filename = OUT_DIR / f"matrix_{N}_{zr_int}_{i+1}.txt"
            save_flat(mat, filename)
            print(f"Saved: {filename}  ({N}x{N}, zero_ratio={ratio})")

elif len(sys.argv) == 5:
    # ── 직사각 모드 ───────────────────────────────────────────
    M           = int(sys.argv[1])
    K           = int(sys.argv[2])
    N           = int(sys.argv[3])
    zero_ratios = [float(x) for x in sys.argv[4].strip("[]").split(",")]

    for ratio in zero_ratios:
        zr_int = int(ratio * 100)
        for i in range(NUM_SETS_PER_RATIO):
            mat_a   = generate_matrix(M, K, ratio)
            mat_b   = generate_matrix(K, N, ratio)
            fname_a = OUT_DIR / f"matrix_a_{M}x{K}_{zr_int}_{i+1}.txt"
            fname_b = OUT_DIR / f"matrix_b_{K}x{N}_{zr_int}_{i+1}.txt"
            save_flat(mat_a, fname_a)
            save_flat(mat_b, fname_b)
            print(f"Saved: {fname_a}  ({M}x{K}, zero_ratio={ratio})")
            print(f"Saved: {fname_b}  ({K}x{N}, zero_ratio={ratio})")

else:
    print("Usage:")
    print("  Square Matrix: python3 gen_matrix.py <N> <ZERO_RATIOS>")
    print("  Rectangular Matrix: python3 gen_matrix.py <M> <K> <N> <ZERO_RATIOS>")
    print("  e.g.   python3 gen_matrix.py 32 0.0,0.1,0.8,0.9")
    print("  e.g.   python3 gen_matrix.py 14 12 10 0.0,0.5,0.9")
    sys.exit(1)