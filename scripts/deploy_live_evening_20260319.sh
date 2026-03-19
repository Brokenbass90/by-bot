#!/usr/bin/env bash
set -euo pipefail

BRANCH="codex/dynamic-symbol-filters"
SERVER_IP="64.226.73.119"
SERVER_USER="root"
BOT_DIR="/root/by-bot"
SSH_KEY="${HOME}/.ssh/by-bot"
SSH_OPTS="-i ${SSH_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

echo ""
echo "=============================================="
echo "  LIVE EVENING ROLLOUT - $(date '+%Y-%m-%d %H:%M:%S')"
echo "  branch=${BRANCH} server=${SERVER_IP}"
echo "=============================================="

if [ ! -f "${SSH_KEY}" ]; then
    echo "Missing SSH key: ${SSH_KEY}"
    exit 1
fi

echo ""
echo "[1/5] Push current branch to GitHub..."
GIT_SSH_COMMAND="ssh -i ${SSH_KEY} -o IdentitiesOnly=yes" git push origin "${BRANCH}"
echo "OK: origin/${BRANCH} updated"

echo ""
echo "[2/5] Pull branch on server..."
ssh ${SSH_OPTS} "${SERVER_USER}@${SERVER_IP}" bash <<ENDSSH
set -euo pipefail
cd "${BOT_DIR}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}" 2>/dev/null || true
git pull --ff-only origin "${BRANCH}"
git log --oneline -3
ENDSSH

echo ""
echo "[3/5] Apply live evening settings..."
ssh ${SSH_OPTS} "${SERVER_USER}@${SERVER_IP}" bash <<'ENDSSH'
set -euo pipefail
cd /root/by-bot

backup=".env.bak.$(date +%Y%m%d_%H%M%S)"
cp .env "$backup"
echo "Backed up .env -> $backup"

python3 - <<'PY'
import json
from pathlib import Path

env_path = Path(".env")
lines = env_path.read_text(encoding="utf-8").splitlines()
data = {}
order = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k = k.strip()
    data[k] = v.strip()
    order.append(k)

def set_kv(key: str, value: str):
    if key not in data:
        order.append(key)
    data[key] = value

raw = data.get("BYBIT_ACCOUNTS_JSON", "").strip()
if raw:
    accounts = json.loads(raw)
    target = data.get("TRADE_ACCOUNT_NAME", "main")
    for acc in accounts:
        if acc.get("name") == target:
            trade = acc.setdefault("trade", {})
            trade["risk_pct"] = 0.01
            trade["max_positions"] = int(trade.get("max_positions", trade.get("max_trades", 3)) or 3)
            trade["bot_capital_usd"] = float(trade.get("bot_capital_usd", 100) or 100)
            break
    set_kv("BYBIT_ACCOUNTS_JSON", json.dumps(accounts, ensure_ascii=False, separators=(",", ":")))

set_kv("MAX_OPEN_PORTFOLIO_RISK_PCT", "3.0")
set_kv("BREAKOUT_SKIP_ALERT_COOLDOWN_SEC", "14400")
set_kv("ENABLE_SLOPED_TRADING", "1")
set_kv("ENABLE_TS132_TRADING", "0")
set_kv("SLOPED_TRY_EVERY_SEC", "60")
set_kv("SLOPED_RISK_MULT", "0.10")
set_kv("SLOPED_MAX_OPEN_TRADES", "1")
set_kv("ASC1_ALLOW_LONGS", "0")
set_kv("ASC1_ALLOW_SHORTS", "1")
set_kv("ASC1_SYMBOL_ALLOWLIST", "ATOMUSDT")
set_kv("ASC1_MAX_ABS_SLOPE_PCT", "2.0")
set_kv("ASC1_MIN_RANGE_R2", "0.25")
set_kv("ASC1_SHORT_MAX_NEAR_UPPER_BARS", "2")
set_kv("ASC1_SHORT_MIN_REJECT_DEPTH_ATR", "0.75")
set_kv("ASC1_SHORT_MIN_RSI", "60")
set_kv("ASC1_SHORT_NEAR_UPPER_ATR", "0.15")
set_kv("ASC1_SHORT_MIN_REJECT_VOL_MULT", "0.0")
set_kv("ASC1_TP1_FRAC", "0.45")
set_kv("ASC1_TP2_BUFFER_PCT", "0.40")
set_kv("ASC1_TIME_STOP_BARS_5M", "480")

