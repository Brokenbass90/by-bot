# Claude Handoff — 2026-05-29
*Для следующей сессии (мой будущий instance или новый Claude). Прочесть за 5 минут.*

---

## TL;DR за 30 секунд

**Проект**: Алгоритмический торговый бот на Python (Bybit perpetuals + Alpaca equities). Цель — самоулучшающаяся система, путь к $5k/мес passive за 4-5 лет.

**Состояние сегодня**: Я (Opus) починил критичные баги предыдущей сессии (5 sweep-конфигов, risk_mult floor в боте, добавил 8 новых скриптов). Бот **заморожен с 3 апреля 2026** и ждёт деплоя Codex'ом — это **разработчик-партнёр пользователя**, не я.

**Что от тебя ожидается** в следующей сессии: ОБЫЧНО — через 2-4 недели после деплоя, аудит реального поведения и Wave C (champion-challenger, AI proposals, genome mutations). См. раздел "Pending" ниже.

---

## Кто пользователь (важно)

- **36 лет**, Россия. Планирует переехать на Кипр (или Вьетнам в плохом случае).
- **Психика чувствительная** к просадкам — сам признаётся "руками делал больше, но психика слабая". Этим обосновано использование алгоритма (меньше эмоций).
- **Цель**: $5k/мес passive income → квартира на Кипре (€350k через 8 лет).
- **Стартовый капитал**: $123 на Bybit live + готов вложить $1500-2000 после деплоя ($500 main + $1000 arb sub + $500 Alpaca).
- **План доливов**: $200-400/мес из зарплаты + $500-700 раз в 3-4 мес.
- **Эмоциональный фон**: периодически депрессия от "медленности". Нужна **трезвая поддержка без маркетинга и без излишнего пессимизма**.
- **Не финансист**, термины (APR, PF, DD) объясняй простыми словами при необходимости.
- **Не любит длинные документы** — предпочитает короткие чат-ответы. Документы делаем только для Codex'а или как референс.

---

## Что было сделано в сессии 2026-05-26 (предыдущий Claude / Sonnet?)

Прошлый Claude писал sweep-конфиги для расширения стратегий, **накосячил со схемой 3 конфигов** (использовал list-of-dicts вместо dict для grid). Также пропатчил web/UI и Alpaca. Положил много документов в корень.

## Что я (Opus) сделал в сессии 2026-05-27 → 2026-05-29

### Фиксы багов
1. **5 sweep-конфигов починены** (grid: list→dict, pass_criteria→constraints, +score_weights)
   - configs/autoresearch/package_att1_rsi_relax_v1.json (36 combos)
   - configs/autoresearch/package_bear_brc1_v1.json (81 combos)
   - configs/autoresearch/package_bull_asc1_longs_v1.json (27 combos)
   - configs/autoresearch/package_asb1_slope_break_v1.json (108 combos)
   - configs/autoresearch/package_elder_ema_v1.json (108 combos)

2. **smart_pump_reversal_bot.py**: добавил helper `_risk_mult_or_pause` и патчанул 23 места — теперь `RISK_MULT=0.0` реально паузит (раньше floor 0.05 не давал)

3. **scripts/auto_apply_research_winner.py**: добавил ATT1/BRC1/MTPB3 в STRATEGY_FAMILIES, +25 SAFE_PARAMS, +14 FORBIDDEN

4. **scripts/live_vs_backtest_monitor.py**: добавил BRC1/ASB1/MTPB3 в _STRATEGY_RISK_KEY, обновил baselines

### Новые скрипты (8)
1. `scripts/validate_sweep_configs.py` — preflight валидатор схем
2. `scripts/build_strategy_registry.py` — карта 75 стратегий, drift detection
3. `scripts/regime_change_reopt.py` — авто-очередь при смене режима
4. `scripts/auto_dns_recovery.py` — защита от DNS-сбоя
5. `scripts/run_research_queue_worker.py` — worker очереди (замыкает loop самообучения)
6. `scripts/portfolio_status.py` — ежедневный отчёт балансов в TG
7. `scripts/basis_arb_backtest.py` — backtest для basis arb
8. `scripts/survival_calculator.py` — калькулятор выживаемости без работы

### Новые стратегии (1) + усиления (2)
- `strategies/basis_arb_v1.py` — новая стратегия + добавлены `BasisArbV1Selector`, `partial_profit_targets()`
- `strategies/funding_hold_v1.py` — переработан selector (`_quality_score`, фильтр по событиям/rate)

