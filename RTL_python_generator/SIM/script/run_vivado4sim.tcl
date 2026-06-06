# run_vivado4sim.tcl
# Usage:
#   vivado -mode batch -source run_vivado4sim.tcl

# -----------------------------
# Settings
# -----------------------------
set TB_TOP   "tb_dig_top"    ;# testbench top module name



set SNAP     "sim_snap"
set FLIST    "flist.f"

set OUT_DIR  "./output"  

set WDB_PATH "$OUT_DIR/wave.wdb"
set VCD_PATH "$OUT_DIR/wave.vcd"
set SIM_LOG  "$OUT_DIR/xsim.log"

# wdb2vcd.tcl이 VCD 경로를 받도록 환경변수로 전달
set ::env(VCD_PATH) $VCD_PATH

# -----------------------------
# Compile
# -----------------------------
puts "==> [clock format [clock seconds]] Compile (xvlog) using $FLIST"
exec xvlog -sv -f $FLIST -log "$OUT_DIR/xvlog.log"

# -----------------------------
# Elaborate
# -----------------------------
puts "==> [clock format [clock seconds]] Elaborate (xelab) top=$TB_TOP snapshot=$SNAP"
exec xelab $TB_TOP -s $SNAP --debug typical -log "$OUT_DIR/xelab.log"

# -----------------------------
# Run (xsim) using fixed tcl script
# -----------------------------
puts "==> [clock format [clock seconds]] Run (xsim) log=$SIM_LOG"
# 고정 스크립트 파일을 그대로 사용
exec xsim $SNAP -tclbatch ./script/wdb2vcd.tcl -wdb $WDB_PATH -log $SIM_LOG

puts "==> DONE"
puts "    WDB: $WDB_PATH"
puts "    VCD: $VCD_PATH"
puts "    LOG: $SIM_LOG"