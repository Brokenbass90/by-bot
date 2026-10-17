# Alpaca strategy parity repair implementation plan

> Execution: superpowers:executing-plans, root-only. Prior exhausted independent
> reviewer restriction remains; no subagent/reviewer retry.

**Goal:** prevent another stale-selection/stale-ATR entry and produce a source-bound
comparison against the exact validated reference, without changing current NET.

**Architecture:** reuse `prepare_intended_report`, `_atr20`, existing reference
stop quantization and manager primitives. A transport-free entry gate/receipt is
consumed by a strict orders-OFF preview; legacy sealed intakes remain readable.
No change to deployed maintenance, HALT, order authority, strategy parameters or
sealed research outcomes. An unresolved reference mismatch can never become PASS.

**Spec:** owner's October16 parity handoff and five Claude corrections;
`reports/ALPACA_STRATEGY_PARITY_REPAIR_2026_10_16.md` reference inventory.

## Constraints and review focus

- Baseline monthly versus approved Dynamic weekly is explicit, not redefined.
- One intended next-session signal; off-cycle confirmation cannot replace ticker.
- ATR20 uses the last completed session before entry, no entry-day/future bar.
- Raw quote CTS/source, full source identities and actual-fill stop provenance.
- Existing NET floor/ratchet/manager unchanged; all future entries stay HALTED.
- Daily proxy versus intraday cadence and exact stop rounding must be reported.
- Incomplete history/pagination/source availability is UNKNOWN, not zero/PASS.

## Tasks

- [x] Pin exact supplied baseline runner/manifest: research981b62f, reference
      2e68b1f,8code/config/59data pins. Independent exact core2347a7ec606cd845.
- [x] TDD transport-free entry gate: Friday→Monday valid, missed entry blocked,
      no substitute ticker, wrong ATR date/invalid/future bars, quote source/CTS.
- [x] Add source-bound raw ATR/selection/actual-fill stop receipt, orders-OFF only.
- [x] Bind strict monthly production preview/rotation/retention to these receipts;
      preserve old sealed intake compatibility and existing NET maintenance.
- [x] Replay recorded Oct9 source and Oct15 intent: source identity and stale
      rejection; current stop is not recalculated/applied to the broker.
- [x] Differential ratchet/rounding/cadence table against reference code and saved
      source; classify known differences without adjusting strategy rules.
- [x] Inventory4declared source books and complete retained broker order history;
      every known prior intent gets ON/OFF/OPERATIONAL_VALIDATION/UNKNOWN with
      evidence and explicit audit coverage. No future outcome/judge consumption.
- [x] Publish compact evidence/diffs/hashes for Claude read-only review. Keep
      global parity BLOCKED until every material comparison is actually resolved.
- [x] Owner explicitly selected monthly/daily baseline on October16; no
      activation follows automatically.
- [x] Bind daily completed-close source and
      durable next-session ratchet, not intraday market-price sampling.
- [ ] Independent Claude review and final full production parity.

After this P0: KITY batch/private-WS orders-OFF under unchanged owner bounds,
then Elder HEDGE_V1 adapter. Separate deliverables; no automatic deployment/GO.

## Approved monthly binding continuation

Use the existing monthly calendar, selector, native rotation/ownership/recovery
primitives. Keep all existing frozen source files and active NET installation
unchanged. New versioned source/book/runner are orders-OFF.

1. Freeze owner contract/caps and make a durable monthly book: source-bound
   signal/selection, retained-name HWM/floor preservation, stale owned rotation
   intentions, protective-only21day cooldown. Atomic restart/repeated-source
   checks; no off-cycle entry and no new money authorization.
2. Bind completed daily raw source/calendar/availability, daily-close state and
   pending next-session stop intentions. No intraday marks as daily close; no
   partial-day OHLC pretending to be a completed source. Missing source keeps
   existing protection and blocks a new ratchet, never fabricates a close.
3. Bridge raw ATR/fill to native protection in the candidate; reuse existing
   native rotation and dispatch semantics, never dynamically patch active NET.
4. TDD/replay saved real payloads and exact reference; construct disabled package
   and explicit remaining production transport/authority matrix. No claim that
   a source/planner-only worker is a finished monetary executor.

October17 delivery: ALPACA_MONTHLY_PRODUCTION_PARITY_CANDIDATE. Durable/native
candidate and disabled32-fileV2 installed, no livefinancialsender activated.
375targetedPASS; final full5257PASS/60existingFAIL, no newfailure names. Sealed
event replay64/64,24selections/66stops/637closes/152ACKs/56protective exits/
8rotations/486restarts; no baseline simulator rerun. Entry quantities are supplied
fills, not independent sizing/accounting proof. Root review found/fixed original
HALT-path omission; finaltargeted + physicalpackage verification cover it.
IndependentClaude review/final strategyPASS/ownerHALTrelease remain unchecked.

October17 independent review7800b72: logicalmonthly/dailyPASS, sizeUNKNOWN.
- [x] Sizeproof: invoke actual prepare_entry calculation on referencecash1000
      with uncapped no-client/no-constructor fixture; independently debitcash,
      markretained names and compute66qty;64closednotional/qty match≤1e-9.
- [x] Confirm66productionceiling cases and constructor487.42 guard unchanged.
- [x] Real-client serializer regression found204.7164→204.72 budget overshoot;
      monthly9dpROUND_DOWN +exactwire journal/readback fixes it, legacy2dp stays.
- [x] 394targetedPASS; V3disabled32fileinstall/59NETpins unchanged/0brokerHTTP.
- [ ] Claude confirms sizingproof +narrowwireencodingdiff, then fullstrategyPASS.
- [ ] Existing operational DAYreadback/alert/protection-time gaps handled before
      financialactivation; not a newstrategy/statistical requirement.
