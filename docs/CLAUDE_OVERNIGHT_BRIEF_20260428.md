# Claude Overnight Brief — 2026-04-28

## What Codex Deployed

- Live crypto canary v2 is deployed on the server and pushed to GitHub.
- Commit: `3017840 Deploy crypto income canary v2 config`.
- Active live sleeves:
  - `alt_trendline_touch_v1` / `ATT1`
  - `alt_resistance_fade_v1` / `flat`
  - `btc_eth_midterm_pullback`
- Disabled in live:
  - `breakdown`, `range`, `IVB1`, `elder`, `vwap`, all v7 sleeves.
- Verified replay for canary v2:
  - `+45.44%`, PF `1.493`, WR `59.9%`, max DD `5.95%`,
    `456` trades, `1` red month over 11 populated monthly windows.
- Server verification after restart:
  - `bybot.service` active.
  - Heartbeat fresh.
  - WebSocket messages flowing.
  - `ws_guard=0`.
  - Open trades at check: `0`.

## Important Live-Control Detail

`REGIME_OVERLAY_ENABLE=0` is now set in the canary env.

Reason: raw `regime_orchestrator_latest.env` can still contain broad live
strategy flags in `bear_chop`. The bot applies allocator after regime at
startup, but direct raw regime hot-reload could briefly re-enable disabled
sleeves between allocator reloads. For canary v2, regime state still updates,
but live strategy gating comes through `portfolio_allocator_latest.env` built
from `portfolio_allocator_policy_canary_v2.json`.

## Server Backup Points

- Server backup stamp: `20260428_170228`.
- `.env` backups:
  - `state/env_backups/.env.20260428_170228.bak`
  - `state/env_backups/.env.20260428_170353.bak`
- Policy/health backups:
  - `runtime/server_backups/*before_crypto_canary_v2_20260428_170228.*`

## Overnight Research Started Locally

Launcher:

- `scripts/run_overnight_income_research_20260428.sh`
- Launcher log:
  - `logs/overnight_income_research_launcher_20260428.log`
- Current run directory:
  - `logs/overnight_income_research_20260428_172114/`
- Remaining-sleeves run directory:
  - `logs/overnight_income_research_20260428_172439/`
- Manifest:
  - `logs/overnight_income_research_20260428_172114/manifest.tsv`
  - `logs/overnight_income_research_20260428_172439/manifest.tsv`
- Max parallel jobs: `3`
- Cache mode: `BACKTEST_CACHE_ONLY=1`

Queued research specs:

- `configs/autoresearch/att1_focused_pivot_sweep_v2_nocache.json`
- `configs/autoresearch/flat_live_universe_repair_v2.json`
- `configs/autoresearch/breakdown_v1_recent180_focus_v1.json`
- `configs/autoresearch/inplay_breakout_retest_focus_v1.json`
- `configs/autoresearch/support_bounce_v1_annual_repair_v2.json`
- `configs/autoresearch/ivb1_wider_universe_v1.json`
- `configs/autoresearch/range_scalp_v1_annual_focus_v2.json`
- `configs/autoresearch/pump_fade_v4r_bear_window.json`
- `configs/autoresearch/flat_slope_symbol_baskets_v3_expand.json`
- `configs/autoresearch/elder_ts_v3_macro_relax_v1.json`
- Alpaca command:
  - `bash scripts/run_equities_intraday_dynamic_v3_shadow_annual_segments.sh`

Early read while jobs are running:

- `flat_live_universe_repair_v2` already finished.
  - Best: PF `1.513`, WR `53.7%`, net `+11.78`, DD `3.40`.
  - This is a useful ARF1 improvement candidate, but it still needs portfolio
    additivity against canary v2 before any live change.
- `range_scalp_v1_annual_focus_v2` already finished.
  - Best: PF `1.849`, net `+18.89`, DD `4.54`.
  - It is worth a portfolio additivity test, but do not promote directly:
    standalone range was previously dangerous inside full stack.
- `breakdown_v1_recent180_focus_v1` looked promising early.
  - Finished best: PF `1.833`, net `+21.73`, DD `8.69`.
  - This is the most interesting next repair lane if final ranked results hold.
- `inplay_breakout_retest_focus_v1` looked weak early.
  - First checked rows were still FAIL around PF `0.51-0.52`.
  - Needs final ranked result before rejecting, but early signal is poor.

## Claude Next Best Use

1. Do not touch live canary until 48-72h live evidence arrives.
2. Parse overnight `ranked_results.csv` files in `backtest_runs/autoresearch_*`.
3. For any PASS candidate:
   - Run annual standalone confirmation.
   - Run dynamic control-plane replay.
   - Run additivity test against `ATT1 + flat + midterm`.
4. Highest expected payoff:
   - `breakdown_v1` repair if final ranked PF/DD holds.
   - ARF1/flat improvement if it improves the canary red month without killing
     trade count.
   - Elder v3 only if it becomes tradeful enough; otherwise use Elder as a
     filter/regime tool rather than as a live trading sleeve.
5. Keep inplay/breakout in repair until it proves additivity. Do not add it to
   live based on standalone pockets.
