# Classic Research Report

- generated_at_utc: `2026-06-16T12:53:45.172022+00:00`
- source: `/root/by-bot/backtest_runs/portfolio_20260616_124447_range_scalp_v1_annual_focus_v2_r019`
- candidates: `1`
- bear_months: `2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04`
- max_concurrent_stack_check: `3`

## #1 range_scalp_v1_annual_focus_v2_r019

- run_dir: `/root/by-bot/backtest_runs/portfolio_20260616_124447_range_scalp_v1_annual_focus_v2_r019`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT`
- summary: trades `74`, net `15.30`, PF `1.955`, WR `0.324`, DD `3.8460`
- autoresearch_passed: `` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2026-03']`
- stack: `neutral` bare={'trades': 74, 'expectancy_R': 0.207, 'profit_factor': 1.96, 'win_pct': 32.4} stacked={'trades': 74, 'expectancy_R': 0.207, 'profit_factor': 1.96, 'win_pct': 32.4} dropped=0

```text
month           pnl  trades   win%  flags
2025-04        0.05       9     33            
2025-05        0.01       5     20            
2025-06        3.59       2    100            
2025-07       -0.78       5     20  RED       
2025-08       -0.92       9     22  RED       
2025-09        1.74       1    100            
2025-10       -2.51      12      8  BEAR RED    <-- RED BEAR (fail)
2025-11        2.20       8     38  BEAR      
2025-12        2.36       6     50  BEAR      
2026-01        2.19       5     60  BEAR      
2026-02        7.66      11     36  BEAR      
2026-03       -0.29       1      0  BEAR RED    <-- RED BEAR (fail)
```
