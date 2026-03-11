# MASTER PLAN — bybit-bot-clean-v28
# Автор: Николай Булгаков | ИИ-ассистент: Claude (Anthropic)
# Дата: 2026-03-11 | Обновлять при каждой рабочей сессии

---

## 🔴 КРИТИЧНО (делать сейчас)

### [DONE] Рефакторинг: bot/ package Phase 1
- Создан пакет `bot/` с модулями: `env_helpers`, `utils`, `auth`, `diagnostics`, `symbol_state`
- Удалены ~190 строк дублирующего кода из `smart_pump_reversal_bot.py`
- Файл уменьшился с 6440 → 6251 строк
- Все imports проверены, shared state работает корректно

### [DONE] Auth flood fix в `_fetch_equity_live`
- Добавлена проверка `auth_disabled()` перед API-вызовом
- `errors.log` больше не флудит сотнями одинаковых строк после экспирации ключа
- Логирование ошибки происходит только при первом сбое (до срабатывания cooldown)

### [DONE] TradeState cleanup — убрать legacy дубли
**Файл:** `trade_state.py`
- `entry_avg_price` убрано из полей dataclass → добавлен `@property`, читает/пишет `avg`
- `reason_close` убрано из полей → добавлен `@property`, читает/пишет `close_reason`
- Добавлен `add_fill(role, price, qty, fee, ts)` — helper для заполнения fills
- Добавлен `realized_pnl_from_fills` — computed property для точного PnL
- Добавлен `best_pnl` — возвращает fills-based PnL если есть, иначе `realized_pnl`
- Все 32 usages `tr.avg` и 11 usages `tr.close_reason` в боте работают без изменений

**Остаток (Phase 2):** заполнять `fills` в реальных местах entry/exit confirm:
- `smart_pump_reversal_bot.py` line ~2672: `tr.avg = float(avg_ex)` + `tr.add_fill('entry', ...)`
- Аналогично при exit confirm (там где close_reason устанавливается)

### [DONE] impulse_weak — диагностика
**Анализ причины:**
- Условие: `max(body, rng) >= impulse_atr_mult * atr` где по умолчанию `impulse_atr_mult=1.0`
- Т.к. `body ≤ rng` всегда, проверка сводится к: `rng >= ATR(14)` на последней 4h свече
- 82% блоков = рынок находился в flat/ranging режиме (свечи меньше среднего ATR)
- Разбивка уже была: `impulse_weak` (size) / `impulse_body_weak` / `impulse_vol_weak`

**Что сделано:**
- `sr_inplay_retest.py`: добавлен атрибут `last_impulse_ratio` (= size/threshold, <1.0 = слабый)
- `breakout_live.py`: добавлен метод `last_impulse_ratio(symbol)`
- `smart_pump_reversal_bot.py`: при `impulse_weak` инкрементируем гистограммные счётчики q1..q4
- `bot/diagnostics.py`: q1..q4 добавлены в `_runtime_diag_snapshot`

**Интерпретация после накопления данных:**
- `q4` (75-100%) = "почти проходит" → снизить `BREAKOUT_IMPULSE_ATR_MULT` до 0.7-0.8
- `q1-q2` (0-50%) = глубокий flat → параметры не помогут, рынок не бьётся
- Если q1-q2 >> q4 → ждать активного рынка ИЛИ добавить `adaptive_range_short`

**TODO (следующий шаг):**
- Запустить бот, дать накопить 500+ `breakout_ns_impulse_weak`, посмотреть `/diag`
- Если q4 >> q1+q2 → установить `BREAKOUT_IMPULSE_ATR_MULT=0.75` в `.env` и тестировать
- Если q1+q2 >> q4 → рынок в глубоком flat, запустить `adaptive_range_short` бэктест

---

## 🟡 ВАЖНО (следующая очередь)

### [TODO] bot/ Phase 2 — BybitClient, telegram, db
**BybitClient (~400 строк, lines 2345-2650):**
- Самостоятельный класс, минимум внешних зависимостей
- Переехать в `bot/exchange/client.py`
- Зависимости на globals (DRY_RUN, POS_IS_ONEWAY, etc.) → передавать через config/конструктор

**Telegram (~200 строк, lines 600-750, 1574-1870):**
- `tg_send`, `tg_trade`, `tg_send_kb`, `tg_send_doc` → `bot/telegram/sender.py`
- `_handle_tg_command`, `tg_cmd_loop` → `bot/telegram/handler.py`
- `_send_report`, `reports_loop`, `_make_trade_chart` → `bot/telegram/reports.py`

**Database (~130 строк, lines 758-890):**
- `_db_init`, `_db_log_event`, `_db_log_ml_entry`, `_db_log_ml_close` → `bot/db.py`

### [TODO] bot/ Phase 3 — strategy entries, risk, portfolio
- `try_breakout_entry_async` (~265 строк) → `bot/strategies/live/breakout.py`
- `try_inplay_entry_async` → `bot/strategies/live/inplay.py`
- `try_retest_entry_async` → `bot/strategies/live/retest.py`
- `try_midterm_entry_async` → `bot/strategies/live/midterm.py`
- `try_range_entry_async` → `bot/strategies/live/range.py`
- Risk sizing functions → `bot/risk/sizer.py`
- Portfolio management → `bot/risk/portfolio.py`

