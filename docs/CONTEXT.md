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

## Latest Bounce Backtest
- backtest_runs/20260212_141924_bounce_180d_combo_universe/summary.csv
- bounce ALL: trades 37, winrate 0.00, net_pnl -36.4484 (loss)

## Notes
- Bounce = уровневые отскоки (support/resistance). Not pump_fade.
- Pump_fade = дамп после сильного пампа.
- inplay и inplay_breakout = разные стратегии, часто работают в комбо.

## Open Questions / TODO
- Pull server .env flags and risk settings
- Decide: disable Bounce execution or rewrite logic
- Decide: enable inplay_breakout in live
