# MASTER HANDOFF — 2026-10-02

Canonical production entry point; October2 owner-approved Tasks1–4 engineering
is delivered. Current code3f999c9; resolve subsequent documentation HEAD from Git.
Read NEW_CHAT_START_HERE.md and TOP checkpoint next. NEW ordersOFF, actual account
BUILD_READY blocked by the named risk/cost/drain/watermark inputs and clean cohort.
Local242/target233 focused tests PASS; unchanged57 baseline full-suite failures
are explicitly reported. Independent financial review's two P1 findings were fixed
and primary-verified; its original CHANGES_REQUIRED verdict remains recorded.

Latest broker follow-ups: Alpaca **19:12:24UTC /22:12 Cyprus**, same3 holdings,
accepted full DAY stops, floor/HWM monotonic and one NEW manager. Original
Oct2 DAY expiry/re-arm PASS at13:38UTC is retained with its timestamp. OLD ATT1
native new-entry pause already applied15:36UTC; signed18:55UTC GET flat/no orders,
service PID492970 preserved. Public18:55UTC:1 IOC nonfill,0filled/clean, PID1584802.
No money/service/cron/risk changes in this engineering delivery.

Current receipts/runbook: ATT1_CANARY_ORDERS_OFF_READINESS_2026_10_02.json,
ATT1_CANARY_ORDERS_OFF_HANDOFF_2026_10_02.md, ALPACA_LIVE_FOLLOWUP_2026_10_02.json.
CURRENT_PROJECT_ROADMAP.md now includes the manager's staged development queue.
Fresh Claude KARTA from originresearch/fabrika-v1@e965b68 supersedes old FX claims:
NOCHNOY is KILLED/NOT_EXECUTABLE; TOLPA first needs current PIT inputs. Research
was read only, no merge/evaluator/window consumption. Drift-prone facts must be
refreshed before future action; historical sections keep their original dates.

October2 roadmap clarification: use admissible history/replay before market waiting;
inventory existing coverage and close named gaps, preserving sealed windows.
Receipt compatibility is separate from net edge;2–3 clean terminals are operational
acceptance. See CURRENT_PROJECT_ROADMAP.md, "History and replay before market waiting".
This clarification ran no replay/evaluator and changed no code/runtime/money gate.

## 1. Repository, authority and delivery

- Production checkout: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824`.
- Branch: `codex/recovery-20260824`; remote: `origin` (Brokenbass90/by-bot).
- Migration commit verified against actual origin at continuation start:
  `8ffe20816fab2ebb6b64dfab5372341ca708ce7e`; branch/head matched. Subsequent
  evidence/documentation commits must be resolved from current Git, not this value.
- Last committed/pushed HEAD **before the migration-only commit**:
  `f361f7e80739afbb46514e59746a91b02734f7ba`, `Record owner Alpaca live launch and protected broker fills`.
- Other exact milestones: `c5745a3` owner activation procedure; `834990d` ATT1 native SL recovery;
  `74b7214b2d722b9e45c12024065d9a78c162567f` installed Alpaca source.
- This file cannot embed its own future commit hash. Resolve the latest document
  version with `git log -1 --format='%H %s' -- reports/MASTER_HANDOFF.md`;
  migration commit is8ffe208. Verify current HEAD against origin.
- Preserved unrelated untracked file: `configs/allowlist_change_log.json`. Do not stage or delete it.
- VPS: `root@64.226.73.119`; SSH key path `~/.ssh/by-bot`; VPS cron timezone **Etc/UTC**.
- Owner performed actual Alpaca activation on Oct1 at 14:05:49 UTC. Codex only
  observed broker GETs afterward. No further activation, sizing escalation or live experiment is authorized by this handoff.
- Separate direct owner instruction Oct2 authorized the native OLD ATT1 new-entry
  pause and NEW canary preparation orders-OFF. Pause executed15:36:43UTC with fresh
  broker pre/postchecks; this does not authorize NEW money or OLD resumption.
- No trading code, service, risk, cron or strategy changes in the migration turn.

## 2. Alpaca LIVE — actually operating

Owner activation backup: `/root/by-bot/runtime/alpaca_intended_live/owner_activation_20261001T140549Z`.
Endpoint `https://api.alpaca.markets`; bound account suffix **f295c6**; currency USD.
Capital cap **$487.42**, frozen gross **0.70**, max positions4, max individual weight0.60.
Three picks are legitimate; do not force a fourth. Entry notional **$341.149999263748**.
The cap is allocated capital, not a guaranteed maximum loss. Stops do not eliminate gap/slippage risk.

