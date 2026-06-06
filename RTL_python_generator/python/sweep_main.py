import os
import re
import glob
import sys
import shutil
import subprocess
import validate_main as validate
import gen_tb_v2
import gen_module

# ── Helpers ───────────────────────────────────────────────────
def collect_and_save_latency(model_key, PYTHON_DIR, int_ratios, IS_WINDOWS, mat_size):
    log_dir = os.path.join(PYTHON_DIR, "sim_logs")
    results = {}
    for ratio in int_ratios:
        if IS_WINDOWS:
            pattern = os.path.join(log_dir, f"sim_{mat_size}_{ratio}.log")
        else:
            pattern = os.path.join(log_dir, f"xsim_{mat_size}_{ratio}.log")
        files = glob.glob(pattern)
        if not files:
            print(f"[WARNING] Missing log for ZR={ratio}")
            continue
        log_file = max(files, key=os.path.getmtime)
        latency = validate.extract_latency(log_file)
        if latency is not None:
            results[ratio] = latency
    if not results:
        print(f"[WARNING] No latency data found for {model_key}")
        return
    out_path = os.path.join(PYTHON_DIR, f"{model_key}.txt")
    with open(out_path, "w") as f:
        for ratio, latency in sorted(results.items()):
            f.write(f"{ratio},{latency}\n")
    print(f"[Saved] {out_path}")


