# Bot Context (Short Memory)

## Local Repo
- Path: /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
- Branch: main
- Last known commit: 7eee905 (Add trend regime breakout and volatility breakout strategies)

## Live Server (DigitalOcean)
- Droplet name: ubuntu-s-1vcpu-1gb-fra1-01
- IPv4: 64.226.73.119
- Region: FRA1
- OS: Ubuntu 24.04 LTS
- Systemd service: bybot (active)
- Repo path on server (from systemd): /root/by-bot
- Bot process: /root/by-bot/.venv/bin/python /root/by-bot/smart_pump_reversal_bot.py

## Live Strategies (to fill from server .env)
- ENABLE_INPLAY_TRADING=
- ENABLE_BREAKOUT_TRADING=
- ENABLE_RETEST_TRADING=
- ENABLE_RANGE_TRADING=
- Bounce execution flag: BOUNCE_EXECUTE_TRADES=

## Risk / Sizing (to fill from server .env)
- RISK_PER_TRADE_PCT=
- BOT_CAPITAL_USD=
- CAP_NOTIONAL_TO_EQUITY=
- MAX_POSITIONS=
- MIN_NOTIONAL_USD=
- MIN_NOTIONAL_FILL_FRAC=

## Known Working Backtests (old-tests, end_date_utc=2026-02-01)
- combo_inplay_breakout_180d: net_pnl +50.93, PF 1.313, DD 7.0604, trades 720
- combo_inplay_breakout_360d: net_pnl +49.81, PF 1.228, DD 9.1557
- inplay_soft_180d: net_pnl +22.34, PF 1.400, DD 5.7071
- inplay_breakout_v2_60d: net_pnl +17.60, PF 3.890, DD 0.9141

## Recent Probes (2026-02-13, end_date_utc=2026-02-01, 60d, portfolio engine)
- probe_combo_inplay_breakout_60d (full 25 symbols): ending_equity 26.56, net_pnl -73.44, PF 0.758, DD 76.14
- probe_inplay_soft_60d (full 25 symbols): ending_equity 79.56, net_pnl -20.44, PF 0.735, DD 28.45
- probe_combo_inplay_breakout_60d_clean8 (exclude worst 8 symbols): ending_equity 119.04, net_pnl +19.04, PF 1.054, DD 22.10
- probe_inplay_60d_clean8 (inplay only, clean8): ending_equity 89.73, net_pnl -10.27, PF 0.952, DD 25.76
- probe_breakout_60d_clean8 (breakout only, clean8): ending_equity 138.42, net_pnl +38.42, PF 1.204, DD 14.13
- probe_combo_inplay_breakout_180d_clean8 (180d, clean8): ending_equity 217.70, net_pnl +117.70, PF 1.134, DD 21.99
- probe_breakout_180d_clean8 (180d, breakout only, clean8): ending_equity 162.25, net_pnl +62.25, PF 1.143, DD 21.26
- probe_breakout_180d_clean8_risk05 (180d, breakout only, clean8, risk 0.5%): ending_equity 129.10, net_pnl +29.10, PF 1.147, DD 11.15
- probe_combo_180d_clean8_risk05 (180d, combo, clean8, risk 0.5%): ending_equity 151.10, net_pnl +51.10, PF 1.138, DD 11.52
- probe_breakout_180d_clean8_regime_soft (EMA soft): ending_equity 162.25, net_pnl +62.25 (no change)
- probe_retest_60d_clean8 (retest_levels): ending_equity 0.00, net_pnl -100.00, PF 0.389, DD ~100 (failed)
- probe_trend_pullback_60d_clean8: ending_equity 0.00, net_pnl -100.00, PF 0.499, DD ~100 (failed)
- probe_trend_pullback_180d_clean8: ending_equity 0.00, net_pnl -100.00, PF 0.559, DD ~100 (failed)
- probe_trend_breakout_60d_clean8: no trades (0)

## Walk-forward (dynamic exclusion, 30d windows, base 25 symbols)
- walkforward_wf_combo_180d: total_net -62.46 (ending_equity ~37.54). Monthly PnL mostly negative. Dynamic exclusion as implemented is not yet stable.
- walkforward_wf_combo_180d_regime (EMA regime enabled): total_net -122.56 (ending_equity ~-22.56). Worse than baseline.
- walkforward_wf_breakout_180d: total_net -41.30 (ending_equity ~58.70). Still negative.

## Latest Bounce Backtest
- backtest_runs/20260212_141924_bounce_180d_combo_universe/summary.csv
- bounce ALL: trades 37, winrate 0.00, net_pnl -36.4484 (loss)

## Notes
- Bounce = уровневые отскоки (support/resistance). Not pump_fade.
- Pump_fade = дамп после сильного пампа.
- inplay и inplay_breakout = разные стратегии, часто работают в комбо.
- Full universe is currently unprofitable; symbol selection materially changes results.
## Dynamic Universe Plan (Bybit-wide)
- Filter: turnover24h >= 25M USDT
- ATR filter: 1h ATR% >= 0.35 (fallback 0.25 if too few)
- Exclude listings younger than 7 days
- Script: scripts/universe_scan.py (prints ranked symbols, optional out file)

## Open Questions / TODO
- Pull server .env flags and risk settings
- Decide: disable Bounce execution or rewrite logic
- Decide: enable inplay_breakout in live
