# Bybit Algo Bot — отчёт для GPT / Session 13 handoff
### Дата: 2026-03-26 | Ветка: codex/dynamic-symbol-filters

---

## 🤝 Контекст совместной работы

Это handoff-документ для параллельной работы двух AI (Claude + GPT).
Каждый видит полную картину. Дублирование работы = трата времени.

**Правило:** перед началом любого таска — сверь список ниже.

---

## 📊 Бот сейчас (live на 64.226.73.119)

**Депозит:** ~$200 | **Накоплено с запуска:** $100 → $200.93 | **PF=2.08, DD=3.65%**

| # | Стратегия | Тип | Монеты | Статус |
|---|-----------|-----|--------|--------|
| 1 | ASC1 (наклонный канал) | SHORT от верхней границы | ATOM, LINK, DOT | ✅ Live |
| 2 | ARF1 (горизонтальное сопротивление) | SHORT от уровня | LINK, LTC, SUI, DOT, ADA, BCH | ✅ Live |
| 3 | Breakout inplay | LONG пробои вверх | TOP-10 динамически | ✅ Live |
| 4 | BTC/ETH Midterm pullback | LONG + SHORT | BTC, ETH | ✅ Live (слабейшая, PF=1.3) |
| 5 | Breakdown inplay | SHORT пробои вниз | BTC, ETH, SOL, LINK, ATOM, LTC | ✅ Live (добавлена сессия 10) |
| 6 | micro_scalper_v1 | LONG/SHORT скальпинг 5m | BTC, ETH, SOL, BNB | ⏳ Добавлена в код, ждёт autoresearch |
| 7 | alt_support_reclaim_v1 (ASR1) | LONG от зон поддержки | BTC, ETH, SOL, LINK, ATOM, DOT... | ⏳ Добавлена в код, ждёт autoresearch |

---

## ✅ ЧТО СДЕЛАНО (сессии 1–13)

### Сессии 1–9 (база)
- [x] Bybit V5 API подключение, asyncio event loop
- [x] Telegram бот с inline кнопками
- [x] 4 live стратегии (ASC1, ARF1, Breakout, Midterm)
- [x] Backtest engine (`backtest/run_portfolio.py`)
- [x] Autoresearch grid-search runner (`scripts/run_strategy_autoresearch.py`)
- [x] Depozit рос с $100 до $200

### Сессия 10
- [x] **Breakdown стратегия** — найден критический баг (не было live wrapper файла), написан `strategies/breakdown_live.py`, реально запущен в live
- [x] **Расширение монет:** ASC1 ATOM+LINK → ATOM+LINK+DOT (+4.82% net backtest), Breakdown 3 → 6 монет (+45% net backtest)
- [x] **DeepSeek AI overlay** — исправлено 4 бага в цепочке: asyncio blocking, snapshot вне thread, `float(None)`, NameError. Команда `/ai` работает.
- [x] Telegram: упрощены кнопки (6 вместо 10), новое `/help` меню

### Сессии 11–12
- [x] **Autoresearch результаты:**
  - Breakout expansion (24 комбо): динамический TOP-10 лучше любого фиксированного набора
  - ASC1 long mode (24 комбо): лонги добавляют +1.17% net но снижают PF 2.86→1.68. Держим шорты. Флаг `ASC1_ALLOW_LONGS=1` готов.
- [x] **Elder Triple Screen v132** — стратегия в архиве, 1024-combo autoresearch запущен локально (PID 93240)
- [x] **DeepSeek action executor** — `/ai_deploy`, `/ai_diff`, `/ai_rollback`, `/ai_shadow` команды
- [x] **AI proposal система:** submit_proposal → approve/reject → execute → deploy to server

### Сессия 13 (текущая)
- [x] **micro_scalper_v1** написан (`strategies/micro_scalper_v1.py`):
  - 5-минутный скальпинг, сессионный фильтр UTC 7–17
  - Momentum + volume confirmation + tight SL/TP
  - Env prefix: `MSCALP_*`
  - Live wrapper: `strategies/micro_scalper_live.py`
  - Autoresearch spec: `configs/autoresearch/micro_scalper_v1_opt.json` (243 комбо)
- [x] **alt_support_reclaim_v1 (ASR1)** написан (`strategies/alt_support_reclaim_v1.py`):
  - LONG от зон поддержки (зеркало ARF1)
  - Кластеризация LOW-уровней, bullish bounce confirmation, RSI ≤ 50, anti-downtrend режим
  - Env prefix: `ASR1_*`
  - Live wrapper: `strategies/support_reclaim_live.py`
  - Autoresearch spec: `configs/autoresearch/support_reclaim_v1.json` (270 комбо)
- [x] **Зарегистрированы в backtest/run_portfolio.py** (5 мест: import, allowed, default, dict init, signal loop)
- [x] **Интегрированы в smart_pump_reversal_bot.py** (engines, env vars, entry functions, main loop)
- [x] **DeepSeek message splitting** — AI ответы >4000 символов разбиваются на чанки [1/N]...[N/N]
- [x] **deepseek_overlay.py system prompt** обновлён — упоминает стратегии 6 и 7
- [x] **Autoresearch запущен** (локально, фоновые процессы):
  - micro_scalper_v1: 243 комбо, результаты в `backtest_runs/`
  - support_reclaim_v1: 270 комбо, результаты в `backtest_runs/`
- [x] **Commit сделан**: `31b08e3` — ветка `codex/dynamic-symbol-filters`
- [x] **Git push**: нужно запустить вручную (`git push origin codex/dynamic-symbol-filters`) — VM без интернета

---

## ❌ ЧТО НЕ СДЕЛАНО (приоритеты для следующих сессий)

### 🔴 HIGH — требуют действия

