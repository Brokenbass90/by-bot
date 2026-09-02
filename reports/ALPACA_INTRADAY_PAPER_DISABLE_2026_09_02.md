# Alpaca intraday paper disabled — 2026-09-02

The two scheduled intraday routes were removed from the server crontab at the
owner's request:

- `run_equities_alpaca_intraday_dynamic_v1.sh --once`;
- `run_equities_alpaca_intraday_dynamic_v3_shadow.sh --once`.

No matching intraday process was active when the change was made. The main
Alpaca v38 manager, protective-exit manager, and read-only health-auditor routes
were preserved. No position, order, risk, or main Alpaca live-trading
configuration was changed; only the two intraday paper/shadow cron routes were
removed.

The pre-change crontab is recoverable from
`/root/crontab.backup_disable_alpaca_intraday_20260902_0625` on the server. Its
SHA-256 is recorded in the machine receipt.

Machine receipt:
`reports/receipts/ALPACA_INTRADAY_PAPER_DISABLE_2026_09_02.json`.
