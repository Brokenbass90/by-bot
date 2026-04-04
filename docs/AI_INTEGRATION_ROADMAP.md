# AI Integration Roadmap

_Последнее обновление: 2026-04-01 (Session 20)_

Карта того, что есть, что работает, чего не хватает и в каком порядке делать.

---

## Текущий статус по слоям

### Слой 1 — Защита входов (health_gate)
| Компонент | Код | На сервере | Работает |
|-----------|-----|-----------|----------|
| `bot/health_gate.py` | ✅ | ❌ | ❌ |
| Вшит в `smart_pump_reversal_bot.py` | ✅ | — | — |
| `strategy_health.json` обновляется кроном | ❌ | ❌ | ❌ |
| `equity_curve_autopilot.py` крон на сервере | ❌ | ❌ | ❌ |

**Вывод:** Код написан, но не задеплоен → health_gate не блокирует ни один вход.

---

### Слой 2 — Авто-обучение на сделках (trade_learning_loop)
| Компонент | Код | На сервере | Работает |
|-----------|-----|-----------|----------|
| `bot/trade_learning_loop.py` | ✅ | ❌ | ❌ |
| Вызывается после закрытия позиции в боте | ✅ | — | — |
| Паттерны копятся в `data/trade_learning_log.jsonl` | ✅ | ❌ | ❌ |
| Proposals попадают в approval queue | ✅ | ❌ | ❌ |

**Вывод:** Архитектурно замкнут, но не запущен ни разу — нет данных.

---

### Слой 3 — DeepSeek операционный AI (еженедельный)
| Компонент | Код | На сервере | Работает |
|-----------|-----|-----------|----------|
| `bot/deepseek_overlay.py` | ✅ | ❌ | ❌ |
| `bot/deepseek_autoresearch_agent.py` | ✅ | ❌ | ❌ |
| `bot/deepseek_action_executor.py` | ✅ | ❌ | ❌ |
| `scripts/deepseek_weekly_cron.py` | ✅ | ❌ | ❌ |
| Крон на сервере (каждый пн. 08:00) | ❌ | ❌ | ❌ |
| `/ai_tune`, `/ai_deploy`, `/ai_results` в Telegram | ✅ | ❌ | ❌ |

**Вывод:** Весь pipeline написан — от анализа до деплоя параметров через Telegram. Не активирован.

---

### Слой 4 — Research Gate (безопасность автономии)
| Компонент | Код | На сервере | Работает |
|-----------|-----|-----------|----------|
| `bot/deepseek_research_gate.py` | ✅ | ❌ | ❌ |
| Tier-система AUTO/PROPOSAL/BLOCKED | ✅ | — | — |
| `configs/approved_specs.txt` | ✅ | ❌ | ❌ |
| Вшит в `deepseek_weekly_cron.py` | ✅ | ❌ | ❌ |

---

### Слой 5 — Семейные профили символов (family_profiles)
| Компонент | Код | На сервере | Работает |
|-----------|-----|-----------|----------|
| `bot/family_profiles.py` | ✅ | ❌ | ❌ |
| `configs/family_profiles.json` | ✅ | ❌ | ❌ |
| Вшит в micro_scalper_v1 | ✅ | — | — |
| Вшит в alt_sloped_channel_v1 | ✅ | — | — |

---

### Слой 6 — Claude стратегический AI (ежемесячный)
| Компонент | Код | API ключ | Работает |
|-----------|-----|---------|----------|
| `scripts/claude_monthly_analyst.py` | ✅ (skeleton) | ❌ | ❌ |
| `configs/claude_analyst.env` | ❌ | ❌ | ❌ |
| Вшит в weekly cron или main bot | ❌ | — | — |

**Условие активации:** P&L > $200/мес стабильно → тогда $5-15/мес на Claude API оправданы.

---

## Приоритетный план

### Фаза 0 — Деплой (СРОЧНО, 1 команда rsync)
Без этого шага всё остальное бессмысленно. Код написан за 20 сессий — он не работает.

```
Файлы: bot/health_gate.py, bot/allowlist_watcher.py, bot/deepseek_research_gate.py,
       bot/deepseek_overlay.py, bot/deepseek_autoresearch_agent.py,
       bot/deepseek_action_executor.py, bot/trade_learning_loop.py,
       bot/family_profiles.py, configs/family_profiles.json,
       scripts/deepseek_weekly_cron.py
Действие: rsync → systemctl restart bybit-bot
```

