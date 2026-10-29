# KITY weekly engineering corrections — 29 October 2026

**DONE: published dossier repair, actual15/22Oct input acceptance, isolated7-day lifecycle and explicit current-owner refusal.** No KITY money authority, broker requests/orders, live dispatcher or changes to PUMP4/Monthly were introduced. This is a completed model rehearsal, not accepted Bybit execution.

## What was fixed

Research commit **30951f9abcdcf56ae4bf853d9168d2ac2d24a34e**, fast-forward published to `research/fabrika-v1` from5c71a9a. Separate temporary Git index/tree; Claude's dirty checkout/index/local branch not touched. Changed only dossier helper, two size/documentation passages,12 regression cases and a specific admission-contract clarification request. Frozen signal/prereg/judge/producer/hold7d/C1–C3 unchanged.

- Removed hardcoded8legs/4L4S. Dossier derives k=n//10 for30≤n≤50, hence6/8/10legs; checks duplicate/missing/wrong-side entry legs. Actual15/22Oct n50 gives5L+5S=10, no padding/dropping or rescaling.
- C2 `C2_PASS_MATCH_ONLY` now accepts the two actual source schemas with binding:22Oct raw signal SHA directly,15Oct original separately pinned pre-comparison source readback. Bare `PASS`/`C2_PASS` cannot produce a ready dossier. Earlier15Oct public receipt remains immutable; no synthetic raw pin was added to it.
- Rebuilt the dossier on copied actual `signal/vhod/kvitanciya_C1` for15/22Oct and accepted C2 receipts. Result **DOSIE_READY** for C1/C2 inputs only; $100/leg is a research example, approximately$1000 before rounding at10legs, not an owner budget or risk guarantee. Actual quantities yield≈990.74USDT reference gross. No exit/outcome/judge files read.

## Full isolated lifecycle actually run

`research_lab/kity_weekly_rehearsal_v1.py` and `scripts/rehearse_kity_weekly_v1.py` reuse existing `LifecycleJournal` and Decimal validation. Model has no network/sender/credential/GO/lease or order switch. Source hashes bind the actual saved22Oct Bybit signal,10shadow quantities and reference prices to C2; they are not relabelled as Binance inputs or real fills.

Actual CLI run produced **252 durable events**:

1.10model entry fills and10fixture native-protection acceptances.
2.Seven-day virtual clock,21explicit8-hour funding settlements per leg, signed qty×mark×rate cash.
3.Normal exit after7days for all10legs and simulated stop cancellations.
4.Flat state with one pending fee: net UNKNOWN and capital not released.
5.Late fee, complete model cost reconciliation, all10quantities zero, model capital released.
6.Restart/replay gives identical state without journal-byte mutation or duplicate effects.

Fees0.0006, funding interval480minutes/rate0.0001, unchanged marks and±10%native stop geometry are **declared test fixtures**, not the account's tariffs, actual Bybit funding/protection or recommended risk parameters. Result `MODEL_LIFECYCLE_PASS`, virtual-clock only; no seven-day market period or future prices were consumed. Model net is approximately−1.192USDT, just the chosen cost fixture at unchanged marks, not strategy economics.

Separate regression scenarios exercised partial fills, lost acknowledgement→restart→GET-equivalent model reconciliation before further entry, duplicated fills/funding, rejected leg→partial basket emergency cleanup, premature exit rejection, native-stop trigger/coverage, unknown fees, missing funding coverage, partial journal nonrepair, and durable R5 halt after two operational FAILs. Flat incomplete/emergency baskets are never counted as a completed normal weekly strategy.

Frozen weekly KITY has no early directional-stop rule. Native-stop execution is therefore a separately labelled **CONTINGENCY_FIXTURE_ONLY/OFF_PROTOCOL** case; it does not rewrite the weekly return or become permission for a real stop. Need a published safety/exit contract before the Bybit adapter can implement protection faithfully.

## One financial owner: concrete reuse / remaining bindings

The saved selected PUMP4 scope was passed to `routing_check`: **KITY admission refused**. No financial owner instantiated and no second lock/manager created.

| Existing component | Reuse | Required change before coexistence |
|---|---|---|
| `kity_micro_physical_owner_v1.AccountLease` | Original account-wide lock/inode818853 | One physical owner process; separate new reviewed handoff, not another writer |
| `SignedPostOnce`, immutable barriers/reconcile | Durable no-blind-retry sends | KITY namespace and per-leg basket ownership must be bound to a separately approved KITY scope |
| `Pump4AccountOwner.__init__/_authority` | Exact scope/custody/entry distinction | Current scope is one PUMP4 entry/position/lifecycle; KITY cannot inherit it. No risk or expiry extension |
| `owned_observation`/`account_view` | Source-backed account/order/fill/cost evidence | Union custody across explicitly registered sleeves; never adopt foreign positions by matching symbols |
| Existing native lifecycle / risk journal | Protection checks, costs/funding, admission latches |10-leg partial-basket unwind, weekly rotation, R5 and aggregate reserve/margin/loss accounting under one future dispatcher |

