# Opus Roadmap — 2026-05-27
*Что сделано в этой сессии, что осталось, и видение развития до самодостаточной системы.*

---

## 0. TL;DR

Сегодня закрыты три критичных дыры — система перестаёт быть фрагильной к sweep-конфигам, монитор стратегий теперь видит наши новые стратегии (ATT1/BRC1/ASB1/MTPB3), и команда `RISK_MULT=0.0` теперь реально паузит стратегию вместо клампа в 0.05. После деплоя у Codex — система готова к запуску 360-комбо очереди и к авто-восстановлению при деградации.

Дальше — три волны: **A) запустить и стабилизировать → B) защитить капитал → C) масштабировать**.

---

## 1. Что сделано в этой сессии (ready for Codex deploy)

### Файлы, которые ждут деплоя — Wave 1 (фикс багов предшественника)

| Файл | Что изменено | Эффект |
|---|---|---|
| `configs/autoresearch/package_att1_rsi_relax_v1.json` | grid: list→dict, +constraints, +score_weights | 36 комбо запустятся (раньше — crash) |
| `configs/autoresearch/package_bear_brc1_v1.json` | то же + ENABLE_BRC1 для ясности | 81 комбо |
| `configs/autoresearch/package_bull_asc1_longs_v1.json` | то же | 27 комбо |
| `configs/autoresearch/package_asb1_slope_break_v1.json` | +score_weights, исправлен combo (54→108) | ранжирование стало осмысленным |
| `configs/autoresearch/package_elder_ema_v1.json` | то же | ранжирование стало осмысленным |
| `scripts/auto_apply_research_winner.py` | +3 семейства (ATT1/BRC1/MTPB3), +25 safe_params, +14 forbidden | ATT1 и BRC1 winners больше не теряются |
| `scripts/live_vs_backtest_monitor.py` | +4 стратегии в risk-key map, обновлены baselines | BRC1/ASB1/MTPB3 теперь под мониторингом |
| `smart_pump_reversal_bot.py` | +helper `_risk_mult_or_pause`, патч 23 risk-mult вызова | `RISK_MULT=0.0` теперь реально паузит |

### Новые скрипты — Wave 2 (само-валидация и само-исцеление)