def execute(choice, PYTHON, PYTHON_DIR, IS_WINDOWS,
            mat_size, sa_size, m_size, k_size, n_size,
            int_ratios, ratios_float_str, ratios_int_str):
    """Execute the selected pipeline based on user's choice."""

    # ── Model definitions ───────────────────────────────────────────────────
    GEN_FUNCS = {
        "non_sparse":  gen_module.generate_nonsparse_module,
        "sparse":      gen_module.generate_sparse_module,
        "sparse3FSM":  gen_module.generate_sparse3FSM_module,
    }

    # ── Inner helpers (closures — no extra params needed) ─────────
    def run(step, cmd, cwd=None):
        print(f"\n{'='*50}")
        print(f"[{step}] {' '.join(cmd)}")
        print(f"{'='*50}")
        result = subprocess.run(cmd, cwd=cwd or PYTHON_DIR)
        if result.returncode != 0:
            print(f"[ERROR] {step} failed.")
            sys.exit(result.returncode)

    def run_pipeline(model_key, final_plot=True):
        print(f"\n{'#'*60}")
        print(f"# Pipeline: {model_key}")
        print(f"{'#'*60}")

        gen_dir = os.path.join(PYTHON_DIR, "generated_tb")
        log_dir = os.path.join(PYTHON_DIR, "sim_logs")
        hw_dir  = os.path.join(PYTHON_DIR, "hw_result")
        tb_dest = os.path.join(PYTHON_DIR, "../TESTBENCH/tb_dig_top.sv")

        if IS_WINDOWS:
            sim_dir = os.path.join(PYTHON_DIR, "../SIM_windows")
            sim_cmd = [PYTHON, "run_sim.py"]
        else:
            sim_dir = os.path.join(PYTHON_DIR, "../SIM")
            sim_cmd = ["./run_sim"]

        os.makedirs(gen_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(hw_dir,  exist_ok=True)

        # Step 1: Generate input matrices (square: MAT_SIZE x MAT_SIZE)
        run("gen_matrix", [PYTHON, os.path.join(PYTHON_DIR, "gen_matrix.py"),
                           str(mat_size), ratios_float_str])

        # Step 2: Generate RTL (model-specific)
        print(f"\n{'='*50}")
        print(f"[gen_module] Generating RTL for {model_key}...")
        print(f"{'='*50}")
        GEN_FUNCS[model_key](mat_size, sa_size)

        # Step 3: Generate all TB files
        print("\n[Step 3] Generating testbench files...")
        for zr in int_ratios:
            file_a   = f"./../python/input_matrix/matrix_{mat_size}_{zr}_1.txt"
            file_b   = f"./../python/input_matrix/matrix_{mat_size}_{zr}_2.txt"
            file_out = f"./../python/hw_result/output_matrix_{mat_size}_{zr}.txt"
            content = gen_tb_v2.generate_tb(
                data_width=8, acc_width=32,
                mat_size=mat_size, sa_size=sa_size,
                file_a=file_a, file_b=file_b, file_out=file_out,
            )
            os.makedirs(os.path.dirname(tb_dest), exist_ok=True)
            with open(tb_dest, "w", encoding="utf-8") as f:
                f.write(content)
            dst_file = os.path.join(gen_dir, f"tb_dig_top_{mat_size}_{zr}.sv")
            shutil.copy2(tb_dest, dst_file)
            print(f"[OK] Generated: {dst_file}")

        # Step 4: Run simulation for each ZR
        print("\n[Step 4] Starting simulations...")
        DISPLAY_KEYWORDS = ("[INFO]", "[PASS]", "[FAIL]", "[ERROR]", "[WARNING]", "===")
        for zr in int_ratios:
            tb_file  = os.path.join(gen_dir, f"tb_dig_top_{mat_size}_{zr}.sv")
            log_file = os.path.join(log_dir, f"sim_{mat_size}_{zr}.log")
            shutil.copy2(tb_file, tb_dest)
            print(f"\n==============================")
            print(f"[INFO] Running ZR = {zr}")
            print(f"==============================")
            print(f"[INFO] Simulating ZR={zr}... (log: {log_file})")
            with open(log_file, "w") as lf:
                proc = subprocess.Popen(sim_cmd, cwd=sim_dir,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True)
                for line in proc.stdout:
                    lf.write(line)
                    if any(kw in line for kw in DISPLAY_KEYWORDS):
                        print(f"  {line}", end="")
                proc.wait()
            if proc.returncode != 0:
                print(f"[ERROR] Simulation failed at ZR={zr}  (see log: {log_file})")
                sys.exit(proc.returncode)
            xsim_log = os.path.join(sim_dir, "output", "xsim.log")
            xsim_dst = os.path.join(log_dir, f"xsim_{mat_size}_{zr}.log")
            if os.path.exists(xsim_log):
                shutil.copy2(xsim_log, xsim_dst)
                print(f"[OK] ZR={zr} done (xsim log: {xsim_dst})")
            else:
                print(f"[OK] ZR={zr} done")

        # Step 5: Verify results
        print(f"\n{'='*50}")
        print(f"[verify_result] Verifying outputs...")
        print(f"{'='*50}")
        validate.verify_result(str(mat_size), int_ratios)

        # Step 6: Plot (individual model)
        if final_plot:
            print(f"\n{'='*50}")
            print(f"[plot_each] Running validate.plot_each...")
            print(f"{'='*50}")
            validate.plot_each(int_ratios)

    def run_pipeline_final():
        """Pipeline for choice 5: sparse3FSM final with rectangular matrix support."""
        print(f"\n{'#'*60}")
        print(f"# Pipeline: sparse3FSM_final  ({m_size}x{k_size} × {k_size}x{n_size})")
        print(f"{'#'*60}")

        label   = f"{m_size}x{k_size}x{n_size}"
        gen_dir = os.path.join(PYTHON_DIR, "generated_tb")
        log_dir = os.path.join(PYTHON_DIR, "sim_logs")
        hw_dir  = os.path.join(PYTHON_DIR, "hw_result")
        tb_dest = os.path.join(PYTHON_DIR, "../TESTBENCH/tb_dig_top.sv")

        if IS_WINDOWS:
            sim_dir = os.path.join(PYTHON_DIR, "../SIM_windows")
            sim_cmd = [PYTHON, "run_sim.py"]
        else:
            sim_dir = os.path.join(PYTHON_DIR, "../SIM")
            sim_cmd = ["./run_sim"]

        os.makedirs(gen_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(hw_dir,  exist_ok=True)

        # Step 1: Generate rectangular input matrices (M×K and K×N)
        run("gen_matrix", [PYTHON, os.path.join(PYTHON_DIR, "gen_matrix.py"),
                           str(m_size), str(k_size), str(n_size), ratios_float_str])

        # Step 2: Generate RTL (M K N SA)
        print(f"\n{'='*50}")
        print(f"[gen_module] Generating RTL for sparse3FSM_final...")
        print(f"{'='*50}")
        gen_module.generate_final_module(m_size, k_size, n_size, sa_size)

        DISPLAY_KEYWORDS = ("[INFO]", "[PASS]", "[FAIL]", "[ERROR]", "[WARNING]", "===")

        # Step 3: Generate all TB files
        print("\n[Step 3] Generating testbench files...")
        for zr in int_ratios:
            file_a   = f"./../python/input_matrix/matrix_a_{m_size}x{k_size}_{zr}_1.txt"
            file_b   = f"./../python/input_matrix/matrix_b_{k_size}x{n_size}_{zr}_1.txt"
            file_out = f"./../python/hw_result/output_matrix_{label}_{zr}.txt"
            content = gen_tb_v2.generate_tb_final(
                data_width=8, acc_width=32,
                m_size=m_size, k_size=k_size, n_size=n_size, sa_size=sa_size,
                file_a=file_a, file_b=file_b, file_out=file_out,
            )
            os.makedirs(os.path.dirname(tb_dest), exist_ok=True)
            with open(tb_dest, "w", encoding="utf-8") as f:
                f.write(content)
            dst_file = os.path.join(gen_dir, f"tb_dig_top_{label}_{zr}.sv")
            shutil.copy2(tb_dest, dst_file)
            print(f"[OK] Saved: {dst_file}")

        # Run simulation for each ZR
        print("\nStarting simulations...")
        for zr in int_ratios:
            tb_file = os.path.join(gen_dir, f"tb_dig_top_{label}_{zr}.sv")
            shutil.copy2(tb_file, tb_dest)

            log_file = os.path.join(log_dir, f"sim_{label}_{zr}.log")
            print(f"\n==============================")
            print(f"[INFO] Running ZR = {zr}")
            print(f"==============================")
            print(f"[INFO] Simulating ZR={zr}... (log: {log_file})")

            with open(log_file, "w") as lf:
                proc = subprocess.Popen(sim_cmd, cwd=sim_dir,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True)
                for line in proc.stdout:
                    lf.write(line)
                    if any(kw in line for kw in DISPLAY_KEYWORDS):
                        print(f"  {line}", end="")
                proc.wait()

            if proc.returncode != 0:
                print(f"[ERROR] Simulation failed at ZR={zr}  (see log: {log_file})")
                sys.exit(proc.returncode)

            xsim_log = os.path.join(sim_dir, "output", "xsim.log")
            xsim_dst = os.path.join(log_dir, f"xsim_{label}_{zr}.log")
            if os.path.exists(xsim_log):
                shutil.copy2(xsim_log, xsim_dst)
                print(f"[OK] ZR={zr} done (xsim log: {xsim_dst})")
            else:
                print(f"[OK] ZR={zr} done")

        # Step 4: Verify results
        print(f"\n{'='*50}")
        print(f"[verify_result] Verifying outputs...")
        print(f"{'='*50}")
        validate.verify_result(label, int_ratios)

        # Step 5: Plot
        print(f"\n{'='*50}")
        print(f"[plot_each] Running validate.plot_each...")
        print(f"{'='*50}")
        validate.plot_each(int_ratios)

    # ── Execute based on choice ───────────────────────────────────
    if choice == "1":
        run_pipeline("non_sparse")

    elif choice == "2":
        run_pipeline("sparse")

    elif choice == "3":
        run_pipeline("sparse3FSM")

    elif choice == "4":
        for model_key in ("non_sparse", "sparse", "sparse3FSM"):
            run_pipeline(model_key, final_plot=False)
            collect_and_save_latency(model_key, PYTHON_DIR, int_ratios,
                                     IS_WINDOWS, mat_size)
        
        print(f"\n{'='*50}")
        print(f"[plot_all] Running validate.plot_all...")
        print(f"{'='*50}")
        validate.plot_all()

    elif choice == "5":
        run_pipeline_final()
