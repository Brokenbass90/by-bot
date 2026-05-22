# Project Status — LIVE

**Last updated:** 2026-05-22 midday (sloped live confirm + Alpaca v39 first research)
**Update rhythm:** еженедельно или при критическом изменении
**Источник правды:** этот файл + `docs/BACKLOG.md` + `docs/RESUME_AFTER_BREAK_20260519.md`

## Однострочник
Bybit perpetuals bot + Alpaca equities. Live equity ≈ $123 Bybit + $1000 Alpaca paper. **2026-05-22:** главный P0 остаётся `live-vs-static_v1 parity`: `crypto_income_static_v1` доказан (`+70.17%` за 365d, PF `1.545`, 445 trades), но current live-effective stack всё ещё торгует другим набором symbols/strategies. Закрыты два конкретных live mismatch: `breakdown_bear_core` теперь сохраняет validated ADA/ONDO после geometry, а `sloped` pending 5m confirmation больше не получает нулевые OHLC. Bybot active after restart, stream fresh, open_trades=0; следующий шаг — 1-3h counters после фиксов. Alpaca v39 event-based первый research-прогон: return выше static, но PF/neg months хуже, verdict `REJECT`.

## Numbers (на 2026-05-19 после рестарта)

### Live state
- **Bybit equity:** ~$123 USDT
- **Last trade:** 2026-04-28 ALGOUSDT range −$0.92. После рестарта ждём первый entry.
- **Alpaca paper:** $1000, open позиции DDOG + GOOGL (после Codex cleanup); stop по GOOGL
- **Owner reserve:** $2000 в крипте, ждёт Фаза 1 trigger
- **Regime:** `bear_trend`, MACRO_BEAR, EMA50/EMA200 daily gap ~−7 %
- **Allocator:** global_risk=0.8, hard_block=False
- **Service:** `bybot` active, рестарт прошёл чисто (open_trades=0 на момент рестарта)

### Что закрыто 2026-05-19

**P0 (все 5) — все Done:**
- P0-1 same-bar guard fix (11:13 UTC)
- P0-2 midterm grouped counters (11:43 UTC)
- P0-3 skip_portfolio split (11:43 UTC)
- P0-4 AI full-context + extras + ohlc cron
- P0-5 DeepSeek/web prompt подключение

**P0.5 — Done:**
- P0.5-1 Alpaca dynamic_v2 backtest → STATIC_BH wins, dynamic_v2 NOT promoted

**Ночные действия Codex'а (вторая половина 19 мая):**
- Surgical unlock ADA + ONDO в breakdown allowlist (после mini-backtest 180d: ADA PF 4.08, ONDO PF 2.14, ENA PF 0.801 — ENA отклонена)
- ADA активна в allowlist, ONDO staged (current geometry её фильтрует)
- DeepSeek evidence-gate правило: `setup card ≠ recommendation`
- Alpaca v3_shadow ↔ v38 monthly конфликт: v3_shadow отправлял SCHW paper orders, v38 отменял → 6 stuck orders, всё canceled, v3_shadow в DRY_RUN by default
- `runtime/allocator_decisions.jsonl` раздулся до 473 MB → архивирован, trace выключен по умолчанию
- Bybot рестартован безопасно

