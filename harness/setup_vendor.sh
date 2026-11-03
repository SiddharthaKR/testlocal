#!/usr/bin/env bash
# Fetch PyRPL into vendor/pyrpl at the commit pinned in config/env.yaml,
# tag it demo-baseline and make it read-only. Linux bash and Git Bash.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

repo="$(abspath "$(yaml_get pyrpl_repo)")"
commit="$(yaml_get pyrpl_commit)"
url="${PYRPL_URL:-https://github.com/lneuhaus/pyrpl.git}"

if [ -d "$repo/.git" ]; then
  echo "setup_vendor: $repo exists, checking it"
else
  mkdir -p "$(dirname "$repo")"
  git clone "$url" "$repo"
fi
chmod -R u+w "$repo"
git -C "$repo" -c advice.detachedHead=false checkout -q "$commit"
git -C "$repo" tag -f demo-baseline "$commit" > /dev/null
chmod -R a-w "$repo"

"$ROOT/harness/check_vendor.sh"