Frozen signal session Sep30 → entry session Oct1. Selection CRWD/AMD/META prepared
Sep30 20:12 UTC. First actual scheduled LIVE cycle Oct1 14:10 UTC; bridge0/ratchet0.
Latest follow-up **Oct2 19:12:24UTC**: same3 held quantities/lineage, full DAY
stops AMD622.24/CRWD242.13/META668.76, HWM644.811/273.335/736.33;
one NEW manager, all58 hashes unchanged, latest completed cycle19:10:05UTC.
See `ALPACA_LIVE_FOLLOWUP_2026_10_02.json`. No filled sell/closed lifecycle.

The DAY re-arm acceptance snapshot below retains its original13:38UTC time:
maintenance receipt **Oct2 13:35:02 UTC**, `LIVE_CYCLE_COMPLETE`,
bridge0/ratchet0, owned names all3; direct broker truth at13:38:52UTC.

| Symbol | Actual qty | Broker avg entry | Accepted DAY stop / durable floor | Durable HWM at snapshot |
|---|---:|---:|---:|---:|
| AMD | 0.186377282 | 609.57 | 615.24 | 637.5625 |
| CRWD | 0.469970151 | 265.336 | 242.13 | 273.335 |
| META | 0.141939508 | 724.534 | 668.76 | 735.79 |

All three original buys filled. Three open sell stops have broker status `new`,
TIF `day`, exact held quantities. Entry/stop order IDs match durable ownership state.
Raw IDs are in private broker receipts and durable state; no account credentials in Git.

Oct2 direct order history proves all3 previous DAY stops expired after Oct1 close;
new stop IDs cover exact remaining quantities. Original fills/account/lifecycle
identity unchanged, floor/HWM monotonic versus Oct1 intraday baseline.
`ALPACA_DAY_REARM_2026_10_02.json` is PASS for this operational transition only.

Software trailing is already working: every5min the same manager ratchets a fixed
DAY broker stop using lifecycle HWM, default activation+3.5%, trail3.5%, minimum
locked gain0.5%. Profile/base env has no overrides for those keys. AMD stop moved
560.90→612.61→615.24, above entry609.57; CRWD/META not yet trail-armed at snapshot.
This is periodic software control and DAY protection, not continuous overnight
coverage or a guaranteed fill/profit at the stop price.
No closed real lifecycle / realized-profit conclusion yet. Initial execution-fee-free
entry-to-stop distance sum was $27.893643758238, **not a guaranteed loss cap**.

Runtime: `/root/by-bot/runtime/alpaca_intended_live`.
App: `/opt/bybot-research/alpaca-intended-live/app`, release `releases/73345c03fa823d82`.
Manifest SHA256 `73345c03fa823d82a2c330902624206d14123ed6269667774569ec5db1f0fbb2`;
all58 source hashes reverified unchanged. Historical243 local/VPS tests were Sep25;
do not claim they were rerun during launch/migration.

Authoritative files: `binding.json`, `latest_intended_run.json`, `latest_selection.json`,
`protective_exit/protective_exit_hwm.json`, `protective_exit/protective_exit_latest.json`,
`monthly_reentry_block.json` when present, `execution.log`, `logs/readonly.log`.
Names containing `paper` or `readonly` in shared code/log/tag names do not establish
execution mode; inspect endpoint, binding and actual cron arguments.

First entry-cycle receipt's `owned_positions=[]` was a **pre-entry snapshot**.
It was not broker-flat evidence; the later maintenance receipt now includes all3.
Initial `--preflight` requires a flat account and MUST NOT be used as health check now.

## 3. Jobs and ownership — preserve, do not toggle

Alpaca schedules below are UTC, weekdays unless otherwise stated.

| Job/tag | Required state / current schedule |
|---|---|
| `alpaca_intended_live_readonly` | **ON, actual `--send-orders`**, `*/5 12-22 * * 1-5`, one cron only; shared cycle/account locks |
| `alpaca_intended_live_data` | ON, `--prepare`, `10,25,40,55 20-22 * * 1-5`; read-only broker preparation |
| `alpaca_live_v38_manager` | **OFF: cron absent, process absent** |
| `alpaca_protective_exit_only` | **OFF: cron absent, process absent**; NEW owns protection |
| `alpaca_v38_daily_refresh` | Remains commented SAFE_HOLD_DISABLED |
| `alpaca_readonly_health_auditor` | Preserve, `7,22,37,52 13-21 * * 1-5` |
| `alpaca_readonly_health_preopen` | Preserve, `45 12 * * 1-5` |
| `alpaca_readonly_health_weekend` | Preserve, `7 */6 * * 6,0` |
| `alpaca_monthly_tg_report` | Preserve, `20 22 1 * *`; reporting, not another owner |
| `alpaca_adaptive_v1_manager` | Preserve isolated legacy PAPER `legacy_preserve.sh`, `*/30 14-21 * * 1-5` |
| `alpaca_adaptive_v1_refresh` / lively shadow | Preserve PAPER research schedules13:10 /12:40 UTC; do not adopt their holdings |
| monthly autopilot `bybit-bot-managed` | Preserve09:30 UTC day1; inspected default env endpoint is PAPER, not NEW LIVE |

