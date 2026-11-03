#!/usr/bin/env bash
# Self-test for check_vendor.sh on a temporary writable clone (never touches vendor/).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T=/tmp/pyrpl_test
fail=0
rm -rf "$T" && git clone -q "$ROOT/vendor/pyrpl" "$T" && chmod -R u+w "$T"
expect() { # expect <0|1> <label>
  PYRPL_REPO="$T" bash "$ROOT/harness/check_vendor.sh" >/dev/null 2>&1; rc=$?
  if [ $(( rc != 0 )) -eq "$1" ]; then echo "PASS $2"; else echo "FAIL $2 (rc=$rc)"; fail=1; fi
}
expect 0 "clean clone accepted"
echo "// x" >> "$T/pyrpl/fpga/rtl/red_pitaya_pid_block.v"; expect 1 "modified file rejected"
git -C "$T" checkout -q -- .
git -C "$T" checkout -q HEAD~1;                         expect 1 "different HEAD rejected"
rm -rf "$T"
exit $fail
