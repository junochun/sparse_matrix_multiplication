import os
import sys
import re
import glob
import platform
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# =========================
# verify_result
# =========================
def load_flat_matrix(path, rows, cols):
    flat = np.loadtxt(path, dtype=np.int64)
    return flat[:rows * cols].reshape(rows, cols)

def verify_square(mat_size, zr):
    PYTHON_DIR = Path(__file__).parent
    file_a    = PYTHON_DIR / f"input_matrix/matrix_{mat_size}_{zr}_1.txt"
    file_b    = PYTHON_DIR / f"input_matrix/matrix_{mat_size}_{zr}_2.txt"
    hw_result = PYTHON_DIR / f"hw_result/output_matrix_{mat_size}_{zr}.txt"

    for f in [file_a, file_b, hw_result]:
        if not f.exists():
            print(f"[ERROR] File not found: {f}")
            return False

    mat_a    = load_flat_matrix(file_a, mat_size, mat_size)
    mat_b    = load_flat_matrix(file_b, mat_size, mat_size)
    hw_c     = load_flat_matrix(hw_result, mat_size, mat_size)
    golden_c = np.matmul(mat_a.astype(np.int64), mat_b.astype(np.int64))

    print("=" * 52)
    print(f"  ZR={zr}%  |  Matrix: {mat_size}x{mat_size}")
    print(f"  Input A   : {file_a.name}")
    print(f"  Input B   : {file_b.name}")
    print(f"  HW Result : {hw_result.name}")
    print("=" * 52)

    mismatch = np.argwhere(hw_c != golden_c)
    if len(mismatch) == 0:
        print(f"  [PASS] All {mat_size*mat_size} elements match!")
    else:
        print(f"  [FAIL] {len(mismatch)} mismatch(es) found:")
        for idx in mismatch:
            i, j = idx
            print(f"    [{i:2d}][{j:2d}]  Expected: {golden_c[i,j]:8d}  Got: {hw_c[i,j]:8d}")
    print()
    return len(mismatch) == 0

def verify_rect(label, zr):
    PYTHON_DIR = Path(__file__).parent
    parts = label.split("x")
    M, K, N = int(parts[0]), int(parts[1]), int(parts[2])

    file_a    = PYTHON_DIR / f"input_matrix/matrix_a_{M}x{K}_{zr}_1.txt"
    file_b    = PYTHON_DIR / f"input_matrix/matrix_b_{K}x{N}_{zr}_1.txt"
    hw_result = PYTHON_DIR / f"hw_result/output_matrix_{label}_{zr}.txt"

    for f in [file_a, file_b, hw_result]:
        if not f.exists():
            print(f"[ERROR] File not found: {f}")
            return False

    mat_a    = load_flat_matrix(file_a, M, K)
    mat_b    = load_flat_matrix(file_b, K, N)
    hw_c     = load_flat_matrix(hw_result, M, N)
    golden_c = np.matmul(mat_a.astype(np.int64), mat_b.astype(np.int64)) % 65536

    print("=" * 57)
    print(f"  ZR={zr}%  |  Matrix: A({M}x{K}) × B({K}x{N}) = C({M}x{N})")
    print(f"  Input A   : {file_a.name}")
    print(f"  Input B   : {file_b.name}")
    print(f"  HW Result : {hw_result.name}")
    print("=" * 57)

    mismatch = np.argwhere(hw_c != golden_c)
    if len(mismatch) == 0:
        print(f"  [PASS] All {M * N} elements match!")
    else:
        print(f"  [FAIL] {len(mismatch)} mismatch(es) found:")
        for idx in mismatch:
            i, j = idx
            print(f"    [{i:2d}][{j:2d}]  Expected: {golden_c[i,j]:8d}  Got: {hw_c[i,j]:8d}")
    print()
    return len(mismatch) == 0

def verify_result(label_arg, int_ratios):
    rect_mode = "x" in str(label_arg)
    all_pass = True

    if rect_mode:
        for zr in int_ratios:
            if not verify_rect(str(label_arg), zr):
                all_pass = False
    else:
        mat_size = int(label_arg)
        for zr in int_ratios:
            if not verify_square(mat_size, zr):
                all_pass = False

    print("=" * 57)
    print("  [ALL PASS]" if all_pass else "  [SOME FAILED]")
    print("=" * 57)

