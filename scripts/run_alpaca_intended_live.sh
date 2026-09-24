#!/usr/bin/env bash
# Native cron entrypoint for the frozen contour. No implicit money activation.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${ALPACA_BASE_LOCAL_ENV:?explicit LIVE environment required}"
: "${ALPACA_INTENDED_RUNTIME:?explicit isolated runtime required}"
: "${ALPACA_INTENDED_CACHE:?explicit source cache required}"
mode="${1:---read-only}"
[[ $# -le 1 ]] || exit 2
case "$mode" in
  --read-only) args=(--run-intended-live --monthly) ;;
  --prepare) args=(--prepare-intended-monthly-live) ;;
  --preflight) args=(--preflight-intended-live) ;;
  --send-orders)
    # A shared lock serializes writes; removing the OLD scheduled writers is
    # separately required so two different profiles cannot alternate ownership.
    cron_text="$(crontab -l)" || { echo exclusive_owner_cron_unavailable >&2; exit 9; }
    process_text="$(ps ax -o command=)" || { echo exclusive_owner_process_truth_unavailable >&2; exit 9; }
    while IFS= read -r line; do
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      case "$line" in
        *run_alpaca_live_v38_once.sh*|*run_alpaca_protective_exit_manager.sh*)
          echo exclusive_owner_old_cron_present >&2; exit 9 ;;
      esac
    done <<< "$cron_text"
    while IFS= read -r line; do
      case "$line" in
        *run_alpaca_live_v38_once.sh*|*run_alpaca_protective_exit_manager.sh*|*" scripts/alpaca_protective_exit_manager.py"*|*"/root/by-bot/scripts/alpaca_protective_exit_manager.py"*)
          echo exclusive_owner_old_process_present >&2; exit 9 ;;
      esac
    done <<< "$process_text"
    args=(--run-intended-live --monthly --send-orders) ;;
  *) echo invalid_intended_live_mode >&2; exit 2 ;;
esac
exec bash "$ROOT/scripts/run_alpaca_adaptive_paper.sh" "${args[@]}" \
  --capital 487.42 --runtime-dir "$ALPACA_INTENDED_RUNTIME" --cache-dir "$ALPACA_INTENDED_CACHE"
