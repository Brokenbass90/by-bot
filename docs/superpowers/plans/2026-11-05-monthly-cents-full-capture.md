# Monthly cents and private rejection capture implementation plan

> Execute inline with superpowers:executing-plans; one bounded independent critical review after targeted verification.

Goal: implement the owner-approved local Monthly cents candidate and exact private broker-rejection capture; no real POST or LIVE deployment.
Spec: reports/MONTHLY_CENTS_NEXT_PACKET_DRAFT_2026_11_05.md plus explicit owner GO in this chat5Nov.
Architecture: reuse native serializer, existing Monthly transport/intent/book and manager observations. Preserve old recovery records and non-Monthly behavior. Private response evidence belongs under existing manager runtime, not a new service or financial journal.
Tech: Python Decimal/ROUND_DOWN, existing atomic create-exclusive publish_once, urllib HTTPError, pytest in-memory HTTP only.

Constraints: no broker operations, key/env access, units/restarts/GO/HALT/lock changes. No PUMP/Polymarket edits. No changed risk, strategy, calendar or money authority. Old3Nov uncertain intent remains spent/no-resend. Source identity changes require future reviewed handoff and separate owner dated BUY GO.

Review focus: old uncertain/recovery intents; float cents boundaries and sub-cent tickets; exact permit vs wire; response body/ID privacy and capture failure; symlink/permissions/truncation/fsync; fill-based STOP and no retry.

## Task1 — cents dispatch and reconciliation
- [ ] Add failing real serializer/transport/intent recovery tests for101.413902261->101.41, cents boundary/sub-cent, permit, retained unrounded cap and old9dp recovery.
- [ ] Extend native Decimal wire helper with explicit precision (legacy9default stays); new Monthly prepares/dispatches2dp, keeps cap, binds exact submitted notional. Restrict Monthly BUY wire to2dp; ordinary Dynamic/default legacy methods unchanged.
- [ ] Run changed and dependent Monthly/native/transport/recovery tests. Fix only intentional cents expectation changes with explicit fixture provenance.

## Task2 — full private capture and safe observations
- [ ] Add failing tests: complete JSON/nonJSON rawbody/requestID private; >8192bytes complete; >2MB explicit truncation; read/write failure original error/no resend; unsafe directory refused; no secrets in public evidence.
- [ ] Read at most2000001response bytes; keep exact first2000000privately plus complete/truncated/unavailable status, hash, byte length, bounded exact requestID. Existing scrubbed8KiB public derivative retained. Never log raw response or headers.
- [ ] Existing MonthlyManager persists capture create-exclusive0600 within owner-only0700 runtime directory, body fsync before manifest. Safe issue references capture ID/status/hash only. Failure never retries financial operation or masks original error.
- [ ] Run targeted acceptance suite and check no selected runtime drift.

## Task3 — acceptance/review/handoff
- [ ] One independent critical diff review; fix confirmed important findings with regression tests.
- [ ] Preserve RED/GREEN and sanitized evidence; source manifest, exact code/test counts, remaining dated GO/handoff gates. Update canonical checkpoint/queue and publish only owned files. Full private body evidence never committed.
- [ ] Report engineering result separately from deployment/BUY; no READY_FOR_BUY claim without fresh authorized account/window/scoped packet.
