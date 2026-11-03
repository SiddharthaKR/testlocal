#!/usr/bin/env bash
# _vivado.sh synth <top> <files...>
# _vivado.sh impl  <top> <period_ns> <files...>
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

mode="$1"; shift
[ $# -ge 2 ] || { echo "usage: run_$mode.sh <top> $([ "$mode" = impl ] && echo '<period_ns> ')<files...>"; exit 64; }
top="$1"; shift
period="$CLK_PERIOD_NS"
if [ "$mode" = impl ]; then period="$1"; shift; fi
out="$mode.json"; dir="${mode}_logs"; mkdir -p "$dir"

viv="$(find_vivado)"
if [ -z "$viv" ]; then
  printf '{"status": "SKIPPED", "reason": "no vivado", "top": "%s"}\n' "$top" > "$out"
  echo "$(echo "$mode" | tr a-z A-Z): SKIPPED (no vivado)  -> $out"
  exit 0
fi

files=""; for f in "$@"; do files="$files {$(nativepath "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")")}"; done

tcl="$dir/run.tcl"
cat > "$tcl" <<EOF
read_verilog -sv [list $files]
synth_design -top $top -mode out_of_context -part $FPGA_PART
create_clock -period $period -name clk [get_ports clk_i]
EOF
if [ "$mode" = impl ]; then
  cat >> "$tcl" <<EOF
opt_design
place_design
route_design
EOF
fi
cat >> "$tcl" <<EOF
report_utilization -file $dir/utilization.rpt
report_timing_summary -file $dir/timing_summary.rpt
report_timing -max_paths 5 -nworst 1 -file $dir/paths.rpt
EOF

t0=$(date +%s)
"$viv" -mode batch -nojournal -log "$dir/vivado.log" -source "$tcl" > /dev/null 2>&1
rc=$?
t1=$(date +%s)

"$PYTHON" "$TOOLS_DIR/_vivado_parse.py" "$mode" "$dir" "$top" "$period" "$rc" "$((t1 - t0))" > "$out"
"$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['summary'])" "$out"
[ $rc -eq 0 ] || { echo "first errors (full log: $dir/vivado.log):"; grep -m 10 "^ERROR" "$dir/vivado.log"; exit 1; }
