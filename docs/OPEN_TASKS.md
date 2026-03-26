# Open Tasks (Single Source of Truth)

Last update: 2026-03-05

## Done Recently
- [x] Added isolated Forex pilot module (`forex/`) with separate engine and strategy.
- [x] Added Forex CLI runner: `scripts/run_forex_backtest.py`.
- [x] Added Forex batch runner: `scripts/run_forex_pilot_batch.sh`.
- [x] Fixed Forex batch runner for macOS Bash 3.2 (no associative arrays).
- [x] Added R&D focus policy: `docs/RD_FOCUS_RULES.md`.
- [x] Added cleanup plan: `docs/RD_CLEANUP_PLAN.md`.
- [x] Added rejected candidates inventory: `docs/rd_cleanup_candidates.csv`.
- [x] Added old runs catalog: `docs/backtest_runs_catalog.csv`.
- [x] Added broker CSV converter for Forex pilot: `scripts/forex_import_csv.py` (MT5/generic -> `ts,o,h,l,c,v`).
- [x] Added Forex preset scanner: `scripts/run_forex_strategy_scan.sh` (conservative/balanced/active per pair with ranked summary).
- [x] Added one-command Forex refresh pipeline: `scripts/run_forex_dynamic_gate.sh` (fetch + data check + recent-aware universe gate + latest snapshots in `docs/`).
- [x] Added Forex combo state machine: `scripts/update_forex_combo_state.py` + `scripts/run_forex_combo_state.sh` (`ACTIVE/CANARY/BANNED` with streaks, cooldown, max-active quota, latest outputs in `docs/forex_combo_*_latest.*`).
- [x] Added Equities combo state machine: `scripts/update_equities_combo_state.py` + `scripts/run_equities_combo_state.sh` (`ACTIVE/CANARY/WATCHLIST/BANNED` over walk-forward raw output; latest snapshots in `docs/equities_combo_*_latest.*`).
- [x] Added free-history Forex fetch path via Dukascopy: `scripts/fetch_forex_dukascopy.py` + `scripts/run_forex_fetch_dukascopy.sh` (tick -> M5 aggregation).
- [x] Added monthly tax export wrapper: `scripts/run_tax_monthly_report.sh` (exports `docs/tax_monthly_latest.csv/txt`).
- [x] Added monthly operator bundle: `scripts/run_operator_monthly_report.sh` (tax + active combo snapshots + data readiness in `docs/operator_monthly_latest.{txt,json}`).

