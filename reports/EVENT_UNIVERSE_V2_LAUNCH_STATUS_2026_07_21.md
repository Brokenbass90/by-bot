# Event Universe V2 — local launch status

> **INVALIDATED:** the original spec declared `frozen_at_utc=19:05Z`, but its
> first observation occurred near `18:13Z`. The screen was stopped and the single
> snapshot was preserved without analysis. See
> `reports/releases/EVENT_UNIVERSE_V2_INVALIDATED_TIMESTAMP_RECEIPT_2026_07_21.json`.
> The replacement is the separately frozen V2r2 spec/root; none of the hashes or
> files described below authorize analysis.

Launched after the V2 spec, implementation, supervisor, and source-finality
preregistration were frozen and their focused tests passed.

- screen: `event_universe_v2_20260721`
- run root: `runtime/research/event_universe_v2_20260721_public1`
- started at ms: `1784657620491`
- deadline at ms: `1785262420491` (seven-day hard bound)
- launch receipt: `runtime/research/event_universe_v2_20260721_public1/launch_receipt_v2.json`
- launch receipt self-hash: `d0e92a2270ae349587b82da9e5369d8b4b05ec64655bb7a739f1bcb808abc33c`
- launch receipt file SHA-256: `283aa9985be55a72e4d59e96607ffb1785acd064e645483385196b6169efb5bd`
- frozen V2 spec SHA-256: `91132805c676810a98a716685bd5b2b5ace0491364bad2f3b7d03e52a1af3727`

First persisted observation:

- sequence: 1
- source as-of ms: `1784657621561`
- eligible universe rows: 752
- prefetched/scored: 100/100
- advisory event candidates: 16
- symbol errors: 0
- immutable symbols tracked: 100
- snapshot SHA-256: `47ac3b389904cf687b4312605768fb12ad102944403a6a49a09fe395be276d5e`

The collector is public GET-only and research-only. It cannot read keys or
environment credentials and cannot reach accounts, private APIs, brokers, orders,
transfers, risk, allocator, or the live router. The supervisor retries ordinary
transient public errors up to its fixed bound, but exit code 3 means an immutable
bar conflict and terminates without retry or rewrite.

Verification at launch: 33 focused V1/replay/scorer/V2 tests passed; Python compile,
shell syntax, and diff whitespace checks passed. Safe manual launch command is
`bash scripts/launch_event_universe_v2.sh`; it refuses to start while the same
screen name already exists.
