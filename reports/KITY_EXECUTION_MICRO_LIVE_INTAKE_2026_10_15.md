# KITY execution micro-LIVE — actual intake and orders-OFF candidate

**BLOCKED_EXECUTION: owner money bounds and integrated ten-leg runtime remain.**
Actual read-only account/instrument feasibility is measured, not deferred until
October23. Pure sizing/clock candidate implemented and tested. No order sender,
permit, reservation, deployment or monetary GO exists in this delivery.

Current machine receipt:
`evidence/kity_micro_live_20261015/execution_intake_terminal.json`.
Its earlier v1/v2 diagnostic exports are retained; use the terminal receipt,
which explicitly scopes account observations and gives IOC limit templates at
the last consumed depth level, rather than assuming unlimited best-price size.

## Actual Bybit observation

October15 **05:13:00.235–05:13:05.550UTC /08:13Cyprus**: one bounded GET-only SSH
capture,55 successful allowlisted API responses, no retries or broker/remote
writes. Existing selected credential source matches the already-running
production process; keys never copied locally. query-api's echoed key/IP fields
are redacted before private serialization, with original response hash retained.
Raw account evidence stays in `.private/kity_micro_live_20261015/` (0600/0700).
Sanitized receipt contains no account IDs, keys, request signatures or IPs.

- All ten exact Oct15 C2 symbols are Trading USDT LinearPerpetual and support
  unified margin. Exact5L/5S retained; no metals/stock omission or substitution.
- Actual key: readOnly0, ContractTrade Order/Position permissions. This is actual
  key-scope evidence; per-symbol future order acceptance is not yet tested.
- UTA2, REGULAR_MARGIN; one-way positionIdx0 on all10. Stored leverage3 on
  LTC/BNB,10 on the other8. No leverage/mode/config change was made. Stored
  leverage does not multiply a submitted fixed quantity; it changes margin terms.
- Complete **linear-USDT** position/open-order pagination:0/0. This is not
  account-wide spot/inverse/USDC clearance or future exclusive-writer proof.
- Account-level totalAvailableBalance/totalEquity1020.21638839USD. Coin-level
  USDT wallet1021.49325496 is a different field; it was not substituted as the
  account's available collateral. Zero observed borrow/accrued-interest fields
  are preserved privately, not a general account-finality certificate.
- Selected key expiry returned November6 08:43:37UTC. No key rotation here.
- All-ten raw matching-engine CTS present. At the common capture completion,
  response-clock offset interval[-80,+245]ms gives worst engine-age upper1477ms:
  `OBSERVED_COMMON_2S_PASS`. The receipt explicitly says **invalid for dispatch**;
  this expired morning observation is not a reusable fresh-entry quote.

## Exact geometry and cost

Shared target uses the largest minimum-lot reference requirement across all10;
quantity is floored to each venue step, never raised to force a target. Price
and quantity grids, market maxima and both-side50-level depth are checked.

| Profile (none approved) | Target per leg | Actual book gross | Flat-price round-trip fees + spread |
|---|---:|---:|---:|
| Venue-floor diagnostic |21.84290|210.266660|0.255878073|
|≤5% per-leg floor-rounding shortfall|66.45856|658.062380|0.80729015125|
|≤2%|87.37160|870.433860|1.08030898975|
|≤1%|374.0932|3733.106280|5.168264744|

The venue-floor profile has LTC20.27% below common target. It is not certified
faithful equal-notional sizing. About77.72 gross obtained by buying each
independent minimum is not an equal-notional basket either. Exact smallest
**approved** basket/capital therefore remains undecided until rounding policy is
concrete. The1% profile exceeds current available collateral at a fully-funded
1x allocation; using leverage to make it fit is not authorized.

Venue-floor diagnostic drafts (historical templates, **not an entry instruction**):

| Symbol | Side | Qty | Entry book notional | Actual taker fee/side |
|---|---|---:|---:|---:|
|BTWUSDT|Buy|10|21.84290|5.5bps|
|XAUUSDT|Buy|0.005|20.76830|2.75bps|
|LTCUSDT|Buy|0.3|17.415|5.5bps|
|VVVUSDT|Buy|0.98|21.728560|11bps|
|BNBUSDT|Buy|0.03|21.5823|5.5bps|
|XAUTUSDT|Sell|0.005|20.69945|5.5bps|
|XPLUSDT|Sell|280|21.76720|5.5bps|
|XAGUSDT|Sell|0.389|21.84235|2.75bps|
|GRASSUSDT|Sell|34|21.69200|5.5bps|
|SPCXUSDT|Sell|0.14|20.9286|2.75bps|

All four profiles include exact ten IOC request **templates**, tick-valid limits,
deterministic `KXM1-<12hex>-E00..E09` entry /X00..X09 exit namespace and explicit
`draft_is_executable=false`. No token/owner GO is generated. Real fills can be
partial or fail even where recorded depth was sufficient.