## In Progress
- [ ] Live diagnostics-driven tuning for breakout+midterm (production stack).
  - Current blocker (2026-03-04 overnight): zero entries (`breakout_try=16097`, `entry=0`; `midterm_try=682`, `entry=0`).
  - Measured reason mix: no-signal mostly `impulse` (`13230 / 16049 = 82.44%`), then `symbol` (`1938 / 16049 = 12.08%`), then `no_break` (`4.65%`).
  - Impulse-only sweep checkpoint (180d):
    - `0.80`: base `+18.88`, stress `+3.60`, trades `213` (stress)
    - `0.75`: base `+19.09`, stress `+3.96`, trades `213` (stress)
    - `0.70`: base `+19.09`, stress `+3.96`, trades `213` (stress)
  - Canary result in live (2026-03-03 17:59 UTC deploy): `BREAKOUT_IMPULSE_ATR_MULT=0.75` did not unlock entries overnight.
  - Guardrail checks:
    - `BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.20` degrades stress (180d: `96.84`, `-3.16`, `DD 7.18`) -> reject.
    - `BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.30` near flat but still worse than baseline (180d stress: `99.86`, `-0.14`, `DD 6.07`) -> reject.
  - Cached-week sanity test (7d ending `2026-03-01`, live-like profile): trades present and positive.
    - base: `11 trades`, `+1.9951` (ending `102.00`)
    - stress: `11 trades`, `+1.2041` (ending `101.20`)
  - Server restart window check (`since 2026-03-04 06:15 UTC`, 34m):
    - `breakout_try=832`, `entry=0`
    - no-signal mix: `impulse_weak=82.45%`, `impulse_body=5.53%`, `symbol=11.66%`, `no_break=0.36%`
    - infra healthy: ws connect/disconnect active, handshake timeouts `0`.
  - Added parity tool: `scripts/run_live_parity_backtest.sh` to replay base+stress with live-like parameters and auto top-N universe, so live-vs-backtest comparison is no longer manual.
  - Added universe guard in live bot: `BREAKOUT_SYMBOL_ALLOWLIST/DENYLIST` now also applied during breakout universe construction (not only in signal wrapper), removing wasted attempts on pre-denied symbols.
  - Added WS reason granularity in runtime counters (`ws_disconnect_timeout/invalid_status/closed/oserror/other`) and diagnostics breakdown in `scripts/run_live_diagnostics.sh` to isolate transport root cause before tuning signal filters.
  - Server deploy checkpoint (`2026-03-05 09:10 UTC`): post-restart 30m window shows WS transport stabilized (`connect=3`, `disconnect=0`, `handshake=0`, status `OK`), while entries remain blocked by weak signal (`impulse_weak`).
  - Live-universe mismatch note:
    - server dynamic top-16 currently includes symbols outside our 10-coin baseline (`RIVER/HYPE/PIPPIN/SAHARA/FARTCOIN/PHA/...`), so fixed-10 backtests are not 1:1 parity with live.
    - approximate replay on available live-like subset (`BTC,ETH,SOL,DOGE,ADA,NEAR`, 7d ending `2026-03-01`) stays positive:
      - base `+3.1954` (13 trades), stress `+2.2589` (13 trades)
  - 7d impulse stress sweep (same window) shows over-loosening is not helpful:
    - `1.00/0.90/0.80`: `10 trades`, `+1.55`, PF `3.546`
    - `0.75/0.65`: `11 trades`, `+1.20`, PF `2.262`
  - Next canary: keep body filter intact, investigate `symbol` blockers and split impulse diagnostics into sub-reasons (`weak/body/vol`).
- [ ] Cleanup phase 1: archive-first strategy/scripts restructuring (no destructive deletes).
  - Technical prerequisite: `backtest/run_portfolio.py` still has static imports for many rejected strategies, so physical file move must happen together with import/allowed-list pruning in one change-set.
  - Gap report generated: `docs/cleanup_gap_report.csv`
    - `prune_import_before_archive=33`
    - `archive_ready=1` (`funding_hold_v1.py`)
