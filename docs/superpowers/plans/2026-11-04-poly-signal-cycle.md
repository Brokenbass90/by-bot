# Polymarket signal → snapshot → resolution implementation plan

> **For agentic workers:** use superpowers:executing-plans inline; one bounded critical review at completion. No framework/service/strategy.

**Goal:** consume Claude's confirmed POLY_SIGNAL_V1 V1.1, capture a real timely quote without orders, append an official model outcome by immutable identity.
**Architecture:** extend existing snapshot CLI with a bounded --cycle-once hook; one lifecycle helper owns chain/provenance validation and immutable state. The existing producer/watch loop must call this hook; no second daemon or collector. Existing measure/join functions reused.
**Tech Stack:** Python3.12 stdlib, existing durable once/read/GET transport.
**Spec:** owner's4Nov E2E instruction; sibling research_lab/KONTRAKT_SIGNALA_POLY_V1_1.md and owner-relayed Claude ACK04Nov08:42UTC.

## Global constraints

- Source POLY_95_V2_SHIROKO is control-only, removed from LIVE queue; no research verdict/prereg/source edits. No future-signal fabrication or historical entry replay.
- Exact market/token/policy/source SHA; source paths fixed to existing broad monitor, never follow arbitrary signal paths. Source journal complete newline prefix only, full hash chain + previously witnessed prefix preserved; no source flock or partial-tail repair.
- Consumer observation after fsync proves availability then, not claimed earlier producer durability. Market open != sports match unfinished; before-sports-FINAL remains UNKNOWN absent independent sports witness.
- Freshness bound120s for input, book10s/Gamma60s; not a financial rule change. Late inputs retained as blocked, never retimed/replayed.
- Captured feeSchedule only; actual budget/limit bounded by existing100/.985 measurement ceiling, source budget retained. Model net not fill/PnL/finality.
- Explicit official resolution condition selector, terminal status/resolved_at/payout proof; proposed/disputed/open/missing/ambiguous => PENDING/UNKNOWN. No settlement inference from price/closed/endDate alone.
- No broker/auth/key/order/financial mutations, no Brain/Factory, no source worker restart. Sensitive mail evidence stays local.

## Review focus

Source-ID collision after producer restart; journal rewrite/truncation/partial tail; symbolic/path traversal and arbitrary source path; mismatched outcome token; official resolution before actual measurement witness; simultaneous consumers; crash after intake before measurement; stale post-hoc input; unknown sports-event finality; no manufacture of completed E2E when source signal absent.

### Task1 — verified signal intake and capture
Files: new research_lab/polymarket_signal_cycle_v1.py; modify scripts/measure_polymarket_snapshot_v1.py (reuse run_member) and research_lab/polymarket_v2_orders_off_v1.py (bounded optional measurement budget); tests/test_polymarket_signal_cycle_v1.py.
Interfaces: cycle_once(research_root,journal_name,state_root), validate_signal; run_member(member,proof,destination,signal=...).
- [x] RED: source-backed signal/budget/captured pair, same-ID idempotency, policy/source/token drift, newline partial prefix and witnessed-prefix rewrite/truncation, stale/future input, source path escape.
- [x] Minimal implementation, targeted GREEN incl existing56 tests; no source writer changes.

### Task2 — official outcome and existing-loop hook
Files: same lifecycle/helper CLI/tests + contract handoff/evidence report.
- [x] RED: default no-network CLI; pending resolution/terminal official winner+time -> exact model join; no join for proposed/ambiguous/mismatched/earlier resolution or receipt tampering; no duplicate join.
- [x] Add fixed GET condition-resolution endpoint, immutable poll/join parent hashes and cycle-once entry point for existing producer loop. No new worker.
- [x] Run focused suite and one bounded critical review; fix material findings with RED→GREEN; preserve accepted snapshots.
- [x] Actual invocation: genuine journal only; absent signal => WAITING_REAL_SIGNAL. Future outcome => PENDING_OUTCOME. Completion only from actual new signal/witness/measurement/future official join; document hook installation status honestly.
- [x] Update checkpoint/roadmap and scoped publish excluding private mail/foreign files. No hard completion date promised.

4Nov steering: confirmed V1.1V3/nulltoken/sourcekak, owner-relayed E2 fix/sourceSHA after actual E1 corruption. Added pinned E2binding;88PASS; exact runtime installed/automatichook actual12:42UTC.
Ruling: V3 sports rawframe unavailable; timestamps checked, beforeSPORTSFINAL deliberately false. Costifwrong: no economic/causalpromotion; freshquote inspection remains valid.
Task1engineering+Task2hookdelivered; real first E2signal/officialfutureoutcome not yetoccurred, so objective PENDING notcomplete.
