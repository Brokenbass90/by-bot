# Alpaca exact baseline — offline candidate delivery, October16

CURRENT **2026-10-16 17:26 UTC /20:26 Cyprus**:
`OFFLINE_BASELINE_COMPONENT_PARITY_PASS`.
**NOT `ALPACA_STRATEGY_PARITY_PASS`; not a deployed monetary runtime.**
New entries remain HALTED. Current NET and its restored maintenance kit were
not modified or redeployed in this work. The last complete independent protection
readback remains16:55:21UTC: one full NET STOP/DAY277.69 for0.325167779.

## Accepted executable reference

Claude research commit **981b62f7da598df95b0cf265902f28c920929469** is already on
actual `origin/research/fabrika-v1` (read-only `git ls-remote` confirmed); no push
or changes to Claude's checkout were needed. Reference code is recovery commit
**2e68b1f5ba6d2767c2144c5dafd8f10a6d2908c6**. Exact supplied runner was read before
execution and exported with the code into an isolated private directory.

Verified all8 supplied code hashes, config SHA
`7b1022ce47933e1de579ca4ebb950cf84675958ba62c3aee9d8337534ad6b245`, and59 raw
files/universe SHA
`36da070b2e1fb6c7a10d3df99716c94e2afcabc7bae57d3ca172441736107172`.
No path-dependent old Strategy ID is used as proof.

The exact runner independently reproduced **64 trades**, core
**2347a7ec606cd845**, DD7.569155255862947%, PF1.810941917777547.
These are reproduction of the existing baseline, not new development evidence,
a holdout run, an improved strategy or a profitability promise.
[Reference/independent runner receipt](evidence/alpaca_parity_repair_20261016/etalon_reference_manifest.json).

## Implemented locally, orders-OFF

`research_lab/alpaca_dynamic_v1.py` now refuses a new reservation from a ranking
outside its intended next-session window: `NO_SEND / STALE_SIGNAL_RESELECT_FAIL`.
Friday→Monday remains valid; a wall-clock24h expiry was not introduced. Existing
sealed/consumed intents remain readable. Newly sealed ATR must be finite, positive
and reproduce the existing selector's exact signal-close expression. This patch
does **not** turn Dynamic weekly into the baseline and is **not** installed in NET.

`research_lab/alpaca_strategy_parity_v1.py` adds a transport-free candidate:

- monthly signal, immediate next-session opening only; confirmation of original
  symbol, no off-cycle substitution;
- reused frozen selector and SPY200 gate, raw ATR20 from the signal session;
- source-bound entry/fill receipts: signal/intended/actual times, signal age,
  ATR session/value, quote CTS/source/hash, selection/history/calendar/code pins;
- initial stop from actual fill−2ATR, exact reference downward quantization and
  five-percent fallback only when the computed raw stop is nonpositive;
- daily-close HWM/ratchet, opening gap→old-stop low→close ratchet ordering,
  raised stop effective next session, unchanged frozen formula/giveback;
- no unfinished daily close consumption; duplicate daily input is idempotent,
  conflicting same-session input or missing held session blocks.

The module has no broker transport, permit/reservation, production writer,
service installation, durable live-manager binding or HALT release. Its receipts
explicitly carry `orders_allowed=false` and `money_authority=false`.

## Actual-source differential verification

`scripts/replay_alpaca_baseline_parity_v1.py` verifies pins before loading data,
compares the current selector wrapper to exact reference `_decisions`, observes
the unchanged reference engine's position states and compares candidate
transitions/exit reasons/prices, then requires the published rounded trade core.
It never counts matching aggregate PnL as sufficient proof.

Final-code replay V2:

| Comparison | Result |
|---|---|
| Monthly selections |24 exact|
| Initial stops |66 exact|
| Daily pre-stop/HWM states |695 exact within1e-9|
| Daily post-stop/HWM states |637 exact within1e-9|
| Protective exits/reasons/reference prices |56 exact|
| Full published trade core |64/64;2347a7ec606cd845|

Two final-day surviving positions (BAC/SPY-calendar July10 and SNOW/July10)
have no next session in the supplied source. Their final close→future-stop
publication is deliberately not evaluated; no future session was fabricated.
Their pre-state checks and all final-day actual protective exits are covered.
Replay clocks are logical OHLC test clocks, **not** broker quote CTS or a live
authoritative exchange calendar.
[Final-code replay](evidence/alpaca_parity_repair_20261016/baseline_component_replay_v2.json).
V1 receipt remains immutable historical evidence of the immediately preceding
adapter revision; its code hashes must not be presented as the final revision.

