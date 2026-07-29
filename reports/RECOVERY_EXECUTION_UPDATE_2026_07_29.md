# Recovery execution update — 29 July 2026

Status time: 2026-07-29 08:55 UTC.

This is the current operational handoff for the next supervisor cycle. It
supersedes informal chat estimates, but does not replace immutable research or
deploy receipts.

## 1. Direct live truth

- VPS Git HEAD: `f7ed0116a5f5`; the server worktree is dirty and materially
  behind the local research branch.
- `bybot.service`: active; heartbeat fresh; WebSocket guard inactive.
- Direct Bybit query: equity approximately `$1019.92`, no open positions.
- Money sleeves: ATT1 short-only at `risk_mult=0.10`; no other crypto sleeve is
  authorized for capital.
- ATT1 last entry: DOTUSDT on 2026-07-24 05:08 UTC.
- Since the latest restart ATT1 has been scheduled 52 times: 34 cooldown
  skips and 18 evaluated attempts. All 18 were legitimate `no_signal`:
  trendline 10, first-bar confirmation 6, touch 2.

Conclusion: ATT1 is enabled and transport/execution are healthy. The quiet
period is signal scarcity plus cooldown, not a stopped strategy. No live
parameter, universe, risk or order mutation was made.

## 2. Dynamic symbol selection

The system now has three distinct layers; they must not be conflated:

1. Liquidity/eligibility universe: available for several research/live paths.
2. Per-strategy ranking: must use inputs appropriate to the strategy.
3. Portfolio priority: common candidate schema plus the three-slot router.

Layer 1 is operational. Layer 2 is now materialized for Funding Positioning V4
as a separate risk-zero challenger. Layer 3 remains observer/shadow until
candidate parity and portfolio replay pass.

The new dynamic Funding universe is selected only from public Bybit data:

- active USDT linear perpetual;
- Bybit crypto symbol type only; stock and commodity perpetuals are rejected;
- listing age at least 90 days;
- 24h turnover at least `$20m`;
- spread at most 12 bps;
- at least 91 funding observations;
- rank by turnover, then spread; neither signal nor PnL is used.

Current 16-symbol universe:

Current clean universe:

`BTC, ETH, SOL, BANK, XRP, HYPE, COTI, AKE, ZEC, DOGE, NEAR, ADA, 1000PEPE,
SUI, LINK, LTC`.

It is regenerated from public data and recorded with a universe hash. Stock
and commodity perpetuals cannot enter merely because their ticker ends in
USDT.

Current clean universe SHA:
`65675f3c6ef4b54442f4ae082e523d35d8dc4752dfec563e4b45a46edac9bbbe`.
It is written to `runtime/funding_positioning_dynamic_universe.json` and every
decision record.

The frozen eight-symbol shadow remains the control. The dynamic challenger has
its own state, ledger and summary and is running as
`funding_position_dynamic_shadow_20260729`. It cannot place orders.

Promotion gate:

- at least 20 closed dynamic lifecycles;
- positive executable distribution after maker nonfills and funding;
- breadth across symbols and concentration below the preregistered ceiling;
- no parity or lifecycle defect;
- dynamic challenger must beat or add useful breadth to the frozen control.

Expected time to the first review is approximately 5–10 days at the observed
event frequency. This is an event-count estimate, not a calendar promise.

## 3. Funding positioning V4

Historical maker audit remains a PASS to prospective shadow, not to money:

- 8/8 frozen symbols positive;
- 5 bps resting-limit proxy fill rate 92.95%;
- residual `+13.49 bps` per submitted trade;
- top-symbol concentration 29.57%.

The prospective frozen shadow is running. After its first event it has eight
trials, three submitted resting entries and five no-signals; the three entries
are still pending fill. There are no closed prospective trades yet.

The 8/8 historical result may justify wider prospective coverage, but cannot
be extrapolated to arbitrary newly listed coins. That is why the dynamic
challenger uses causal liquidity/history gates and a separate ledger.

## 4. Cross-exchange funding arbitrage

Truthful post-fix cohort:

- closed `N12`;
- wins 2, losses 10;
- mean `-0.1391%` per cycle on total capital;
- median `-0.1671%`;
- p25 `-0.2238%`;
- five cycles open.

