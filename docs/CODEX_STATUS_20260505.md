# Codex Status — 2026-05-05

## Live / Server

- Server bot is alive: `bybot.service` active, fresh heartbeat, `open_trades=0`.
- Live mirror was synced locally via `scripts/sync_web_live_mirror.sh`.
- Current server control-plane still points to canary v2 policy (`2026-04-28-canary-v2`).
- Web screenshots were stale before mirror sync: dashboard showed old April trades and old strategy attribution.

## Crypto Verdict

- Do not deploy canary v2.2 yet.
- 180d looked attractive for `ATT1 + support_bounce`, but fresh 60d failed:
  - `ATT1 + support_bounce`: `-1.97`, PF `0.903`, DD `4.84`, 67 trades.
  - `ATT1 only`: `+0.04`, PF `1.003`, DD `3.79`, 56 trades.
  - `support_bounce only`: `-1.96`, PF `0.664`, DD `2.36`, 15 trades.
  - current core (`ATT1 + flat + midterm` proxy): `-1.43`, PF `0.919`, DD `5.27`, 59 trades.
- Interpretation: the current 60d market is not paying the live core. We need missing flat/short/event sleeves, not just higher risk.

## Alpaca

- v38 paper gate is alive and holding `UNH + GOOGL`; `AMD` blocked by earnings.
- Monthly v38 latest summary still shows strong historical stats: about `+50.0%` compounded over 24 calendar months, PF `7.69`, WR `82%`, max monthly DD about `-3.86%`.
- Telegram repeated HOLD-only messages were noisy, not a trading failure.
- Added HOLD-only Telegram dedupe to `scripts/equities_alpaca_paper_bridge.py`; BUY/CLOSE/STOP alerts still pass.

## Research Started

- Added and pushed commit `ce54809`: new research sleeves:
  - `alt_spike_rejection_v1`
  - `alt_bear_regime_continuation_v1`
  - `alt_whale_print_follow_v1`
  - canary v2.2 rescue env with corrected live `BOUNCE1_*` keys.
- Added and pushed commit `9b20100`: `scripts/run_strategy_autoresearch.py --jobs`.
- Server was patched carefully instead of `git pull` because `/root/by-bot` has a very dirty live worktree.
- Server overnight queue is running sequentially:
  - `configs/autoresearch/spike_rejection_v1_initial_sweep.json`
  - `configs/autoresearch/bear_regime_continuation_v1_initial_sweep.json`
  - `configs/autoresearch/whale_print_follow_v1_initial_sweep.json`
- Main log: `/root/by-bot/logs/overnight_rescue_20260505/server_three_sweeps.log`.

## Next

1. Read the overnight ranked results and promote only if recent 60d + annual both pass.
2. If no new sleeve passes, repair existing short/flat sleeves in this order: `breakdown_v1`, `pump_fade`, `range_scalp`, `inplay_breakdown`.
3. Fix web truth model: show live-enabled strategies from control-plane, not only historical trade attribution.
4. Before crypto capital grows above small canary size, implement broker-side Bybit bracket `stopLoss/takeProfit` and exit-lock fixes from Pass 2 review.