Targeted verification: **266 PASS**, covering entry-book, new baseline adapter,
existing PAPER/maintenance/intake/LIVE/first-intent/owner-repair safety. No broad
suite rerun or independent reviewer signoff is claimed.

Saved real Oct9 ranking/Oct15 intake was passed through the same new session-TTL
predicate: **rejected**. Actual Oct14 selection/ATR is not in those saved entry
sources and remains UNKNOWN. Reference-rounding diagnostic using the old ATR is
277.67 versus actual277.69; it is **not** permission to lower the existing stop.
[Saved input replay](evidence/alpaca_parity_repair_20261016/saved_live_entry_replay.json).

## Previous intents / evidence quarantine

One new bounded GET-only SSH capture read4 declared source books and exhausted
the accounts' retained order histories: **836 PAPER orders/2 pages**,
**214 LIVE orders/1 page**,500-row limit with exclusive order-ID pagination.
No fee polling, broker mutation, manager operation or remote write was performed.
Private raw capture stays uncommitted; the public result contains hashes and
explicit classifications, not credentials/account IDs.

- NET PAPER12–13October: `OPERATIONAL_VALIDATION` (forced lifecycle exit).
- NET LIVE15October: `OFF_PROTOCOL_STALE_SIGNAL`, secondary
  `OFF_PROTOCOL_RISK_REFERENCE`, relative to the exact validated monthly baseline.
  Dynamic weekly was separately owner-approved Oct6; this is a baseline-evidence
  mismatch, not a claim that an unauthorized monetary order was sent.
- October1 CRWD/AMD/META: selection is Sep30→Oct1, but actual entries14:10UTC
  versus reference open13:30UTC. CRWD initial stop matches reference rounding;
  AMD/META initial stop is one cent above reference rounding. Classifications
  retain the actual schedule/rounding distinctions, not a fabricated stale ATR.
- Older entries and unfilled orders without full selection/ATR lineage remain
  `UNKNOWN` or explicitly no-fill. None is silently promoted to ON_PROTOCOL.

All346 retained buy orders have a row;341 are UNKNOWN (including no-fill
records). This is a complete inventory of the returned retained broker history,
**not** a claim that old raw selection/ATR evidence exists or every historical
strategy is now reconstructed. Missing historical lineage is quarantined; no
new retrospective research/PAPER gate was added to future entries.
[Sanitized inventory](evidence/alpaca_parity_repair_20261016/prior_intents_classification.json).

## Complete known remaining boundary

| Item | Current evidence / required next action |
|---|---|
| Trading contract choice | Owner was asked whether future entries return to validated monthly/daily or retain weekly pending separate validation. Oct6 approval of weekly cannot be relabelled monthly. No money/activation authority follows from the choice. |
| Future production binding | Existing Dynamic compiler still allocates replacement slots weekly and propagates rounded risk distance; existing manager ratchets intraday. Bind a versioned monthly entry/rotation/retention path and daily-close durable manager candidate orders-OFF, using the existing single-owner/recovery primitives. Current NET must retain its existing maintenance. |
| Daily-close source | Bind actual completed-session close/calendar/availability and idempotent next-session activation. The historical replay's logical clock is not such a source. |
| Independent review | Claude reads final diffs/code hashes/replay against981b62f; no reviewer has signed off this candidate yet. |
| Financial activation | Fresh account/quote/caps/session checks and separate exact owner monetary authority remain. No extra PAPER/statistical waiting is required by this delivery. |

Thus the missing executable reference is closed and component parity is proven.
**Deployed full-strategy parity remains BLOCKED**, with these named differences;
neither a green unit suite nor64 matching historical trades clears entry HALT.

Reproduce component comparison (new output pathname required):

```bash
PYTHONHASHSEED=0 .venv/bin/python scripts/replay_alpaca_baseline_parity_v1.py \
  --reference .private/alpaca_parity_20261016/etalon-reference \
  --data ../bybit-bot-clean-v28/runtime/equities_1h_parity_20260710 \
  --output /tmp/alpaca-component-replay-new.json
```

Claude handoff: this report, final replay V2, exact manifest, saved-entry replay,
prior-intent inventory, `alpaca_dynamic_v1.py` TTL diff and
`alpaca_strategy_parity_v1.py`. No direct message was sent to another chat.
