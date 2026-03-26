#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SRC_CSV="${1:-docs/rd_cleanup_candidates.csv}"
ARCH_DIR="${2:-archive/strategies_rejected}"
DRY_RUN="${DRY_RUN:-1}"   # 1 = print only, 0 = move files

if [[ ! -f "$SRC_CSV" ]]; then
  echo "missing csv: $SRC_CSV"
  exit 1
fi

STAMP="$(date -u +%Y%m%d_%H%M%S)"
MANIFEST_DIR="archive"
MANIFEST_PATH="${MANIFEST_DIR}/rejected_manifest_${STAMP}.csv"

mkdir -p "$ARCH_DIR" "$MANIFEST_DIR"

echo "archive rejected strategies"
echo "src_csv=${SRC_CSV}"
echo "archive_dir=${ARCH_DIR}"
echo "dry_run=${DRY_RUN}"
echo "manifest=${MANIFEST_PATH}"

echo "date_utc,action,src,dst,status" > "$MANIFEST_PATH"

tail -n +2 "$SRC_CSV" | while IFS=, read -r file status; do
  file="$(echo "$file" | tr -d '\r' | xargs)"
  status="$(echo "$status" | tr -d '\r' | xargs)"
  [[ -z "$file" ]] && continue

  if [[ "$status" != "archive_candidate" ]]; then
    continue
  fi

  src="strategies/${file}"
  dst="${ARCH_DIR}/${file}"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [[ ! -f "$src" ]]; then
    echo "${now},skip_missing,${src},${dst},missing" >> "$MANIFEST_PATH"
    continue
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRY: move ${src} -> ${dst}"
    echo "${now},plan_move,${src},${dst},dry_run" >> "$MANIFEST_PATH"
  else
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    echo "MOVED: ${src} -> ${dst}"
    echo "${now},moved,${src},${dst},ok" >> "$MANIFEST_PATH"
  fi
done

echo "done manifest=${MANIFEST_PATH}"