VPS services/timers: Oct1 inventory retained unless explicitly refreshed below:

- `bybot.service` OLD crypto LIVE running/enabled, PID492970; `att1-lifecycle-zero-risk-v2.service`
  running/enabled, NEW public PID1584802 after authorized Oct2 cutover. Both
  NRestarts0 since their respective current starts; OLD PID492970 unchanged.
  This is not zero lifetime restarts; earlier OLD start reason not audited here.
- `liquidation-collector.service` running/enabled PID492740.
- `att1-fixed51-raw-shadow.timer`, `att1-ets2s-signal-shadow.timer`,
  `btc-h1-regime-updater.timer` active/enabled. L1 signal service itself was
  inactive/dead, Result=success, unit disabled: normal timer-triggered oneshot, not a missing daemon.
- `sbr1-zero-risk-shadow.timer` active/enabled; last checked17:10 service result timeout/failed.
  Claude describes valid underlying coverage and a misleading summary counter.
  Keep both facts; systemd failure alone does not prove the research dataset broken,
  and Claude's note alone does not prove current operational health. No restart/repair today.
  Fresh17:13UTC prefix:47,968 events, valid chain,0 admitted/fills/outcomes,
  control journal absent; last17:10 run timed out. This blocks comparison, not
  a strategy verdict or evidence-corruption conclusion. See continuation receipt.
- Density collector remains OFF, no required OLD/public ATT1 consumer found in checked code.
  Do not resurrect a manual screen collector to make a process list look complete.
- Existing unrelated cron entries are **preserve-as-is**, not approval to revive
  obsolete strategies. Do not replace an entire crontab with an old snapshot.
- Bounded ATT1 desktop monitor was last confirmed paused Sept29; service continues independently.
  Do not assume a next-day notification exists. No new automation installed during migration.
- Claude reports Factory daemon stopped for evidence-acceptance defects. Fresh Mac
  process-list lookup was unavailable (`sysmond service not found`), so current daemon
  state is NOT_CONFIRMED. Do not start it or new launchd jobs from this handoff.

## 4. DAY operational check — October 2 PASS; next October 5

Oct2 check completed PASS by direct broker history, accepted full-qty protection,
monotonic lifecycle floors/HWM, completed manager cycle and single NEW owner.
Receipt `ALPACA_DAY_REARM_2026_10_02.json`; no manual activation or order writes.
Comparison used saved **Oct1 17:07 intraday** baseline, not an EOD HWM snapshot.

Fresh broker clock: next close **Oct2 20:00 UTC /23:00 Cyprus**; next regular
open **Oct5 13:30 UTC /16:30 Cyprus**. Apply the same acceptance procedure below
to remaining owned positions; genuine filled exits require reconciliation. All
calendar times are broker-backed snapshot facts; later DST/calendar must be refreshed.
The numbered Oct2 protocol below is retained as the acceptance method/history.

1. Preserve an end-of-session baseline privately: owned positions, full remaining qty,
   last accepted stop IDs/status, durable floor/HWM/entry IDs, latest successful receipt.
   An interim17:07UTC baseline is already saved as
   `.private/continuation_20261001/alpaca_baseline_20261001T170706Z.json`.
   It is intraday; prefer the later end-of-session baseline when available.
2. Query those stop IDs after expiry. Position-present + actual `expired` DAY receipt
   establishes expiry; absence from open orders alone does not. Filled stops require
   real fill/remaining-position reconciliation instead of assumed expiry.
3. At Oct2 regular open, allow existing scheduled manager to run. Observe first completed
   cycle and direct broker truth, then compare against the saved baseline. Do not run
   `--send-orders`, kill, restart or activation manually as a test.
4. Reconcile every remaining owned position to a newly accepted stop order ID, exact
   remaining qty and persisted floor **identical or higher**. HWM must not decrease;
   ownership/account/entry lineage must be unchanged. Genuine closed-flat positions
   need exit receipts, not a forced re-arm or re-entry. Oct2 is maintenance-only.
5. Verify exactly one NEW writer and zero OLD writers/processes again. Check source
   hashes and errors. Account/list endpoints must be complete, not truncated pages.

**PASS:** actual expiry/legitimate fill evidence + next-session accepted protection
for all residual owned qty; durable floor/HWM monotonic, exact identities, fresh
successful cycle, single manager, no duplicate buys/sells or unknown ownership.
This proves this operational transition only, not profitability or live restart testing.

**FAIL / NOT_CONFIRMED:** evidence missing/stale/incomplete, pending stop not yet
accepted, no completed post-open cycle, source/identity mismatch. Do not promote it to PASS.

