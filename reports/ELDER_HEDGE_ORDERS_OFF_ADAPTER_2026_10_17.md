# Elder Crash Hedge — ORDERS_OFF adapter, October 17

**ELDER_HEDGE_ORDERS_OFF_ADAPTER_DELIVERED / BLOCKED_SOURCE_CONTRACT.**
Standalone Elder remains KILL. No collector/research/outcome judge was run,
no live shadow rows were read, no money policy or service was activated.

## Delivered

`research_lab/elder_hedge_orders_off_v1.py` consumes one explicit first raw
ETS2S decision, causal regime/risk snapshots and instrument constraints.
It emits SHADOW intent/ownership namespace, native guard, two CONTROL targets,
OpportunityRecord V2 join and ReportEvent v1/TAX-A preparation fields.
Unknown actual money/order/fee/funding values remain UNKNOWN, not zero.

Frozen rules preserved: short only, limit close×1.002, six subsequent H1 bars,
expanded stop×4, f1=.55, maxhold336h, source MAX_LEV100,
HEDGE ON BEAR/NEUTRAL/explicit UNKNOWN; BULL rejects only new entries.
Detection clock explicitly uses the existing ETS2S source bar-open convention,
not an invented availability timestamp. Missing causal geometry blocks.
Risk budget<=portfolio/3, trade budget=sleeve/6, max6/open-symbol exclusion,
no eviction. Qty rounds down; price/native stop round conservatively to tick.
These are calculations against supplied Risk Engine inputs, NOT a deployed
capital allocator or authority to change account settings.

Separate synchronous-FULL SQLite book deduplicates opportunity IDs across
restart, detects conflicting intents, refuses foreign SQLite/symlink paths.
It is a shadow-intent journal, not a financial position/portfolio reservation.
Existing common writer primitives are the intended later execution binding;
this adapter deliberately exposes no broker client/credential loader/sender.

`elder_hedge_frozen_fill_v1.py` contains the **unchanged** pure ispolnenie
function from yadro SHA b413a48f67158ccb4a69c769bb1114065468a9610eace7d367400555d4821b66,
matching the already published ETS2M manifest. Function SHA
54a962ba22d4a9bf2490bf23874706dfefa3feacecff3b351d110c476d474946.
No bootstrap/import of the ignored research judge or cold signal regeneration.
Only contiguous completed H1 bars are used; pending bars remain PENDING,
never synthetic NO_FILL or exit-at-last-bar. A reference touch predating the
intent is explicitly ambiguous and never claimed as a broker fill.

Saved-input CLI: `scripts/elder_hedge_orders_off_v1.py --bundle <file>
--bundle-sha256 <pin> --output <new-receipt>`.
Create-exclusive receipt, explicit saved-source label, no network/order option.
No actual source bundle has been consumed in this delivery.

## Two material source/contract issues, found before live ingestion

1. **FIRST_ETS2S_ROW_LACKS_DECISION_GEOMETRY.** Code-only inspection of ten.py
   shows initial zap contains ts/sym/side/zapisano/vovremya. stop_dolya/rr1/rr2
   appear only in the later `res is not None` branch alongside R/barov.
   yadro.istochnik_vhodov explicitly requires closed decisions to obtain them.
   That is valid for its existing historical comparison, not for a new causal
   live execution adapter. Do not backfill an earlier intent from terminal
   geometry or rerun the stateful strategy cold. The warm producer needs a
   versioned first-decision snapshot with ref_close/e_ref/raw_sl/raw_tps/f1 and
   actual availability/source pins. The adapter accepts no late geometry as
   if it were in the first record. Claude's source remains untouched.
2. **CONTROL_STOP_ANCHOR_RECONCILIATION_REQUIRED.** The terse frozen contract
   specifies absolute stop e_ref+(raw_sl−e_ref)×4. yadro.prodvinut instead uses
   risk=actual_fill×stop_pct, stop=actual_fill+risk for shorts. They differ
   whenever fill!=e_ref. Example only: ref_close=e_ref100, raw_sl102 gives
   native absolute108; limit100.2 gives CONTROL108.216. Both are exposed;
   no silent formula choice or promotion. Research owner must clarify the
   authoritative executable stop/target anchor, with a versioned contract.

These are the exhaustive observed blockers for actual source intake in this
bounded delivery, not new statistical gates. Producer amendment/anchor
clarification remains required before production shadow parity can be claimed.

## Verification and deployment

**20 new /31 targeted PASS**, including frozen function identity, causal clocks,
source incompleteness, long/late rejection, regime states, risk/lot/capacity,
durable restart/conflict, pending/no-fill/touch, completed-H1 integrity,
saved-input CLI/no-overwrite and existing ETS2M isolated-fixture tests.
No actual ETS2M900 re-evaluation or hedge outcome result was consumed.
Installed a24-file source kit on VPS **disabled**, import/source hashes verified;
no unit registration or money transport. Evidence in
`evidence/elder_hedge_orders_off_20261017/` records exact research/code pins,
sourcekit and test-log hashes. This is not ELDER_CANARY_READY.

Prospective gates unchanged:>=30 events, intentions>=97% within1tick/1lot,
execution decisions>=95%,0 unexplained material defects, restart PASS,
latency<=5min in>=95%, original ETS2M900 gate, then bounded dossier/owner GO.
No real events are credited from these fixtures. Alpaca/KITY/ATT1/LIQ untouched.
