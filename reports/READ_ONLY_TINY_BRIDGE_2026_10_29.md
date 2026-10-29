# PUMP4 observation / one-candidate Research → TINY — 29 October 2026

**Delivered: file-only observation component and one actual KITY intake. No new financial integration.** PUMP4 remains `LIVE_ARMED_HEALTHY`, waiting for a signal; Monthly v6 remains selected. This change creates neither a trading engine nor automatic research promotion.

## DONE / actual evidence

- Existing `BrainEventJournal`/`ShadowJournal` reused for actual PUMP4 execution receipts in a separate lab DATA journal: `../bybit-bot-clean-v28/research_lab/data/brain_pump4_live_observer_v1`. Two distinct samples, **192 immutable receipt events**, no lifecycle events. Each snapshot replay added **0** records. Latest capture selected the 96 newest receipt files by mtime; status samples are **not an opportunity census**.
- Raw source scope/config/receipts kept private in `.private/pump4_brain_observer_20261029`; only sanitized summaries/source hashes are published. Scope has canonical-JSON identity, config has byte identity, and scope's financial config projection excludes authority/runtime aliases exactly as the existing runner does. Stable event-ID buckets prevent changed timestamps evading conflict detection; receiver uses existing locks/hash chain/fsync/capacity limits, never repairs partial evidence.
- Fixed allowlist SSH reader opens only packet `scope.json`, `runner.json`, selected `owner-scope.json`, bounded supervisor receipts and three explicitly named flow journals. It never follows `credential_source` or `source_files` paths, invokes financial constructors, or writes on VPS.
- Existing Brain advice journal verified: **225 chain records, 87 PUMP4 rows, 0 V1.1/V1.2 version labels**. `do_ishoda` does not prove a timely LIVE decision. No causal versioned comparison or model improvement is claimed; comparison **UNKNOWN**. Need version, policy SHA, stable signal identity and independently witnessed availability before actual decision. No historical judge/outcome/policy was run.
- Local-app heartbeat `pump4-read-only-brain-receipts` created ACTIVE, every six hours, quiet while unchanged. It uses the tested file-only capture/import; first scheduled run is still future. It supplements native VPS safety/Telegram, depends on the Mac/app being available, and does not replace or change a server process/cron. Every snapshot retains actual arrival time; sleep is not retroactive observation.

Evidence: `reports/evidence/read_only_tiny_bridge_20261029/` contains first/latest imports, replays, advice audit, operational readback, KITY intake, review status and source hash manifest. Raw broker/account configs are not committed.

## P0 continuity / expiry

Independent existing GET readback at `1793276409800`:

- Exact PUMP4 scope `fec235e3…fcf794`, config `fa0b3b2e…53014a`, PID3198429, zero restarts; health `LIVE_FLAT_WAITING_SIGNAL`, no entry proven. Same50/30/20 scope and original expiry, no GO or activation replay. `orders_allowed:false` in the health observer concerns the observer's rights.
- Latest96 sample contains **one** `BLOCKED_OBSERVATION/SourceError`, followed by42 normal `NO_NEW_SIGNAL` ticks; fresh health is healthy. Root cause is UNKNOWN, not silently classified as no opportunity and not repaired by changing LIVE. The failure is retained in evidence; no claim that all ticks were error-free.
- New-entry authority ends **1 November 2026, 19:26:32.774 UTC**. Current expiry state `WAITING_WITHIN_ENTRY_PERIOD`. No automatic extension. Owned position custody/exits continue after expiry. The expiry classifier requires a fresh post-deadline capture AND complete durable empty monetary history AND broker-flat proof before `NO_TRADE_CONFIRMED`. This snapshot does not prove exhaustive history, so those future facts cannot be pre-approved. Absence of an entry in a sample is insufficient.
- Monthly unit SHA unchanged `9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d`; timer active/waiting/enabled. Budget400/280/40, strategy, risk, data and the30Octsource→2Novconditional entry/CASH calendar preserved. No Monthly reactivation or broker writes by this change.

