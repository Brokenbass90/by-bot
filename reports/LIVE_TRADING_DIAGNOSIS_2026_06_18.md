# Live trading diagnosis — 2026-06-18

## Scope and sources

- Server snapshot generated at `2026-06-18 07:13 UTC`.
- Current canary window: closes on or after `2026-06-17 00:00 UTC`.
- Sources: `runtime/live_trade_events.jsonl`, `data/trade_learning_log.jsonl`,
  `runtime/strategy_health.json`, Alpaca paper logs and state files.
- Historical full journal is reported separately because it contains older code,
  older risk settings and the April ALGO range trade.

## Crypto: current canary

| metric | value |
|---|---:|
| strategy | range / trading the range |
| closed trades | 14 |
| wins / losses | 5 / 9 |
| realized P&L | -0.2542 USDT |
| profit factor | 0.885 |
| logged fees | 0.2160 USDT |
| average winner | +2.67R |
| average loser | -1.17R |

The result is slightly negative and does not yet prove an edge. The payoff shape
is nevertheless useful: PYTH, DOGE and DYDX closed at approximately +3.12R,
+5.42R and +3.73R. The nominal take-profit geometry is not the main defect.

The main execution defect is adverse market-order fill while the strategy stop
remains fixed at the level:

| symbol | planned risk | actual risk after fill | expansion |
|---|---:|---:|---:|
| POLUSDT | ~0.135 USDT | 0.321 USDT | 2.38x |
| DASHUSDT | ~0.135 USDT | 0.256 USDT | 1.90x |
| GALAUSDT (first) | ~0.135 USDT | 0.246 USDT | 1.82x |

Therefore the immediate profitability lever is execution: passive/post-only
entry with explicit timeout/cancel/fallback and a post-fill risk cap. Raising
risk or relaxing signal filters before this is fixed would magnify an execution
defect rather than improve the strategy.

## Crypto: full journal

The unfiltered journal reports `40` trades, `-3.8081 USDT`, fees `0.8792 USDT`.
This includes older ATT1, breakdown and April range trades and must not be used
as the current canary result. Use:

```bash
python scripts/pnl_by_sleeve.py --since 2026-06-17
```

Current runtime risk is positive only for `range=0.25` and `flat=0.30`.
ATT1, breakdown, IVB1, midterm and other enabled scanners have live risk `0.0`.
The bot is live, not globally blocked, and has zero open trades at this snapshot.

## Research status

- `inplay_breakout_retest_htf_runner_v2`: server run active, approximately
  `288/1152`; no candidate has passed. High PF rows around r225-r256 have too few
  trades and too little net profit, so they are not promotable.
- `ivb1_impulse_retrace_v2_relaxed_mirror`: local run stopped around `1276/1536`;
  observed rows were negative and none passed. The detached screen is stale and
  is not evidence of an active computation.
- Pair-arbitrage matrix: all 180 rows returned zero P&L despite many trades. This
  is a harness/accounting defect until proven otherwise, not a strategy verdict.
- Bybit liquidation collector is active and accumulating the event history needed
  for the liquidation-sweep hypothesis test.

No new directional sleeve is ready for positive live risk today. The next useful
addition is the first candidate that passes fees/slippage, multi-window and
monthly gates with a meaningful trade count. Execution repair on range is higher
priority than adding another unproven sleeve.

## Alpaca

Current order-sending monthly paper sleeve is v38. `alpaca_adaptive_v1` is shadow
only. In the 2022 bear bake-off, adaptive gated was the least damaging tested
variant but still negative: return `-6.54%`, PF `0.280`, max drawdown `2.23%`,
12 trades. This demonstrates capital protection, not annual profitability.

Two live-paper blockers were found:

1. Monthly ownership briefly read the intraday state as empty and submitted
   closes for COST, MSFT and PLTR. State writes are now atomic and monthly cleanup
   fails closed when the ownership file is malformed.
2. Fractional intraday orders fall back from broker brackets to software-managed
   exits. The manager did not check ordinary TP/SL, which allowed PLTR to trade
   above its target without closing. Software TP/SL handling is now implemented.

Real `$500` remains conditional on deployment plus five consecutive US market
days with: no ownership conflicts, every fractional position closed by TP/SL/
trail as designed, and realized fills/P&L reconciled. If deployment and the next
five sessions are clean, the earliest evidence-based funding decision is around
`2026-06-25`, not another open-ended waiting period.

## Code corrections in this session

- Trade learning is recorded even when the AI operator is disabled.
- Monthly AI analysis reads canonical `pnl_closed` and `tags` fields.
- Review-time scanner/OHLC snapshots are no longer described as entry-time facts.
- Stale hard-coded portfolio performance is explicitly marked historical and
  unverified in AI context.
- The degradation monitor recognizes the live `range` label.
- `pnl_by_sleeve.py` supports a canary start date.
- Alpaca intraday ownership state writes are atomic.
- Alpaca monthly cleanup aborts on malformed intraday ownership state.
- Fractional Alpaca positions now have executable software TP/SL decisions.

Validation: full local suite `361 passed`.
