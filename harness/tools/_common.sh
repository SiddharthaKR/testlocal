# Sourced by the tools. Reads tool_env.sh (written by the harness) if present.
TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$TOOLS_DIR/tool_env.sh" ] && source "$TOOLS_DIR/tool_env.sh"
PYTHON="${PYTHON:-python3}"
VIVADO="${VIVADO:-auto}"
FPGA_PART="${FPGA_PART:-xc7z010clg400-1}"
CLK_PERIOD_NS="${CLK_PERIOD_NS:-8.0}"

IVERILOG="iverilog"; VVP="vvp"
if [ -n "${IVERILOG_DIR:-}" ]; then IVERILOG="$IVERILOG_DIR/iverilog"; VVP="$IVERILOG_DIR/vvp"; fi

MAX_LINES=40   # agent context budget: summaries never exceed this

# nativepath: Windows-style path under Git Bash (for Windows executables); no-op on Linux
nativepath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }

# find_vivado: prints the vivado command, or nothing if unavailable
find_vivado() {
  case "$VIVADO" in
    none|"") ;;
    auto) command -v vivado 2>/dev/null || true ;;
    *) [ -x "$VIVADO" ] && echo "$VIVADO" ;;
  esac
}

# clip <file> <n>: print at most n lines of file, noting how many were cut
clip() {
  local total; total=$(wc -l < "$1")
  head -n "$2" "$1"
  [ "$total" -gt "$2" ] && echo "... ($((total - $2)) more lines in $1)"
  return 0
}