**ALERT:** held exposure without accepted protection after the manager's expected
post-open maintenance cycle, lowered floor/HWM, duplicate/foreign orders, simultaneous
writers, incident/emergency receipt, or manager unable to run. Notify owner promptly;
preserve receipts. If first-cycle completion has not appeared, inspect by13:35 UTC
and escalate unresolved missing protection; this is an observation deadline, not
a changed strategy gate. Overnight DAY expiry is expected behavior and requires
the next-session check; it is not continuous overnight stop coverage.

Owner emergency procedure: `ALPACA_OWNER_ACTIVATION_2026_09_30.md`, sections4–6.
Entry halt retains SAME protection manager; kill is proof-scoped, flat rollback
requires fresh broker-flat. Never disable all protection or resurrect OLD over NEW positions.
No live kill/restart experiment is authorized for acceptance evidence.

## 5. ATT1 current public epoch and money gate

**Oct2 13:57:43UTC DEPLOYED_PUBLIC_ONLY_COHORT_PENDING.** Existing public unit
`att1-lifecycle-zero-risk-v2.service` now runs epoch
`att1-public-lifecycle-20261002-paired-observation`, runtime
`/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20261002-paired-observation`.
Driver97239996…345d6885/config4f35079c…1825c. Only observation driver and fresh
epoch/runtime metadata changed; other30 deployed pins, old core/profile/strategy,
unit, 2s/freshness, admission/risk and single journal writer preserved.

All32 old pins matched before cutover; fresh14-session/162-record replay and
journal bytes identical with candidate. Old epoch has12 filled simulations,
2 nonfills,12 recovery gaps,0 clean filled terminal,0 held/pending. Retired209
journal/source/epoch/scan evidence files preserved with exact hashes. Old labels
remain dirty; no journal pins were rewritten or sessions imported into new epoch.
51 hash/geometry/closed-H1 validated caches seeded; no old lifecycle import.
Oct1 54 local/VPS targeted tests remain the engineering proof, not a new Oct2 rerun.

Target preflight read-only/no network passed as bybot-research; fresh RUNNING
heartbeat/public PID1584802 and broker/order calls0. OLD PID492970, Alpaca binding,
all58 source pins and complete cron unchanged. First new H1 scan complete51/51
at14:07UTC:50 NO_SIGNAL,1 HFT stale-bar rejection;0 sessions,0 poll errors.
Heartbeat fresh388ms. Successful scanning is not a cohort PASS. See
`ATT1_PUBLIC_CUTOVER_2026_10_02.json` for latest postcheck and exact receipts.
Backup driver/config/unit in `rollback-paired-observation-20261002`; file restore
roundtrip PASS Oct1, actual runtime rollback NOT_NEEDED_NOT_TESTED. If future
rollback is needed, stop only public unit and preserve all new epoch evidence.

The tested fix fetches at most2 adjacent eligible books, drains before ordered
management, never bypasses pending exits/protection and rechecks freshness at
consumption. Existing IOC post-fetch continuity marking remains outside this
patch: a clean verdict requires actual2s source/consumption/continuity evidence,
not receipt labels alone. Any new gap stays fail-closed and must be localized.

NEW authenticated binding native SL→fees/funding→finality is code complete,
**orders OFF**, not installed over OLD money service. Existing346 local/VPS tests
are engineering evidence, not broker cohort. Next money gate remains **2–3 clean
prospective filled terminals with terminal net-R**, then fresh exact OLD absolute
risk, exclusive handoff/canary dossier and explicit owner financial action.
OLD risk_multiplier0.10 alone is not absolute USD per-trade risk.

Oct2 early-LIVE follow-up14:55:22UTC signed Bybit GET:0 linearUSDT positions,
0 open orders/complete pagination; OLD492970 unchanged, ATT1enabled/Elderdisabled.
Breaker21-day5 trades/net-1.0271USDT/winrate40% is diagnostic, not full account PnL.
Public NEW still RUNNING/0 sessions/open/calls at this capture. Code-complete
binding above is GET-only evidence/reconciliation, SEND_ENABLEDfalse; no installed
autonomous NEW money runner or one-flag activation. Replay profile enforces
send_enabledfalse. Exact absolute risk and exclusive financial installation
remain required; question about tiny LIVE does not waive frozen clean-cohort gate.
OLD capital override absent/percentage-equity model/minqty fallback defaulttrue:
do not substitute old0.10 multiplier or virtual public risk1 for money cap.
Verified hot-read OLD new-entry pause proposal:
`ATT1_OLD_ENTRY_PAUSE_PROPOSAL_2026_10_02.md` was PREPARED_NOT_EXECUTED at14:55UTC.
Receipt `ATT1_EARLY_LIVE_AND_LEADS_2026_10_02.json`; refresh truth before any action.

