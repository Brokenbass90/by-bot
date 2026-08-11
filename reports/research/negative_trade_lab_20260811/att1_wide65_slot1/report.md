# Negative Trade Lab — att1_wide65_slot1

Generated: `2026-08-11T13:18:51.322114+00:00`

## Technical result

**Diagnostic class: `positive_gross_edge_killed_by_costs`.**
Across **823** trades / **64** symbols, net was **-28.770R**: gross **19.339R** minus costs **48.109R**. Mean net was **-0.0350R/trade**, t=**-0.99**, PF=**0.932**.

This is a descriptive decomposition. It rejects or diagnoses the measured run; it does not prove that a bucket filter will work out of sample.

## Exit-path decomposition separates entry failure from cost drag

| Exit path | Trades | Gross R | Costs R | Net R | Mean net R |
|---|---:|---:|---:|---:|---:|
| SL | 393 | -396.992 | 23.721 | -420.713 | -1.0705 |
| TP1+SL | 9 | -2.063 | 0.461 | -2.524 | -0.2805 |
| EOP | 1 | -0.074 | 0.030 | -0.104 | -0.1036 |
| TIME | 1 | 0.754 | 0.057 | 0.697 | 0.6967 |
| SL_same_bar | 1 | 0.878 | 0.125 | 0.754 | 0.7536 |
| TP1+TP2 | 20 | 23.003 | 1.070 | 21.932 | 1.0966 |
| TRAIL_SL | 190 | 159.989 | 10.612 | 149.376 | 0.7862 |
| TP1+TRAIL_SL | 208 | 233.846 | 12.033 | 221.813 | 1.0664 |

## Regime and symbol concentration

### Regime

| Bucket | Trades | Gross R | Costs R | Net R | t |
|---|---:|---:|---:|---:|---:|
| unknown | 823 | 19.339 | 48.109 | -28.770 | -0.99 |

### Worst symbols

| Bucket | Trades | Gross R | Costs R | Net R | t |
|---|---:|---:|---:|---:|---:|
| ARBUSDT | 16 | -9.990 | 0.974 | -10.964 | -3.26 |
| XMRUSDT | 33 | -7.071 | 2.051 | -9.122 | -1.55 |
| ACTUSDT | 18 | -7.059 | 0.925 | -7.984 | -1.83 |
| GALAUSDT | 14 | -6.102 | 0.631 | -6.732 | -1.90 |
| CRVUSDT | 18 | -4.874 | 0.888 | -5.762 | -1.38 |
| AAVEUSDT | 23 | -4.318 | 1.410 | -5.728 | -1.12 |
| BNBUSDT | 19 | -3.720 | 1.677 | -5.396 | -1.22 |
| MEUSDT | 12 | -3.918 | 0.778 | -4.697 | -1.35 |
| 1000RATSUSDT | 17 | -3.997 | 0.689 | -4.686 | -1.04 |
| BIOUSDT | 14 | -4.035 | 0.633 | -4.668 | -1.21 |
| ACEUSDT | 24 | -3.225 | 1.315 | -4.540 | -0.94 |
| SHIB1000USDT | 6 | -3.940 | 0.518 | -4.458 | -2.02 |

## Falsifiable next experiments

1. Separate direct-stop trades from trades that reached TP1/trailing; do not tune one exit rule across both phenotypes.
2. For direct stops, add MFE/MAE and time-to-failure labels, then preregister one entry/regime hypothesis on the next untouched window.
3. For gross-positive but net-negative paths, test a minimum gross-edge-to-cost gate and lower-turnover exit variants. Do not assume maker entry helps impulse setups.
4. Treat worst-symbol and regime exclusions as hypotheses only; verify with leave-one-symbol-out and forward time splits before any ban or promotion.
5. Pass only the summarized proposal packet to the local LLM. The model may rank hypotheses but may not alter code, risk, orders, or promotion state.

## Data and limitations

- Data quality status: `pass`; usable 823 / 823; duplicates 0.
- Material bucket threshold: 17 trades.
- Buckets are descriptive diagnostics, not causal filters. Any proposed exclusion or parameter change requires preregistration and untouched time/symbol replication.
- Raw trade ledgers do not contain full intratrade price paths. MFE/MAE attribution requires the existing candle-forensics stage.
