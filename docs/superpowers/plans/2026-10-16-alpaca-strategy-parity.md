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
- [ ] Bind strict monthly production preview/rotation/retention to these receipts;
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
- [ ] Owner contract choice monthly/daily vs weekly separate validation; no
      activation follows automatically. Bind daily completed-close source and
      durable next-session ratchet, not intraday market-price sampling.
- [ ] Independent Claude review and final full production parity.

After this P0: KITY batch/private-WS orders-OFF under unchanged owner bounds,
then Elder HEDGE_V1 adapter. Separate deliverables; no automatic deployment/GO.
