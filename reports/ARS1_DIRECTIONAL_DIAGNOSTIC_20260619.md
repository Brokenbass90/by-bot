# ARS1 directional diagnostic - 2026-06-19

Source: `range_scalp_v1_annual_repair_v3_r004`, 360 days through 2026-04-01,
next-bar-open entries, 6 bps fee plus 2 bps slippage per side.

## Aggregate

| Side | Trades | Net PnL | PF |
|---|---:|---:|---:|
| Long | 65 | +9.6346 | 1.619 |
| Short | 43 | +6.9803 | 1.791 |
| Combined | 108 | +16.61 | 1.682 |

## Monthly PnL by side

| Month | Long | Short |
|---|---:|---:|
| 2025-04 | +0.9096 | -0.3060 |
| 2025-05 | -1.0841 | +0.8484 |
| 2025-06 | +3.0186 | -0.5507 |
| 2025-07 | +0.4111 | -0.3364 |
| 2025-08 | -2.5724 | +0.8872 |
| 2025-09 | 0.0000 | +1.7385 |
| 2025-10 | -2.4776 | -1.7709 |
| 2025-11 | -2.7451 | +2.5692 |
| 2025-12 | -0.9750 | +4.1350 |
| 2026-01 | +1.2539 | +1.4712 |
| 2026-02 | +13.8956 | -1.7053 |

## Technical finding

Both directions have positive aggregate expectancy, but neither direction is
stable by itself. A regime-side switch would avoid several wrong-direction
months, especially long exposure in late-2025 bear conditions, but it would not
fix 2025-10 where both directions lost. Promotion therefore requires an
additional range-quality or breakout-avoidance condition and fresh OOS
validation. The current live Range implementation is a different strategy and
must not inherit these ARS1 metrics.
