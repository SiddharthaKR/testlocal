#!/usr/bin/env bash
# judge_selftest.sh [H|B|C|all]
# Validates judges: reference solutions must PASS, broken variants must FAIL.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

"$ROOT/harness/check_vendor.sh" || exit 1

track="${1:-all}"
OUT="$ROOT/runs/selftest"
fail=0

expect() {  # expect <PASS|FAIL> <label> <cmd...>
  local want="$1" label="$2"; shift 2
  "$@" > "$OUT/$label.log" 2>&1; local rc=$?
  local got=FAIL; [ $rc -eq 0 ] && got=PASS
  [ $rc -ge 2 ] && got="ERROR(rc=$rc)"
  if [ "$got" = "$want" ]; then echo "  ok    $label: $got (expected $want)"
  else echo "  WRONG $label: $got (expected $want)  see $OUT/$label.log"; fail=1; fi
}

if [ "$track" = H ] || [ "$track" = all ]; then
  echo "Track H (notch / gain / FIR judges):"
  rm -rf "$OUT/H"; mkdir -p "$OUT/H"
  J="$ROOT/harness/judge/notch/run_judge.py"
  R="$ROOT/harness/judge/ref_solutions/notch"
  "$PYTHON" "$R/make_broken.py" > /dev/null || exit 2
  expect PASS H_ref "$PYTHON" "$J" "$OUT/H/ref" "$R/red_pitaya_notch_block.v"
  for v in "$R"/broken/*.v; do
    n="$(basename "$v" .v)"
    expect FAIL "H_broken_$n" "$PYTHON" "$J" "$OUT/H/$n" "$v"
  done
  for lvl in easy:gain:gain_block medium:fir:fir_block; do
    IFS=: read -r L D M <<< "$lvl"
    R="$ROOT/harness/judge/ref_solutions/$D"
    "$PYTHON" "$R/make_broken.py" > /dev/null || exit 2
    expect PASS "H_${L}_ref" "$PYTHON" "$J" "$OUT/H/${L}_ref" "$R/red_pitaya_$M.v" --level "$L"
    for v in "$R"/broken/*.v; do
      n="$(basename "$v" .v)"
      expect FAIL "H_${L}_broken_$n" "$PYTHON" "$J" "$OUT/H/${L}_$n" "$v" --level "$L"
    done
  done
fi

if [ "$track" = B ] || [ "$track" = all ]; then
  echo "Track B (PID equivalence judge):"
  P="$ROOT/harness/judge/ref_solutions/pid"
  rm -rf "$OUT/B"; mkdir -p "$OUT/B"
  "$PYTHON" "$P/make_pid_solutions.py" > /dev/null || exit 2
  J="$ROOT/harness/judge/pid_equiv/run_judge.py"
  expect PASS B_pid_ref_itself "$PYTHON" "$J" "$OUT/B/pid_ref" "$ROOT/harness/tasks/B/pid_ref.v"
  expect PASS B_ref_optimized "$PYTHON" "$J" "$OUT/B/ref" "$P/red_pitaya_pid_block.v"
  for v in "$P"/broken/*.v; do
    n="$(basename "$v" .v)"
    expect FAIL "B_broken_$n" "$PYTHON" "$J" "$OUT/B/$n" "$v"
  done
  RTLV="$ROOT/$(yaml_get pyrpl_repo)/$(yaml_get pyrpl_rtl)"
  for lvl in easy medium; do
    if [ "$lvl" = easy ]; then G=iq_demod; M=red_pitaya_iq_demodulator_block; else G=iq_mod; M=red_pitaya_iq_modulator_block; fi
    P="$ROOT/harness/judge/ref_solutions/$G"
    echo "Track B ($lvl):"
    "$PYTHON" "$P/make_${G}_solutions.py" > /dev/null || exit 2
    expect PASS "B_${lvl}_ref_itself" "$PYTHON" "$J" "$OUT/B/${lvl}_ref" "$RTLV/$M.v" --level $lvl
    expect PASS "B_${lvl}_ref_optimized" "$PYTHON" "$J" "$OUT/B/${lvl}_opt" "$P/$M.v" --level $lvl
    for v in "$P"/broken/*.v; do
      n="$(basename "$v" .v)"
      expect FAIL "B_${lvl}_$n" "$PYTHON" "$J" "$OUT/B/${lvl}_$n" "$v" --level $lvl
    done
  done
fi

if [ "$track" = C ] || [ "$track" = all ]; then
  echo "Track C (bug hunt):"
  "$PYTHON" "$ROOT/harness/judge/bughunt/bugs.py" key > /dev/null || exit 2
  "$PYTHON" "$ROOT/harness/judge/bughunt/selftest.py" || fail=1
fi

[ $fail -eq 0 ] && echo "SELFTEST: OK" || echo "SELFTEST: FAILED"
exit $fail
