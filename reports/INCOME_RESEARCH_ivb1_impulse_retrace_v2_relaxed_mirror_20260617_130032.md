# Classic Research Report

- generated_at_utc: `2026-06-18T21:04:27.759483+00:00`
- source: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260617_130032_ivb1_impulse_retrace_v2_relaxed_mirror`
- candidates: `12`
- bear_months: `2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03, 2026-04`
- max_concurrent_stack_check: `3`

## #1 ivb1_impulse_retrace_v2_relaxed_mirror_r1358

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_143520_ivb1_impulse_retrace_v2_relaxed_mirror_r1358`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `287`, net `7.15`, PF `1.116`, WR `0.526`, DD `7.1263`
- autoresearch_passed: `False` fail_reasons: `pf<1.2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 287, 'expectancy_R': 0.025, 'profit_factor': 1.12, 'win_pct': 52.6} stacked={'trades': 248, 'expectancy_R': 0.03, 'profit_factor': 1.15, 'win_pct': 53.2} dropped=39

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        1.24      20     55            
2025-06        1.35      21     62            
2025-07       -3.40      26     38  RED       
2025-08        0.35      20     60            
2025-09        0.92       8     50            
2025-10        6.96      29     72  BEAR      
2025-11        1.47      42     57  BEAR      
2025-12        3.77      34     59  BEAR      
2026-01        2.40      27     48  BEAR      
2026-02       -4.37      39     38  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #2 ivb1_impulse_retrace_v2_relaxed_mirror_r1374

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_152757_ivb1_impulse_retrace_v2_relaxed_mirror_r1374`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `285`, net `6.88`, PF `1.112`, WR `0.526`, DD `7.7078`
- autoresearch_passed: `False` fail_reasons: `pf<1.2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 285, 'expectancy_R': 0.024, 'profit_factor': 1.11, 'win_pct': 52.6} stacked={'trades': 247, 'expectancy_R': 0.032, 'profit_factor': 1.16, 'win_pct': 53.4} dropped=38

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.52      19     53            
2025-06        1.34      21     62            
2025-07       -3.39      26     38  RED       
2025-08        0.35      20     60            
2025-09        1.40       7     57            
2025-10        6.94      29     72  BEAR      
2025-11        1.47      42     57  BEAR      
2025-12        3.76      34     59  BEAR      
2026-01        2.39      27     48  BEAR      
2026-02       -4.37      39     38  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #3 ivb1_impulse_retrace_v2_relaxed_mirror_r1354

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_142203_ivb1_impulse_retrace_v2_relaxed_mirror_r1354`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `302`, net `6.55`, PF `1.102`, WR `0.523`, DD `7.6653`
- autoresearch_passed: `False` fail_reasons: `pf<1.2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 302, 'expectancy_R': 0.022, 'profit_factor': 1.1, 'win_pct': 52.3} stacked={'trades': 261, 'expectancy_R': 0.023, 'profit_factor': 1.11, 'win_pct': 52.5} dropped=41

```text
month           pnl  trades   win%  flags
2025-04       -5.59      17     18  RED       
2025-05        1.24      20     55            
2025-06        1.27      23     61            
2025-07       -3.31      27     37  RED       
2025-08        0.32      21     57            
2025-09        0.63       9     44            
2025-10        7.45      32     75  BEAR      
2025-11        1.60      42     57  BEAR      
2025-12        3.38      35     57  BEAR      
2026-01        2.43      27     48  BEAR      
2026-02       -4.27      42     40  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #4 ivb1_impulse_retrace_v2_relaxed_mirror_r590

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_211532_ivb1_impulse_retrace_v2_relaxed_mirror_r590`
- strategies: `impulse_volume_breakout_v1`
- symbols: `DOGEUSDT;LINKUSDT;SOLUSDT;ADAUSDT`
- summary: trades `245`, net `6.30`, PF `1.122`, WR `0.527`, DD `8.0524`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;dd>8.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 245, 'expectancy_R': 0.026, 'profit_factor': 1.12, 'win_pct': 52.7} stacked={'trades': 227, 'expectancy_R': 0.033, 'profit_factor': 1.16, 'win_pct': 53.7} dropped=18

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.77      17     53            
2025-06        0.72      18     56            
2025-07       -3.38      26     38  RED       
2025-08        0.09      19     58            
2025-09        1.24       7     57            
2025-10        6.46      26     73  BEAR      
2025-11        0.16      33     54  BEAR      
2025-12        2.07      30     53  BEAR      
2026-01        2.65      23     52  BEAR      
2026-02       -0.96      25     48  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #5 ivb1_impulse_retrace_v2_relaxed_mirror_r1357

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_143205_ivb1_impulse_retrace_v2_relaxed_mirror_r1357`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `287`, net `4.59`, PF `1.075`, WR `0.526`, DD `6.9447`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;net<5.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 287, 'expectancy_R': 0.016, 'profit_factor': 1.07, 'win_pct': 52.6} stacked={'trades': 251, 'expectancy_R': 0.023, 'profit_factor': 1.11, 'win_pct': 53.4} dropped=36

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.85      20     55            
2025-06        1.43      21     62            
2025-07       -3.04      26     38  RED       
2025-08        0.41      20     60            
2025-09        0.75       8     50            
2025-10        6.37      29     72  BEAR      
2025-11        1.50      42     57  BEAR      
2025-12        3.75      34     59  BEAR      
2026-01        1.00      27     48  BEAR      
2026-02       -4.85      39     38  BEAR RED    <-- RED BEAR (fail)
2026-03        1.36       7     86  BEAR      
```

## #6 ivb1_impulse_retrace_v2_relaxed_mirror_r606

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_214941_ivb1_impulse_retrace_v2_relaxed_mirror_r606`
- strategies: `impulse_volume_breakout_v1`
- symbols: `DOGEUSDT;LINKUSDT;SOLUSDT;ADAUSDT`
- summary: trades `244`, net `6.33`, PF `1.123`, WR `0.529`, DD `8.5047`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;dd>8.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 244, 'expectancy_R': 0.026, 'profit_factor': 1.12, 'win_pct': 52.9} stacked={'trades': 226, 'expectancy_R': 0.035, 'profit_factor': 1.17, 'win_pct': 54.0} dropped=18

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.31      17     53            
2025-06        0.71      18     56            
2025-07       -3.37      26     38  RED       
2025-08        0.09      19     58            
2025-09        1.72       6     67            
2025-10        6.46      26     73  BEAR      
2025-11        0.16      33     54  BEAR      
2025-12        2.07      30     53  BEAR      
2026-01        2.65      23     52  BEAR      
2026-02       -0.96      25     48  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #7 ivb1_impulse_retrace_v2_relaxed_mirror_r1370

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_151504_ivb1_impulse_retrace_v2_relaxed_mirror_r1370`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `300`, net `6.29`, PF `1.098`, WR `0.523`, DD `8.3325`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;dd>8.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 300, 'expectancy_R': 0.021, 'profit_factor': 1.1, 'win_pct': 52.3} stacked={'trades': 260, 'expectancy_R': 0.025, 'profit_factor': 1.12, 'win_pct': 52.7} dropped=40

```text
month           pnl  trades   win%  flags
2025-04       -5.59      17     18  RED       
2025-05        0.52      19     53            
2025-06        1.27      23     61            
2025-07       -3.29      27     37  RED       
2025-08        0.31      21     57            
2025-09        1.11       8     50            
2025-10        7.44      32     75  BEAR      
2025-11        1.60      42     57  BEAR      
2025-12        3.37      35     57  BEAR      
2026-01        2.42      27     48  BEAR      
2026-02       -4.28      42     40  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #8 ivb1_impulse_retrace_v2_relaxed_mirror_r1373

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_152445_ivb1_impulse_retrace_v2_relaxed_mirror_r1373`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `285`, net `4.32`, PF `1.071`, WR `0.526`, DD `7.6488`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;net<5.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 285, 'expectancy_R': 0.015, 'profit_factor': 1.07, 'win_pct': 52.6} stacked={'trades': 250, 'expectancy_R': 0.025, 'profit_factor': 1.12, 'win_pct': 53.6} dropped=35

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.13      19     53            
2025-06        1.42      21     62            
2025-07       -3.02      26     38  RED       
2025-08        0.41      20     60            
2025-09        1.23       7     57            
2025-10        6.36      29     72  BEAR      
2025-11        1.50      42     57  BEAR      
2025-12        3.73      34     59  BEAR      
2026-01        0.99      27     48  BEAR      
2026-02       -4.84      39     38  BEAR RED    <-- RED BEAR (fail)
2026-03        1.36       7     86  BEAR      
```

