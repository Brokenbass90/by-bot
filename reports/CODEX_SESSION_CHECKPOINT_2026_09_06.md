# Codex session checkpoint — 2026-09-06

## Public continuation checkpoint

Latest continuation — **September 14, 06:51–06:55 UTC**:
- Completed the next default-off binding increment: selected signed identity
  before/after complete USDT-linear positions and open-order pagination, strict
  freshness/schema/duplicate checks, and flat snapshot required before existing
  OLD durable reservation. HTTP runs in a worker thread. Snapshot flatness
  never releases an unresolved reservation and cannot establish trade finality.
- Existing Bybit client only; no new coordinator/ledger. Collection is sequential,
  bounded to 16 pages per endpoint and rejects results beyond a 50s collection
  budget (an in-flight signed GET retains its existing timeout/retry bound).
- **128 focused binding tests PASS**, **11 Mac supervisor tests PASS**;
  **102 tests PASS on VPS Python 3.12** in isolated `/tmp`. A fresh signed
  GET-only probe using the reviewed AST helpers PASS; exact account data stays
  ignored/private. Tested adapter/monolith hashes match local files. This is
  not a production startup or NEW execution parity verdict.
- Money binding and OLD fairness fix remain **NOT DEPLOYED**. OLD PID and
  deployed source unchanged during the signed check. Public PID 451398,
  NRestarts=0, heartbeat age 565ms, 51/51 scan attempts (one stale HFT feed).
- Public epoch now has 10 sessions, **0 clean terminal net-R**. Journal evidence
  identifies 5 `public polling continuity gap` incidents and 2 rejected stale
  books aged 2113/2274ms. No future clock incident in these seven. These are
  real evidence failures, not process exits. Do not wait indefinitely for clean
  outcomes or relax the 2s gate; localize the existing observation loop delays.
- Native `com.tradingstation.att1-research` completed all four updated stages
  at **06:53:09 UTC**, exit 0, caffeinate gone. Added the new reconciliation
  fixture to its fixed allowlist. Prior completed output preserved in
  `runtime/mac_att1_research_job-20260913-complete`. No other jobs stopped.
- Mechanical snapshot tests used actual `gpt-5.6-luna / medium`, verified in
  runtime thread metadata and rollout turn_context. Root reviewed/integrated.
- Receipt: `reports/ATT1_RECONCILIATION_RECEIPT_2026_09_14.json`.

**READY FOR OWNER ACTIVATION = FALSE.** Next bounded P0: finish existing NEW
production dispatch → fills/protection → actual fees/funding/finality, and
resolve measured public observation gaps without a new subsystem. Then clean
2–3 terminal public lifecycles + fresh exact effective OLD absolute risk →
micro-canary dossier. No owner approval inferred from successful tests.

Earlier continuation (superseded where noted):

Latest continuation — September 13, after local application failures:
- Commits `c431231` (local buffered WebSocket fairness fix) and `fc531fa`
  (default-off broker UID identity + Mac supervisor) are implemented. Neither
  money binding nor the OLD fairness change has been deployed to production.
- Account UID replaces config alias/key identity on enabled reservation/recovery;
  signed selected-client GET, freshness and credential binding are required.
  Legacy cfg rows block silent route creation. 81 focused local tests PASS;
  isolated VPS Python identity smoke 22 PASS. NEW full broker lifecycle remains
  unfinished; READY FOR OWNER ACTIVATION = FALSE.
- Restored two missing committed scripts. Homebrew Python was missing; the
  separate ignored `.venv-att1-mac` uses available bundled Python 3.12 and local
  test dependencies. Do not silently redirect old Gold/research environments.
- Native LaunchAgent `com.tradingstation.att1-research` is installed. Four fixed
  offline ATT1 stages actually completed at 19:34:51 UTC; receipt:
  `reports/ATT1_MAC_JOB_RECEIPT_2026_09_13.json`. OS network access and credential
  file contents are denied; 11 supervisor tests verify crash/resume, inherited
  lock, retries, heartbeat and caffeinate cleanup. Wake checks every 15m;
  completed unchanged work is a no-op. Requires user login after reboot;
  physical reboot was not tested. Changed source requires a reviewed new run.
- First launch failure is preserved at
  `runtime/mac_att1_research_job-first-launch-failure`; current result/status/logs
  are in `runtime/mac_att1_research_job`. Do not delete either as cleanup.
- Read-only VPS check around 19:32 UTC: public PID 451398, NRestarts=0,
  heartbeat 0.35s, 51 symbols. Four sessions: ALGO/TRX have RECOVERY_GAP;
  1000RATS/STRK have no incident yet but are not terminal. Clean terminal count=0.
- Timed OLD stacks were collected (not an idle sample): heartbeat ages 31–73s,
  mostly buffered trade processing; three synchronous `get_sell_pressure`
  network waits. Fairness regression reproduced starvation and preserves
  message order with one explicit yield. Do not claim OLD incident resolved
  before separate deployment/observation. Capture finished its bounded run.
