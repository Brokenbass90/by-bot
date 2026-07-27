# Execution update — 2026-07-27

## Verified live truth

- `bybot.service` is active with the same core PID/start time as before the web
  work. Heartbeat was fresh, `trade_on=true`, `dry_run=false`, broker position
  count `0`, and ATT1 remained the only money sleeve at `risk_mult=0.10`.
- `trading-journal-web.service` was restarted independently after the targeted
  two-file web deployment. `/ping` returned `{"pong":true}` and local/remote
  SHA-256 hashes matched.
- Alpaca live logic and orders were not changed.

## XSEC V4

- Risk-zero shadow remains active.
- Two independent staggered decisions exist: phase 0 on `2026-07-26` and phase
  1 on `2026-07-27`; phase 2 has not made its first decision yet.
- Backtest `+49.1%`, DD `6.8%`, Sharpe `2.73` remains a research result.
- Earliest defensible August action is a tiny canary only after `20–30` clean
  decisions plus PIT/survivorship, execution-cost, fill, restart/idempotency,
  correlation and capacity gates. There is no automatic calendar promotion.

## ATT1 A3/3R challenger

- The A3 rule is now represented in the production ATT1 strategy behind
  `ATT1_TREND_GUARD_BARS`; default `0` preserves the live champion exactly.
- A3 at `3` bars rejects a short when the latest H1 close is above the close
  three completed H1 bars earlier. Long logic is mirrored.
- A frozen risk-zero config and preregistration define the fixed-3R comparison.
- Proxy evidence remains `N=194`, `+0.180R/trade`, PF `1.263` at 4 bps and
  `+0.118R/trade` at 11 bps, with one unstable fold. It is not money authority.

## Cross-exchange funding

- `19` paper cycles are closed, but only `3` belong to the post-churn-fix
  cohort: one positive and two negative.
- Five paper pairs were open at the audit; aggregate current markout was about
  `-1.61%` of virtual pair capital. This blocks keys/capital.
- The lifecycle now persists each pair's worst intracycle markout. This is
  evidence for a separately preregistered basis/markout breaker; it does not
  retroactively tune or close the current cohort.

## FX/CFD

- The completed broad scan produced `108` base/stress rows and zero promoted
  pair/family combinations.
- The apparent XAUUSD grid-reversion near-miss was invalid: the harness had
  treated gold as a `0.0001`-pip instrument and materially understated spread
  and swap.
- The contract is repaired: XAU pip size `0.01`, diagnostic spread `35` pips
  (`$0.35`) and symmetric placeholder swap `-20` pips/day (`$0.20`) pending
  broker-specific data. A corrected nine-family XAU rerun is active.

## Web trade geometry

- Closed-trade records now retain `signal_geometry` from the entry event even
  if a later lifecycle event contains an empty geometry object.
- The trade chart draws saved horizontal levels and the entry-time sloped-line
  projection alongside entry, exit, SL and TP.
- The UI labels geometry as exact immutable `position_geometry_v1`,
  reconstructed, or missing. It no longer implies exactness for old records.

## Verification and release

- Full local regression: `1547 passed`.
- Code commit/push: `ce31df3b88a8fc909d81db062181c31cc7704615`.
- Targeted web backup stamp: `20260727T065323Z`.
- Remote web hashes:
  - `web/routes/data_routes.py`:
    `f5971f0ec4d9476276895586be34f0dff63862b69af98341f03846ac78f2796b`
  - `web/static/index.html`:
    `5322f1f07d0bacd596bf52ac91d6380aedcdb707f97a9a3a8f9e1b62682fa212`
