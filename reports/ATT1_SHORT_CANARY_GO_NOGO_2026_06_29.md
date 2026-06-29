# ATT1 short-only crypto canary — Go/No-Go + runbook (2026-06-29)

Strategy: `alt_trendline_touch_v1`, **short side only**.
Author: Claude (central). Recheck/deploy: Codex + owner.
Artifacts shipped with this doc:
- `configs/att1_short_canary_20260629.env` — deployable canary env (PROPOSAL).
- `bot/strategy_breaker.py` — tested auto-rollback breaker (11/11 tests green).
- `tests/test_strategy_breaker.py` — unit tests.

---

## Verdict: TECHNICALLY CLOSE — build is ready, launch still gated

The canary package is built and the safety brake is tested. Codex additionally
ran an exact cache-only ATT1 short-only replay on 2026-06-29 using the strong
top-revalidate parameters and next-open execution. The numbers are green enough
for a tiny canary **after** monolith breaker wiring + shadow sanity.

Exact ATT1 short-only replay (`att1_short_only_exact_local_20260629`):

| trades | net | PF | WR | max DD | red months | red streak |
|---:|---:|---:|---:|---:|---:|---:|
| 296 | +28.17 | 1.402 | 59.1% | 6.59 | 2 | 1 |

Symbol split: SUI +7.30, DOT +6.12, LTC +5.02, ETH +3.58, LINK +2.79,
BTC +2.10, ADA +1.78, SOL -0.51.

The previous `package_att1_short_ars1_additivity_20260628` is **not** a valid
final verdict: its control rows used a weaker ATT1 baseline (`net~9`, PF~1.12,
5-6 red months), not the proven short-only config above. Codex prepared a
corrected spec: `configs/autoresearch/package_att1_strong_short_ars1_additivity_20260629.json`.

### GO gates (all required)
1. **Execution-accurate replay** — green locally: +28.17, PF 1.402, DD 6.59,
   2 red months. Server replay should be captured/archived before live if possible.
2. **Monolith breaker wiring** — `bot/strategy_breaker.py` exists and is tested,
   but is not yet wired into `smart_pump_reversal_bot.py`. Do not run an open-ended
   canary without this or equivalent manual expiry/rollback.
3. **Shadow sanity**: ATT1 already runs shadow; confirm recent shadow signals look
   sane (no degenerate clustering) before flipping risk on.
4. **Package additivity**: ARS1 is not required for first canary. Include it only
   if the corrected package test improves DD/monthly stability over the ATT1-only
   control rows.

If 1–3 pass → tiny canary at `ATT1_RISK_MULT=0.10`, short-only, with breaker/expiry armed.

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