**Утро 2026-05-20:**
- Удалён архивный `runtime/archive/allocator_decisions_20260520_0515.jsonl` на сервере; `runtime/archive` теперь ~4 KB.
- Cleanup сломал портфельные backtests: `backtest/run_portfolio.py` жёстко импортировал удалённую `alt_liquidity_sweep_reversal_v1`. Исправлено optional import, задеплоено на сервер, `py_compile` OK.
- `scripts/alpaca_dynamic_full_backtest.py` больше не пишет жёстко в `/root/by-bot/runtime`; локально пишет в repo `runtime/`, на сервере работает как раньше.
- Контрольный backtest `crypto_income_static_v1`: `+70.17%`, PF `1.545`, WR `58.7%`, MaxDD `6.23%`, 445 trades.
- Attribution: ATT1 `+39.05`, breakdown `+16.42`, ARF1 `+7.61`, midterm `+7.08`.
- Live allocator сейчас отключает ATT1 и midterm в `bear_trend`, поэтому live не равен проверенному пакету.
- Быстрая статическая аппроксимация текущего live allocator (`breakdown + flat + sloped + asm1`, cached symbols only): `+17.45%`, PF `1.211`, MaxDD `13.25%`, 274 trades. Это хуже `crypto_income_static_v1` по return, PF и DD.
- P1-1a shadow/control-plane replay `crypto_income_static_v1`: `+42.31%` за 360d, PF `1.383`, WR `58.8%`, MaxDD `5.87%`, 536 trades, 1 красный месяц. Это подтверждает, что восстановление старого пакета через allocator/policy перспективнее текущего live-состава, но не равно слепому live-включению.
- В P1-1a replay основной вклад дал ATT1 (`+32.33`, 392 trades); flat stabilizer `+12.74`, breakdown `-2.76`. В `bear_trend` пакет торговал только `flat+breakdown` и был слабоплюсовой: PF `1.198`, `+0.66`.
- P1-1b: static-v1 policy/health/env артефакты досинхронизированы на сервер; allocator `--dry-run` с static-v1 policy работает, но `bear_trend` orchestrator всё равно оставляет только `flat+breakdown`. Это ожидаемо по replay, но объясняет почему ATT1/midterm не появятся без отдельного overlay-решения.
- Crypto blocker улучшен до symbol-aware отчёта: `runtime/crypto_blocker/latest.json`, 67 cards; классы: `blocked_runtime_disabled_or_zero_risk=36`, `blocked_by_symbol_allowlist=23`, `blocked_by_symbol=6`, `blocked_by_range=2`. Главный свежий разрыв: scanner видит flat на большем наборе монет, а allocator разрешает flat только `LINKUSDT,LTCUSDT`.

### Главные новые факты от Codex
1. **Bybit не торговал за ночь** — open_trades=0 при regime bear_trend.
2. **Причина не "нет рынка"** — после свежего рестарта доминирует `breakdown_ns_symbol`; allowed breakdown symbols не дают setup, а scanner чаще видит flat/ASB1 cards.
3. **365d simplified research результат:** только **IVB1_static слабоплюсовой** PF~1.18. Это не тот же пакет, что `crypto_income_static_v1`.
4. **Проверенный crypto package жив:** `crypto_income_static_v1` снова воспроизводит +70.17%/365d.
5. **Главный конфликт:** live allocator в bear_trend выключает ATT1/midterm, а router/allowlist слишком узко даёт `flat+breakdown`. P1-1a replay подтвердил, что контрольная плоскость может сохранить прибыльность, но P1-1b показал: текущий первый практический фикс — backtest-driven symbol/router expansion для `flat`/`breakdown`, а не включение ASB1.

### Validated backtests (только то, что прошло metric)
- **Alpaca v38 hybrid top4** (paper): 24м +50.77 %, PF 6.29, WR 82.9 %, MaxDD −2.28 %. **Доказан в paper.**
- **crypto_income_static_v1**: 365d static `+70.17%`, PF `1.545`, MaxDD `6.23%`, 445 trades; 360d control-plane replay `+42.31%`, PF `1.383`, MaxDD `5.87%`, 536 trades, 1 red month — **главный crypto recovery candidate**, но включать только через shadow/live parity.
- **IVB1_static** (crypto 365d): PF ≈ 1.18 — **слабоплюсовой, на границе**.
- **breakdown ADA 180d**: PF 4.08 — **сильный, но один символ, мало sample**.
- **breakdown ONDO 180d**: PF 2.14 — **сильный, ждёт geometry unlock**.

### Active research queue
- `elder_v3_macro_off_full_relax_v1` — running on server (`run_strategy_autoresearch.py`, r043 на момент проверки)
- `att1_density_more_pivots` — queued/следующий research-кандидат
- `asb1_bull_chop_repair_v1` — не продвигать в live без repair acceptance

