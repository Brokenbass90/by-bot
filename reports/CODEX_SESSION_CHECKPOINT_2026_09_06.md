# Codex session checkpoint — 2026-09-06

## Public continuation checkpoint

Latest continuation — **September 23, PAPER acceptance completed: 7/7 PASS**:
- At 13:44:52 UTC the existing proof-scoped PAPER kill command returned
  `confirmed_flat`: four actual filled sell orders for CRM/CRWD/CVX/MRK;
  fresh intended-flat, no open orders. Five foreign positions retain qty/entry.
- **All seven original PAPER evidence rows PASS.** Dossier:
  `reports/TINY_LIVE_CANARY_DOSSIER_2026_09_23.md`. Canonical JSON updated with
  close IDs/fills and raw private receipt hash. No strategy/risk changes.
- After confirmed-flat, removed ONLY completed intended acceptance cron;
  other cron lines unchanged. Existing PAPER account halt and durable state
  preserved. This acceptance run is complete, not an ongoing monthly selector.
- READY_FOR_OWNER_REVIEW=TRUE; LIVE_ACTIVATION_READY/READY_FOR_CANARY=FALSE:
  verified runner is exact-PAPER-only. Next concrete implementation is exact
  LIVE account/profile binding default-off, then owner amount + activation
  approval. Do not describe 7/7 as a ready LIVE toggle or profitability proof.
- Legacy ABNB/ABT/MA historical HWM remains unproven; never fabricate or adopt.
  AMZN intraday-owned. ATT1/LIVE untouched. Final broker evidence is private at
  `/root/by-bot/runtime/alpaca_intended_paper/acceptance_kill/final_receipt.json`.

Earlier continuation (superseded where noted):

Latest continuation — **September 23, next-session re-arm proven: 6/7**:
- Archived real broker snapshots at Sep22 13:30:51 and 13:31:13 UTC prove cron
  re-armed all four fractional positions with NEW accepted DAY stop IDs, exact
  quantities and unchanged durable floors. **Existing row 5 PASS; total 6/7.**
- Current inspection resumed Sep23 ~08:00 UTC, market CLOSED. Latest scheduled
  Sep22 21:59 cycle is `WAITING_FOR_REGULAR_SESSION`; cron active. Overnight
  absence of new cron receipts is expected for the 13–21 UTC schedule.
- **Only row 7 remains:** during regular market hours, existing proof-scoped
  intended PAPER kill → fresh owned-flat and foreign-unchanged truth. Rows 4/5
  are now secured, so acceptance kill may proceed once broker clock is open.
  Prepared private proof: `.private/alpaca_intended_20260919/intended_acceptance_kill_proof.json`.
  Validator must recheck exact PAPER account, entry IDs/fills and current scope;
  never adopt/close ABNB/ABT/MA/SCHW/AMZN. No kill command was executed this check.
- Updated canonical receipt has both archived snapshot hashes/new broker IDs.
  READY_FOR_CANARY remains FALSE until final actual kill evidence and dossier.
  No deploy, reset, strategy change or LIVE action. Next open Sep23 13:30 UTC.

Earlier continuation (superseded where noted):

Latest continuation — **September 21, after-close broker evidence: 5/7**:
- Read-only 20:42 UTC snapshot confirms all four intended PAPER positions retain
  exact entry quantities/averages, zero open orders, and all four original DAY
  stops explicitly `expired` with zero fills. **Existing row 4 PASS; total 5/7.**
- Cron active, one intended schedule, fresh runner/evidence (~33s/~31s);
  `WAITING_FOR_REGULAR_SESSION` is expected while broker clock is closed.
- Receipt updated: `reports/ALPACA_AUTONOMOUS_PAPER_2026_09_21.json` includes
  broker stop IDs, expiry timestamps and private snapshot hashes. No VPS writes,
  orders, restarts, reseeding or deployment in this check.
- Remaining rows **5 and 7 only**: Sep22 broker open 13:30 UTC / 16:30 Cyprus,
  verify new accepted DAY stops and preserved floors; then proof-scoped intended
  PAPER kill + owned-flat receipt. Never run acceptance kill before re-arm proof.
  Legacy foreign holdings remain excluded. READY_FOR_CANARY still FALSE.

Earlier continuation (superseded where noted):

