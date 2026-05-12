# Codex Status - 2026-05-12

## What Changed Today

- Verified the live Bybit bot on the server: service is running, heartbeat is fresh, auth is OK, `DRY_RUN=false`, `open_trades=0`.
- Fixed the live support-bounce wiring: bull overlays and `build_regime_state.py` now emit the real live flag `ENABLE_BOUNCE1_TRADING=1` instead of only the legacy `ENABLE_BOUNCE_TRADING`.
- Rebuilt server regime/router/allocator state and restarted `bybot.service`.
- Repaired router evidence gating in the live `.env` by applying the control-plane env patch; the server router now reads `runtime/control_plane/router_trades_baseline.csv` and rejects weak symbols before they reach sleeves.
- Fixed the DeepSeek research approval cache so pre-approved queue specs stay approved across repeated checks.
- Hardened the research process guard so long but healthy autoresearch/backtest rows are not killed too early.
- Added an approved research queue for support-bounce, breakdown, inplay, pump-fade, Elder, BRC1, spike rejection, whale print, and liquidity sweep research.
- Reconciled `strategy_health.json` on the server and marked `alt_support_bounce_v1` as `OK` based on positive 180d additivity evidence.

## Current Server Truth

- Live mode: real Bybit mode, not dry-run.
- Service state: alive and scanning.
- Current regime: `bull_chop`.
- No open crypto trades right now.
- Not blocked by safe mode: `safe_mode=false`, `hard_block_new_entries=false`.
- Allocator is still `degraded`, but the current reason is a risk-quality warning, not a hard trading block:
  - `overall_health_watch`: some enabled sleeves are still research/watch quality.
  - `portfolio_overlap`: several sleeves want similar symbols, so the allocator applies haircuts.
- Core OK sleeves now include: `att1`, `bounce1`, `flat`, `midterm`.
- Watch/research sleeves still need proof before promotion: `breakout`, `impulse/ivb1`, `asb1`, `sloped`, `asm1`.

## Alpaca Truth

- Alpaca v38 monthly paper is active and is the best protected compounder candidate.
- Current v38 monthly picks/positions are `AMD`, `UNH`, `GOOGL`.
- Broker-side simple stop orders are armed for these monthly positions.
- App-managed trailing logic is enabled for v38, but this is not the same as native Alpaca broker-side trailing-stop execution.
- Intraday income lane is not ready for real money yet: stale paper positions (`COST`, `META`, `NFLX`) are occupying capacity and need a cleanup/reconcile pass with stop coverage checks.
- Intraday cleanup now cancels open orders for a stale paper symbol before trying to close the position; this targets the known Alpaca `held_for_orders` cleanup loop.

## Research Queue

- Server-side queue is active.
- Current first active job: `support_bounce_v1_annual_repair_v2`.
- Queue is guarded and should resume/continue from server cron, not from the laptop session.
- Winners do not auto-deploy. Promotion still requires annual/OOS/additivity checks.

## Next Moves

1. Commit and push today’s safe fixes only; do not include `.env` or unreviewed Claude/user tails.
2. Clean Alpaca intraday paper state so the dynamic income lane can actually test instead of being blocked by stale positions.
3. Decide whether to keep watch sleeves scanning at reduced risk or switch to a clean OK-only live core to remove allocator `degraded`.
4. Let the server research queue finish support-bounce/breakdown/inplay/pump-fade/Elder/BRC/spike/whale/liquidity and promote only proven annual/additive winners.
5. Add a clearer web split: Live, Paper Alpaca, Research, Backtest Evidence.
