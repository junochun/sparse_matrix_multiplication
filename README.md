# Sparse Systolic Array Matrix Multiplication Accelerator
> This is the source code for sparse matrix multiplication HW. This repo includes python auto generation codes for RTL and RTL simulator 
> Bitvector (BV)-based Zero-Skip Sparse Matrix Multiplication Accelerator — RTL Design · FPGA Verification

---

## Project Overview
 
This project implements a **Bitvector-based Zero-Skip accelerator** that skips unnecessary MAC operations involving zero values in **sparse matrix multiplication**.
 
Inspired by the Google TPU v1 (ISCA 2017) Systolic Array architecture, we implement a fully parameterizable Systolic Array based on a **4×4 PE (Processing Element) array** and verify it on a Zynq-7000 FPGA via AXI4-Lite interface.
 
### Key Contributions
 
- **BV Zero-Skip Mechanism**: Selectively executes only valid MACs using `bv_a & bv_b` AND logic
- **Fully Parameterizable Design**: Supports arbitrary SA size (N×N) — a key differentiating contribution in the paper
- **FPGA Verification**: Functional verification on Zynq-7000 via AXI4-Lite interface
- **Cycle-Accurate Simulator**: Python simulator validated within ~1–2% error against RTL measurements

---
 
## Repository Structure
 
```
sparse_matrix_multiplication/
│
├── AXI_to_RTL_for_FPGA/                        # FPGA implementation (Zynq-7000, AXI4-Lite)
│   ├── RTL/
│   │   ├── AXI_to_RTL.v                        # AXI4-Lite top-level wrapper
│   │   ├── AXI_to_RTL_slave_full_v1_0_S00_AXI.sv  # AXI4-Lite slave interface
│   │   ├── SA_16x16.sv                         # 16×16 Systolic Array
│   │   ├── SA_16x16_TOP.sv                     # SA top with BV zero-skip control
│   │   ├── SRAM_AB.sv                          # Input matrix SRAM (A, B)
│   │   ├── SRAM_C.sv                           # Output matrix SRAM (C)
│   │   ├── accelerator_top.sv                  # Accelerator top-level
│   │   ├── accumulator_bank.sv                 # Output accumulation logic
│   │   ├── activation_unit.sv                  # Activation function unit
│   │   ├── dig_top.v                           # Digital top integration
│   │   ├── memory_top.sv                       # Memory subsystem top
│   │   ├── norm_pool.sv                        # Normalization / pooling unit
│   │   ├── sa_controller.sv                    # Systolic Array FSM controller
│   │   └── sparse_single_PE.sv                 # Single PE with BV zero-skip logic
│   └── TESTBENCH/
│       ├── tb_axi_vip.sv                       # AXI VIP-based testbench
│       ├── tb_dig_top.sv                       # Digital top testbench
│       └── tb_vitis.c                          # Vitis C software driver for FPGA test
│
├── RTL_python_generator/                       # Python-driven RTL & simulation generator
│   ├── SIM/
│   │   ├── run_sim                             # Simulation run script (Linux)
│   │   └── script/
│   │       ├── gen_flist.sh                    # File list generator for simulation
│   │       ├── run_vivado4sim.tcl              # Vivado simulation TCL script
│   │       └── wdb2vcd.tcl                     # WDB to VCD waveform converter
│   ├── SIM_windows/
│   │   └── run_sim.py                          # Simulation runner for Windows
│   ├── clean.bat                               # Clean build artifacts (Windows)
│   ├── clean.sh                                # Clean build artifacts (Linux)
│   └── python/
│       ├── gen_matrix.py                       # Test matrix generator
│       ├── gen_module.py                       # RTL module code generator
│       ├── gen_tb_v2.py                        # Testbench generator (v2)
│       ├── main_v2.py                          # Main entry point (v2)
│       ├── rtl_module.py                       # RTL module abstraction class
│       ├── sel_model_main.py                   # Model selection entry point
│       ├── sweep_main.py                       # Parameter sweep runner
│       └── validate_main.py                    # Output validation against golden model
│
└── RTL_simulator/                              # Cycle-accurate Python simulator
    ├── core/
    │   ├── __init__.py
    │   └── sparse_RTL_simulator.py             # Core BV zero-skip cycle simulator
    ├── analysis/
    │   ├── activation_sparsity_analysis.py     # Activation sparsity sweep analysis
    │   ├── baseline_comparison.py              # Baseline comparison (TPU v1, Eyeriss)
    │   ├── format_comparison.py                # Sparse format comparison (BV vs block)
    │   ├── latency_breakdown.py                # Cycle latency breakdown analysis
    │   ├── paper_baseline_comparison.py        # Final paper baseline comparison script
    │   └── paper_baseline_comparison.png       # Output figure for paper
    ├── demo/
    │   └── pygame_MNIST.py                     # Interactive MNIST inference demo
    ├── input_matrix/                           # Pre-generated sparse test matrices
    │   └── matrix_{a,b}_48x48_{20~90}_{1,2}.txt  # Sparsity 20~90%, 2 seeds each
    ├── results/
    │   └── COMPUTE_REPORT.csv                  # Cycle count results across experiments
    ├── topologies/
    │   └── mnist_dnn.csv                       # MNIST DNN layer topology definition
    ├── training/
    │   ├── dnn_trainer.py                      # DNN training script (PyTorch/NumPy)
    │   └── trained_dnn_weights.npz             # Pre-trained MNIST DNN weights
    ├── main_simulator.py                       # Simulator entry point
    └── run_network.py                          # End-to-end network inference runner
```
 