- [ ] Forex stabilization program (primary R&D track).
  - Data status now healthy: `docs/forex_data_status.csv` shows `ready=12/12` for majors/crosses (`EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURGBP, EURJPY, GBPJPY, AUDJPY, CADJPY`).
  - Added broker-grade year+ fetch path: `scripts/fetch_forex_oanda.py` + `scripts/run_forex_fetch_oanda.sh` (requires `OANDA_API_TOKEN`).
  - Dynamic gate result (`scripts/run_forex_dynamic_gate.sh`, tag `fx_gate_dynamic_20260304_093245`):
    - pass: `GBPUSD conservative` (`base +158.97`, `stress +105.37`, `recent_stress +56.87`, `87 trades`, `DD 86.24`)
    - fail: all other scanned pairs on current parameters and costs.
  - Multi-strategy fast gate (`scripts/run_forex_multi_strategy_gate.sh`, recent bars, 3 strategies):
    - pass candidates: `AUDJPY + breakout_continuation_session_v1` (`stress +31.67`, `21 trades`), `USDCHF + breakout_continuation_session_v1` (`stress +1.86`, `23 trades`)
    - implication: single-strategy bottleneck is real; pair+strategy routing increases candidate count.
  - Multi-strategy full-history gate (`12 pairs x 5 strategies`) confirms robustness check:
    - robust pass: `GBPUSD + trend_retest_session_v1` only.
    - example of stale profile rejected by recent filter: `EURJPY + grid_reversion_session_v1` (overall stress positive, recent stress negative).
  - Afternoon verification (`2026-03-04 14:04 UTC`, fast window `FX_MAX_BARS=4000`) produced extra temporary passes (`GBPJPY trend_retest`, `AUDJPY breakout_continuation`, `EURUSD trend_retest`, `EURJPY grid`, `AUDUSD trend_retest`), but full-history focus gate right after (`4 pairs x 3 strategies`, no bar cap) collapsed back to single robust pass: `GBPUSD trend_retest`.
  - Walk-forward delta check (`2026-03-04 14:07 UTC`) confirms stability gap:
    - `GBPUSD conservative`: monthly `2/3` positive, rolling `6/9` positive.
    - `GBPJPY conservative`: monthly `1/3` positive, rolling `4/9` positive with deep late-window drawdowns.
  - State machine bootstrapped (`2026-03-04 14:29 UTC`):
    - `docs/forex_combo_state_latest.csv` now tracks `ACTIVE/CANARY/WATCHLIST/BANNED` per `pair+strategy`.
    - strategy ID canonicalization enabled (`strategy:default`) to prevent duplicate keys in state.
    - current active set after promotion streak: `GBPUSD@trend_retest_session_v1:conservative`.
  - Added two-stage runner (`scripts/run_forex_two_stage_gate.sh`):
    - stage1: fast multi-preset scout (`max_bars` window),
    - stage2: full-history confirm on top fast candidates,
    - stage3: state update from full confirm only.
  - Added pair-specific preset `grid_reversion_session_v1:eurjpy_canary` to lock tuned EURJPY grid parameters from brute-force scan.
    - full confirm (`fx_stage_full_smoke_20260304_155121`): `EURJPY grid:eurjpy_canary base +324.63 / stress +249.40 / recent +74.74 / trades 148 / dd 97.86`.
  - Added pair-specific preset `trend_retest_session_v1:eurusd_canary` from staged EURUSD sweep.
    - checkpoint (`fx_third_combo_check_20260304_173235`): `EURUSD trend:eurusd_canary base +114.63 / stress +67.83 / recent +71.26 / trades 93 / dd 94.63`.
  - State canonicalization fix: `trend_retest_session_v1:default` is now normalized to `:conservative` in state updater to avoid duplicate combo keys.
  - Multi-preset fast scan found additional short-window positives, but full confirm still rejects them; useful for narrowing tuning targets, not for direct promotion to ACTIVE.
  - Added soft-canary policy in state updater:
    - near-pass combos (positive stress/base, sufficient trades/DD, slightly negative recent) are tracked as `CANARY` instead of dropping to `WATCHLIST`.
    - fail chain corrected: first fail keeps `CANARY`, ban only after configured fail streak.
  - Current practical split:
    - `ACTIVE`: `EURJPY@grid_reversion_session_v1:eurjpy_canary`, `GBPUSD@trend_retest_session_v1:conservative`, `EURUSD@trend_retest_session_v1:eurusd_canary`
    - `CANARY`: `EURJPY@grid_reversion_session_v1:active` (positive full-history stress, weaker stability vs canary preset).
  - Added generic combo walk-forward tool: `scripts/run_forex_combo_walkforward.py` (works for any `strategy:preset`, outputs base+stress by segment).
    - Rolling 28/7 checkpoint (`2026-03-04`):
      - `GBPUSD trend_retest:conservative`: `6/9` windows both positive (`base+stress`), but has weak Dec-Jan windows.
      - `EURJPY grid:eurjpy_canary`: `9/9` windows both positive on current 60d sample.
  - Added live filter exporter: `scripts/export_forex_live_filters.py` and wired it into `scripts/run_forex_combo_state.sh` (auto-export `ACTIVE/CANARY` as txt/csv/json/env after each state update).
  - Additional full-history branch scans (`2026-03-04`):
    - `trend_pullback_rebound_v1` (default/strict, 12 pairs): `0` gate passes.
    - `range_bounce_session_v1` (default/loose, 12 pairs): `0` gate passes.
  - Staged tuning checks (`2026-03-04`):
    - `AUDJPY breakout_continuation`: fast-window winners collapsed on full confirm (`0` strict passes).
    - `USDCAD grid_reversion`: strong fast-window scores, but full confirm failed hard (`0` strict passes, stress negative, DD > 300).
  - Trend-family full scan (`trend_retest` presets on 12 pairs): robust passes remain `GBPUSD:conservative` and `EURUSD:eurusd_canary`; no additional pair passed strict gate.
  - Full-universe two-stage confirm (`fx_stage_full_fullrun_20260304_155821`) validates 2 robust combos:
    - `EURJPY@grid_reversion_session_v1:eurjpy_canary`
    - `GBPUSD@trend_retest_session_v1:conservative`
  - Expanded pair-check gate (`fx_third_combo_check_20260304_173235`) also passes:
    - `EURUSD@trend_retest_session_v1:eurusd_canary`
  - State file status now:
    - `ACTIVE=3`, `CANARY=1`, `BANNED=0`.
    - Added anti-concentration control `max_active_per_pair` (default `1`) in state updater to avoid duplicate ACTIVE presets on same pair.
  - Active-health checkpoint (`2026-03-04 18:18 UTC`, rolling windows):
    - `EURJPY@grid_reversion_session_v1:eurjpy_canary`: `9/9` both-positive, `stress_total +778.80` (`OK`)
    - `GBPUSD@trend_retest_session_v1:conservative`: `6/9` both-positive, `stress_total +411.09` (`OK`)
    - `EURUSD@trend_retest_session_v1:eurusd_canary`: `5/9` both-positive, `stress_total +33.87` (`OK`)
  - Overnight refresh (`2026-03-05 05:30 UTC`, 12 pairs, full two-stage) re-confirmed ACTIVE=3 with updated full-history stress:
    - `EURJPY grid:eurjpy_canary` stress `+192.83`
    - `EURUSD trend:eurusd_canary` stress `+81.14`
    - `GBPUSD trend:conservative` stress `+75.93`
  - Fresh full confirm (`2026-03-05 09:22 UTC`) keeps robust core unchanged; with per-pair active cap applied, ACTIVE set is:
    - `EURJPY@grid_reversion_session_v1:eurjpy_canary`
    - `GBPUSD@trend_retest_session_v1:conservative`
    - `EURUSD@trend_retest_session_v1:eurusd_canary`
    - `EURJPY@grid_reversion_session_v1:active` tracked as `CANARY`.
  - Robustness checkpoints already positive for `GBPUSD conservative`:
    - stress1 (`spread=1.8`, `swap=-0.6`): `+105.37`
    - stress2 (`spread=2.4`, `swap=-0.8`): `+51.77`
  - Near-term goal:
    - keep 3 active forex combos in paper portfolio and monitor decay with daily gate + rolling walk-forward.
    - add fourth independent combo (different pair/logic) before live forex rollout with meaningful capital.
    - run overnight full-history multi-strategy gate (all 5 strategies) and confirm fast-scan passes are not local-noise artifacts.
    - completed (`2026-03-04`): two-stage gate now auto-includes existing `ACTIVE` combos in full-confirm shortlist (`FX_INCLUDE_ACTIVE_IN_FULL=1` by default) to prevent accidental demotion from short-window omission.
