# Codex Handoff — 2026-06-08

## What Was Applied

- Read and triaged `AUDIT_AND_FIXES_2026_06_08.md`.
- Confirmed the P0 live execution bug: live fills were overwriting strategy-designed TP/SL with global `TP_PCT` / `SL_PCT` for modern strategies.
- Committed and pushed:
  - `0f792e2 Preserve strategy TP/SL on live fills`
  - `6f320a8 Add robustness and research scaffolds`
  - `6f34e52 Add guarded crypto research queue`
- Deployed only the live P0 files to server `/root/by-bot`:
  - `smart_pump_reversal_bot.py`
  - `bot/tpsl_policy.py`
- Restarted `bybot` safely after confirming `open_trades=0`.

## Current Live Bot State

Server: `root@64.226.73.119:/root/by-bot`

Latest check:

- `systemd bybot`: active
- bot PID: `4018899`
- `dry_run`: `false`
- `trade_on`: `true`
- `open_trades`: `0`
- `regime`: `bear_chop`
- `last_error`: `null`
- heartbeat file: `runtime/bot_heartbeat.json`
- heartbeat age at last check: about 22 seconds

Important: the bot is not frozen. It is live-enabled, but it may still wait for valid strategy signals.

## Current Research Processes

Active screen:

- `4020891.crypto_research_guard_20260608`

Active pre-existing autoresearch:

- PID `3659949`
- spec: `configs/autoresearch/liquidity_sweep_reversal_v2_param_sweep_v1.json`
- progress at last check: `317 / 486`
- current result quality: failing, PF `0.0`, fail reasons include `trades<30;pf<1.18;net<3.0`

The guarded queue is waiting for this process before starting the new sequential package queue. This is intentional to avoid overloading the server.

Guard log:

- `logs/crypto_research_guard_20260608/queue.log`

After the old liquidity sweep finishes, guard will run sequentially:

1. `package_brc1_bounded_additivity_v1.json`
2. `package_bear_brc1_v1_nowide.json`
3. `support_bounce_v1_annual_repair_v2.json`
4. `inplay_breakout_retest_focus_v1.json`
5. `package_elder_revived_v1.json`
6. `elder_canonical_rewrite_v1.json`

Expected timing:

- current liquidity sweep: likely a few more hours
- full guarded queue: likely overnight / next 24h depending on timeouts

## Crypto Strategy State

- P0 TP/SL execution bug is fixed live.
- ARF1 r002 winner is already applied in `configs/approved_strategy_params.env`:
  - `ARF1_MIN_RSI=48`
  - `ARF1_REJECT_BELOW_RES_ATR=0.08`
  - `ARF1_RES_TOUCH_BUFFER_ATR=0.35`
- Next validation target: first new live trade after the P0 fix. Verify that `request_sl` / `request_tp` preserve strategy levels instead of global percent fallback.

## Arbitrage State

Latest file: `runtime/arb_roi_estimate.json`

Closed-cycle sample:

- closed cycles: `19`
- open cycles: `5`
- wins/losses: `7 / 12`
- winrate: `36.84%`
- mean cycle return: `+0.1374%`
- median cycle return: `-0.1046%`
- p25 cycle return: `-0.16785%`
- worst/best: `-0.4702% / +1.7135%`
- conservative p25 monthly projection: about `-4.99%`

Conclusion: not live-ready. Do not add more capital for arbitrage yet. Need better filters before tiny live.

## Alpaca State

Monthly v38:

- Research result remains attractive: June candidate set was `DDOG,QCOM,NOW`, historical 24m return about `+58%`, PF about `6.62`.
- Real/paper launch is still blocked by execution verification, not by missing research:
  - previous protected order attempts hit pre-market / fill timing issue
  - needs fresh market-hour protected order plan with actual fills and broker-side protection

Intraday Alpaca:

- Paper bridge is active.
- Latest log showed open paper position in `UBER`, filters passed, but not production-approved.

Conclusion: do not fund real Alpaca $500 until one fresh market-hour paper gate shows protected fills and no cleanup/protection conflict.

## Security / Dirty Files

