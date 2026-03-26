#!/usr/bin/env bash
set -euo pipefail

# Find likely Forex CSV exports without requiring ripgrep.
# Default search roots: ~/Downloads and ~/Desktop

ROOTS="${FX_SEARCH_ROOTS:-$HOME/Downloads,$HOME/Desktop}"
PAIRS="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}"

echo "forex source search start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "roots=$ROOTS"
echo "pairs=$PAIRS"
echo ""

IFS=',' read -r -a roots_arr <<< "$ROOTS"
IFS=',' read -r -a pairs_arr <<< "$PAIRS"

for raw_pair in "${pairs_arr[@]}"; do
  pair="$(echo "$raw_pair" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  [[ -z "$pair" ]] && continue

  echo ">>> ${pair}"
  found_any=0
  for raw_root in "${roots_arr[@]}"; do
    root="$(echo "$raw_root" | sed 's/[[:space:]]//g')"
    [[ -z "$root" ]] && continue
    if [[ ! -d "$root" ]]; then
      continue
    fi

    # Keep matcher broad enough for MT5/broker naming conventions.
    while IFS= read -r f; do
      found_any=1
      printf '%s\n' "$f"
    done < <(find "$root" -type f \( -iname "*.csv" -o -iname "*.txt" \) 2>/dev/null | \
      grep -Ei "${pair}|${pair}_M5|${pair}.*M5|M5.*${pair}" || true)
  done

  if [[ "$found_any" -eq 0 ]]; then
    echo "not found"
  fi
  echo ""
done

echo "forex source search done"
