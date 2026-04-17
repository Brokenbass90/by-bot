#!/usr/bin/env bash
# =============================================================================
#  alpaca_paper_launch_both.sh
#  Launch BOTH Alpaca paper trading branches on the server.
#
#  Run ONCE on server:
#    chmod +x scripts/alpaca_paper_launch_both.sh
#    bash scripts/alpaca_paper_launch_both.sh
#
#  What it does:
#    1. Verify Alpaca API connectivity (dry-run check)
#    2. Run monthly autopilot dry-run (check current picks)
#    3. Run intraday bridge dry-run (check signal + SPY gate)
#    4. Set up cron for intraday (every 5 min, market hours Mon-Fri)
#    5. Set up cron for monthly autopilot (1st of month, 09:30 UTC)
#    6. Set up cron for Alpaca TG daily report (16:30 UTC Mon-Fri)
#    7. Send Telegram launch confirmation
#
#  Both branches use configs/alpaca_paper_local.env for credentials.
#  Monthly uses configs/alpaca_paper_v36_candidate.env for strategy config.
#  Intraday uses configs/alpaca_intraday_dynamic_v1.env for watchlist config.
#
#  Capital split ($1000 account):
#    Monthly sleeve  → ALPACA_CAPITAL_OVERRIDE_USD=500 (2 picks × $225 each)
#    Intraday sleeve → INTRADAY_NOTIONAL_USD=150 × 3 positions = $450 max
#    Total max deployed: ~$900 (no overlap: monthly=hold, intraday=day-close)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN=".venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