**Later owner-approved pause executed15:36:43.296–15:36:43.300UTC.** Native
`bot.operator_strategy_controls.pause('att1', source='owner_codex_20261002')`
wrote `/root/by-bot/runtime/operator_strategy_controls.json`; only ATT1 new
entries paused, no other sleeve key changed. Fresh signed GET immediately before,
immediately after,90.167s after,692.768s after and nextH1 at16:02:50UTC:0 positions/0 open orders,
complete pagination. OLD PID492970 unchanged; no service stop/restart, env/risk/
strategy/SL/TP/position change or broker write by this procedure.
Control readbacks15:53:21UTC and16:02:50UTC: is_pausedtrue, no read error, SHA
`239a24050a91155358a1aa545d67e6c720fa3bef4da54a53c2951b4570bf02ef`.
Module/source hot-read entry boundary verified. After nextH1, actual daemon
`att1_skip_operator_pause=115`, ATT1 schedule delta115 and entries unchanged1.
These are suppressed entry-handler calls, not115 signals/trades. No restart test.
Base heartbeat still reports ATT1enabled/money config: operator pause is a separate
hot-read gate. Existing control missing/damage fails OPEN; pause is not a hard
kill, instant drain or finality proof. No automatic resume; a late fill remains
OLD management's responsibility and blocks handoff.
`ATT1_OLD_ENTRY_PAUSE_EXECUTED_2026_10_02.json` contains sanitized receipts/hashes.

At15:53 public NEW PID1584802 RUNNING, calls0/open0, same epoch: **1 C98 session,
0 filled simulations/0 clean filled terminals**. Its three-record valid chain is
START→ENTRY_ACK→ENTRY_FINAL CANCELLED, no fill. This simulated IOC nonfill does
not verify held-position timing or satisfy the2–3 clean terminal gate.

Owner's next build scope: `docs/superpowers/plans/2026-10-02-att1-canary-orders-off.md`.
Four bounded tasks reuse existing process/reservation/coordinator: source-proven
fixedUSDT risk and daily OLD+NEW budget; atomic reserve/finality cash transfer;
captured entry/protection/exit/recovery commands; inert source closure plus
rollback/handoff dossier. No second money daemon or one-flag activation.
Owner approved the Native plan; Tasks1–4 are now delivered locally/Git.
Engineering242 local/233 targetPASS; actual numeric source acceptance remains
BLOCKED. Runbook/receipt above include the two implemented critical review fixes.
No code/build installed on money service and no numeric risk approval claimed.
Regime/Elder separate and nonblocking. Public collection continues during build;
NEW money requires clean cohort + fresh absolute-risk/exclusive dossier + owner GO.

Oct2 read-only regime/Elder inventory: existing BTC H1 EMA200±2% updater is alive
and hash-bound; at13:45UTC its13:00 closed-H1 receipt was above_band (+3.416%) but
older than the5min admission freshness gate. It is not proof of every alt's trend.
Actual OLD entrypoint already has caller regime code behind default-OFF
ATT1_CALLER_RECEIPT_ENABLE; current config chain leaves it absent/defaultOFF,
legacy ATT1_TREND_GUARD_BARS absent/default0, REGIME_OVERLAY_ENABLE0. This config
read is not mutable process-state or historical PnL proof. No money setting changed.
Existing native research contract allows ATT1 only flat_down, not every bear regime.
Follow-up14:29UTC: same public epoch/PID/pins, RUNNING, heartbeat180ms,
51 scan results(50 NO_SIGNAL/1 stale HFT),0 sessions/open/poll errors,
broker/order calls0, financial authority false. No prospective filled case yet.
Current OLD path overrides also absent: default manifest and regime input missing
under/root/by-bot; updater's real input is under/opt/bybot-research/live-caller-parity.
Default caller journal absent expectedOFF; no broken-writer verdict. Do not simply
enable caller: source-pin comparison cannot run without actual manifest.

14:00H1 scan51/51 hash-chain/bytes validated: completion14:00:23.369–14:02:13.126UTC.
Current same-hour BTC file replacement14:03:06.841 is53715ms after last scan;
mtime does not prove complete historical availability. Late receipt is not
causal input for earlier decisions, and SCAN completion is not admission.
`ATT1_REGIME_GATE_READINESS_2026_10_02.json` records exact timestamps, pins and limits.
Next written DRAFT: `docs/superpowers/specs/2026-10-02-att1-regime-prospective-design.md`.
First immutable receipt availability archive + expected hour×51 scan/source audit,
with UNKNOWN/omissions and bounded resource isolation; then a separately frozen
policy comparison with independent admission/cooldown and common causal book tape.
Filtering existing trades alone cannot prove policy improvement. Draft reviewed
critically; owner written-spec approval still pending, no product implementation.
Global bull/bear/range routing is separate; public timing burn-in stays unchanged.
`REGIME_ELDER_INVENTORY_2026_10_02.json` records findings and limits.

## 6. LTC id257 — final bounded conclusion

