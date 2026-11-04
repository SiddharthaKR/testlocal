#!/usr/bin/env bash
# run_equiv.sh [candidate.v] [extra candidate .v ...]
# Small equivalence check of your block against the original (tasks/B/ref/).
# The block under test is detected from the original in tasks/B/ref/:
#   red_pitaya_pid_block.v            (+ filter_block, lpf_block)
#   red_pitaya_iq_demodulator_block.v
#   red_pitaya_iq_modulator_block.v   (+ product_sat, saturate)
# Default candidate: pyrpl/pyrpl/fpga/rtl/<block>.v (+ its dependencies from the same folder).
# Accepts any fixed output latency 0..8 cycles. Prints a short summary; full log in equiv_logs/.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

RTL=pyrpl/pyrpl/fpga/rtl
REF=tasks/B/ref
[ -d "$REF" ] || { echo "run_equiv: $REF not found (Track B only)"; exit 64; }
LOG=equiv_logs; mkdir -p "$LOG/ref"; rm -f "$LOG"/ref/*.v

if   [ -f "$REF/red_pitaya_pid_block.v" ]; then
  TOP=red_pitaya_pid_block; TB="$TOOLS_DIR/_equiv_tb.v"
  MODS="pid_block|filter_block|lpf_block"; DEPS="red_pitaya_filter_block.v red_pitaya_lpf_block.v"
elif [ -f "$REF/red_pitaya_iq_demodulator_block.v" ]; then
  TOP=red_pitaya_iq_demodulator_block; TB="$TOOLS_DIR/_equiv_tb_iq_demod.v"
  MODS="iq_demodulator_block"; DEPS=""
elif [ -f "$REF/red_pitaya_iq_modulator_block.v" ]; then
  TOP=red_pitaya_iq_modulator_block; TB="$TOOLS_DIR/_equiv_tb_iq_mod.v"
  MODS="iq_modulator_block|product_sat|saturate"; DEPS="red_pitaya_product_sat.v red_pitaya_saturate.v"
else
  echo "run_equiv: no known original block found in $REF/"; exit 64
fi

cand=("$@")
[ ${#cand[@]} -gt 0 ] || cand=("$RTL/$TOP.v")
for dep in $DEPS; do
  case " ${cand[*]} " in *"$dep"*) ;; *) cand+=("$RTL/$dep") ;; esac
done

for f in "$REF"/*.v; do
  sed -E "s/\bred_pitaya_($MODS)\b/ref_red_pitaya_\1/g" "$f" > "$LOG/ref/ref_$(basename "$f")"
done

"$IVERILOG" -g2012 -o "$LOG/equiv.out" "$TB" "$LOG"/ref/*.v "${cand[@]}" > "$LOG/compile.log" 2>&1 || {
  echo "EQUIV: COMPILE FAIL (full log: $LOG/compile.log)"
  grep -iE "error" "$LOG/compile.log" | head -n 15
  exit 1
}
"$VVP" -n "$LOG/equiv.out" > "$LOG/sim.log" 2>&1
grep -E "EQUIV|first mismatch|READBACK" "$LOG/sim.log" | head -n 12
grep -q "EQUIV PASS" "$LOG/sim.log"
