# Classic Research Report

- generated_at_utc: `2026-06-19T05:23:18.828898+00:00`
- source: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260619_050525_vwap_mean_reversion_v1_annual_repair_v2`
- candidates: `2`
- bear_months: `2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04`
- max_concurrent_stack_check: `3`

## #1 vwap_mean_reversion_v1_annual_repair_v2_r002

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_081230_vwap_mean_reversion_v1_annual_repair_v2_r002`
- strategies: `alt_vwap_mean_reversion_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;ADAUSDT;DOTUSDT;LTCUSDT;SUIUSDT`
- summary: trades `3912`, net `-98.53`, PF `0.545`, WR `0.439`, DD `98.5341`
- autoresearch_passed: `False` fail_reasons: `pf<1.15;dd>10.0;net<4.0;neg_months>4;neg_streak>2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03']`
- stack: `neutral` bare={'trades': 3912, 'expectancy_R': -0.025, 'profit_factor': 0.54, 'win_pct': 43.9} stacked={'trades': 3410, 'expectancy_R': -0.026, 'profit_factor': 0.54, 'win_pct': 44.1} dropped=502

```text
month           pnl  trades   win%  flags
2025-04      -15.17     229     46  RED       
2025-05      -30.05     320     38  RED       
2025-06      -12.96     352     49  RED       
2025-07      -16.54     360     40  RED       
2025-08       -8.14     361     41  RED       
2025-09       -6.26     339     45  RED       
2025-10       -2.72     339     45  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.24     325     50  BEAR RED    <-- RED BEAR (fail)
2025-12       -2.90     315     39  BEAR RED    <-- RED BEAR (fail)
2026-01       -1.48     349     44  BEAR RED    <-- RED BEAR (fail)
2026-02       -0.54     304     45  BEAR RED    <-- RED BEAR (fail)
2026-03       -0.52     319     45  BEAR RED    <-- RED BEAR (fail)
```

## #2 vwap_mean_reversion_v1_annual_repair_v2_r001

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_080533_vwap_mean_reversion_v1_annual_repair_v2_r001`
- strategies: `alt_vwap_mean_reversion_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;ADAUSDT;DOTUSDT;LTCUSDT;SUIUSDT`
- summary: trades `4256`, net `-99.33`, PF `0.534`, WR `0.429`, DD `99.3308`
- autoresearch_passed: `False` fail_reasons: `pf<1.15;dd>10.0;net<4.0;neg_months>4;neg_streak>2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03']`
- stack: `neutral` bare={'trades': 4256, 'expectancy_R': -0.023, 'profit_factor': 0.53, 'win_pct': 42.9} stacked={'trades': 3647, 'expectancy_R': -0.024, 'profit_factor': 0.53, 'win_pct': 43.0} dropped=609

```text
month           pnl  trades   win%  flags
2025-04      -12.56     247     49  RED       
2025-05      -35.75     350     37  RED       
2025-06      -12.80     372     48  RED       
2025-07      -17.34     399     40  RED       
2025-08       -7.65     386     40  RED       
2025-09       -5.55     361     44  RED       
2025-10       -2.26     367     45  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.78     361     45  BEAR RED    <-- RED BEAR (fail)
2025-12       -2.19     356     37  BEAR RED    <-- RED BEAR (fail)
2026-01       -0.81     382     44  BEAR RED    <-- RED BEAR (fail)
2026-02       -0.32     329     45  BEAR RED    <-- RED BEAR (fail)
2026-03       -0.32     346     44  BEAR RED    <-- RED BEAR (fail)
```
