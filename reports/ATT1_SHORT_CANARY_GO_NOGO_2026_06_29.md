# ATT1 short-only crypto canary — Go/No-Go + runbook (2026-06-29)

Strategy: `alt_trendline_touch_v1`, **short side only**.
Author: Claude (central). Recheck/deploy: Codex + owner.
Artifacts shipped with this doc:
- `configs/att1_short_canary_20260629.env` — deployable canary env (PROPOSAL).
- `bot/strategy_breaker.py` — tested auto-rollback breaker (11/11 tests green).
- `tests/test_strategy_breaker.py` — unit tests.

---

## Verdict: NOT YET — build is ready, launch is gated

The canary package is built and the safety brake is tested. Live risk must wait for
the non-negotiable guardrail: execution-accurate replay → DD/monthly/side forensics
→ shadow → tiny canary. Two gates need owner/Codex input first.

### GO gates (all required)
1. **Research confirms ATT1 short-only is still the pick.** The queued server jobs
   `spike_fade_v3_link_short_bounded` and `package_att1_short_ars1_additivity_20260628`
   must finish. Send me the final ranking logs and I will interpret:
   - does ARS1 help ATT1's DD / monthly stability, or stay research-only?
   - is short-only still net+, PF>1 after 6/2 bps fees, ≤3 red months, red streak ≤2?
2. **Execution-accurate replay** of ATT1 short-only on current cache (next-open,
   fees/slippage 6/2, closed-candle parity) reproduces the +37 / PF~1.3 / DD~5-6 class.
3. **Shadow sanity**: ATT1 already runs shadow; confirm recent shadow signals look
   sane (no degenerate clustering) before flipping risk on.

If 1–3 pass → tiny canary at `ATT1_RISK_MULT=0.10`, short-only, with the breaker armed.

---

## Why short-only / why these numbers
Best server revalidation (`att1_density_top_revalidate_..._r005`): 457 trades, net
+37.35, PF 1.325, WR 58.9%, DD ~4.67–6.41, 2 red months, max red streak 1; short side
+28.02 vs long +9.33. The long leg is kept for a future bull regime, not this canary.

## Auto-rollback brake (new, tested)
`bot/strategy_breaker.py` reads realized ATT1 closes from `trades.db` and forces a
rollback when any of these hit (defaults in the env file):
- realized net ≤ `ATT1_BREAKER_HARD_NET_PNL` (-3.0) over ≥6 closes → **hard pause**;
- `ATT1_BREAKER_MAX_CONSEC_LOSSES` (5) consecutive losers → **hard pause** (works on
  small samples too);
- net ≤ `ATT1_BREAKER_SOFT_NET_PNL` (-1.5) → **soft cut** to ×0.50;
- `ATT1_CANARY_EXPIRY_UTC` (2026-07-20) reached → **hard pause until human renews**.

Tested with synthetic DBs: aggregate/streak math, soft cut, hard block, consecutive-loss
kill, min-trades gate, expiry (past/future), lookback exclusion, missing-DB safety.

## Monolith wiring (one insertion — apply on GO; Codex rechecks)
Mirror the existing BREAKDOWN_BREAKER pattern.

1) Near the ATT1 env defs (~line 745), add:
```python
from bot.strategy_breaker import breaker_state as _strategy_breaker_state  # top imports

ATT1_BREAKER_ENABLE = _env_bool("ATT1_BREAKER_ENABLE", True)
ATT1_BREAKER_LOOKBACK_DAYS = max(3, int(os.getenv("ATT1_BREAKER_LOOKBACK_DAYS", "21") or 21))
ATT1_BREAKER_MIN_TRADES = max(1, int(os.getenv("ATT1_BREAKER_MIN_TRADES", "6") or 6))
ATT1_BREAKER_SOFT_NET_PNL = float(os.getenv("ATT1_BREAKER_SOFT_NET_PNL", "-1.5") or -1.5)
ATT1_BREAKER_SOFT_MULT = max(0.05, min(1.0, float(os.getenv("ATT1_BREAKER_SOFT_MULT", "0.50") or 0.50)))
ATT1_BREAKER_HARD_NET_PNL = float(os.getenv("ATT1_BREAKER_HARD_NET_PNL", "-3.0") or -3.0)
ATT1_BREAKER_MAX_CONSEC_LOSSES = int(os.getenv("ATT1_BREAKER_MAX_CONSEC_LOSSES", "5") or 5)
ATT1_BREAKER_ALERT_COOLDOWN_SEC = max(300, int(os.getenv("ATT1_BREAKER_ALERT_COOLDOWN_SEC", "1800") or 1800))
ATT1_CANARY_EXPIRY_UTC = os.getenv("ATT1_CANARY_EXPIRY_UTC", "").strip()

def _att1_breaker_state():
    return _strategy_breaker_state(
        TRADE_DB_PATH, "alt_trendline_touch_v1",
        enable=ATT1_BREAKER_ENABLE,
        lookback_days=ATT1_BREAKER_LOOKBACK_DAYS,
        min_trades=ATT1_BREAKER_MIN_TRADES,
        soft_net_pnl=ATT1_BREAKER_SOFT_NET_PNL,
        soft_mult=ATT1_BREAKER_SOFT_MULT,
        hard_net_pnl=ATT1_BREAKER_HARD_NET_PNL,
        max_consec_losses=ATT1_BREAKER_MAX_CONSEC_LOSSES,
        expiry_utc=ATT1_CANARY_EXPIRY_UTC or None,
    )
```

2) In the ATT1 entry path, right after `stop_pct = ...` and before
`dyn_usd = calc_notional_usd_from_stop_pct(stop_pct, risk_mult=ATT1_RISK_MULT)`
(~line 10529), insert:
```python
    _att1_brk = _att1_breaker_state()
    if _att1_brk.get("blocked"):
        _diag_inc("att1_skip_breaker")
        tg_trade_throttled(f"att1_breaker:block:{symbol}",
            f"🛑 ATT1 BLOCKED {symbol}: {_att1_brk.get('reason','breaker')}",
            ATT1_BREAKER_ALERT_COOLDOWN_SEC)
        return
    _att1_brk_mult = float(_att1_brk.get("risk_mult", 1.0) or 1.0)
    _att1_effective_risk_mult = float(ATT1_RISK_MULT) * _att1_brk_mult
```
then change the sizing line(s) to use `_att1_effective_risk_mult` instead of
`ATT1_RISK_MULT` (also in the minqty fallback branch).

3) (optional) add `"att1_breaker": _att1_breaker_state()` to the heartbeat dict
(~line 2994) for observability in proof-of-life.

After wiring: `python -m py_compile smart_pump_reversal_bot.py` and run
`pytest tests/test_strategy_breaker.py tests/test_strategy_pause_contract.py -q`.

## Launch steps (owner, on server, after GO)
```bash
cd /root/by-bot
# 1) shadow→canary: source the canary env on top of live env, restart service
set -a; source configs/att1_short_canary_20260629.env; set +a
# 2) confirm posture in proof-of-life: ATT1 live x0.10 short-only, others paused
# 3) watch first closes; the breaker auto-pauses on the gates above
```

## Rollback
Set `ATT1_RISK_MULT=0.0` (explicit pause) and restart — or let the breaker/expiry do it.
No code revert needed; the wiring is inert while ATT1 is paused.
