# PUMP4 sizing: exact 84-case attribution, 27 October 2026

**82 blocked / 2 fixture sizing passes; no current trade is proved executable.**
All84 results independently reproduce both the preserved native84 receipt and
the unchanged `source_sizing` function. The distinction matters: native protocol
PASS84 does not admit84 financially. No strategy, risk, capital, source gate,
funding policy, selected owner, Monthly state, GO or order was changed.

## Capital and evidence basis

The saved OFF proposal is allocation **50 USDT**, gross **30**, reserve **20**,
cost-inclusive risk **1**; one entry/position, day loss2/week3/drawdown6,
slippage scenario10bps per side. Policy SHA
`befacba9bd781538b92fb6c195c0b996450fcb54656584b8c614b5f17a2d2502` exactly matches
the selected execution-policy hash in
`evidence/pump4_entry_and_h1_20261027/readback-final.json` (dated27Oct05:31UTC).
This is an OFF proposal, not approved monetary authority. Later selected-runtime
identity is the primary operator's separate readback; this audit makes no VPS call.

The native84 harness uses fictional available balance100, capped by allocation50.
It is not the owner's actual balance. More deposited cash alone does not change
the risk1/gross30/allocation50 ceilings. No capital increase is proposed.

The84 plans are historical. Instrument metadata and account-specific fees are
from **26Oct13:19:41.441UTC**; the harness replaces bid/ask/last with each historical
reference entry and makes the capture clocks fictional. It does not price an old
stop against today's market. The earlier owner-decision table used a different
hybrid basis: dated26Oct bid times historical percentage stop width. Both reports
have82 gross-fitting cases, but their quantities/risk figures are not interchangeable.
Neither is fresh pre-send evidence or a new backtest/PnL run.

## Exact blockers

| First failed sizing stage | Cases | Concrete reason |
|---|---:|---|
| Base capacity, risk only |49|Smallest legal40/60 quantity exceeds1 USDT stop-risk scenario before fees/funding|
| Base capacity, risk and gross |2|LITE and ZEC also exceed gross30 at the minimum legal quantity|
| Cost-inclusive capacity, funding decisive |30|Minimum quantity fits base risk and fee/slippage risk; full168h adverse funding-cap scenario takes total above1|
| Cost-inclusive capacity, fee/slippage already sufficient |1|TRUMP minimum risk0.989949 +fee0.0064735 +slippage0.01177 =1.0081925 before funding|
| Fixture sizing pass |2|ALGO09Oct08H and WLD10Oct21H; historical examples only|

No first-stage refusal is attributed to account cash, reserve or exchange maximum
market quantity. Seven base quantities round to zero. All51 base failures
already violate risk1 at minimum quantity, so a gross-cap increase alone would
not repair them. All31 cost failures have positive costs; reducing quantity below
the exchange/split floor cannot produce a legal entry.

For every case the minimum opening quantity is
`ceil_to_5qtyStep(max(minOrderQty/.4, minNotional/entry))`.
Both40% and60% legs must meet minQty and qtyStep. The opening must meet
minNotional; no5USDT minimum is imposed on reduce-only closing legs. Before
rounding, entry min-notional sets the larger lower bound for80 cases; split
minQty sets it for4. Rounding to5×step is required for the exact40/60 split.

Base sizing is the existing minimum of risk-distance, adverse-price gross and
allocation limits, rounded down to5×step. Cost sizing further reduces that
quantity using original-reference/adverse-entry distance plus roundtrip fees,
10bps/side impact and current-cap funding stress. Native stop tick tightening
never reduces the original reference risk basis or increases quantity.

| Case | Minimum qty | Entry nominal | Stop-risk scenario | Fee + slippage | Funding stress | Total scenario |
|---|---:|---:|---:|---:|---:|---:|
| LITE |.05|49.4595|7.925079|.126122|20.772990|28.824190|
| ZEC |.05|59.2160|8.251525|.183570|8.207338|16.642432|
| TRUMP04Sep07H |2.5|5.8850|.989949|.018244|.939246|1.947439|
| PEOPLE, nearest cost failure |600|5.0220|.483575|.015568|.527310|1.026453|
| ALGO09Oct08H |42.5|5.033275|.421055|.015603|.348806|.785464|
| WLD10Oct21H |9.0|5.01120|.441411|.015535|.452511|.909457|