LOCAL_ENV="configs/alpaca_paper_local.env"
LOG_DIR="logs"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $*${NC}"; }
fail() { echo -e "${RED}  ❌ $*${NC}"; exit 1; }
step() { echo -e "\n══════════════════════════════════════════"; echo -e "  → $*"; echo -e "══════════════════════════════════════════"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ALPACA PAPER LAUNCH — BOTH BRANCHES     ║"
echo "║  Monthly (v36) + Intraday (dynamic v1)   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

mkdir -p "$LOG_DIR" runtime/equities_monthly_v36 runtime/equities_intraday_dynamic_v1

# ── Load env for TG ──────────────────────────────────────────────────────────
if [ -f "$LOCAL_ENV" ]; then
    set -a; source "$LOCAL_ENV"; set +a
fi

TG_TOKEN="${TG_TOKEN:-}"
TG_CHAT_ID="${TG_CHAT_ID:-}"

_tg() {
    local msg="$1"
    [ -z "$TG_TOKEN" ] && return 0
    "$PYTHON_BIN" -c "
import json, ssl, urllib.request
payload = json.dumps({'chat_id': '$TG_CHAT_ID', 'text': '''$msg''', 'parse_mode': 'HTML'}).encode()
req = urllib.request.Request('https://api.telegram.org/bot$TG_TOKEN/sendMessage', data=payload, headers={'Content-Type': 'application/json'})
ctx = ssl.create_default_context()
try:
    urllib.request.urlopen(req, context=ctx, timeout=10)
    print('  TG: sent')
except Exception as e:
    print(f'  TG: failed ({e})')
" 2>/dev/null || true
}

# ── 1. SYNTAX CHECK ──────────────────────────────────────────────────────────
step "[1/7] Syntax check Alpaca scripts"

"$PYTHON_BIN" -m py_compile scripts/equities_alpaca_paper_bridge.py \
    && ok "equities_alpaca_paper_bridge.py: OK" \
    || fail "equities_alpaca_paper_bridge.py: SYNTAX ERROR"

"$PYTHON_BIN" -m py_compile scripts/equities_alpaca_intraday_bridge.py \
    && ok "equities_alpaca_intraday_bridge.py: OK" \
    || fail "equities_alpaca_intraday_bridge.py: SYNTAX ERROR"

"$PYTHON_BIN" -m py_compile scripts/equities_alpaca_tg_report.py 2>/dev/null \
    && ok "equities_alpaca_tg_report.py: OK" \
    || warn "equities_alpaca_tg_report.py: not found or syntax error"

# ── 2. MONTHLY DRY-RUN ───────────────────────────────────────────────────────
step "[2/7] Monthly branch dry-run (picks check)"

echo "  Loading monthly config..."
MONTHLY_BASE_ENV="${ALPACA_AUTOPILOT_BASE_ENV:-$ROOT/configs/alpaca_paper_v36_candidate.env}"
RUNTIME_DIR="${ALPACA_AUTOPILOT_RUNTIME_DIR:-runtime/equities_monthly_v36}"
LATEST_ENV="$RUNTIME_DIR/latest_refresh.env"
LATEST_PICKS=""

if [ -f "$LATEST_ENV" ]; then
    set -a; source "$LATEST_ENV"; set +a
    LATEST_PICKS="${EQ_LATEST_PICKS_CSV:-}"
fi
if [ -z "$LATEST_PICKS" ] && [ -f "$RUNTIME_DIR/latest_picks.csv" ]; then
    LATEST_PICKS="$RUNTIME_DIR/latest_picks.csv"
fi

if [ -z "$LATEST_PICKS" ]; then
    warn "No picks found — running full refresh first..."
    bash scripts/run_equities_alpaca_monthly_autopilot.sh --dry-run 2>&1 | tail -5
else
    echo "  Picks: $LATEST_PICKS"
    # Show current cycle picks
    echo "  Current cycle:"
    if [ -f "$RUNTIME_DIR/current_cycle_picks.csv" ]; then
        tail -n +2 "$RUNTIME_DIR/current_cycle_picks.csv" | awk -F',' '{print "    " $2 " (month=" $1 ", score=" $7 ")"}'
    else
        tail -3 "$LATEST_PICKS" | awk -F',' '{print "    " $2 " (month=" $1 ")"}'
    fi
    # Run dry-run check
    echo ""
    echo "  Running monthly dry-run..."
    ALPACA_SEND_ORDERS=0 ALPACA_PICKS_CSV="$LATEST_PICKS" \
        "$PYTHON_BIN" scripts/equities_alpaca_paper_bridge.py 2>&1 | tail -10 \
        && ok "Monthly dry-run passed" \
        || warn "Monthly dry-run had warnings (check above)"
fi

# ── 3. INTRADAY DRY-RUN ──────────────────────────────────────────────────────
step "[3/7] Intraday branch dry-run (signal check)"

echo "  Running intraday dry-run (--dry-run --once)..."
bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --dry-run --once 2>&1 | tail -20 \
    && ok "Intraday dry-run passed" \
    || warn "Intraday dry-run had warnings (check above — outside market hours is normal)"

# ── 4. CRON: INTRADAY ────────────────────────────────────────────────────────
step "[4/7] Set up intraday cron (every 5 min, Mon-Fri 14:00-21:00 UTC)"

BOT_DIR="$ROOT"
INTRADAY_CRON="alpaca_intraday_dynamic_v1"
INTRADAY_LINE="*/5 14-21 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once >> $LOG_DIR/alpaca_intraday_dynamic_v1.log 2>&1' # $INTRADAY_CRON"

(crontab -l 2>/dev/null | grep -v "$INTRADAY_CRON" || true; echo "$INTRADAY_LINE") | crontab -
ok "Intraday cron added: every 5 min Mon-Fri 14:00-21:00 UTC"
echo "  → logs/alpaca_intraday_dynamic_v1.log"

# ── 5. CRON: MONTHLY ─────────────────────────────────────────────────────────
step "[5/7] Set up monthly cron (1st of month, 09:30 UTC)"

MONTHLY_CRON="alpaca_monthly_autopilot"
MONTHLY_LINE="30 9 1 * * /bin/bash -lc 'cd $BOT_DIR && bash scripts/run_equities_alpaca_monthly_autopilot.sh >> $LOG_DIR/alpaca_monthly.log 2>&1' # $MONTHLY_CRON"

(crontab -l 2>/dev/null | grep -v "$MONTHLY_CRON" || true; echo "$MONTHLY_LINE") | crontab -
ok "Monthly cron added: 1st of each month at 09:30 UTC"
echo "  → logs/alpaca_monthly.log"

# ── 6. CRON: TG REPORT ───────────────────────────────────────────────────────
step "[6/7] Set up Alpaca TG daily report (Mon-Fri 16:30 UTC = market close)"

TG_REPORT_CRON="alpaca_tg_report"
TG_REPORT_LINE="30 16 * * 1-5 /bin/bash -lc 'cd $BOT_DIR && source .venv/bin/activate && python3 scripts/equities_alpaca_tg_report.py >> $LOG_DIR/alpaca_tg_report.log 2>&1' # $TG_REPORT_CRON"

if "$PYTHON_BIN" -m py_compile scripts/equities_alpaca_tg_report.py 2>/dev/null; then
    (crontab -l 2>/dev/null | grep -v "$TG_REPORT_CRON" || true; echo "$TG_REPORT_LINE") | crontab -
    ok "TG report cron: Mon-Fri 16:30 UTC (market close)"
    echo "  → logs/alpaca_tg_report.log"
else
    warn "equities_alpaca_tg_report.py not found — skipping TG report cron"
fi

# ── 7. SHOW CRONS ────────────────────────────────────────────────────────────
step "[7/7] Verify crontab + send Telegram launch confirmation"

echo ""
echo "  Active Alpaca crons:"
crontab -l 2>/dev/null | grep "alpaca\|equities_alpaca" | while IFS= read -r line; do
    echo "  → $line"
done

# Final TG message
LAUNCH_MSG="🚀 <b>Alpaca Paper Launch — BOTH BRANCHES LIVE</b>

<b>📅 Monthly (v36 picks):</b>
• Picks: $([ -f "$RUNTIME_DIR/current_cycle_picks.csv" ] && awk -F',' 'NR>1{printf "%s ", $2}' "$RUNTIME_DIR/current_cycle_picks.csv" || echo 'see runtime/equities_monthly_v36')
• Capital: \$500 override | 2 positions × 45%
• Cron: 1st of month at 09:30 UTC

<b>📈 Intraday (dynamic v1):</b>
• Watchlist: dynamic 10 symbols (breakout + reversion)
• Notional: \$150/pos × 3 max = \$450 deployed
• Cron: every 5 min Mon-Fri 14:00-21:00 UTC
• Guards: SPY gate + 2.5% daily loss limit + equity curve filter

<b>⚙️ Account: \$1000 paper demo</b>
• Fractional shares: ON (NVDA etc. at correct \$150 notional)
• Max deployed: ~\$900 (monthly \$450 + intraday \$450)
• TG reports: Mon-Fri 16:30 UTC

Paper test started: $(date -u '+%Y-%m-%d %H:%M UTC')"

_tg "$LAUNCH_MSG"
ok "Telegram launch notification sent"

echo ""
echo "  ══════════════════════════════════════════"
echo "  ALPACA PAPER BOTH BRANCHES: LIVE ✅"
echo ""
echo "  Watch logs:"
echo "    tail -f logs/alpaca_intraday_dynamic_v1.log"
echo "    tail -f logs/alpaca_monthly.log"
echo ""
echo "  Manual test (intraday, NOW):"
echo "    bash scripts/run_equities_alpaca_intraday_dynamic_v1.sh --once"
echo ""
echo "  Manual test (monthly, NOW):"
echo "    bash scripts/run_equities_alpaca_monthly_autopilot.sh"
echo ""
echo "  Check positions (Alpaca paper dashboard):"
echo "    https://app.alpaca.markets/paper-trading/portfolio/positions"
echo "  ══════════════════════════════════════════"
echo ""
