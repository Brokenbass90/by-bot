# Deploy Checklist — Core-2 Pack (breakdown_v1 + ARF1)

**Date**: 2026-04-04
**Target env**: `configs/live_candidate_core2_breakdown_arf1_20260404.env`
**Regime**: bear_chop

---

## Pre-deploy (on dev machine)

- [ ] `python3 -m py_compile strategies/alt_inplay_breakdown_v1.py strategies/alt_resistance_fade_v1.py` — both OK
- [ ] `python3 -m py_compile smart_pump_reversal_bot.py` — OK
- [ ] `git log --oneline -5` — confirm working commits
- [ ] `git diff HEAD` — no uncommitted surprises
- [ ] Confirm `orchestrator_state.json` shows `"regime": "bear_chop"` before push

---

## Server transfer

```bash
# From dev:
rsync -av --exclude '__pycache__' --exclude '*.pyc' \
  strategies/alt_inplay_breakdown_v1.py \
  strategies/alt_resistance_fade_v1.py \
  strategies/alt_sloped_channel_v1.py \
  smart_pump_reversal_bot.py \
  scripts/dynamic_allowlist.py \
  scripts/strategy_scorer.py \
  configs/live_candidate_core2_breakdown_arf1_20260404.env \
  user@server:/path/to/bot/
```

---

## Server-side pre-start checks

- [ ] No open positions: `/status` or REST check `GET /v5/position/list`
- [ ] Paper mode sanity run: `PAPER_MODE=1 python3 smart_pump_reversal_bot.py` — starts without errors
- [ ] Verify `TRADE_ON=0` is set; confirm trades only after manual review of first signal
- [ ] Set `max_positions=2` in trade JSON config (or send `/set max_positions 2` after start)

---

## Service config (systemd example)

```ini
[Service]
EnvironmentFile=/path/to/server.env
EnvironmentFile=/path/to/configs/live_candidate_core2_breakdown_arf1_20260404.env
ExecStart=/usr/bin/python3 /path/to/smart_pump_reversal_bot.py
Restart=on-failure
RestartSec=30
```

**Load order**: `server.env` first (API keys), then this candidate file (strategy params).
Duplicate keys: last file wins — strategy params here will override base.

---

## First 48 hours monitoring

### Accept as normal:
- Signals firing within 30 min of 1h candle close
- TP/SL confirmed in Bybit position UI
- Occasional `KLINE_STALE` warnings (kline lag < 90s is fine)

### Escalate immediately:
- `TPSL failsafe armed` in logs → check if position protected; failsafe closes if not
- Consecutive losses ≥ 3 without any win → pause and review
- Live DD > 3% → halt, compare signals to backtest conditions
- Bot crash / restart loop → check logs for error pattern

---

## Risk staging plan

| Timeline | `ORCH_GLOBAL_RISK_MULT` | `BREAKDOWN_RISK_MULT` | Effective risk/trade |
|---|---|---|---|
| Week 1-2 | 0.50 | 0.80 | breakdown 0.40%, ARF1 0.50% |
| Week 3+ (if WR ≥ 45%) | 0.70 | 0.80 | breakdown 0.56%, ARF1 0.70% |
| Month 2 (if PF ≥ 1.4) | 0.70 | 1.00 | breakdown 0.70%, ARF1 0.70% |

---

## What stays OUT of this deploy

| Strategy | Reason | Action |
|---|---|---|
| breakout | Losing in chop (-0.53% / 90d) | Codex sweep for retune |
| ASC1/sloped | Unproven with new slope params | Paper mode first |
| pump_fade_v2 | No live validation yet | Autoresearch sweep pending |
| range_scalp_v1 | No live validation yet | Autoresearch sweep pending |
| elder_ts_v2 | No live validation yet | Autoresearch sweep pending |
| support_bounce_v1 | OFF in bear_chop | Re-enable on bull_trend |

---

## Post-deploy: 2-week review criteria

Promote to full risk (week 3+) if:
- breakdown live WR ≥ 45% (backtest 51-61%)
- ARF1 live WR ≥ 65% (backtest 77.8%)
- Portfolio DD stays < 5%
- No TPSL failsafe triggers

Demote / pause if:
- Either strategy live WR falls > 10pp below backtest
- TPSL failsafe triggers more than once in a week
- Unexplained trade sizes or duplicate orders appear