Fresh authenticated historical GETs resolve the **0.4 entry /0.2 final SL discrepancy**:
Sell0.4@71.87; reduce-only Buy0.2@70.96; **14.768s later** StopLoss Buy0.2@70.99.
Total exit0.4; current LTC position0; gross0.358, execution fees0.0314259,
execution-fee net **+0.3265741 USDT**, matching DB close id258.

Status **QUANTITY_DISCREPANCY_EXPLAINED_CLOSED_FLAT**. A final0.2 stop protected the
remaining0.2 after a real partial exit; it does not prove original half-protection.
Initial SL72.8 armed quantity and continuous protection before partial exit remain
**NOT_PROVEN** from final mutable order history. Do not call OLD repaired or infer
the first partial exit was TP1 without runner evidence. No funding transaction audit
was done in this bounded check. Reference `LTC_ID257_PROTECTION_STATUS_2026_10_01.json`.

## 7. DO NOT TOUCH

- Alpaca frozen selection/sizing/exits, capital cap, live endpoint binding,
  current positions/protection/orders, entry intents, locks, floor/HWM, same manager.
- Do not rerun owner activation or initial-flat preflight on the now nonflat account.
- OLD ATT1 configuration/risk/positions/management and **applied new-entry pause**;
  no auto-resume or service stop. NEW order submission remains OFF.
- Public ATT12s gate, current epoch/journals, dirty/retired evidence, implementation pins.
- Consumed/sealed research windows, original datasets/manifests, private broker evidence.
- Foreign legacy PAPER ABNB/ABT/MA/SCHW and intraday AMZN; no silent adoption/liquidation.
- Claude checkout/branch, unrelated dirty files, global crontab, Factory/Mac autorun state.
- Never publish env/key material, full broker account records, credential-bearing logs,
  private evidence or a whole-repository archive. Read credentials in memory only.

## 8. Project direction and Claude continuity

Objective: durable multi-market system finding **real net edge after costs**, then
carefully implementing and measuring it. Reward measured progress, kill weak leads,
preserve capital and optionality. Profit is a hypothesis to test, not a deadline promise.

Production priority: protect/observe Alpaca LIVE → ATT1 existing gate/dossier.
Oct1 owner-manager scope: Claude only PM2 after valid v5 snapshots and TOLPA_1D
after≥90% hourly coverage. SBR1 parked, no new research directions until those
results; no Factory rewrite or Alpaca expansion. Owner Oct2 additionally asked Codex to
assess existing trend/Elder/range components; inventory is read-only and policy
changes remain a separately reviewed design. Latest owner Oct2 direction keeps
regime work separate/nonblocking and reports a connected `BullWaves-LIVE` account
for read-only FX costs. This owner report is not independently verified exporter
binding or accepted NOCHNOY_DREYF net-edge evidence.
Existing leads were reconciled read-only against current registry Oct1. SBR1
comparison is blocked at0 main outcomes/no control journal; deployed fixed51 is
preparity raw, so existing prereg section7 certification remains necessary.
XSEC exact PIT and Bull Continuation tested variants are NEGATIVE; do not revive.
ETS2M WIDE frozen-cohort verdict is no earlier Oct10 19:00UTC. Claude's FX
confirmation claim still lacks spread/swap and accepted net-cost evidence.
Preliminary SBR1 +22.35R/PF2.14
is a historical lead, not fresh/live profitability. Strategy diversification is
a goal; it is not permission to force trades or loosen admissions.

Research owner Claude: sibling `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`.
Authoritative research branch is **research/fabrika-v1**, commits via Git plumbing.
Oct2 local and cached tracking ref both
`c12af845575337933fb2a5e2be8a615680b2b625`; actual origin independently verified
at same SHA. Earlier Oct1 publication divergence is historical and resolved.
No research push/merge/checkout mutation by Codex.
Later Oct2 source reconciliation: local research ref and actual origin both
`f6f2e20a3b88bfcad41d1cdc1fa7b98fa2a0687b`, current KARTA/protocols read from that
immutable ref. Cached tracking not refreshed/claimed. No Codex research mutation.
The deliberately unchanged working checkout **codex/dynamic-symbol-filters**,
HEAD `76fc63ccbe43197e24452e3e4e28ae79a719e4ef`, is not the research work ref.
Earlier "branch mismatch" interpretation was incorrect and is superseded here.
Read `research_lab/KARTA.md` from the immutable research ref, especially
"Синхронизация с Codex"; use `git show research/fabrika-v1:research_lab/KARTA.md`.
Old HANDOFF_CLAUDE_2026_09_30*, STRATEGY_MASTER and reestr.json are historical maps.
The frozen Alpaca packet retains its independent operational lineage; the old
CODEX_ATT1_ONE_SESSION_HANDOFF is superseded for native-SL wiring.

