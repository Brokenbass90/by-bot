# Recovery checkpoint — 2026-07-30

## Executive truth

- The Jul 29 ETHUSDT and DOTUSDT ATT1 orders exposed a real live lifecycle
  defect: Bybit accepted the order, then the process raised
  `NameError: signal_reason is not defined` before the reservation was adopted
  as a managed trade, TP/SL was submitted, Telegram was notified and the trade
  was written to the local ledger.
- The secondary untracked-position scanner also treated an
  `ENTRY_RESERVATION` as if it were a managed position. This is why repeated
  `ENTRY RESERVATION STALE` warnings coexisted with an unmanaged exchange
  position.
- Both defects are fixed, tested, pushed and targeted-deployed to the live VPS.
  ATT1 risk, signal rules and universe were not changed.
- Direct post-deploy truth: `bybot.service` is active with one trading process,
  heartbeat is fresh, `trade_on=true`, `dry_run=false`, `open_trades=0`, and
  `ws_guard_active=0`.

## Incident accounting

Direct Bybit order/fill history, not the incomplete local snapshot, is the
authoritative source:

| Symbol | Bot entry | Owner exit | Net closed PnL |
|---|---:|---:|---:|
| ETHUSDT short 0.01 | 1914.48 | 1913.94 | -0.01527334 USDT |
| DOTUSDT short 43 | 0.7600 | 0.7551 | +0.17486788 USDT |
| **Combined** | | | **+0.15959454 USDT** |

These trades never reached `trades.db` or the live trade-event ledger, so they
do not currently contaminate the autonomous ATT1 edge cohort and there is no
reason to restart its statistics. If a later broker-fill reconciliation imports
them, retain them for broker/accounting truth but tag them
`INCIDENT_EXCLUDED` for strategy-promotion statistics.

## Live fix and release truth

Local pushed branch: `codex/dynamic-symbol-filters`.

- `46541d6` — adopt an acknowledged ATT1 order before optional hooks; submit
  protection immediately; do not let reservations mask exchange positions.
- `f1a0c98` — make the flat-restart gate safely read the live service account
  configuration without printing or persisting credentials.
- `e673883` — deployment receipt.

Relevant tests passed: 17 lifecycle/regression tests, 3 restart-helper tests,
plus local and server `py_compile`.

The live VPS received an exact-file overlay and a direct-exchange,
three-confirmation flat restart. The VPS repository remains intentionally
behind and dirty; a broad `git pull` was not used. This is a systemd/VPS
deployment, not a Heroku deployment.

Receipt:
`reports/releases/ATT1_ENTRY_RESERVATION_HOTFIX_DEPLOY_RECEIPT_2026_07_30.json`.

## Current contour truth

### ATT1

- Only current Bybit money sleeve, still `x0.10`, short-only.
- The next normal entry must prove the repaired full lifecycle:
  reservation -> exchange acknowledgement -> managed state -> exchange
  protection -> Telegram -> database/event ledger.
- The Jul 29 notionals do not prove a fixed live `$30` cap. ETH was constrained
  by minimum quantity/notional; DOT followed risk/stop-distance sizing.
  Backtest/live sizing parity still needs a deterministic same-input test.
- Do not increase risk because of the incident trades. Use clean autonomous
  closes and the existing N20 review / N30 scale gate.

### XSEC

- Strongest crypto research candidate: robustness and family tests are
  positive, but the evidence is survivor-only and not independent PIT/OOS.
- XSEC intentionally runs in a detached local Mac research screen, not on the
  live VPS. Direct local inspection confirms `xsec_v3_shadow_20260726` is alive,
  with five immutable risk-zero ledger decisions through 30 July. The hourly
  loop is idempotently reporting that today's decision is already complete.
- Next work: PIT universe, execution/fill parity, immutable daily ledger, then
  N10 interim and N20-30 decision. No real money yet.

### Funding positioning V4

- Historical maker audit at frozen 5 bps: 92.95% modeled fill,
  +13.49 bps per submitted decision, 8/8 frozen symbols positive.
- A separate dynamic selector already builds a causal universe from listing
  age, turnover, spread and funding-history coverage. This is the correct way
  to expand beyond eight manually named coins.
