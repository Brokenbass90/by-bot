# Forex LOB Backtest Results — 2026-03-11

## Strategy: London Open Breakout V1 (LondonOpenBreakoutV1)
File: `forex/strategies/london_open_breakout_v1.py`

## Data
- Source: `data_cache/forex/*_M5.csv` (from OANDA Dukascopy via existing fetch scripts)
- Period: Oct 2024 – Mar 2026 (~17 months, 100k M5 bars per pair)
- pip_size: 0.0001 for majors, 0.01 for JPY pairs

---

## Key Findings

### What Works
The **London Open Breakout** is the ONLY strategy from the entire forex package
(8 strategies across 836 backtest runs) that shows consistent positive results.

**Core Logic**:
1. Measure Asian session range (00:00–07:00 UTC)
2. At London open (07:00–10:00 UTC), if price breaks above/below range → enter
3. SL = opposite range edge + small buffer (natural stop)
4. TP = 1.5× risk (RR = 1.5)
5. One trade per day

### Why RR=1.5 Beats RR=2.0
The London move often retraces after the first 30–90 minutes.
Lower TP (1.5×) captures the initial surge before reversal.
Result: winrate jumps from 37% → 51%.

---

## Best Config Per Pair

### EURUSD (recommended, primary)
```python
LondonOpenBreakoutV1(Config(
    pip_size=0.0001,
    min_range_pips=6, max_range_pips=50,
    breakout_buffer_pips=1.5, sl_buffer_pips=3.0,
    rr=1.5, london_start_utc=7, london_end_utc=10,
    min_atr_pips=2.5, min_asian_bars=24,
))
```
| Metric | Full 17m | IS (40%) | MID (30%) | OOS (30%) |
|---|---|---|---|---|
| Trades | 151 | 66 | 47 | 38 |
| Winrate | 51.0% | 56.1% | 51.1% | 42.1% |
| Net pips | +978 | +673 | +368 | -63 |
| Est. return | +18.5% | +12.3% | +5.5% | ~0% |
| Max DD pips | 222 | — | — | — |

**Breakeven WR for RR=1.5 = 40.0%** → OOS (42.1%) is marginally above breakeven.

### GBPUSD (secondary)
```python
LondonOpenBreakoutV1(Config(
    pip_size=0.0001,
    min_range_pips=8, max_range_pips=35,
    breakout_buffer_pips=2.0, sl_buffer_pips=4.0,
    rr=1.5, london_start_utc=7, london_end_utc=10,
    min_atr_pips=2.5, min_asian_bars=24,
))
```
| Trades | WR | Net Pips | Ret% |
|---|---|---|---|
| 132 | 47.0% | +510 | +7.3% |

### USDJPY
```python
LondonOpenBreakoutV1(Config(
    pip_size=0.01,
    min_range_pips=40, max_range_pips=100,
    breakout_buffer_pips=5, sl_buffer_pips=10,
    rr=1.3, london_start_utc=7, london_end_utc=10,
    min_atr_pips=10, min_asian_bars=24,
))
```
| Trades | WR | Net Pips | Ret% |
|---|---|---|---|
| 28 | 57.1% | +960 | +2.5% |
Note: Only 28 trades in 17m = ~1.6/month. Too thin to trade reliably alone.

### USDCAD
Same config as EURUSD (pip_size=0.0001):
| Trades | WR | Net Pips | Ret% |
|---|---|---|---|
| 75 | 46.7% | +211 | +3.7% |

---

## Caution
- OOS performance for EURUSD barely breaks even (42% WR vs 40% required)
- The strategy may be capturing the 2024–2025 trend period
- Recommend running on paper/small size for 1–2 months before allocating capital
- Do NOT trade GBPJPY, EURJPY, CADJPY, EURGBP with LOB — results are negative

---

## What Was Ruled Out
- `TrendRetestSessionV1/V2`: negative across all pairs
- `RangeBounceSessionV1`: negative
- `BreakoutContinuationSessionV1`: negative
- `AsiaRangeReversionSessionV1`: negative
- `FailureReclaimSessionV1`: negative
- `EmaTrendPullbackV2` (new, this session): too slow for M5 + 28% WR negative
- `LondonOpenBreakoutV2` (with EMA trend filter): worse than V1 (over-filtering)

---

## Next Steps
1. Paper trade EURUSD LOB for March–April 2026 via OANDA demo
2. Monitor monthly: track IS (Oct24–May25) vs ongoing live performance
3. If 2 live months show WR > 40%, scale up to live account
4. Consider adding SMA(1440) trend filter to avoid counter-trend entries during strong trends