TOLPA_1D cheap-screen at497600d: SURVIVED, edge16.3bps/day with model12bps/funding,
t_NW2.14,1283 days, halves1.5/31bps, coverage96.9%. Result/source read, not rerun;
same family as weekly L1, evidence must not be added. Current c12af845 already contains
`tolpa1d_vpered.py`: prospective beginsOct2, fixed180/365 daily observations,
t_NW lag1>=2.2; source read only, no evaluator rerun. Expected historical effect
has low power even at365 days; do not promise quick confirmation. Weekly L1
`tolpa_vpered.py` is separate and evidence is not additive.
PM2 evidence only valid v5 from Oct1 16:09:19UTC; frozen judge requires at least
three calendar data dates, preliminary diagnostics before then. EXECUTABLE means
pricing-screen evidence and still needs both-leg/cost/execution gates before money.

Claude handoff reports Factory acceptance-guard defects and exhausted O1/O2 windows;
daemon stopped, equities BLOCKED_DATA on survivorship/universe, not merely two tickers.
These defect claims are historical: current f6f2e20 KARTA reports self-check PASS,
daemon stopped/queue empty, new preregistered Discovery item required. Source/map
read only, not independently rerun tests or fresh Mac process audit. Current PM2
preliminary2 calendar dates/496 ladder rounds/0 violations; complete its frozen
judge before new direction. FX current exporter permits same-broker/type demo
while report requests intended live-broker costs; equivalence NOT_VERIFIED.
Full frozen gate requires summer/winter spread, slippage, commission and swap
for all7 pairs. Demo can begin collecting, cannot itself certify LIVE costs.
Do not start momentum/Gold tests or consume new windows from this document. These
research claims were not independently revalidated or merged in migration.
Future queue: resolve existing evidence/acceptance defects → repair existing leads →
bounded diverse hypotheses. Factory ceiling READY_FOR_BUILD; money promotion stays explicit.
Cleanup later: inventory→archive with hashes/references→verify no active dependency;
no deletions of evidence, active state, credentials or unknown work. No cleanup today.

## 9. Read-only commands for continuation

Run on Mac; stdout below can contain financial records, so keep it private.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824
git status --short
git branch --show-current
git log -1 --format='%H %s'
git log -1 --format='%H %s' -- reports/MASTER_HANDOFF.md
git ls-remote origin refs/heads/codex/recovery-20260824
```

Cheap runtime/manager inspection (no restart or invocation of trading runner):

```bash
ssh -i ~/.ssh/by-bot -o BatchMode=yes -o StrictHostKeyChecking=yes root@64.226.73.119 \
  'systemctl show bybot.service att1-lifecycle-zero-risk-v2.service liquidation-collector.service -p Id -p ActiveState -p MainPID -p NRestarts -p ExecMainStartTimestamp; systemctl --failed --no-pager; systemctl list-timers --all --no-pager; crontab -l | sed -n "/alpaca/p"; ps ax -o pid=,comm= | head -25'
```

Exact **fresh broker GET-only** command (reads known env include without executing
it; writes receipt locally only; no broker mutation endpoint). This remains usable
in a new clone without the private helper scripts:

```bash
umask 077
mkdir -p .private/migration_checks
ssh -i ~/.ssh/by-bot -o BatchMode=yes -o StrictHostKeyChecking=yes root@64.226.73.119 \
  'timeout 90 /root/by-bot/.venv/bin/python -' > ".private/migration_checks/alpaca-$(date -u +%Y%m%dT%H%M%SZ).json" <<'PY'