- [ ] Equities stabilization program (parallel R&D track).
  - Walk-forward gate (`2026-03-05 07:00 UTC`) produced `7` robust pass combos (top: `TSLA grid`, `META trend_retest`, `GOOGL trend_retest`).
  - State bootstrap (`2026-03-05 07:05 UTC`) initialized from raw walk-forward:
    - pass #1: `ACTIVE=0`, `CANARY=9`, `WATCHLIST=1`, `BANNED=0`.
    - pass #2 (same raw, streak promotion): `ACTIVE=6`, `CANARY=3`, `WATCHLIST=1`, `BANNED=0`.
    - active combos now include: `TSLA grid`, `META trend_retest`, `GOOGL trend_retest`, `META breakout_continuation`, `AMD breakout_continuation`, `AAPL breakout_continuation`.
- [ ] Telegram control-plane cleanup and Forex commands.
  - Problem: current bot commands/panels are mixed and hard to operate quickly.
  - Target:
    - split control sections: `crypto live`, `forex live`, `rd/scans`, `risk/execution`, `diagnostics`.
    - add explicit Forex commands (universe, gate status, active pair list, manual refresh, dry-run/live toggle per stack).
    - unify status output format and add concise “what changed since last run” block.
  - Deliverables:
    - command map doc,
    - revised Telegram handler routes,
    - quick-operate menu layout (minimal taps).

