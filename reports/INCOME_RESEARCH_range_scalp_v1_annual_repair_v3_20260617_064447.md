# Classic Research Report

- generated_at_utc: `2026-06-17T12:44:27.542807+00:00`
- source: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260617_064447_range_scalp_v1_annual_repair_v3`
- candidates: `12`
- bear_months: `2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04`
- max_concurrent_stack_check: `3`

## #1 range_scalp_v1_annual_repair_v3_r050

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_054904_range_scalp_v1_annual_repair_v3_r050`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `147`, net `14.55`, PF `1.447`, WR `0.272`, DD `7.0870`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2026-03']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 147, 'expectancy_R': 0.099, 'profit_factor': 1.45, 'win_pct': 27.2} stacked={'trades': 139, 'expectancy_R': 0.058, 'profit_factor': 1.26, 'win_pct': 25.9} dropped=8

```text
month           pnl  trades   win%  flags
2025-04        0.06      17     29            
2025-05       -0.75      11     18  RED       
2025-06        1.00       5     20            
2025-07        0.27      12     33            
2025-08        0.35      11     27            
2025-09        1.44       2     50            
2025-10       -4.29      25     12  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.53      21     14  BEAR RED    <-- RED BEAR (fail)
2025-12        2.94      13     46  BEAR      
2026-01        2.41      10     40  BEAR      
2026-02       12.93      19     42  BEAR      
2026-03       -0.29       1      0  BEAR RED    <-- RED BEAR (fail)
```

## #2 range_scalp_v1_annual_repair_v3_r004

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_050852_range_scalp_v1_annual_repair_v3_r004`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `108`, net `16.85`, PF `1.691`, WR `0.296`, DD `6.5801`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 108, 'expectancy_R': 0.156, 'profit_factor': 1.69, 'win_pct': 29.6} stacked={'trades': 102, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 29.4} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.17      10     40            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        3.16      11     46  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02       12.19      15     40  BEAR      
```

## #3 range_scalp_v1_annual_repair_v3_r028

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_052949_range_scalp_v1_annual_repair_v3_r028`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `104`, net `16.40`, PF `1.697`, WR `0.288`, DD `6.5268`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 104, 'expectancy_R': 0.158, 'profit_factor': 1.7, 'win_pct': 28.8} stacked={'trades': 98, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 28.6} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.46       8     38            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        2.14      10     40  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02       12.48      14     43  BEAR      
```

## #4 range_scalp_v1_annual_repair_v3_r052

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_055038_range_scalp_v1_annual_repair_v3_r052`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `102`, net `16.15`, PF `1.697`, WR `0.284`, DD `6.5038`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 102, 'expectancy_R': 0.158, 'profit_factor': 1.7, 'win_pct': 28.4} stacked={'trades': 96, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 28.1} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.97      10     40            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.46       8     38            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        2.14      10     40  BEAR      
2026-01        2.22       5     60  BEAR      
2026-02       12.48      14     43  BEAR      
```

## #5 range_scalp_v1_annual_repair_v3_r003

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_050801_range_scalp_v1_annual_repair_v3_r003`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `107`, net `14.28`, PF `1.586`, WR `0.290`, DD `6.5801`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `neutral` bare={'trades': 107, 'expectancy_R': 0.134, 'profit_factor': 1.59, 'win_pct': 29.0} stacked={'trades': 102, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 29.4} dropped=5

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.17      10     40            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        3.16      11     46  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02        9.63      14     36  BEAR      
```

## #6 range_scalp_v1_annual_repair_v3_r027

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_052900_range_scalp_v1_annual_repair_v3_r027`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `103`, net `13.84`, PF `1.588`, WR `0.282`, DD `6.5268`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `neutral` bare={'trades': 103, 'expectancy_R': 0.134, 'profit_factor': 1.59, 'win_pct': 28.2} stacked={'trades': 98, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 28.6} dropped=5

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.46       8     38            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        2.14      10     40  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02        9.91      13     38  BEAR      
```

## #7 range_scalp_v1_annual_repair_v3_r049

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_054818_range_scalp_v1_annual_repair_v3_r049`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `145`, net `10.73`, PF `1.329`, WR `0.262`, DD `7.0870`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2026-03']`
- stack: `neutral` bare={'trades': 145, 'expectancy_R': 0.074, 'profit_factor': 1.33, 'win_pct': 26.2} stacked={'trades': 139, 'expectancy_R': 0.058, 'profit_factor': 1.26, 'win_pct': 25.9} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.06      17     29            
2025-05       -0.75      11     18  RED       
2025-06        1.00       5     20            
2025-07        0.27      12     33            
2025-08        0.35      11     27            
2025-09        1.44       2     50            
2025-10       -4.29      25     12  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.53      21     14  BEAR RED    <-- RED BEAR (fail)
2025-12        2.94      13     46  BEAR      
2026-01        1.16       9     33  BEAR      
2026-02       10.37      18     39  BEAR      
2026-03       -0.29       1      0  BEAR RED    <-- RED BEAR (fail)
```

## #8 range_scalp_v1_annual_repair_v3_r051

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_054951_range_scalp_v1_annual_repair_v3_r051`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `101`, net `13.58`, PF `1.587`, WR `0.277`, DD `6.5038`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `neutral` bare={'trades': 101, 'expectancy_R': 0.134, 'profit_factor': 1.59, 'win_pct': 27.7} stacked={'trades': 96, 'expectancy_R': 0.121, 'profit_factor': 1.54, 'win_pct': 28.1} dropped=5

