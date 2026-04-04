# CODEX_TODO — Tasks for Codex/GPT
_Составлено: 2026-04-01 | Проект: bybit-bot-clean-v28_

Это задачи, которые требуют доступа к серверу или внешних ключей.
Всё остальное уже сделано и лежит в репозитории.

---

## 🔴 ПРИОРИТЕТ 1 — Деплой на сервер (делай в первую очередь)

### Задача 1.1 — Запустить скрипт деплоя

Готовый скрипт уже в репозитории. Просто запусти его:

```bash
bash scripts/deploy_autonomy.sh
```

Скрипт сделает всё сам:
- Скопирует все AI-файлы на сервер (`rsync`)
- Проверит импорты на сервере
- Перезапустит бота (`systemctl restart bybot`)
- Настроит три cron-задачи

**Если SSH ключ не на дефолтном месте:**
```bash
SSH_KEY=~/.ssh/твой_ключ bash scripts/deploy_autonomy.sh
```

**Dry-run (посмотреть что будет, без изменений):**
```bash
bash scripts/deploy_autonomy.sh --dry-run
```

---

### Задача 1.2 — Проверить что бот запустился с новыми модулями

После деплоя на сервере выполни:
```bash
ssh root@64.226.73.119 'cd /root/by-bot && python3 -c "
from bot.health_gate import gate
from bot.family_profiles import profiles
from bot.deepseek_research_gate import gate as rg
print(\"health_gate:\", gate.status_report()[:80])
print(\"family_profiles BTC sl:\", profiles.scale(\"BTCUSDT\",\"sl\",1.0))
print(\"research_gate:\", rg.status_report()[:80])
"'
```

Все три строки должны вывести `OK` или данные без ошибок.

---

## 🟡 ПРИОРИТЕТ 2 — Настройка после деплоя

### Задача 2.1 — Добавить DeepSeek API ключ (если ещё нет)

Проверь что на сервере в `configs/local.env` или `configs/server.env` есть:
```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_ENABLED=1
```

Без этого `deepseek_weekly_cron.py` будет запускаться, но не сможет звонить в AI.

---

### Задача 2.2 — Первый ручной запуск equity_curve_autopilot

Это генерирует `configs/strategy_health.json` — без него `health_gate` не работает:
```bash
ssh root@64.226.73.119 'cd /root/by-bot && python3 scripts/equity_curve_autopilot.py --no-tg'
```

Если выдаёт `ERROR: No backtest run found` — значит нужно сначала запустить бэктест:
```bash
ssh root@64.226.73.119 'cd /root/by-bot && python3 backtest/run_portfolio.py \
  --strategies inplay_breakout,alt_sloped_channel_v1,alt_resistance_fade_v1 \
  --days 90 --symbols BTCUSDT,ETHUSDT,SOLUSDT'
```

---

### Задача 2.3 — Первый ручной запуск deepseek_weekly_cron

Проверить что еженедельный аудит работает:
```bash
ssh root@64.226.73.119 'cd /root/by-bot && \
  source configs/local.env && \
  python3 scripts/deepseek_weekly_cron.py --dry-run'
```

`--dry-run` не отправляет реальные запросы к DeepSeek, просто показывает что будет делать.

---

## 🟢 ПРИОРИТЕТ 3 — Alpaca (когда захочешь включить auto-exit)

### Задача 3.1 — Протестировать auto-exit в dry-run режиме

В `configs/alpaca_paper_local.env` добавь:
```
ALPACA_AUTO_EXIT_ENABLED=1
ALPACA_AUTO_EXIT_DRY_RUN=1
ALPACA_AUTO_EXIT_MIN_LOSS_PCT=-8.0
```

Потом запусти вручную:
```bash
python3 scripts/equities_midmonth_monitor.py
```

Посмотри что в Telegram написало "🤖 [DRY RUN] Would close..." — если логика правильная,
убери `ALPACA_AUTO_EXIT_DRY_RUN=1` (или поставь `0`).

**НЕ включай `ALPACA_AUTO_EXIT_ENABLED=1` без dry-run периода!**

---

### Задача 3.2 — Расширить intraday тикеры (NVDA, META и т.д.)

Новые тикеры уже в `configs/intraday_config.json`. Но нужны M5 данные в кеше.
Если есть скрипт для скачивания данных:
```bash
python3 scripts/download_equity_m5.py --tickers NVDA,META,MSFT,AMZN,AAPL,AMD,PLTR
```

После скачивания — в `configs/intraday_config.json` уже всё настроено, ничего менять не нужно.

---

## 🔵 ПРИОРИТЕТ 4 — Claude Monthly Analyst (когда будет API ключ)

### Задача 4.1 — Создать файл с ключом

```bash
cp configs/claude_analyst.env.template configs/claude_analyst.env
nano configs/claude_analyst.env
# Заполни ANTHROPIC_API_KEY=sk-ant-...
```

### Задача 4.2 — Первый тест

```bash
python3 scripts/claude_monthly_analyst.py --report
```

Если выдаёт отчёт — всё работает. Команда `/ai_monthly` в Telegram тоже будет работать.

---

## 📋 Что уже сделано (не трогай)

| Файл | Статус |
|------|--------|
| `bot/health_gate.py` | ✅ готов |
| `bot/deepseek_research_gate.py` | ✅ готов |
| `bot/family_profiles.py` | ✅ готов, BTC/ETH/ALTS профили |
| `bot/trade_learning_loop.py` | ✅ готов |
| `bot/deepseek_overlay.py` | ✅ готов |
| `bot/deepseek_autoresearch_agent.py` | ✅ готов |
| `bot/deepseek_action_executor.py` | ✅ готов |
| `configs/approved_specs.txt` | ✅ создан (21 спек для AUTO тира) |
| `configs/claude_analyst.env.template` | ✅ создан |
| `configs/intraday_config.json` | ✅ создан (10 тикеров) |
| `configs/family_profiles.json` | ✅ существует |
| `scripts/deploy_autonomy.sh` | ✅ готов, запускать им |
| `scripts/equity_curve_autopilot.py` | ✅ полный, 518 строк |
| `scripts/deepseek_weekly_cron.py` | ✅ готов |
| `scripts/claude_monthly_analyst.py` | ✅ готов (нужен API ключ) |
| `/ai_monthly` в Telegram | ✅ добавлен в бота |
| `docs/AI_INTEGRATION_ROADMAP.md` | ✅ полный roadmap |
| `docs/IMPROVEMENTS_20260401.md` | ✅ отчёт о всех изменениях |

---

## ⚠️ Важные замечания

1. **Порядок важен**: сначала деплой (задача 1.1), потом equity_curve_autopilot (2.2), потом deepseek_weekly_cron (2.3). Каждый шаг зависит от предыдущего.

2. **Два бага уже исправлены локально** (исправил владелец):
   - `equities_midmonth_monitor.py` line 238: CRITICAL_STOP теперь проверяется до STOP_BREACHED
   - `equities_alpaca_intraday_bridge.py` line 804: hot-reload теперь работает на каждом цикле

3. **Сервис называется `bybot`** (судя по предыдущим деплой-скриптам). Если `deploy_autonomy.sh` не найдёт его — рестарт нужно сделать вручную.

4. **Не удаляй `.bak` файлы** — это резервные копии перед изменениями этой сессии.