| Задача | Статус | Кто берёт | Детали |
|--------|--------|-----------|--------|
| **Запустить autoresearch на своей машине** | ⚠️ Нужен запуск | Ты | `nohup python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/micro_scalper_v1_opt.json > /tmp/ms.log 2>&1 &` и то же для support_reclaim_v1.json |
| **Git push** | ⚠️ Нужен push | Ты | `cd ~/Documents/Work/bot-new/bybit-bot-clean-v28 && git push origin codex/dynamic-symbol-filters` |
| **Deploy новых файлов на сервер** | ❌ Не сделан | — | micro_scalper_live.py, support_reclaim_live.py, обновлённый smart_pump_reversal_bot.py |
| **Включить стратегии в .env** | ❌ Pending | — | После хорошего autoresearch: `ENABLE_MICRO_SCALPER_TRADING=1`, `ENABLE_SUPPORT_RECLAIM_TRADING=1` |
| **Elder Triple Screen результаты** | 🔄 Ждём PID 93240 | — | ~1024 комбо, запущен сессия 13 локально. Проверить: `cat ~/ts132_elder.log` |

### 🟡 MEDIUM — важные улучшения

| Задача | Статус | Детали |
|--------|--------|--------|
| **Midterm pullback autoresearch** | ❌ Не начат | Слабейшая стратегия (WR 46%, PF 1.3). Spec: нужно написать. Идея: изменить SL/TP ratio, добавить trend filter, попробовать другие таймфреймы входа |
| **Inline Telegram кнопки для AI approval** | ❌ Не сделан | callback_query handler не реализован. Сейчас approve через `/ai_approve <id>` — текстом. Нужно: кнопки ✅/❌ прямо в сообщении |
| **Proactive DeepSeek monitoring** | ❌ Не сделан | Фоновый hourly анализ: смотреть на PnL, DD, аномалии и писать в TG без запроса |
| **asyncio.Lock на STATE dict** | ❌ Не сделан | Потенциальный race condition при параллельных стратегиях. Низкий риск сейчас, но растёт с числом стратегий |

### 🟢 LOW — новые идеи / будущее

| Задача | Статус | Детали |
|--------|--------|--------|
| **Alpaca equities paper trading** | ❌ Ждёт API ключей | Инфраструктура написана (bridge, autopilot, TG report). Нужны ключи в .env: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` |
| **ARF1 longs (alt_support_reclaim_v1 live)** | ⏳ После autoresearch | Аналог ARF1 но для лонгов. Стратегия написана, нужны хорошие параметры |
| **Автоматическая ротация монет** | ❌ Не начата | Запись в WORKLOG: перепроверять allowlist монет каждые 2 недели по volume/volatility данным |
| **Ретест после пробоя (breakout + retest)** | ❌ Не завершён | Идея: после пробоя ждать возврата к уровню и войти там (лучшая цена). Записан как идея, не реализован |
| **Trailing stop** | ❌ Не начат | После накопления достаточно статистики (100+ трейдов на стратегию) |

---

## 🏗️ Архитектура / стек

```
smart_pump_reversal_bot.py   — главный asyncio бот
├── strategies/
│   ├── asc1_live.py          — ASC1 live engine
│   ├── flat_resistance_fade_live.py — ARF1 live engine
│   ├── inplay_live.py        — Breakout live engine
│   ├── midterm_pullback_live.py — Midterm live engine
│   ├── breakdown_live.py     — Breakdown live engine ✅ (сессия 10)
│   ├── micro_scalper_live.py — Scalper live engine ⏳ (сессия 13)
│   └── support_reclaim_live.py — ASR1 live engine ⏳ (сессия 13)
├── bot/
│   ├── deepseek_overlay.py   — DeepSeek AI chat (/ai команда)
│   ├── deepseek_action_executor.py — env patching + SSH deploy
│   └── deepseek_autoresearch_agent.py — AI-driven autoresearch
├── backtest/
│   └── run_portfolio.py      — backtest engine (все стратегии зарегистрированы)
├── scripts/
│   └── run_strategy_autoresearch.py — grid search runner
└── configs/autoresearch/
    ├── micro_scalper_v1_opt.json — 243 комбо
    └── support_reclaim_v1.json — 270 комбо
```

**Сервер:** DigitalOcean Ubuntu, 64.226.73.119, systemd `bybot`
**SSH:** `ssh -i ~/.ssh/by-bot root@64.226.73.119`
**Перезапуск:** `systemctl restart bybot`

---

## 📋 Как работает совместная разработка

**Claude (этот чат):**
- Пишет код, стратегии, конфиги
- Регистрирует стратегии в run_portfolio.py
- Запускает autoresearch локально
- Интегрирует в main bot

**GPT:**
- Анализирует результаты autoresearch (ranked_results.csv)
- Предлагает и пишет новые стратегии
- Проверяет код Claude на баги
- Пишет deploy-скрипты и документацию

**Правило передачи:**
1. Claude делает работу → коммит → пушит → пишет этот отчёт
2. Ты (пользователь) копируешь отчёт в GPT
3. GPT видит картину, берёт незакрытые задачи
4. GPT даёт код/план → ты проверяешь → Claude интегрирует

---

## 🚀 Следующие шаги (приоритет)

1. **Запустить git push** (из твоего терминала)
2. **Дождаться autoresearch результатов** micro_scalper + support_reclaim (~2-4 часа на 243/270 комбо)
3. **Проверить Elder v11 результаты** (`cat ~/ts132_elder.log | tail -20`)
4. **Если хорошие результаты** → написать deploy_session14.sh → запустить на сервере
5. **GPT задача:** написать spec для midterm pullback autoresearch (`configs/autoresearch/midterm_pullback_v1.json`)