- Both prospective collectors intentionally run in detached local Mac research
  screens. Their ledgers and summaries were fresh at the 30 July inspection:
  frozen V4 had 40 trials, 9 submitted, 6 fills and 5 closed; the dynamic
  challenger had 111 trials, 6 submitted, 6 fills and 3 closed. Both explicitly
  have `capital_authorized=false`.
- The dynamic summary's very large early mean is based on only three closes and
  is diagnostic, not a return estimate. Continue measuring non-fill adverse
  selection and queue position.

### Cross-exchange funding arbitrage

- Scanner, validator and paper lifecycle are genuinely scheduled every
  15 minutes and their runtime files are fresh.
- Clean post-cutover gate remains N12: 2 wins / 10 losses, median -0.1671%,
  p25 -0.2238%, with five open 24-hour cycles in the latest canonical receipt.
- At the observed cadence N20 is approximately 1-3 days away. The
  preregistered negative-median/p25 retirement rule remains binding.
- No exchange deposits or trade keys are needed before a positive paper gate.

### Alpaca

- Real account remains protected SAFE_HOLD; new live entries and rotation are
  off.
- Latest direct receipt: equity about $484.64, ABBV unrealized about +4.0%,
  SCHW about +2.0%; broker stops cover 2/2 positions at ABBV 236.60 and
  SCHW 96.87.
- These profits can revert before the fixed stops fill. Fractional positions
  have no native trailing order. Under SAFE_HOLD there is no scheduled
  profit-taking date: exit is by broker stop or a separate owner-authorized
  close/rotation decision.
- Adaptive Alpaca paper is genuinely scheduled. It is progress toward a new
  model, not yet evidence for real-money promotion. Free data is sufficient at
  the current gate; do not buy a Massive plan yet.

### FX/CFD

- OANDA KYC, deposit and private API are not required for the historical gate.
  Public OANDA swap tables already removed the immediate cost-data blocker.
- Next sealed package is D1 carry+trend plus H4 breakout/retest using public
  asymmetric swap and base/stress spread/commission contracts.
- Only after an historical PASS is it rational to fund or finish a practice/live
  broker integration.

### Event universe

- Terminal result: aggregate 1h and 4h `FAIL`; 24h `BLOCKED_DATA`.
- The short 24h split is a new discovery only. It requires a fresh short-only,
  regime/beta-controlled preregistration and cannot be promoted from the same
  viewed outcomes.

## Claude package acceptance

Accepted and now incorporated:

- reservation-mask defect (with the deeper live `signal_reason` root cause);
- maker non-fill/adverse-selection warning;
- need for dynamic PIT selectors and execution parity;
- backtest notional-cap defect as a harness issue;
- cooldown counts as scheduler/telemetry duplication rather than proven lost
  ATT1 opportunities;
- the onboard AI loop is largely unused and must stay proposal-only.

Qualified or rejected:

- no evidence of a fixed `$30` live notional cap;
- “77 ready technologies” is an inventory claim, not wiring or money-readiness;
- small, survivor-selected or regime-selected backtests are not live
  promotion evidence;
- broad cleanup/commit/deploy of the dirty tree remains unsafe without
  exact-file review.

## Immediate queue

1. Observe the first post-hotfix ATT1 entry end-to-end and emit a lifecycle
   receipt; do not alter ATT1 risk/signal/universe.
2. Continue the already-running local XSEC and Funding Positioning risk-zero
   supervisors; emit bounded interim receipts without restarting duplicates.
3. Let cross-exchange funding reach its automatic N20 decision.
4. Run the public-cost FX D1/H4 sealed package.
5. Complete Alpaca adaptive exit/parity attribution before any real rotation.
6. Target-deploy the read-only AI technology registry and Book Status web view
   only after local/server parity review. Keep AI auto-apply disabled.
7. Add deterministic backtest/live sizing parity and trade-to-geometry
   provenance so web charts can show the exact levels the bot traded.

## Owner action

No keys, deposits, paid data or OANDA KYC are needed now. The only optional
owner decision is whether the existing profitable ABBV/SCHW SAFE_HOLD
positions should keep their fixed loss-protection stops or receive a separately
reviewed profit-protection/exit instruction.
