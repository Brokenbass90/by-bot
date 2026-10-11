# October12 NET PAPER session — armed October11

Terminal engineering result: **ALPACA_NEXT_SESSION_ARMED**. At October11
15:37:46.544UTC / 18:37:46 Cyprus, authenticated broker and installed-process
readback passed. This is operational arming, not PAPER_EXECUTION_PASS or LIVE GO.
Canonical evidence is `reports/evidence/alpaca_net_arm_20261011/arming_receipt.json`.

The unchanged weekly selector uses all59 closed-FridayOctober9 histories and
chooses NET; the exact draft ranking remains
`3368b51d8a07465c9dcca6acf1ffd5ddc1831e12fd3332fd596d9d2ecea5a5fb`.
NET earningsOctober29, inherited reentry exclusions and concentration mapping
are retained. No old XOM ranking/plan is reused, no reservation made on Sunday.

## Installed and observed

The isolated reviewed81-file app is under
`/opt/bybot-research/alpaca-net-paper-session-20261012`. Exact proposal:
`dde67bfff6b028e091a091c5a14e335e04a36ad3ad010db6fc5a7c6758f3ccb3`.
Packet: `9ceda9395eda310bb32d1b05cb96c7be228945901a6574da359b36eb61d001dd`.
One independently runtime-verified `gpt-6-astra/high` review approved only this
PAPER install; two initial P1 findings and narrow packaging closures are retained.

| New unit | Actual PID | State | NRestarts |
|---|---:|---|---:|
| alpaca-net-paper-open-20261012.service |1979384|active/running|0|
| alpaca-net-paper-guard-20261012.service |1979385|active/running|0|

Both are static one-shot units with `Restart=no`; neither is enabled at boot.
Opening persisted STATIC_PREPARED at15:36:45.627UTC and READY_TO_DISPATCH
at15:36:45.656UTC on Sunday. All packet/static/manifest pins match actual files.
The guard is preloaded, accepts no BUY, and owns only the exact persisted NET
attempt. The user computer and an active Codex turn are not required at opening.
A VPS/process interruption is an explicit operational blocker, not a restart or
second attempt authorization.

NET was appended to the existing legacy PAPER exclusion under the original
shared lock. Before/after exclusion hashes and exact original backup are retained.
The five legacy holdings ABNB/ABT/AMZN/MA/SCHW remain outside this candidate.
Original book: one old intent, one explicit retirement, zero new attempts;
original five-table hash unchanged. Original broker PAPER store has zero intents.

LIVE is flat/HALT, cash/nonmarginable496.12, pending/accrued fees0. Known six
old fills/five posted fees still support old net+8.70 at broker cents; this is not
a new strategy verdict. Three original app manifests61/23/46, original root cron,
legacy wrappers, LIVE profiles/binding and production PIDs1648585/1623208/1584802
with NRestarts0 are unchanged. No broker write occurred on Sunday.

## Fixed execution schedule and remaining gate

MondayOctober12 opening is13:30–13:35UTC /16:30–16:35Cyprus. Static and READY
deadlines13:15/13:29UTC are already met. At opening the existing preloaded path
performs fresh authenticated account/asset/quote/raw timestamp/liability checks,
then seals the unchanged ranking, reserves at most one exact plan and invokes
the existing PAPER adapter once. No documentation/search/research/helper work
is performed in that window. Fresh stage30s, reservation5s, adapter preflight
allowance120s remain unchanged; accepted-entry protection is never aborted by
an opening timeout. Missing/conflicting sources fail closed; no resend/reprice.

Caps remain LIVE-derived487.42/gross0.70/maxpositions4/one new entry. The freed
CRWD lineage retains notional ceiling124.699999985736 and risk ceiling
10.906127324106. Exact NET quantity and fill-relative stop are determined only
from Monday-fresh inputs. The CAT reserve reduces spendable cash before sizing;
commission-free does not mean regulatory-fee-free. IEX is not NBBO and HTTP
receive time does not establish raw quote freshness.

