# Bear Chop Repair — 2026-06-11

## Problem

The current crypto core is not all-weather. The 365d package still has positive net PnL, but the recent regime is failing:

- `core_live_v1` 365d ending 2026-06-11: net `+25.48`, PF `1.160`, 782 trades, max DD `10.37`, red months `6/13`.
- Last three months are red: 2026-04 `-3.92`, 2026-05 `-5.78`, 2026-06 `-3.56`.
- 90d ending 2026-06-11: net `-6.44`, PF `0.855`, max DD `11.47`.

Main recent damage:

- 90d long side: `-7.02`; short side: `+0.58`.
- 90d by strategy: ATT1 `-4.44`, ARF1 `-1.52`, BD1/inplay `-0.49`.
- Live 30d health: `alt_inplay_breakdown_v1` degraded, live PF about `0.28`.

## Bear Defense Matrix

90d ending 2026-06-11:

| Case | Trades | Net | PF | Max DD | Verdict |
|---|---:|---:|---:|---:|---|
| Current core | 221 | `-6.44` | `0.855` | `11.47` | fail |
| Short-only core | 159 | `-3.02` | `0.937` | `10.75` | improves but still fail |
| ARF1 + BD1 | 123 | `-6.13` | `0.842` | `12.21` | fail |
| ATT1 short-only | 36 | `+5.20` | `1.630` | `3.27` | candidate |
| ARF1 only | 39 | `-1.55` | `0.875` | `6.03` | fail |
| BD1 only | 84 | `-4.89` | `0.816` | `8.38` | fail |

ATT1 short-only is the only clearly positive 90d bear candidate. It is not a full all-weather fix: monthly PnL was 2026-03 `-0.08`, 2026-04 `-2.10`, 2026-05 `-0.35`, 2026-06 `+7.73`.

## Implemented Guard

Patched `scripts/build_regime_state.py` so `bear_chop` emits:

- `ENABLE_ATT1_TRADING=1`
- `ATT1_ALLOW_LONGS=0`
- `ATT1_ALLOW_SHORTS=1`
- `ENABLE_BREAKDOWN_TRADING=0`

Also updated `configs/regime_overlay_bear_chop.env` for consistency and added `tests/test_build_regime_state_decisions.py`.

Validation:

- `python3 tests/test_build_regime_state_decisions.py`
- `python3 -m py_compile scripts/build_regime_state.py tests/test_build_regime_state_decisions.py`
- `python3 scripts/build_regime_state.py --dry-run` confirmed the expected bear_chop keys.

## Live Hotfix

Server hotfix applied without bot restart:

- Patched `/root/by-bot/configs/regime_orchestrator_latest.env`.
- Patched `/root/by-bot/scripts/build_regime_state.py` so hourly cron should preserve the guard.
- Patched `/root/by-bot/.env` for next safe restart: `ENABLE_BREAKDOWN_TRADING=0`, `BREAKDOWN_RISK_MULT=0.0`, `ATT1_ALLOW_LONGS=0`, `ATT1_ALLOW_SHORTS=1`.
- Patched `/root/by-bot/smart_pump_reversal_bot.py` so hot reload reads `runtime/strategy_pause.env` before recalculating strategy risk. This fixes the bug where the live-vs-backtest monitor could write a zero-risk pause while the running bot kept old in-memory risk until restart.
- Backups were written next to both files with `.bak_codex_bearfix_*`.

Current live positions at hotfix time remained two ATT1 shorts (`DOTUSDT`, `LTCUSDT`); no TP/SL or position close was touched.

Validation:

- Server `py_compile` passed for `/root/by-bot/smart_pump_reversal_bot.py` and `/root/by-bot/scripts/build_regime_state.py`.
- Server `.env` confirmed `ENABLE_BREAKDOWN_TRADING=0`, `BREAKDOWN_RISK_MULT=0.0`, `ATT1_ALLOW_LONGS=0`, `ATT1_ALLOW_SHORTS=1`.

Caveat: the currently running bot process was not restarted because it has open positions. Full effective-runtime confirmation happens after positions close and a safe restart/reload is performed.

## Open Work

- BD1/inplay repair sweep is running under `screen bd1_elder_repair_20260611`.
- Early BD1 repair rows are failing; first 74 checked candidates all failed the PF/net/month gates. Best early net/PF is still below promotion gates.
- Elder v3 repair runs after the BD1 limited sweep in the same screen.
- Full 365d package run is still calculating remaining package cases.

## Interim Verdict

Do not promote ATT2, micro-scalper, grid, or legacy BD1 based on current evidence.

Use `ATT1 short-only` as a defensive bear_chop guard, not as a final portfolio. Red-month repair still needs independent sleeves: liquidity sweep reversal, pair-stat-arb/funding, and a repaired range/mean-reversion sleeve that survives April-May style chop.
