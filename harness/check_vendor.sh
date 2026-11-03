#!/usr/bin/env bash
# Fail unless vendor/pyrpl is clean and at the commit pinned in config/env.yaml.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Env overrides (self-tests only; never edit env.yaml for tests)
repo="$(abspath "${PYRPL_REPO:-$(yaml_get pyrpl_repo)}")"
pinned="${PYRPL_COMMIT:-$(yaml_get pyrpl_commit)}"

[ -n "$pinned" ] || { echo "check_vendor: FAIL pyrpl_commit missing in $ENV_YAML" >&2; exit 1; }
[ -d "$repo/.git" ] || { echo "check_vendor: FAIL $repo is not a git repo" >&2; exit 1; }

dirty="$(git -C "$repo" status --porcelain)"
if [ -n "$dirty" ]; then
  echo "check_vendor: FAIL vendor tree modified:" >&2
  echo "$dirty" >&2
  exit 1
fi

head="$(git -C "$repo" rev-parse HEAD)"
if [ "$head" != "$pinned" ]; then
  echo "check_vendor: FAIL HEAD $head != pinned $pinned" >&2
  exit 1
fi

echo "check_vendor: OK ($head)"
