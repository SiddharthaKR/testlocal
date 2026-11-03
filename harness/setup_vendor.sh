#!/usr/bin/env bash
# Fetch PyRPL into vendor/pyrpl at the commit pinned in config/env.yaml,
# tag it demo-baseline and make it read-only. Linux bash and Git Bash.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

repo="$(abspath "$(yaml_get pyrpl_repo)")"
commit="$(yaml_get pyrpl_commit)"
url="${PYRPL_URL:-https://github.com/lneuhaus/pyrpl.git}"

if [ -d "$repo/.git" ] && git -C "$repo" cat-file -e "$commit^{commit}" 2>/dev/null; then
  echo "setup_vendor: $repo exists, checking it"
else
  # missing or half-cloned (e.g. an earlier failed checkout): start over
  [ -e "$repo" ] && { chmod -R u+w "$repo"; rm -rf "$repo"; }
  mkdir -p "$(dirname "$repo")"
  # core.longpaths: PyRPL has notebook paths longer than Windows' MAX_PATH (no effect on Linux)
  git -c core.longpaths=true clone "$url" "$repo"
  git -C "$repo" config core.longpaths true
fi
chmod -R u+w "$repo"
git -C "$repo" -c advice.detachedHead=false checkout -q "$commit"
git -C "$repo" tag -f demo-baseline "$commit" > /dev/null
chmod -R a-w "$repo"

"$ROOT/harness/check_vendor.sh"
