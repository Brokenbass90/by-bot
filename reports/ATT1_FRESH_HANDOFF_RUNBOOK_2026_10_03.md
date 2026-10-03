# ATT1 cold migration — local candidate, orders OFF

Owner accepted the existing fresh-epoch direction for orders-OFF implementation
on October3. Scope: the existing preparation/route boundary. Tasks1–4, strategy,
public epoch,2s freshness, risk caps and money authority remain unchanged.

Implemented interfaces:

- `validate_canary_fresh_handoff` / `bind_canary_fresh_handoff` in
  `bot/att1_canary_preparation.py` validate explicit `COLD_96_CLOSED_M5_V1`.
- `prepare_att1_fresh_cutover` in `bot/att1_coordinator_adapter.py` atomically stores
  the declaration and its evidence in the existing local route ledger.
- Existing entry preparation/command capture and cash-aware reservation consume
  the new binding. Legacy handoff validation still requires genuine watermarks.

Required declarations are source-bound, not self-authenticating. Fresh signed
collector/review provenance is still required for actual-account use. A policy
approval hash records migration acceptance; it is never owner money GO.

## Preparation sequence

1. Verify durable OLD entry retirement: effective existing entry guard disabled
   across reload/startup, native pause readable, entry restart denied and management
   preserved. Supply a complete current intent/finality/cost inventory and fresh
   authenticated flat/no-orders. No runtime retirement write was performed here.
2. Declare account, exact frozen profile and preparation implementation pins,
   approved-policy source, retirement clock and `legacy_state=UNKNOWN`.
   The H1 fence is the next H1 boundary at/after retirement, backed by actual
   availability. No fabricated `last_old_h1_ms` or OLD cooldown.
3. Supply actual closed M5 timestamps and source hashes after the fence, with a
   current complete capture. Require96 consecutive closes; gaps restart the
   pre-completion count, duplicates/future bars deny. Later observations preserve
   the first proven completion. The eligible signal cutover is its next/equal H1
   boundary. Missing/latest-stale data still denies current preparation.
4. Persist only into a disposable/local orders-OFF coordinator for acceptance.
   A live/occupied route or unresolved costs deny the transaction. NEW_READY is
   preparation only; no production DB migration or transport is installed.
5. Bind fresh existing budget/cash inputs and the exact declaration before captured
   command preparation. OLD re-enable, late drain, changed/missing epoch, wrong
   account/code/profile, stale evidence or budget failure denies. Existing uncertain
   prepared commands remain recovery-owned and return lookup-only after restart.

## Actual packet blockers — do not turn declarations green by hand

- Actual durable entry retirement/quarantine provenance is not yet collected.
- LINK repeatedly exposes hedge indices1/2; current command/binding require
  one-way positionIdx0. Global flat and the terminal placeholder row do not solve
  that conflict. No broker mode was switched or universe filtered.
- The source-bound funding policy for frozen14-day hold is unresolved. Captured
  full-limit stress at full draft R0.4/minimal notional5 exceeds D0.8 for OLD8.
  Smaller quantities can differ; no risk increase/hold change/latest-rate shortcut.
- Actual HFT fee coverage is missing. No guessed fee or symbol removal.
- Existing selected-account GET/capture/recovery code is retained. Autonomous
  money dispatch/protection/exit/finality integration remains a separate delivery;
  this cold-path implementation does not claim it is finished.

Actual-account archive is **BLOCKED_ACTUAL_INPUTS**, not BUILD_READY. No actual
packet was manufactured from synthetic declarations. Public snapshot06:50:33UTC
still3sessions/18records/1filled SEI/1gap/0clean/0held and0broker/order calls.

Rollback remains NEW ordersOFF; do not automatically resume OLD entries. If any
future exposure exists, preserve its owning protection/exit manager. Flat rollback
requires fresh authenticated absence of exposure/orders and captured finality.
Gate2–3 clean prospective filled terminals/net-R, fresh exclusive dossier and
separate owner money GO remain unchanged.