## #9 ivb1_impulse_retrace_v2_relaxed_mirror_r1390

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260618_161938_ivb1_impulse_retrace_v2_relaxed_mirror_r1390`
- strategies: `impulse_volume_breakout_v1`
- symbols: `BTCUSDT;ETHUSDT;SOLUSDT;LINKUSDT;DOGEUSDT;ADAUSDT`
- summary: trades `279`, net `5.08`, PF `1.083`, WR `0.513`, DD `7.7042`
- autoresearch_passed: `False` fail_reasons: `pf<1.2`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 279, 'expectancy_R': 0.018, 'profit_factor': 1.08, 'win_pct': 51.3} stacked={'trades': 242, 'expectancy_R': 0.025, 'profit_factor': 1.12, 'win_pct': 52.1} dropped=37

```text
month           pnl  trades   win%  flags
2025-04       -5.68      14      7  RED       
2025-05        0.80      19     53            
2025-06        1.19      20     60            
2025-07       -3.38      26     38  RED       
2025-08        0.95      19     63            
2025-09        0.91       8     50            
2025-10        6.91      29     72  BEAR      
2025-11        1.09      37     54  BEAR      
2025-12        3.21      35     57  BEAR      
2026-01        2.32      27     48  BEAR      
2026-02       -4.65      38     37  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #10 ivb1_impulse_retrace_v2_relaxed_mirror_r589

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_211321_ivb1_impulse_retrace_v2_relaxed_mirror_r589`
- strategies: `impulse_volume_breakout_v1`
- symbols: `DOGEUSDT;LINKUSDT;SOLUSDT;ADAUSDT`
- summary: trades `245`, net `4.41`, PF `1.086`, WR `0.527`, DD `7.8341`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;net<5.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 245, 'expectancy_R': 0.018, 'profit_factor': 1.09, 'win_pct': 52.7} stacked={'trades': 228, 'expectancy_R': 0.024, 'profit_factor': 1.12, 'win_pct': 53.5} dropped=17

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.55      17     53            
2025-06        0.80      18     56            
2025-07       -3.02      26     38  RED       
2025-08        0.15      19     58            
2025-09        1.07       7     57            
2025-10        5.93      26     73  BEAR      
2025-11        0.25      33     54  BEAR      
2025-12        2.05      30     53  BEAR      
2026-01        1.47      23     52  BEAR      
2026-02       -1.28      25     48  BEAR RED    <-- RED BEAR (fail)
2026-03        1.36       7     86  BEAR      
```

