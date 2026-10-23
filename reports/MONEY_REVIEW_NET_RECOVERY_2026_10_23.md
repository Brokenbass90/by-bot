# NET safety / PUMP4 review closure — 23 October 2026

**LATEST: R4 SELECTED after exact owner approval; personal command NOT EXECUTED.**
Original NET personal launcher remains **TECHNICAL HOLD / SUPERSEDED**.
PUMP4 remains **TINY_BLOCKED**, Monthly remains ORDERS_OFF.
Owner's current execution order: **Alpaca → PUMP4 → Polymarket → KITY**.
No financial command, broker write, unit change or Monthly activation occurred.

## Owner decision and actual selection — 23Oct11:48UTC

Owner explicitly answered «Да, установить R4 и выдать замену личной команды».
The sole approved NET spec-path substitution was applied under the unchanged
account lock, inode813893. All64 new manifest pins match;9 old financial pins,
4 unit files and98 observer checks remain unchanged. No GOfile, personal claim,
exit dispatch or financial command was created/executed.
[Owner approval](evidence/money_review_20261023/net-r4-owner-approval.json),
[selection](evidence/money_review_20261023/net-r4-selection.json),
[independent readback](evidence/money_review_20261023/net-r4-selected-readback.json).

New human-only launcher, issued0700 and **never executed by the agent**:
`.private/claude_review_intake_20261023/net-recovery-r4/owner-net-exit-once.sh`.
SHA:`27c038ad91815e4669ee7ae3844498d96f5e3ec98dbe919d3c4b08acbeaa9bde`.
Only23Oct17:00–17:05Cyprus /14:00–14:05UTC, exactly once. Its early invocation
refuses before claim/SSH; uncertain output consumes initiation and needs GET
reconciliation, never a retry. The old rev2 command must not be used.
Actual11:49:49UTC broker GET: original NET0.325167779 still open, market closed,
no accepted open DAY-stop; quote307.15/PnL−1.324084 is a dated premarket snapshot.
SHOP remains absent and disabled/inactive. Today's13:30UTC opening stop readback
is still PENDING, not implied by this installation.
[Post-selection GET](evidence/money_review_20261023/net-after-selection-get.json).
After the human's sale command: independent flat/terminal/cost/cash proof, then
separate old-manager retirement/Monthly authority; no automatic Monthly BUY.
The sections below preserve the completed engineering and pre-approval review.

## DONE / TESTED

199 tests locally and the **same 199 on VPS**, no failures/errors/skips;
89 exact packaged files,43 imports,0 checkout fallbacks. Sockets denied locally,
VPS additionally used `unshare --net`. Material:
`8213d6053961593ab66670c7134a80f3c1c1314f405a2895aaf4b78183d6894f`.
[Receipt](evidence/money_review_20261023/receipt.json),
[local](evidence/money_review_20261023/local-acceptance.json),
[VPS](evidence/money_review_20261023/vps-acceptance.json),
[independent VPS readback](evidence/money_review_20261023/vps-readback.json).
An earlier isolated bundle lacked an existing policy fixture and failed at fixture
setup. The final manifest includes it; no financial logic was changed to hide that failure.
Monthly's previously accepted53 source hashes remain identical; its241 financial
tests were not rerun or added to this count. The9 old financial pins, original
packet, selected manager and foreign allowlist remain unchanged.

**NET:** Four fault probes against the exact deployed overlay reproduced the
missing residual protection after rejected/unknown/active-partial market exits.
The original personal helper also imports a publisher absent from its VPS app.
These are confirmed defects, not a reason to re-approve the same sale blindly.
[Deployed fault evidence](evidence/money_review_20261023/deployed-net-fault-probes.json).

The unselected repair retains the existing actor, account lock, ownership,
floor/HWM, original market CID and dispatch barrier. A durable recovery hold stops
future manager/kill cycles from cancelling a restored stop or resending the sale.
Only exact terminal owned-market truth plus fresh remaining quantity/no competing
order permits stop restoration. Unknown/active market truth remains BLOCKED with
owner action, because a competing stop could oversell. Generic HTTP422 is not
proof of no acceptance. DAY expiry/partial stop fill, late lookups, lost stop ACK
and a new-interpreter restart are covered. The native stop never lowers the floor.
The cancel-to-market interval still carries execution risk; this is not a guarantee.

The replacement helper embeds the existing source-pinned create-exclusive
publisher instead of importing the missing module. Its financial functions match
the old helper AST except for removing that import. The manifest pins all56 spec
static files,64 total dependencies, before personal execution.

