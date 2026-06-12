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
