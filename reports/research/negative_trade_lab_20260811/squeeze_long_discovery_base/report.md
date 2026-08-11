# Negative Trade Lab — squeeze_long_discovery_base

Generated: `2026-08-11T13:18:51.019610+00:00`

## Technical result

**Diagnostic class: `negative_gross_edge_plus_cost_drag`.**
Across **620** trades / **24** symbols, net was **-131.342R**: gross **-40.373R** minus costs **90.969R**. Mean net was **-0.2118R/trade**, t=**-6.74**, PF=**0.537**.

This is a descriptive decomposition. It rejects or diagnoses the measured run; it does not prove that a bucket filter will work out of sample.

## Exit-path decomposition separates entry failure from cost drag

| Exit path | Trades | Gross R | Costs R | Net R | Mean net R |
|---|---:|---:|---:|---:|---:|
| TRAIL_SL | 309 | -161.687 | 44.791 | -206.478 | -0.6682 |
| SL | 62 | -63.998 | 12.024 | -76.022 | -1.2262 |
| SL_same_bar | 3 | -0.552 | 0.452 | -1.004 | -0.3347 |
| TP1+SL_same_bar | 1 | 0.306 | 0.200 | 0.106 | 0.1056 |
| TP1+TRAIL_SL | 106 | 40.137 | 15.226 | 24.911 | 0.2350 |
| TP1+TP2+TRAIL_SL | 139 | 145.421 | 18.275 | 127.147 | 0.9147 |

## Regime and symbol concentration

### Regime

| Bucket | Trades | Gross R | Costs R | Net R | t |
|---|---:|---:|---:|---:|---:|
| bull_trend | 417 | -10.043 | 56.474 | -66.516 | -4.12 |
| bull_chop | 203 | -30.330 | 34.495 | -64.825 | -6.00 |

### Worst symbols

| Bucket | Trades | Gross R | Costs R | Net R | t |
|---|---:|---:|---:|---:|---:|
| PEOPLEUSDT | 36 | -17.605 | 5.768 | -23.373 | -5.98 |
| C98USDT | 46 | -13.443 | 7.796 | -21.239 | -4.49 |
| HFTUSDT | 32 | -8.558 | 4.779 | -13.337 | -3.52 |
| GALAUSDT | 37 | -6.754 | 6.463 | -13.217 | -2.96 |
| ORDIUSDT | 54 | -3.946 | 6.346 | -10.292 | -1.95 |
| SHIB1000USDT | 16 | -5.229 | 2.666 | -7.895 | -3.46 |
| AAVEUSDT | 19 | -3.676 | 3.259 | -6.935 | -1.98 |
| APTUSDT | 27 | -1.690 | 4.319 | -6.009 | -1.40 |
| CRVUSDT | 32 | -0.380 | 5.442 | -5.822 | -1.44 |
| OPUSDT | 30 | -1.115 | 4.676 | -5.792 | -1.30 |
| ARBUSDT | 17 | -2.222 | 2.877 | -5.100 | -1.58 |
| ICPUSDT | 18 | -1.880 | 2.504 | -4.385 | -1.65 |

## Falsifiable next experiments

1. Separate direct-stop trades from trades that reached TP1/trailing; do not tune one exit rule across both phenotypes.
2. For direct stops, add MFE/MAE and time-to-failure labels, then preregister one entry/regime hypothesis on the next untouched window.
3. For gross-positive but net-negative paths, test a minimum gross-edge-to-cost gate and lower-turnover exit variants. Do not assume maker entry helps impulse setups.
4. Treat worst-symbol and regime exclusions as hypotheses only; verify with leave-one-symbol-out and forward time splits before any ban or promotion.
5. Pass only the summarized proposal packet to the local LLM. The model may rank hypotheses but may not alter code, risk, orders, or promotion state.

## Data and limitations

- Data quality status: `pass`; usable 620 / 620; duplicates 0.
- Material bucket threshold: 13 trades.
- Buckets are descriptive diagnostics, not causal filters. Any proposed exclusion or parameter change requires preregistration and untouched time/symbol replication.
- Raw trade ledgers do not contain full intratrade price paths. MFE/MAE attribution requires the existing candle-forensics stage.