**PUMP4:** Nonzero/malformed Bybit ACKs now remain reconciliation-only behind
the existing persistent send barrier. Added rejected-entry, rate-limit, rejected
TP1/TP2 and reduce/stop-race cases. No blind resend, phantom fill or entry reset.
An accepted create-order ACK is asynchronous, not proof of execution.
[Bybit create-order](https://bybit-exchange.github.io/docs/v5/order/create-order),
[error codes](https://bybit-exchange.github.io/docs/v5/error).
Two bounded independent reviewers used verified `gpt-6-astra/high`; confirmed
findings were reproduced and fixed. No remaining P1/P2 in their reviewed scope.
[Review evidence and limits](evidence/money_review_20261023/review.json).

## Claude review dispositions

Review `17eded0` predates `d2bd4e4`, `f5a517f`, `fc46bdf`; it was verified as an
ancestor of observed research origin`d8706ac`. No research merge or judge was run.

| Item | Disposition against current code |
|---|---|
| P1-1 hardcoded NET date | NOT_APPLICABLE today: exact approved23Oct window; unchanged |
| P1-2 exit failure protection | FIXED in unselected R4; OPEN in selected old runtime, launcher HOLD |
| P1-3 PUMP40/60 and168H | FIXED by existing lifecycle/tests; actual market execution versus research prices still OPEN |
| P1-4 Bybit errors/races | FIXED by checked ACK + persistent no-resend/error scenarios |
| P1-5 actual GET/history | COMPONENT FIXED in`f5a517f`; financial-owner integration OPEN |
| P1-6 fake quantity fixture | Actual sizing diagnostic exists; executable risk/cost admission OPEN |
| P1-7 one-way | Actual hedge exposure rejected; flat empty list cannot prove symbol configuration, readiness OPEN |
| P2-1 bare helper CLI import | Actual control loader sets the pinned app root; missing publisher separately fixed in R4 |
| P2-2/3 helper closure/KITY import | Confirmed missing VPS file; embedded pinned publisher + full manifest closure in R4 |
| P2-4 consumed personal claim | Intentional no-retry barrier; failed/unknown command needs GET reconciliation, no fallback GO |
| P2-5 NET fault tests | FIXED: exact deployed probes +33 candidate regressions |
| P2-6 restart | FIXED in lifecycle and actual new-interpreter tests; deployment not implied |
| P2-7 real costs | Actual fee/funding GET captured; financial finality/admission remains OPEN |

## Exact NET replacement decision

Original sale GO remains recorded:23Oct17:00–17:05Cyprus /14:00–14:05UTC,
actual original remainder≤0.325167779, market exit regardless PnL. **Do not run
the old `.private/monthly_early_exit_20261022/rev2/owner-net-early-exit-once.sh`.**
R3 was superseded during bootstrap inspection; it was never selected or released.

R4 manifest SHA:
`2839e305a8b1a026b943ee4aca52c3847f9855fd4649853545b0cdae0ba0a382`.
Runtime SHA:`d5377514c8730690cd3750252e917c31562f4f824f0f7aa194dfe038cd945746`.
Candidate remote directory:
`/opt/bybot-research/alpaca-dynamic-live-20261013/repairs/net-exit-recovery-20261023-r4`.
[Selection envelope](evidence/money_review_20261023/net-r4-owner-review.json),
[exact manager diff](evidence/money_review_20261023/net-manager.diff),
[structural check](evidence/money_review_20261023/net-r4-structural-review.json).

Required new confirmation covers **only** selecting this recovery source by
replacing the NET `--spec` path in the existing manager-wrapper and issuing the
replacement source-pinned personal packet. Units, timer, original custody,
quantity, sale window, floor, SHOP cancellation and Monthly authority stay fixed.
It does not repeat or enlarge the sale GO. AGENTS requires separate confirmation
for existing money positions; owner also required preserving the signed packet.
Before selection: fresh source/claim/dispatch/custody checks and broker GET;
after selection: independent readback. Agent never invokes the personal launcher.
Rollback to unsafe runtime is allowed only before any exit dispatch/recovery hold;
afterwards preserve custody and reconcile, never resurrect the unsafe unwind.
If approval/window is missed: no shifted date or automatic retry.

Last broker GET11:22UTC: original NET0.325167779 open, quoted308/PnL−1.047691,
market closed, no accepted open stop. This is a dated premarket observation.
Today's opening13:30UTC requires a fresh accepted DAY-stop receipt; no claim of
protection is made before that evidence. SHOP timer remains disabled/inactive.

## REMAINING / next gate

1. Alpaca: exact recovery-selection decision → actual personal exit → independent
   flat/terminal-order/cost/cash proof → separately authorized old-manager retirement
   and Monthly activation. Future frozen source/account gates remain; no automatic BUY.
2. PUMP4: existing account-wide owner/send-once integration, durable day/week/DD
   latches and source-bound fee/funding/risk admission.50/30/R1/max1 proposals are
   not authority. Full40/60/native-stop economics versus research fills needs
   an explicit execution contract, not silently replacing market exits with limits.
3. Polymarket: existing tests/data/prereg acceptance after PUMP4; no new framework.
4. KITY: local research`4c3b69a` reports DOSIE_READY/C1/C2 PASS; not contained in
   observed origin`d8706ac`. Dossier's800/8-leg template conflicts with its corrected
   path document300/10-leg; latter is not financial authority. Funding C1.7/weekly
   executor remain; old micro GO spent. No new weekly LIVE GO.

Status delta for Claude: NET repair component passed but selection awaits owner;
PUMP ACK/error component passed, TINY blocked by financial owner/admission;
Monthly241 unchanged, terminal handoff pending. No message sent to Claude.