```text
month           pnl  trades   win%  flags
2025-04        0.97      10     40            
2025-05       -0.24       9     22  RED       
2025-06        2.49       6     33            
2025-07        0.46       8     38            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        2.14      10     40  BEAR      
2026-01        2.22       5     60  BEAR      
2026-02        9.91      13     38  BEAR      
```

## #9 range_scalp_v1_annual_repair_v3_r340

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_132848_range_scalp_v1_annual_repair_v3_r340`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `99`, net `16.95`, PF `1.758`, WR `0.293`, DD `6.2306`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 99, 'expectancy_R': 0.171, 'profit_factor': 1.76, 'win_pct': 29.3} stacked={'trades': 93, 'expectancy_R': 0.134, 'profit_factor': 1.6, 'win_pct': 29.0} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.97      10     40            
2025-05       -0.24       9     22  RED       
2025-06        2.77       5     40            
2025-07        0.73       7     43            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11        0.08      15     20  BEAR      
2025-12        2.14      10     40  BEAR      
2026-01        2.22       5     60  BEAR      
2026-02       12.48      14     43  BEAR      
```

## #10 range_scalp_v1_annual_repair_v3_r292

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_124702_range_scalp_v1_annual_repair_v3_r292`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `106`, net `17.40`, PF `1.730`, WR `0.302`, DD `6.5103`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 106, 'expectancy_R': 0.164, 'profit_factor': 1.73, 'win_pct': 30.2} stacked={'trades': 100, 'expectancy_R': 0.129, 'profit_factor': 1.58, 'win_pct': 30.0} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.77       5     40            
2025-07        0.44       9     44            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        3.16      11     46  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02       12.19      15     40  BEAR      
```

## #11 range_scalp_v1_annual_repair_v3_r338

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_132717_range_scalp_v1_annual_repair_v3_r338`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `143`, net `14.69`, PF `1.462`, WR `0.273`, DD `7.0769`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11', '2026-03']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 143, 'expectancy_R': 0.103, 'profit_factor': 1.46, 'win_pct': 27.3} stacked={'trades': 135, 'expectancy_R': 0.06, 'profit_factor': 1.27, 'win_pct': 25.9} dropped=8

```text
month           pnl  trades   win%  flags
2025-04        0.06      17     29            
2025-05       -0.75      11     18  RED       
2025-06        1.29       4     25            
2025-07        0.13       9     33            
2025-08        0.35      11     27            
2025-09        1.44       2     50            
2025-10       -4.29      25     12  BEAR RED    <-- RED BEAR (fail)
2025-11       -1.53      21     14  BEAR RED    <-- RED BEAR (fail)
2025-12        2.94      13     46  BEAR      
2026-01        2.41      10     40  BEAR      
2026-02       12.93      19     42  BEAR      
2026-03       -0.29       1      0  BEAR RED    <-- RED BEAR (fail)
```

## #12 range_scalp_v1_annual_repair_v3_r316

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_130807_range_scalp_v1_annual_repair_v3_r316`
- strategies: `alt_range_scalp_v1`
- symbols: `ADAUSDT;LINKUSDT;DOTUSDT;LTCUSDT;SUIUSDT;ATOMUSDT;SOLUSDT`
- summary: trades `102`, net `16.96`, PF `1.738`, WR `0.294`, DD `6.4922`
- autoresearch_passed: `True` fail_reasons: ``
- monthly_verdict: `FAIL` reason: `red bear months: ['2025-10', '2025-11']`
- stack: `control-plane HURTS (fix obвязку, not strategy)` bare={'trades': 102, 'expectancy_R': 0.166, 'profit_factor': 1.74, 'win_pct': 29.4} stacked={'trades': 96, 'expectancy_R': 0.13, 'profit_factor': 1.58, 'win_pct': 29.2} dropped=6

```text
month           pnl  trades   win%  flags
2025-04        0.60      11     36            
2025-05       -0.24       9     22  RED       
2025-06        2.77       5     40            
2025-07        0.73       7     43            
2025-08       -1.69      10     10  RED       
2025-09        1.74       1    100            
2025-10       -4.25      13      0  BEAR RED    <-- RED BEAR (fail)
2025-11       -0.18      16     19  BEAR RED    <-- RED BEAR (fail)
2025-12        2.14      10     40  BEAR      
2026-01        2.84       6     67  BEAR      
2026-02       12.48      14     43  BEAR      
```