## Next Actions (Priority Order)
1. Capture next 2h crypto diagnostics window after env-order hotfix and confirm WS stays `OK/WARN` (not `CRITICAL`) before any further entry-threshold tuning.
2. Commit cleanup metadata and move rejected strategies to archive namespace with manifest.
3. Continue Forex gate refresh daily (`run_forex_dynamic_gate.sh`) and start walk-forward auto-disable rule for active pair list.
4. Extend MT5 demo set from `ACTIVE=1` to `ACTIVE>=2` by tuning one independent non-GBPJPY combo under return-aware gate (`min_stress_return_pct_est>=0`).
5. Add crypto WS noise guardrail: track keepalive timeout frequency and auto-alert when reconnect rate breaches threshold (server not broken, but stream quality is noisy).
   - implemented (`2026-03-05`): pulse-level WS watchdog with windowed deltas and `WARN/CRITICAL` Telegram alerts (`WS_HEALTH_*` envs).
6. Use new nightly runner (`scripts/run_forex_overnight_research.sh`) as default background R&D pipeline while waiting for broker API history.
7. Draft Telegram control-plane refactor plan and implement Forex command subset first.
8. Build simple pass/fail gate report for crypto candidates (base+stress).
9. Start equities R&D track (M5, US regular session): run daily fetch/check/scan, then add walk-forward gate before any paper/live step.
10. Add equities state machine (ACTIVE/CANARY/WATCHLIST/BANNED) mirroring forex flow, then keep only walk-forward-passing candidates in ACTIVE.
11. Add monthly operator report bundle (PnL + estimated tax + fees by stack) and align fields with manual Cyprus filing workflow.
12. ML overlay backlog (post-demo only): train probability/ranking model on closed-trade dataset (>=500 trades per stack), validate with strict walk-forward, and allow only score-based ranking/sizing caps while rule-based entry/exit remains mandatory.

## Blocked / Waiting
- Forex is not data-blocked anymore (`ready=12/12`).
- Main blocker shifted from candidate scarcity to data horizon/cost calibration: strict MT5 long-window full-confirm (`2026-03-06`) still yields `ACTIVE=0`, while demo-calibrated window (`max_bars=15000`, return-aware gate) yields `ACTIVE=1` (`GBPJPY trend_retest:conservative`, health `both+=37/67`).
- Additional long-window check (`max_bars=30000`, `GBPJPY/USDJPY/AUDJPY`, return-aware gate) confirms `0` strict passes; keep this as the current hard constraint for promoting any pair to AUTO demo-live.
- Current classifier (`docs/forex_live_or_kill_latest.csv`): `short_ok=9` but `long_ok=0` over latest fast/full windows; decision remains `canary-only`, no auto scaling.
- For 12m+ M5 validation: waiting for broker API token/account (or MT5/cTrader export) with stable historical pull access.
- Crypto live entries remain blocked mostly by signal quality (`impulse_weak`); WS transport had noisy windows before, but latest post-restart sample is healthy. Keep watchdog active and continue monitoring.

## Rule Reminder
- If no crypto candidate passes both base+stress for 10-14 days, shift 50% R&D to Forex.