Flat-price costs are diagnostics, not future loss or capital bounds. Current
fee rates differ per instrument, notably VVV. Funding rates/next times and
instrument intervals/bounds were captured; the seven-day scenario in JSON holds
today's rate limits and notionals constant and is explicitly **not a proven
future bound** or an approved reserve. Tiny execution duration is still unset.
The approximate initial margin at stored3x/10x (30.13 for the floor profile) is
not minimum safe capital or a tiny account-loss guarantee. Cross collateral
and unbounded short tails must be reflected in the approved experiment policy.

## Decision and next action

1. Owner selects aggregate/per-leg gross caps, allowed rounding, planned loss
   including costs and finite execution-probe duration/account policy. A concise
   question is pending; this is not a request to approve an unspecified order.
2. Finish only the isolated ten-leg sender/owned recovery, shared writer custody,
   partial-basket cancel/unwind and finality wiring against that concrete plan.
   Existing research assessor/coordinator are not deployed basket senders.
3. Replay the exact adapter lifecycle, including restart/unknown send/partial
   failures, then produce a fresh account-bound exact GO packet. No new research
   result, additional prospective week or statistical PAPER is required merely
   for this separate execution experiment. Frozen strategy canary gates continue.

The written implementation contract is
`../docs/superpowers/specs/2026-10-15-kity-execution-micro-live-v1-design.md`.
Unwind means only proven owned quantities via reduce-only, preserving unknown
dispatch and foreign positions; kill is not account-wide flatten. Risk thresholds
cannot guarantee a fill/loss through gaps or broker outages.

## Current families — no new judge or prospective PnL consumed

| Family | Research status from frozen existing evidence | Execution/micro status | Minimum capital | Next action |
|---|---|---|---|---|
|KITY Bybit|Existing historical CROSS_VENUE_PASS; actual first source/C2 PASS. Same historical era as Binance, not independent future proof. C1/second week remain separate.|NO now: explicit bounds + integrated basket runtime outstanding. Actual10-symbol/key/minimum/depth/fees intake done.|Approved value undecided; measured references above.|Select bounds; wire/test exact execution-only lifecycle; separate exact GO.|
|Elder ETS2M_V2|Prereg explicitly describes ETS2S +0.0668R/4.22sigma as **informational**, not money-tested. Historical windows consumed; new900/900 prospective protocol unchanged.|NO: no verified pre-prospective cost-adjusted executable EDGE_DEV_PASS packet for this version.|Not assessed.|Claude supplies an existing applicable causal DEV/cost/identity receipt if one exists; do not read interim prospective profitability to invent it.|
|LIQ V2|Clean new prospective source epoch gathering; source gate not reached. Historical directional V1 is tainted where inverted normalization applies.|NO verified historical V2 DEV/causal source-semantic packet in this cycle; no executor work.|Not assessed.|Claude owns separately pinned raw-source renormalized DEV; prove raw S/time identity before outcome use. No old PASS/KILL reversal or fake prospective backfill.|
|Bounce|Mac prereg shadow is research authority; old VPS source BLOCKED_DATA remains closed.|NO new money/edge acceptance from this task.|Not assessed.|Keep existing frozen shadow; Claude research lane.|
|Breakout|Source/bridge parity is engineering, not verified profitable execution edge.|NO; not promoted for activity.|Not assessed.|Existing prereg evidence lane only.|
|ATT1|Existing independent terminal/continuity gates unchanged; not P0.|NO revival or risk changes.|Not assessed.|Preserve current state/gates.|

No new tests/judges/outcomes were run on these research families. Only already
published historical KITY/ETS2M prereg/result sources were read; no prospective
profitability was used. No claim that renormalizing direction alone repairs
V1 missingness, timestamp gaps or bankruptcy-price execution assumptions.

## Verification and P0

398 targeted tests PASS:29 new micro geometry/clock cases plus existing KITY
assessor/CLI/251 signal-vector tests. Original research/source/calculator and
Alpaca code remain unchanged. No full-suite/real-order lifecycle PASS is claimed.
Pure dossiers replay offline; original55 API responses are never requested again
by their builder. Root review only; prior independent-review quota not retried.

Alpaca today retains frozen priority: fresh preflight before16:15Cyprus, owner's
separate exact GO, arm before16:29, one opening attempt16:30–16:35 within existing
latest-start boundary. This crypto capture did not query Alpaca, clear HALT,
activate a unit or produce a fresh NET dossier. No unattended wakeup was added.

Official sources used for the execution contract:
[instrument/lot/funding fields](https://bybit-exchange.github.io/docs/v5/market/instrument),
[key permission fields](https://bybit-exchange.github.io/docs/v5/user/apikey-info),
[account margin mode](https://bybit-exchange.github.io/docs/v5/account/account-info),
[positionIdx/leverage/reduce-only fields](https://bybit-exchange.github.io/docs/v5/position),
[account USD wallet totals](https://bybit-exchange.github.io/docs/v5/account/wallet-balance),
[IOC/linkID/reduce-only order semantics](https://bybit-exchange.github.io/docs/v5/order/create-order).