import json, urllib.request, hashlib, subprocess
from pathlib import Path
from io import StringIO
from dotenv import dotenv_values
r=Path('/root/by-bot/runtime/alpaca_intended_live')
a=Path('/opt/bybot-research/alpaca-intended-live/app')
lines=(r/'profile.env').read_text().splitlines()
assert lines[0]=='source /root/by-bot/configs/alpaca_live_v38.env'
assert not any(l.startswith(('source ','. ')) for l in lines[1:])
env=dict(dotenv_values('/root/by-bot/configs/alpaca_live_v38.env'))
env.update(dict(dotenv_values(stream=StringIO('\n'.join(lines[1:])))))
assert env['ALPACA_BASE_URL'].rstrip('/')=='https://api.alpaca.markets'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise RuntimeError('redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
allowed={'/v2/account','/v2/clock','/v2/positions',
 '/v2/orders?status=open&limit=100&nested=true',
 '/v2/orders?status=all&after=2026-10-01T00%3A00%3A00Z&limit=100&nested=true'}
def get(path):
    assert path in allowed
    req=urllib.request.Request('https://api.alpaca.markets'+path,method='GET',headers={
     'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],
     'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
    with opener.open(req,timeout=15) as response: raw=response.read(3000001)
    assert len(raw)<=3000000
    return json.loads(raw)
b=json.loads((r/'binding.json').read_text());account=get('/v2/account')
assert account['id']==b['account_id']
orders=get('/v2/orders?status=open&limit=100&nested=true')
history=get('/v2/orders?status=all&after=2026-10-01T00%3A00%3A00Z&limit=100&nested=true')
assert len(orders)<100 and len(history)<100, 'pagination required; do not certify incomplete receipt'
manifest=(a/'source_manifest.json').read_bytes()
assert hashlib.sha256(manifest).hexdigest()=='73345c03fa823d82a2c330902624206d14123ed6269667774569ec5db1f0fbb2'
m=json.loads(manifest)
artifacts={}
for name in ['latest_intended_run.json','protective_exit/protective_exit_hwm.json',
 'protective_exit/protective_exit_latest.json','monthly_reentry_block.json']:
    p=r/name
    if p.exists():
        assert p.stat().st_size<2000000
        artifacts[name]=json.loads(p.read_text())
needles=('run_alpaca_live_v38_once.sh','run_alpaca_protective_exit_manager.sh',
 ' scripts/alpaca_protective_exit_manager.py','/root/by-bot/scripts/alpaca_protective_exit_manager.py')
print(json.dumps({'clock':get('/v2/clock'),'account_suffix':account['id'][-6:],
 'account_status':account['status'],'cash':account['cash'],
 'enabled':b['enabled'],'capital':b['capital_usd'],'gross':b['gross_exposure'],
 'positions':get('/v2/positions'),'open_orders':orders,'history':history,
 'hashes_match':all(hashlib.sha256((a/p).read_bytes()).hexdigest()==h for p,h in m.items()),
 'cron':[l for l in subprocess.check_output(['crontab','-l'],text=True).splitlines() if 'alpaca' in l],
 'old_processes':[l for l in subprocess.check_output(['ps','ax','-o','command='],text=True).splitlines()
                  if any(n in l for n in needles)],'artifacts':artifacts}))
PY
```

The time window above is the Oct1→Oct2 acceptance window; once >100 orders,
use an explicit bounded paginated GET by known stop IDs. Never silently truncate.
Compare broker stop IDs/statuses to the private prior snapshot before claiming re-arm.

Existing local helpers are preserved for cheap full evidence collection:

```bash
umask 077
ssh -i ~/.ssh/by-bot -o BatchMode=yes -o StrictHostKeyChecking=yes root@64.226.73.119 \
  'timeout 100 /root/by-bot/.venv/bin/python -' \
  < .private/migration_20261001/snapshot.py \
  > ".private/migration_checks/full-$(date -u +%Y%m%dT%H%M%SZ).json"
```

This helper queries Alpaca and copies bounded public ATT1 journals to a temporary
directory for read-only replay under **deployed** code. It does not alter real
journals or bypass implementation pins. Missing private helper is a restore-needed
artifact, not permission to reseed runtime. Cheap ATT1 heartbeat/log inspection:

```bash
ssh -i ~/.ssh/by-bot -o BatchMode=yes -o StrictHostKeyChecking=yes root@64.226.73.119 \
  'cat /opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260928-observation-timing/heartbeat.json; journalctl -u att1-lifecycle-zero-risk-v2.service -n 30 --no-pager; journalctl -u sbr1-zero-risk-shadow.service -n 20 --no-pager'
```

Do not display `.env`/`profile.env`, use `set -x`, execute a trading script to
"see what happens", or use the nonflat-incompatible initial preflight.

## 10. Evidence index

- `ALPACA_LIVE_LAUNCH_2026_10_01.json`: first actual3 fills/3 stops.
- `ALPACA_OWNER_PREFLIGHT_2026_10_01.json`: historical pre-entry flat verification.
- `ALPACA_OWNER_ACTIVATION_2026_09_30.md`: owner-only emergency/rollback procedures.
- `ATT1_NATIVE_SL_AND_RESIZE_2026_09_30.json`: code tests/manifest, historical VPS snapshot.
- `LTC_ID257_PROTECTION_STATUS_2026_10_01.json`: resolved final-qty discrepancy and limits.
- `MIGRATION_STATE_2026_10_01.json`: current snapshot summary/hashes, no credentials.
- `CONTINUATION_EVIDENCE_2026_10_01.json`:17:07 LIVE check, new ATT1 source timing/
  local reproduction, fresh SBR1 comparison blocker and registry reconciliation.
- Raw financial receipts: `.private/migration_20261001/{snapshot,ltc_truth,units}.json`,
  `.private/alpaca_activation_20261001/first_live_cycle.json`. Local only, ignored by Git.
- Latest raw snapshots and interim baseline: `.private/continuation_20261001/`.
  SBR1 fixed append-only prefix is in its `sbr1/` subdirectory. No private receipt
  is staged; the public JSON contains only a summary and hashes.
- Keep the canonical checkpoint's top synchronized with new operational facts;
  do not create competing truth documents or rewrite historical evidence.
