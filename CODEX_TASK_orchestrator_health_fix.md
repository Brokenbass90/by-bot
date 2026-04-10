# CODEX TASK: Diagnose and fix orchestrator staleness + add health watchdog

## Problem
The orchestrator state file has not been updated since 2026-04-03 (7+ days stale).
File: `runtime/regime/orchestrator_state.json`
Last update: `"timestamp_utc": "2026-04-03T08:56:14"`

This means the bot is making regime decisions on week-old BTC data.
If the regime cron is dead, the bot may be silently not trading (wrong regime assessment).

## Task 1: Check and restart regime cron

```bash
# On server — check if cron is running
crontab -l | grep orchestrat

# Check last log entry for orchestrator
tail -50 logs/orchestrator.log 2>/dev/null || tail -50 logs/bot.log | grep -i "orche\|regime"

# If cron exists but failed — run manually to see error:
cd $BOT_DIR && $PYTHON scripts/regime_orchestrator.py --once 2>&1 | tail -30

# If no cron — re-run setup:
bash scripts/setup_server_crons.sh
```

## Task 2: Add orchestrator health watchdog to setup_server_crons.sh

Open `scripts/setup_server_crons.sh` and add these two crons:

```bash
# Cron #13 — orchestrator freshness check (every 6h, alert if state is >3h stale)
0 */6 * * * cd $BOT_DIR && $PYTHON scripts/check_orchestrator_health.py >> logs/health_check.log 2>&1
```

## Task 3: Create scripts/check_orchestrator_health.py

Create a new file `scripts/check_orchestrator_health.py` with the following logic:

```python
#!/usr/bin/env python3
"""
Orchestrator health watchdog.
Checks if orchestrator_state.json is stale (>MAX_STALE_HOURS).
If stale: tries to re-run the orchestrator, sends TG alert.
If orchestrator fails: sends TG alert with error.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "runtime" / "regime" / "orchestrator_state.json"
MAX_STALE_HOURS = 3  # alert if older than 3h
BOT_DIR = str(BASE_DIR)

def send_tg(msg: str) -> None:
    """Send Telegram notification via operator script if available."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            print(f"[health] TG not configured: {msg}")
            return
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[health] TG send failed: {e}")

def main() -> None:
    now = datetime.now(timezone.utc)
    
    if not STATE_PATH.exists():
        send_tg("⚠️ <b>Orchestrator MISSING</b>\nState file not found. Regime unknown.")
        sys.exit(1)
    
    try:
        state = json.loads(STATE_PATH.read_text())
        ts_str = state.get("timestamp_utc", "")
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age_h = (now - ts).total_seconds() / 3600
    except Exception as e:
        send_tg(f"⚠️ <b>Orchestrator state unreadable</b>\n{e}")
        sys.exit(1)
    
    if age_h <= MAX_STALE_HOURS:
        print(f"[health] OK — orchestrator is {age_h:.1f}h old (regime={state.get('regime','?')})")
        return
    
    print(f"[health] STALE — orchestrator is {age_h:.1f}h old. Attempting re-run...")
    
    # Try to re-run orchestrator
    python = sys.executable
    result = subprocess.run(
        [python, str(BASE_DIR / "scripts" / "regime_orchestrator.py"), "--once"],
        capture_output=True, text=True, timeout=60, cwd=BOT_DIR
    )
    
    if result.returncode == 0:
        print(f"[health] Orchestrator re-run OK.")
        send_tg(f"✅ <b>Orchestrator auto-recovered</b>\nWas {age_h:.1f}h stale. Successfully refreshed.")
    else:
        err = (result.stderr or result.stdout or "no output")[-500:]
        send_tg(f"🚨 <b>Orchestrator FAILED</b>\nStale {age_h:.1f}h + re-run failed:\n<code>{err}</code>")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Task 4: Verify orchestrator is running after fix

```bash
# Run health check manually
$PYTHON scripts/check_orchestrator_health.py

# Check that state file was updated
python3 -c "
import json; d=json.load(open('runtime/regime/orchestrator_state.json'))
print('Regime:', d['regime'])
print('Updated:', d['timestamp_utc'])
print('BTC close:', d['indicators']['close'])
"
```

## Task 5: Check why bot hasn't traded recently

```bash
# Last 100 lines of bot log
tail -100 logs/bot.log | grep -E "signal|entry|trade|ERROR|block|reject"

# Check open positions
$PYTHON scripts/check_positions.py 2>/dev/null || \
tail -20 logs/bot.log | grep -i "position\|open\|filled"

# Check last trade timestamp
grep -E "filled|executed|trade_open" logs/bot.log | tail -5
```

## Expected outcome
- `orchestrator_state.json` updated with current BTC price and regime
- `check_orchestrator_health.py` added to cron #13
- TG notification when orchestrator goes stale
- Bot resumes regime-aware trading
