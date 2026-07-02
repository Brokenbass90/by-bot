# Morning research verdict — 2026-07-02

Дата снятия: 2026-07-02 morning, Asia/Nicosia.

## Короткий вердикт

Ночь была полезной, но не дала нового crypto-live рукава, который можно честно разморозить сегодня.

Что получили:

- ARF2 / range-fade: **NO-GO для live**. Новые уровни увеличили частоту, но edge не появился.
- FX: **есть 3 demo/canary-кандидата**, но нет ACTIVE-кандидата после full confirm.
- Pair-arb: **NO-GO** в проверенной матрице, все 80 вариантов FAIL.
- Server ATT1+ARS1: есть положительные варианты, но это пока **не сильнее, чем ATT1 solo**, и не доказывает, что ARS1 надо добавлять.
- Elder canonical rewrite: **жёсткий FAIL**, серверный sweep остановлен как бесполезная нагрузка.
- Live crypto: бот жив, но реально торгует только `att1 x0.10`, сделок новых нет.

## 1. ARF2 overnight

Источники:

- `reports/research/arf2_overnight_20260701/diagnostic/summary.md`
- `reports/research/arf2_overnight_20260701/portfolio_summaries.md`

### Diagnostic direct chain

| variant | raw | filled | netR | PF | WR |
|---|---:|---:|---:|---:|---:|
| old | 5 | 5 | -1.58 | 0.524 | 40.0% |
| unified | 39 | 39 | -4.38 | 0.846 | 33.3% |
| unified_minrange1 | 57 | 57 | -8.43 | 0.801 | 33.3% |
| unified_retest025/035/045 | 4 | 4 | -1.22 | 0.633 | 25.0% |
| unified_level_v12 | 56 | 12 | -12.03 | 0.156 | 8.3% |
| unified_level_v24 | 56 | 22 | -21.89 | 0.167 | 9.1% |

Read:

- `unified_levels` fixed silence, not profitability.
- `retest_quality` improved selectivity but killed frequency and still lost in direct R model.
- `level_entry` on ARF2 fade is bad with current geometry: fills are low quality, not edge.

### Portfolio replay

| tag | trades | net | PF | WR | DD |
|---|---:|---:|---:|---:|---:|
| unified_retest025/035/045 | 3 | +0.45 | 1.991 | 66.7% | 0.45 |
| old | 6 | +0.26 | 1.204 | 66.7% | 0.79 |
| unified | 52 | -1.85 | 0.899 | 44.2% | 7.41 |
| unified_minrange1 | 54 | -2.40 | 0.872 | 42.6% | 8.08 |
| unified_level_v12/v24 | 0 | 0 | 0 | 0 | 0 |

Decision:

- Do **not** canary ARF2.
- Do **not** promote “3 trades PF 1.99”; too few trades.
- Next useful ARF2 work is not another grid. It needs logic change: fade only after exhaustion / failed breakout, not simply “at resistance”.

## 2. FX gate

Источники:

- `backtest_runs/forex_multi_strategy_gate_fx_stage_fast_20260701_203420/`
- `backtest_runs/forex_multi_strategy_gate_fx_stage_full_20260701_203652/`
- `docs/forex_live_filter_latest.env`
- `docs/forex_combo_state_latest.csv`

Fast scout showed many attractive rows, especially GBPJPY/GBPUSD trend-retest pockets.

Full confirm:

- `GATE PASS`: none.
- State update:
  - ACTIVE = 0
  - CANARY = 3
  - WATCHLIST = 122
  - BANNED = 3

Current canary list:

```text
GBPJPY@trend_retest_session_v1:gbpjpy_stability_b
GBPJPY@trend_retest_session_v1:conservative
GBPUSD@trend_retest_session_v1:gbpjpy_stability_b
```

Decision:

- FX is **not ready for live/OANDA real money**.
- FX is eligible for **demo canary only** after execution bridge check.
- Positive direction: FX has more statistical mass than current crypto range, but full-confirm still rejected active promotion.

## 3. Pair stat-arb

Источник:

- `reports/PAIR_ARB_MATRIX_20260701_204131.md`

Result:

- 80/80 variants FAIL.
- Best row: `SOLUSDT/ETHUSDT`, lookback 168, z 2.4/0.5/3.5:
  - ret +0.01%
  - PF 14.42
  - 75 trades
  - but worst fold -7.08%, only 9/15 positive folds -> FAIL.

