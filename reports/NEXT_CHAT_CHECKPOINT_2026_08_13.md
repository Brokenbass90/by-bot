# Next chat checkpoint — 2026-08-13

Read order:

1. `reports/NEXT_CHAT_CHECKPOINT_2026_08_13.md`
2. `reports/PROJECT_STATE_AND_ACCELERATION_2026_08_13.md`
3. `reports/CURRENT_PROJECT_ROADMAP.md`

## Git receipt

- Branch: `codex/dynamic-symbol-filters`
- Functional commit: `bd0256f` — research truth, AI idea intake, funding/Alpaca/
  SOL/Inplay/XAU diagnostics, FX force-flat, fail-closed Bybit checker.
- Focused suite: `32 passed`.
- Independent audits: funding V2 PASS, Alpaca proxy PASS, XAU V2 PASS.
- No live deploy, order, cancel, close, or risk change occurred.

## Current direct truth at 2026-08-13 05:45 UTC

- VPS `bybot.service active/running`.
- Heartbeat fresh: trade on, dry-run false, open trades 0, WS guard inactive.
- Direct server broker checker: retCode 0, positions 0.
- Only ATT1 has money authority, risk multiplier 0.10.
- Research station 6/6 healthy after research-only supervisor reload.
- Local tape/L2 collectors healthy; 94 GiB free.
- Redundant VPS `/root/research-l2` stopped correctly at its 2 GiB storage cap.
  Do not override the guard; local collection is continuous.

## Strategy truth

- ATT1: tiny canary, clean post-release cohort remains 1/20 on canonical
  roadmap evidence; do not use mixed breaker N11 as promotion evidence.
- Inplay ETH: prospective N0; historical cadence 0.782/day, N30 estimate 5.5
  weeks (3.8–7.7). Do not tune during collection.
- Inplay BTC portability: rejected, 0/30 variants stable in >=3/4 windows.
- Funding mapped V2: survives historical fees weakly, 3.77%/2.55% annualized
  on gross two-leg capital; halves unstable, forward N4 negative; no money.
- Alpaca clean-962 proxy: 11.14%/10.41% annualized base/stress, DD 23.7–23.8%,
  but sector unknown in 93% of selected slots and gap/stop losses unresolved.
- RMR1 SOL: regime did not explain pocket; no leg.
- XAU intraday: session breakout/retest +3.92R/+3.01R base/stress and 3/4 folds,
  but N13; other two families negative. Extend history and shadow only.

## Next exact work

1. Alpaca V2: sector/PIT completion plus entry-relative stop and gap guard;
   rerun base/stress and independent audit.
2. XAU V3: longer pre-holdout history, account-specific spread stress; only
   session breakout/retest, no new parameter grid.
3. Legacy batch: sweep_reclaim, sloped_break_retest, l2_density_edge; one frozen
   causal reproduction each, maximum five simultaneous candidates.
4. ATT1 golden lifecycle parity plus scheduled broker-runner-owner-accounting
   reconciliation. Risk stays 0.10.
5. Build allowlisted public-source digest collector feeding proposal-only
   `market_scanner_ai -> idea_intake`; no autonomous experiment or money.
6. Alpaca/Massive key rotation requires user-authenticated dashboard session:
   new key -> secret store/env -> GET-only smoke -> revoke old.

The old heartbeat automations `six-day-trading-research-guard` and
`trading-research-and-data-continuity-guard` were not present when queried in
the Codex app, so there is no active scheduled task to pause under those IDs.
