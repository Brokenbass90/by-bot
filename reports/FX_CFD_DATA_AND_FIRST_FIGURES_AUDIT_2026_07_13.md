# FX/CFD data and first-figures audit — 2026-07-13

Статус: `DATA_DIAGNOSTICS_ONLY`. Денег, broker calls и performance-прогона V3 не было.

## Короткий вывод

Реальные Dukascopy M5 данные уже существуют почти за два года; утверждение, что FX заблокирован полным отсутствием M5, неверно. Но ни один символ пока не является promotion-grade: календарные/загрузочные дыры не нормализованы, исторические новости и реальные OANDA costs не закреплены, а кодовый контракт V3 требует нескольких fail-closed ремонтов до вычисления PnL.

Старые V2 цифры уже есть и отрицательны. V3 — причинно более аккуратная ветка с физически раздельными long/short sleeves, но у неё пока нет замороженного performance runner. Первые честные приблизительные V3 цифры реалистичны через 2–4 дня после получения owner inputs; полный пяти-рукавный verdict — примерно через неделю. XAU/индексные CFD требуют отдельной очереди.

## Data-quality matrix

| Проверка | Факт | Вердикт |
|---|---|---|
| Grain/provenance | Dukascopy tick -> mid M5, шесть инструментов, примерно 728.4 дня; provenance: `logs/fx_cfd_backfill_gate_20260706/01_dukascopy_backfill_730d.log` | источник реален |
| Row counts | EURUSD 147862; GBPUSD 148422; USDJPY 148035; EURJPY 144854; GBPJPY 148477; XAUUSD 140756 | достаточно для диагностики |
| Source coverage | 0.991560 / 0.995427 / 0.992683 / 0.971400 / 0.995676 / 0.977101 в том же порядке | EURJPY/XAU слабее |
| Uniqueness/validity | duplicates=0; invalid OHLC=0; frozen input hashes совпадают | PASS |
| Missing runs | max 324 / 120 / 132 / 1440 / 96 / 276 M5; failed fetch hours 159 / 73 / 73 / 394 / 23 / 86 | FAIL promotion |
| Schedule normalization | off-schedule 401 / 386 / 407 / 392 / 404 / 288; incomplete H1 buckets 15 / 29 / 29 / 165 / 178 / 25 | нужен broker holiday calendar + refetch/merge |
| Timeliness | snapshot был примерно 171.5h stale на 2026-07-13 09:27 UTC | refresh required |
| News | нет hash-pinned macro history с полноценным двухлетним покрытием и instrument-currency filtering | BLOCKED |
| Costs | нет account-specific bid/ask p50/p95, commission и financing по symbol/session | BLOCKED |
| Leakage guard | V3 performance ещё не вычислялся; повторён только preflight | PASS |

Повторный локальный preflight 2026-07-13 воспроизвёл: диагностические `EURUSD, GBPUSD, USDJPY, GBPJPY`; promotion-grade symbols `0`; permission `DATA_DIAGNOSTICS_ONLY`. Каноническое evidence: `reports/research/fx_v3_preflight_20260711/`.

## Уже полученные первые цифры V2

Это честные diagnostic-only результаты, а не разрешение demo/live.

| Sleeve | Base PF / netR | Stress PF / netR | N |
|---|---:|---:|---:|
| impulse breakout/retest long | 0.793 / -4.06 | 0.609 / -8.61 | 26 |
| impulse breakout/retest short | 0.414 / -8.17 | 0.382 / -9.06 | 16 |
| sweep/reclaim long | 0.832 / -11.69 | 0.747 / -18.56 | 101 |
| sweep/reclaim short | 0.859 / -9.66 | 0.690 / -23.56 | 101 |
| range/pila long | 0.566 / -10.96 | 0.394 / -16.86 | 28 |
| range/pila short | 0.747 / -8.42 | 0.587 / -15.18 | 41 |

Evidence: `reports/research/fx_v2_gate_20260711/summary.md`. Все старые семейства остаются `NO_PROMOTION`; повторять их сетку или ослаблять gate запрещено.

## Ближайшие V3 семьи

1. `failed_break_retest_short_v3` — физически short-only: break -> reclaim -> более поздний первый retest.
2. `horizontal_range_rejection_v3` — отдельные long-only и short-only рукава от плоских горизонтальных границ.
3. `range_edge_expansion_retest_v3` — отдельные long-only и short-only рукава: замороженная граница диапазона -> expansion -> первый retest.

Итого это пять side-separated sleeves, а не три смешанных long/short стратегии.

## Что исправить до outcome

- `bot/fx_setups_v3.py`: проверка `min_resolved_reactions` сейчас fail-open при недостатке разрешённых реакций. Нужно выбрать строгую семантику, исправить, протестировать и перезаморозить до PnL.
- News artifact: `min_rows=1` и проверка только верхнеуровневых полей не доказывают двухлетнее покрытие. Нужны schema/type/range/duplicate/currency/density gates.
- Cost artifact: нужны uniqueness `symbol+session`, numeric/range guards, `p50 <= p95`, freshness и account-pricing identity; шесть дубликатов не могут считаться шестью режимами.
- `scripts/import_news_events_csv.py` несовместим с V3 schema (`ts_utc/title`, строковый impact вместо `ts/event`, numeric impact). Нужен нормализатор и фильтр валюты инструмента.
- Контракт должен заранее решить `H1 next-open` либо `H1 context + M15 execution`. Сейчас код фактически H1 (`h1_interval=60`, `execution_bar_seconds=3600`), несмотря на прежние слова о M15.
- `scripts/fetch_forex_oanda.py` получает только midpoint, полностью переписывает файл, не сохраняет bid/ask costs и не имеет XAUUSD mapping. Нужен resumable BA/cost collector.
- Текущий CFD scope — только XAUUSD; индексных CFD data/spec V3 пока нет.

## Что требуется от владельца

Депозит не требуется.

1. Создать/подтвердить OANDA v20 `fxTrade Practice` account.
2. Сохранить локально, не в чате, `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENV=practice`.
3. Сообщить regulatory division/регион, pricing model (`spread-only` или `commission/core`) и желаемые инструменты.
4. Выбрать лицензированный источник исторического macro calendar за 2024-07-08..2026-07-06 с UTC timestamp, currency, numeric impact и event name.

OANDA официально рекомендует practice endpoint для тестирования; bearer token позволяет получить доступные account IDs/instruments, а pricing API возвращает bid/ask: https://developer.oanda.com/rest-live-v20/development-guide/ , https://developer.oanda.com/rest-live-v20/account-ep/ , https://developer.oanda.com/rest-live-v20/pricing-ep/ . Доступные инструменты зависят от account/division, поэтому их нельзя угадывать из общего списка.

## Срок после получения inputs

- День 1: закрыть fail-open contracts, news normalization/currency scope, resumable BA ingestion, H1/M15 freeze; проверить account instruments; обновить EURUSD/GBPUSD/USDJPY.
- День 2–4: закрепить news и account costs; получить `>=3` clean majors; заморозить один runner и первые approximate V3 figures с costs/folds/embargo/holdout/LOSO.
- День 5–7: полный пяти-рукавный report и автоматический `NO_GO` либо `RESEARCH_PASS`.
- XAU/прочие CFD: отдельная очередь ориентировочно 5–10+ дней.
- Demo orders: только после strict PASS. Реальные деньги: только после не менее 30 чистых demo closes и отдельного owner approval.

Проверка этой сессии: 42 focused FX tests PASS; repo/live не изменялись.
