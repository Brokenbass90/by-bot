# Production data and shadow integration — execution plan

Authority: owner's17 October direct implementation instruction. No new
architecture/spec review requested; use published frozen contracts. Work on
existing `codex/recovery-20260824`; preserve unrelated allowlist and Claude tree.

## Constraints

- Money Lane and OS Lane proceed concurrently. Neither waits for full Brain.
- No LIVE source, manager, strategy, risk, HALT, service or financial authority change.
- KITY today's personal-only micro policy remains untouched; observe after owner action.
- No sealed outcomes/judges, policy tuning or duplicate Brain/financial truth.
- Existing source-pinned Alpaca32-file candidate stays byte-identical.
- Read-only data source acceptance is distinct from actual trading/ten-session proof.

## Task1 — Alpaca source and schedule (root)

New `research_lab/alpaca_monthly_source_ops_v1.py`,
`scripts/run_alpaca_monthly_source_ops_v1.py`, associated targeted tests.
Reuse frozen Yahoo1h/unadjusted/RTH fetcher, aggregator, broker calendar normalizer
and MonthlyBook;57 frozen tickers+SPY, complete latest session and200-session
warmup, full raw/source hashes, no interpolation/current partial bars. New
capture directory only. Source failures return one bounded per-symbol issue list.
Daily/month-end schedule follows actual calendar/DST/half days and writes only
an isolated orders-OFF source book. No native financial constructor/transport.

- [x] RED→GREEN coverage/missing-symbol/missing-hour/nonfinite/hash/partial/future,
      calendar/DST/halfday, idempotence/revision/no-authority tests.
- [x] One actual full-universe public-data capture and real GET-only broker
      calendar; classify DATA_READY or exact DATA_BLOCKED without relaxed gates.
- [x] Prepare source-only runbook and systemd-validated units; actual separate
      data timer activated and VPS bootstrap PASS. Ruling: direct owner's source/
      schedule/ORDERSOFF instruction permits this isolated data activation; no
      financial unit/current NET book is touched. No monetary activation follows.

## Task2 — IBIT DATA-ONLY (isolated worker)

Published07438fc v1.1 + base5a23fc3; existing frozen rule source reused exactly.
Own adapter/CLI/tests/vendor namespace. SIP/raw timestamps/full hashes,
calendar, fixed15–16NY BTC, earlycloseNO_SEND, immutable unique-session decisions,
separate append-only Massive QA/restart. No financial API or source daemon.

- [x] Targeted RED→GREEN source/restart/halfday/QA/parity checks.
- [x] Root integrates/reviews and records limitations; no10-session claim.

## Task3 — Brain read-only receiver (isolated worker)

Published0efbca7 prereg/source. Own adapter/CLI/tests. Map actual producer aliases,
validate context/availability/source/policy pins and append idempotent SHADOW
envelopes. No scoring/allocator duplication. HEDGE/CONFLICT/INDEPENDENT separate
metadata; producer UNKNOWN remains UNKNOWN and no frozen policy is repaired.

- [x] RED→GREEN causal/tamper/restart/relationship/source-destination checks.
- [x] Root integrates/reviews; source-policy findings go to Claude delta.

## Completion

- [x] Focused combined tests and bounded full-suite baseline comparison; preserve
      pre-existing failures, no unrelated repairs or green-suite claim.
- [x] Fresh KITY/account readback after source-only deployment; no market recapture.
- [x] Receipts, canonical board, per-lane commits; concise Claude delta.
      Independent-review quota restriction remains; root review, no replacement.

Code: ab68e36 /9fcb4cb /9177b75. Receipt/document publication follows in the
same bounded cycle. Actual Brain V2 event remains external/input pending, not
fabricated by importing old history; IBIT collector/10 sessions remain separate.

## Authorized continuation after Claude/PM actual-event report

- [x] Recheck same producer journals after13:52UTC; actual8 events/twoV2 received,
      full-chain validation and restart replay without duplicates. No outcomes.
- [x] Deterministic Monthly Oct19 NO_SEND/month-end contract receipt; existing
      nativeDAY/ratchet/restart/foreignNET/sizing checks,57PASS; conditional KITY
      Oct22/23 dossier filled with exact proved/open gates, no money command.
- [x] Fixed GET-only IBIT collector, immutable first network captures, delayedQA
      provider→normalizedQA link, typed errors, disk limits, capture-only probe.
- [x] Immutable historical81-session seed before forward decisions; real receipt
      causality/raw lineage, no backfilled freshness/QA/prospective credit or
      frozen rule change; avoid61new-session wait.74IBITfocusedPASS.
- [x] Isolated six-file DATA-only VPS source package and timer; actual16Oct probe
      four sourcesCAPTURED, errors0, decisions0,97financial/sourcepins preserved.
- [x] Actual81historical network bootstrap, restart readback, final preservation
      receipt and canonical publication; no future-event PASS.