## #11 ivb1_impulse_retrace_v2_relaxed_mirror_r586

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_210650_ivb1_impulse_retrace_v2_relaxed_mirror_r586`
- strategies: `impulse_volume_breakout_v1`
- symbols: `DOGEUSDT;LINKUSDT;SOLUSDT;ADAUSDT`
- summary: trades `254`, net `5.34`, PF `1.100`, WR `0.524`, DD `8.3193`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;dd>8.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 254, 'expectancy_R': 0.021, 'profit_factor': 1.1, 'win_pct': 52.4} stacked={'trades': 236, 'expectancy_R': 0.028, 'profit_factor': 1.14, 'win_pct': 53.4} dropped=18

```text
month           pnl  trades   win%  flags
2025-04       -5.29      16     19  RED       
2025-05        0.77      17     53            
2025-06        0.72      18     56            
2025-07       -3.29      27     37  RED       
2025-08        0.06      20     55            
2025-09        0.96       8     50            
2025-10        6.66      28     75  BEAR      
2025-11        0.16      33     54  BEAR      
2025-12        2.05      30     53  BEAR      
2026-01        2.63      23     52  BEAR      
2026-02       -1.50      27     48  BEAR RED    <-- RED BEAR (fail)
2026-03        1.41       7     86  BEAR      
```

## #12 ivb1_impulse_retrace_v2_relaxed_mirror_r605

- run_dir: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260617_214733_ivb1_impulse_retrace_v2_relaxed_mirror_r605`
- strategies: `impulse_volume_breakout_v1`
- symbols: `DOGEUSDT;LINKUSDT;SOLUSDT;ADAUSDT`
- summary: trades `244`, net `4.45`, PF `1.087`, WR `0.529`, DD `8.2855`
- autoresearch_passed: `False` fail_reasons: `pf<1.2;dd>8.0;net<5.0`
- monthly_verdict: `FAIL` reason: `red bear months: ['2026-02']`
- stack: `neutral` bare={'trades': 244, 'expectancy_R': 0.018, 'profit_factor': 1.09, 'win_pct': 52.9} stacked={'trades': 227, 'expectancy_R': 0.026, 'profit_factor': 1.13, 'win_pct': 53.7} dropped=17

```text
month           pnl  trades   win%  flags
2025-04       -4.94      14     14  RED       
2025-05        0.09      17     53            
2025-06        0.80      18     56            
2025-07       -3.01      26     38  RED       
2025-08        0.15      19     58            
2025-09        1.56       6     67            
2025-10        5.94      26     73  BEAR      
2025-11        0.25      33     54  BEAR      
2025-12        2.06      30     53  BEAR      
2026-01        1.47      23     52  BEAR      
2026-02       -1.28      25     48  BEAR RED    <-- RED BEAR (fail)
2026-03        1.36       7     86  BEAR      
```