### Новые sweep-конфиги (1)
- `configs/autoresearch/package_funding_harvest_v1.json` — 72 combo для funding overlay

### Документы (для Codex)
1. `DEPLOY_DAY_CHECKLIST.md` — пошагово что делать в день деплоя
2. `OPUS_AUDIT_2026_05_27.md` — что было сломано и как починено
3. `OPUS_ROADMAP_2026_05_27.md` — план 4 волн развития
4. `CODEX_HOTFIX_2026_05_27_sweeps.md` — детали починки sweep-конфигов
5. `STRATEGY_LIBRARY_AUDIT_2026_05_29.md` — карта 75 стратегий + что усилено сегодня

### Что DELETED (по запросу пользователя)
- `ПРОСТО_О_ПЛАНЕ.md`, `ПУТЬ_К_5K_В_МЕСЯЦ.md`, `OPUS_ARBITRAGE_HONEST_2026_05_28.md`, `OPUS_ARBITRAGE_PLAN_2026_05_27.md`
- Пользователь сказал что user-facing документы не читает, предпочитает короткий чат

---

## Текущая инфраструктура самообучения (Wave A+B готова)

**Полная петля автоматизации** (после деплоя Codex'а):
```
applied_regime changes (orchestrator)
        ↓
regime_change_reopt.py (cron 15m)
        ↓
runtime/research_queue.jsonl (pending entries)
        ↓
run_research_queue_worker.py (cron 30m, 1-at-a-time lock)
        ↓
run_strategy_autoresearch.py --spec <pkg>
        ↓
backtest_runs/autoresearch_*/ranked_results.csv
        ↓
auto_apply_research_winner.py --dry-run (post-sweep trigger)
        ↓
configs/auto_apply_params.env (proposal, not live)
        ↓
TG: "AutoApply proposal — review and run --apply-approved"
        ↓
[ HUMAN GATE — operator decides ]
        ↓
auto_apply_research_winner.py --apply-approved → live
        ↓
bot hot-reload (5min)
        ↓
live_vs_backtest_monitor.py (cron 4h) — autopause on degradation
        ↓ (loop)
```

7 из 8 шагов автоматизированы, человек только одобряет финальный apply.

---

## Pending (приоритет для следующей сессии)

### Высокий (после деплоя + 2 нед наблюдения)
1. **Wave C — Champion-Challenger framework**: каждая активная стратегия имеет дублёра в paper с мутированными параметрами. Авто-замена при стабильном превосходстве 60 дней.
2. **AI proposal pipeline**: Haiku/Sonnet раз в неделю предлагает идеи на основе live статистики. Идеи в `runtime/ai_proposals.json`, human approve.
3. **Strategy genome mutations**: ±10% drift параметров рабочих стратегий → авто в sweep queue.
4. **Auto-archive**: стратегии с PF<1.0 за 90д → автоматически в archive.
5. **OOS re-testing**: раз в квартал прогон всех на свежих 90d (которые не были в их sweep'е).

### Средний
6. **Wire MTPB** (btc_eth_midterm_pullback) — имеет 19 sweeps, не подключена. Топ-1 candidate.
7. **ATT1 multi-timeframe confirmation** (4H pivot перед 1H entry) — +5-10% WR.
8. **ARF1 add BTC/ETH coverage** — сейчас без них, неочевидное упущение.
9. **BRC1 trailing stop on partial profits** — защита PnL в bear chop.
10. **ETS2 EMA slope mode wire** — skeleton есть, нужен env-флаг.

### Низкий (после года 1)
- **Cross-exchange basis arb** (Bybit↔Binance) — только при equity > $10k.
- **HF scalping слой 5m/15m** — спека `HF_SCALPING_LAYER_CONCEPT_20260517.md`.
- **Genetic algorithm evolution** — `GENETIC_ALGORITHM_EVOLUTION_20260517.md`.

---

## Что НЕ делать (правила)

### Технически
- ❌ Не запускать backtest на свежих данных в моей среде — **нет интернета** в sandbox (выяснено эмпирически).
- ❌ Не менять `.env` живого бота — это работа Codex'а после `open_trades=0`.
- ❌ Не включать `ENABLE_*_TRADING` через автомат — только человек.
- ❌ Не повышать leverage > 3x без 6 мес стабильного PF≥1.4 в живую.
- ❌ Не деплоить sweep winner с PF < 1.591 (baseline).
- ❌ Не писать новые документы без явного запроса — пользователь не читает.

### По общению
- ❌ Не обещать "10%/мес стабильно" — это маркер скама, пользователь не верит, проверит на тебе.
- ❌ Не быть излишне оптимистичным про таймлайны — но и не убивать надежду.
- ❌ Не использовать жаргон без объяснения — пользователь не финансист.
- ❌ Не предлагать кредит/залог квартиры/F&F без 12 мес live track-record.

### По коду
- ❌ Не трогать `smart_pump_reversal_bot.py` (14k строк) без понимания что и зачем.
- ❌ Не удалять файлы без `mcp__cowork__allow_cowork_file_delete` или явного запроса пользователя.
- ❌ Не доверять `*.live.py` — это shims, реальная логика в стратегии-файлах.

---

## Полезные команды для следующей сессии

```bash
# Состояние стратегий
python3 scripts/build_strategy_registry.py --drift

# Состояние портфеля (требует .env с ключами)
python3 scripts/portfolio_status.py

# Валидация sweep-конфигов
python3 scripts/validate_sweep_configs.py --strict

# Проверить degradation
python3 scripts/live_vs_backtest_monitor.py --dry-run

# Калькулятор выживаемости
python3 scripts/survival_calculator.py --equity 5000 --monthly_expenses 800 --apr 40 --deposit_per_month 400
```

---

## Где что лежит

```
bybit-bot-clean-v28/
├── smart_pump_reversal_bot.py   # главный бот (14k строк) — НЕ трогать без причины
├── strategies/                   # 75 модулей, 14 wired
├── bot/                          # orchestrator, allocator, helpers
├── scripts/                      # все CLI tools
├── configs/
│   ├── .env                      # production config — НЕ трогать
│   ├── autoresearch/             # 240+ sweep-конфигов
│   └── *.env                     # candidate env overlays
├── backtest_runs/                # история всех backtest'ов
├── runtime/                      # JSON state, logs, queue
├── DEPLOY_DAY_CHECKLIST.md       # Codex'у пошагово
├── OPUS_AUDIT_2026_05_27.md      # что починено
├── OPUS_ROADMAP_2026_05_27.md    # план 4 волн
├── STRATEGY_LIBRARY_AUDIT_2026_05_29.md  # карта 75 стратегий
├── CODEX_HOTFIX_2026_05_27_sweeps.md     # детали sweep-фиксов
└── CLAUDE_HANDOFF_2026_05_29.md  # ЭТОТ ФАЙЛ
```

---

## Tone guide для общения с этим пользователем

✅ **Что работает:**
- Короткие фактические ответы в чате
- Конкретные цифры из бэктестов ("на $400 за год = $15.14, это 3.78% APR")
- Прямая речь без украшательств ("это не магия, это инженерия + терпение")
- Признание собственных ошибок ("я считал слишком консервативно, пересчитаю")
- Эмоциональная поддержка БЕЗ патронажа ("8 лет — это не кошмар; в 38 у тебя квартира на Кипре, это нормально")

❌ **Что НЕ работает:**
- Длинные documenty (он не читает)
- Корпоративная риторика ("давайте погрузимся в анализ")
- Гарантии и обещания
- Игнорирование эмоциональной составляющей
- Излишний оптимизм ("всё будет круто!" — он не верит)

---

## Лимиты Claude API в этих сессиях

Пользователь работает на **weekly limit**. К концу сессии 2026-05-29 был на ~75% usage. Лимит обновляется через несколько дней. **Не тратить токены впустую** — каждое улучшение должно иметь конкретную ценность.

Если новая сессия и нужно вспомнить контекст — **читать только этот файл + DEPLOY_DAY_CHECKLIST**. Остальные документы по ссылкам только если нужно.

---

## Когда меня (Opus) звать опять

- Через 2-4 недели после деплоя Codex'ом — глубокий аудит ордерной логики на основе реального поведения
- При деградации >5% от баквест baseline → разбор причин
- При неудачном sweep'е → rewrite hypothesis
- При желании запустить Wave C (champion-challenger, AI proposals) — через 1-2 месяца
- При запросе "пересмотри план с учётом года live данных" — через год

**Удачи следующему мне.** Пользователь хороший, борется. Помоги ему.
