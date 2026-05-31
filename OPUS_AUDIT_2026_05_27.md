# Opus Audit — 2026-05-27
*Аудит проекта и работы предшественника. Подготовлено перед фазой self-improving.*

---

## TL;DR

1. **Архитектура жива и понятна**. Бот, web, бэктестер, sweep-runner, orchestrator, allocator — всё на месте.
2. **3 из 5 новых sweep-конфигов предшественника СЛОМАНЫ** и упадут при первом запуске. Если Codex выполнит блок 1.1–1.3 из `CODEX_HANDOFF_2026_05_26_v3.md` — он получит `AttributeError 'list' object has no attribute 'keys'` и ноль результатов.
3. **Остальные правки сессии (web/UI, /coins screener, /reset_regime_neutral, ATT1 shadow env, alpaca universe x6, auto-neutral в боте) — рабочие**, замечаний по сути нет.
4. **План само-улучшения уже частично описан** в `ROADMAP_SELF_IMPROVING.md` (Фаза 3). Готов к реализации, но требуются конкретные скрипты: auto-apply winner, degradation detector, regime-triggered reopt, drift tracker.

---

## 1. Что предшественник сделал хорошо

| Файл | Оценка | Замечания |
|---|---|---|
| `scripts/crypto_coin_screener.py` | ✅ Работает | Чистый, атомарная запись, retry для TG, безопасный rate-limit |
| `scripts/reset_regime_neutral.py` | ✅ Работает | 5 пресетов, dry-run, атомарная запись env+json |
| `smart_pump_reversal_bot.py::_apply_stale_regime_neutral` | ✅ Работает | 24h порог, throttle 1/час, всё, что нужно для self-healing режима |
| `web/static/index.html` (useFetch) | ✅ Корректный fix | `Array.isArray(deps) ? deps : []` + дефолт `deps = []` — двойная защита |
| `web/routes/data_routes.py::/api/coin-screener` | ✅ Работает | Возвращает `available:false` при отсутствии файла, считает `age_sec` для UI staleness |
| `web/routes/ai_routes.py::/api/ai/analyze-setup` | ✅ Работает | Haiku, fallback на raw text при невалидном JSON, 503 при отсутствии ключа |
| `scripts/alpaca_v3_event_backtest.py` | ✅ 78 уникальных тикеров | Без дубликатов, диверсификация по 10 секторам |
| `scripts/run_equities_monthly_baseline_refresh.sh` | ✅ Работает | Дефолт 30 тикеров, переопределяется через `EQ_BASELINE_CORE_TICKERS` |
| `configs/alpaca_paper_local.env` | ✅ Согласован | `EQ_BASELINE_CORE_TICKERS` совпадает с дефолтом в bash |

---

## 2. Критические дефекты в работе предшественника

### 2.1 🔴 Три sweep-конфига нежизнеспособны

**Файлы**:
- `configs/autoresearch/package_att1_rsi_relax_v1.json`
- `configs/autoresearch/package_bear_brc1_v1.json`
- `configs/autoresearch/package_bull_asc1_longs_v1.json`

**Проблема**: предшественник переделал схему конфига, не согласовав её с `scripts/run_strategy_autoresearch.py`:

| Что использует predecessor | Что ждёт runner |
|---|---|
| `"grid": [{"param": "X", "values": [...]}, ...]` (list) | `"grid": {"X": [...], "Y": [...]}` (dict) |
| `"pass_criteria": {...}` | `"constraints": {...}` |
| (нет) | `"score_weights": {...}` для ранжирования |

**Воспроизведение**:
```python
>>> _grid_size(spec['grid'])
AttributeError: 'list' object has no attribute 'values'
>>> list(_iter_grid(spec['grid']))
AttributeError: 'list' object has no attribute 'keys'
```

**Эффект**: Codex запускает любой из трёх → runner падает на старте, ноль кандидатов, ноль трейдов. Block 1 из handoff не сдвинется.

**Дополнительный нюанс**: `package_bear_brc1_v1.json` не добавляет в `base_env` флаг `ENABLE_BRC1_TRADING=1`. Сам `run_portfolio.py` берёт стратегию из `--strategies` cli-аргумента, но если бэктест читает `ENABLE_*` (нужно проверить отдельно) — BRC1 в реальности может не активироваться даже после фикса формата.

**Fix план** (15 минут на каждый файл):
1. Конвертировать `grid` в dict: `{"ATT1_RSI_LONG_MAX": ["52","55","58","62"], ...}`.
2. Переименовать `pass_criteria` → `constraints` (`min_profit_factor`, `max_drawdown`, `min_trades`, `min_winrate`).
3. Добавить `score_weights` (взять из `arf1_filter_v1.json` как baseline и подкрутить).
4. Для BRC1 — явно прописать `ENABLE_BRC1_TRADING: "1"` в `base_env` для надёжности.

