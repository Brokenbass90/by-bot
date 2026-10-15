# KITY micro — real GET transport and scoped writer handoff preparation

**Terminal: BLOCKED_EXECUTION — physical single-owner binding is not applied.**
Owner approved engineering only, gross215 / immediate all-in exit threshold15 /
30min /20.3% floor shortfall / exact10. No monetary GO. The owner explicitly
allows a scoped handoff design instead of unsafe hot integration and forbids
performing that handoff in this task. That fallback was selected.

## Actual account/source progress

The new authenticated GET transport ran against the existing selected account
at **2026-10-15 06:51:20.824–06:51:25.882UTC**. It loaded only existing selected
credentials and matched their source to original PID1648585. **59 GETs;0 writes.**
Private capture692f7d8c…5cfb2c is0600; no credentials in public receipts.

- API key readOnly0, ContractTrade Order/Position; actual account permissions
  captured. REGULAR_MARGIN / one-way positionIdx0; configured leverage retained.
- Complete linear-USDT position/order pages0/0. This is dated scoped truth,
  not proof that all account products are flat or no other writer exists.
- Fresh per-leg instrument/minimum/step/tick/depth/fee/funding sources for all10.
- Common source-clock observation: worst CTS upper age890ms, PASS at capture.
  These prices are now dated and explicitly not current dispatch inputs.
- Actual signed history, execution and transaction endpoints responded. Empty
  transaction log used `nextPageCursor:null`. A narrowly versioned, offline
  EMPTY_TRANSACTION_NULL_CURSOR_V1 interpretation closes only an empty successful
  transaction page. Raw capture remains unchanged. Null cursor with rows stays
  UNKNOWN. This is not future fee/funding finality or permission to use zero.

The deterministic minimum target satisfying the **already approved20.3%** floor
rounding is21.4797/leg at this source. It produces **206.530670USDT gross**, below
215, with worst shortfall19.3424489%. The unconstrained minimum floor has a
29.149% BNB shortfall and is correctly not selected. No leg was dropped or
substituted and no tolerance was increased. The old210.266660 source is history.

Source-derived sizing/cost references:

- margin reference at unchanged per-symbol leverage:29.707497USDT;
- constant-price entry+exit taker fees:.21598153225USDT;
- 30min funding scenario at captured next-settlement times/rate limits:0;
- fully funded reference including these fees/funding:206.74665153225USDT.

These are preparation references, not a certified exchange order-margin quote.
The fully funded reference is a capital reservation calculation, not a leverage
change or a guaranteed loss bound. Future price/fees/funding/liquidity are not bounded
by this observation. Available account funding is in the private capture and
sanitized dossier; no order/balance/mode/leverage change was performed.

## Delivered local components

`kity_micro_transport_v1.py` is a real authenticated GET-only client, with fixed
endpoint/symbol scope, canonical HMAC, raw retention/hash, bounded pages/body,
timeouts and no redirect/retry. It has no POST method or daemon.

`kity_micro_account_bridge_v1.py` delegates order work only to an already
exclusive physical account owner. It loads no credentials and creates no second
sender. Without that owner it raises PHYSICAL_OWNER_UNBOUND before any intent.
Entry additionally needs exact plan GO. The owner interface must supply actual
exclusivity, fresh preflight and a genuinely one-shot POST; a boolean/receipt
alone is not the missing physical integration.

Durable intent precedes the single delegated call. ACK is not a fill; uncertain
send stays reconciliation across restart, without resend. Realtime **and**
history **and** execution pages feed the existing strict identity journal.
Material conflicts durably stop new entries. Same-symbol foreign quantity is
never adopted. Full owned snapshots and exact execution/cash/fee/funding rows
are required for finality; an empty page does not invent cash or funding coverage.

The prepared entry requests include proposed native Full market SL fallback,
derived proportionally from the remaining15 budget after sourced fees/funding,
with ticks rounded toward entry. This is execution-test safety, sealed in the
future exact GO dossier, not a change to KITY's research exit/hold. Native SL
readback binds only exact quantity/side/trigger/brokerID after exclusive clean
symbol custody. Missing/ambiguous protection causes durable owned unwind.
Native fills stop further entries; partial market recovery and owned native
cancel/readback retain their exact identities. No native stop was actually sent.

The original15 threshold and30min journal/deadline survive restart. These local
components do not themselves supply the missing running supervisor/physical
writer. No actual protection, partial fill or live lifecycle PASS is claimed.

## Exact remaining material blocker

**PHYSICAL_SINGLE_WRITER_DISPATCH_PROTECTION_RECOVERY_NOT_BOUND.**

Actual `bybot.service` is still active PID1648585/NRestarts0/DRY_RUN=false; source
c8ca2c32…a699d1. Its reservation lock is process-local asyncio. Direct hot
integration spans many existing trading paths and was not chosen. The web
service PID1623208 also exposes admin/AI control/subprocess routes; full absence
of transitive write effects is not proven. Quiescing only the monolith while
leaving those control paths unconstrained would not establish exclusivity.

`evidence/kity_micro_integration_20261015/handoff_design.json` pins the exact old
units/source/cron and defines a non-applied handoff: fresh old-owner flat/order
finality, explicit bounded quiescence/inhibition of the approved mutator units,
one physical account owner with the new adapter/protection/guard loop, source/
PID/lock/restart verification, separate fresh exact money GO, then owned unwind
and scoped rollback only after no uncertain send/owned exposure remains.

The old units were **not** stopped/masked; no replacement was installed or
activated. In particular, the physical owner callback and supervisor binding are
not delivered as an active or launch-ready service. The handoff design is a
reviewable fallback, not a claim that only toggling a flag remains. This is the
remaining engineering/application boundary; it is not a research/PAPER gate.

Exact10 proposals and stops: `prepared_dossier_native_v2.json`, SHA11705c04…ac46,
plan4855c37a…d7d83. It is a dated preparation candidate, **not an active money GO
packet**. No exact launch command or monetary permit is issued while unbound.

## Verification / preserved scope

Targeted regression:536PASS, including original251 KITY vectors. New tests cover
real request signing/schema, exact215/V1–V2 preservation, owner/no-GO refusal,
durable send-before-call, duplicate/unknown-send recovery, partial/native guard
states, exact cash rows and source UNKNOWN. Root review found and fixed a stale
duplicate-proposal POST path, nonpersistent readback failure and rehashed-plan
quantity/cap validation. Local native/recovery tests remain synthetic.

Actual V3 saved-source replay and original V1/V2 previews match exactly under
network denial. Original intake/source manifests remain unchanged. Full repository
suite was not run; no independent review quota retry/replacement.

Five bounded SSH observations (one source inventory failed; bounded direct-file
follow-up retained it),59 broker GETs, zero broker/VPS writes or process changes.
AppleDouble `._*.py` metadata syntax errors were not treated as application code
or repaired. Alpaca frozen Oct15 code/HALT/opening priority, Claude/research,
ATT1 and liquidation processes remain unchanged. No judge/outcome/PAPER run or
new gate/automation was added.

Official contracts: [HMAC authentication](https://bybit-exchange.github.io/docs/v5/guide),
[orders and IOC](https://bybit-exchange.github.io/docs/v5/order/create-order),
[Full native stops](https://bybit-exchange.github.io/docs/v5/position/trading-stop),
[transaction rows](https://bybit-exchange.github.io/docs/v5/account/transaction-log).