Latest continuation — **September 21, autonomous Alpaca PAPER actually deployed**:
- **AUTONOMOUS_PAPER_ACTIVE; 4/7 real operational receipts PASS.** Canonical
  receipt: `reports/ALPACA_AUTONOMOUS_PAPER_2026_09_21.json`. Read it first.
- Installed isolated app `/opt/bybot-research/alpaca-intended-paper/app`;
  durable runtime `/root/by-bot/runtime/alpaca_intended_paper`. Cron enabled
  17:22:32 UTC; first automatic execution 17:23 UTC. No manual order trigger.
- Broker filled CRM/CRWD/CVX/MRK, all fractional; actual qty × average fill
  totals **$699.94** against frozen PAPER capital $1000 / gross 0.70.
  Four accepted DAY stops cover full actual quantities; actual-fill anchors.
- Fresh 17:24 cron process restored identical floor/HWM/entry IDs/quantities;
  subsequent cycles PASS, no duplicate BUY. Real evidence rows 1/2/3/6 PASS.
- Stop-exit → durable 21-calendar-day block, re-arm, emergency path integrated
  into existing bridge/runner. 151 focused checks PASS both Mac and VPS Python
  3.12.3, 46/46 hashes matched. No new coordinator/framework or strategy change.
- OLD PAPER manager is preserve-only (no new entries/stale rotation), with
  intended symbols excluded and shared account lock. All other cron lines,
  including LIVE, unchanged. All five foreign positions retain qty/entry:
  ABNB/ABT/MA/SCHW legacy adaptive; AMZN intraday. No foreign position adopted.
- **Next only:** collect real DAY expiry after Sept21 close, next-session new
  stop IDs at Sept22 13:30 UTC open, then existing proof-scoped intended PAPER
  kill + owned-flat receipt. Do not kill acceptance positions before rows 4/5.
  Evidence collector runs GET-only from the existing cron; private snapshots
  `runtime/alpaca_intended_paper/evidence/`, runner receipts in `receipts/`.
- This is one-session operational PAPER acceptance, NOT monthly strategy
  performance evidence. Entries allowed Sept21 only; later cycles maintain and
  reconcile. No claim that monthly strategy selection is autonomously scheduled.
- **READY_FOR_CANARY=FALSE.** Rows 4/5/7 pending. Legacy ABNB/ABT/MA historical
  HWM remains unproven; do not fabricate it. Uncertain pre-persist order ownership
  halts rather than auto-adopts; no durable pre-submit intent claimed.
- Existing heartbeat repurposed to Alpaca acceptance at 16:40/23:40 Cyprus on
  weekdays; unchanged results quiet. Raw broker artifacts remain private.
  ATT1/LIVE/risk unchanged; no new money enabled. After Alpaca dossier → ATT1.

Earlier continuation (superseded where noted):

Latest continuation — **September 20, intended PAPER fill/floor binding + sizing**:
- Default-off `ALPACA_INTENDED_PAPER=1` now binds terminal actual fill and
  broker-confirmed stop to the existing durable floor/HWM state. Partial fills
  require cancellation + terminal readback; uncertain orders halt new entries.
- Identity/account/strategy/finite-value checks fail closed. A broker stop below
  durable floor cannot report protection; an unreconciled prior lifecycle blocks
  a new buy before submission. Ratchet preserves entry ownership metadata.
- Frozen sizing uses explicit weights without redistribution or minimum-order
  inflation. Empty no-signal picks remain valid; small allocations are skipped.
- Mac integration fixture proves fill → ratchet → restart lifecycle-state
  equality → existing DAY re-arm floor calculation. Invalid quote cannot replace
  trusted HWM. This is NOT a real broker/scheduler lifecycle receipt.
- **120 focused Mac PASS; 131 target PASS including 11 legacy checks.** Python
  3.12.3; all 43 source hashes match. Isolated candidate:
  `/tmp/alpaca-paper-fill-floor-20260920-v1`. NOT production; no cron/order changes.
- **Next code step:** broker-filled stop exit → existing 21-calendar-day reentry
  record before lifecycle retirement; then finish existing intended runner
  ownership/emergency/re-arm scheduling and prospective PAPER deployment.
  Legacy missing-HWM PAPER recovery is prepared, not executed. AMZN remains
  intraday-owned. Do not claim that the market is the only remaining blocker.