- `configs/web_config.json` is locally modified and contains user/server auth material. Do not commit it.
- Many old untracked docs/configs remain in the repo from prior work. Do not mass-add.

## Next Recommended Checks

In 6-12 hours:

```bash
ssh -i ~/.ssh/by-bot root@64.226.73.119 'cd /root/by-bot && screen -ls && tail -80 logs/crypto_research_guard_20260608/queue.log'
ssh -i ~/.ssh/by-bot root@64.226.73.119 'cd /root/by-bot && cat runtime/bot_heartbeat.json'
```

When a new crypto trade appears:

```bash
ssh -i ~/.ssh/by-bot root@64.226.73.119 'cd /root/by-bot && tail -80 runtime/live_trade_events.jsonl'
```

Check whether strategy TP/SL were preserved.

## Next Work Items

P0:

- Monitor first live crypto trade after TP/SL fix.
- Let guarded research queue finish and promote only package-level winners.
- Keep crypto risk conservative until 20-30 post-fix trades exist.

P1:

- Improve arbitrage filters before adding capital.
- Run Alpaca v38 market-hour paper preflight.
- Clean/triage untracked repo files separately, not mixed with trading changes.

## 2026-06-12 Codex Session Addendum — Web Control Layer + Live Diagnosis

Context:

- Bot was checked after roughly 4 hours of live runtime after the IVB1 canary deploy.
- `dry_run=false`, `trade_on=true`, `open_trades=0`.
- Websocket/data path was alive: `bybit_msgs` was growing normally.
- Regime remained `bear_chop`; orchestrator risk was conservative (`global_risk_mult` about `0.55`, effective risk per trade about `0.44%`).

Why there were no new crypto entries:

- This was not a frozen bot.
- Active live sleeves were too narrow/strict for the current tape:
  - `ivb1`: about 1105 attempts, all `no_signal`; most rejects were `ivb1_ns_other`, then `no_breakout` / `impulse_body`.
  - `att1`: about 35 attempts, all `no_signal`; mostly no trendline/first-bar/touch quality.
  - `flat`: about 30 attempts, all `no_signal`.
  - `breakdown` is effectively zero-risk in runtime and should be treated as disabled until repaired.
- Practical meaning for user: no entry is currently a strategy coverage/frequency problem, not an exchange connectivity problem.

Weekly live-vs-backtest report translated:

- Report: `reports/weekly_live_vs_backtest/weekly_live_vs_backtest_20260612_073424.md`.
- Live 7d: `9` trades, PnL about `-0.8544`, PF `0.267`.
- Replay/backtest same window: `24` exits, PnL about `+1.3070`, PF `1.315`.
- Important caveat: replay uses the config snapshot at report time, so it is evidence only after a stable-config window.
- Real issue: live bleed is concentrated in old `alt_inplay_breakdown_v1` and live ATT1 behavior:
  - Live `alt_inplay_breakdown_v1`: 5 trades, net about `-0.476`, PF `0.330`.
  - Live ATT1: 4 trades, net about `-0.378`, PF `0.168`.
- Interpretation: do not add risk to these mechanisms until repaired and revalidated.

Web/control changes made locally in this session:

- Added read-only endpoint `POST /api/ai/analyze-live-position` in `web/routes/extra_routes.py`.
  - It returns a human-readable position risk readout: missing SL, near SL, losing position, profit protection after about 1R, runner/no TP.
  - It does not execute trades.
- Extended Dashboard live positions widget in `web/static/index.html`.
  - Adds TP column next to SL.
  - Adds `AI read` button for a live position.
  - Adds `Queue close` button that only creates a pending action through the existing `/api/ai/propose-position-action` path.
  - Confirmation/execution remains separated; no hidden auto-close was added.
- Fixed `web/routes/data_routes.py` live P&L sleeve health source.
  - Prefer `runtime/strategy_health.json`; fall back to `configs/strategy_health.json`.
- Added targeted tests: `tests/test_web_live_position_analysis.py`.

ATT1 live refresh applied after server result review:

- Source result: `att1_density_v3_more_pivots_v1_r259` from server run `backtest_runs/autoresearch_20260611_141702_att1_density_v3_more_pivots_v1/results.csv`.
- Evidence on 360d:
  - net `+39.18`
  - PF `1.376`
  - WR `59.4%`
  - max DD `3.97`
  - trades `421`
  - red months `1`, max red streak `1`