existing = {line.split("=", 1)[0].strip(): line for line in lines if "=" in line and line.strip() and not line.strip().startswith("#")}
new_lines = []
written = set()
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        new_lines.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    new_lines.append(f"{key}={data[key]}")
    written.add(key)
for key in order:
    if key not in written:
        new_lines.append(f"{key}={data[key]}")
env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

accounts = json.loads(data["BYBIT_ACCOUNTS_JSON"])
target = data.get("TRADE_ACCOUNT_NAME", "main")
for acc in accounts:
    if acc.get("name") == target:
        trade = acc.get("trade") or acc
        print(f"TRADE_ACCOUNT_NAME={acc.get('name')}")
        print(f"RISK_PCT_JSON={trade.get('risk_pct')}")
        print(f"MAX_POSITIONS_JSON={trade.get('max_positions', trade.get('max_trades'))}")
        print(f"BOT_CAPITAL_USD_JSON={trade.get('bot_capital_usd')}")
        break
print(f"MAX_OPEN_PORTFOLIO_RISK_PCT={data.get('MAX_OPEN_PORTFOLIO_RISK_PCT')}")
print(f"BREAKOUT_SKIP_ALERT_COOLDOWN_SEC={data.get('BREAKOUT_SKIP_ALERT_COOLDOWN_SEC')}")
print(f"ENABLE_SLOPED_TRADING={data.get('ENABLE_SLOPED_TRADING')}")
print(f"ENABLE_TS132_TRADING={data.get('ENABLE_TS132_TRADING')}")
print(f"SLOPED_RISK_MULT={data.get('SLOPED_RISK_MULT')}")
print(f"SLOPED_MAX_OPEN_TRADES={data.get('SLOPED_MAX_OPEN_TRADES')}")
print(f"ASC1_SYMBOL_ALLOWLIST={data.get('ASC1_SYMBOL_ALLOWLIST')}")
PY
ENDSSH

echo ""
echo "[4/5] Restart live bot..."
ssh ${SSH_OPTS} "${SERVER_USER}@${SERVER_IP}" bash <<'ENDSSH'
set -euo pipefail
cd /root/by-bot

if screen -list 2>/dev/null | grep -q "\.bot"; then
    screen -S bot -X quit 2>/dev/null || true
    sleep 2
fi

if [ -f scripts/start_bot.sh ]; then
    screen -dmS bot stdbuf -oL -eL bash scripts/start_bot.sh
else
    screen -dmS bot stdbuf -oL -eL python3 smart_pump_reversal_bot.py
fi

sleep 5
screen -list | grep bot || true
ENDSSH

echo ""
echo "[5/5] Smoke-check startup..."
ssh ${SSH_OPTS} "${SERVER_USER}@${SERVER_IP}" bash <<'ENDSSH'
set -euo pipefail
cd /root/by-bot
if [ -f runtime/live.out ]; then
    tail -n 60 runtime/live.out
else
    screen -S bot -X hardcopy -h /tmp/bot_screen.txt || true
    tail -n 60 /tmp/bot_screen.txt || true
fi
ENDSSH

echo ""
echo "=============================================="
echo "  Evening rollout complete"
echo "  live risk_pct -> 1.0%"
echo "  open portfolio risk cap -> 3.0%"
echo "  sloped stays tiny canary on ATOM"
echo "=============================================="
