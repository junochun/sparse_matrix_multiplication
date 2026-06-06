import os
import glob
import subprocess

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
RTL_DIR = os.path.normpath(os.path.join(SIM_DIR, "../RTL"))
TB_DIR  = os.path.normpath(os.path.join(SIM_DIR, "../TESTBENCH"))

BIN = r"C:\Xilinx\2025.1\Vivado\bin"

XVLOG = os.path.join(BIN, "xvlog.bat")
XELAB = os.path.join(BIN, "xelab.bat")
XSIM  = os.path.join(BIN, "xsim.bat")

FLIST = os.path.join(SIM_DIR, "flist.f")

# =========================
# Auto-generate flist.f
# =========================
print("[INFO] Generating flist.f...")

rtl_files = sorted(
    glob.glob(os.path.join(RTL_DIR, "*.v")) +
    glob.glob(os.path.join(RTL_DIR, "*.sv"))
)
tb_files = sorted(
    glob.glob(os.path.join(TB_DIR, "*.v")) +
    glob.glob(os.path.join(TB_DIR, "*.sv"))
)

with open(FLIST, "w") as f:
    f.write("# RTL\n")
    for path in rtl_files:
        f.write(f"../RTL/{os.path.basename(path)}\n")
    f.write("\n# TESTBENCH\n")
    for path in tb_files:
        f.write(f"../TESTBENCH/{os.path.basename(path)}\n")

print("[INFO] flist.f generated:")
with open(FLIST) as f:
    print(f.read())

print("[INFO] Running XSIM flow...")

# =========================
# Compile
# =========================
subprocess.run(
    f'"{XVLOG}" -sv -f "{FLIST}"',
    cwd=SIM_DIR,
    shell=True,
    check=True
)

# =========================
# Elaborate
# =========================
subprocess.run(
    f'"{XELAB}" tb_dig_top -s sim_snap',
    cwd=SIM_DIR,
    shell=True,
    check=True
)

# =========================
# Simulate
# =========================
subprocess.run(
    f'"{XSIM}" sim_snap -runall',
    cwd=SIM_DIR,
    shell=True,
    check=True
)

print("[INFO] Simulation complete")