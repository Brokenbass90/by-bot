# ATT1 density revalidate verdict — 2026-07-02

Run:

- `backtest_runs/autoresearch_20260702_075058_att1_density_top_revalidate_20260626`
- Spec: `configs/autoresearch/att1_density_top_revalidate_20260626.json`
- Scope: 360d, end `2026-04-30`, next-open execution, `fee_bps=6`, `slippage_bps=2`, `max_positions=3`.
- Symbols: `BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`.

Result:

- 12/12 grid candidates passed the configured revalidate constraints.
- Top rows: `r005` / `r011`.

Top candidate (`r005`):

| metric | value |
| --- | ---: |
| trades | 442 |
| net PnL | +36.67 |
| PF | 1.331 |
| WR | 59.0% |
| max DD | 4.668 |
| positive months | 9 |
| negative months | 2 |
| max negative streak | 1 |
| worst month | -2.501 |

Parameters:

```json
{
  "ATT1_MAX_PIVOT_AGE": "24",
  "ATT1_MIN_PIVOTS": "2",
  "ATT1_MIN_R2": "0.55",
  "ATT1_PIVOT_LEFT": "2",
  "ATT1_PIVOT_RIGHT": "3",
  "ATT1_RSI_LONG_MAX": "52",
  "ATT1_TOUCH_ATR": "0.5"
}
```

Side split for `r005`:

| side | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| long | 194 | +6.48 | 1.122 | 56.7% |
| short | 248 | +30.19 | 1.522 | 60.9% |

Symbol split for `r005`:

| symbol | trades | net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| ADAUSDT | 63 | -0.08 | 0.996 | 52.4% |
| LTCUSDT | 59 | +2.95 | 1.208 | 55.9% |
| SOLUSDT | 62 | +3.34 | 1.209 | 56.5% |
| BTCUSDT | 29 | +4.68 | 2.111 | 72.4% |
| SUIUSDT | 61 | +5.43 | 1.329 | 60.7% |
| LINKUSDT | 66 | +5.83 | 1.325 | 59.1% |
| DOTUSDT | 53 | +6.90 | 1.536 | 62.3% |
| ETHUSDT | 49 | +7.62 | 1.750 | 61.2% |

Verdict:

- This is the strongest current crypto evidence.
- It supports keeping `ATT1 short-only` as the primary crypto canary.
- It does **not** authorize a risk increase yet: this is a 360d revalidate grid, not strict rolling OOS.
- Next required gate before any risk increase: strict rolling-OOS with `wf_folds + oos_selector`, side-specific (`ATT1 short` separately from `ATT1 long`).
- `ATT1 long` is not dead, but should be treated as a separate lower-priority sleeve because its PF is materially weaker.

Operational note:

- Current live risk should remain tiny until strict OOS passes.
- If strict OOS passes, promote via `smart_risk` / breaker / expiry, not a manual jump.
