#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/ui"
DST="$REPO_ROOT/frontend"

echo "Syncing $SRC -> $DST"
mkdir -p "$DST"
rsync -av --delete "$SRC/" "$DST/"
echo "Sync complete"
