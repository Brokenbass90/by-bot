# XAU intraday flat baseline V2

Authority: research only. No live, broker, promotion, or risk authority.

V1 stopped before producing PnL because its generic 24/7 coverage gate treated
scheduled FX closures and holidays as feed failures. V2 changes only the
predeclared data-quality thresholds and the physical input receipt; it does not
change setup parameters after seeing strategy returns.

- Window: 2024-07-08 through 2025-09-30, end exclusive 2025-10-01.
- The reserved 2025-10-01 through 2026-06-30 outcomes are not used.
- Instrument/timeframe: XAUUSD, H1 aggregated from M5.
- Data gate: coverage >= 95%; longest non-scheduled gap <= 30 H1 bars; scheduled
  market closures >= 36 H1 bars are excluded by the existing coverage contract.
- Execution: completed-bar signal, current harness fill, stop-first within a bar.
- Flat contract: no entry on the first H1 bar at/after 20:55 UTC; an open
  position closes at that bar open (normally the 21:00 UTC bar).
- Fixed families: session breakout/retest, trend pullback, round-level sweep.
- Fixed parameters: 2R target, 1.5 ATR stop, six H1 bars max. Three variants total.
- Base costs: 1.0 bps fee/spread proxy plus 0.5 bps slippage per side.
- Stress costs: 2.0 bps fee/spread proxy plus 1.0 bps slippage per side.
- Survival screen: base and stress net R positive; at least 30 trades; at least
  three of four chronological folds positive.

This is a bounded baseline, not a new parameter search. Exact account-specific
bid/ask spread, session calendar, and broker contract remain promotion blockers.