### Фаза 1 — Замкнуть петлю equity_curve → health_gate
Сейчас `strategy_health.json` никогда не обновляется автоматически.
health_gate читает устаревший файл → все стратегии статус OK → блокировки нет.

```
Нужно: крон equity_curve_autopilot.py раз в неделю (пн 09:00)
Результат: health_gate начинает реально влиять на торговлю
```

### Фаза 2 — Первые данные из trade_learning_loop
После деплоя нужно дать боту 2-4 недели торговли, чтобы накопить записи в
`data/trade_learning_log.jsonl`. После этого:
- `deepseek_autoresearch_agent.py` сможет анализировать реальные паттерны
- Появятся первые proposals в очереди
- Появится смысл использовать `/ai_tune` в Telegram

### Фаза 3 — Первый цикл DeepSeek weekly cron
После накопления данных:
1. Запустить `deepseek_weekly_cron.py` вручную, проверить отчёт
2. Убедиться что proposals корректны
3. Только потом ставить автоматический крон

### Фаза 4 — Alpaca auto-exit (осторожно)
Последовательность безопасного включения:
1. Сначала 2-3 цикла `ALPACA_AUTO_EXIT_DRY_RUN=1` — проверить что закрывает правильные позиции
2. Потом `ALPACA_AUTO_EXIT_ENABLED=1` только на paper account
3. Никогда не включать на live без 2+ недель наблюдения в dry-run

**Исправленный баг (уже поправлен локально):**
Проверка CRITICAL_STOP (2 ATR) должна идти ДО STOP_BREACHED (1.5 ATR).
Иначе CRITICAL_STOP никогда не достигается.

### Фаза 5 — Claude Monthly Analyst (когда P&L > $200/мес)
- Создать `configs/claude_analyst.env` с `ANTHROPIC_API_KEY`
- Запустить `python3 scripts/claude_monthly_analyst.py --report` вручную
- Оценить качество анализа
- Добавить в крон (раз в месяц, 1-е число, 10:00)

---

## Архитектура двух AI (будущее)

```
                    ┌─────────────────────────────────────┐
                    │         LIVE BOT                    │
                    │  health_gate → strategy entry gate  │
                    │  trade_learning_loop → patterns     │
                    │  family_profiles → per-symbol tune  │
                    └────────────┬────────────────────────┘
                                 │ данные, паттерны, P&L
                    ┌────────────▼────────────────────────┐
                    │         DEEPSEEK (еженедельно)      │
                    │  Роль: операционный тюнинг          │
                    │  • анализ параметров                │
                    │  • proposals для approval           │
                    │  • запуск autoresearch grid'ов      │
                    │  Стоимость: ~$0.5-2/неделя          │
                    └────────────┬────────────────────────┘
                                 │ proposals + отчёты
                    ┌────────────▼────────────────────────┐
                    │  RESEARCH GATE (safety layer)       │
                    │  AUTO / PROPOSAL / BLOCKED          │
                    └────────────┬────────────────────────┘
                                 │ одобренные изменения
                    ┌────────────▼────────────────────────┐
                    │         CLAUDE (ежемесячно)         │
                    │  Роль: стратегический контроль      │
                    │  • аудит системы целиком            │
                    │  • "не деградирует ли ARF1?"        │
                    │  • идеи новых стратегий             │
                    │  • review решений DeepSeek          │
                    │  Стоимость: ~$5-15/месяц            │
                    └─────────────────────────────────────┘
```

**Принцип взаимоконтроля:**
- DeepSeek НЕ может самостоятельно менять live параметры — всё через research_gate
- Claude раз в месяц проверяет не накопились ли систематические ошибки от DeepSeek
- Финальное слово всегда за человеком (`/ai_deploy` — ручная команда)
- В будущем: Claude может ОТКЛОНЯТЬ proposals DeepSeek через API интеграцию

---

## Что НЕ нужно делать (антипаттерны)

❌ Давать любому AI прямой write-доступ к `smart_pump_reversal_bot.py`
❌ Включать `ALPACA_AUTO_EXIT_ENABLED=1` без dry-run периода
❌ Ставить `INTRADAY_AUTODISCOVER_FROM_CACHE=True` без проверки качества M5 данных
❌ Запускать autoresearch без `min_trades ≥ 25` в constraints (будет оверфит)
❌ Деплоить proposals DeepSeek без просмотра diff'а (`/ai_diff` перед `/ai_deploy`)

---

_Следующий review: после первых 2 недель живых данных с сервера_
