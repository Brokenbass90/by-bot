# v28_19_debug_tools (v2)

Эти скрипты **не являются ботом**. Это утилиты для анализа CSV (trades*.csv) и точечной визуализации сделок.

## 1) Где брать CSV
CSV создаются вашим ботом после прогонов:
- `backtest_runs/<run_id>/trades_inplay.csv`
- `backtest_runs/<run_id>/trades_bounce.csv`
- `backtest_runs/<run_id>/trades.csv` (портфель)

`<run_id>` — папка прогона (например `20260206_154455_inplay_runner_30d_baseline`).

## 2) Примеры запуска

### Top/killers по CSV
```bash
python3 scripts/analyze_trades_csv.py /ABS/PATH/backtest_runs/<run_id>/trades_inplay.csv --top 15
python3 scripts/analyze_trades_csv.py /ABS/PATH/backtest_runs/<run_id>/trades_inplay.csv --symbol DOTUSDT
python3 scripts/find_killers.py /ABS/PATH/backtest_runs/<run_id> --top 15
```

### Плот одной сделки (Bybit public klines)
```bash
python3 scripts/plot_trade_bybit.py --symbol DOTUSDT --entry_ts 1738871100000 --exit_ts 1738875300000 --tf 5 --pad_bars 200
```

## 3) Если ругается на зависимости
Эти утилиты используют только стандартную библиотеку + matplotlib (для plot):
```bash
python3 -m pip install matplotlib
```

## 4) Важно
`bash scripts/run_core_suite.sh ...` запускается **внутри репозитория бота**, а не в папке debug_tools.