- Live config changed in `configs/approved_strategy_params.env`:
  - `ATT1_MAX_PIVOT_AGE=20` -> `16`
  - `ATT1_MIN_R2=0.7` -> `0.65`
- Other ATT1 r259 params already matched live (`PIVOT_LEFT=2`, `PIVOT_RIGHT=3`, `MIN_PIVOTS=2`, `TOUCH_ATR=0.5`, `RSI_LONG_MAX=52`).
- Expected P&L effect: improve ATT1 quality/frequency without adding a new sleeve. It is still a canary-style live refresh; monitor the next 20-30 ATT1 trades before increasing risk.

Deploy status:

- Web/control package committed and pushed as `2255afa Add web live position AI controls`.
- ATT1 r259 refresh committed and pushed as `352e68a Apply ATT1 r259 live refresh`.
- Server had a dirty working tree, so deploy was done by targeted backup + `scp`, not by `git pull`.
- Web deployed:
  - `web/routes/extra_routes.py`
  - `web/routes/data_routes.py`
  - `web/static/index.html`
  - `tests/test_web_live_position_analysis.py`
  - `docs/CODEX_HANDOFF_2026_06_08.md`
  - restarted only `trading-journal-web.service`; `/ping` returned `{"pong": true}`.
- ATT1 config deployed:
  - `configs/approved_strategy_params.env`
  - bot was restarted only after confirming `open_trades=0`.
- Post-restart live status:
  - `bybot.service`: active
  - `trading-journal-web.service`: active
  - `dry_run=false`, `trade_on=true`, `open_trades=0`
  - heartbeat fresh
  - websocket/data flow recovered after startup subscription warm-up: `bybit_msgs` grew to `21798`
  - current regime: `bear_chop`

Validation run:

- `python3 -m py_compile web/routes/extra_routes.py web/routes/data_routes.py` — OK.
- `.venv/bin/python tests/smoke_test.py` — 22/22 OK.
- Direct live-position analysis checks — OK.
- `node` syntax parse of `web/static/index.html` script — OK.
- Local `pytest` was not available in this workspace venv, so the new pytest file was additionally validated by direct Python assertions.

Expected P&L / ops effect:

- Direct P&L effect: none, intentionally. This is a control/visibility layer.
- Expected operational effect: fewer blind manual decisions on open positions, faster detection of missing stops / near-stop / profit-protection cases, and less noisy Telegram dependence.

Next portfolio repair queue:

1. Repair `alt_inplay_breakdown_v1` before any more risk:
   - Test wider SL / fewer stop-then-reverse cases.
   - Add local regime filter and impulse-exhaustion filter.
   - Gate on 180d and 360d, with `stop_then_reversed` target below 15% and PF above 1.0.
2. ATT1 additivity audit:
   - Compare ATT1 daily PnL correlation and trade overlap against ASB1.
   - If correlation is high, ATT1 should not stack risk on the same symbol/time; it needs a portfolio-level overlap guard.
3. BTC/ETH midterm pullback:
   - Expand to 360d and require at least 30 trades, PF above 1.3, WR above 45%.
   - If passed, use it as a different niche from alt chop strategies.
4. Web next:
   - Add Alpaca live/paper positions into the same positions panel.
   - Add pending action inbox with explicit confirm/deny.
   - Add human-language report cards for weekly live-vs-backtest and sleeve health.
5. Crypto frequency:
   - Do not blindly loosen all filters.
   - Add one validated canary at a time: LSR1 trend-filtered, repaired inplay, then ASB1/bounce only if regime/additivity gates pass.

## 2026-06-12 Addendum — External Strategy Audits Applied Carefully

Input reviewed:

- Elder audits: `elder_triple_screen_v2`, `elder_triple_screen_v3`, `alt_elder_revived_v1`.
- Liquidity sweep audit: `alt_liquidity_sweep_reversal_v2`.
- Bounce/breakout audit: `alt_support_bounce_v1`, ASB/breakouts, IVB1, squeeze.
- Inplay audit: `alt_inplay_breakdown_v2`.
- Pump/dump audit: `pump_fade_smart_v1`, `pump_momentum_v1`.
- Pair-arb audit: `pair_stat_arb_v1` + executor + validators.
- TPB/RMR/MTPB audit: `trend_pullback_v1`, `range_mean_reversion_v1`, `btc_eth_midterm_pullback_v2`.

Applied in code now, live-neutral:

- `strategies/alt_liquidity_sweep_reversal_v2.py`
  - ATR and ADX gates now use bars before the sweep candle, so a large wick cannot widen its own filter.
  - Added explicit volume mode: `LQH2_VOL_MODE=quote|base` (default `quote`, preserving current dollar-volume intent).
  - Raised default TP1 from `0.8R` to `1.0R`.
  - Added same-pool cooldown (`LQH2_POOL_COOLDOWN_BARS_5M`, default `72`) to avoid repeated entries on the same swept level.
  - Added optional chop-protection ADX gate (`LQH2_MAX_ADX`, default off in code; research spec sets `25`).
  - Expected effect: fewer repeated false reversals and cleaner sweep stats; likely fewer trades, higher quality if edge is real.

- `strategies/alt_inplay_breakdown_v2.py`
  - Support is now built from the previous 1h window, excluding the latest break-confirmation bar.
  - Added `BREAKDOWN2_REQUIRE_1H_CLOSE=1`: latest completed 1h close must break the prior support.
  - Default research params are more conservative: 48h lookback, `RSI_MAX=45`, `MIN_BREAK_ATR=0.25`, `MAX_DIST_ATR=1.2`, `VOL_MULT=1.3`, `COOLDOWN=24`.
  - Added BE/trailing fields to reduce "went green then full SL" behavior.
  - Expected effect: should reduce stop-then-reverse bleed from old inplay/breakdown logic. It may also reduce frequency; verify by 360d matrix before any live risk.

- `strategies/pair_stat_arb_v1.py`, `strategies/pair_arb_executor_v1.py`, `scripts/validate_pair_arb.py`, `scripts/walkforward_pair_arb.py`
  - More conservative defaults: lookback 336, entry z 2.5, stop z 3.0, half-life <=48, corr >=0.75, risk per pair 0.3.
  - Added beta-stability gate (`max_beta_drift_frac`).
  - Executor default leg fraction reduced from 0.5 to 0.3; max hold default increased to 168 bars.
  - Validators now accept conservative funding drag: `--funding-bps-per-8h`.
  - Expected effect: arb will look worse but more honest. If it still passes after fees+funding, it becomes a stabilizer; if not, no capital.

- `strategies/pump_fade_smart_v1.py`
  - Pump detection now uses highs inside the pump window, not close-only movement.
  - Defaults tightened around review: pump 4%, vol z 2.5, RSI 70, rejection body 0.50, wick 0.40, max distance 1.5 ATR, SL buffer 0.3 ATR, TP1 1R, TP2 2R, cooldown 48.
  - Signal side fixed to canonical `short`; returns TP1/TP2/trailing fields and validates `TradeSignal`.
  - Expected effect: less random fade spam, better alignment between backtest and live signal object.

- `strategies/pump_momentum_v1.py`
  - Pump size now measures from recent lows, not close lows.
  - Defaults tightened: max pump 30%, SL 1.5 ATR, stop range 1%-6%, time stop 12h.
  - Still not live-ready; next redesign must add retest/pullback instead of buying the top of the trigger candle.

- Research specs updated:
  - `configs/autoresearch/liquidity_sweep_reversal_v2_full_grid_v1.json`
  - `configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json`

Validation:

- `python3 -m py_compile` on changed strategy/scripts/tests — OK.
- `.venv/bin/python tests/smoke_test.py` — 22/22 OK.
- Local `pytest` is still unavailable in this workspace; direct import/function checks were run instead:
  - `tests/test_strategy_review_fixes.py`
  - `tests/test_pair_arb_executor.py`
  - `tests/test_pair_arb_scanner.py`
  - `tests/test_pfs1_funding_gate.py`
  - `tests/test_new_strategies.py`
  - direct checks: 26/26 OK.

