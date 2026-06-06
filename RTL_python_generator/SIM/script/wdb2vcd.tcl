# xsim -tclbatch 로 실행되는 스크립트
# run_vivado4sim.tcl에서 env(VCD_PATH)를 넘겨주면 그 위치로 VCD 생성

if {[info exists ::env(VCD_PATH)] && $::env(VCD_PATH) ne ""} {
  set vcd_path $::env(VCD_PATH)
} else {
  set vcd_path "./output/wave.vcd"
}

puts "INFO: VCD will be written to: $vcd_path"

open_vcd $vcd_path
log_vcd /*
run all
close_vcd
quit
