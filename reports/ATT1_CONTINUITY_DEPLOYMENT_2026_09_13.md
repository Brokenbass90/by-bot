# ATT1 public continuity deployment — September 13, 2026

## Result and scope

**PUBLIC CONTINUITY DEPLOYED; six consecutive 51/51 scans; observed rejected
book handled without process exit. READY FOR OWNER ACTIVATION = FALSE.**

This supersedes the pre-deployment status in `ATT1_PUBLIC_PROGRESS_2026_09_13.md`.
Machine-readable public evidence: `ATT1_CONTINUITY_RECEIPT_2026_09_13.json`.
Private broker/economic snapshots remain ignored and are not published.
Public simulation is not broker execution parity or evidence of positive edge.

## Deployment receipt

| Field | Value |
|---|---|
| Deployment UTC | 2026-09-13 07:52:12.581 |
| Existing service | `att1-lifecycle-zero-risk-v2.service` |
| Source commit | `f38badcaa4b87d5f2aa9ffc285766fbbda13e116` |
| Closure SHA256 | `ea78a3bb5970292601145167f3780750074be8c7ecd9cdbb09095aa8359c633f` |
| Archive SHA256 | `e9e10d0abc7ad73cce26046d42073f80f27681ae191509de3bab2d99fae64c4a` |
| Epoch | `att1-public-lifecycle-20260913-continuity` |
| Runtime | `/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260913-continuity` |
| PID / start UTC | `451398` / 07:52:11 |
| Authority | money, orders, private API and promotion all false |
| Packaging | 32 files, clean source tree; no monolith or money adapter |

Only the public release and its epoch changed. OLD PID, source, configuration
and risk-control file hashes were unchanged across deployment. Subsequent OLD
watchdog restarts are separate events. The unit and resource limits stayed
unchanged. Previous epoch journals/epoch hashes were preserved after stopping;
rollback material is `retired-app-v2-20260913`,
`retired-manifest-v2-20260913.json`, and `retired-epoch-20260913.json` under
the same service root. Do not rewrite dirty evidence. L1 final operational
burn-in PASS remains historical truth; no new evaluator or burn-in reset.

## Verified runtime changes

The exact future/2-second public-book gate remains enforced. Rejected held-
position quotes now preserve a sourced RECOVERY_GAP and exposure without
terminating the process. The next acceptable quote uses the existing incident
exit. Invalid entry quotes produce a sourced simulated nonfill; malformed
invariants remain fatal. No untrusted quote creates a simulated fill.

The existing H1 scan runs in one bounded worker while the main loop alone
owns admission, lifecycle mutations and journals. Reusing validated causal
prefixes removes repeated history validation without changing the same 48
decisions. Public HTTP concurrency is capped at two, request starts at eight
per second. Deterministic identities still bind epoch, symbol and H1 close.

Validation: 193 focused public tests passed; the subsequent platform-errno
portability fix passed 18 cache tests. Target Python 3.12.3 passed 55 tests,
preflight and the end-to-end verifier, including 23 durable restart boundaries.
Ten recorded public fixtures produced **480/480 identical causal decisions**,
matching recorded signals. Fixture tests also check candle cutoffs, absence of
future leakage, deterministic journal/restart dedupe and API limits. On the
VPS, the ten-case replay took 33.491s before and 2.385s after; this is a bounded
replay benchmark, not a whole-service or financial performance estimate.

Observation at 13:32 UTC: heartbeat age **0.64s**, status RUNNING, same PID,
NRestarts=0 and no service journal entries after startup. These observations
cover the measured interval, not a guarantee against future failures.

| H1 close UTC | Unique symbols attempted | Completion after close |
|---|---:|---:|
| 08:00 | 51/51 | 107.484s |
| 09:00 | 51/51 | 105.052s |
| 10:00 | 51/51 | 102.882s |
| 11:00 | 51/51 | 153.339s |
| 12:00 | 51/51 | 105.985s |
| 13:00 | 51/51 | 117.678s |

HFTUSDT consistently returns STALE_CLOSED_BAR; full attempted coverage does
not mean 51 fresh tradable feeds. The other 50 had a fresh evaluated result.

The first prospective ALGOUSDT simulation filled and acknowledged protection.
At approximately 11:07:28 UTC a rejected future/stale book recorded
RECOVERY_GAP. Subsequent acceptable data flattened the simulation, including
partial exit handling, in the same process. Scenario costs completed, but
final net-R remains null and lifecycle_terminal=false. This is actual public
evidence of no process exit on a rejected book; it is **not a clean lifecycle**.
There are currently **zero** clean filled lifecycles with terminal net-R.

## Default-off OLD dispatch preparation, separately committed

Local commit `d5c1242` connects the existing durable reservation ledger to an
opt-in OLD pre-send path, stable orderLinkId and startup recovery of unknown
dispatch ACKs using the existing broker GET. The default flag remains false;
the normal disabled path does not load the adapter or create its database.
75 focused tests and compile checks passed. Critical review permits retaining
this default-off preparation; it does not approve money activation.

This code was **not deployed** with the public runtime. It is not yet a full
NEW production binding. Remaining exact blockers are authenticated broker
account identity (the current config fingerprint is insufficient), pre-binding
OLD position/order reconciliation, NEW dispatch and lifecycle management,
and actual fills/protection/fees/funding/finality reconciliation. A recovered
ACK alone neither proves a fill nor releases a reservation. Keep unknown sends
occupied; do not claim the production OLD→NEW exclusive handoff is ready.

Fresh exact OLD absolute risk remains unconfirmed until runtime capital and
effective sizing inputs are bound to authenticated broker truth. A wallet
balance or x0.10 multiplier alone cannot establish exact absolute risk.

## OLD watchdog and next bounded continuation

OLD watchdog restarted its process at 11:12:06 UTC following the reported
128-second heartbeat age. The host did not reboot and public PID stayed
unchanged. The September 12 Telegram wait repair did not eliminate every
stall. The remaining blocking call is NOT_CONFIRMED; no general audit is needed.

A separate bounded read-only diagnostic process is armed at
`/root/by-bot/runtime/att1-stall-capture-20260913`. It captures timed nonblocking
py-spy stacks after heartbeat age reaches 30s, with no locals, no money calls,
at most 24 dumps and a 12-hour deadline. Retrieve `capture.jsonl` privately.
Attribute a cause only from stale-episode timestamps and MainThread frames.
An idle stack is not stall attribution. A thread heartbeat checks progress
every two hours for at most 12 runs, remaining quiet when nothing actionable
changes. This adds no trading service and changes no OLD risk or watchdog rule.

Next gate: two or three incident-free prospective filled lifecycles with
terminal=true, costs_complete=true and non-null net-R. This is an operational
gate, not statistical evidence of positive economics. Continue the existing
default-off broker binding work; after clean evidence and binding verification,
collect fresh exact OLD risk truth and finish the micro-canary dossier. NEW
money still requires explicit owner approval. No valid activation command yet.

Planning estimates, not deadlines: completing and verifying the remaining
broker integration is roughly 2–4 focused working days if no new critical
defect appears. Market evidence runs in parallel and has no guaranteed date:
several days or longer, with a frozen 336-hour maximum time exit per position.
Fresh risk truth/dossier should take one focused cycle once both gates pass.
No profitability date can be inferred from these engineering milestones.
