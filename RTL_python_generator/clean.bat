@echo off
set DIR=%~dp0

echo [INFO] Cleaning simulation outputs in python folder...

rd /s /q "%DIR%python\generated_tb" 2>nul
rd /s /q "%DIR%python\hw_result"    2>nul
rd /s /q "%DIR%python\input_matrix" 2>nul
rd /s /q "%DIR%python\sim_logs"     2>nul
del /q "%DIR%python\*.txt"          2>nul

echo [INFO] Cleaning RTL ^& TESTBENCH folders...

rd /s /q "%DIR%RTL"       2>nul
rd /s /q "%DIR%TESTBENCH" 2>nul

echo [INFO] Cleaning outputs from SIM_windows folders...

rd /s /q "%DIR%SIM_windows\xsim.dir" 2>nul
rd /s /q "%DIR%SIM_windows\output"   2>nul
rd /s /q "%DIR%SIM_windows\logs"     2>nul
rd /s /q "%DIR%SIM_windows\.Xil"     2>nul

del /q "%DIR%SIM_windows\xsim.jou"       2>nul
del /q "%DIR%SIM_windows\xsim.log"       2>nul
del /q "%DIR%SIM_windows\vivado.jou"     2>nul
del /q "%DIR%SIM_windows\vivado.log"     2>nul
del /q "%DIR%SIM_windows\xvlog.log"      2>nul
del /q "%DIR%SIM_windows\xvlog.pb"       2>nul
del /q "%DIR%SIM_windows\xelab.log"      2>nul
del /q "%DIR%SIM_windows\xelab.pb"       2>nul
del /q "%DIR%SIM_windows\webtalk.log"    2>nul
del /q "%DIR%SIM_windows\webtalk.jou"    2>nul
del /q "%DIR%SIM_windows\webtalk_*.log"  2>nul
del /q "%DIR%SIM_windows\hs_err_pid*.log" 2>nul
del /q "%DIR%SIM_windows\*.wdb"          2>nul
del /q "%DIR%SIM_windows\*.vcd"          2>nul
del /q "%DIR%SIM_windows\*.str"          2>nul
del /q "%DIR%SIM_windows\*.zip"          2>nul
del /q "%DIR%SIM_windows\flist.f"        2>nul
del /q "%DIR%SIM_windows\*.backup.jou"   2>nul

echo [INFO] Done.
