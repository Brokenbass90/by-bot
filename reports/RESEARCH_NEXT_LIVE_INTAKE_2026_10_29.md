# Следующий путь к LIVE: ограниченный intake исследований, 29 октября 2026

**Курс принят по существу. Выбор следующего LIVE пока не доказан.**
PUMP4/Monthly остаются в текущих разрешениях. Это read-only source review,
не новая стратегия, не разрешение запускать ещё три производственных процесса.

## Новые проверенные факты

Опубликован origin/research/fabrika-v1 **47b90288c55114ad7e730377c2265b54c5a97406**;
bb496fc/88b68b4/3cf44a9 входят в его историю. Прежняя PENDING_PUBLICATION на эти
SHA устарела. Код не сливался, не запускался; research checkout не изменялся.

1. **Funding: сначала исправить часы расчёта.** `fanding_mezhbirzhevoy.py:44–59`
   сохраняет close H4 (`x[4]`) под startTime (`x[0]`), затем :80–94 использует
   `pa[w1]`/`pb[w1]` как вход в начале8h окна. Цена относится к закрытию через4h,
   а funding начисляется за весь период сw1. Эти часы несовместимы. Это static
   finding, не результат повторного backtest. Нужна версия исследования с
   причинной исполнимой ценой и funding только при фактическом удержании.
   [Bybit Kline](https://bybit-exchange.github.io/docs/v5/market/kline),
   [Binance Kline/funding](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).
   Также universe выбирается по текущему turnover/доступности для2025 — survivorship
   limitation, не PIT universe; holding loop должен отвергать gaps, а не считать
   три любых доступных окна за24h.25bps — модель, не фактический тариф двух счетов.
   Net считать на весь занятый капитал пары, с четырьмя fills, basis, funding timing,
   риском незахеджированной ноги и расходами поддержания маржи на обеих площадках.
   Прежний FUNDING_CARRY_GATE NO-GO не переносится на новый механизм автоматически.
2. **Polymarket: следующий ограниченный инженерный gate.** ESPN collector:19–34
   хранит секунды записи после обработки; нет request_started/response_received,
   raw response hash и интервала last_nonfinal→first_final. При polling невозможно
   выдать first_seen за точное время первого появления факта у поставщика.
   Sequential13 leagues +timeouts не гарантируют60s cadence; parse exceptions:35
   сейчас теряются. Нужны QA и clocks перед сравнением с executable book.
   Официальный [Polymarket real-time feed](https://docs.polymarket.com/market-data/realtime-data)
   уже включает sports status и L2 book: использовать как источник venue-состояния
   и сопоставления; он сам по себе не независимый ранний сигнал относительно рынка.
   Проверка: внешний факт реально получен→рынок принимает заявки→видимый объём
   по цене после задержки+fee→исход по правилам конкретного рынка. Сравнение только
   сlast trade/0.95 не доказывает fill; неизвестная остановка/стакан = UNKNOWN.
3. **LIQ: существующий BybitV2.1 сохраняем.** Сначала исследование тех же25 монет;
   отдельный Binance источник нужен лишь конкретному prereg cross-venue вопросу.
   Binance liquidation stream публикует только последнее событие наsymbol за1000ms:
   его нельзя подмешивать как полную ленту с тем же QA.
   [Официальная семантика](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market).
4. **Unlocks/ИИ:** дляunlock сначала PITдаты и фактическая доступность источника;
   длягенератора — unique/valid/nonduplicate hypotheses и forward вердикты. Число
   формул/скриптов не является свидетельством денег. Эти линии не отнимают LIVE P0.

## Рекомендация и следующий измеримый результат

- Довести фактический lifecycle PUMP4; Monthly30Octsource→2Novconditionalentry/CASH.
  Последний operational readback описан в TRADING_OPERATIONS_AND_SHORT_HVOST_INTAKE;
  эта записка не является новой проверкой брокера и не меняет существующий срок GO.
- Из новой инженерии выбрать **один Polymarket fact→executable book DATA_ONLY gate**:
  таблица matched events, clock bounds, available size, net modeled edge, причины
  отказа. Сначала проверить, что уже пишет существующий монитор; не дублировать его.
- Claude: LIQ на существующем потоке и один исправленный funding screen. PASS_V_TEN
  не финансовыйPASS. Положительный результат без реальногоclock/source parity не
  передаётся в денежную очередь. Исследовательский producer Codex не переписывает.
- SHORT_HVOST/KITY не ускорять через смягчение gates. Новая денежная нога выбирается
  по опубликованной воспроизводимой экономике и исполнимости, без обещания даты прибыли.

Новые collector/unit/GO/APIorder/margin/risk/strategy изменения0. Новые процессы не
создавались. Сообщений Claude не отправлялось. [Source hashes](evidence/research_next_live_intake_20261029/source-review.json).