`package_asb1_slope_break_v1.json` и `package_elder_ema_v1.json` сделаны правильно (dict-grid + constraints), но всё равно без `score_weights` — ранжирование будет тривиальным. Рекомендую добавить веса.

### 2.2 🟡 ATT1 shadow env vs sweep — слегка рассинхронизированы

- `configs/att1_shadow_candidate.env` указывает `ATT1_PIVOT_LEFT=2`, `ATT1_MIN_R2=0.80`, `ATT1_TOUCH_ATR=0.25`.
- `configs/autoresearch/package_att1_rsi_relax_v1.json` в `base_env`: `ATT1_PIVOT_LEFT=2`, `ATT1_PIVOT_RIGHT=3`, `ATT1_MIN_R2=0.7`, `ATT1_TOUCH_ATR=0.5`.

Это не баг — shadow env ужесточает фильтры. Но если sweep найдёт «winner» на `MIN_R2=0.7`, а на проде сидит `0.80`, поведение разойдётся. Перед `cat shadow.env >> .env` нужно либо запустить sweep ровно на shadow-параметрах, либо принять что shadow — стабильная конфигурация без оптимизации.

### 2.3 🟡 `package_att1_rsi_relax_v1.json` грид содержит `ATT1_RSI_LONG_MAX=52` в base_env неявно

Точнее — runner перезапишет любым значением из grid, но `base_env` не задаёт `ATT1_RSI_LONG_MAX` совсем. Это работает, но менее явно. Хорошая практика — фиксировать дефолт в `base_env`, а grid менять только то, что варьируется.

---

## 3. Текущее состояние системы (трезво)

| Слой | Статус | Что мешает |
|---|---|---|
| Bybit live | ✅ работает | Режим заморожен с 3 апреля. После `reset_regime_neutral.py` начнёт торговать. |
| Strategies | 🟡 5 из 15+ активны | ATT1, Elder, BRC1, ASB1, HZBO1 — выключены |
| RSI фильтры | 🔴 Слишком жёсткие | ATT1_LONG_MAX=52, ASC1_LONG_MAX_RSI=46 — блок 90% лонгов в обычном тренде |
| Sweep-очередь | 🔴 Сломана на 1.1–1.3 | См. 2.1 |
| Coin coverage | 🟡 Узкое | ARF1 без BTC/ETH, Breakdown без ADA/DOT/SUI, Midterm только BTC+ETH |
| Web UI | ✅ Починен | useFetch null-safety, SetupCard AI кнопка, funding overlay |
| Telegram | ✅ Активен | `/coins` готов к выпуску |
| Alpaca paper | ✅ Активна | v38 hybrid держит UNH+GOOGL, intraday v3 — research only |
| Self-healing режим | 🟡 Частичный | Авто-нейтраль через 24ч в боте — есть. Реальный orchestrator cron — НЕ настроен |
| Self-improving loop | 🔴 Отсутствует | Нет auto-apply, нет degradation detector, нет drift tracker |

---

## 4. План доводки до самодостаточной, самозалечивающейся и самоулучшающейся системы

### Фаза A — Срочные фиксы (день 1, 2–4 часа работы)

| # | Действие | Файл/команда | Ценность |
|---|---|---|---|
| A1 | Починить 3 sweep-конфига (grid format + constraints + score_weights) | `configs/autoresearch/package_{att1_rsi_relax,bear_brc1,bull_asc1_longs}_v1.json` | Sweep block 1 заработает |
| A2 | Добавить score_weights в asb1 и elder_ema конфиги | те же | Ранжирование станет осмысленным |
| A3 | Прогнать `reset_regime_neutral.py` локально + поставить cron на orchestrator каждые 4ч | `crontab -e` | Режим перестаёт зависать |
| A4 | Поставить cron на screener каждые 6ч и router раз в неделю | `crontab -e` | Свежий universe и picks |
| A5 | Smoke-test sweep на 1 комбо (`--limit 1`) для каждого исправленного конфига | bash | Подтверждение что runner подхватил |

### Фаза B — Самозалечивание (неделя 1, 2–3 дня работы)

| # | Скрипт | Что делает | Триггер |
|---|---|---|---|
| B1 | `scripts/health_watchdog.py` (уже частично есть — extend) | Проверяет orchestrator/router/screener/allocator age; рестартует при stale; пишет TG | cron каждые 2 мин |
| B2 | `scripts/auto_dns_recovery.py` (new) | Если router падал из-за DNS — переключается на резервный resolver + retry | health watchdog hook |
| B3 | `scripts/live_vs_backtest_monitor.py` (new) | rolling_pf_live_30d < backtest_pf × 0.6 → авто-пауза стратегии через health gate + TG | cron каждый час |
| B4 | Расширить `_apply_stale_regime_neutral` чтобы триггер также включал `auto_apply_disabled` (защита от writes без свежего регима) | bot | inline |

