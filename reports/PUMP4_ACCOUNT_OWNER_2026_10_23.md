# PUMP4 account owner — 23 October 2026

**COMPONENT_PASS; TINY_BLOCKED.** The account-owner adapter now connects the
existing PUMP4 lifecycle to the existing account lease, durable send-once gateway
and risk journal. It was accepted locally and in an unselected VPS candidate:
**178 tests in each environment**, zero failures/errors/skips. These are the same
tests in two environments, not 356 independent broker checks. No real broker
request, order, installed financial unit or owner grant was created.

## Delivered

`research_lab/pump4_account_owner_v1.py` reuses `AccountLease`, `SignedPostOnce`,
`LifecycleJournal`, `Pump4Lifecycle`, and the accepted source/account normalizers.
It adds no alternative strategy, account book or execution framework.

- Original shared lock identity, exact account fingerprint, immutable scope and
  caller-supplied physical-owner verification precede dispatch. Real credential
  loading and physical runner selection are deliberately still unbound.
- ENTRY requires exact scope-bound GO, validity, fresh authenticated account and
  instrument/quote evidence, explicit symbol one-way mode and no foreign exposure.
  Missing flat-mode evidence is not interpreted as permission.
- Sizing preserves frozen stop/targets and 40/60 lot divisibility. It includes
  account taker fees, slippage and a constant-price/current-funding-cap stress over
  the strategy's 168-hour maximum hold. This scenario is not a bound on future
  funding caps, liquidation, gaps or actual losses.
- A durable account admission reserves **one lifecycle** before wire I/O. Exact
  dispatch tickets bind request, lifecycle, scope, source observation and entry
  sizing. A lifecycle reservation alone cannot bypass the financial gateway.
  Missing/unknown responses and nonzero Bybit ACKs require reconciliation; no
  second request is sent merely because the previous response was lost.
- Existing lifecycle handles native stop verification, actual partial quantities,
  40/60 targets, time exit and restart. Native order acknowledgement is not fill
  or protection proof. Unknown final costs keep the lifecycle reserved.
- Account risk history includes owned fills, actual fees, signed funding and
  marked exposure. Day/week boundaries retain the previous mark; drawdown retains
  the high-water mark. Durable loss/unknown-risk markers inhibit new entries;
  proven owned custody continues. No reset API is provided.

Funding follows the existing normalizer: positive funding is receipt, negative
funding is expense. Bybit transaction logs can be delayed; their temporary absence
does not prove final costs. [Official transaction-log contract](https://bybit-exchange.github.io/docs/v5/account/transaction-log).

## Acceptance and review

Evidence: [exact source manifest](evidence/pump4_owner_20261023/source-manifest.json),
[local acceptance](evidence/pump4_owner_20261023/local-acceptance.json),
[independent VPS readback](evidence/pump4_owner_20261023/vps-independent-readback.json),
[memory-cycle receipts](evidence/pump4_owner_20261023/local-memory-receipts.json),
[review disposition](evidence/pump4_owner_20261023/review.json).

Material: `45143de325ebd6e5d0b9ef70c42bff18bffd52021c2582eb7ede1a3d9e381a49`.
81 packaged files, eight targeted test modules, 28 recorded imports, zero checkout
fallback. Parent/child socket traffic is denied; VPS additionally uses an isolated
network namespace. The package contains no real account profile or GO.

Tests include full memory-wire entry → stop observation → TP1 → TP2 → flat with
costs pending; partial fills; global writer competition; wrong key/lock/GO/mode;
stale sources; cost-inclusive capacity; request loss before/after acceptance;
nonzero ACK; a new interpreter after restart; expiry/revocation with custody;
loss-latch persistence; risk-journal corruption with independently proven exit;
funding signs; day-boundary loss; high-water drawdown; dispatch-ticket bypass;
and mutation of immutable scope/configuration.

One independent critical review used **gpt-6-astra/high**, verified against actual
rollout `turn_context`, not merely requested settings. It found two defects:
replacement of the send-barrier directory could evade a prior barrier, and the
final ENTRY wire freshness check omitted older instrument evidence. Root reproduced
both as failing regressions, added immutable directory path/device/inode binding
and sizing-bound final freshness, then passed the full final suite. There was no
second reviewer pass; final fixes were verified by root and both acceptance runs.

Readback verifies all 64 protected selected NET R4 files unchanged and no PUMP4
financial unit. All 53 accepted Monthly sources also remain byte-identical.
The existing NET exit is spent; no NET command or Monthly activation was run.

Reproduction from an isolated copy matching the manifest:

```bash
unshare --net /root/by-bot/.venv/bin/python -B /opt/bybot-research/pump4-account-owner-orders-off-20261023/candidate-45143de325ebd6e5/accept.py
```

The acceptance driver creates exclusive output files. Do not rerun into the
already accepted directory; create a new isolated copy. The saved
`evidence/pump4_owner_20261023/accept.py` is the exact driver.

## Remaining actual gates

1. Bind this component to the existing physical owner verifier, original Bybit
   lock/profile and causal closed-H1 production intake in one pinned runner.
   Verify actual competing-writer state and restart under that wiring. A memory
   callback does not prove deployed physical ownership.
2. Run current-account ORDERS_OFF admission through that exact runner, including
   complete fresh sources, current lot/fees/funding and per-signal feasibility.
   The earlier 136/137 instrument coverage and HFT explicit QA exclusion remain
   visible; this component does not create the missing instrument or a signal.
3. Present the exact one-lifecycle TINY scope, current risk/cost estimates,
   recovery/alert receipt and hashes for separate owner approval. Fixture values
   allocation50/gross30/reserve20/R1/day2/week3/drawdown6 are **unapproved proposals**.
   No real PUMP4 GO, financial service or automatic continuation was issued.

Alpaca's pending NET commissions are not a dependency of these PUMP4 engineering
steps. This component proves execution controls in isolation, not strategy edge,
live fills or profitability.
