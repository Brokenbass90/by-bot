#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SRC_ENV="${FX_LIVE_FILTER_ENV:-docs/forex_live_filter_latest.env}"
OUT_ENV="${FX_DEMO_ENV_OUT:-docs/forex_demo_env_latest.env}"
DEMO_RISK="${FX_DEMO_RISK_PER_TRADE_PCT:-0.50}"

if [[ ! -f "${SRC_ENV}" ]]; then
  echo "source env not found: ${SRC_ENV}"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${SRC_ENV}"
set +a

cat > "${OUT_ENV}" <<EOF
FOREX_DEMO_ENABLED=1
FOREX_ENABLED_PAIRS=${FOREX_ENABLED_PAIRS:-}
FOREX_ENABLED_COMBOS=${FOREX_ENABLED_COMBOS:-}
FOREX_ACTIVE_PAIRS=${FOREX_ACTIVE_PAIRS:-}
FOREX_ACTIVE_COMBOS=${FOREX_ACTIVE_COMBOS:-}
FOREX_CANARY_PAIRS=${FOREX_CANARY_PAIRS:-}
FOREX_CANARY_COMBOS=${FOREX_CANARY_COMBOS:-}
FOREX_CANARY_RISK_MULT=${FOREX_CANARY_RISK_MULT:-0.50}
FOREX_RISK_PER_TRADE_PCT=${DEMO_RISK}
EOF

echo "forex demo env export done"
echo "source=${PWD}/${SRC_ENV}"
echo "saved=${PWD}/${OUT_ENV}"
