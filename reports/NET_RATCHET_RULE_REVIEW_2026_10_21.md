# NET: activation review, read-only

**RULE_REPRODUCTION_PASS; historical same-entry PnL/MaxDD comparison BLOCKED_DATA.**
No LIVE change, strategy edit, broker call, new order or research judge run.
This is a bounded descriptive check; Monthly → PUMP4 priorities remain unchanged.

## Origin and meaning

The3.5% activation/trail defaults entered the protective-exit helper in
`06869be5dc7c5ec1842d4210924af3d920600904` (1Aug). The isolated Dynamic runtime
`f39fb324156e8a5ffd335fb1d6397706aa7b4814` reused them unchanged. The inspected
commits/release receipts establish implementation and deployment; no NET-specific
paired result proving3.5% optimal was found there. Absence of that evidence is
not evidence that1% is better.

Initial protection is separate: frozen2×ATR distance, retained in the Oct15
intent as33.54241333009 per share; see [preflight](ALPACA_OCT15_FINAL_LIVE_PREFLIGHT.md)
and [actual entry](ALPACA_OCT15_ACTUAL_LIVE_OPENING.md). About10.77% at that fill
came from the fixed absolute distance, not a separate10.77% trailing setting.

The selected legacy helper samples broker marks every5minutes and uses:
`floor_to_tick(min(max(old_stop, accepted_floor, HWM*.965, entry*1.005), mark*.999))`.
Minimum raise10bps; DAY rearm retains accepted floor. This is distinct from the
new Monthly completed-daily/next-session policy. Helper hash2d5243ee…bce5eea1
matches the installed hash previously verified in the dated NET read-only checks.

## Isolated calculation using the existing helper

Normalized entry100, mark first sampled exactly at threshold/HWM, old stop89.23;
trail3.5%, minimum lock.5%, market gap10bps, same quantity and remaining rules:

| Activation | Sampled price | Proposed stop | Gross gain at stop | Stop distance below mark |
|---|---:|---:|---:|---:|
|1%|101|100.49|0.49%|0.505%|
|2%|102|100.49|0.49%|1.480%|
|3.5%|103.5|100.49|0.49%|2.908%|

The initial floor is controlled by minimum lock, not by nominal3.5% trail width.
Earlier activation makes the stop tighter relative to the current price; more
noise exits are plausible, not measured here. Existing float arithmetic plus
cent-floor gives100.49 in this example, not exactly100.50. No precision/live patch.

The minimum lock is not unconditional: for a late observation with HWM101.38 and
mark99.45, changing activation to1% now yields proposed stop99.35 because the
market ceiling binds. A past peak cannot retroactively guarantee a profitable exit.
Stop prices are not guaranteed fill prices ([Alpaca order documentation](https://docs.alpaca.markets/us/docs/orders-at-alpaca)).

Hypothetical TOTAL round-trip fees+spread+slippage of10/20/40/60bps of entry
capital reduce0.49% to0.39/0.29/0.09/−0.11%. These are sensitivity assumptions,
not actual account charges; gap losses are not bounded by this table.

## Requested historical metrics and exact limitation

Counts reaching each threshold, mean net profit, portfolio/trade MaxDD and
premature-exit frequency are **NOT_ESTIMATED**. Inspected NET daily archive:
501unique, valid OHLC rows,12Aug2024–11Aug2026. It lacks5minute broker-mark paths,
same-entry legacy lifecycle set, actual stop replace/DAY timing and fills/costs.
Daily high/low cannot determine ordering or whether a five-minute poll saw a peak.
One still-open verified legacy NET lifecycle is not a historical trade sample.

Published H6 (`359b19b…7e2`, prereg9112083/003eb08) contains aggregate Monthly
statistics and a separately frozen forward experiment. It is not a legacy NET
comparison; its A20/A35 are not evidence for live NET. A10 is not a prereg H6 arm.
No new arm was added, used history retuned, or judge rerun; existing H6 stays with Claude.

Next data gate ONLY if this P1 is resumed: verified same-entry closed NET episodes
plus causal5minute marks and order/cost timing, or an explicitly labelled
coarser proxy with uncertainty bounds. Do not delay Monthly/PUMP4 or select a new
LIVE threshold from the normalized calculation. Current protection unchanged.

[Reproduction](evidence/net_ratchet_review_20261021/analysis.py),
[QA/calculation receipt](evidence/net_ratchet_review_20261021/receipt.json).
