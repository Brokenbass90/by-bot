#!/usr/bin/env bash
set -u

ROOT_DIR="${ROOT_DIR:-/root/by-bot}"
cd "$ROOT_DIR" || exit 1

LOG_DIR="logs/crypto_research_guard_20260608"
mkdir -p "$LOG_DIR"
QUEUE_LOG="$LOG_DIR/queue.log"

log() {
  echo "$(date -u +%FT%TZ) $*" | tee -a "$QUEUE_LOG"
}

wait_for_existing_autoresearch() {
  while pgrep -fal "scripts/run_strategy_autoresearch.py --spec" | grep -v "run_crypto_research_guard_20260608" >/dev/null 2>&1; do
    log "WAIT existing autoresearch still running"
    sleep 300
  done
}

run_one() {
  local spec="$1"
  local limit="$2"
  local name
  name="$(basename "$spec" .json)"
  local attempt rc log_file
  for attempt in 1 2; do
    wait_for_existing_autoresearch
    log "START $name limit=$limit attempt=$attempt"
    log_file="$LOG_DIR/${name}_attempt${attempt}_$(date -u +%Y%m%d_%H%M%S).log"
    if [ "$limit" = "all" ]; then
      .venv/bin/python3 scripts/run_strategy_autoresearch.py --spec "$spec" --jobs 1 >"$log_file" 2>&1
    else
      .venv/bin/python3 scripts/run_strategy_autoresearch.py --spec "$spec" --limit "$limit" --jobs 1 >"$log_file" 2>&1
    fi
    rc=$?
    log "DONE $name rc=$rc log=$log_file"
    tail -40 "$log_file" >> "$LOG_DIR/queue_tail.log" 2>/dev/null || true
    if [ "$rc" -eq 0 ]; then
      return 0
    fi
    log "RETRY_SCHEDULED $name after rc=$rc"
    sleep 120
  done
  log "FAILED_AFTER_RETRY $name"
  return 0
}

log "GUARD_QUEUE_BEGIN"

# High-priority additivity/repair candidates. Sequential on purpose: 1 vCPU server.
run_one "configs/autoresearch/package_brc1_bounded_additivity_v1.json" "all"
run_one "configs/autoresearch/package_bear_brc1_v1_nowide.json" "all"
run_one "configs/autoresearch/support_bounce_v1_annual_repair_v2.json" "all"
run_one "configs/autoresearch/inplay_breakout_retest_focus_v1.json" "240"

# Longer-shot research at the end so it cannot block the higher-priority queue.
run_one "configs/autoresearch/package_elder_revived_v1.json" "48"
run_one "configs/autoresearch/elder_canonical_rewrite_v1.json" "240"

log "GUARD_QUEUE_COMPLETE"