Guard starts observing at13:30UTC, polling each second within the opening window
and each30s thereafter, serialized by the original account lock. Definitive first
stop422 persists rejection provenance and uses quantity-proven owned PAPER
unwind. A full/partial stop fill before protection readback preserves actual
STOP/MARKET sources and never invents full protection. Unknown stop dispatch
remains UNKNOWN_INITIAL_STOP_OWNER_ACTION_REQUIRED; no blind resend/offset.
Restart recovery reads exact IDs/state; it cannot create a second BUY.

If Monday entry is held overnight, the next actual DAY rearm is TuesdayOctober13,
not Monday. The scoped PAPER test unwind is no earlier than Tuesday13:35UTC /
16:35Cyprus; guard hard end14:00UTC /17:00Cyprus. Actual exit/finality or a hard
deadline blocker is retained. Pending-fee/net finality is not fabricated when
the guard terminates. No extra statistical PAPER days or schedule extension.

Remaining evidence is one actual broker lifecycle: entry, full native protection
and readback, persistent-state recovery, actual DAY rearm if overnight, owned exit,
cost/finality reconciliation. Only then prepare exact LIVE ticker/qty/risk/stop/
ownership/kill dossier. LIVE HALT cannot clear and no LIVE entry can occur without
separate owner GO. Synthetic tests and Sunday READY do not satisfy that gate.

## Readback and rollback

Read without restarting/preparing: new unit state, installed packet/manifest,
`runtime/opening/{prepared,ready,fresh,reserve,invoking_adapter,terminal}.json`,
`runtime/guard/{latest,terminal}.json`, original book and broker PAPER store.
The archived `read_armed_session.py` is specifically a pre-open verification;
after dispatch its zero-attempt assertions are no longer appropriate.

Before an entry, stop only the two new units if rollback is needed. Preserve
runtime/history. NET exclusion can be restored from the exact before-backup
only under the original shared lock after a fresh NET-flat/no-open-orders/no-
uncertain-dispatch proof and CAS of the current after hash. Do not clear LIVE HALT.

After an entry, preserve protection/management before stopping anything. Use
the existing scoped owned maintenance/unwind or this exact guard; never flatten
the account or adopt legacy positions. To use the existing maintenance CLI,
extract the exact `reserve.json.value`, verify its wrapper digest and unchanged
active source membership via `require_source_plan`, then use original plan-store,
PAPER profile/account/runtime with `--paper-maintain` (and explicitly
`--paper-submit --paper-unwind` only for the scoped PAPER unwind). Initial-stop
failure uses `recover_initial_paper`, not a fabricated accepted-stop ledger.
Unknown POST outcomes require source reconciliation or owner action, not resend.
Do not restart the opener: a second prepare would conflict with its durable
STATIC_PREPARED timestamp and cannot authorize another attempt.

## Verification and next crypto action

138 local targeted PASS and96 isolated VPS targeted PASS. Actual early staging
had90PASS/6FAIL from one absent unchanged protocol test fixture; its log is retained
alongside the completed log. An earlier spool-file versus `crontab -l` hash mismatch
failed before mutation; both unchanged byte sources and its correction are retained.
Neither failure is concealed or attributed to strategy outcomes. Historical full
suite remains NOT_GREEN and was not rerun. Foreign allowlist diff is untouched.

Claude source handoff is
`reports/BOUNCE_CLAUDE_SOURCE_HANDOFF_2026_10_11.md`, with14 independently verified
referenced hashes. BTC/ETH baseline/H1/H4/funding archives are packaged. Funding
treatment, rawM5/PIT provenance and admissible independent validation remain
Claude declarations before baseline-versus-context prereg. No outcomes, context
thresholds or judge were consumed. Breakout original M5 recovery remains separate;
no ATT1/KITY rescue, new family, broad architecture or Claude message was performed.
