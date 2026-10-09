# October9 bounded engineering delivery

**Alpaca LOCAL_CANDIDATE_PASS; operational BLOCKED_DATA_NEXT_SESSION_PACKET.**
**CRYPTO_CORE_V2_BASELINES_READY_FOR_PREREG_INPUT; edge NOT_PROVEN.**
Receipt: [delivery.json](evidence/alpaca_dispatch_v2_20261009/delivery.json).
No VPS/service/broker/automation changes this cycle. Last broker truth remains
the dated October9 opening/postcheck; it was not refreshed for this code cycle.
LIVE HALT, caps, old reservation and original source histories are preserved.

## Delivered

`research_lab/alpaca_open_dispatch_v2.py` and
`scripts/run_alpaca_open_dispatch_v2.py` reuse DynamicBook and the existing PAPER
adapter. Static review/pins must FINISH by T−15m; READY must finish by T−1m.
The selector can be precomputed from closed data with its actual preparation
timestamp; only the unchanged draft is sealed at opening. No opening rescan,
source discovery, model review or helper construction. Read-only LIVE GETs supply
account, positions, orders, asset and raw IEX quote; IEX is not NBBO. Pending fees
and missing sources block. Source-bound CAT reserve reduces spendable cash before
planning. Fractional DAY STOP eligibility is bound to the archived reviewed
protocol; this is not broker acceptance.

Opening budgets: fresh30s, reserve5s, existing adapter preflight allowance120s.
Fresh/reserve budgets include evidence hashing/persistence. Credential-free raw
GET sources and the exact snapshot are retained in private hashed runtime files,
not merely their digests; two primary source-retention RED/GREEN checks closed. Insufficient time
blocks before consuming a slot. Phase traces survive errors; durable invocation
claim permits at most one adapter call. No second GET rehearsal before sending.
No controller timer can abort protection after an accepted entry. An ambiguous
adapter call is terminal and requires existing owned reconciliation; no resend.
Default CLI is static preparation, not a scheduler or authority issuer.

Crypto adapter `research_lab/crypto_core_v2_baselines.py` calls exactly the original
event-expansion/retest-long and support-bounce sources. Git blob parity is checked;
native strategies were not edited. Stateful event FSM progresses through its
original lifecycle; bounce consumes a frozen copy of the exact validated H1/H4
rows instead of an unrelated backing store. Effective config/allowlists and
actual observation time are pinned. Native JSON receipts are immutable/detached.
Unknown costs remain blocked; CONFIRMED requires finite nonnegative fee/slippage/
funding, resolved unknowns and a source hash. No costs are invented or inferred
from another venue. Original bounce already has its own context rule; no new
global trend veto was added.

## Evidence and limits

143 targeted tests PASS: opening controller, original planner/PAPER/maintenance,
two baseline adapters and original event/env/geometry tests. One independent
financial review found four Important defects; eight reproducing RED tests were
closed in one fix pass. Settings verified from runtime turn_context:
gpt-5.6-luna/medium worker, gpt-6-astra/high review. No measured saving claimed.

[Final rehearsal](evidence/alpaca_dispatch_v2_20261009/rehearsal_final.json):30 exact local
fresh-publisher→planner→adapter→full native stop→idempotent read paths. Source GET
delays0/.5/2.5s are simulated, adapter broker is synthetic. Maximum simulated
completion13.5s after opening; measured local wall median16.35ms/max77.36ms.
This does not measure real network latency or prove actual PAPER lifecycle.
Reproduce with `.venv/bin/python scripts/rehearse_alpaca_open_dispatch_v2.py
--output <new-evidence-path>`; never overwrite sealed evidence.

The worker unnecessarily ran the full suite: reported4110PASS/58FAIL. Its output
was not preserved and no same-HEAD comparison was made. Full suite is NOT_GREEN;
the claim that all58failures were preexisting is NOT_PROVEN. The scoped143-test
result above was freshly run and inspected by the primary agent.
That full-suite run appended four local allowlist audit entries. The exact
pre-cycle four-entry byte content was recovered only after its SHA256 matched
the original add587f1…f19a1 pin; our append was removed, original foreign diff
remains unstaged. [Restoration receipt](evidence/alpaca_dispatch_v2_20261009/test_side_effect_restore.json).

## Concrete next gates

1. Close the Oct9 non-dispatch reservation with a reviewed, provenance-retaining
   prospective handoff. Do not delete it, fabricate a fill/child, retry/reprice
   its plan or substitute an empty book. The controller currently blocks it.
2. Before the next attempted opening, finish the actual source packet: existing
   owner/writer/shared-lock/PAPER-account/XOM exclusion, terminal slots, earnings,
   concentration, protocol and exact next-session ranking. For weekly Monday
   refresh, use preceding-session closed data and real availability/preparation
   times. The Oct7/9 XOM result is not automatically Monday's candidate.
3. Actual attempt must be explicitly PAPER-only and session-scoped. Install/arm
   only a complete reviewed packet. By16:15Cyprus static preparation is closed;
   by16:29 READY is closed; at16:30 only fixed source checks/planner/adapter run.
   An unmet pre-open gate ends the attempt BEFORE opening. No job is armed now.
4. One actual protected PAPER lifecycle/recovery/finality and true later DAY
   re-arm precede exact LIVE dossier and separate owner GO. No extra statistical
   PAPER days, LIVE HALTclear or resurrection of CRWD/META.
5. Claude receives exactly two original engineering baselines. Consumed historical
   dates and untouched validation periods remain UNKNOWN in
   [validation_inventory.json](evidence/crypto_core_v2_baselines_20261009/validation_inventory.json).
   Source/cost/prereg independence must close before any judge/outcome run.
   One outcome-consuming research slot; KEEP/KILL, not an automatic recovery.

No ATT1 revival, current KITY rescue, new strategy family, B3 rerun, Claude edits/
messages, UI, AI authority or broad architecture work. ETS original schedule is
unchanged. These are engineering gates, not a promised income date.
