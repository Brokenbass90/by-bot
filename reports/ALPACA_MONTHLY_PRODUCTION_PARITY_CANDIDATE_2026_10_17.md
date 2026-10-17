# Alpaca monthly production-binding candidate — October17

UPDATE: independent Claude review507f782 accepts d205f8f with
`ALPACA_STRATEGY_PARITY_PASS`. Financial activation remains separate. Read
[accepted review and current DAY work](ALPACA_PARITY_ACCEPTED_DAY_NEXT_2026_10_17.md).

Continuation supersedes the source version below:
[sizing closeout and serializer correction/V3](ALPACA_MONTHLY_SIZING_CLOSEOUT_2026_10_17.md).
Claude7800b72 accepted logic; sizing now64/64PASS. V2 stays immutable/disabled
and must not be activated as the final candidate; new wire delta review pending.

CURRENT: **ALPACA_MONTHLY_PRODUCTION_PARITY_CANDIDATE**, orders-OFF.
This is **not ALPACA_STRATEGY_PARITY_PASS and not LIVE activation**.
Owner chose monthly selection + daily ratchet. Independent Claude review remains
pending; clearing entry HALT requires a separate owner decision after review.

The interrupted work was preserved and completed as a versioned durable book,
closed-session source adapter and binding to the existing native execution
primitives. The 64-trade baseline simulator was **not rerun** in this continuation.
No research parameters, current NET policy, stop, manager, credentials or services
were changed. No broker HTTP request/order was made by this continuation.

## Reference and identity

Reference remains research981b62f / recovery2e68b1f, engine
`simulate_live_protection_daily_proxy`, selector `v38_successor_gated`, explicit
entry-fill anchor, published core **2347a7ec606cd845**. The previous independent
64-trade reproduction remains the reference; this work does not create new
strategy evidence.

New path-independent identity:
`ALPACA_MONTHLY_BASELINE_7bf7cf6ae049345b13c80fb01f0f2bcb30ffc376ce10d875fc38df183be49ccc`.
It hashes relative code names/bytes, explicit contract, frozen config/universe
and reference core, without an absolute local path.
[Exact identity and physical source manifest](evidence/alpaca_monthly_binding_20261017/strategy_identity.json).

## Bound behavior

| Requirement | Implemented and checked |
|---|---|
| Selection | Frozen selector/SPY200 gate at month end; immediate next-session window only. Off-cycle/missed entry returns `STALE_SIGNAL_RESELECT_FAIL`; no ticker substitution or vacancy replacement. |
| Source | Same pinned unadjusted/RTH hourly loader and daily aggregator. Actual calendar normalization handles NY DST/half-days. Full expected hourly coverage required; unfinished current day excluded. |
| Initial stop | Raw signal-session ATR20 and actual fill, exact downward reference grid/fallback; a different tighter stop is also a parity conflict. New monthly picks contain ATR20, no old absolute `stop_price`. |
| Provenance | Sealed causal-history/calendar/source hashes; signal/intended sessions, quote CTS/source/hash and raw ATR retained in durable entry intent before native POST. |
| Daily ratchet | HWM from completed closes only; original activation/trail/lock/market ceiling, no formula retuning. Raised stop effective next session. Five-minute health ticks cannot create an intraday ratchet. |
| Restart/ACK | SQLite FULL transactions and original native journal; pending stop intent remains until exact broker readback. Separate logical target and broker-accepted floor. |
| Unknown send | Persist before dispatch; no repeat after uncertain entry, initial stop, re-arm, replacement or monthly exit. Exact CID/readback resolves a known accepted request. |
| Protection/exit | Existing native full-stop checks and journaled scoped unwind reused. Full/partial stop readback, gap below floor, definitive protection rejection and two-journal exit recovery covered with fake transport. No new unscoped flatten route. |
| Rotation | Retain selected owned names without rebuy/HWM reset; settle stale owned exits before new admission. Crash after native retirement is reconciled before book admission. |
| Cooldown | Protective exits block for21 calendar dates, matching baseline; monthly rotation does not invent a stop cooldown. |
| Authority | Default OFF, explicit original account-lock and entry-HALT paths; old native account/approval guard remains. Source CLI has no apply/GO flag or credential loader. |

Implementation: `research_lab/alpaca_monthly_binding_v1.py`,
`research_lab/alpaca_monthly_native_binding_v1.py`,
`research_lab/alpaca_completed_session_source_v1.py`, and
`scripts/run_alpaca_monthly_binding_v1.py`.
Native bridge changes are optional monthly-tagged seams; old sealed callers
and the installed current NET kit retain their existing bytes/behavior.

## Actual source and replay

The previously captured real hourly source completed October16 17:57UTC yields
completed **October15**, deliberately excluding the then-incomplete October16.
Its raw/source hashes are retained; no new capture/poll was done for a better
result. It was not adopted into the current NET ledger.
[Actual source proof](evidence/alpaca_monthly_binding_20261017/actual_closed_source_oct16.json).

`scripts/replay_alpaca_monthly_binding_v1.py` consumes the already sealed
reference trade/decision files and the same59-file source. It does not invoke
the baseline simulator or an outcome judge. It exercises the durable book,
state acknowledgements and repeated reopening:

| Comparison | Result |
|---|---|
| Monthly selections |24 exact|
| Initial stops |66 exact|
| Completed held-position daily closes |637|
| Next-session stop acknowledgements |152|
| Protective exits |56 exact|
| Monthly rotations |8 exact|
| Retained positions / cooldown decisions |2 /24|
| Restart/state comparisons |486|
| Closed-trade core fields |64/64 match archived core within1e-9|

Limits: archived entry quantities are exogenous broker-like inputs, **not** an
independent reconstruction of portfolio sizing/accounting. Two final surviving
names have no next calendar row in the supplied source: their future stop is
not fabricated. Replay intraday times are fixtures over recorded session labels,
not an official historical exchange calendar. DST/half-day source semantics and
actual native entry/protection/unwind paths are tested separately. This is an
engineering parity candidate, not proof of exact future broker fills/PnL.
[Final durable replay with exact code/input hashes](evidence/alpaca_monthly_binding_20261017/durable_book_replay.json).

## Verification and remaining red suite

**375 targeted PASS** on final source, covering the candidate and existing
Dynamic/native/owned-manager/first-intent safety tests.
Full suite: **5257 PASS /60 FAIL**, zero additional failure names against the
retained60-failure baseline. The full-suite snapshot preceded only the mandatory
original-HALT constructor argument; final targeted tests and the installed-file
verification cover that final source change.

An earlier run found4 additional failures from obsolete fixtures: stale ranking
reuse and missing signal/ATR metadata. They were corrected without weakening
the source TTL: the old off-cycle success test now proves that even exact GO
cannot dispatch an expired weekly ranking. Scheduled fresh-ranking/read-only
retirement coverage remains. Those3 modules pass23tests.

The remaining60 are **not fixed, deleted, waived into PASS or claimed harmless**.
Inventory:44 ATT1/SBR1/host-runtime,3 Alpaca research materialization/historical
receipts,1 Brain source-pin,12 other research/Factory/environment. Their causes
were not all re-diagnosed in this money-path P0. No failing test is in the
375-test monthly/native critical-path set. A future relevant material failure
must still block activation; the global suite remains red.
[Complete names/disposition](evidence/alpaca_monthly_binding_20261017/legacy_failure_classification.json),
[verification](evidence/alpaca_monthly_binding_20261017/verification.json).

## Disabled physical package

Installed **October17 05:21:48.278UTC** into a new directory:
`/opt/bybot-research/alpaca-monthly-baseline-20261016/source-binding-v2/app`.
32 physical source files; spec SHA
`ca4b48681ab76ba19ffba7177a319ef740ff82b1abc5e5bff1a04b1babe5f6b5`.
VPS verifier returned `MONTHLY_SOURCE_PACKAGE_VERIFIED_ORDERS_OFF`.
All59 protected NET/source/unit/HALT pins matched before and after installation.
No broker request, systemd/cron/profile change, service registration/start or
financial activation occurred. Source-binding-v1 remains unchanged historical
source-only installation.
[Deployed receipt](evidence/alpaca_monthly_binding_20261017/deployed_receipt.json).

`monetary_transport_bound=false` is deliberate physical authority state:
the candidate contains the source→native binding methods, but no credentialed
monthly sender/manager is activated or owner-permitted. A disabled source
verifier is not evidence of a running money daemon. Review/owner activation must
not be inferred from installation or green unit tests.

## Removing old ambiguity

The entry registry designates only the monthly/daily contract for future entries;
weekly Dynamic is quarantined from that authority. Current NET remains under its
separately restored old manager and stays off-protocol for baseline edge evidence.
No automatic migration, lowering277.69, HWM reset or rollback to broken code.
[Version/authority registry](evidence/alpaca_monthly_binding_20261017/strategy_entry_registry.json).

Legacy `stop_price` fields and the old engine's `signal_close` default are retained
for immutable reference/old consumers; they are not used by the new monthly
stop path. Changing those frozen files now would destroy the established pins.
Unused old research may later be moved only after dependency inventory; Claude's
checkout was not edited by Codex.

**GTC is not a valid repair for current fractional NET.** Alpaca documents fractional
stop/market/limit orders with DAY TIF. The current0.325167779 position therefore
needs native DAY re-arm; whole-share GTC requires a different authorized quantity,
which this task does not permit. No test order was used to probe TIF.
[Official fractional-order contract](https://docs.alpaca.markets/us/docs/fractional-trading).

## Exact next steps / independent review

1. Claude reads this candidate, exact diffs/manifest, durable replay and tests;
   verifies selection, raw ATR/actual-fill stop, daily close HWM/next-session
   effect, rotation/cooldown and the stated replay limits against981b62f/2e68b1f.
2. Only after that independent review may the strategy receive
   `ALPACA_STRATEGY_PARITY_PASS`. No fresh independent signoff is claimed here;
   the existing root-only/reviewer-bucket restriction was respected.
3. Before any financial activation, bind the original shared lock/HALT/account,
   full latest closed-universe source, actual exchange calendar, fresh quote CTS,
   account/asset/cash/liability/caps and exact owner authority. Keep current NET's
   manager separate. No new PAPER/statistical waiting is introduced.
4. Entry-HALT release/any monetary sender activation is a separate owner decision.
   Missed monthly windows cannot be transferred to an arbitrary later day.

Then continue KITY batch/private-WS orders-OFF, then Elder HEDGE orders-OFF.
Old KITY9051 policy expired October16 21UTC; no replay, date transfer or new
money attempt is authorized by this Alpaca candidate.
