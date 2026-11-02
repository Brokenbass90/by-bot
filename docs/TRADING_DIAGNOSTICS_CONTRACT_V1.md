# Trading diagnostics contract V1 — draft, 1 November 2026

Status DRAFT / PARTIAL_PUMP4_IMPLEMENTATION; updated2November2026. Reuses existing Decision Bus,
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
BLOCKED reasons through existing supervisor. That194-file repaired source was
selected1November under the separate one-entry owner GO; generic NO_SIGNAL /
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
current signal→risk trace, second-mechanism SHADOW adapter and broader operational
longevity tests remain separate evidence gates. One-entry financial handoff was
accepted1November; serial TINY-2 handoff remains unperformed.
Only expand test coverage for confirmed defects or changed paths; preserve
existing restart/send-once/journal-failure tests rather than duplicate suites.
The canonical priority queue remains ROADMAP_SELF_IMPROVING.md.


## Minimal causal Brain pair — integration contract, 2 November

Documentation contract only; no new producer, judge, policy or LIVE integration.
Reuse existing Decision Bus/opportunity IDs, durable journals and future-outcome
join. Claude owns research advice/eligibility and preregistered comparisons;
Codex validates execution-time provenance. Historical records are not repaired.

One comparison unit is one **actual distinct eligible opportunity**, never a timer
heartbeat, repeated daily advice or a NO_NEW_SIGNAL receipt. Preserve rejected,
missed and unknown opportunities in denominator/quality counts separately.

| Required immutable field group | Meaning |
|---|---|
| Identity | opportunity_id, strategy/source version and frozen-policy SHA, instrument/side, signal ID/bar, epoch and input hashes |
| Availability | signal_observed_ms, max_input_available_ms, actual local observed_ms, independently witnessed durable decision time; unknown timestamps stay UNKNOWN |
| Execution contract | Source-pinned entry_deadline_ms and shared comparison_cutoff_ms, execution/position/exit/cost policy hashes; deadlines are never invented by the advisor |
| Baseline | Frozen action and size/risk policy, decision time, exact version/hash; same opportunity, data and capital/risk constraints as the Brain arm |
| Brain arm | Policy/model version and SHA, input features/hash, action/reason, compute and durable-publication timestamps |
| Future join | opportunity/decision hashes, predeclared outcome horizon, actual future source bytes/timestamps, fees/funding/spread/slippage and finality/reserve status for each arm |

A timely trading comparison requires both decisions durably available strictly
before `min(entry_deadline_ms, comparison_cutoff_ms)` and before their outcome
becomes available. `max_input_available_ms` cannot exceed that cutoff. For PUMP4,
use the real source-bound ≤60-second entry gate, not an hour after the signal.
A producer timestamp written before fsync is not independent proof of durable
availability. Without a witness, timeliness is UNKNOWN, not retroactively PASS.
Advice arriving later is LEARNING_ONLY and excluded from actionable comparison;
advice after known outcome is retrospective even if within the nominal hour.
Using advice to claim improvement of a particular LIVE decision additionally
requires it was available before that actual decision, not merely before deadline.

Before the future horizon closes, join status is PENDING_OUTCOME. Afterward, use
the original decision prefix and future capture; never select the favorable
horizon or backfill advice. Compare **paired net after expenses**, including
no-trade actions, under the same predefined execution assumptions. A hypothetical
counterfactual is separately labelled; market return is not strategy PnL. Missing
cost/liquidity evidence is UNKNOWN or explicitly bounded by a pinned accepted
policy; absence of fees is not zero. Never silently discard losses or missing
arms, combine model PnL with actual fills, or attribute a baseline gain to Brain.

Required output: unique opportunities, timely/late/unknown pairs and exclusions;
per-arm net/cost status and paired delta; pending horizons; actual vs hypothetical
execution. First15 outcomes are diagnostic only. An economic PASS needs Claude's
preregistered independent-sample/cost criteria; this contract grants no such PASS,
new money authority, automatic retraining or promotion.
