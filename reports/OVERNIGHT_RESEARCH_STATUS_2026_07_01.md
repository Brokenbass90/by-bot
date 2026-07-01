# Overnight research status — 2026-07-01

Цель ночи: не добавлять новые гипотезы, а загрузить локальный Mac и сервер уже готовыми проверками, чтобы утром получить конкретные PASS/FAIL-кандидаты.

## Local Mac screens

### 1. `arf2_overnight_20260701`

Команда:

```bash
screen -dmS arf2_overnight_20260701 bash -lc 'cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 && /usr/bin/caffeinate -dimsu bash scripts/run_arf2_overnight_20260701.sh > logs/manual_research/arf2_overnight_20260701.log 2>&1'
```

Что проверяет:

- ARF2 baseline vs `unified_levels`;
- варианты с `retest_quality`;
- варианты с `level_entry` maker-limit validity 12/24;
- portfolio replay матрицу по тем же вариантам.

Пути:

- log: `logs/manual_research/arf2_overnight_20260701.log`
- outputs: `reports/research/arf2_overnight_20260701/`

Early read:

- old ARF2 почти молчит и минусует;
- `unified_levels` повышает частоту, но без дополнительных фильтров пока не даёт edge;
- retest-фильтр резко режет частоту; утром нужен итог по `level_entry`/portfolio summary.

### 2. `fx_gate_overnight_20260701`

Команда:

```bash
screen -dmS fx_gate_overnight_20260701 bash -lc 'cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 && /usr/bin/caffeinate -dimsu bash scripts/run_forex_two_stage_gate.sh > logs/manual_research/fx_gate_overnight_20260701.log 2>&1'
```

Что проверяет:

- FX two-stage gate на готовых локальных M5 CSV;
- стратегии: trend retest, range bounce, breakout continuation, grid reversion, trend pullback;
- это не порт крипто-логики, а отдельный FX/CFD-трек.

Пути:

- log: `logs/manual_research/fx_gate_overnight_20260701.log`
- outputs: `backtest_runs/forex_multi_strategy_gate_*`
- current/latest docs: `docs/forex_combo_active_latest.*`, `docs/forex_live_canary_combos_latest.*`

### 3. `pair_arb_matrix_overnight_20260701`

Команда:

```bash
screen -dmS pair_arb_matrix_overnight_20260701 bash -lc 'cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 && /usr/bin/caffeinate -dimsu python3 scripts/run_pair_arb_matrix.py --limit 80 > logs/manual_research/pair_arb_matrix_overnight_20260701.log 2>&1'
```

Что проверяет:

- bounded pair-stat-arb matrix на локальном crypto cache;
- market-neutral трек, отдельно от directional price-action;
- первые ETH/BTC карманы уже FAIL, но это только начало матрицы.

Пути:

- log: `logs/manual_research/pair_arb_matrix_overnight_20260701.log`
- outputs: `reports/PAIR_ARB_MATRIX_*.md/json`

## Server state

Live-VPS не перегружается дополнительными sweep:

- live bot stays active;
- liquidation collector active;
- running research: `package_att1_strong_short_ars1_additivity_20260629`, latest seen `r048`.

Latest completed server rows before night:

| run | trades | net | PF | WR | DD |
|---|---:|---:|---:|---:|---:|
| r043 | 367 | +23.25 | 1.276 | 55.0% | 7.99 |
| r044 | 371 | +22.40 | 1.267 | 54.7% | 8.85 |
| r045 | 610 | +6.65 | 1.055 | 41.3% | 11.25 |
| r046 | 625 | +8.70 | 1.077 | 44.6% | 9.92 |
| r047 | 522 | +13.47 | 1.124 | 45.2% | 9.01 |

Read: ATT1+ARS1 additivity is not yet a clean canary; some rows are positive, but PF/DD are not consistently strong enough.

## Morning checklist

Run:

```bash
screen -ls
tail -120 logs/manual_research/arf2_overnight_20260701.log
tail -120 logs/manual_research/fx_gate_overnight_20260701.log
tail -120 logs/manual_research/pair_arb_matrix_overnight_20260701.log
find reports/research/arf2_overnight_20260701 -maxdepth 4 -type f | sort
ls -1dt backtest_runs/forex_multi_strategy_gate_* | head
ls -1t reports/PAIR_ARB_MATRIX_*.md | head
```

Decision rules:

- ARF2 only moves toward canary if side-specific variant has enough trades, PF > 1.2, DD controlled, and not one-symbol concentration.
- FX moves only to demo/canary candidate list after full-stage confirmation, not fast scout only.
- Pair-arb/carry stays research unless WF has robust folds and fee sensitivity passes.
- No new live crypto risk is added from overnight results without controlled unpause: replay → OOS/robust gate → shadow → tiny canary → breaker/expiry.