- No research processes were stopped: prior inventory found no proven obsolete
  output. After local failures only targeted fresh process check confirmed a
  `local_research_station.py` process; old Gold/Alpaca broker state is not fresh.

Next bounded work: existing broker reconciliation → NEW dispatch/protection/
actual fees/funding/finality, alongside clean public lifecycle collection.
Use Mac for the existing approved ATT1 jobs; no new framework or strategy.
Owner defers server purchase until first revenue. No NEW money without approval.

Earlier deployment receipt below remains valid where not superseded:

Current continuation: **September 13, 13:32 UTC; ATT1 P0 only**. Read
`reports/ATT1_CONTINUITY_DEPLOYMENT_2026_09_13.md` first; its accompanying
`reports/ATT1_CONTINUITY_RECEIPT_2026_09_13.json` contains public evidence.

**PUBLIC CONTINUITY DEPLOYED** at 07:52 UTC, source
`f38badcaa4b87d5f2aa9ffc285766fbbda13e116`, closure
`ea78a3bb5970292601145167f3780750074be8c7ecd9cdbb09095aa8359c633f`.
Existing v2 service, new epoch `att1-public-lifecycle-20260913-continuity`,
runtime `/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260913-continuity`.
PID 451398 unchanged, NRestarts=0, heartbeat age 0.64s at observation.
Six consecutive H1 closes (08:00–13:00 UTC) completed **51/51 attempts**;
HFTUSDT is explicitly stale, so this is not 51 fresh feeds. Actual ALGO public
simulation rejected a future/stale book around 11:07 UTC, retained RECOVERY_GAP,
then flattened on acceptable data without process exit/restart. Costs complete,
net-R null. **Clean filled terminal net-R count = 0**; preserve this dirty session.
193 local focused public tests, subsequent 18 cache checks, 55 target Python
3.12.3 tests and end-to-end verifier PASS; 480 recorded public decisions exact
parity. The 2s gate, profile, deterministic journal identities and strategy rules
remain unchanged. Prior epochs and L1 burn-in PASS remain preserved.

Local **default-off preparation** is committed as `d5c1242`, 75 tests PASS:
existing OLD durable reservation/send hook, stable orderLinkId and unknown ACK
recovery. **Not deployed**, no money adapter in the public release. Full NEW
production dispatch/management and authenticated account/fill/protection/cost
finality remain unfinished. A config fingerprint is not broker account proof.
READY FOR OWNER ACTIVATION = FALSE; no activation command. OLD absolute risk
still needs authenticated fresh truth plus actual runtime capital/sizing inputs.
Do not change OLD positions/risk or enable NEW money.

OLD watchdog restarted OLD at 11:12:06 UTC after 128s heartbeat age; host did not
reboot and public PID stayed unchanged. Remaining blocking call NOT_CONFIRMED.
A bounded read-only timed-stack capture is armed in
`/root/by-bot/runtime/att1-stall-capture-20260913` (30s trigger, <=24 nonblocking
py-spy dumps, <=12h). Read capture.jsonl privately; no idle-stack attribution.
Automation `att1-continuity-and-canary-gate` checks this thread every 2h for
12 runs, quiet unless actionable. Do not create duplicate monitors or audits.

Next: finish the existing default-off production binding, inspect next timed
OLD stall if captured, and observe **2–3 clean filled prospective terminal net-R**
lifecycles. Once evidence and binding gates pass, fresh exact OLD risk truth →
micro-canary dossier → separate owner approval. These are operational gates,
not proof of positive edge. No new architecture, strategy, Alpaca, LAB or replay.

The following snapshots are historical and superseded where they conflict:

Prior September 12 deployment record: read
`reports/ATT1_STABILITY_DEPLOYMENT_2026_09_12.md` first.
Source `79be191ba4ef8238df7a4b0e2b61ec75da3d9a03`: OLD Telegram long polling
fix is DEPLOYED (only HTTP wait moved off the main event loop). Controlled
restart PID 3563637 → 3650522; signed GET at 08:28:28 UTC flat/no orders,
heartbeat age 3.2s, control hashes and visible risk settings unchanged.
44.17s post-fix sample: heartbeat age 0.81–10.86s, PID stable; public v2 CPU 1.14%.
Do not yet claim the entire hourly incident resolved; observe an hourly boundary.

Public replay-cache fix is DEPLOYED in the existing v2 service, new epoch
`att1-public-lifecycle-20260910-stability`, runtime `runtime/20260910-stability`.
Redundant public v1 is stopped/disabled; previous v1/v2 journals are preserved.
200 local tests, 14 target Python tests and end-to-end target verifier PASS.
NEW is still public-only. The reported ETH money entry used OLD.
READY FOR OWNER ACTIVATION = FALSE; production dispatch/broker binding remains
unimplemented and clean prospective filled evidence is absent. Continue the
existing reservation integration after runtime verification; no new core/lab.
Final burn-in automation deleted as obsolete; retain the existing L1 PASS.

The following September 9 snapshot is historical, superseded by the above:

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
