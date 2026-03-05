#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

OUT_DIR="${FX_DATA_DIR:-data_cache/forex}"
TZ_OFFSET="${FX_IMPORT_TZ_OFFSET_HOURS:-0}"
AUTO_DISCOVER="${FX_IMPORT_AUTODISCOVER:-1}"
SEARCH_ROOTS="${FX_IMPORT_SEARCH_ROOTS:-$HOME/Downloads,$HOME/Desktop}"

PAIRS_CSV="${FX_PAIRS:-EURUSD,GBPUSD,USDJPY}"
IFS=',' read -r -a PAIRS <<< "$PAIRS_CSV"
IFS=',' read -r -a ROOTS <<< "$SEARCH_ROOTS"

discover_src_for_pair() {
  local pair="$1"
  local root
  local f
  local pattern
  pattern="${pair}|${pair}_M5|${pair}.*M5|M5.*${pair}"

  for root in "${ROOTS[@]}"; do
    root="$(echo "$root" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$root" ]] && continue
    [[ ! -d "$root" ]] && continue

    while IFS= read -r f; do
      if [[ -n "$f" ]]; then
        printf '%s\n' "$f"
        return 0
      fi
    done < <(find "$root" -type f \( -iname "*.csv" -o -iname "*.txt" \) 2>/dev/null | grep -Ei "$pattern" | head -n 1 || true)
  done
  return 1
}

echo "forex import batch start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "pairs=${PAIRS_CSV}"
echo "out_dir=${OUT_DIR}"
echo "tz_offset_hours=${TZ_OFFSET}"
echo "auto_discover=${AUTO_DISCOVER}"
echo "search_roots=${SEARCH_ROOTS}"

for raw in "${PAIRS[@]}"; do
  pair="$(echo "$raw" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  [[ -z "$pair" ]] && continue

  src_var="FX_${pair}_SRC"
  src="${!src_var-}"
  if [[ -z "$src" && "$AUTO_DISCOVER" == "1" ]]; then
    src="$(discover_src_for_pair "$pair" || true)"
    if [[ -n "$src" ]]; then
      echo "auto ${pair}: found source=${src}"
    fi
  fi
  if [[ -z "$src" ]]; then
    echo "skip ${pair}: source not set/found (env ${src_var} empty; auto_discover=${AUTO_DISCOVER})"
    continue
  fi
  if [[ "$src" == *"/ABS/"* || "$src" == *"/ABSOLUTE/"* || "$src" == *"/REAL/PATH/"* || "$src" == *"/путь/"* || "$src" == *"<"* ]]; then
    echo "skip ${pair}: ${src_var} looks like a placeholder path: ${src}"
    continue
  fi
  if [[ ! -f "$src" ]]; then
    echo "skip ${pair}: source file not found: ${src}"
    continue
  fi

  dst="${OUT_DIR}/${pair}_M5.csv"
  echo ""
  echo ">>> IMPORT ${pair}"
  python3 scripts/forex_import_csv.py \
    --input "$src" \
    --output "$dst" \
    --symbol "$pair" \
    --tz_offset_hours "$TZ_OFFSET"
done

echo ""
echo "forex import batch done: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "next: FX_DATA_DIR=${OUT_DIR} FX_PAIRS=${PAIRS_CSV} bash scripts/run_forex_data_check.sh"
