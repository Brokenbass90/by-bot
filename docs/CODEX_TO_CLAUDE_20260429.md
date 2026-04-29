# Codex -> Claude Handoff — 2026-04-29

## Current Live State

- `crypto_income_live_canary_v2` is deployed on the server.
- Live active crypto sleeves: `ATT1 + flat/ARF1 + btc_eth_midterm_pullback`.
- v7 sleeves, breakdown, range, IVB1, elder, vwap and other unvalidated sleeves are disabled in live canary.
- Server check at `2026-04-29 05:51 UTC`: `bybot.service` active, heartbeat fresh, router OK, allocator OK, `safe_mode=0`, open trades `0`.
- Web service was checked active (`trading-journal-web.service` active).
- Live bot is scanning, but no trades yet. Latest pulses show `ATT1` and `flat` try counters rising, mostly `no_signal`, `cooldown`, and `portfolio skip`.

## Overnight Research Survived

The overnight local research did complete after the app restart. Useful ranked outputs are present under:

- `logs/overnight_income_research_20260428_172114/`
- `logs/overnight_income_research_20260428_172439/`
- `backtest_runs/autoresearch_20260428_*`

Best standalone/research results from the overnight set:

| Candidate | Result | Verdict |
|---|---:|---|
| `range_scalp_v1_annual_focus_v2` | PF `1.849`, DD `4.54`, trades `104`, net `+18.89` | strongest repair candidate, but must pass portfolio additivity |
| `breakdown_v1_recent180_focus_v1` | PF `1.833`, DD `8.69`, trades `126`, net `+21.73` | standalone edge alive, but control-plane/portfolio is still suspicious |
| `elder_ts_v3_macro_relax_v1` | PF `2.715`, DD `0.67`, trades `7`, net `+2.09` | too sparse as engine; better as filter |
| `ivb1_wider_universe_v1` | PF `1.584`, DD `1.78`, trades `39`, net `+4.57` | small candidate, but not enough alone |
| `support_bounce_v1_annual_repair_v2` | PF `1.405`, DD `9.05`, trades `129`, net `+19.22` | not promotion-ready; DD fails gate |
| `flat_slope_symbol_baskets_v3_expand` | PF `4.969`, DD `1.30`, trades `13`, net `+8.55` | confirms sloped pockets, but too thin |
| `pump_fade_v4r_bear_window` | PF `0.0`, trades `1`, net `-0.27` | reject for now |

## Additivity Tests Run By Codex

Generated local-only test files in `runtime/additivity_20260429/` and ran dynamic 360d stitched tests against canary v2 baseline.

Baseline canary v2:

- return `+45.44%`
- PF `1.4927`
- WR `59.87%`
- DD `5.95%`
- trades `456`
- negative months `1`

Results:

| Case | Return | PF | WR | DD | Trades | Red Months | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| canary v2 baseline | `+45.44%` | `1.493` | `59.9%` | `5.95%` | `456` | `1` | keep live |
| canary + breakdown | `+30.16%` | `1.200` | `56.4%` | `9.73%` | `811` | `4` | reject live; root-cause needed |
| canary + range_chop | `+41.06%` | `1.342` | `51.3%` | `5.96%` | `589` | `1` | possible activity add-on, but not better than baseline |
| canary + IVB1 | `+44.58%` | `1.478` | `59.8%` | `5.74%` | `460` | `1` | harmless but barely additive |

Strategy attribution:

- Baseline: `ATT1 +32.51`, `ARF1 +12.92`.
- `canary + breakdown`: `breakdown_v1 -9.32` over `346` trades; this confirms the full-stack regression.
- `canary + range_chop`: `range_scalp -2.26` over `132` trades; activity improves but it is not additive as configured.
- `canary + IVB1`: `IVB1 -0.79` over only `3` trades; not useful yet.

## Codex View

- Do not expand live with `breakdown_v1`, `range_scalp`, or `IVB1` yet.
- Keep `crypto_income_live_canary_v2` running 48-72 hours for real live evidence.
- The first repair track should be `breakdown_v1` root-cause diff: standalone `+21.73` vs full-stack `-9.32` attribution in the canary additivity replay.
- `range_scalp` is the best activity candidate, but it needs another tuning pass specifically inside portfolio/control-plane, not standalone.
- `IVB1` should stay research-only until it produces meaningful trades in dynamic replay.
- Elder v3 should be used first as a filter/regime quality layer, not as a profit engine.

## Horizontal vs Sloped Levels

Yes: we should test the same trading ideas on both horizontal and sloped geometry, but not with identical parameters.

- Horizontal families: `ARF1`, `ASB1`, `range_scalp`, `breakdown_v1`, `inplay_breakout`.
- Sloped families: `ATT1`, `alt_sloped_channel_v1`, `alt_sloped_momentum_v1`, `sloped_break_retest_v1`, `sloped_resistance_choch_v1`.
- Current live proof is strongest for sloped touch (`ATT1`) plus horizontal resistance fade (`ARF1`).
- The next search should explicitly pair horizontal and sloped variants by regime: range/chop gets horizontal levels, trend/impulse gets sloped/trendline logic.

## Alpaca Note

The overnight Alpaca `intraday_dynamic_v3_shadow` annual segment runner completed, but all four WF raw files contain only headers. That means no clean intraday income candidate passed the current annual segment gate. Existing best Alpaca lane remains monthly v38/hybrid as a compounder, not income. Broker-side real trailing/stop execution is still required before real money.

## Recommended Next Work

1. Let live canary v2 continue unchanged unless it misbehaves.
2. Run trade-by-trade root-cause diff for `breakdown_v1`: standalone winner vs canary+breakdown dynamic replay.
3. Run a portfolio-native range sweep: range enabled only in chop, lower risk, stricter no-trend filter, and maybe Elder/ER filter.
4. Search sloped/horizontal pairs: ATT1 + ARF1 is proven; next pair should be sloped breakout/retest + horizontal range scalp, each with regime-specific policy.
5. Revive AI workflow on server: nightly research queue, DeepSeek weekly, operator snapshot with PnL/backtest/live counters. AI may propose, but not auto-deploy.
