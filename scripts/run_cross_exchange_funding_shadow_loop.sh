#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
LOG_DIR="${ROOT}/runtime/arb/logs"
INTERVAL_SECONDS="${CROSS_ARB_SHADOW_INTERVAL_SECONDS:-600}"
LOCK_DIR="${ROOT}/runtime/arb/cross_exchange_funding_shadow_loop.lock"
LOCK_PID="${LOCK_DIR}/pid"

mkdir -p "${LOG_DIR}"

acquire_lock() {
  if mkdir "${LOCK_DIR}" 2>/dev/null; then
    printf '%s\n' "$$" >"${LOCK_PID}"
    return 0
  fi

  owner_pid=""
  if [[ -f "${LOCK_PID}" ]]; then
    owner_pid="$(sed -n '1p' "${LOCK_PID}" 2>/dev/null || true)"
  fi
  echo "funding shadow supervisor lock exists owner=${owner_pid:-unknown}" >&2
  echo "refusing automatic stale-lock recovery; inspect the owner first" >&2
  return 73
}

release_lock() {
  current_owner=""
  if [[ -f "${LOCK_PID}" ]]; then
    current_owner="$(sed -n '1p' "${LOCK_PID}" 2>/dev/null || true)"
  fi
  if [[ "${current_owner}" != "$$" ]]; then
    return 0
  fi
  rm -f "${LOCK_PID}"
  rmdir "${LOCK_DIR}" 2>/dev/null || true
}

acquire_lock || exit $?
trap release_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  log="${LOG_DIR}/cross_exchange_funding_${stamp}.log"

  {
    echo "[$(date -u +%FT%TZ)] public scan"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_scan.py" \
      --exchanges bybit,binance,bitget \
      --min-volume-usd 1000000 \
      --min-spread-apr-pct 5.5 \
      --top 30

    echo "[$(date -u +%FT%TZ)] executable validation"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_validate.py" \
      --notional-usd 100 \
      --hold-hours 24 \
      --taker-fee-bps 6 \
      --max-slippage-bps 12 \
      --max-entry-basis-pct 1 \
      --min-spread-apr-pct 36 \
      --min-persistence-count 2 \
      --persistence-window-min 90 \
      --keep-failed

    echo "[$(date -u +%FT%TZ)] risk-zero paper lifecycle"
    "${PYTHON}" "${ROOT}/scripts/cross_exchange_funding_shadow.py" \
      --notional-usd 100 \
      --hold-hours 24 \
      --max-open 5 \
      --min-net-pct 0.20 \
      --min-persistence-count 3 \
      --taker-fee-bps 6 \
      --close-invalid-after-hours 2 \
      --close-invalid-count 3 \
      --reentry-cooldown-hours 6

    echo "[$(date -u +%FT%TZ)] bounded promotion gate"
    "${PYTHON}" "${ROOT}/scripts/arb_roi_calculator.py" \
      --state-json runtime/arb/cross_exchange_funding_shadow.json \
      --output-json runtime/arb/arb_roi_estimate.json \
      --capital 1000 \
      --min-closed-cycles 20 \
      --confirmation-closed-cycles 30 \
      --min-annualized-simple-pct 8 \
      --cohort explicit_validation_v1 \
      --opened-after-utc 2026-07-27T10:53:00Z
  } >"${log}" 2>&1 || true

  ln -sfn "${log}" "${LOG_DIR}/latest.log"
  terminal_decision="$(${PYTHON} -c 'import json,sys; p=json.load(open(sys.argv[1])); print((p.get("promotion_decision") or {}).get("decision") or "")' "${ROOT}/runtime/arb/arb_roi_estimate.json" 2>/dev/null || true)"
  if [[ "${terminal_decision}" == "retire_standalone_sleeve" ]]; then
    receipt="${ROOT}/runtime/arb/cross_exchange_funding_terminal_receipt.json"
    "${PYTHON}" -c 'import json,sys; from datetime import datetime,timezone; src=json.load(open(sys.argv[1])); out={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"status":"terminal","decision":"retire_standalone_sleeve","capital_authorized":False,"source":sys.argv[1],"reason":(src.get("promotion_decision") or {}).get("reason"),"reuse_allowed":(src.get("promotion_decision") or {}).get("reuse_allowed") or []}; json.dump(out,open(sys.argv[2],"w"),indent=2); open(sys.argv[2],"a").write("\n")' "${ROOT}/runtime/arb/arb_roi_estimate.json" "${receipt}"
    echo "[$(date -u +%FT%TZ)] terminal decision reached; supervisor exits and releases WIP slot" >>"${log}"
    break
  fi
  sleep "${INTERVAL_SECONDS}"
done
