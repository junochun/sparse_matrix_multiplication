#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Cleaning simulation outputs in python folder..."

rm -rf ./python/generated_tb
rm -rf ./python/hw_result
rm -rf ./python/input_matrix
rm -rf ./python/sim_logs
rm -rf ./python/*.txt

echo "[INFO] Cleaning RTL & TESTBENCH folders..."
rm -rf RTL
rm -rf TESTBENCH


echo "[INFO] Cleaning outputs from SIM folders..."

rm -rf \
  ./SIM/xsim.dir \
  ./SIM/output \
  ./SIM/logs \
  ./SIM/.Xil

rm -f \
  ./SIM/xsim.jou ./SIM/xsim.log ./SIM/vivado.jou ./SIM/vivado.log \
  ./SIM/xvlog.log ./SIM/xvlog.pb \
  ./SIM/xelab.log ./SIM/xelab.pb \
  ./SIM/webtalk.log ./SIM/webtalk.jou ./SIM/webtalk_*.log \
  ./SIM/hs_err_pid*.log \
  ./SIM/*.wdb ./SIM/*.vcd \
  ./SIM/*.str \
  ./SIM/*.zip

rm -f ./SIM/flist.f
rm -f ./SIM/*.backup.jou


echo "[INFO] Done."
