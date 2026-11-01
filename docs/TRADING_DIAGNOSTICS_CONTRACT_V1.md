# Trading diagnostics contract V1 — draft, 1 November 2026

Status DRAFT / PARTIAL_PUMP4_IMPLEMENTATION. Reuses existing Decision Bus,
source receipts, selected supervisor and account-owner journals. No new engine,
financial authority, risk policy or research eligibility is created by this file.

## Fields and meanings

Every claimed complete trace needs strategy/version/frozen policy SHA, decision ID,
source cutoff/available/actual observed/durable witness times, immutable input
hashes, source coverage and unavailable instrument set, eligibility result/reason,
fresh account source time/risk admission result/reason, request/ack/fill/native
protection state and costs/finality. Missing evidence is UNKNOWN, never zero.
Wall timestamps in producer JSON are not independent durable witnesses.

| Stage | Existing proof | Meaning of failure/absence |
|---|---|---|
| DATA_FRESHNESS | Pinned input, monotonic closed cursor, available/observed clocks | SOURCE_UNKNOWN; no forced refresh/backdating |
| COVERAGE | Frozen census + exact current index/original observation pairs | Partial expected prefix is PENDING; failed/deadline-missed complete source blocks entries |
| SIGNAL_ELIGIBILITY | Frozen source pins, causal journal+fresh HTTPS, cooldown/window | STRATEGY_REJECTED only for a completed check; source inability remains UNKNOWN |
| RISK_ADMISSION | Original single lease, exact GO/window/caps, fresh account/filters/fees/risk state | RISK_REJECTED with explicit reason, or UNKNOWN if evidence is missing |
| EXECUTION_STATUS | Durable request-before-send, ack/fills/reconciliation/native stop | EXECUTION_BLOCKED/UNKNOWN differs from no signal; custody runs before new input |
| COSTS | Owned fills/fees/funding and completeness/reserve policy | Empty transaction log is not terminal cost finality or next-entry release |

NO_SIGNAL requires a completed source/strategy scan; a raw strategy signal does not
prove account eligibility or execution. Aggregate views preserve original receipt
status and reason; no rewriting immutable past receipts into new statuses.

## Actual PUMP4 subset and remaining work

Current candidate implements WAITING_H1_PUBLICATION_PREFIX,
WAITING_H1_CENSUS_FINALIZATION, ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED and source
BLOCKED reasons through existing supervisor. It is UNSELECTED; generic NO_SIGNAL /
RISK_REJECTED normalization across every module is NOT_IMPLEMENTED.

The real14UTC closed-hour source proof is source-only. Five past raw positives
do not have historical account/quotes/HTTPS admission proof. Do not fabricate a
complete financial trace by replaying them against today's account or outcomes.
Next eligible current signal must leave a trace BEFORE the outcome; ORDERS_OFF
can report hypothetical admission but cannot claim a fill or extend scope.

Second mechanism: LIQ SHADOW compatibility remains NOT_TESTED. Read the published
frozen source/eligibility contract; adapt existing evidence fields only. No judge,
new outcomes, epoch reset, research change or claim of economic PASS is authorized.

## Acceptance

PUMP4 source/freshness/coverage and bounded archive tests are delivered. Single
current signal→risk trace, accepted financial handoff, second-mechanism SHADOW
adapter and broader operational longevity tests remain separate evidence gates.
Only expand test coverage for confirmed defects or changed paths; preserve
existing restart/send-once/journal-failure tests rather than duplicate suites.
The canonical priority queue remains ROADMAP_SELF_IMPROVING.md.
