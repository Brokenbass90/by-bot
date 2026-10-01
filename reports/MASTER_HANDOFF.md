# MASTER HANDOFF — 2026-10-01

Canonical migration entry point. Latest production snapshot
**2026-10-01 17:07 UTC / 20:07 Cyprus**; ATT1 engineering18:13UTC;
original migration snapshot14:18UTC. No new Alpaca broker read in engineering cycle.
runtime facts must be refreshed, never inferred from this document's age.
Read this document, then `NEW_CHAT_START_HERE.md`, then only the relevant section
at the TOP of `CODEX_SESSION_CHECKPOINT_2026_09_06.md`. Older sections are history.

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
- No trading code, service, risk, cron or strategy changes in the migration turn.

## 2. Alpaca LIVE — actually operating

Owner activation backup: `/root/by-bot/runtime/alpaca_intended_live/owner_activation_20261001T140549Z`.
Endpoint `https://api.alpaca.markets`; bound account suffix **f295c6**; currency USD.
Capital cap **$487.42**, frozen gross **0.70**, max positions4, max individual weight0.60.
Three picks are legitimate; do not force a fourth. Entry notional **$341.149999263748**.
The cap is allocated capital, not a guaranteed maximum loss. Stops do not eliminate gap/slippage risk.

Frozen signal session Sep30 → entry session Oct1. Selection CRWD/AMD/META prepared
Sep30 20:12 UTC. First actual scheduled LIVE cycle Oct1 14:10 UTC; bridge0/ratchet0.
Latest checked maintenance receipt **17:05:05 UTC**, `LIVE_CYCLE_COMPLETE`, owned names all3.

| Symbol | Actual qty | Broker avg entry | Accepted DAY stop / durable floor | Durable HWM at snapshot |
|---|---:|---:|---:|---:|
| AMD | 0.186377282 | 609.57 | 560.90 | 612.37 |
| CRWD | 0.469970151 | 265.336 | 242.13 | 266.57 |
| META | 0.141939508 | 724.534 | 668.76 | 729.8101 |

All three original buys filled. Three open sell stops have broker status `new`,
TIF `day`, exact held quantities. Entry/stop order IDs match durable ownership state.
Raw IDs are in private broker receipts and durable state; no account credentials in Git.
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

VPS services/timers freshly observed:

- `bybot.service` OLD crypto LIVE running/enabled, PID492970; `att1-lifecycle-zero-risk-v2.service`
  running/enabled, PID492814. Both NRestarts0 **since their current starts Sep30 06:17 UTC**.
  This is not zero lifetime restarts; actor/reason of those starts not audited here.
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

## 4. Mandatory operational check — October 2

Broker clock observed Oct1: next close **Oct1 20:00 UTC /23:00 Cyprus**;
next open **Oct2 13:30 UTC /16:30 Cyprus**. Verify broker clock/calendar again.
These dates are broker-backed snapshot facts; later DST/calendar changes must not be hardcoded.

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

## 5. ATT1 fresh prospective state and next gate

Epoch `att1-public-lifecycle-20260928-observation-timing`, runtime
`/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260928-observation-timing`.
At Oct1 17:07 UTC: **9 sessions; 8 filled simulations; 1 nonfill; 0 clean filled terminal**.
All8 filled simulations flat and dirty:1000RATS/BCH/JTO/ACE/GALA/AVAX/DOGE/PAXG.
**8 RECOVERY_GAP total**. New AVAX2094ms/DOGE2602ms gaps span sequential
management of two held books; no recorded individual book request crossed2s.
Disposable local reproduction confirms aggregate serial budget can fail with two
fresh books at1100ms/request. The subsequently tested candidate fixes that
reproducer; it is not deployed evidence. New PAXG gap
is an actually stale book2643ms; scheduling cannot alone certify stale sources.
**71 H1 cycles, each51/51 unique symbols; duplicate journal event IDs0**.
Missing external transitions remain NOT_PROVEN because gaps occurred. Current
driver/core/strategy pins unchanged. Full source evidence is preserved privately;
`CONTINUATION_EVIDENCE_2026_10_01.json` carries counts and timing receipts.

Oct1 18:13 engineering result: adjacent-pair public observations, drained before
ordered management; pending exits/protection are never bypassed, fresh exit IOC
cannot compete with observation workers. Hard2s/freshness and single writer remain.
54 targeted tests PASS on current local core, captured deployed core and VPS;
old9 sessions/113 records replay identically. Only driver is overlaid on the actual
deployed closure. Do not deploy local newer coordinator over those journal pins.
Public service/source/PID remain unchanged; clean prospective terminals still0.
Release/preflight/file rollback ready, **not deployed; live rollback not tested**.
Use `ATT1_AGGREGATE_BUDGET_CANDIDATE_2026_10_01.json` for exact hashes, private
archive, fresh epoch and bounded cutover/rollback gates. Refresh public flat/pins
before cutover; retire old evidence intact. Alpaca Oct2 re-arm remains first.

NEW authenticated binding native SL→fees/funding→finality code complete **orders OFF**,
commit834990d, 346 local +346 isolated VPS tests, 42 candidate hashes. Not installed
over production; fixtures are not prospective broker executions. Existing journal
implementation pins must not be rewritten to accept changed coordinator code.

Next gate: existing **2–3 clean prospective filled terminals with terminal net-R**.
Localize any new gap from actual source timing, preserve2s gate and dirty evidence.
Then fresh exact OLD absolute risk → exclusive handoff/canary dossier → owner action.
OLD risk_multiplier0.10 is NOT itself absolute per-trade USD risk; refresh actual
effective sizing/breaker/rounding before a monetary comparison. No NEW crypto activation.
OLD's local trendline short need not align with a broad-market uptrend; trend_guard0
is a frozen default. Broker entry qty/price checks passed, full historical PIT parity
was not proven by Codex. Claude reports parityPASS; preserve that attribution distinction.

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
- OLD ATT1 LIVE configuration/risk/positions; NEW order submission remains OFF.
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
results; no Factory rewrite or Alpaca expansion. Owner FX Raw/ECN MT5 demo is
the external cost-data step for NOCHNOY_DREYF, not accepted production net edge.
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
Actual checkout observed branch **codex/dynamic-symbol-filters**, HEAD
`76fc63ccbe43197e24452e3e4e28ae79a719e4ef`. Old handoff says research/fabrika-v1:
**branch mismatch — verify before any push/merge, do not use old command blindly**.
Read only these entry points before bounded reconciliation:

- `research_lab/HANDOFF_CLAUDE_2026_09_30-1.md` and `HANDOFF_CLAUDE_2026_09_30.md`.
- `research_lab/STRATEGY_MASTER.md`, `research_lab/data/reestr.json` (existing registry).
- `research_lab/pakety/PROMOTION_PACKET_ALPACA_INTENDED.md` (frozen packet).
- `research_lab/CODEX_ATT1_ONE_SESSION_HANDOFF_2026_09_30.md` is superseded for native-SL wiring.

Claude handoff reports Factory acceptance-guard defects and exhausted O1/O2 windows;
daemon stopped, equities BLOCKED_DATA on survivorship/universe, not merely two tickers.
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
