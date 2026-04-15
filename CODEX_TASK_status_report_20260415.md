# Отчёт о состоянии проекта — 2026-04-15
# Для синхронизации: Claude + Codex + владелец

---

## ЧТО СДЕЛАНО СЕГОДНЯ (2026-04-15)

### 1. ATT1/ASM1 — WF-22 валидация ЗАВЕРШЕНА ✅

**ATT1 (alt_trendline_touch_v1)**
- Прогнали 22 скользящих окна по 45 дней
- Средний PF = 1.35, последние 9 окон подряд PF > 1.0
- Решение: **DEPLOY** с риск-мультом 0.70×

**ASM1 (alt_sloped_momentum_v1)**
- 0 сделок в 10 из 22 окон, PF 0.44–0.70 в январе-феврале 2026
- Решение: **ВЫКЛЮЧИТЬ**, перевключить когда 3+ окна подряд PF≥1.2

Конфиг обновлён: `configs/core3_live_canary_20260411_sloped_momentum.env`

---

### 2. Интеграция ATT1/ASM1 в бот — ЗАВЕРШЕНА ✅

GPT написал, мы проверили и прошли smoke tests (10/10):
- `bot/entry_guard.py` — EntryCircuitBreaker (3 ошибки → пауза 90 сек)
- `bot/runner_state.py` — единый helper для trail/TP/time-stop
- В `smart_pump_reversal_bot.py`:
  - `_ENTRY_RESERVATION_LOCK` (asyncio) — защита от двойных входов
  - `try_att1_entry_async()` и `try_asm1_entry_async()` — подключены к главному циклу
  - `EntryCircuitBreaker` интегрирован

---

### 3. Walk-forward runner — ИСПРАВЛЕН ✅

Файл: `scripts/run_sloped_wf_quick.py`

Два бага исправлены:
- `_build_windows`: генерировал 1 окно вместо 22 (неверное условие выхода)
- Переменная окружения: `CACHE_ONLY` → `BACKTEST_CACHE_ONLY`

---

### 4. Alpaca fractional shares — ИСПРАВЛЕНО ✅

Файл: `scripts/equities_alpaca_intraday_bridge.py`

Баг: `max(1, int(notional/price))` → минимум 1 акция NVDA ($880) вместо $80
Исправление: флаг `ALPACA_FRACTIONAL_SHARES=1` → `round(notional/price, 3)`

Новые конфиги:
- `configs/alpaca_small_cap_500eur.env` — для €500/$550
- `configs/alpaca_1000usd.env` — для $1000

---

### 5. VSM1 — ЗАДЕБАЖЕН и ЗАКРЫТ ❌

Стратегия `alt_volume_spike_momentum_v1.py` (5m volume spike scalper)

**Баг 0-трейдов найден**: `MIN_NOTIONAL_FILL_FRAC=0.40` убивал все сделки.
С tight SL (0.5 ATR) нужен огромный notional чтобы рискнуть $1 →
fill ratio = 3%, порог 40% → 0 сделок.

**Результаты sweep (12 конфигов, 90 дней, 3 символа)**:
```
SL=0.5, spike=1.5x  → PF=0.13, WR=10%, 204 сделки  ← TERRIBLE
SL=0.8, spike=2.0x  → PF=0.21, WR=15%,  40 сделки  ← Лучший, но всё равно < 1.0
```

**Причина**: паттерн "компрессия + спайк" на 5-минутном ТФ — это шум.
Концепция правильная, но нужен 15m/1h таймфрейм.

**Решение**: SHELVED (помечен в коде). Переделать под 1h если нужно.

---

### 6. Задеплоен CODEX-task для ATT1

`CODEX_TASK_att1_canary_deploy.md` — пошаговая инструкция для сервера.

---

### 7. Commit сделан

Ветка: `codex/dynamic-symbol-filters`
Коммит: `983ceaf` + `130a5c4`

---

## СТАТУС СЕРВЕРА СЕЙЧАС

