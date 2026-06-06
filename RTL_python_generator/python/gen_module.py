"""
gen_module.py
=============
High-level RTL generation entry points called by sweep_main.py.

Each function generates a complete set of SystemVerilog source files for one
hardware configuration and writes them to OUT_DIR (default: ../RTL relative to
this file).  Change OUT_DIR below if your project layout is different.

  generate_nonsparse_module(mat_size, sa_size)   -> choice 1
  generate_sparse_module(mat_size, sa_size)       -> choice 2
  generate_sparse3FSM_module(mat_size, sa_size)   -> choice 3
  generate_final_module(m_size, k_size, n_size, sa_size) -> choice 5
"""

from pathlib import Path
import rtl_module as rtl

OUT_DIR = Path("./../RTL")
OUT_DIR.mkdir(exist_ok=True)

def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Choice 1 : non-sparse (no gating, no skip logic)
# ─────────────────────────────────────────────────────────────────────────────
def generate_nonsparse_module(mat_size: int, sa_size: int) -> None:
    if mat_size % sa_size != 0:
        raise ValueError("MAT_SIZE must be divisible by SA_SIZE")

    sa_top_name = rtl.sa_top_mod_name(sa_size)
    sa_name     = rtl.sa_mod_name(sa_size)

    print(f"[gen_module] non_sparse  {mat_size}x{mat_size}  SA={sa_size}x{sa_size}")
    write_text(OUT_DIR / "dig_top.sv",             rtl.gen_dig_top(mat_size, sa_size))
    write_text(OUT_DIR / "memory_top.sv",          rtl.gen_memory_top(mat_size, sa_size))
    write_text(OUT_DIR / "accelerator_top.sv",     rtl.gen_accelerator_top_non_sparse(mat_size, sa_size))
    write_text(OUT_DIR / f"{sa_top_name}.sv",      rtl.gen_sa_top_non_sparse(sa_size))
    write_text(OUT_DIR / f"{sa_name}.sv",          rtl.gen_sa_core_non_sparse(sa_size))
    write_text(OUT_DIR / "single_PE.sv",           rtl.gen_single_pe_non_sparse())
    write_text(OUT_DIR / "BRAM_A.sv",              rtl.gen_bram_a(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_B.sv",              rtl.gen_bram_b(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_C.sv",              rtl.gen_bram_c(mat_size, sa_size))
    write_text(OUT_DIR / "sa_controller.sv",       rtl.gen_sa_controller_non_sparse(mat_size, sa_size))


# ─────────────────────────────────────────────────────────────────────────────
# Choice 2 : sparse (PE-level valid/ready handshake, no 3-FSM)
# ─────────────────────────────────────────────────────────────────────────────
def generate_sparse_module(mat_size: int, sa_size: int) -> None:
    if mat_size % sa_size != 0:
        raise ValueError("MAT_SIZE must be divisible by SA_SIZE")

    sa_top_name = rtl.sa_top_mod_name(sa_size)
    sa_name     = rtl.sa_mod_name(sa_size)

    print(f"[gen_module] sparse  {mat_size}x{mat_size}  SA={sa_size}x{sa_size}")
    write_text(OUT_DIR / "dig_top.sv",             rtl.gen_dig_top(mat_size, sa_size))
    write_text(OUT_DIR / "memory_top.sv",          rtl.gen_memory_top(mat_size, sa_size))
    write_text(OUT_DIR / "accelerator_top.sv",     rtl.gen_accelerator_top_sparse(mat_size, sa_size))
    write_text(OUT_DIR / f"{sa_top_name}.sv",      rtl.gen_sa_top_sparse(sa_size))
    write_text(OUT_DIR / f"{sa_name}.sv",          rtl.gen_sa_core_sparse(sa_size))
    write_text(OUT_DIR / "sparse_single_PE.sv",    rtl.gen_single_pe_sparse(sa_size))
    write_text(OUT_DIR / "BRAM_A.sv",              rtl.gen_bram_a(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_B.sv",              rtl.gen_bram_b(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_C.sv",              rtl.gen_bram_c(mat_size, sa_size))
    write_text(OUT_DIR / "sa_controller.sv",       rtl.gen_sa_controller_sparse(mat_size, sa_size))


# ─────────────────────────────────────────────────────────────────────────────
# Choice 3 : sparse with 3-state FSM controller
# ─────────────────────────────────────────────────────────────────────────────
def generate_sparse3FSM_module(mat_size: int, sa_size: int) -> None:
    if mat_size % sa_size != 0:
        raise ValueError("MAT_SIZE must be divisible by SA_SIZE")

    sa_top_name = rtl.sa_top_mod_name(sa_size)
    sa_name     = rtl.sa_mod_name(sa_size)

    print(f"[gen_module] sparse3FSM  {mat_size}x{mat_size}  SA={sa_size}x{sa_size}")
    write_text(OUT_DIR / "dig_top.sv",             rtl.gen_dig_top(mat_size, sa_size))
    write_text(OUT_DIR / "memory_top.sv",          rtl.gen_memory_top(mat_size, sa_size))
    write_text(OUT_DIR / "accelerator_top.sv",     rtl.gen_accelerator_top_sparse(mat_size, sa_size))
    write_text(OUT_DIR / f"{sa_top_name}.sv",      rtl.gen_sa_top_sparse(sa_size))
    write_text(OUT_DIR / f"{sa_name}.sv",          rtl.gen_sa_core_sparse(sa_size))
    write_text(OUT_DIR / "sparse_single_PE.sv",    rtl.gen_single_pe_sparse(sa_size))
    write_text(OUT_DIR / "BRAM_A.sv",              rtl.gen_bram_a(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_B.sv",              rtl.gen_bram_b(mat_size, sa_size))
    write_text(OUT_DIR / "BRAM_C.sv",              rtl.gen_bram_c(mat_size, sa_size))
    write_text(OUT_DIR / "sa_controller.sv",       rtl.gen_sa_controller_sparse_3FSM(mat_size, sa_size))


# ─────────────────────────────────────────────────────────────────────────────
# Choice 5 : final  (rectangular M×K × K×N, clock-gated PE, accumulator bank,
#                    activation unit, norm/pool)
# ─────────────────────────────────────────────────────────────────────────────
def generate_final_module(m_size: int, k_size: int, n_size: int, sa_size: int) -> None:
    sa_top_name = rtl.sa_top_mod_name(sa_size)
    sa_name     = rtl.sa_mod_name(sa_size)

    print(f"[gen_module] sparse3FSM_final  {m_size}x{k_size}x{n_size}  SA={sa_size}x{sa_size}")
    write_text(OUT_DIR / "dig_top.sv",             rtl.gen_dig_top_final(m_size, k_size, n_size, sa_size))
    write_text(OUT_DIR / "memory_top.sv",          rtl.gen_memory_top_final(m_size, k_size, n_size, sa_size))
    write_text(OUT_DIR / "accelerator_top.sv",     rtl.gen_accelerator_top_final(m_size, k_size, n_size, sa_size))
    write_text(OUT_DIR / f"{sa_top_name}.sv",      rtl.gen_sa_top_final(sa_size))
    write_text(OUT_DIR / f"{sa_name}.sv",          rtl.gen_sa_core_final(sa_size))
    write_text(OUT_DIR / "sparse_single_PE.sv",    rtl.gen_single_pe_final(sa_size))
    write_text(OUT_DIR / "SRAM_AB.sv",             rtl.gen_sram_ab_final(m_size, k_size, n_size, sa_size))
    write_text(OUT_DIR / "SRAM_C.sv",              rtl.gen_sram_c_final(m_size, n_size, sa_size))
    write_text(OUT_DIR / "sa_controller.sv",       rtl.gen_sa_controller_final(m_size, k_size, n_size, sa_size))
    write_text(OUT_DIR / "accumulator_bank.sv",    rtl.gen_accumulator_bank(sa_size))
    write_text(OUT_DIR / "activation_unit.sv",     rtl.gen_activation_unit(sa_size))
    write_text(OUT_DIR / "norm_pool.sv",           rtl.gen_norm_pool(sa_size))

