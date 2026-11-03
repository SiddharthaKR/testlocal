#!/usr/bin/env bash
# run_equiv.sh [candidate_pid.v] [extra candidate .v ...]
# Small equivalence check of your PID against the original (tasks/B/ref/).
# Default candidate: pyrpl/pyrpl/fpga/rtl/red_pitaya_pid_block.v (+ its filter/lpf).
# Accepts any fixed output latency 0..8 cycles. Prints a short summary; full log in equiv_logs/.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

RTL=pyrpl/pyrpl/fpga/rtl
REF=tasks/B/ref
[ -d "$REF" ] || { echo "run_equiv: $REF not found (Track B only)"; exit 64; }
LOG=equiv_logs; mkdir -p "$LOG/ref"

cand=("$@")
[ ${#cand[@]} -gt 0 ] || cand=("$RTL/red_pitaya_pid_block.v")
for dep in red_pitaya_filter_block.v red_pitaya_lpf_block.v; do
  case " ${cand[*]} " in *"$dep"*) ;; *) cand+=("$RTL/$dep") ;; esac
done

for f in "$REF"/*.v; do
  sed -E 's/\bred_pitaya_(pid_block|filter_block|lpf_block)\b/ref_red_pitaya_\1/g' "$f" > "$LOG/ref/ref_$(basename "$f")"
done

"$IVERILOG" -g2012 -o "$LOG/equiv.out" "$TOOLS_DIR/_equiv_tb.v" "$LOG"/ref/*.v "${cand[@]}" > "$LOG/compile.log" 2>&1 || {
  echo "EQUIV: COMPILE FAIL (full log: $LOG/compile.log)"
  grep -iE "error" "$LOG/compile.log" | head -n 15
  exit 1
}
"$VVP" -n "$LOG/equiv.out" > "$LOG/sim.log" 2>&1
grep -E "EQUIV|first mismatch|READBACK" "$LOG/sim.log" | head -n 12
grep -q "EQUIV PASS" "$LOG/sim.log"
