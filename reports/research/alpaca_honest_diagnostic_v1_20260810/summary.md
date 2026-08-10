# Alpaca honest diagnostic v1

Verdict: `NEEDS_REVISION / RESEARCH_ONLY` until PIT membership, authoritative XNYS sessions, corporate actions and broker-calibrated intraday data are pinned.

| window | arm | cost/side | return | daily DD | PF realized | trades | avg exposure |
|---|---|---:|---:|---:|---:|---:|---:|
| bear_2022_survivor_proxy | v38_successor_gated | 5 bps | -2.75% | 3.97% | 0.383 | 7 | 2.9% |
| bear_2022_survivor_proxy | v38_successor_gated | 10 bps | -2.89% | 4.00% | 0.363 | 7 | 2.9% |
| bear_2022_survivor_proxy | v38_successor_ungated | 5 bps | -4.41% | 10.18% | 0.650 | 15 | 13.4% |
| bear_2022_survivor_proxy | v38_successor_ungated | 10 bps | -4.81% | 10.42% | 0.624 | 15 | 13.4% |
| bear_2022_survivor_proxy | adaptive_v1_gated | 5 bps | -5.38% | 6.49% | 0.364 | 14 | 14.3% |
| bear_2022_survivor_proxy | adaptive_v1_gated | 10 bps | -5.63% | 6.58% | 0.345 | 14 | 14.3% |
| bear_2022_survivor_proxy | adaptive_v1_ungated | 5 bps | -11.02% | 12.15% | 0.249 | 26 | 27.5% |
| bear_2022_survivor_proxy | adaptive_v1_ungated | 10 bps | -11.44% | 12.50% | 0.234 | 26 | 27.5% |
| live_universe_2024_2026_cached_intraday_proxy | v38_successor_gated | 5 bps | +31.88% | 7.61% | 1.919 | 65 | 26.6% |
| live_universe_2024_2026_cached_intraday_proxy | v38_successor_gated | 10 bps | +30.16% | 7.84% | 1.863 | 65 | 26.6% |
| live_universe_2024_2026_cached_intraday_proxy | v38_successor_ungated | 5 bps | +24.43% | 8.72% | 1.600 | 69 | 28.4% |
| live_universe_2024_2026_cached_intraday_proxy | v38_successor_ungated | 10 bps | +22.67% | 8.89% | 1.553 | 69 | 28.4% |
| live_universe_2024_2026_cached_intraday_proxy | adaptive_v1_gated | 5 bps | +20.66% | 4.78% | 1.974 | 70 | 31.2% |
| live_universe_2024_2026_cached_intraday_proxy | adaptive_v1_gated | 10 bps | +18.75% | 4.94% | 1.856 | 70 | 31.5% |
| live_universe_2024_2026_cached_intraday_proxy | adaptive_v1_ungated | 5 bps | +16.61% | 6.51% | 1.631 | 78 | 33.4% |
| live_universe_2024_2026_cached_intraday_proxy | adaptive_v1_ungated | 10 bps | +14.62% | 6.74% | 1.540 | 78 | 33.7% |

## What is repaired

- completed calendar-month close -> next observed session open;
- one cash ledger, fractional quantities and 70% target gross exposure;
- costs on every buy and sell, including gaps and rotations;
- deployable simple-stop plus next-session daily ratchet proxy;
- retained positions are not fictitiously sold/rebought;
- daily MTM and drawdown include initial capital.

## Why this is still not promotion grade

- fixed current-survivor universes rather than point-in-time membership;
- calendar inferred from observed SPY sessions rather than authoritative Alpaca XNYS ledger;
- cached data lacks a pinned corporate-action and delisting ledger;
- daily close ratchet proxy cannot reproduce the live 15-minute observation path;
- historical cost assumptions are not yet calibrated to broker order lifecycle receipts;
- the untouched August-November 2026 forward outcome remains sealed.