- **0/7 real intended broker receipts; READY_FOR_CANARY=FALSE.** Receipt:
  `reports/ALPACA_PAPER_PREPARATION_2026_09_20.json`, execution_binding_continuation.
  ATT1/LIVE/risk unchanged. Worker `gpt-5.6-terra / medium` runtime verified.

Earlier continuation (superseded where noted):

Latest continuation — **September 20, Alpaca preparation**:
- Frozen selector/config/aggregator match the research checkout. Existing
  rehearsal reproduced 4/4 symbols, notionals and actual-fill stop distances.
  New `--prepare-intended` mode is offline-only; it deliberately rejects orders.
- Historical HWM for ABNB/ABT/MA cannot be proven from available artifacts.
  Bootstrap now refuses absent/mismatched HWM instead of seeding current price.
  No existing HWM state was replaced. Prepare emergency recovery, not fabrication.
- Existing bridge PAPER kill action has exact account/entry proof checks,
  durable per-account entry halt, owner scope and fresh flat confirmation.
  Actual signed VPS GET-only dry-run validated ABNB/ABT/MA; AMZN/SCHW excluded.
  Initial full-account 500-order cap failure fixed by scoped symbol query;
  cap still fails closed. No broker writes, emergency execution or cron changes.
- 89 focused checks PASS on Mac and target Python; 11 additional unchanged
  legacy adaptive checks PASS on VPS. All 39 staged source hashes match.
  Candidate only: `/tmp/alpaca-paper-preparation-20260919-v1`, NOT production.
- **Next exact code step:** existing bridge `_submit_buy_action` must persist
  terminal actual fill + confirmed stop into the existing floor/HWM state;
  prove restart/re-arm, frozen sizing and owned scope across bridge/ratchet.
  That execution integration remains unfinished. Do not say only market waits remain.
- **0/7 intended broker evidence; READY_FOR_CANARY=FALSE.** Kill preparation
  and fake-broker tests are not accepted broker lifecycle receipts.
- Receipt: `reports/ALPACA_PAPER_PREPARATION_2026_09_20.json`. Source/proof data
  remain private; no new framework/strategy and no ATT1 or LIVE changes.

Earlier continuation (superseded where noted):

Latest continuation — **September 19, Alpaca first (owner reprioritized)**:
- PAPER endpoint support implemented in existing protection manager; frozen strategy
  unchanged. 61 focused tests PASS on Mac and VPS Python 3.12.3, 13 hashes match.
  Candidate staged in isolated `/tmp/alpaca-paper-endpoint-20260919-v1` only;
  production files/cron/broker orders were NOT changed. Not a service deployment.
- All five PAPER positions traced by exact filled order IDs: ABNB/ABT/MA/SCHW
  are legacy adaptive; AMZN is intraday (state + log + broker qty/ID match).
  Do not treat AMZN as ownerless or adopt it into intended Alpaca.
- Historical broker stop levels found for all four adaptive positions; current
  open orders zero in CLOSED session. ABNB/ABT/MA HWM recovery remains unresolved;
  monthly HWM file is empty. No synthetic HWM or floor state was written.
- Intended operational evidence remains **0/7**, readiness FALSE. Fix/lineage
  do not replace real intended PAPER startup/fill/DAY/re-arm/restart/kill receipts.
- Next: audited legacy floor/HWM recovery and frozen intended PAPER wiring;
  existing seven broker steps; dossier; owner live amount/approval. Then ATT1,
  then SBR1. ATT1 services/risk and public shadow untouched this cycle.
- Receipt: `reports/ALPACA_PAPER_PROGRESS_2026_09_19.json`. Full suite collection
  remains blocked by missing yfinance; focused suite is not full-suite PASS.
- Worker actually ran `gpt-5.6-terra / medium`, checked in runtime metadata.

Earlier analysis snapshot (superseded above):

Latest owner handoff — **September 19, analysis only**:
- Scope updated: Codex owns ATT1 production + Alpaca frozen packet to VPS/PAPER.
  Claude owns existing registry/Factory and Gold. Earlier Alpaca pause below
  is superseded. No deployment, orders, strategy changes or new gates this cycle.
- Read `reports/CONTINUATION_HANDOFF_2026_09_19.md` for the complete short
  new-chat handoff, artifact paths/hashes and exact next action;
  `reports/CURRENT_PROJECT_ROADMAP.md` is updated with owner/queue priorities.