```
Крипта (Bybit):  МОЛЧИТ — нет активных стратегий в трейдинге
Alpaca:          Сообщения приходят, но НЕ ТОРГУЕТ
```

**Почему Alpaca не торгует**: скорее всего либо `ALPACA_FRACTIONAL_SHARES` не в конфиге,
либо fractional qty обрезается до 0 (старый баг). После деплоя нового кода — должно заработать.

**Почему крипта молчит**: ATT1 ещё не задеплоен на сервере. Код написан, но сервер ещё на старой версии.

---

## ЧТО НАДО СДЕЛАТЬ CODEX'у ЗАВТРА

### Приоритет 1 — Сервер (критично, бот стоит)

1. Зайти на сервер и сделать `git pull origin codex/dynamic-symbol-filters`
2. Запустить `python3 tests/smoke_test.py` — должно быть 10/10
3. Обновить конфиг на сервере: включить `ENABLE_ATT1_TRADING=1`, `ATT1_RISK_MULT=0.70`
4. Перезапустить бот
5. Для Alpaca: добавить `ALPACA_FRACTIONAL_SHARES=1` и `INTRADAY_NOTIONAL_USD=150`
6. Следить за логами 24ч — см. `CODEX_TASK_att1_canary_deploy.md`

### Приоритет 2 — Портфель крипты (диверсификация)

Текущий портфель: только ATT1. Нет диверсификации по режимам.

Что надо добавить для устойчивого портфеля (без красных месяцев):
```
Нужно              Статус
───────────────────────────────────────────────
Trend strategy     ATT1 ✅ уже есть
Mean-reversion     ? нет ничего для flat рынка
Momentum breakout  TS132 есть, нужна WF-22
Pump fade          pump_fade_v4r — нужна WF
Short scalper      нет хорошей стратегии
```

**Задача**: прогнать WF-22 для `triple_screen_v132` (TS132) и `pump_fade_v4r`,
чтобы понять что добавить рядом с ATT1.

### Приоритет 3 — Elder Triple Screen (есть CODEX task)

`CODEX_TASK_elder_fix.md` — уже готовый план. Elder нужно исправить
(RSI пороги слишком строгие, TP слишком далеко).
Если Elder заработает — будет отличная диверсификация с ATT1.

### Приоритет 4 — WebSocket диагностика

Есть сообщения оператора о 66% дисконнектах Alpaca WebSocket.
Файл: `ws_transport_guard_state.json` — нужно проверить на сервере.

---

## ПЛАН ДИВЕРСИФИКАЦИИ КРИПТО-ПОРТФЕЛЯ

Цель: портфель который **не несёт красных месяцев** за счёт некоррелированных стратегий.

```
Стратегия          Режим рынка    RR      Частота
────────────────────────────────────────────────
ATT1               Trend/flat     2.5:1   1/день
Elder v2 (после фикса)  Trend    2.0:1   2/день
TS132 (если WF OK) Любой          2.0:1   3/день
pump_fade_v4r      Volatile       1.5:1   1-2/день
```

Это даёт ~7-10 сделок в день на 8 символах — хорошая диверсификация.

---

## ПАРАМЕТРЫ ALPACA ДЛЯ $1000

```
INTRADAY_NOTIONAL_USD=150          # $150 на позицию
INTRADAY_MAX_POSITIONS=3           # 3 позиции = $450 = 45% капитала
INTRADAY_MAX_DAILY_LOSS_PCT=2.5    # Стоп: $25/день
ALPACA_FRACTIONAL_SHARES=1         # Обязательно для NVDA, META
INTRADAY_SYMBOLS=AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AMD
```

Реалистичная цель: 2-4% в месяц = **$20-40/месяц** с $1000.

---

## БУКВАЛЬНО СЛЕДУЮЩИЙ ШАГ (для владельца)

1. Закинуть $1000 на Alpaca
2. Передать Codex'у этот файл + `CODEX_TASK_att1_canary_deploy.md`
3. Codex деплоит сегодня/завтра
4. Мы с Claude работаем над Elder + TS132 WF валидацией