The fee inputs are68×5.5bps,14×11bps,2×2.75bps per side. Funding stress assumes
the full initial notional for168h, using21 eight-hour or42 four-hour settlements
at the dated adverse cap. It is neither expected funding nor a guaranteed future
loss bound. It does not credit an early TP1 or replace unknown costs with zero.
The30 funding-decisive labels are arithmetic attribution only, not permission to
remove the funding term or select a cheaper scenario.

## Minimum feasible examples and the actual selected size

Within this preserved fixture, WLD is the smallest nominal example that passes
all retained sizing arithmetic: minimum9 WLD,5.01120USDT, split3.6/5.4,
total stop+cost scenario0.9094572. ALGO minimum42.5,5.033275USDT,
split17/25.5, scenario0.785464345. Their minimum cash plus costs plus reserve20
is25.47924608 and25.39768411 respectively, within allocation50.

The existing sizing algorithm actually selects **9.5 WLD /5.28960USDT /
0.9599826 risk+cost** and **54 ALGO /6.395220USDT /0.998001756 risk+cost**.
The smaller arithmetic minima are not newly selected quantities or orders.
Neither historical signal can be traded now or interpreted as a current candidate.
Thus **current eligible live cases established by this task: zero**; the future
eligible fraction is unknown, not an estimated2/84 success probability.

## Evidence still needed for a current signal

Use the existing bounded GET capture and admission path, only when a qualifying
timely signal exists. It must bind:

1. Fresh exact-symbol instrument filters, tick/minQty/qtyStep/minNotional/maxMktQty,
   funding interval/caps; current bid/ask/LastPrice/funding/nextFundingTime and
   exchange clock. Full source coverage, hashes and permitted freshness remain.
2. Authenticated symbol fees, available balance/no borrowing/regular margin,
   complete account positions/orders and exact-symbol one-way mode, original
   owner lock plus current risk/admission/claim history. Equity alone is not cash.
3. Original H1 open/reference price, fresh forming-interval evidence showing no
   earlier native-stop/TP1 touch, accepted deadline/drift and native geometry.
4. Existing exact-scope authority and personal financial GO before any send.
   Passing arithmetic alone supplies neither. Actual execution/funding cash
   finality remains downstream and cannot be inferred from this analysis.

No extra data collection, retroactive signal, owner action or command is issued
by this report. Next bounded use is the unchanged sizing function on the next
qualifying current signal with fresh existing sources; preserve rejection if no
legal quantity fits. H1 latency/source-loss and economics remain separate gates.

## Reproduction and verification

`python -m research_lab.pump4_sizing_readiness_v1 tests/fixtures/pump4_native_reference_84_20261026.json`
emits Decimal attribution only. It is not imported into the financial runtime.
The module rejects another policy/plan hash or missing funding rather than
silently changing the assumptions. No network or exchange implementation is called.

`pytest -q tests/test_pump4_sizing_readiness_v1.py`: **5 PASS**. Tests include
all84 independent comparisons against the unchanged production sizing and saved
receipt, exact minimum/split checks, and missing-funding/nonfinite/changed-contract
rejection. RED first:5 expected missing-module assertion failures; GREEN:5PASS.
No repository-wide suite, economic judge, new outcomes or funding downloads ran.

Per-case numbers, identities, first-stage reasons and cost components:
[JSON](evidence/pump4_sizing_readiness_20261027/attribution.json),
[CSV84](evidence/pump4_sizing_readiness_20261027/cases84.csv).
The JSON distinguishes simulated prices/cash, dated metadata and absent authority.
Input/output/source hashes are in the adjacent manifest.