---

## Architecture Overview
 
### Systolic Array with BV Zero-Skip
 
```
Input A (matrix)        Input B (matrix)
    │                       │
[bv_a generation]       [bv_b generation]
    │                       │
    └──── bv_a & bv_b ──────┘
              │
         Zero-Skip?
         ┌────┴────┐
        YES        NO
    (skip cycle)  (MAC executed)
                   │
             Systolic Array
             ┌────┬────┐
             │ PE │ PE │ ...
             ├────┼────┤
             │ PE │ PE │
             └────┴────┘
                   │
             Output C (matrix)
```


- **PE**: Multiply-Accumulate (MAC) unit with pipeline registers
- **Systolic Timing**: Accounts for row skew + horizontal propagation + feed cycles + register stages
- **BRAM**: 1-cycle read latency explicitly managed at FSM state transition boundaries
---
 
## 🔬 Simulation & Verification
 
### Python Cycle-Accurate Simulator
 
```bash
python scripts/sparse_RTL_simulator.py \
  --sa_size 4 \
  --matrix_size 64 \
  --sparsity 0.7
```
 
Validated against RTL simulation results with cycle counts matching within **~1–2% error**.
 
### RTL Simulation (VCS)
 
```bash
cd sim/
bash run_vcs.sh tb_top
# or for a specific testbench
bash run_vcs.sh tb_sa_top
```
 
### RTL Simulation (Vivado XSim)
 
```bash
bash run_xsim.sh tb_top
```
 
### Waveform Analysis (Verdi)
 
```bash
verdi -f filelist.f -ssf wave/dump.fsdb
```
 
---
 
## 📊 Baseline Comparison Experiments
 
Run all baseline comparison experiments via:
 
```bash
python scripts/paper_baseline_comparison.py
```
 
| Experiment | Baseline | SA Size | Peak Speedup |
|------------|----------|---------|--------------|
| Exp 1 | vs TPU v1 | 256×256 | **1.43×** @ 90% sparsity |
| Exp 2 | vs Eyeriss | 14×14 | **1.09×** @ 60% sparsity |
| Exp 3 | Block-size sensitivity | — | Block=32 incurs +10% cycle overhead vs BV |
 
> **Comparison scope**: SA compute cycles only. FSM/BRAM overhead is applied equally to all baselines for fairness. Full-chip comparison with published baselines is methodologically excluded.
 
---
 
## 🖥️ FPGA Verification (Zynq-7000)
 
- **Board**: Zynq-7000 (XC7Z020)
- **Interface**: AXI4-Lite slave
- **Environment**: Vivado (block design) + Vitis (C driver)
- **Verified**: 4×4 PE array functional correctness, matrix multiplication accuracy
```
PS (ARM Cortex-A9)
    │ AXI4-Lite
    ▼
PL (FPGA Fabric)
 ┌──────────────┐
 │  axi_slave   │
 │      │       │
 │  sa_top (4×4)│
 └──────────────┘
```
 
---

## 📄 License

This project was developed for academic purposes as part of the Capstone Design course in the Department of Semiconductor Systems Engineering, Sungkyunkwan University.