#!/usr/bin/env bash
# gen_flist.sh: RTL/TESTBENCH 폴더를 스캔해서 flist.f 자동 생성
# SIM 디렉토리에서 실행되는 것을 전제로 함

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIM_DIR="$(dirname "$SCRIPT_DIR")"

RTL_DIR="$SIM_DIR/../RTL"
TB_DIR="$SIM_DIR/../TESTBENCH"
OUT="$SIM_DIR/flist.f"

{
  echo "# RTL"
  find "$RTL_DIR" -name "*.v" -o -name "*.sv" | sort | while read -r f; do
    echo "../RTL/$(basename "$f")"
  done

  echo ""
  echo "# TESTBENCH"
  find "$TB_DIR" -name "*.v" -o -name "*.sv" | sort | while read -r f; do
    echo "../TESTBENCH/$(basename "$f")"
  done
} > "$OUT"

echo "[INFO] flist.f generated:"
cat "$OUT"