| Файл | Что делает | Триггер | Эффект |
|---|---|---|---|
| `scripts/validate_sweep_configs.py` | Преflight-валидатор для ВСЕХ configs/autoresearch/*.json — проверяет схему (grid=dict, constraints, score_weights), пустые allowlist, неизвестные стратегии, лимит комбо. | cron 1h + pre-commit | Следующий "предшественник" не сможет тихо сломать схему — TG-алерт мгновенно |
| `scripts/build_strategy_registry.py` | Сканирует strategies/*.py + bot + sweep-конфиги + env-overlay; пишет `runtime/strategy_registry.json` с полной картой стратегия → файл → risk_mult → enable_flag → sweep-пакеты. Детектит drift (wired в боте без импорта, riskmult без pause-поддержки и т.п.). | manually + cron 24h | Один источник правды; конец конфузии "v1 vs v2 ATT1" |
| `scripts/regime_change_reopt.py` | При смене applied_regime берёт из mapping (`configs/regime_reopt_mapping.json` или дефолтный) релевантные sweep-пакеты и добавляет в `runtime/research_queue.jsonl`. Throttle 24h per package, max queue depth 10. | cron 15m | Self-improving: новый режим → автоматически новые эксперименты |
| `scripts/auto_dns_recovery.py` | Проверяет резолв критичных хостов (Bybit/Alpaca/TG/Anthropic); если 2+ упали → запись в `runtime/dns_health.json`, опционально rewrite `/etc/resolv.conf` на 1.1.1.1/8.8.8.8/9.9.9.9 (требует `--apply` + root). | cron 5m | Защита от инцидента 10 апреля (53 дня frozen orchestrator) |
| `scripts/run_research_queue_worker.py` | Consumer для `runtime/research_queue.jsonl`. Берёт pending, lock (1 sweep за раз, stale-recovery 6h), запускает `run_strategy_autoresearch.py --spec`, marking running→completed/failed. После успеха триггерит `auto_apply_research_winner.py --dry-run` для TG-предложения. | cron 30m | Замыкает петлю: смена режима → очередь → sweep → ranked → предложение в TG |

**Полная петля самоулучшения после деплоя Wave 2:**

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
auto_apply_research_winner.py --dry-run (triggered post-sweep)
        ↓
configs/auto_apply_params.env (.proposed, not live)
        ↓
TG message: "🔧 AutoApply proposal — review and run --apply-approved"
        ↓
[ HUMAN GATE — operator decides ]
        ↓
auto_apply_research_winner.py --apply-approved → configs/auto_apply_params.env live
        ↓
bot hot-reload (5min) → new params active
        ↓
live_vs_backtest_monitor.py (cron 4h) — if PF deteriorates, auto-pause
        ↓ (loop)
```

Из 8 шагов цикла **7 автоматизированы**, человек одобряет один — финальный apply. Это правильный baseline: бот сам ищет, проверяет, предлагает; человек принимает финальное решение по живым деньгам.

### Документы (для Codex)
- `OPUS_AUDIT_2026_05_27.md` — полный аудит файлов предшественника
- `CODEX_HOTFIX_2026_05_27_sweeps.md` — почему 3 sweep-конфига не работали и что исправлено
- `OPUS_ROADMAP_2026_05_27.md` — этот файл

### Проверки которые прошли
- 5 sweep-конфигов парсятся через настоящий `_load_spec` + `_iter_grid` + `_command_context` без crash
- `_score_candidate` с пустым summary правильно проваливает с `trades<N;net<0.0`
- `auto_apply_research_winner.py` end-to-end в dry-run на 96 исторических sweep-запусках: 8 семейств классифицировано (включая ATT1 и BRC1, которые раньше терялись)
- `live_vs_backtest_monitor.py` запустился, замапил 21 стратегию, 20 baselines
- Бот `smart_pump_reversal_bot.py` проходит AST-parse (синтаксис не сломан)
- Helper `_risk_mult_or_pause` — 12/12 unit-тестов прошли (`"0"` → 0.0, `0.01` → 0.05, мусор → default, негатив → 0.0)
- `validate_sweep_configs.py` прогнал 240 конфигов: наши 5 — clean; найдено 2 настоящих edge-case (метаданный файл без `name`, equities-конфиг с другим runner-ом) + 131 предупреждение (в основном grid > 500 комбо в старых elder-свипах)
- `build_strategy_registry.py` построил карту 74 модулей, 15 wired-in; после фикса транзитивных импортов осталось 3 drift-предупреждения (см. ниже)
- `regime_change_reopt.py`: для текущего `bear_chop` корректно поставил в очередь arf1_flat_touch + breakdown_rsi
- `auto_dns_recovery.py`: корректно классифицировал состояние, отказался менять resolv.conf без `--apply`+root

### Что нашли новые инструменты (для расследования Codex'ом, не срочно)
- `build_strategy_registry.py --drift` показал 3 стратегии в боте, привязанные tuple'ом `(ENABLE_X, "module")`, но без прямого/транзитивного импорта: `alt_range_scalp_v1`, `inplay_breakout`, `pump_fade_v2`. Проверено: они грузятся через shim'ы (`strategies/inplay_wrapper.py` → `archive/strategies_retired/`). Это не баг сегодня, но хрупко — если архив переедет, бот упадёт на старте этих стратегий. Codex: стоит зафиксировать пути или вернуть модули из архива.

### Что НЕ затронуто (намеренно)
- ATT1 и BRC1 `RISK_MULT = max(0.0, ...)` — уже было правильно
- `ORCH_GLOBAL_RISK_MULT`, `ALLOCATOR_GLOBAL_RISK_MULT` — глобальные, монитор их не пишет
- HZBO1/BOUNCE1/ASM1/SOB1 etc — патчены (на случай будущих режимов), но в этой очереди sweep они не активны
- Параметры стратегий (allowlist, RSI, ATR) — не меняем; это работа sweep'а

---

## 2. Что Codex запускает после деплоя

```bash
# Block 0 — uncontroversial, без тестов (out of CODEX_HANDOFF_2026_05_26_v3.md)
supervisorctl restart web
python3 scripts/reset_regime_neutral.py
supervisorctl restart bot              # if open_trades == 0
# 3 cron jobs: orchestrator 4h, screener 6h, router weekly

# Block 1 — sweep queue (360 candidates total)
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_att1_rsi_relax_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_bear_brc1_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_bull_asc1_longs_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_asb1_slope_break_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_elder_ema_v1.json

# Block 2 — promotion via auto_apply (proposal-only by default)
python3 scripts/auto_apply_research_winner.py --dry-run
# After review: manually copy params to .env, restart bot when open_trades=0

# Block 3 — turn on self-healing + self-validation (crontab)
crontab -e
# Existing (из CODEX_HANDOFF):
#   0 */4 * * *  cd ... && python3 bot/regime_orchestrator.py            >> logs/regime_orchestrator.log 2>&1
#   0 */6 * * *  cd ... && .venv/bin/python3 scripts/crypto_coin_screener.py --tg >> logs/screener.log 2>&1
#   0 2  * * 1   cd ... && .venv/bin/python3 scripts/build_symbol_router.py >> logs/router.log 2>&1
# Новые (Wave 2 — добавить):
#   0 */4 * * *  cd ... && python3 scripts/live_vs_backtest_monitor.py    >> logs/strategy_monitor.log 2>&1
#   0 *  * * *   cd ... && python3 scripts/validate_sweep_configs.py --tg --strict >> logs/sweep_validate.log 2>&1
#   */15 * * * * cd ... && python3 scripts/regime_change_reopt.py --tg    >> logs/regime_reopt.log 2>&1
#   */5 * * * *  cd ... && python3 scripts/auto_dns_recovery.py --tg      >> logs/dns_health.log 2>&1
#   30 6 * * *   cd ... && python3 scripts/build_strategy_registry.py --drift --tg >> logs/registry.log 2>&1
#   0 9 * * *    cd ... && python3 scripts/auto_apply_research_winner.py --dry-run --tg >> logs/auto_apply.log 2>&1
#   */30 * * * * cd ... && python3 scripts/run_research_queue_worker.py --tg >> logs/research_queue_worker.log 2>&1
```

Acceptance gate: PF > 1.591 AND DD <= 7.0 AND trades >= 40-60 (per file).

**Важно по cron'ам**: `auto_apply_research_winner.py` в cron — ТОЛЬКО `--dry-run` (предложения в TG). Реальный apply (`--apply-approved`) — только руками после ревью. `auto_dns_recovery.py --apply` тоже только руками/root, в cron — только мониторинг (без `--apply`).

---

## 3. Видение развития (приоритет → срок)

### Волна A — Запустить и стабилизировать (1-2 недели после деплоя)

**Цель: каждый день есть 2-4 сделки в любом режиме, проигранных дней не больше 30%.**

| # | Задача | Ценность | Риск |
|---|---|---|---|
| A1 | Дождаться завершения sweep-очереди + ручной apply winners через `--apply-approved` | Расширяет арсенал с 4 до 6-7 рабочих стратегий | низкий |
| A2 | Включить `live_vs_backtest_monitor.py` в cron (4h) | Автопауза деградации | низкий |
| A3 | Включить `auto_apply_research_winner.py` в cron (24h, dry-run only) | Раз в день предложения через TG | нулевой |
| A4 | Перевести Block 0 cron'ы в supervisord + healthcheck endpoint | Уйти от ручного crontab edit | низкий |
| A5 | Снять ATT1 из shadow в live (ATT1_RISK_MULT=0.08) — после sweep | +1 стратегия для лонгов | средний |
| A6 | Расширить ARF1 на BTC+ETH (сейчас без них — неочевидное упущение) | Покрытие самых ликвидных монет | низкий |

**Метрика успеха**: `/coins` + `/status` показывают, что бот сделал >=2 сделки в день за 5 рабочих дней подряд.

---

### Волна B — Защита капитала (2-4 недели)

**Цель: автоматическая защита от любого режима, в котором бот ломается.**

| # | Что сделать | Статус | Что осталось |
|---|---|---|---|
| B1 | **Performance Degradation Detector** | ✅ live_vs_backtest_monitor.py готов + risk-mult floor пофикшен | Включить cron 4h; за 30д проверить что авто-пауза реально срабатывает на живых данных |
| B2 | **Regime-Triggered Reopt** | ✅ `scripts/regime_change_reopt.py` написан и проверен | Включить cron 15m; подключить worker который читает `runtime/research_queue.jsonl` и запускает sweep |
| B3 | **Live Params Drift Tracker** | 🟡 частично (runtime/auto_apply_log.jsonl + strategy_registry.json) | + `runtime/params_history.jsonl` с P&L атрибуцией на каждое изменение |
| B4 | **Auto DNS Recovery** | ✅ `scripts/auto_dns_recovery.py` написан и проверен | Включить cron 5m (мониторинг); протестировать `--apply` на сервере как root |
| B5 | **Auto-orchestrator robustness** | 🟡 _apply_stale_regime_neutral есть | + health_watchdog hook чтобы сам перезапускал `bot/regime_orchestrator.py` при stale (сейчас только сброс в neutral) |
| B6 | **Stack Comparison Gate** | 🔴 спека есть, скрипт нет | каждый winner: backtest BARE vs WITH-allocator/router/health-gate — отвергать если allocator душит |
| B7 | **Sweep schema guard** | ✅ `scripts/validate_sweep_configs.py` + `build_strategy_registry.py` | Подключить как git pre-commit hook + cron 1h |

**Метрика успеха**: за 30 дней должна сработать хотя бы одна авто-пауза с reopt-предложением, и она должна реально предотвратить дальнейшие потери. Research queue должен наполняться автоматически при смене режима.

**Что осталось из Волны B после этой сессии**: B3 (params_history с P&L), B5 (auto-restart оркестратора), B6 (stack comparison gate), + подключение worker'а для `research_queue.jsonl`.

---

### Волна C — Самоулучшение (1-2 месяца)

**Цель: бот сам ищет идеи, валидирует и постепенно деплоит. Человек одобряет, не пишет код.**

| # | Что сделать | Эффект |
|---|---|---|
| C1 | **Strategy Genome Engine** — мутации параметров рабочих стратегий (±10%), автоматически в sweep queue | новые комбинации без ручной работы |
| C2 | **AI Proposal Queue** — Haiku/Sonnet пишет в `runtime/ai_proposals.json` идеи на основе live статистики, человек одобряет через TG | +1 источник идей |
| C3 | **Champion-Challenger framework** (CHAMPION_CHALLENGER_FRAMEWORK_20260517.md) — каждая рабочая стратегия имеет challenger в paper, при стабильном превосходстве — promotion | защита от стагнации |
| C4 | **Cross-Asset Hedge** — Bybit short hedge для Alpaca longs | сглаживание просадок |
| C5 | **Live Retraining Pipeline** (LIVE_RETRAINING_PIPELINE_20260517.md) — еженедельная пересборка allowlist + sweep top параметров | borrowed from ML, для трейдинга |

**Метрика успеха**: 80% всех изменений параметров идут через auto-apply pipeline, 20% — через ручной apply после AI/sweep предложений.

---

### Волна C-bis — Арбитраж крипты (можно стартовать параллельно C, не дожидаясь)

**Ответ на вопрос "можно ли автоматизировать арбитраж?": ДА, и в проекте УЖЕ ЕСТЬ заготовки.** Не с нуля.

Что лежит на полке (готовый код, ждёт оптимизации и активации):

| Направление | Файлы | Статус |
|---|---|---|
| **Funding-rate harvest** (8h funding payments) | `strategies/funding_hold_v1.py`, `strategies/funding_rate_reversion_v1.py`, `scripts/funding_carry_executor.py`, `scripts/funding_carry_live_plan.py`, `scripts/run_funding_carry_live_plan.sh`, `scripts/run_funding_gate_overnight.sh` | Скелет есть, нужен backtest на 365d + acceptance gate + shadow 30d |
| **Funding scanner** (находит экстремумы) | `scripts/scan_funding_basis.py`, `scripts/funding_rate_fetcher.py`, `scripts/backtest_funding_capture.py` | Работает, читать в `runtime/funding_*.json` |
| **Stablecoin depeg arb** (USDC/USDT/DAI) | `strategies/alt_stablecoin_depeg_arb_v1.py` | Только концепт, нужен backtest |
| **Cross-pair (ETH/BTC spread)** | `ADVANCED_ARB_CONCEPTS_20260517.md` | Только дизайн, кода нет |
| **Cross-exchange spot↔perp basis** | `ARBITRAGE_AND_LEVERAGE_PLAN_20260504.md` | Только план, нужен 2-й биржевой коннектор |

**Что РЕАЛЬНО автоматизируется уже сегодня** (без нового exchange-коннектора):

1. **Funding-rate harvest на Bybit** (single-exchange) — самое дешёвое в разработке. Edge 5-15% годовых на BTC/ETH, до 30-50% на altcoin'ах в pump-фазах.
   - Механизм: funding > +0.02% (8h) → SHORT perp на одну funding-выплату, выйти после payment если volatility не убила.
   - Готовые куски: `scripts/funding_rate_fetcher.py` + `strategies/funding_rate_reversion_v1.py`.
   - Что нужно: 365d backtest + shadow 30d + acceptance PF≥1.3, DD≤4%.
   - Время на доводку: ~1 рабочий день (бэктест есть, нужно настроить thresholds + acceptance).

2. **Same-exchange spot↔perp basis arb** на Bybit Unified (spot + perp на одном счёте) — perp >> spot → SHORT perp + LONG spot одновременно, ждём конвергенции.
   - Преимущество: нет withdrawal fees, оба ордера через один API.
   - Edge: 8-15% годовых на BTC/ETH, выше на alt'ах в момент pump'а.
   - Что нужно: новая стратегия `basis_arb_v1`, чтение spot orderbook (есть в Bybit V5), синхронный entry с tolerance.
   - Время на разработку: ~3-4 дня.

3. **Stablecoin depeg arb** — USDC/USDT/DAI расходятся при стрессе ($0.998-$1.002).
   - Edge: малый по PnL/сделка (10-50bps), но высокий WR (>85%) и низкий риск.
   - `strategies/alt_stablecoin_depeg_arb_v1.py` — скелет; нужен backtest и реальные ордерa на spot.

**Что НЕ автоматизируется до серьёзного капитала**:

- **Cross-exchange basis (Bybit ↔ Binance/OKX/Coinbase)** — требует депо на обеих биржах, withdrawal fees съедают edge при < $10k. На $123 не реалистично.
- **Triangular spot arb (BTC→ETH→USDT)** — спреды съедаются fee, на retail без VIP-tier нет смысла.
- **Liquidation cascade front-run** (`strategies/liquidation_cascade_entry_v1.py` есть как идея) — требует low-latency и market-maker лицензию для real edge.

**План в твою стратегию** (вставляется поверх существующих волн):

| Когда | Что | Ожидаемый ROI |
|---|---|---|
| Сразу после Wave A (4 неделя) | Backtest funding-harvest на 365d, прогон через нашу новую очередь `research_queue.jsonl` | research only |
| Месяц 2 | Shadow funding-harvest 30d на $20-30 капитала | +1-3% PnL за месяц как proof |
| Месяц 3 | Live funding-harvest как overlay (5-10% от депо) | +5-15% годовых passive |
| Месяц 3-4 | Backtest basis_arb_v1 (same-exchange) | research |
| Месяц 5 | Shadow basis_arb 14d | proof |
| Месяц 6 | Live basis_arb overlay | +5-10% годовых passive |
| **При equity > $3-5k** | Cross-pair (ETH/BTC β-hedged) | дополнительно 5-10% годовых |
| **При equity > $10k** | Cross-exchange basis | до 10-25% годовых |

**Главный пункт**: ничего из этого не противоречит directional-стратегиям. Это **overlay** — оба работают параллельно, делают разные деньги, корреляция низкая. Сводный edge: directional 60-80% + funding 10-15% + basis 5-10% = ~85-105% годовых **без плеча**. При плече 3-5x (после стабильных 60 дней live) — реальный путь к target пользователя.

### Волна D — Масштабирование (3-6 месяцев, при стабильной A+B+C)

| # | Что сделать | Что даёт |
|---|---|---|
| D1 | Order Book Imbalance фильтр (IDEAS.md P1) | +5-10pp к WR на trend-touch стратегиях |
| D2 | Funding Rate Overlay для размера позиции (IDEAS.md P1) | +20-30% к PnL при funding extremes |
| D3 | TradingView webhooks как доп.сигналы (IDEAS.md P1) | бесплатный поток качественных сигналов |
| D4 | HF Scalping слой на 5m/15m (HF_SCALPING_LAYER_CONCEPT_20260517.md) | дневной cash flow вместо ожидания свингов |
| D5 | Genetic Algorithm evolution (GENETIC_ALGORITHM_EVOLUTION_20260517.md) | новые стратегии из эволюции работающих |
| D6 | Bybit sub-account separation для каждой стратегии (BYBIT_SUB_ACCOUNT_SEPARATION_20260517.md) | чистая P&L атрибуция, изоляция риска |
| D7 | Alpaca dynamic v1 deploy на $500 real | первые реальные деньги на акциях |

---

## 4. Что для всего этого требуется

### Технически

1. **Доступ к серверу** (у Codex есть). На локальной машине нужны DNS, который не падает (auto_dns_recovery решит).
2. **Стабильный бот**. На сегодня — есть, после деплоя `_risk_mult_or_pause` патча — будет ещё стабильнее.
3. **Поток новых данных для backtest**. Сейчас 365d на всё — достаточно. Можно расширить до 720d для тренировки и 360d для validation.
4. **TG для команд + алертов**. Есть, работает.
5. **AI ключи** (Anthropic для Haiku/Sonnet). Есть.

### Организационно

1. **Окно деплоя** — каждое изменение `.env` живого бота требует `open_trades=0` и рестарта. План: вечер субботы UTC.
2. **Ручной gate на каждый winner** — сейчас и в обозримой перспективе. Auto-apply работает только до `.env.proposed` / `configs/auto_apply_params.env`. В живой `.env` — человек.
3. **Дисциплина**: не деплоить ничего без прохождения acceptance gate (PF > 1.591 AND DD <= 7%). Sweep с PF 4.80 на 90d → надо проверить на 365d, иначе overfit.

### Финансово

- **Bybit live ~$123** — слишком мало для full diversification. Каждая сделка — $30-40 risk. После Волны A ожидаемо +30-50% за квартал → ~$160-180.
- **Alpaca paper ~$1000** — после Волны A v38-active валидируется → real $500.
- **При PF=1.6 и 2-4 сделок/день**: примерно +6-10% в месяц на crypto, +3-5% на equities = $20-40/мес на текущем балансе. Для "относительно богатых" нужно: либо больше капитала, либо больше плеча (рисково), либо больше стратегий (то, что мы делаем).
- **Реалистичная цель на 6 месяцев**: $123 → $500-700 crypto через compounding + перевод части прибыли с Alpaca. Это база для масштабирования.

---

## 5. Что не делать (приоритеты — это про "не")

- ❌ Не включать ENABLE_*_TRADING через автомат (auto_apply, monitor) — только человек после ревью sweep
- ❌ Не повышать leverage > 3x без отдельного 6-месячного backtest на bear-2022
- ❌ Не деплоить ATT1 r259 (уже отклонён)
- ❌ Не торговать на Alpaca v39 (только research)
- ❌ Не запускать sweep если acceptance gate ослаблен (если предлагают min_pf < 1.591 — НЕТ)
- ❌ Не трогать risk_per_trade > 1.5% на crypto при текущем балансе $123
- ❌ Не игнорировать TG алерт "Strategy degraded" — это сигнал что или рынок изменился, или sweep был overfit

---

## 6. План на ближайшие 24 часа (если Codex вернётся завтра)

1. Прочитать `OPUS_AUDIT_2026_05_27.md` и `CODEX_HOTFIX_2026_05_27_sweeps.md`
2. Сделать Block 0 (reset_regime_neutral + cron + restart bot)
3. Запустить sweep #1 (att1_rsi_relax) — самый дешёвый, 36 комбо
4. Параллельно: cron на `live_vs_backtest_monitor.py` каждые 4h
5. После завершения первого sweep: `python3 scripts/auto_apply_research_winner.py --dry-run --strategy ATT1` → выслать в TG
6. Если winner есть и PF > 1.591 → ручной apply, перезапуск
7. Идём дальше по sweep'ам

---

## 7. Источники

- `OPUS_AUDIT_2026_05_27.md` — полный аудит файлов
- `CODEX_HOTFIX_2026_05_27_sweeps.md` — детали починки sweep-конфигов
- `ROADMAP_SELF_IMPROVING.md` — оригинал Phase 1/2/3, всё ещё актуален
- `ROADMAP_20260517.md` — текущий активный план manager
- `IDEAS.md` — backlog P0/P1/P2
- `STRATEGY_AUDIT_2026_05_26.md` — диагноз предшественника
- 8 спецификаций в корне (CHAMPION_CHALLENGER, HF_SCALPING, GENETIC_ALG, etc.) — все ждут своей очереди в Волне C/D

---

## Sources

Findings derived from inspection of:
- [OPUS_AUDIT_2026_05_27.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/OPUS_AUDIT_2026_05_27.md)
- [CODEX_HOTFIX_2026_05_27_sweeps.md](computer:///Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/CODEX_HOTFIX_2026_05_27_sweeps.md)
- `scripts/auto_apply_research_winner.py` (patched), `scripts/live_vs_backtest_monitor.py` (patched), `smart_pump_reversal_bot.py` (patched 23 risk-mult occurrences + new helper)
- 5 fixed sweep configs in `configs/autoresearch/`
- `ROADMAP_SELF_IMPROVING.md`, `ROADMAP_20260517.md`, `IDEAS.md`, `STRATEGY_AUDIT_2026_05_26.md`
