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