Not deeply rewritten yet:

- Elder: review is directionally right, but the correct next step is a new hybrid preset/spec, not another one-off parameter tweak. Base candidate: v2 mechanics + v3 macro/ATR quality + optional RSI/volume + ADX, then 360d WF. Do not live-enable Elder before that.
- Bounce/breakouts: audit points are useful, but each sleeve needs isolated research. IVB1 already has macro filter/BE fields; next change should be adaptive impulse ATR grid, not live loosening.
- TPB/RMR/MTPB: keep as promising research-only diversifiers. Need volume/rejection/channel simplification tests, then a RegimeRouter/additivity check.

Dynamic symbol selection standard:

- Keep dynamic coin selection. It is needed to avoid stale allowlists.
- New standard: every promoted strategy must be tested in two modes:
  1. frozen signal geometry with fixed researched universe;
  2. same geometry with dynamic router/allowlist snapshots chosen from prior data only.
- A router can promote a strategy only if it does not worsen PF/DD/red-month count versus the fixed benchmark, or if it materially improves frequency with acceptable DD.
- ATT1 r259 (`+39.18`, PF `1.376`, WR `59.4%`, DD `3.97`, 421 trades, 1 red month) is not yet "byte-for-byte live equal" because live also uses the dynamic router. Next quality task: ATT1 r259 router-parity report.

Next server research queue to start:

1. `breakdown_v2_1h_bear_sweep_v1` after code deploy: verifies repaired previous-window support + 1h close gate.
2. `liquidity_sweep_reversal_v2_full_grid_v1` after code deploy: verifies closed-bar ATR + same-pool cooldown + ADX gate.
3. Pair-arb walk-forward on 15-20 pairs with funding drag scenarios (`0`, `2`, `5` bps/8h conservative).
4. Pump-fade smart 360d / recent bear-window matrix after high-based pump fix.

Operational rule:

- Do not restart live bot for these code changes while positions are open.
- Do not increase live risk from this package. This is research/validator repair first, promotion later.

Server deploy / research launch:

- Commit pushed: `267c57a Apply strategy audit repair package`.
- Targeted `scp` deploy to `/root/by-bot`; no `git pull`, no live bot restart.
- Server validation:
  - `.venv/bin/python -m py_compile` on changed strategy/scripts/tests — OK.
  - Direct portable checks: 13/13 OK.
- Research screens started:
  - `bd2_audit_20260612`
    - spec: `configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json`
    - log: `logs/research_audit_20260612/bd2_audit.log`
    - run dir: `backtest_runs/autoresearch_20260612_121825_breakdown_v2_1h_bear_sweep_v1`
  - `lsr2_audit_20260612`
    - spec: `configs/autoresearch/liquidity_sweep_reversal_v2_full_grid_v1.json`
    - log: `logs/research_audit_20260612/lsr2_audit.log`
    - run dir: `backtest_runs/autoresearch_20260612_121825_liquidity_sweep_reversal_v2_full_grid_v1`
- At launch both were on candidate `r001`; `results.csv` had only headers while the first backtests were still running.
- Live bot status during launch:
  - `open_trades=0`
  - `dry_run=false`
  - `trade_on=true`
  - `max_positions=3`
  - `regime=bear_chop`
  - Bybit message counter growing.

Arbitrage quick check after audit fixes:

- `scripts/pair_arb_scanner.py --lookback 336 --max 10` on server cache found no current candidates among `BNBUSDT,BTCUSDT,ETHUSDT,LINKUSDT,LTCUSDT,SOLUSDT,XRPUSDT`.
- ETH/BTC walk-forward with `lookback=336`, `entry_z=2.5`, `stop_z=3.0`, fees `6bps/fill`, conservative funding drag `2bps/8h`:
  - aligned 1h bars: `38976`
  - OOS trades: `193`
  - aggregate verdict: `fragile`
  - median fold PF: `0.5103`
  - mean fold return: `-1.4092%`
  - fee sensitivity verdict: `fee_fragile`
- Conclusion: pair-arb remains research-only. Do not allocate capital until pair-universe scan + regime/funding filters produce positive OOS after costs.
