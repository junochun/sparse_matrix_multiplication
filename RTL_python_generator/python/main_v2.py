import os

from sweep_main import execute
from sel_model_main import os_detection, model_selection

# =========================
# Usage:
#   macOS:   python3 main_v2.py
#   Windows: python  main_v2.py
#
# All parameters are entered interactively.
# Choice 6 (sparse3FSM final) accepts M_SIZE, K_SIZE, N_SIZE separately
# to support rectangular matrix multiplication.
# =========================

# ── Detect OS ─────────────────────────────────────────────────
IS_WINDOWS, PYTHON = os_detection()

# ── Model selection & input parameters ────────────────────────
(choice, mat_size, sa_size, m_size, k_size, n_size,
 float_ratios, int_ratios, ratios_float_str, ratios_int_str) = model_selection()

# ── Path resolution ───────────────────────────────────────────
PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Execute pipeline ──────────────────────────────────────────
execute(choice, PYTHON, PYTHON_DIR, IS_WINDOWS,
        mat_size, sa_size, m_size, k_size, n_size,
        int_ratios, ratios_float_str, ratios_int_str)

print("\n[Done] All pipelines complete.")
