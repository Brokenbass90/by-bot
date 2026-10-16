# TRADING OS REPORTING V1 — единый слой отчётов для всех рукавов (16.10.2026, Claude; production не тронут)

Канон вида = отчёты крипто-бота (`smart_pump_reversal_bot._make_trade_chart`): тёмный фон, cyan ВХОД, green ЦЕЛЬ, red СТОП,
orange ВЫХОД, пунктир в моменты входа/выхода. Распространяется на Alpaca, KITY, Elder/HEDGE и будущие рукава Фабрики.

## Принципы
1. **Одна схема событий** `ReportEvent v1` (`sobytiya_v1.py`) кормит И Telegram, И веб. Отдельной логики для веба нет.
2. **Одна правда о деньгах.** gross / fees / funding / net / qty / px берутся из неизменяемого журнала исполнения; отчёт ничего не
   пересчитывает. Проверка согласованности встроена: net = gross − fees + funding (иначе событие отклоняется). TAX-A читает те же строки.
3. **Отчёт никогда не блокирует торговлю**: отрисовка и отправка — после записи журнала, в try/except, с таймаутом; ошибка → строка
   в лог и текстовое сообщение без картинки.
4. У каждого события `evidence_id` — ссылка на квитанцию/строку журнала (аудит и налоги).
5. Режим на каждой карточке: LIVE / PAPER / SHADOW / DEMO. Деньги — со знаком и стрелкой ▲▼, не только цветом.

## События
| type | когда | обязательные поля сверх общих |
|---|---|---|
| ENTRY_FILLED | исполнение входа | symbol, side, qty, px, ccy (+ stop_px, targets, slippage_bps) |
| PROTECTION_BOUND | нативный стоп подтверждён биржей | symbol, stop_px |
| STOP_MOVED | храповик / перенос стопа | symbol, stop_px, stop_px_prev |
| PARTIAL_FILL | частичное исполнение | symbol, side, qty, px, qty_planned |
| EXIT_FILLED | выход | symbol, side, qty, px, reason, ccy (+ net_pnl) |
| FAILED_SAFE_FLAT | попытка не прошла целиком, всё закрыто | reason, owner_flat, legs, net_pnl, ccy |
| NO_SEND | ордер не отправлен (безопасный отказ) | reason |
| ACCOUNTING_FINAL | итоговый учёт сделки/корзины | gross_pnl, fees, funding, net_pnl, ccy |
Общие: type, ts_ms, sleeve, venue, strategy, evidence_id, mode.

## Файлы (research_lab/otchety/)
| файл | что |
|---|---|
| `sobytiya_v1.py` | схема, проверка, `dlya_lenty()` → формат существующей веб-ленты, адаптер `iz_kity_terminal()` |
| `stil.py` | палитра крипто-бота, ▲▼ деньги, длительность, словарь причин по-русски |
| `karta_sdelki.py` | карточка одной сделки (свечи, вход/стоп/цели/выход, объём, комиссии, фандинг, проскальзывание, время в позиции, evidence) |
| `karta_korzina.py` | многоногая корзина и FAILED_SAFE_FLAT / NO_SEND (ноги, защита, шкала GO → отправки → дедлайн) |
| `karta_portfel.py` | дневная сводка портфеля по рукавам (открытый риск, реализ./нереализ., здоровье) |
| `tekst_tg.py` | подпись Telegram (≤ 1024) для каждого типа |
| `demo_otchety.py` | 5 образцов; KITY — по НАСТОЯЩЕЙ квитанции 16.10 |
| `tests/test_otchety_v1.py` | 3 теста (адаптер KITY, согласованность учёта, формат ленты) |

## Что подключает Codex (после KITY latency-P0)
1. **Telegram.** На запись события в журнал рукава: собрать `ReportEvent` → `tekst_tg.podpis(e)` + картинка
   (`karta_sdelki` для одиночной сделки, `karta_korzina` для корзины/отказа) → существующий sendPhoto
   (`smart_pump_reversal_bot.tg_send_photo` / `equities_alpaca_tg_report._tg_send_photo`). Раз в день `karta_portfel`.
   KITY: после терминальной квитанции — `iz_kity_terminal(квитанция)` → готовые события.
2. **Веб-лента.** `sobytiya_v1.dlya_lenty(e)` даёт строку в формате `web/activity_feed.read_trade_events`; дописать в
   `EVENT_RU` новые типы (protection_bound, stop_moved, failed_safe_flat, no_send, accounting_final).
3. **График в вебе.** `/trades/chart`: добавить `venue=alpaca` (свечи Alpaca Market Data) — ответ того же вида
   `{time_ms, open, high, low, close, volume}`; фронт не меняется.
4. **Карточка сделки в вебе** (`/trades/{evidence_id}`): та же картинка большая + лента исполнения по времени из событий этой
   сделки: сигнал → намерение → ENTRY_FILLED → PROTECTION_BOUND → STOP_MOVED… → EXIT_FILLED → ACCOUNTING_FINAL.
5. **Портфель в вебе** (`/portfolio`): таблица как `karta_portfel` по всем рукавам + последние 10 событий + ссылки evidence.
   Источник — те же события; SHADOW-рукава серым, денег не суммируются.
6. Зависимость: `matplotlib` в окружении бота/веба. Старый веб сейчас остановлен Codex — включение отдельным решением.
