# InPlay maker short — independent additivity gate (2026-07-10)

- Verdict: **NO_PROMOTION**.
- Independent universe: `BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,AVAXUSDT`; no overlap with development symbols.
- Data gate: `PASS`; exact shared M5 timeline, cache-only, no internal gaps; max tail lag `9.92h`.
- Direction audit: `1064` short / `0` long signals.
- Stress full: N `42`, net `1.4389R`, PF `1.075`, unfilled `14.3%`.
- Chronological stress folds: `3/4` positive.
- Final 90d holdout: N `16`, net `2.0344R`, PF `1.286`.
- Symbol breadth: traded `2/5`, positive `1/5`.
- Gross-profit concentration: `67.7%` (gate `< 35%`).
- Failed gates: `stress_pf_1.075<1.2; symbols_with_trades_2<3; positive_symbols_1<2; gross_profit_concentration_0.677`.

Fixed one-combination test: offset 0.4 ATR, validity 24 bars, short-only, base and adverse costs. No grid or broker/live access.
The final 90-day holdout is evaluated once and is not used for symbol, parameter, or threshold selection.
PASS would permit only a risk=0 shadow/parity stage; it would not authorize money deployment.