## Что работает прямо сейчас
- ✅ Bybit auth + same-bar fix
- ✅ Allocator auto-tier
- ✅ Heartbeat + grouped counters (ATT1/ASM1/Flat/MIDTERM/breakdown/sloped split)
- ✅ AI context bridge (3 cron'а)
- ✅ DeepSeek-on-bot читает scanner cards + crypto blocker + extras + ohlc
- ✅ DeepSeek evidence-gate (новое правило: setup card ≠ recommendation)
- ✅ Web UI, admin endpoints, AI history
- ✅ Watchdog (один cron)
- ✅ Alpaca paper intraday + monthly v38 hybrid
- ✅ Alpaca v3_shadow DRY_RUN (больше не конфликтует с v38 monthly)
- ✅ Disk hygiene: allocator trace выключен default
- ✅ 2026-05-21 evening: scheduler теперь читает свежие allowlists для `ATT1`, `ASM1`, `sloped`; `sloped_ns_symbol` ушёл после патча, остался малый sample `same_bar/first_bar`.
- ✅ 2026-05-22 morning: `breakdown_bear_core` router geometry over-filter fixed for validated ADA/ONDO only; ADA/ONDO now survive geometry if already selected by market/backtest router.
- ✅ 2026-05-22 midday: `sloped_channel_live.py` now passes real closed 5m OHLC into pending confirmation instead of zero OHLC; this fixes live execution parity without loosening risk/filter thresholds.
- ✅ 2026-05-22 midday: `scripts/alpaca_v3_event_backtest.py` + `strategies/alpaca_dynamic_v3_event.py` added and first server run completed. `V39_EVENT`: `+34.47%`, PF `1.328`, WR `50.5%`, trades `222`, DD `24.07%`, red months `10/24`; verdict `REJECT`, not paper/live.

## Что НЕ работает (top blockers)
0. **P0-NEW: live-vs-static_v1 parity.** 7d окно до 2026-04-30 оказалось неторговым для static_v1, поэтому оно не подходит для acceptance. Запущена проверка на tradeful окне 30d до 2026-02-24, где static_v1 ранее дал 75 trades, `+9.76`, PF `1.664`.
1. **Live-stack не совпадает с проверенным `crypto_income_static_v1`.** P1-1a/P1-1b показали: static-v1 policy сама по себе не включает ATT1/midterm в bear_trend, а текущие `flat+breakdown` получают слишком узкие symbol lists.
2. **Symbol allowlist/router mismatch** — частично закрыт для scheduler (`ATT1/ASM1/sloped`) и для `breakdown` ADA/ONDO. Остаются scanner cards вне allocator symbols, особенно `flat`.
3. **Post-router-fix sample маленький.** После рестарта compare показывает `breakdown_try=4`, blocker уже не allowlist, а `support/rsi`; `flat/sloped` пока mostly `same_bar`/cooldown. Нужен 1-3h sample before next filter change.
4. **direction-aware risk_mult** — long и short режутся одинаково в bear macro.
5. **SAFETY Patch 1 SL/TP на брокере** — критично.
6. **Alpaca v39 written but not accepted** — first event-based research run improves return vs simple static but fails PF/red-month quality; v38 hybrid пока единственный paper-proven.
7. **Market data freshness Alpaca** — last bar 2026-05-18 19:30 UTC.

## Принятые архитектурные решения (НЕ менять без owner)
- **Single live env:** `crypto_income_live_canary_v2_2_rescue.env`
- **Evidence-first acceptance gate:** PF≥1.25, DD≤8%, neg_months≤3, neg_streak≤2, trades≥30, fees учтены
- **DeepSeek = ORACLE stage только** (не ADVISOR, не EXECUTOR)
- **setup card ≠ recommendation** (новое правило, добавлено в DeepSeek prompt)
- **Не редактируем .env без явного запроса owner'а**
- **Не активируем new strategies без backtest gate**
- **Не запускаем real money Alpaca без 14d stable paper validated v39**

## Заморожено
- ❌ Forex/OANDA (до конца лета)
- ❌ 11 alt_*_v1 strategies (acceptance gate не пройден)
- ❌ AI ADVISOR/EXECUTOR stages
- ❌ Phase 2 monolith refactoring
- ❌ Champion-challenger framework
- ❌ Genetic algorithm
- ❌ ASB1 → live в bear_trend (r001 FAIL)
- ❌ Alpaca dynamic_v1, v2, v38 more-active (все проиграли benchmark)
- ❌ Включение ENA в breakdown allowlist (PF 0.801 < 1.0)
- ❌ Ручной подбор монет как способ заработать (только rolling backtest → router → allocator → live)
- ❌ DeepSeek с правом менять live state (только read + recommend)

## Финансовая фаза
**Сейчас:** Фаза 0. Никаких новых депозитов до:
- ≥ 10 trades за 7d
- PnL ≥ −5 %
- хотя бы 1 sleeve с PF > 1.0 на ≥ 5 trades

| Фаза | Trigger | Bybit | Alpaca | Total real |
|---|---|---|---|---|
| 0 | now | $123 | $0 | $123 |
| 1 | acceptance выше | $623 | $0 | $623 |
| 2 | 14d stable | $623 | $500 | $1123 |
| 3 | 30d, PF>1.1, DD<10% | $1323 | $800 | $2123 |
| 4 | 60d funding-carry validated | $1273 + $50 sub | $800 | $2123 |

## Артефакты Claude (сводно)

### Скрипты (5)
- `scripts/build_ai_full_context.py` — основной AI context
- `scripts/build_ai_extras.py` — trade history, errors, indicators, memory
- `scripts/build_ai_ohlc_and_logs.py` — OHLC top-3 + raw log tail
- `scripts/compare_live_pulse_vs_backtest.py` — диагностика
- `scripts/alpaca_dynamic_v2_backtest.py` — Alpaca research (verdict DONE)

### Документы (9)
- `docs/PROJECT_STATUS.md` — этот файл (live)
- `docs/BACKLOG.md` — приоритеты P0/P1/P2/P3
- `docs/RESUME_AFTER_BREAK_20260519.md` — handoff на 5 дней
- `docs/NEW_CHAT_START_PROMPT.md` — как заходить новому чату с минимумом токенов
- `docs/CLAUDE_AUDIT_20260519.md` — детальный аудит
- `docs/STRATEGY_SET_PER_REGIME_20260519.md` — strategy matrix
- `docs/MIDTERM_GROUPED_COUNTERS_SPEC_20260519.md` — выполнено
- `docs/MINIMAL_VIABLE_STACK_20260519.md` — NEW: что у нас доказанно прибыльное, как собрать MVP
- `docs/CLAUDE_START_HERE_20260518.md` + `docs/CODEX_CURRENT_STATE_20260518.md` — Codex'а (non-negotiable rules)

## Ссылки
- `docs/BACKLOG.md` — приоритеты
- `docs/MINIMAL_VIABLE_STACK_20260519.md` — ответ «можно ли уже сейчас собрать торгующую систему»
- `docs/NEW_CHAT_START_PROMPT.md` — как начать новый Claude-чат
- `runtime/live_mirror/bot_heartbeat.json` — counters
- `runtime/ai_context/{full_context,extras,ohlc_and_logs,memory_lines}.json` — что видит DeepSeek
- `runtime/project_doctor/latest.json` — auto health

## История изменений
- 2026-05-22 morning: Codex found overnight no-trade cause shifted from old scheduler mismatch to router geometry over-filter: `BREAKDOWN_SYMBOL_ALLOWLIST` was only `BTCUSDT,ETHUSDT` while scanner had ADA breakdown. Patched `scripts/build_symbol_router.py` + `configs/strategy_profile_registry.json` with `geometry_force_keep_symbols=["ADAUSDT","ONDOUSDT"]` for `breakdown_bear_core`. Rebuilt router/allocator on server: breakdown count 2→4, risk 0.7125→0.8550, `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,ADAUSDT,ONDOUSDT`. Controlled restart with `open_trades=0`; stream recovered, bybit msgs growing, first fresh counters show no portfolio/global block.
- 2026-05-21 evening: Codex patched scheduler allowlist drift for `ATT1`, `ASM1`, `sloped`; added grouped `sloped_ns_*` diagnostics. Server restarted safely with `open_trades=0`; stream fresh, `bybit_msgs` growing. Fresh compare: allocator hard block false, `breakdown_ns_support`, `flat/sloped same_bar` with small post-restart sample, no `sloped_ns_symbol` domination.
- 2026-05-21 morning: P0-NEW поднят выше всех задач: `live-vs-static_v1 parity fix`. Проверка 7d до 2026-04-30 отброшена как неторговое окно; стартовала 30d parity-проверка до 2026-02-24.
- 2026-05-19 morning: первая редакция Claude. Снят старый baseline.
- 2026-05-19 day: Codex закрыл весь P0, P0.5-1, AI context, Alpaca 422 fix.
- 2026-05-19 evening: Claude добавил ohlc_and_logs.py + RESUME_AFTER_BREAK + NEW_CHAT_START_PROMPT + MINIMAL_VIABLE_STACK. Codex ночью: ADA/ONDO surgical unlock, allocator trace cleanup, v3_shadow DRY_RUN.
- 2026-05-20 morning: Codex удалил архивный allocator trace, восстановил запуск portfolio backtests после cleanup, подтвердил `crypto_income_static_v1` +70.17%/365d и зафиксировал live mismatch: ATT1/midterm выключены allocator'ом.
- 2026-05-20 midday: P1-1a control-plane replay прошёл: +42.31%/360d, PF 1.383, MaxDD 5.87%, 1 red month. P1-1b dry-run показал, что static-v1 policy на текущем bear_trend оставляет `flat+breakdown`; crypto blocker стал symbol-aware и выявил 23 scanner cards вне allocator symbols.
