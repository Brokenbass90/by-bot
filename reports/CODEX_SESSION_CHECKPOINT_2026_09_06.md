# Codex session checkpoint — 2026-09-06

## Public continuation checkpoint

Latest continuation: September 9, after OLD watchdog restarts at 16:02 and
17:02 UTC. Immediate blocker: recurring VPS lifecycle discontinuity; public v2
also has two dirty RECOVERY_GAP sessions, no clean prospective final net-R.
Read `reports/ATT1_HANDOFF_AND_WATCHDOG_2026_09_09.md` first.
Durable handoff preparation: 192 focused tests PASS, including 25 SQLite
reservation tests also PASS on target Python 3.12.3. These functions are NOT
connected to production dispatch/send/recovery. Next implementation work:
authenticated production OLD→NEW dispatch/send/reconciliation in the monolith.
READY FOR OWNER ACTIVATION = FALSE; no valid owner activation command yet.

The external watchdog restarted OLD for heartbeat ages 96s and 145s; the VPS
did not reboot. Second OLD PID 1206069, start 17:02:15 UTC; heartbeat recovered
to ~10s at 17:03. After-second-restart signed GET at 17:05:40 UTC: flat, no orders,
complete pagination, unchanged PID, heartbeat age 9.1s. Existing sar proves CPU/swap pressure (16:00–16:10 CPU idle
0.34%); the exact stalling call remains NOT_CONFIRMED. v2 CRV/DOGE gap journals
must stay dirty; poll_errors={} does not imply clean lifecycle continuity.
No OLD money/settings, public service or watchdog changes were made in this cycle.
Fully bound OLD absolute risk still requires runtime capital/equity inputs
absent from heartbeat; do not infer exact risk from wallet/config alone.

Prior completed continuation: Public v2 DEPLOYED + RESTART PASS;
read-only broker replay implemented.

Then read `reports/ATT1_PUBLIC_V2_AND_BROKER_REPLAY_2026_09_09.md`.
Service source `8e3b122c926cb0e5f0227ad26f4d40c53b5ce94d`; new separate unit
`att1-lifecycle-zero-risk-v2.service`, runtime under its own `runtime/v2`.
Original v1, OLD micro-live and L1 were preserved. 167 tests, target Python,
23 nonzero fixture restart boundaries and actual empty-state service restart PASS.
No clean prospective filled v2 lifecycle is claimed by the restart receipt.

Canonical branch: `codex/recovery-20260824`. Only ATT1 P0 is active.
Private broker snapshots and account economics remain on local branch
`local/private-evidence-20260908` and its verified local Git bundle. They are
not included in this public history. Original deployed commit identities are
retained as evidence; public export does not redeploy any runtime.

Read `reports/ATT1_PUBLIC_LIFECYCLE_2026_09_08.md`. The separate public-only
service passed target Python smoke and exact durable restart verification.
L1 final operational burn-in passed. These do not prove broker parity or edge.

Read `reports/ATT1_MICRO_CANARY_RECONCILIATION_2026_09_08.md` and
`docs/superpowers/plans/2026-09-08-att1-profile-migration.md`. NEW is canonical
for the next canary: trendline+6.6ATR, BE/trailing OFF, 336h, frozen profile
`79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050`.
OLD has different signal/stop/target/management behavior and stays untouched.

Prospective public ADA evidence is dirty: RECOVERY_GAP, flat simulated exposure,
no clean final net-R. The captured 266-row journal restores identically with
the incident. Preserve it; do not relax the 2s gate or rewrite public v1.

Next bounded P0: connect the tested SQLite handoff/reservation functions to the
existing bybot dispatch/send/recovery, with authenticated broker finality and
runtime risk/daily cost binding. Do not build another ledger or replay core.
Read-only mappers
and exact funding cash replay are implemented but not connected to money.
Follow v2 prospective continuity; preserve all dirty v1 evidence. No financial
activation before actual PASS receipts. Owner operates the money transition.
No fallback to OLD and no simultaneous OLD/NEW money entry.

Other strategies stay in the queue: ETS2S profile/timing binding is pending;
Alpaca lineage belongs to Claude. No competing work is launched. Historical
research/strategy queues remain in the original local archive and existing
research reports; none becomes an automatic money promotion.

LAB_AI_V0 remains a read-only research-assistant design, not a running AI worker
verified by this checkpoint. The existing laboratory replay, journals, fixtures
and accounting support ATT1 now. After ATT1 gates: deterministic evidence
catalog, quality classification, source-cited lifecycle/net-R explanations,
then bounded historical entry/protection/exit comparisons through the same
evidence pipeline. No new strategy, architecture, Alpaca or LAB implementation
competes with current ATT1 P0.
