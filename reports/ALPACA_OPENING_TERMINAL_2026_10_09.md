# October9 Alpaca — exact opening result

**BLOCKED_EXECUTION_CURRENT_OPENING. No PAPER entry, no LIVE GO.**
[Pinned receipt](evidence/alpaca_opening_20261009/terminal_receipt.json).

The operator started at13:26:24UTC. Fresh opening sources at13:30:27–32 confirmed
LIVE flat/HALT/cash and nonmarginable496.12/pendingfees0, PAPER five unchanged
legacy positions/XOMflat/orders0.61/23/21 source pins and original copied/sealed
books matched. Fresh IEX raw timestamp13:30:01.90114532Z, receive13:30:32.117Z,
bid158.93/ask176.72; SIP403. IEX is not NBBO. No new spread threshold or rescan.
XOM active/fractionable; actual earnings query before planning returnedOct30;
existing concentration check passed against selected LIVE flat inventory.

## What was actually reached

One orders-OFF plan prepared13:33:57.216UTC from CRWD's deterministic inherited
lineage: XOM0.705636034, reference ask176.72, notional124.69999992848,
reference stop169.41/riskdistance7.31, modeled stoprisk5.15819940854.
CAT entry reserve.01 reduced source spendable cash496.12→496.11 before planner;
quantity≤source-bound ceiling and inherited notional/risk caps. This is a plan,
not an entry/fill/protected position or maximum guaranteed loss. Actual protection
would be fill-relative; no accepted stop exists.

Existing runner GET rehearsal returned PAPER_READ_ONLY_READY; receipt file
mtime13:34:57.580559512UTC. Final submit returned BLOCKED_DATA with
PAPER_DISPATCH_WINDOW_OR_CLOCK_EXPIRED; file mtime13:35:00.017581752UTC.
The branch is before persisted dispatch and POST. The compound predicate also
covers closed broker clock, >5s skew and excessive plan age; these branches
were not individually logged. Late operator orchestration is evidenced by the
timeline; do not claim uniquely measured clock root cause or a latency SLA.

Postcheck at13:37:51UTC: broker XOMabsent/orders0/entryCID404, PAPER store0intents,
sourcebook1reservedintent. LIVE remains flat/HALT/cash496.12/fees0; five legacy
PAPER holdings unchanged. Source61/23 pins unchanged, productionPIDs
1648585/1623208/1584802 and NRestarts0 unchanged at13:42:18UTC.
No entry, stop, partial, restart protection or DAY re-arm acceptance was proved.

## Source review and bounded correction

One runtime-verified6-astra/high review confirmed pre-POST rejection and the
money boundaries, and found operator-helper source limitations: owner closure
partly manual (cron sources archived, not automatically exhaustively evaluated),
protection eligibility assigned without dedicated mapping, fresh earnings/cost
companion outside initial archive hash, snapshot-specific cash/exit extraction.
Do not present the original input booleans as full automated broker truth.

Preserved the exact executed helper privately with hash247dda3a…6c8. Corrected
local helper now requires a distinct reviewed source companion *before* snapshot,
SSH or reservation; missing review blocks. Future source hash includes actual
fresh earnings, cost and operator review. Validator itself cannot authenticate
the broker or certify inventory completeness; protocol eligibility is explicitly
separate from actual stop acceptance. This is a local refusal/binding correction,
not a deployed source publisher or PAPER/LIVE PASS.

TDD:11 initial failures for missing guard; after implementation plus CLI refusal
regression,72 targeted tests PASS (guard/DynamicBook/PAPER adapter). No full-suite,
new strategy, financial-policy change, live patch or broker-lifecycle PASS claimed.

## Next action and DO NOT TOUCH

Prebuild and review source/plan/runner tooling before any next approved opening;
do not write it at13:34. Close all-writer and protection-eligibility source mappings
and companion binding before reservation. Preserve one expired never-dispatched
Oct9 plan; no deletion, repricing, resend, fabricated child fill or fresh-book
shortcut. A reviewed prospective handoff is needed before a different execution
session; Monday is not automatically authorized by this receipt. Any weekly
ranking refresh remains the actual frozen first-XNYS-session rule, not a reason
to pretend Oct9's plan is current.

Original two-check Oct8/9 heartbeat ends here and is deleted, not extended.
No Oct9 XOM position exists to re-arm Oct12. LIVE cap487.42/gross.70/HALT and
separate owner GO remain. ATT1/KITY/B3/ETS/Claude/sealed outcomes were not changed.
Foreign allowlist add587f1…f19a1 stays untouched and unstaged.