Read:

- High PF here is misleading because returns/folds are unstable.
- Pair-arb stays research. No live.

## 4. Server ATT1+ARS1 additivity

Server completed 96 `package_att1_strong_short_ars1_additivity_20260629` summaries.

Best stable-looking rows:

| run | trades | net | PF | WR | DD |
|---|---:|---:|---:|---:|---:|
| r001-r016 identical pocket | 320 | +24.79 | 1.316 | 57.8% | 8.18 |
| r036 | 346 | +24.42 | 1.304 | 56.4% | 8.24 |
| r020 | 355 | +24.19 | 1.300 | 55.8% | 8.23 |

But earlier stack comparison said ATT1 short solo was stronger than ATT1+ARS1 package. Current additivity rows are positive, but not enough to override that conclusion without side/symbol/month breakdown.

The best DD-controlled row is more relevant for canary:

| run | trades | net | PF | WR | DD |
|---|---:|---:|---:|---:|---:|
| r068 | 284 | +19.17 | 1.300 | 56.7% | 6.61 |

r068 composition:

- ATT1 short: 257 trades, +19.32
- ARS1: 27 trades, -0.15
- Therefore ARS1 is not additive enough for live.
- r068 env uses the reduced symbol set `BTC,SOL,LINK,LTC,DOT,SUI` and ATT1 geometry:
  `MAX_PIVOT_AGE=24`, `MIN_R2=0.55`, `TOUCH_ATR=0.50`.

Decision:

- Keep live as `ATT1 short-only x0.10`.
- Do **not** add ARS1 to live yet.
- Align the ATT1 canary env with r068 geometry, but keep risk tiny.
- Next: live reload only after confirming `open_trades=0`.

## 5. Elder canonical rewrite

Server sweep status:

- 2700+ completed Elder runs were inspected.
- Nonzero rows are catastrophically bad: best PF around 0.36, net around -94R, DD around 94R.
- Latest rows had 0 trades.

Action taken:

- Stopped current Elder research process on server.
- Confirmed `bybot.service` remained active.

Decision:

- Elder is not a standalone engine.
- Keep as possible filter/confluence only.
- Do not spend server time on Elder standalone grids.

## 6. Live bot status

Server proof-of-life:

```text
STATUS: ALIVE | regime=bear_chop | dry_run=False | open_trades=0
LIVE risk>0: att1 x0.10
shadow risk=0: bounce1, flat, ivb1, midterm, range
last trade: 12.0d ago
```

Read:

- Bot is not globally blocked.
- It is alive but waiting for ATT1 trendline setup.
- Horizontal/range legs are still correctly not live-risk because ARF2/range evidence did not pass.

## Next actions

### P0 — today

1. Pull server top ATT1+ARS1 trades for r016:
   - monthly breakdown;
   - per-strategy contribution;
   - compare against ATT1 solo.
   Goal: decide if ARS1 is harmful, neutral, or useful only in specific months.

2. Deploy/run H4 real-data smoke only if required scripts are on server:
   - server has real Bybit liquidations JSONL;
   - server currently lacks `backtest/liquidation_sweep_run.py`;
   - do not run proxy H4 again.

3. Keep crypto live unchanged:
   - ATT1 short-only tiny canary stays.
   - No ARF2/range/pair-arb live promotion.

### P1

1. FX demo-canary preparation:
   - no real money;
   - use the 3 current CANARY combos only;
   - verify execution bridge and reporting.

2. ARF2 rewrite direction:
   - from “short at resistance” to “failed breakout/exhaustion at resistance”;
   - include pump_exhaustion / breakout_confirm, not just unified_levels.

3. Alpaca:
   - still the cleanest first real-money path once account/key/funding are ready.

## Bottom line

This night prevented bad promotions. It did not unlock a new crypto sleeve.

That is not emotionally satisfying, but it is correct operationally:

- ARF2 failed;
- pair-arb failed;
- FX has demo candidates only;
- Elder standalone is dead;
- ATT1 remains the only current crypto live sleeve.

Next real chance for crypto is not “more of the same range grid”; it is either:

- ATT1 short-only proven with cleaner monthly/side/symbol evidence;
- H4 liquidation/cascade with real data;
- rewritten ARF2 as failed-breakout exhaustion, then preflight/OOS.
