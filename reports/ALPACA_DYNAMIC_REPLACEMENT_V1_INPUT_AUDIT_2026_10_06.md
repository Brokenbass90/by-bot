# Alpaca dynamic replacement V1 — source intake October 6

Owner scope accepted: bounded reserve replacement first; current LIVE positions,
capital/risk/stop/earnings/reentry/concentration gates remain frozen. KITY is the
highest new money priority October8–9. No broad architecture/UI/refactor/family.
This source-only intake returns **BLOCKED_DATA_INPUT_CONTRACT**, not a negative
strategy verdict. No new challenger implementation or test/holdout result claimed.
Machine receipt: `ALPACA_DYNAMIC_REPLACEMENT_V1_INPUT_AUDIT_2026_10_06.json`.

## Two measured contract issues

The preserved broker/runtime packet generated September30 20:12:25UTC has only
three primary picks: CRWD/AMD/META, max_positions4. `prepare_intended_report`
materializes `select_v38_successor(...top_n=4...)` and the CSV writes those primary
picks/weights only; no distinct reserve artifact was established in this intake.
The selector ranks/diversifies only until top_n, not a complete reserve contract.
The unused fourth capacity is not a genuinely freed owned slot. AMD's terminal
exit cannot authorize reentry into AMD, a held name or a new scan. A reserve
reconstructed now is not an already sealed September30 LIVE reserve.

Legacy bridge replacement uses `closed_out` local SL/trail/rotation candidates
and `replacement_slots` before terminal broker/cash proof. It is not sufficient
to enable this path with a flag. Intended sizing expects frozen weights for every
candidate and explicitly prohibits redistribution. New reserve candidates need
an exact frozen slot/cash/risk sizing rule; unknown weights cannot silently be
normalized over current holdings. Reuse tested primitives, not this old entry flow.

Initial native protection is **already entry-relative and ATR-aware**. Signal
reference minus2ATR is shifted to actual filled entry by `_entry_relative_stop_price`.
CRWD265.336−2×11.602153778085 →242.13; META724.534−2×27.88864135742 →668.76.
Both match original accepted broker floors in preserved evidence. Current CRWD
floor275.45 then reflects the existing monotonic3.5% ratchet. Comparing an
entry-relative initial stop against the same baseline would duplicate an arm.
These calculations check the contract, not current-trade profitability for tuning.

## Bounded next implementation/result

1. Freeze a challenger-only monthly reserve artifact from completed signal-time
   inputs **before exits**, preserving identical primary picks; deterministic
   eligibility/ranking/ties, source hashes, candidate reference stops and exact
   slot budget. Check concentration against actual surviving holdings at use.
   No retrospective October money eligibility or artificial primary padding.
2. One terminal owned lifecycle can issue at most one consumed replacement token;
   partial/late/pending exit, unknown cash/finality, pending buy/foreign ownership,
   earnings/reentry/concentration/risk/minimum/protection rejection keep cash.
   Same-slot restart/duplicate events cannot issue a second entry. Do not scale
   survivors upward or convert broker buying power into extra sleeve authority.
3. Local isolated orders-OFF candidate and meaningful terminal/partial/late fill,
   duplicate/restart, source mutation/missing reserve, cash/risk/earnings/weight
   rejection tests. No LIVE sender, profile flag or source deployment.
4. Pin exact baseline/replacement sizing, PIT data/security membership and prior
   outcome-access ledger before historical comparison. The older962 proxy was
   already used for structural/protection research. September28 deep handoff
   explicitly blocked identity/PIT acceptance; extra years are not proof of an
   untouched holdout. Verify a genuinely unused accepted interval, otherwise
   **BLOCKED_DATA** and an explicitly prospective evidence plan. No holdout read now.
5. Same capital/risk/cost event replay → net PnL/DD/expectancy/turnover/idle cash/
   exposure/replacement quality, with predeclared acceptance/sample sufficiency.
   Only READY_FOR_PAPER after honest evidence; PAPER lifecycle and separate owner
   GO packet precede LIVE. More entries alone are not a positive verdict.

P0 here means one bounded challenger cycle/result, not indefinite data digging.
On October8–9 preserve KITY unseen raw OI/candles, independent exact basket parity
and actual Bybit/account execution feasibility as the main money path. Reserve
or holdout blockage cannot consume that slot. No further ATT1 probe/heartbeat;
its terminal evidence stays preserved and NEW ordersOFF.

## Stop challenger / later refresh

`ALPACA_STOP_CHALLENGER_V1` is separately SCOPED/NOT_IMPLEMENTED/NOT_PREREG_FROZEN.
First identify a genuinely distinct volatility-aware ratchet/exit rule, not the
already deployed entry-relative2ATR initial stop. Freeze one comparator and its
risk/cost/acceptance rules before any outcome inspection; no coefficient sweep
or choice based on CRWD/META. Existing August protection V2 is historical proxy
research, not an untouched confirmation or permission to retune current LIVE.
Weekly refresh/rotation follows replacement evidence as a separate experiment.
The goal remains monthly selection→management→confirmed exit→reserve replacement,
then later weekly refresh, with independently verified promotion gates.
