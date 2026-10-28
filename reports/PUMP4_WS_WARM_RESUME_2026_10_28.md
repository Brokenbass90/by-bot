# PUMP4: resident WS/warm continuation — 28 October 2026

Engineering COMPONENT PASS; operational source selection and actual full137 H1
remain PENDING at this commit. TINY_READY=false, economics INCONCLUSIVE.
Monthly v6 and all financial limits/authorities unchanged. No monetary GO.

## Implementation and verified fixes

Resumed the interrupted working tree rather than recreating the pipeline.
The resident warm reducer uses the original frozen producer and original journal
hash chain/lock/fsync. It advances memory only after durable append, reuses verified
state across H1, and rebuilds on drift/recovery. Raw WS frames and original clocks
are sealed before parsing. Both server and receipt time of the next-open row must
follow the H1 boundary. Wall/monotonic continuity is checked after raw capture and
journal publication; late decisions remain DATA_ONLY. An exclusive setup attempt
is durable before the first metadata request; interruption cannot retry that H1.

Independent critical review (actual gpt-6-astra/high metadata verified) found three
Important issues: unnecessary per-H1 cold rebuild, first metadata failure before
claim, and pre-boundary next-open acceptance. All three received RED regressions,
fixes and focused re-review: no remaining Critical/Important. Final focused suites:
36 targeted PASS; independent run including source parser: 46 PASS.

## Exact package acceptance

Material SHA256: `7d8ae05dab162ec5eaded17a7ed779c14d092880553dcd96345cf3d3198e6cf0`.
Manifest SHA256: `ea65a0c785606dcbecdebd93cab3071c45f519263b8f5195b37fdcede16f28d0`.
129 files / 25 test modules / 66 imports. Local 406 PASS; identical staged VPS
package 406 PASS with network denied, no checkout fallback, errors, failures or
skips. 178 fixture receipts. VPS run used nice15/idle I/O; no priority promotion.
Zero real broker requests/writes. See `evidence/pump4_ws_resume_20261028/`.

Two preceding package attempts exposed missing fixture JSON and a dynamically
imported probe script. Both dependencies were included; no test was removed.
The final exact package above passed. It remains inert until the reviewed OFF
operational handoff. Existing positive-signal financial consumer keeps its
independent fresh HTTPS causal-plan check; WS is not direct order authority.

## DATA continuity

Missing Monthly58 sessions 26/27 October and LIQ snapshot 28 October were delivered
with original seals, actual import time and previous hashes/inodes/mtimes intact.
Monthly58: 8 seals, strictly 57+SPY/core200complete. LIQ: 12 seals / 70,007 raw
cumulative events /25 symbols, same epoch; coverage UNKNOWN, no prospective credit.
No collector restart, research/judge edits, or broker mutations.

## Next gate

1. Reuse existing OFF handoff with fresh flat-account/one-writer proof; preserve
   original Bybit lock818853, financial policy, all history and protected Monthly.
2. Select resident source at normal resource priority; verify preload/subscription
   before H1 and complete actual full137 receipt against <=60s publication gate.
3. Only after actual source proof: current account/sizing/native protection and
   exact owner TINY packet. Do not call engineering tests TINY or economic PASS.
