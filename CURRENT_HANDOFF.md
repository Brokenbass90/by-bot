# Current handoff — 2026-08-29

Canonical tree: `bybit-bot-recovery-20260824`.
Canonical branch: `codex/recovery-20260824`.

Read first:

1. `reports/CODEX_SESSION_CHECKPOINT_2026_08_29.md`;
2. `reports/CURRENT_PROJECT_ROADMAP.md`;
3. older dated reports only as history.

## Current gate

The owner-authorized ATT1/SBR1 reserved diagnostic was run exactly once and is
consumed. It terminated `FAIL_CLOSED_AFTER_CLAIM` on an `AttributeError` in the
runner summarizer after all scorer artifacts had been written. It must not be
retried under the consumed authorization.

Independent failure-forensic reconstruction validates exact inputs, outputs,
research/live parity, normalized comparator parity and zero live/private/order
impact. The formal attempt remains failed. Offline pre-frozen decisions are:

- ATT1: `FAIL_CLOSED`; stress second half `-0.337197R` despite total
  `+19.502091R`;
- SBR1: `INCONCLUSIVE_LOW_N`; `N=16`, stress `-3.688072R`, PF `0.6080`;
- money authority, promotion authority and live risk changes: zero.

Final independent review is `Spec PASS` / `Code-quality PASS`; the dedicated
failure-forensic suite is `26 passed`. The post-authorization regression suite
is `64 passed, 2 deselected`; the two omitted tests require authorization to be
absent and are intentionally inapplicable after the consumed run.

Read `reports/ATT1_SBR1_RESERVED_OOS_RESULT_2026_08_29.md` for the complete
publication and exact hashes.

## Next action

Do not spend a new authorization on a mechanical rerun: the immutable forensic
economics already rejects promotion. Preserve v1 byte-for-byte. Move research
to a preregistered bull-continuation candidate and XSEC PIT rebuild; separately
analyze ATT1 temporal degradation without tuning against the consumed window.
Any future formal v2 needs a new output path, claim, config and explicit owner
authorization.

Alpaca remains a separate SAFE_HOLD track. Historical replay can compress most
selector, gap, restart, partial-fill and stop-ratchet checks, but cannot replace
a short prospective broker paper lifecycle under the real bridge.