A successor common-owner dispatcher can hold the same sole lock and route existing PUMP4 custody under its original exact scope plus KITY under a new separate scope. It cannot be selected without source/physical-owner review, account-wide reservation/custody evidence, a safe handoff and new exact financial permission. Existing PUMP4 code rejects a foreign sleeve; adding KITY positions now would violate its account checks. An isolated second account is an alternative, not silently assumed. No common dispatcher was installed in this change.

## Corrected economic classification / exact research request

The earlier generic intake applied the18Oct Binance M3 INCONCLUSIVE label too broadly to the Bybit-native packet. **That was an imprecise classification and is corrected.** These are distinct source/version contracts.

Published Bybit prereg reports historical CROSS_VENUE_PASS187weeks, but also says a money verdict requires26forward weeks. Published canary conditions allow a tiny-canary dossier after two valid C1/C2weeks. Codex does not resolve this by inventing a PASS, KILL, or mandatory26-week implementation delay. New status: **BYBIT_ECONOMIC_ADMISSION_CONTRACT_UNRESOLVED**. The exact version/scope clarification is published as `research_lab/ZAPROS_KITY_ADMISSION_SCOPE_2026_10_29.md` in30951f9; no message was sent to Claude and no judge or future outcome was consumed.

Research must state whether execution-only TINY before26weeks is permitted and on what pre-existing economic/safety basis. C1/C2 completeness and a successful model do not settle that question. This is different from claiming there is no historical Bybit evidence.

## TESTED / review

**98 PASS** in one final command: PUMP4 observer, one-candidate intake, new weekly rehearsal, existing Brain bridge/OS2 journal regressions, and12isolated research-dossier cases. Local final CLI/evidence is separate from tests; no VPS acceptance or actual exchange fills is claimed.

Independent Astra/high review resumed once under the owner's explicit after-reset request and fresh allowed-usage state. Runtime model/effort verified; same review session01a1871e-02b7-70f3-898d-86b5fc91295c. It found four Important issues, no critical money-authority defect:
- Lifecycle observer re-opened source after byte pin: now parses the already-pinned bytes through the existing journal validator on a private unlinked descriptor.
- Bare C2 status bypassed binding: unsupported aliases rejected.
- Off-grid funding counted as cash: explicit fixture calendar required.
- Repeated funding cleared established model finality: same settlement now preserves it.

All four were reproduced RED and fixed GREEN by primary. No second independent signoff is claimed. Existing imported192receipts had0lifecycleevents, so that race did not affect those recorded facts; post-fix replay adds0events. Local observer source manifest updated, financial pins untouched.

## REMAINING / next gates

| Gate | State / next action |
|---|---|
| Dossier8vs10 and C2 intake | **CLOSED**, published30951f9, actual15/22inputs accepted |
| Seven-day pure lifecycle | **MODEL_PASS**, full saved-packet CLI + failure/restart tests |
| Actual-account ORDERS_OFF executor | **NOT_READY**: bind saved real Bybit payloads/rounding/ACK/native-stop/cost/funding sources to the weekly contract; current module is not a transport adapter |
| Safety / partial basket / execution window | Published native protection and emergency policy required; do not invent a research stop or treat historical close as an executable fill |
| Shared ownership / margin / reservations | Current owner refusal proven; future common-owner union-custody/aggregate risk/handoff still needs implementation/review in isolation |
| Economics | Exact Bybit prereg/canary scope clarification pending; source-reported historical PASS distinct from original Binance M3 |
| Financial TINY | No new weekly scope/budget/GO; do not reuse spent micro300 or PUMP50/30/20 |

Owner29Oct engineering priority is now KITY blockers while Polymarket remains research/executability-only until an actual opportunity is proven. PUMP4 and Monthly continue on existing scopes/calendar; no strategy modernization, AI live influence or architecture expansion was performed. Goal Brain/Factory/portfolio development remains on the canonical roadmap, not a new competing plan.

Evidence: `reports/evidence/kity_weekly_engineering_20261029/` — corrected actual dossier, research commit/pins, complete model journal/profile/receipt, owner-route refusal, review and post-fix bridge replay. No private credentials or actual account payloads committed.
