# Classic Research Report

- generated_at_utc: `2026-06-19T05:25:49.256169+00:00`
- source: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260619_052154_range_scalp_v1_annual_repair_v3`
- candidates: `4`
- bear_months: `2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04`
- max_concurrent_stack_check: `3`

## #1 range_scalp_v1_annual_repair_v3_r004

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_082458_range_scalp_v1_annual_repair_v3_r004`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `108`, net `16.61`, PF `1.682`, WR `0.296`, DD `6.6773`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 108, 'expectancy_R': 0.154, 'profit_factor': 1.68, 'win_pct': 29.6} stacked={'trades': 105, 'expectancy_R': 0.105, 'profit_factor': 1.46, 'win_pct': 28.6} dropped=3

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.47       6     33            
2025-07        0.07      10     40            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        3.16      11     46  BEAR      
2026-01        2.73       6     67  BEAR      
2026-02       12.19      15     40  BEAR      
```

## #2 range_scalp_v1_annual_repair_v3_r003

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_082359_range_scalp_v1_annual_repair_v3_r003`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `107`, net `14.05`, PF `1.576`, WR `0.290`, DD `6.6773`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 107, 'expectancy_R': 0.131, 'profit_factor': 1.58, 'win_pct': 29.0} stacked={'trades': 105, 'expectancy_R': 0.105, 'profit_factor': 1.46, 'win_pct': 28.6} dropped=2

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.47       6     33            
2025-07        0.07      10     40            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        3.16      11     46  BEAR      
2026-01        2.73       6     67  BEAR      
2026-02        9.63      14     36  BEAR      
```

## #3 range_scalp_v1_annual_repair_v3_r002

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_082300_range_scalp_v1_annual_repair_v3_r002`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `160`, net `13.69`, PF `1.383`, WR `0.269`, DD `8.4135`
- autoresearch_passed: `False` fail_reasons: `neg_months>4`
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2026-03']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 160, 'expectancy_R': 0.086, 'profit_factor': 1.38, 'win_pct': 26.9} stacked={'trades': 155, 'expectancy_R': 0.04, 'profit_factor': 1.18, 'win_pct': 25.2} dropped=5

```text
month           pnl  trades   win%  flags
2025-04       -0.83      20     25  RED       
2025-05       -0.75      11     18  RED       
2025-06        2.47       6     33            
2025-07       -0.51      12     33  RED       
2025-08       -0.33      13     23  RED       
2025-09        1.44       2     50            
2025-10       -4.53      26     12  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.78      22     14  BEAR RED    <-- RED BEAR (fail)
2025-12        3.13      17     41  BEAR      
2026-01        2.83      11     46  BEAR      
2026-02       12.86      19     42  BEAR      
2026-03       -0.29       1      0  BEAR RED    <-- RED BEAR (fail)
```

## #4 range_scalp_v1_annual_repair_v3_r001

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260619_082201_range_scalp_v1_annual_repair_v3_r001`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `161`, net `9.15`, PF `1.250`, WR `0.255`, DD `8.4135`
- autoresearch_passed: `False` fail_reasons: `neg_months>4`
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2026-03']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 161, 'expectancy_R': 0.057, 'profit_factor': 1.25, 'win_pct': 25.5} stacked={'trades': 158, 'expectancy_R': 0.034, 'profit_factor': 1.15, 'win_pct': 24.7} dropped=3

```text
month           pnl  trades   win%  flags
2025-04       -0.83      20     25  RED       
2025-05       -0.75      11     18  RED       
2025-06        2.47       6     33            
2025-07       -0.51      12     33  RED       
2025-08       -0.33      13     23  RED       
2025-09        1.44       2     50            
2025-10       -4.53      26     12  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.78      22     14  BEAR RED    <-- RED BEAR (fail)
2025-12        3.13      17     41  BEAR      
2026-01        1.67      10     40  BEAR      
2026-02       10.02      19     37  BEAR      
2026-03       -0.82       3      0  BEAR RED    <-- RED BEAR (fail)
```
