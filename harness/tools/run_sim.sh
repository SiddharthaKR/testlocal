#!/usr/bin/env bash
# run_sim.sh <tb.v> <src.v...>
# Compile with iverilog -g2012 and run with vvp. Prints a summary of at most
# 40 lines; full logs go to sim_logs/compile.log and sim_logs/sim.log.
# Exit: 0 ok, 1 compile error, 2 simulation error ($fatal, or a line with FAIL/ERROR).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

[ $# -ge 1 ] || { echo "usage: run_sim.sh <tb.v> <src.v...>"; exit 64; }
LOG=sim_logs; mkdir -p "$LOG"

"$IVERILOG" -g2012 -o sim.out "$@" > "$LOG/compile.log" 2>&1
if [ $? -ne 0 ]; then
  echo "COMPILE: FAIL  (full log: $LOG/compile.log)"
  grep -iE "error|syntax|not found" "$LOG/compile.log" | head -n 15 | grep . || tail -n 15 "$LOG/compile.log"
  exit 1
fi
nwarn=$(grep -ci warning "$LOG/compile.log")
echo "COMPILE: OK  ($nwarn warnings, see $LOG/compile.log)"

"$VVP" -n sim.out > "$LOG/sim.log" 2>&1
rc=$?
nfail=$(grep -cE "FAIL|ERROR|FATAL|MISMATCH" "$LOG/sim.log")
if [ $rc -ne 0 ] || [ "$nfail" -gt 0 ]; then status=FAIL; else status=OK; fi
echo "SIM: $status  (vvp exit $rc, $(wc -l < "$LOG/sim.log") log lines, $nfail FAIL/ERROR lines; full log: $LOG/sim.log)"

if [ "$nfail" -gt 0 ]; then
  echo "--- first FAIL/ERROR lines:"
  grep -m 10 -E "FAIL|ERROR|FATAL|MISMATCH" "$LOG/sim.log"
fi
echo "--- last lines:"
tail -n 15 "$LOG/sim.log"
csv=$(ls -t *.csv 2>/dev/null | head -n 3 | tr '\n' ' ')
[ -n "$csv" ] && echo "CSV files: $csv"
[ "$status" = OK ] || exit 2
