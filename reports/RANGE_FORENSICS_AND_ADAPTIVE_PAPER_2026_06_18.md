# Range Forensics and Adaptive Alpaca Paper - 2026-06-18

## Server state

- Crypto bot: alive, `bear_chop`, live feed increasing, no open trades, no hard block, no safe mode.
- Risk-bearing sleeves: `flat_resistance_fade x0.30` and `range x0.25`.
- `range` is deployed short-only through `configs/range_short_only_canary.env`.
- ATT1, bounce, breakdown, IVB1 and midterm are enabled only as zero-risk/shadow observers.
- The dashboard strategy cards are historical closed-trade attribution. They are not the current risk-bearing roster.

## Exact range evidence

Source: `runtime/live_trade_events.jsonl` joined to exact entry fills and one-minute candles.

- 14 trades: net `-0.2542`, PF `0.885`, WR `35.7%`.
- Long: 11 trades, net `-0.7842`, PF `0.617`, WR `27.3%`.
- Short: 3 trades, net `+0.5301`, PF `4.364`, WR `66.7%`.
- Verdicts: 6 stop-then-reversed, 3 TP-then-continued, 2 clean wins, 2 stopped without a later reversal, 1 gave back profit.
- A blanket 10% wider stop is not approved. Some stopped trades later reversed, while other paths exceeded the wider level. Any wider stop must reduce quantity so dollar risk remains unchanged.
- `BOUNCE_TIME` is a three-hour market exit, not a stop. The two observed timed exits were profitable (`BERA +0.0642`, `APE +0.0992`).

Detailed artifact:

- `reports/trade_forensics/trade_forensics_20260618_175502_range_exact_v3_20260618.md`
- `reports/trade_forensics/trade_forensics_20260618_175502_range_exact_v3_20260618.jsonl`

## Range research

The backtest adapter previously ignored live `RANGE_ALLOW_LONG/SHORT`, `RANGE_SL_WIDTH_FRAC`, `RANGE_SL_ATR_MULT`, and `RANGE_CONFIRM_LIMIT`. This made side and stop comparisons non-equivalent to live. The adapter now consumes those settings and has a parity test.

Server research started:

- spec: `configs/autoresearch/range_live_side_exit_repair_v1.json`
- window: 180 days through 2026-06-18
- costs: 6 bps fee plus 2 bps slippage
- comparisons: long-only, short-only, both sides; reclaim/wick confirmation; 1.0x versus 1.1x stop distance at fixed account risk
- session: `range_live_repair_20260618`

## Alpaca adaptive_v1

`adaptive_v1` is now the real paper monthly driver, not shadow-only.

- Old v38 order cron disabled; its research/refresh artifacts remain available for comparison.
- Baseline adaptive selection refreshes once per trading day.
- The existing selection is managed every 30 minutes, avoiding intraday ranking churn.
- Paper capital boundary: `$1000`; target allocation: `70%` scaled by regime exposure.
- Current positions: AAPL, JPM and UNH, about `$700` total.
- All three entries filled and each has an active broker-hosted stop order.
- LLY was selected but correctly blocked by the 21-day post-trailing re-entry guard.
- `lively_config` runs as a separate no-order A/B shadow until multi-regime evidence exists.
- The first automatic manager tick exposed an ownership conflict: intraday cleanup recognized only the legacy v38 CSV and closed the new adaptive symbols. The monthly symbol loader now unions legacy and adaptive cycle files. A live paper verification preserved AAPL/JPM/UNH as monthly-owned and reported zero intraday slots consumed. The adaptive positions were reopened with broker stops after the fix.

First `$500` decision gate: five clean US trading sessions with correct fills, stable ownership between monthly/intraday managers, and broker protection present after every fill. If no execution incident occurs, review on 2026-06-25.

## Alpaca cleanup warning

The JPM `40410000 position not found` cleanup warning was the visible result of two issues: stale monthly ownership caused intraday cleanup to target a monthly symbol, then the position disappeared between listing and DELETE. Monthly ownership now unions all active cycle files. The client also preserves structured HTTP status/details and treats only Alpaca's exact missing-position code as already flat. Other 404/errors still alert.

## Strategy review entry points

- Elder EMA50: `strategies/elder_triple_screen_v2.py`; research `configs/autoresearch/elder_ema50_force_canonical_v1.json`.
- InPlay retest v3: `strategies/inplay_retest_v3.py`; tests `tests/test_inplay_retest_v3.py`; research `configs/autoresearch/inplay_retest_v3_level_retest_repair_v2.json`.
- Pump fade: `strategies/pump_fade_v2.py`; research `configs/autoresearch/pump_fade_v5_bear_window_v1.json`.
- Breakdown: `strategies/alt_inplay_breakdown_v1.py`; research `configs/autoresearch/breakdown_recent_bear_window_v2_entry_quality.json`.
- Trendline touch ATT1: `strategies/alt_trendline_touch_v1.py`, live wrapper `strategies/att1_live.py`.
- Slope break ASB1: `strategies/alt_slope_break_v1.py`, live wrapper `strategies/asb1_live.py`.

InPlay v3 and Elder support separate long/short switches. Pump-fade research is short-only. Current breakdown research is short-only. ATT1 is bidirectional. ASB1 has separate long/short switches. InPlay v3 includes horizontal pivot clusters and a regression-channel sloped level.

## Active research queue

- Elder EMA50 annual canonical search is active.
- The queued classic sequence waits for Elder, then runs InPlay v3, pump-fade and breakdown.
- Range live-parity side/exit research runs in parallel.

No strategy is promoted from these jobs until fee/slippage results and monthly/OOS stability pass their configured constraints.
