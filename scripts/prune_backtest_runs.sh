#!/usr/bin/env bash
set -euo pipefail

# Keep only the newest N run folders under backtest_runs/.
# Usage:
#   bash scripts/prune_backtest_runs.sh 50            # delete older, keep newest 50
#   bash scripts/prune_backtest_runs.sh 50 --dry-run  # show what would be deleted

N="${1:-}"
DRY="${2:-}"

if [[ -z "$N" ]]; then
  echo "Usage: $0 <keep_n> [--dry-run]" >&2
  exit 2
fi
if ! [[ "$N" =~ ^[0-9]+$ ]]; then
  echo "keep_n must be an integer" >&2
  exit 2
fi

ROOT="backtest_runs"
if [[ ! -d "$ROOT" ]]; then
  echo "No $ROOT directory" >&2
  exit 0
fi

# List directories sorted by mtime (newest first).
# NOTE: macOS ships bash 3.2 by default, which does NOT support `mapfile`.
# We keep this script compatible.
shopt -s nullglob

DIRS=()

# Collect candidates first to avoid ls errors when the glob is empty.
candidates=("$ROOT"/*)
if (( ${#candidates[@]} == 0 )); then
  echo "Nothing to prune: total=0 keep=$N" >&2
  exit 0
fi

while IFS= read -r p; do
  [[ -d "$p" ]] && DIRS+=("$p")
done < <(ls -1dt "${candidates[@]}" 2>/dev/null || true)

TOTAL=${#DIRS[@]}
if (( TOTAL <= N )); then
  echo "Nothing to prune: total=$TOTAL keep=$N" >&2
  exit 0
fi

TO_DELETE=("${DIRS[@]:$N}")

echo "Pruning $ROOT: total=$TOTAL keep=$N delete=${#TO_DELETE[@]}"

if [[ "$DRY" == "--dry-run" ]]; then
  printf '%s\n' "${TO_DELETE[@]}"
  exit 0
fi

for d in "${TO_DELETE[@]}"; do
  rm -rf "$d"
done

echo "Done."
