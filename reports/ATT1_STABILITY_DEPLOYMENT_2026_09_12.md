# ATT1 stability deployment — September 12

The Telegram entry notification still belongs to **OLD ATT1**. NEW has no
production broker-send path and remains public-only. `RISK CUT` is an OLD
control message, not evidence of NEW activation or proof of halved absolute R.
`READY FOR OWNER ACTIVATION = FALSE`.

## Deployed repair

Source commit: `79be191ba4ef8238df7a4b0e2b61ec75da3d9a03`.

Read-only, nonblocking Python stack sampling found the OLD main thread inside
the synchronous Telegram `getUpdates` call in 8 of 12 samples. Its 20-second
long poll shares the event loop with pulse and management. This establishes a
blocking component; it does not attribute every historical 90-second stall to
that call alone. The profiler was installed separately under `/tmp`, without
changing the bot's dependencies. See the [py-spy documentation](https://github.com/benfred/py-spy).

The OLD deployment changes exactly one call to `await asyncio.to_thread(...)`.
URL, polling parameters, update offsets, access filters and command handlers
remain unchanged. Handlers stay on the main event loop. Trading entry, sizing,
protection and exit source is byte-for-byte unchanged.

- OLD original source SHA: `8e8ccea73fa94d1d4d262b0d3d1415159637b3a463a81c8b132a15bb1ff9585d`.
- Patched source SHA: `aeda59e299fac9833c68816088997e927d82b8392137072521ecb76e081b2128`.
- Fresh signed GET proved flat/no orders before the controlled restart.
- OLD PID `3563637 → 3650522`; after-restart signed GET at
  **2026-09-12 08:28:28 UTC** again proved flat/no orders, complete pagination,
  unchanged PID during collection and heartbeat age **3.2 seconds**.
- Persistent money-control file hashes and visible heartbeat risk settings
  matched before/after. This does not newly prove the unobserved runtime
  capital override or exact absolute OLD risk required for canary binding.
- Rollback source and control hashes remain under
  `/root/by-bot/runtime/deploy-backups/att1-stability-20260912/`.

Post-fix observation over **44.17s / 23 samples**: OLD heartbeat age
**0.81–10.86s**, unchanged PID, active service; none of three main-thread stack
samples was in Telegram polling. Public v2 used **1.14% of one CPU** over that
same interval; retired v1 was inactive. This short window verifies immediate
liveness, not passage of the next hourly load peak.

## Public lifecycle repair

Every heartbeat previously reopened and replayed the full journal history.
The driver now caches verified state against journal path/device/inode/size/
mtime/ctime. Changes require full replay; before/after file signatures must
match. Cache returns are copies. Explicit verification and startup recovery
still replay, and the 2-second continuity gate remains unchanged.

The existing `att1-lifecycle-zero-risk-v2.service` was updated September 10,
with epoch `att1-public-lifecycle-20260910-stability` under
`/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260910-stability`.
Release closure:
`74471903331c3c85982ce76b35276a39b0bed3893656cf2b160f68f1ece0ee79`.

The redundant old public v1 service is stopped and disabled. Original v1 and
v2 runtime directories remain intact; their 6 and 4 journal/epoch file hashes
matched across replacement. Retired app, manifest and journal hashes remain
under the existing v2 service directory. OLD money was untouched by this public
deployment; one public-only comparator remains running.

The September 12 observation has six public sessions: five `RECOVERY_GAP`, one
flat with no incident; all have null final net-R. This is not a clean completed
filled cohort. Old incidents were not erased or reclassified by the repair.

## Evidence and next gate

200 focused local tests PASS. Target Python 3.12.3: 14 targeted liveness/runtime
tests PASS and the existing end-to-end verifier PASS. The old Telegram code
fails the same heartbeat regression. Three additional full-monolith startup
tests could not import locally because the research venv lacks `requests`;
they are not claimed as passing. No bot dependency installation was performed.

Private signed snapshots, staging/deployment scripts and raw stack samples are
under ignored `.private/att1_handoff_20260909/`. Public Git excludes them.

The obsolete final-burn-in automation was deleted: the L1 final verdict is
already `PASS_OPERATIONAL_BURN_IN`; no repeated evaluator is necessary.

Next: observe the next hourly boundary after the OLD patch, then continue the
existing production OLD→NEW dispatch/send/recovery binding using the already
tested reservation functions. Do not build another ledger, strategy or core.
Exact runtime risk, authenticated finality/protection/cost binding and clean
prospective evidence remain activation gates. No money activation is authorized
by this stability receipt.
