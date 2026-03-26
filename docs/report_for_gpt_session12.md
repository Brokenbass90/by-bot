# Bybit Algo Bot — отчёт по состоянию на 2026-03-26

## Контекст
Bybit perpetual futures бот на Python. Сервер: 64.226.73.119. Депозит ~$200.
Ведём разработку уже 12 сессий. Этот отчёт — итог последних сессий (10-12).

---

## 🟢 Что сейчас торгует в live (5 стратегий)

| Стратегия | Тип | Монеты | Статус |
|---|---|---|---|
| ASC1 (naклонный канал) | SHORT от верхней границы | ATOM, LINK, DOT | ✅ Live |
| ARF1 (горизонтальное сопротивление) | SHORT от уровня | LINK, LTC, SUI, DOT, ADA, BCH | ✅ Live |
| Breakout inplay | LONG пробои вверх | Top-10 динамически | ✅ Live |
| BTC/ETH Midterm pullback | LONG + SHORT | BTC, ETH | ✅ Live |
| Breakdown inplay | SHORT пробои вниз | BTC, ETH, SOL, LINK, ATOM, LTC | ✅ Live (добавлено сессия 10) |

Общая статистика с момента запуска: $100 → $200.93, PF=2.08, DD=3.65%.

---

## 🔬 Что исследовали и нашли

### Breakout expansion (24 комбо монет)
- Проверяли: стоит ли заменить динамический TOP-10 на фиксированный набор монет
- Результат: все 24 варианта не прошли по качеству
- Вывод: **динамический TOP-10 лучше любого фиксированного набора**. Изменений нет.

### ASC1 long режим (24 комбо)
- Проверяли: включить ли ALLOW_LONGS=1 в ASC1 (покупка от нижней границы канала)
- Результат: лонги добавляют +1.17% net, но снижают PF с 2.86 до 1.68
- Вывод: **держим шорты-only сейчас** (медвежий рынок). Один флаг в .env чтобы включить лонги при развороте.

### Лонговая готовность стратегий
- Breakout + Midterm: ✅ уже торгуют лонги
- ASC1: ✅ код готов, ждёт разворота рынка
- ARF1: ❌ шорты-only, нужна новая стратегия (лонг от поддержки)

---

## 🛠 Что было сделано технически

### Breakdown стратегия — был найден критический баг
Стратегия была ВКЛЮЧЕНА флагом в .env с самого начала, но никогда не исполнялась в live — не было live-wrapper файла. Написан `strategies/breakdown_live.py`, интегрирован в основной бот. Теперь реально торгует.

### /ai команда (DeepSeek) — найдено 4 бага в цепочке
1. Блокировка asyncio event loop → Threading fix
2. Snapshot вне thread (exception глотался молча) → перенесён внутрь thread
3. `float(None)` при старте бота → `float(x or 0)`
4. `ENABLE_PUMP_STRATEGY` NameError → правильное имя переменной

Итог: `/ai` теперь свободно общается на любые темы как senior партнёр.

### Монеты расширены по autoresearch
- ASC1: добавлен DOT (ATOM+LINK → ATOM+LINK+DOT, net +4.82%)
- Breakdown: добавлены LINK+ATOM+LTC (3 монеты → 6 монет, net +45%)

---

## 📋 Что планируем дальше (приоритеты)

1. **Midterm pullback improvement** — слабейшая стратегия (WR 46%, PF 1.3), нужен autoresearch
2. **Alpaca equities** — инфраструктура уже написана (bridge, autopilot, TG report), нужно API ключи и запустить paper trading
3. **Long от поддержки** — аналог ARF1 но лонги, новая стратегия `alt_support_reclaim_v1`
4. **Elder Triple Screen v11** — 1024 комбо autoresearch, запускается локально
5. **Trailing stop** — после накопления статистики

---

## Стек
- Python 3.11, asyncio, Bybit V5 API
- Telegram бот (команды + inline кнопки)
- DeepSeek AI overlay (`/ai`)
- Autoresearch grid-search (кастомный runner)
- Backtest engine (5-min kline, portfolio-level)
- Сервер: DigitalOcean Ubuntu, systemd сервис `bybot`
