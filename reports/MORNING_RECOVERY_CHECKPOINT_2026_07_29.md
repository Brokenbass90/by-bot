# Morning recovery checkpoint — 2026-07-29

## Outcome first

The station moved forward overnight without changing live risk:

- Bybit direct broker truth at `2026-07-29 06:57 UTC`: service active,
  heartbeat fresh, positions `0`, equity `$1019.82`, unrealized PnL `$0`;
- ATT1 remains the only money crypto sleeve, short-only, `risk_mult=0.10`;
- XSEC wrote its fourth immutable daily decision and its first phase markout;
- Alpaca adaptive shadow reached six unique decisions and changed its ranking;
- cross-exchange funding reached `N12` clean post-cutover closed cycles;
- Event V2r2 is terminal: aggregate `FAIL` at 1h/4h and `BLOCKED_DATA` at 24h;
- a causal historical maker-fill V4 was completed for funding positioning;
- public OANDA swap data removed the historical FX financing data blocker.

No live signal, universe, real order or risk multiplier was changed.

## Dynamic symbol selection: actual architecture

Dynamic selection is and must remain strategy-specific.

1. **Global tradability layer** removes instruments that fail liquidity,
   listing-age, volatility, data-freshness or cost constraints.
2. **Strategy profile layer** ranks the surviving symbols differently:
   - ATT1: valid trendline geometry, mature pivots, trend/regime and costs;
   - BOUNCE1: support quality, distance, reclaim and bullish regime;
   - BREAKDOWN: support break quality, bearish regime and optional positive
     funding crowding;
   - pump/exhaustion: relative volume anomaly, extension and exhaustion;
   - XSEC: point-in-time relative strength/weakness and execution capacity;
   - funding positioning: funding percentile, side, symbol health and fill
     economics.
3. **Portfolio priority layer** compares already-generated candidates by
   after-cost expected R, signal/evidence/regime/health/execution multipliers
   and symbol rank, then applies three slots, side caps, symbol overlap and
   beta-cluster constraints.

Layers 1–2 run in the current server control plane. The server refreshed its
per-strategy allowlists at `2026-07-29 04:03 UTC`. Layer 3 exists as
`bot/strategy_priority_router.py` and has focused tests, but is not yet wired
as the common live candidate queue. It must first run in shadow against
immutable decision ledgers; it cannot silently alter ATT1.

## Claude package acceptance

### Accepted as useful findings

- Maker nonfills are not random and must be explicitly measured.
- Overnight/intraday decomposition is not competitive with buy-and-hold on the
  current survivor-only sample after turnover costs.
- The gap proxy does not prove or disprove true PEAD; real earnings dates and
  surprise magnitude are required.
- FX swap must be long/short and broker-specific.

### Not accepted as canonical numbers

- Claude's `-4.3 bps` maker adverse-selection haircut was not backed by a
  committed reproducible implementation.
- His 6/8 per-symbol funding result does not use the same rolling-beta,
  non-overlap, funding-cashflow and three-slot contract as canonical V3.
- `equity_overnight.py` uses UTC first/last bars rather than a verified exchange
  session calendar, uses a survivor list and approximates combined return by
  addition.
- `equity_gap_drift.py` is not PEAD, includes the event stock in its market
  benchmark and does not control overlapping events or PIT membership.

The conclusions are retained here, but those exploratory scripts are not
promoted to sources of truth.

## Funding positioning V4 historical maker audit

Frozen signal: `p70 / 16h`, rolling beta from 60 previously completed trades,
maximum three positions, 6 bps maker round trip.

| Limit improvement | Fill | Filled residual | Realized per submitted signal | Positive symbols | Max positive concentration |
|---|---:|---:|---:|---:|---:|
| 2 bps | 97.09% | +13.15 bps | +12.77 bps | 6/8 | 48.07% |
| **5 bps** | **92.95%** | **+14.51 bps** | **+13.49 bps** | **8/8** | **29.57%** |
| 10 bps | 86.90% | +20.82 bps | +18.09 bps | 8/8 | 29.33% |
| 20 bps | 72.56% | +30.56 bps | +22.18 bps | 8/8 | 30.47% |

The frozen 5 bps historical gate passes, but the monotonic improvement from
deeper limits is a warning that bar trade-through may overstate actual queue
fills. Verdict: `PASS_HISTORICAL_TO_PROSPECTIVE_SHADOW`, not money.

A 72-hour public-data shadow records completed Bybit funding events, frozen
thresholds, maker quote, strict fill/nonfill and the 16-hour outcome. It uses
no credentials and sends no orders.

Reproduction command:

```bash
.venv/bin/python scripts/audit_funding_positioning_v4_maker.py \
  --output reports/research/funding_positioning_v4_maker_20260729/results.json
```

Evidence hashes before commit:

- V4 source: `c4b534e5e892f58a6cfedfbfc8ff59103f2a6a67ce6e5625b074a188f351e4a0`;
- preregistration: `c3627c5bf938a4b653ec7ff5e4fe1c275c0794b6c46da1ace88f5ed14be00369`;
- result: `6cfc21de886770eea4d06b8972af1a748cc740b8e373a7269789b59439435b79`.

## FX/CFD public contract

OANDA's public weekly table valid `2026-07-27..2026-08-02` provides annualized
long/short swaps. These were materialized in
`configs/research/fx_oanda_public_cost_contract_20260729.json`.

Examples:

| Instrument | Long annual | Short annual | Long daily | Short daily |
|---|---:|---:|---:|---:|
| EURUSD | -2.41% | +0.44% | -0.669 bps | +0.122 bps |
| GBPUSD | -0.88% | -1.05% | -0.244 bps | -0.292 bps |
| USDJPY | +1.61% | -3.52% | +0.447 bps | -0.978 bps |
| EURJPY | +0.20% | -2.15% | +0.056 bps | -0.597 bps |
| GBPJPY | +1.70% | -3.60% | +0.472 bps | -1.000 bps |
| GOLD | -6.64% | +0.64% | -1.844 bps | +0.178 bps |

Research no longer needs OANDA live KYC, a second utility bill or a deposit.
The remaining account-specific unknown is `.pro` commission; therefore the
sealed study must include a nonzero commission stress arm and cannot promote
from the zero-commission arm alone.

## Active 72-hour evidence queue

| Process | Current truth | Next useful gate |
|---|---|---|
| XSEC V3 shadow | N4 daily decisions; first phase gross markout -0.44% | N10 interim, N20–30 decision |
| Alpaca adaptive shadow | N6 unique decisions; latest SNOW/PANW/DDOG/ABBV | exact exit/parity attribution, then N20 |
| Cross-exchange funding | N12, 2 wins/10 losses, median -0.1671%, p25 -0.2238% | N20 standalone retire/continue rule |
| Funding positioning V4 | new prospective public shadow | 72h fill/lifecycle receipt; longer N20 later |

## Next implementation order

1. Materialize long/short OANDA swaps in the FX harness and run sealed D1
   carry+trend plus H4 breakout/retest with base and stress costs.
2. Build a common shadow candidate adapter for the priority router; compare
   “first signal wins” against after-cost EV ranking without changing money.
3. Complete a code-parity BOUNCE1 shadow only after resolving the server/local
   strategy SHA mismatch (`a6c5...` server vs `d7f1...` local).
4. Keep true PEAD queued behind PIT earnings-event data; do not substitute the
   gap proxy.
