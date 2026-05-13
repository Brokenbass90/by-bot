# Codex Status - 2026-05-13

## Server Truth

- Server bot process is alive: `bybot.service` is active.
- Current market state is `bull_chop`.
- Current open crypto trades: `0`.
- Bybit live mode is still intended to be real mode, not dry-run, but any key values must stay in `.env` only and must not be committed.
- Router is fresh and dynamic:
  - `runtime/router/symbol_router_state.json` is `status=ok`.
  - `scan_ok=true`.
  - symbol baskets are being rebuilt from router/geometry/backtest-gate data, not only from old manual allowlists.
- Allocator is degraded but not hard-blocking:
  - `safe_mode=false`.
  - `hard_block_new_entries=false`.
  - `allocator_global_risk_mult=0.765`.
  - reasons are `overall_health_watch` and `portfolio_overlap`.
  - practical meaning: entries are allowed, but risk is haircut because several active sleeves are still WATCH-quality and overlap on symbols.

## What The Web Screens Mean

- The `Strategies` screen is the live runtime sleeve table. `ACTIVE` means the bot is scanning that sleeve. It does not mean every sleeve is already annual-proven.
- `OK` sleeves are closer to production confidence; `WATCH` sleeves are allowed to scan at reduced risk but still need stronger evidence.
- The `Setup Scanner` screen is a radar. It shows levels, resistance/support fades, candidate strategies, invalidation, and runtime risk. These cards are not orders and not permission to trade by themselves.
- Current scanner cards are useful: they prove the router/geometry layer sees setups. The missing piece is whether strategy logic converts those setups into entries under live filters.

## Current Live Crypto Sleeve Shape

Active runtime sleeves on the server include:

- `bounce1`
- `att1`
- `sloped`
- `midterm`
- `asm1`
- `asb1`
- `impulse`
- `breakout`
- `flat`

Important distinction:

- The strongest annual-proven base remains `ATT1 + flat + midterm`: `+52.99`, PF `1.376`, DD `5.30`, `521` trades, `1` red month on 365d.
- That annual base implies roughly `43` backtest trades per month on average, but live cadence can be lower if the current regime does not match entry filters.
- The expanded current server shape has more sleeves active than the old annual core, so it must be checked with live-effective parity instead of assuming old numbers still apply.

## Live Silence Investigation

The fresh conclusion is sharper than the morning checkpoint:

- the bot is not dead;
- `TRADE_ON=1` and `DRY_RUN=0`;
- live WebSocket traffic is flowing;
- the real fresh log is `runtime/live.out`, not stale `logs/bot.log`;
- the live detect scheduler is running: `detect_call`, `detect_gate_on`, `detect_sched_seen`, and per-strategy `*_try` counters are increasing;
- the allocator is still degraded, but it is not hard-blocking entries.

So the current blocker is not auth/offline/safe-mode. The current blocker is live strategy conversion:

- `breakout` is trying often but mostly exits as `breakout_ns_symbol`, meaning symbols reaching the live loop do not pass the strategy's own symbol/universe gate.
- `flat` tries but currently exits as `flat_ns_same_bar` plus cooldown/no-signal.
- `att1`, `asm1`, `ivb1`, and `midterm` are alive but are ending in no-signal/cooldown on the current feed.
- `sloped` is scheduled and tries, but much of the sampled period was cooldown.

Practical meaning: the bot is scanning and attempting, but the portfolio is still commercially too strict or mismatched for the current market. The next fix should target entry filters, per-strategy symbol gating, and live-vs-backtest entry mismatch, not another blind server restart.

To make this measurable, I hardened and deployed the weekly live-vs-backtest checker:

- `scripts/run_live_effective_parity.py`
- `scripts/weekly_live_vs_backtest_report.py`

The checker now:

- reads the actual live allocator/router universe;
- runs with a warmup window instead of a fake cold start;
- reports recent backtest `Entries` as well as exits;
- fails loudly if backtest `trades.csv` is missing;
- answers the key question: "Did live miss entries that the live-effective backtest would have taken?"

Server smoke result for `1d` ending `2026-05-13`:

- Live: `0` closed trades.
- Backtest: `0` recent entries, `3` exits from older warmup positions, PnL `-2.0353`, PF `0.000`.
- Meaning: the last 24h alone does not prove a missed-entry bug, because the warmup-aware replay did not open fresh entries in that 24h window.

Full `7d` warmup-aware parity verdict:

- Live: `0` closed trades.
- Backtest replay: `8` recent entries, `9` exits, net `-2.6963`, PF `0.463`, WR `33.3%`, DD `5.26%`.
- Meaning: even if the backtest took the recent live-effective entries, the last week was not a profitable window. But the live/backtest mismatch still matters: we must explain why live did not enter while replay did. This is now a targeted diagnostics task, not a vague "bot does nothing" complaint.

## Alpaca Truth

- Best tested Alpaca candidate remains `v38_hybrid_top4`.
- Historical OOS headline remains about `+27.95%` annual, PF `7.85`, low DD, but only around `15` trades/year.
- v38 monthly is a protected compounder, not a high-frequency income engine.
- On a `$500` account positions are fractional; Alpaca rejects native broker-side trailing stops for fractional shares.
- Current v38 behavior is therefore:
  - broker-side fixed stop protection for fractional positions;
  - safe software trailing close path;
  - whole-share native trailing remains available later when position sizes allow it.
- Intraday income sleeves are still paper-only and need position reconciliation/capacity cleanup before real-money use.

## AI Operator Truth

- The AI operator sees bot status, allocator/router summaries, scanner context, some Alpaca state, and recent trade summaries.
- It does not yet see the entire codebase/backtest registry automatically.
- Next required product step is an AI context bridge:
  - compact code map;
  - latest validated backtests;
  - current server state;
  - scanner cards;
  - Alpaca positions/orders;
  - trade-forensics summaries.
- AI should be allowed to propose and queue tests, but live mutations must remain user-approved.

## Current Research State

- Server research queue is active and server-owned, so it should continue even if the laptop sleeps.
- Active research at this checkpoint:
  - `support_bounce_v1_annual_repair_v2`.
- The `7d` live-effective weekly parity report completed and showed weak recent-market results, so the next expansion should prioritize phase-specific sleeves rather than just loosening the current core.

## Immediate Next Moves

1. Investigate `breakout_ns_symbol` first. It is the loudest live skip counter and suggests a strategy/universe mismatch.
2. Add per-strategy "why no entry" summaries into the daily report and web so silence becomes measurable within hours, not after a week.
3. Run/promote phase-specific candidates for the current market: support/bounce, repaired breakdown/bear continuation, spike/whale/liquidity, and Elder canonical only after annual/OOS/additivity proof.
4. Reconcile Alpaca intraday paper positions and stop coverage before treating intraday as a real income lane.
5. Build the scanner chart modal and AI context bridge so the operator can explain setup cards with evidence but cannot mutate live without approval.