# =========================
# plot_all
# =========================
def plot_all():
    PLOT_DIR = os.path.dirname(os.path.abspath(__file__))

    DISPLAY_NAMES = {
        "non_sparse":  "NonSparse",
        "sparse":      "Sparse",
        "sparse3FSM":  "Sparse 3FSM",
    }

    model_data = {}

    for file in os.listdir(PLOT_DIR):
        if file.endswith(".txt"):
            model_key = file.replace(".txt", "")
            if model_key not in DISPLAY_NAMES:
                continue

            path = os.path.join(PLOT_DIR, file)
            ratios = []
            latencies = []

            with open(path, "r") as f:
                for line in f:
                    r, l = line.strip().split(",")
                    ratios.append(int(r))
                    latencies.append(int(l))

            model_data[model_key] = (ratios, latencies)

    ORDER = ["non_sparse", "sparse", "sparse3FSM"]
    models = [m for m in ORDER if m in model_data]
    
    if not models:
        print("[WARNING] No valid data found for plot_all")
        return

    ratios = sorted(set.intersection(*[set(model_data[m][0]) for m in models]))

    latency_map = {}
    for model in models:
        r_list, l_list = model_data[model]
        temp = {r: l for r, l in zip(r_list, l_list)}
        latency_map[model] = [temp[r] for r in ratios]

    x = np.arange(len(ratios))  # ZR 개수
    width = 0.25               # 막대 너비

    plt.figure(figsize=(10, 6))

    for i, model in enumerate(models):
        plt.bar(x + i*width, latency_map[model], width, label=DISPLAY_NAMES[model])

    # x축 위치 중앙 정렬
    plt.xticks(x + width*(len(models)-1)/2, [f"{r}%" for r in ratios])

    plt.xlabel("Zero Ratio (%)", fontsize=12)
    plt.ylabel("Latency (clock cycles)", fontsize=12)
    plt.title("Latency Comparison Across Models", fontsize=14, fontweight='bold')

    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    # 값 표시
    for i, model in enumerate(models):
        for j, val in enumerate(latency_map[model]):
            plt.text(x[j] + i*width, val, str(val),
                     ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.show()


# =========================
# plot_each
# =========================
def extract_latency(log_file):
    with open(log_file, "r") as f:
        for line in f:
            match = re.search(r"Latency:\s+\d+\s+\((\d+)\s+clock cycles\)", line)
            if match:
                return int(match.group(1))
    return None

def plot_each(ratios_input):
    PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_DIR = os.path.join(PYTHON_DIR, "sim_logs")

    results = {}

    for ratio in ratios_input:
        if platform.system() == "Windows":
            pattern = os.path.join(LOG_DIR, f"sim_*_{ratio}.log")
        else:
            pattern = os.path.join(LOG_DIR, f"xsim_*_{ratio}.log")
        files = glob.glob(pattern)

        if not files:
            print(f"[WARNING] Missing log for ZR={ratio}")
            continue

        # 최신 로그 선택
        log_file = max(files, key=os.path.getmtime)
        latency = extract_latency(log_file)

        if latency is not None:
            results[ratio] = latency

    ratios = sorted(results.keys())
    
    if not ratios:
        print("[WARNING] No latencies found for plot_each")
        return
        
    latencies = [results[r] for r in ratios]

    print("\n[RESULT]")
    for r, l in zip(ratios, latencies):
        print(f"ZR={r}% → Latency={l}")

    plt.figure()

    plt.bar([str(r) for r in ratios], latencies)

    plt.xlabel("Zero Ratio (%)")
    plt.ylabel("Latency (clock cycles)")
    plt.title("Latency vs Zero Ratio")

    for i, v in enumerate(latencies):
        plt.text(i, v, str(v), ha='center', va='bottom')

    plt.grid(axis='y')

    plt.show()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python validate.py all")
        print("  python validate.py each <ZERO_RATIOS>")
        print("    ex) python validate.py each 0.1,0.5")
        print("  python validate.py verify <LABEL_OR_SIZE> <ZERO_RATIOS>")
        print("    ex) python validate.py verify 32 0.0,0.1,0.8")
        sys.exit(1)

    mode = sys.argv[1]
    
    if mode == "all":
        plot_all()
    elif mode == "each":
        if len(sys.argv) != 3:
            print("Usage: python validate.py each <ZERO_RATIOS>")
            sys.exit(1)
        ratios_input = [round(float(x) * 100) for x in sys.argv[2].split(",")]
        plot_each(ratios_input)
    elif mode == "verify":
        if len(sys.argv) != 4:
            print("Usage: python validate.py verify <LABEL_OR_SIZE> <ZERO_RATIOS>")
            sys.exit(1)
        label_arg = sys.argv[2]
        ratios_raw = [float(x) for x in sys.argv[3].split(",")]
        ratios_input = [int(r * 100) if r <= 1.0 else int(r) for r in ratios_raw]
        verify_result(label_arg, ratios_input)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
