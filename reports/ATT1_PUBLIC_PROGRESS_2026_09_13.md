# ATT1 accumulated public evidence — September 13, Cyprus

Snapshot: September 12, 23:37–23:41 UTC (September 13 in Cyprus).
This is a read-only continuation. No source deployment, service restart,
money authority, position, sizing or strategy changes were made in this cycle.

## Answer about the ETH entry

The reported ETH short fill at 2468.51 belongs to OLD ATT1. NEW's coordinator
is still not connected to production broker sends. The current monolith hash
is the September 12 Telegram repair release:
`aeda59e299fac9833c68816088997e927d82b8392137072521ecb76e081b2128`.
The message's risk-cut multiplier is not proof of the effective absolute risk;
retain the existing runtime capital/equity and minimum-quantity caveats.

Signed broker GET at 23:37:39 UTC: account main, zero nonzero linear-USDT
positions and zero open linear-USDT orders; pagination complete and PID stable.
Raw account data stays in ignored `.private/att1_handoff_20260909/`.

## What accumulated

L1 covers September 5 08:00 through September 12 23:00 UTC:

| Existing signal stream | Forward decision rows | Rows with a signal |
|---|---:|---:|
| ATT1 | 9,200 | 42 |
| ETS2S | 9,200 | 325 |

Another 102 rows are initial backfill, with no signals. Total 18,502 rows;
zero duplicate claim keys and zero exception fields in this inventory.
These are signal decisions, not orders, independent completed trades or net edge.
The final L1 operational burn-in verdict remains the already completed PASS;
this inventory does not rerun or replace it.

| Public lifecycle epoch | Sessions | Sessions with simulated entry fills | Nonfill | Filled sessions with RECOVERY_GAP | Clean final net-R |
|---|---:|---:|---:|---:|---:|
| Retired v1 | 4 | 3 | 1 | 3 | 0 |
| Retired v2 | 2 | 2 | 0 | 2 | 0 |
| Current 20260910-stability | 6 | 5 | 1 | 5 | 0 |
| Total session counts | 12 | 10 | 2 | 10 | 0 |

All 12 session journal hash chains and all three scan journal hash chains
verified read-only. All ten filled sessions have simulated exit fills and
zero remaining exposure, but incident contamination prevents clean final net-R.
Do not treat the totals as a statistically independent cohort or actual fills.
The current CRV session is a cancelled IOC with no entry fill, not an unfinished
profitable trade. No clean economic result can be inferred from a null net-R.

The current epoch has 2,114 scan records across 66 hourly slots. The latest
16 slots scanned only 29–34 symbols each out of the fixed 51, due to the
five-minute scan window expiring before the sequential scan finishes. This
is incomplete, order-dependent universe coverage, not proof of no signals in
the unvisited symbols. Exact counters and public journal hashes are in
`research_lab/results/att1_public_progress_20260913/public_evidence_summary.json`.

## Continuity findings

OLD PID 3650522 has remained running since September 12 08:28:20 UTC, including
15 subsequent hourly boundaries. Snapshot heartbeat age was 7.64 seconds.
The watchdog restart state still points to September 9 23:02:02 UTC; its recent
tail reports healthy heartbeats. This confirms no subsequent OLD process
restart through the snapshot, not continuous subsecond event-loop health.

Public PID 3563703 has remained running since September 12 06:22:39 UTC.
Public v1 remains inactive; the existing L1 timer and public v2 remain active.
The current public heartbeat still explicitly denies all money/private/order
authority. There have been no new session admissions since September 11 10:00 UTC,
so uptime after the OLD repair has not validated a fresh filled lifecycle.

The public systemd log identifies both September 11 in-position crashes:
`future/stale public book` caused exit status 2 and a 20-second restart delay.
HBAR and AAVE then recorded `restart lost public observation continuity`.
INJ, ICP and BNB recorded ordinary `public polling continuity gap` instead.
Thus the prior replay-cache fix did not establish prospective continuity.
Old evidence remains dirty and unchanged; the 2-second gate is not relaxed.

## Binding next gate

**READY FOR OWNER ACTIVATION = FALSE.** The immediate blocker is an unreliable
public observation lifecycle: every observed filled session was contaminated
before reaching a clean economic endpoint. Waiting alone is not a solution.

Next bounded implementation: reproduce stale-book handling and loop timing in
the existing runner, retain durable fail-closed incident/exposure truth while
avoiding an unnecessary process-restart delay, and validate realistic public
response latency on target Python. Any public deployment must preserve the
old epoch, retain the strict continuity gate and obtain prospective evidence;
fixtures or stable uptime cannot substitute for that evidence. Address the
measured scan coverage in the existing scan path without changing strategy rules.
After this gate, continue the already specified production dispatch/broker
binding; do not create another coordinator, ledger or research direction.