The current five open cycles are scheduled to age out between 29 and 30 July,
which would bring the cohort to N17. If discovery continues at the current
rate, N20 is expected around 31 July–1 August, approximately 2–3 days.

The preregistered N20 rule is unchanged: negative p25/median or simple
annualized economics below 8% retires the standalone money sleeve. The public
collector, basis/legging evidence and reusable execution controls are retained.

## 5. OANDA / FX / CFD

No OANDA KYC, utility bill, deposit, private token or paid data is needed for
the current historical stage.

The public OANDA weekly contract is now wired into the V2 research harness:

- spread in broker pips is converted to price bps using the run's reference
  price;
- long and short swap are signed and modeled separately;
- a positive swap is a credit, a negative swap is a debit;
- stress makes debits larger and credits smaller;
- unknown `.pro` commission is covered by a mandatory stress arm.

This repairs the symmetric-near-zero financing defect. It does not create a
strategy result by itself. Next work is a newly sealed D1 carry+trend and H4
breakout/retest preregistration; old SHA-pinned FX receipts are not silently
rewritten. Expected first honest historical receipt: 3–7 days.

OANDA registration becomes useful only after historical PASS, when exact demo
quotes and order lifecycle must be measured. No initial deposit is requested
now.

## 6. AI awareness and web

Claude's observation was accepted in substance but its headline count was not.
There are 124 `bot/` modules. Static analysis currently finds:

- 37 direct monolith references;
- 42 modules transitively reachable from the monolith;
- 74 modules mentioned by tests but not statically reachable.

The last category does **not** mean “74 ready technologies.” A test-file mention
does not prove behavioral coverage, production readiness, live parity or edge.

Implemented:

- conservative `technology_inventory_v2`;
- static import reachability instead of one-file grep;
- explicit `static_inventory_not_promotion_evidence` authority;
- compact registry in both full and brief AI contexts;
- generated full context validated at 428.5 KB;
- read-only web `/api/book-status`;
- web “Book Status” page with sleeves, risk, N/gate, health and next action.

The live VPS already rebuilds `full_context.json` every five minutes, so the
“stale since 22 July” diagnosis describes an earlier incident, not current
truth. The new registry and Book Status page are committed locally but require
a targeted observer/web deploy; a full repository pull is unsafe because the
server is roughly 150 commits behind and dirty.

## 7. Active risk-zero processes

1. `cross_arb_shadow_20260728`
2. `alpaca_adaptive_shadow_20260726`
3. `funding_position_v4_shadow_20260729`
4. `funding_position_dynamic_shadow_20260729`
5. `xsec_v3_shadow_20260726`

Safe supervisor behavior:

- restart only these research processes through their receipt/lock contracts;
- never change ATT1 live risk, signal, universe or real orders;
- do not merge the frozen and dynamic Funding ledgers;
- produce terminal `PASS`, `FAIL` or `BLOCKED_DATA`, never “almost PASS.”

## 8. Realistic next gates

- 31 July–1 August: cross-exchange arbitrage N20 decision if event cadence
  persists.
- 3–8 August: first Funding V4/dynamic lifecycle review; N20 may take 5–10
  days.
- Early/mid August: XSEC N10–15 interim and Alpaca PIT/exit-parity receipt.
- 3–7 days: first new FX receipt with signed public OANDA swap costs.
- Mid/late August is the earliest plausible window for a new tiny money sleeve,
  and only if its independent shadow gate passes. This is not a return promise.

## 9. Next implementation order

1. Run sealed FX D1 carry+trend, then H4 breakout/retest with the new cost
   contract.
2. Finish Funding V4 frozen-versus-dynamic shadow comparison.
3. Complete BOUNCE1 virtual lifecycle and untouched preregistration.
4. Build the common candidate adapter for ATT1/BOUNCE1/BREAKDOWN/XSEC.
5. Replay the three-slot priority router against first-signal-wins.
6. Targeted deploy of observer-only AI registry and Book Status after
   server-file parity checks.
7. Continue Alpaca PIT/corporate-action materialization and exit repair.

## 10. What is required from the owner

Nothing for the current crypto, Funding, XSEC, Alpaca historical or FX public
research. Do not send trading keys or add OANDA money now.
