#!/usr/bin/env bash
# run_impl.sh <top> <period_ns> <files...>
# Vivado OOC synth + opt + place + route -> impl.json (resources, WNS, Fmax,
# top-5 critical paths). Prints SKIPPED (no vivado) and exits 0 without Vivado.
exec "$(dirname "${BASH_SOURCE[0]}")/_vivado.sh" impl "$@"
