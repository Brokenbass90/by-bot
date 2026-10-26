# PUMP4 native stop mapping implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Continue in the dedicated recovery checkout under the owner's detailed OFF implementation instruction; no new financial permission.

**Goal:** Represent the frozen reference stop on Bybit's tick grid without widening risk or increasing quantity; preserve restart/send-once behavior.
**Architecture:** Pure versioned mapping beside the unchanged reference plan. Optional immutable mapping only on off-tick lifecycle configs; legacy exact-tick configs/CIDs stay byte-identical. Checked sources derive/revalidate it; mapped financial dispatch stays disabled in this OFF delivery.
**Tech Stack:** Python Decimal, existing source validation, lifecycle/hash-chain and memory Bybit.
**Spec:** reports/PUMP4_OWNER_DECISION_2026_10_26.md and owner's26Oct attachment570271fd.

## Global constraints

- Producer/intake/reference plan/hash/40–60/hold168/60s unchanged; no moneyGO, broker writes, Monthly changes or funding download.
- SHORT floor, LONG ceil; native stop positive, tick aligned, protective beyond reference entry and fresh LastPrice; reject invalid geometry.
- Keep original reference/adverse risk distance for qty; rounding cannot increase size or loosen caps.
- Persist mapping plus metadata snapshot/hash once; resume validates, does not regenerate from new metadata. Fresh tick/identity/native price must agree before entry.
- Mapped readback must equal mapped stop and correct trigger/side/full qty. Legacy semantics stay unchanged.
- Preserve explicit distinctions:84 offline protocol fixtures != current-account admission; unknown costs != zero.
- Existing lifecycle5s/exact-open gate is a separate residual blocker, not silently relaxed here.

## Review focus

Tampered mapping/plan/tick; changed metadata before entry; rounded stop at/past trigger; wrong tighter native-stop adoption; partial qty/ambiguous send on restart. Each receives a focused test.

## Task1: Mapping and integration

Files: new research_lab/pump4_native_stop_v1.py; pump4_execution_lifecycle_v1.py, pump4_account_adapter_v1.py, pump4_account_owner_v1.py; focused tests.
- [x] RED tests for mapping, legacy config identity, restart/tamper/exact readback, unchanged sizing and OFF dispatch guard.
- [x] Implement pure mapper and optional immutable config; checked-source integration.
- [x] Targeted tests + scoped existing PUMP suite; one critical review.

## Task2:84-case evidence

- [x] Run all84 reference geometries through native mapping and offline protocol/restart/TP40–60/ambiguous-send checks, explicitly label memory-only evidence.
- [x] Separately retain every real-source sizing/cost/geometry blocker; never raise financial risk/qty for fixture acceptance.
- [x] Preserve local/VPS exact package acceptance; no financial deployment/GO from tests alone.

## Task3: Remaining concrete gates

- [x] Source-only sync29366fb/76c9041/publication; consume Claude funding result only when ready, do not duplicate running download.
- [ ] Narrow measured CURRENT prefix work, retain full existing acceptance validation and new-H1 proof; no300s.
- [x] Bounded KITY status from existing evidence, no backtest/runtime selection.
- [ ] Update canonical checkpoint and commit measured outcomes.
