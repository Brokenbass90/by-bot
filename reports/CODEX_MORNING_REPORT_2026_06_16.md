# Codex Morning Report — 2026-06-16

## Executive summary

Ночной crypto-rework дал честный `NO-GO` по ASB1/ATT1: ослабление входов подняло частоту только немного и не создало canary-кандидатов. Включать эти рукава риском сейчас нельзя — это было бы торговать надежду.

Funding-carry research дал первый зелёный механический контур: basket `INJ/XMR/WLD/SUI/ZEC/BCH/LINK/AAVE`, 180 дней, `$100` notional per symbol, net после комиссий:

- base fees: `+$27.28` на `$800` notional за 180 дней
- stress fees: `+$26.16` на `$800` notional за 180 дней

Это research-only, не live-решение: нужно добавить hedge/basis/mark-to-market/liquidation guards перед деньгами.

## Why the bot is quiet

Live process is healthy:

- `bybot.service`: active, uptime ~20h
- `DRY_RUN=false`, `trade_on=true`
- `open_trades=0`
- Bybit feed alive: `bybit_msgs > 7.7M`
- regime: `bull_trend`

Но реальные live-рукава сейчас почти все зажаты:

- `flat`: enabled, `risk_mult=0.3`
- `ivb1`: enabled, `risk_mult=0.25`
- `att1`: enabled but `risk_mult=0.0`
- `breakdown`: enabled but `risk_mult=0.0`
- `midterm`: enabled but `risk_mult=0.0`
- `asb1`: off / `0.0`

Последний trade event: `2026-06-13 18:00:15 UTC`, `flat_resistance_fade LTCUSDT`, `+0.1739`.

Runtime diagnostics since restart show the bot is scanning, not dead:

- `ivb1_try=4665`, `ivb1_no_signal=4665`
- `flat_try=46`, `flat_signal=1`
- `breakdown_try=434`, mostly `structure_idle/regime/rsi`
- `att1_try=69`, mostly `trendline` no-signal

Conclusion: silence is mostly filter/risk configuration, not process failure.

## Nightly results

### ASB1 / ATT1 entry rework

Report: `reports/ENTRY_REWORK_SWEEP_latest.md`

ASB1 best combo:

- candidate-like symbols: `0`
- symbols with trades: `4`
- total trades: `6`
- avg expectancy: `+0.235R`, but too few windows/trades

ATT1 best combo:

- candidate-like symbols: `0`
- symbols with trades: `2`
- total trades: `17`
- avg expectancy: `-0.0978R`

Verdict: no canary promotion.

### Auto-pick WF with param profiles

Report: `reports/AUTO_PICK_WF_TOP10_60_240_param_profiles_nightly.json`

Pass candidates: `[]`.

Notable weak pockets:

- ASB1 `SAFEUSDT`: `+2.951R`, but only `1/1` traded window
- ASB1 `SIGNUSDT`: `1/3` positive, weak
- ARF1 `LTCUSDT`: `1/4` positive, weak

Verdict: no live risk increase.

### Funding gate

Report: `reports/FUNDING_GATE_AB_20260615_184113.txt`

Funding is currently the best non-correlated path, but must remain research/shadow until hedge execution and basis-risk handling are proven.

## New day run started

Started server screen:

- `breakout_runner_day_20260616`

It runs:

1. `configs/autoresearch/inplay_breakout_retest_runner_current_v1.json`
   - current WLD-style 1h breakout -> 5m retest -> staged exits + runner
2. `configs/autoresearch/ivb1_live_canary_annual_focus_v1.json`
   - focused IVB1 annual validation

This targets the user screenshot pattern directly: compression breakout, shallow retest, continuation runner.

## Decision

Do not raise live crypto risk yet. Next promotion can come only from:

1. breakout/retest runner passing the gate;
2. IVB1 focus producing a real candidate;
3. funding-carry graduating from research to hedged shadow/canary.

Alpaca paper is alive, but real `$500` is not ready yet: current v38 monthly paper is holding `AMD/GE/LLY/SNOW` with broker stop protection, while intraday branches are mostly blocked by monthly positions/max-position limits. Need clean paper-cycle reconciliation before real funds.
