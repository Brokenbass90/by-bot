# LIQ research delivery implementation plan

**Goal:** deliver the existing V2.1 epoch to Claude daily without altering its collector or research rules.
**Spec:** published `research_lab/ZAPROS_CODEX_LIQ_EKSPORT_2026_10_17.md` and
`research_lab/dosie/ZAGOTOVKA_DOSIE_LIQ_OTSKOK_4H_V2.md` at origin431cc92.
**Architecture:** unchanged normalized exporter; immutable heartbeat/gap sidecars and last-published delivery receipt; idempotent byte-preserving mirror. No record deduplication, outcome access or source gate verdict.

- [ ] Add tests for immutable export, exact timestamps/duplicate retention, known disconnects, source identity, corrupt hashes, partial publication/restart and repeat import without new bytes.
- [ ] Implement `research_lab/liq_research_delivery_v1.py`: `seal_daily(root, day)` and `import_snapshot(exports, destination, day)`, own locks, fixed epoch, SHA verification, create-exclusive files; copy normalized bytes exactly.
- [ ] Add default no-network CLI for explicit seal/import. Install isolated daily00:10UTC export unit with low resource priority, no network or credential access, only own export directory writable. Never restart the existing collector.
- [ ] Read fresh25 instrument metadata and selected-account taker fee using GET only. Preserve exact receipts privately, publish sanitized source facts; unknowns remain UNKNOWN.
- [ ] Deliver first actual snapshot to Claude's named data directory. Existing research files/KARTA/VOROTA stay untouched. Add recurring local pull through the supported app scheduler; no messages to Claude.
- [ ] IBIT19Oct forward→Claude journal remains scheduled acceptance work, MassivePENDING. Preserve Alpaca/KITY P0 board, current financial units/pins/foreign allowlist. Publish tests, receipts, commits and concise delta.

Review: partial writes cannot overwrite an old seal; cumulative snapshots must not double-count deliveries; raw duplicates stay; gap hours are UNKNOWN (the Claude consumer currently does not apply gap sidecars and must be repaired by Claude); historical rows never become prospective decisions. Root-only review restriction retained.