## One actual intake / next TINY readiness

This exercises the existing **KITY22Oct** signal/C2/shadow-entry packet, not another economic experiment and not a promotion over Polymarket. Research ref `5c71a9a30e2c7584d18ef3c40cf9d345502ea05d` read without merging or touching Claude's code.

| Gate | Actual result | Bounded next action |
|---|---|---|
| Frozen signal parity | Existing C2 PASS_MATCH_ONLY,50features; exact saved signal hash matched | Reuse accepted selector/C2, no new signal research |
| Cardinality | Actual5L+5S=10; published helper still says4L+4S=8 | Claude must reconcile/version dossier; do not drop/pad legs in executor |
| Saved sizes | 10 shadow quantities, all pass dated step/minimum/notional check; ≈990.74USDT shadow gross | This is the research100/leg sample, not an owner budget or current sizing proof |
| Economic gate | Original ECONOMIC_INCONCLUSIVE | Published qualifying economic verdict required; C1/C2 never substitutes |
| Costs / margin | Fresh fees, seven-day funding, slippage/depth, leverage/margin/stress UNKNOWN | Dated account/instrument/quote capture and cost bounds; missing activities never mean zero |
| Financial ownership | Active sole Bybit owner is PUMP4 | Separate isolation or explicitly reviewed common-owner route; never start a second financial writer |
| Weekly lifecycle | Existing micro primitives reusable; weekly exit/native/recovery/R5 acceptance not established | Bind frozen weekly contract to existing primitives; ORDERS_OFF replay/partial/failure cases |
| Financial GO | No new exact weekly KITY scope | Only after preceding gates; old spent micro300 scope cannot be reused |

Result **NOT_READY_FOR_TINY**. The public source dossier's `NOG=8` is a concrete mismatch, not proof all KITY signal logic is broken. The generic handoff checklist is `docs/RESEARCH_TO_TINY_HANDOFF_V1.md`. No new allocator or Factory trading worker exists. No automatic changes to KARTA/prereg/judge or messages to Claude.

Independent work now possible: reconcile published dossier cardinality, supply causal versioned advice, and complete read-only cost/ownership evidence on an economically eligible candidate. Account sharing and weekly lifecycle still need specific design/acceptance; they are not a one-line activation. Canonical engineering queue remains Polymarket → KITY while preserving PUMP4 and Monthly.

## TESTED / REMAINING / BLOCKERS

- **75 PASS**: two new targeted suites plus existing Brain receiver and OS2 journal regression. Tests cover source pins/projection, replay, changed-time conflict, corruption/aliases, lifecycle prefixes, partial-tail nonrepair, expiry proof requirements, research side/size/rounding mismatch and noncausal advice. Real SSH capture/import/replay and existing health GET also executed; these are distinct from unit tests.
- Primary reviewed the file-only boundary and actual saved outputs. Bounded independent critical review requested Astra/high; runtime metadata confirms both settings (`01a1871e-02b7-70f3-898d-86b5fc91295c`), but worker hit usage limit before returning a review. **Independent critical PASS is NOT claimed**, no retry/fallback charged. That review remains required before broader integration; this change only delivers isolated DATA observation/intake.
- No actual PUMP4 fill/native40-60/exit/terminal net economics exists to compare in this capture; future execution and final fees remain future evidence. Scheduled observer run acceptance remains future; manual capture/import is accepted. Advice source contract and KITY economic/account/weekly gates remain external/engineering blockers as above.
- Initial broad capture command was rejected by automatic approval review before execution because it iterated all `source_files` paths and might reach secret material. The approved replacement uses an explicit evidence-only allowlist and never reads those paths. No rejected action was executed, and no such block remains unresolved.

Commit: see published Git commit for this report and the canonical checkpoint. Private inputs and foreign `configs/allowlist_change_log.json` remain unstaged.
