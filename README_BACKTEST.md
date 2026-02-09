# Backtest: сравнение стратегий за ~1 месяц

## Быстрый старт

1) Создайте виртуальное окружение и установите зависимости:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2) Запустите бэктест на 30 дней (5m свечи) для выбранных символов:

```bash
python3 backtest/run_month.py \
  --symbols SOLUSDT,ADAUSDT,SUIUSDT \
  --days 30 \
  --strategies range,bounce,pump_fade,inplay
```

Результаты появятся в папке `backtest_results/`:
- `summary.csv` — агрегированная таблица по стратегиям
- `summary_per_symbol.csv` — статистика по каждому символу
- `trades_<strategy>.csv` — список сделок по стратегии

## Важно
- Бэктест использует **публичные** эндпоинты Bybit (`/v5/market/kline`), ключи не нужны.
- Данные кэшируются в `data_cache/`.
- Модель исполнения — упрощённая: вход по close сигнальной свечи, выход по TP/SL на следующих свечах, комиссия/проскальзывание учитываются.

## Настройки
Основные параметры:
- `--risk_pct` риск на сделку (доля от equity)
- `--cap_notional` ограничение notional
- `--fee_bps` комиссия (bps) на сторону
- `--slippage_bps` проскальзывание (bps) на сторону

