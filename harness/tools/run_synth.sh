#!/usr/bin/env bash
# run_synth.sh <top> <files...>
# Vivado out-of-context synthesis -> synth.json {status, LUT, FF, DSP, CARRY4, WNS}.
# Prints SKIPPED (no vivado) and exits 0 if Vivado is not available.
exec "$(dirname "${BASH_SOURCE[0]}")/_vivado.sh" synth "$@"
