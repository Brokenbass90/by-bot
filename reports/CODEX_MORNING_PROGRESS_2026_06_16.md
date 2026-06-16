# Codex Morning Progress — 2026-06-16

## Live / AI Map

- Server bot is alive: `bybot.service` active since `2026-06-15 07:57:16 UTC`, `DRY_RUN=false`, `trade_on=true`, `open_trades=0`, Bybit WS messages increasing.
- On-board AI can read the project map: server `bot.ai_tools.get_project_map()` returns the fresh `PROJECT_MAP.md`, and `available_tools()` includes `get_project_map`.
- Bot silence is not a crash. Current live risk is intentionally narrow:
  - `flat=0.30`, `ivb1=0.25`
  - `att1=0`, `breakdown=0/low`, `midterm=0`, `bounce/asb1=0`
  - runtime blockers: flat mostly no level touch, IVB1 no breakout/other, breakdown blocked by non-bear regime, ATT1 trendline/pivot filters.

## Funding Carry Gate

Objective: test whether carry is ready for hedged shadow / tiny canary after real costs.

30d, no-borrow but not all spot-hedgeable:

- run: `backtest_runs/funding_20260616_080542_funding_carry_30d_positive_no_borrow_stress`
- symbols: `XMRUSDT,SUIUSDT,1000PEPEUSDT`
- gate with 8 bps extra spread, basis=0: **NO-GO**
- net `$0.90` on `$300`, annualized `3.7%` (< 4% floor)
- important reality check: `XMRUSDT` and `1000PEPEUSDT` have no Bybit spot market, so they are not valid for a simple short-perp + long-spot hedge.

30d, spot-hedgeable only:

- run: `backtest_runs/funding_20260616_080859_funding_carry_30d_spot_hedgeable_stress`
- symbols: `SUIUSDT`
- gate with 8 bps extra spread, basis=0: **NO-GO**
- net `$0.10` on `$100`, annualized `1.2%`; consistency `1/2` windows.

180d, spot-hedgeable only:

- run: `backtest_runs/funding_20260616_080919_funding_carry_180d_spot_hedgeable_stress`
- symbols: `SUIUSDT,LINKUSDT,LTCUSDT,NEARUSDT,HYPEUSDT,DOGEUSDT,AVAXUSDT,BNBUSDT`
- gate with 8 bps extra spread, basis=0: **NO-GO**
- net `$7.22` on `$800`, annualized `1.8%`; positive `7/7` windows.
- stress basis `-$3`: net `$4.22`, annualized `1.1%`; positive `5/7` windows.

Verdict: carry is real but too thin on the simple Bybit spot-hedged basket. Do not open the `$100` carry canary yet. Next carry work should enforce spot availability in picker, measure live basis drift, and search better exchanges/universe/execution before promotion.

## Liquidation Sweep

- Added read-only collector: `scripts/collect_bybit_liquidations.py`.
- Added tests: `tests/test_collect_bybit_liquidations.py`.
- Server collector is running in screen: `bybit_liquidations_collector_20260616`.
- Output: `runtime/liquidations/bybit_liquidations.jsonl`.
- First event was captured: `SUIUSDT` long liquidation, about `$7.48k`.

Verdict: no historical 2-month liquidation archive was found on the server. The research engine is ready, but the data stream starts now unless we source external history.

## Breakout / IVB1 Runner

- Screen: `breakout_runner_day_20260616` still running.
- Current progress observed: around `258/324` on `inplay_breakout_retest_runner_current_v1`.
- All observed variants were **FAIL** with PF about `0.24-0.32`, negative net, and drawdown above gate.
- IVB1 second phase has not started yet at the time of this note.

Verdict so far: directional risk should stay frozen. Wait for final runner output, but current breakout evidence is strongly NO-GO.

## Tests

- Local full suite: `297 passed`.
- Server targeted:
  - carry/liquidation/promotion/AI-map tests: `29 passed`.
  - collector + liquidation research tests: `10 passed`.
