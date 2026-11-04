#!/usr/bin/env bash
# run_demo.sh --track {H|B|C} [--level easy|medium|hard] [--assist] [--interactive] [--setup-only]
# 1-2: fresh workspace + tools/tasks (here); 3-7: proxy, agent, judge, QoR,
# leak check, report (harness/run_stages.py). Output: runs/<ts>_<track>/report.html
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

track=""; level=hard; assist=false; interactive=false; setup_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --track) track="$2"; shift 2 ;;
    --level) level="$2"; shift 2 ;;
    --assist) assist=true; shift ;;
    --interactive) interactive=true; shift ;;
    --setup-only) setup_only=true; shift ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done
case "$track" in H|B|C) ;; *) echo "usage: run_demo.sh --track {H|B|C} [--level easy|medium|hard] [--assist] [--interactive]" >&2; exit 64 ;; esac
case "$level" in easy|medium|hard) ;; *) echo "--level must be easy, medium or hard" >&2; exit 64 ;; esac
if $assist && [ "$track" != H ]; then echo "--assist is only defined for track H" >&2; exit 64; fi

HARNESS="$ROOT/harness"
VENDOR="$(abspath "$(yaml_get pyrpl_repo)")"
WS="$(cd "$ROOT" && mkdir -p "$(yaml_get workspace_dir)" && cd "$(yaml_get workspace_dir)" && pwd)"
case "$WS" in *ai_demo*|*harness*|*judge*) echo "workspace_dir must not be inside or named like the repo: $WS" >&2; exit 1 ;; esac
RTL_REL="pyrpl/$(yaml_get pyrpl_rtl)"      # path of the RTL inside workspace/

"$HARNESS/check_vendor.sh"

ts="$(date +%Y%m%d_%H%M%S)"
RUN="$ROOT/runs/${ts}_${track}_${level}$($assist && echo _assist || true)"
mkdir -p "$RUN"

# 1. Fresh workspace: copy pinned PyRPL without .git, then baseline commit.
#    Track C gets only the seeded review set: the full tree has near-copies
#    (e.g. pid_block_with_normalizer.v) that would reveal the bugs by diff.
rm -rf "$WS"
if [ "$track" = C ]; then
  mkdir -p "$WS"
  "$PYTHON" "$(nativepath "$HARNESS/judge/bughunt/bugs.py")" build "$(nativepath "$WS/review")" "$level" > /dev/null
else
mkdir -p "$WS/pyrpl"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude .git "$VENDOR/" "$WS/pyrpl/"
else
  # Fallback (Git Bash on Windows has no rsync): same result via tar.
  tar -C "$VENDOR" --exclude=.git -cf - . | tar -C "$WS/pyrpl" -xf -
fi
chmod -R u+w "$WS/pyrpl"   # vendor is read-only; workspace must be writable
fi

# 2. Tools, rules, task files (never harness/judge).
cp -r "$HARNESS/tools" "$WS/tools"
write_tool_env "$WS/tools/tool_env.sh"
chmod +x "$WS"/tools/*.sh
cp "$HARNESS/tasks/AGENTS.md" "$WS/AGENTS.md"
mkdir -p "$WS/tasks/$track"
# hard = tasks/<T>/ (original task); easy/medium = tasks/<T>/<level>/ when that level has its own files
TASKSRC="$HARNESS/tasks/$track"
[ "$level" != hard ] && [ -d "$TASKSRC/$level" ] && TASKSRC="$TASKSRC/$level"
find "$TASKSRC" -maxdepth 1 -type f ! -name KNOWN_ISSUES.md ! -name pid_ref.v ! -name baseline.json ! -name 'ref_*' \
  -exec cp {} "$WS/tasks/$track/" \;
if [ "$track" = C ]; then   # list exactly this level's review files in the task
  "$PYTHON" - "$(nativepath "$HARNESS/judge/bughunt")" "$level" "$(nativepath "$WS/tasks/C/task.md")" <<'PYEOF'
import sys; sys.path.insert(0, sys.argv[1]); import bugs
files = "\n".join(f"- `{f}`" for f in bugs.LEVELS[sys.argv[2]]["review"])
p = sys.argv[3]; text = open(p).read().replace("{REVIEW_FILES}", files); open(p, "w").write(text)
PYEOF
fi
if [ "$track" = B ]; then
  # functional reference for run_equiv.sh (original + kd fix); not a solution
  mkdir -p "$WS/tasks/B/ref"
  cp "$HARNESS/tasks/B/pid_ref.v" "$WS/tasks/B/ref/red_pitaya_pid_block.v"
  cp "$VENDOR/$(yaml_get pyrpl_rtl)/red_pitaya_filter_block.v" "$VENDOR/$(yaml_get pyrpl_rtl)/red_pitaya_lpf_block.v" "$WS/tasks/B/ref/"
  chmod u+w "$WS"/tasks/B/ref/*.v
  # start from pid_ref.v (upstream + kd X fix) so the agent isn't failed by the upstream sim bug
  cp "$HARNESS/tasks/B/pid_ref.v" "$WS/$RTL_REL/red_pitaya_pid_block.v"
  t_target="$("$PYTHON" -c "import json,sys; print(json.load(open(sys.argv[1]))['T_target_ns'])" "$(nativepath "$HARNESS/tasks/B/baseline.json")")"
  sed -i "s/{T_TARGET}/$t_target/g" "$WS/tasks/B/task.md"
fi
if $assist; then
  cp "$HARNESS/tasks/H/assist/red_pitaya_notch_block.v" "$WS/$RTL_REL/red_pitaya_notch_block.v"
fi

# Baseline commit covers everything the agent starts with, so the diff is only its work.
git -C "$WS" init -q
git -C "$WS" -c core.autocrlf=false add -A
git -C "$WS" -c user.name=demo -c user.email=demo@localhost \
  commit -q -m "baseline: pyrpl $(git -C "$VENDOR" rev-parse --short HEAD) (demo-baseline), track $track, assist=$assist"

"$PYTHON" "$(nativepath "$HARNESS/gen_opencode_config.py")" > /dev/null

# Demo policy: the management demo uses a non-Chinese model (Gemma). Other
# models (e.g. Qwen) are allowed for plumbing tests only and are flagged.
model="$(yaml_get model)"
case "$(echo "$model" | tr A-Z a-z)" in *gemma*) demo_model=true ;; *) demo_model=false
  echo "WARNING: model '$model' is not a demo model; this run is marked PLUMBING TEST" >&2 ;; esac

cat > "$RUN/run_meta.json" <<EOF
{"track": "$track", "level": "$level", "assist": $assist, "interactive": $interactive, "timestamp": "$ts",
 "model": "$model", "demo_model": $demo_model, "upstream_url": "$(yaml_get upstream_url)",
 "pyrpl_commit": "$(yaml_get pyrpl_commit)", "context_limit": $(yaml_get context_limit)}
EOF

echo "workspace ready: $WS  (track $track, assist=$assist)"
echo "run dir: $RUN"
$setup_only && exit 0

args=(--level "$level"); $assist && args+=(--assist); $interactive && args+=(--interactive)
"$PYTHON" "$(nativepath "$HARNESS/run_stages.py")" "$(nativepath "$RUN")" "$(nativepath "$WS")" "$track" "${args[@]}"