**Цель Phase 3:** главный файл остаётся только оркестратором (~1000-1500 строк)

### [DONE] news_filter.py — подключить в live
**Статус:** Подключён. Блокирует только high-impact события (FOMC, NFP, CPI).
- `runtime/news_filter/events.csv` — 15 событий до июля 2026 (FOMC, NFP, CPI, PPI)
- `runtime/news_filter/policy.json` — политика по стратегиям
- `smart_pump_reversal_bot.py`: добавлен `_get_news_events_and_policy()` + check в `try_breakout_entry_async`
- TTL-кэш обновления: 5 мин (без перезапуска)
- Диагностика: `breakout_skip_news` в RUNTIME_COUNTER
- ENV: `NEWS_FILTER_ENABLE=0` — выключить, `NEWS_EVENTS_PATH` / `NEWS_POLICY_PATH` — override путей

**TODO (следующий шаг):**
- Добавить Telegram-команду `/news` — показать ближайшие события и статус blackout
- Сделать автообновление events.csv из бесплатного источника (ForexFactory или Investing.com API)
- Обновлять events.csv вручную каждый квартал

### [DONE] Архивирование мёртвых стратегий с manifest
- 36 файлов перемещены из `strategies/` → `archive/strategies_retired/`
- Создан `archive/strategies_retired/MANIFEST.md` с причинами отставки каждой стратегии
- Активных в `strategies/`: `inplay_breakout.py`, `btc_eth_midterm_pullback.py`, `signals.py`, `__init__.py`
- `adaptive_range_short.py` — помечен в манифесте как "revisit при flat-рынке"

### [DONE] Smoke-тесты для ключевых функций
**Файл:** `tests/smoke_test.py` — 8 тестов, все проходят (`python tests/smoke_test.py`):
1. `bot/env_helpers._env_bool`
2. `bot/auth.auth_disabled` + cooldown logic
3. `bot/diagnostics._diag_inc` + shared counter
4. `bot/symbol_state.SymState` + update_5m_bar + trim
5. `bot/utils.dist_pct` — signed (не abs!)
6. `trade_state.TradeState` — aliases, fills, PnL
7. `news_filter.is_news_blocked` — high/medium/FX/disabled scenarios
8. `diagnostics._runtime_diag_snapshot` — новые ключи histogram + news

---

## 🟢 ИДЕИ РАЗВИТИЯ (не срочно, но зафиксировать)

### Крипто
- **Funding carry**: торговать высокий funding rate как пассивный доход
  - Уже есть `runtime/funding_carry/` папка
  - При funding >0.05%/8h — держать лонг на споте и хедж на фьючерсах
- **adaptive_range_short**: запустить бэктест при flat-рынке как альтернативу breakout
- **Adaptive impulse threshold**: слабее в flat-рынке, жёстче в трендовом
- **ML overlay (post-demo)**: score-based ranking поверх существующих сигналов
  - Только после накопления ≥500 сделок на одну стратегию
  - Только для sizing cap, не для entry/exit логики

### Форекс
- Четвёртый независимый комбо: нужен до масштабирования капитала
  - Кандидат: `asia_range_reversion_session_v1` на USD/JPY (предсказуемые азиатские диапазоны)
- Auto-disable при rolling walk-forward decay (пока только запланировано)
- cTrader live execution adapter — ждём одобрения API

### Акции (Equities)
- Лучший кандидат: growth5_no_nvda_tsla_pair — +79.67% за 20 месяцев, 15/20 позитивных
- Paper trading на Alpaca — ждём одобрения аккаунта
- Расширить историю бэктеста до 3+ лет (включить кризис 2022)

### Кастомные индикаторы (для всех стратегий)
Написать в `custom_indicators.py` (файл уже существует):
1. **Volume Weighted ATR (VATR)**: ATR взвешенный по объёму — лучше фильтрует шум
2. **Trend Strength Index (TSI)**: комбинирует ADX + EMA alignment + volume ratio
3. **Session Volume Profile**: профиль объёма по сессиям (asia/europe/us) для SR уровней
4. **Impulse Quality Score**: числовой индикатор качества импульса (решает impulse_weak)
5. **Funding Carry Score**: оценка carry opportunity по funding rate + OI

### Telegram улучшения
- Разделить меню: `/crypto`, `/forex`, `/equities`, `/risk`, `/diag`
- Унифицировать формат алертов по всем веткам
- Добавить "что изменилось с последнего запуска"
- Telegram Web App для удобного управления (долгосрочно)

---

## Текущее состояние веток

| Ветка    | Статус     | Капитал  | Проблема               |
|----------|------------|----------|------------------------|
| Крипто   | 🟡 LIVE    | $100     | impulse_weak 82%       |
| Форекс   | 🔵 бэктест | —        | нет long-robust комбо  |
| Акции    | 🔵 бэктест | —        | ждём Alpaca approval   |

---

## Git / Deploy

```bash
# Локально (Mac):
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
git add .
git commit -m "refactor: phase 1 bot/ package + auth flood fix"
git push origin codex/dynamic-symbol-filters

# Deploy на сервер:
ssh -i ~/.ssh/by-bot root@SERVER_IP 'cd /path/to/bot && git pull && systemctl restart bybot'
```

---
_Последнее обновление: 2026-03-11 (сессия 2)_