- Fresh VPS check: OLD fairness hash remains deployed, heartbeat 3.17s, service
  starts September 18 06:38 UTC (later restart cause NOT checked). Public
  PID 451398 unchanged, heartbeat 0.77s, 21 sessions, **0 clean filled terminal**.
  Current scan snapshot 49 symbols, not proof of completed 51/51 this hour.
  September 14 bounded collector finished with START/DONE only, no stacks.
- Alpaca packet is in sibling `../bybit-bot-clean-v28/research_lab/pakety/`.
  Research handoff sufficient to START operational work. Its wrong offline
  evidence link is resolved to `research_lab/data/alpaca_repetitsiya.json`:
  9/9 offline PASS, **0/7 VPS/PAPER receipts confirmed from packet artifacts**.
  Do not conflate those counts. Actual current Alpaca broker truth was not read.
- Next executable action: PAPER account/positions/orders plus existing ownership,
  HWM and manager receipts. Then the packet's seven operational steps unchanged.
  No AMZN disposition by assumption; no owner capital chosen from rehearsal.
- Reuse existing `research_lab/data/reestr.json`; no duplicate master registry.
  SBR1 next: restore existing shadow/parity results (August 24 deploy receipt
  exists), not restart historical research. Preliminary +22.35R/PF2.14 unverified.
- **READY_FOR_CANARY: ATT1 NO / Alpaca NO.** Owner live approval absent.
  A new chat has not been opened; paste-ready continuation is in the handoff.

Earlier continuation (superseded where noted):

Latest continuation — **September 14, 10:29 UTC**:
- **OLD WebSocket fairness fix DEPLOYED**, separately from money binding.
  Exact live base `aeda59e299fac9833c68816088997e927d82b8392137072521ecb76e081b2128`
  plus only the yield from commit `c431231`; deployed SHA256
  `c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1`.
  Do NOT deploy the full recovery monolith as this patch; it contains additional
  unfinished default-off binding work.
- Watchdog's 127s stall and restart at 08:02 UTC are confirmed. VPS did not
  reboot. No timed stack for that exact incident. The exact deployed OLD source
  reproduced buffered-message starvation on Mac; candidate and VPS Python
  regression PASS. Whole AST otherwise identical. This is a targeted mechanism
  fix, not proof all synchronous blocking calls have been eliminated.
- Deployment required fresh signed flat/no-orders truth both before and after
  a brief maintenance stop, source/config hash guards, existing watchdog lock,
  atomic backup and rollback. First attempt aborted BEFORE stop on stale
  heartbeat; second completed with guards unchanged. OLD remains active, risk
  and config unchanged; NEW binding remains **NOT DEPLOYED**.
- New OLD PID **1360223**, started **10:27:03 UTC**; post-check heartbeat 7.15s,
  PID unchanged, NRestarts=0. Runtime backup/private receipt:
  `/root/by-bot/runtime/old-fairness-release-20260914T102701Z`.
- Existing read-only nonblocking timed collector re-armed under
  `/root/by-bot/runtime/att1-stall-capture-20260914`: 12h/24 dumps maximum,
  trigger heartbeat >=30s, no duplicate collector. Post-check START/no stacks.
  September 13 collector is completed history. Existing heartbeat automation
  now follows the new capture path and deployed patch; do not reapply it.
- Public runtime unchanged: PID 451398, heartbeat 0.53s, 51/51 attempts,
  10 sessions, **0 clean terminal net-R**. Public observation gap remains open.
- Mac native research job remains COMPLETE (four stages at 06:53 UTC); exact
  OLD baseline/candidate regression also ran on Mac this cycle. No production
  dependency was moved and no unrelated process was stopped. Owner explicitly
  defers server upgrade until at least $10/month profit; no purchase now.
- Receipt: `reports/ATT1_OLD_FAIRNESS_DEPLOYMENT_2026_09_14.json`.

Next: use new timed stacks if another OLD stall occurs; otherwise continue
existing NEW dispatch/fill/protection/cost finality and public observation gap.
A slow synchronous public orderbook request is a reproducible observation-loop
bottleneck; changing a timeout alone does not prove continuity. Preserve 2s gate.
**READY FOR OWNER ACTIVATION = FALSE.** No new subsystem or strategy.

Earlier continuation (superseded where noted):

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
