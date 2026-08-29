# Current handoff — 2026-08-29

Canonical tree: `bybit-bot-recovery-20260824`.
Canonical branch: `codex/recovery-20260824`.

Read first:

1. `reports/CODEX_SESSION_CHECKPOINT_2026_08_29.md`;
2. `reports/CURRENT_PROJECT_ROADMAP.md`;
3. older dated reports only as history.

## Current gate

`RESERVED_OOS_RUNNER_CLOSURE` is complete and independently reviewed:

- spec verdict: `PASS`;
- code-quality verdict: `PASS`;
- Task 1-3 focused suite: `66 passed`;
- preflight: `READY_FOR_OWNER_AUTHORIZATION`;
- owner authorization, one-shot claim and scored result: absent;
- live/broker/order/risk/money changes: zero.

Public major-8 M5 rows for `[2025-10-01, 2026-07-01)` were materialized and
validated under the separately authorized no-score operation. They were not
scored. The metadata-only preflight and independent pre-execution audit opened
zero market payloads and decoded zero rows.

## Next action requires the owner

Do not run the one-shot implicitly. Ask for one explicit owner decision. If the
owner authorizes it, create the hash-bound one-shot authorization, run the
frozen diagnostic exactly once, then run the independent post-execution audit
and publish any sign. A PASS grants only zero-risk integration review; it does
not grant money, order, risk, slot, universe or promotion authority.

Alpaca remains a separate SAFE_HOLD track. Historical replay can compress most
selector, gap, restart, partial-fill and stop-ratchet checks, but cannot replace
a short prospective broker paper lifecycle under the real bridge.
