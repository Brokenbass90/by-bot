# ATT1 short fee/slippage stress — 2026-07-02

Candidate:

- `ATT1 short-only`
- Params from top strict-OOS grading row `r001`:

```bash
ATT1_ALLOW_LONGS=0
ATT1_ALLOW_SHORTS=1
ATT1_MAX_PIVOT_AGE=16
ATT1_MIN_PIVOTS=2
ATT1_MIN_R2=0.55
ATT1_PIVOT_LEFT=2
ATT1_PIVOT_RIGHT=3
ATT1_RSI_LONG_MAX=52
ATT1_TOUCH_ATR=0.5
```

Scope:

- 360d, end `2026-04-30`
- symbols: `BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`
- strategy: `alt_trendline_touch_v1`
- next-open execution
- `risk_pct=0.0075`, `max_positions=3`

Results:

| costs | trades | net | PF | WR | max DD | negative months | positive months | max red streak | worst month |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fee 6 / slip 2 bps | 290 | +27.77 | 1.402 | 59.3% | 6.55 | 2 | 9 | 1 | -1.57 |
| fee 8 / slip 4 bps | 297 | +21.11 | 1.288 | 58.9% | 7.67 | 2 | 9 | 1 | -2.46 |
| fee 10 / slip 5 bps | 307 | +16.53 | 1.214 | 58.6% | 8.46 | 2 | 9 | 1 | -3.03 |

Worst stress symbol split (`fee 10 / slip 5`):

| symbol | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| SOLUSDT | 37 | -1.20 | 0.890 | 54.1% |
| ADAUSDT | 35 | -0.52 | 0.949 | 51.4% |
| LINKUSDT | 43 | +1.40 | 1.119 | 58.1% |
| BTCUSDT | 24 | +1.92 | 1.423 | 66.7% |
| ETHUSDT | 30 | +2.29 | 1.312 | 56.7% |
| LTCUSDT | 52 | +3.50 | 1.310 | 61.5% |
| DOTUSDT | 41 | +3.55 | 1.360 | 58.5% |
| SUIUSDT | 45 | +5.60 | 1.494 | 62.2% |

Verdict:

- ATT1 short survives severe fee/slippage stress.
- This strengthens promotion case from tiny canary to the next controlled risk step.
- Weak symbols under worst stress: `SOLUSDT`, `ADAUSDT`; do not remove blindly yet, but monitor separately in live/shadow because they dilute the sleeve under stress.

Current live canary config check:

The live canary file `configs/att1_short_canary_20260629.env` is close to the passing family but not identical to top `r001`:

- live: `ATT1_MAX_PIVOT_AGE=24`
- live allowlist: `BTCUSDT,SOLUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`
- top `r001`: `ATT1_MAX_PIVOT_AGE=16`, broader tested universe included `ETHUSDT,ADAUSDT`.

Stress result for current live config:

| config | costs | trades | net | PF | WR | max DD | negative months | max red streak | worst month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| livecfg | fee 6 / slip 2 bps | 246 | +21.09 | 1.361 | 58.9% | 6.13 | 4 | 1 | -2.92 |
| livecfg | fee 10 / slip 5 bps | 257 | +10.85 | 1.167 | 58.0% | 7.39 | 5 | 1 | -3.64 |

Interpretation:

- Current live config is still positive under stress, but weaker and less month-stable than top `r001`.
- For a risk increase, prefer migrating the canary to the stronger `r001` geometry after explicit approval, or keep live config risk small and only collect live evidence.

Operational recommendation:

- Keep `ATT1 long` out of promotion.
- Promote only `ATT1 short` and only through `smart_risk`, breaker, expiry and edge-monitor rollback.
- First practical next step: controlled bump from tiny canary to the next risk tier after verifying live config matches the candidate params.