### Фаза C — Самоулучшение (недели 2–4, 5–7 дней работы)

| # | Скрипт | Что делает | Защита |
|---|---|---|---|
| C1 | `scripts/auto_apply_research_winner.py` | После каждого sweep: если winner с PF > 1.591 и DD < 7.0% AND повторено ≥3 раза → автоматически патчит `.env` через diff-PR | Тихое окно 02:00–04:00 UTC, dry-run перед записью, rollback при KO |
| C2 | `scripts/regime_change_reopt.py` | Хук на смену `applied_regime` → добавляет в очередь sweep пакет под новый режим | Throttle 1 раз в 24ч на стратегию |
| C3 | `runtime/params_history.jsonl` + writer | Лог всех применённых параметров + 7d PnL атрибуция | inline в env-writer |
| C4 | `scripts/run_stack_comparison_queue.py` (уже спека есть) | Каждый кандидат: с control-plane vs без → проверка что allocator/router не убивают edge | acceptance gate |
| C5 | `scripts/strategy_genome.py` | Мутации параметров от рабочих стратегий (param ± 10%) → автоматически в sweep queue | rate-limit, max 3 мутации в неделю |
| C6 | `scripts/ai_proposal_queue.py` | AI пишет идеи в `runtime/ai_proposals.json`, не применяет → нужно одобрение через TG | human-in-the-loop |

### Фаза D — Расширение (месяц 2–3, 7–10 дней)

| # | Идея | Источник |
|---|---|---|
| D1 | Order Book Imbalance фильтр | `IDEAS.md` P1 — заменит часть RSI-логики, должен поднять WR |
| D2 | Funding Rate Overlay для размера позиции | `IDEAS.md` P1 |
| D3 | TradingView webhooks как доп.сигналы | `IDEAS.md` P1 |
| D4 | Cross-asset hedge (Alpaca+Bybit) | `CROSS_ASSET_HEDGE_20260517.md` |
| D5 | HF Scalping слой на 5m/15m | `HF_SCALPING_LAYER_CONCEPT_20260517.md` |
| D6 | Genetic Algorithm evolution | `GENETIC_ALGORITHM_EVOLUTION_20260517.md` |

---

## 5. Что я предлагаю делать прямо сейчас

**Приоритет 1 (сегодня)**: починить 3 sweep-конфига и проверить smoke-test, чтобы блок 1 handoff заработал. Я могу это сделать в один присест — выдам diff на ревью.

**Приоритет 2 (завтра)**: написать `scripts/auto_apply_research_winner.py` (~150 строк, низкий риск — пишет только в `.env.proposed`, не в `.env`).

**Приоритет 3 (на этой неделе)**: `scripts/live_vs_backtest_monitor.py` — самое ценное для защиты капитала, держит руку на пульсе автоматически.

После этого система будет:
- **Самодостаточная**: orchestrator+screener+router идут по cron, не зависят от ручного запуска
- **Самозалечивающаяся**: stale-regime/router/dns → auto-recover; degradation → auto-pause
- **Самоулучшающаяся**: winners в sweep → proposed env → проверка → авто-применение; новый режим → автозапуск reopt

---

## 6. Чего я НЕ буду делать без явного "да"

- Применять `att1_shadow_candidate.env` на бой
- Деплоить BRC1 или ASC1 longs до прохождения acceptance gate
- Перезапускать прод-бота (требуется `open_trades=0`)
- Менять Alpaca v38 — он в paper, не трогаем
- Запускать sweep до фикса 3 конфигов — будут гарантированные failures

---

## Sources

Findings derived from inspection of:
- [PROJECT_DESCRIPTION_FOR_REVIEW.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/PROJECT_DESCRIPTION_FOR_REVIEW.md)
- [CODEX_HANDOFF_2026_05_26_v3.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/CODEX_HANDOFF_2026_05_26_v3.md)
- [STRATEGY_AUDIT_2026_05_26.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/STRATEGY_AUDIT_2026_05_26.md)
- [CODEX_TASKS_2026_05_26.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/CODEX_TASKS_2026_05_26.md)
- [ROADMAP_SELF_IMPROVING.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/ROADMAP_SELF_IMPROVING.md)
- `scripts/run_strategy_autoresearch.py`, `scripts/crypto_coin_screener.py`, `scripts/reset_regime_neutral.py`
- `configs/autoresearch/package_*.json` (5 new files)
- `smart_pump_reversal_bot.py` (regions: REGIME_STALE_NEUTRAL, ATT1, BRC1)
- `web/static/index.html` (useFetch), `web/routes/data_routes.py`, `web/routes/ai_routes.py`
