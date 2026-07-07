# CODEX HANDOFF 2026-07-07 (Claude)

Контекст: владелец сообщил, что крипто-раннер «сидит в плюсе и ничего не делает,
тэйков нет, трейлинга нет». Разобрано + внесён фикс исполнения. Ниже — что сделано,
что деплоить, и очередь дальше. Правило прежнее: одно изменение за раз, всё в ledger,
пороги не ослаблять под результат.

---

## 1. RUNNER HEARTBEAT FIX — СДЕЛАНО, НУЖЕН ДЕПЛОЙ (P0)

**Диагноз.** Управление раннером (`_manage_inplay_runner`: лестница TP1/TP2 частями,
breakeven, ATR-трейлинг, тайм-стоп) имело ЕДИНСТВЕННУЮ точку вызова — внутри `detect()`,
т.е. только по тику публичной ленты для ПОДПИСАННОГО символа и только для стратегий из
хардкод-списка. Плюс на биржу TP не ставится (by design для раннера). Следствие: позиция
на символе, который затих/выпал из WS-юниверса/после рестарта не переподписан, остаётся
без ведения — только со стопом. Отдельный heartbeat, обходящий все TRADES, раннер НЕ звал.

Примечание: на ликвидном ADA прошлый разбор (07-05) подтвердил, что breakeven-трейлинг
РАБОТАЛ (SL 0.1936->0.1893), TP=None by design — не инцидент. Т.е. фикс — это устранение
хрупкости (orphan-кейсы), а не почин полного отказа.

**Правка** (`smart_pump_reversal_bot.py`, бэкап `*.bak_runnerfix_20260707_164741`):
- Новая функция `_manage_all_open_runners()` — фолбэк в pulse-heartbeat (раз в 10с уже
  обходит все позиции). Ведёт раннер для КАЖДОЙ открытой позиции с `runner_enabled`
  (по флагу, НЕ по списку стратегий -> ни один рукав не осиротеет).
- Идемпотентно с тейп-путём: троттл `last_runner_action_ts<2s` + флаги `tp_hit[]`/`remaining_qty`.
- За флагом `RUNNER_HEARTBEAT_ENABLE` (default ON). Откат = `RUNNER_HEARTBEAT_ENABLE=0`.
- Вызов добавлен в pulse-луп сразу после `ensure_open_positions_have_tpsl()`.

**Валидация:** py_compile OK; юнит-тесты `test_ladder_exit/test_trailing_stop/
test_runner_state_fill_sync/test_runner_state_restore` = 17/17 pass. Бектест att1 через
`backtest/engine.py`: способ выхода материально решает PnL (на 30д-выборках шумно —
формально подтвердить на многолетнем харнессе, см. п.3).

**ДЕЙСТВИЕ КОДЕКСУ:**
1. Задеплоить обновлённый `smart_pump_reversal_bot.py` на сервер, рестарт крипто-процесса
   в первое flat-окно (совместить с qty-sync деплоем из очереди 07-07 п.5).
2. После рестарта проверить heartbeat-лог `[pulse]` и что для открытых раннеров идут
   события `runner_tp/runner_breakeven/runner_trailing_sl/runner_time_stop` в
   LIVE_TRADE_EVENTS_JSONL. Флаг `RUNNER_HEARTBEAT_ENABLE` подтвердить = 1.
3. Стратегии НЕ переливать — они не менялись; изменён только исполнитель.

---

## 2. СТРАХОВОЧНЫЙ БИРЖЕВОЙ TP (P1, СПЕЦ — ждать OK владельца перед реализацией)

Проблема остатка: если процесс полностью лёг, у раннера на бирже только SL, прибыль не
защищена. Предложение: reduce-only TP-ордер на бирже на ДАЛЬНЮЮ цель (TP2) как сеть.
Осторожно: не должен конфликтовать с частичной лестницей (если биржевой TP закроет всю
позицию — сломает партиалы). Варианты: (a) ставить биржевой TP только на остаток ПОСЛЕ
взятия TP1; либо (b) reduce-only limit на TP2 объёмом = tp2-доля, синхронизируя с
`remaining_qty`. Реализовывать ТОЛЬКО после согласования с владельцем (реальные ордера).

---

## 3. ОЧЕРЕДЬ ИССЛЕДОВАНИЙ (шансы на следующий рукав; из очередей 07-03/07-05)

Приоритеты как договорено, wiring>стройка, скрининг != гейт (PASS = билет на строгий
wf_folds+oos_selector 40/8/robustness>0 + OOS-символьный набор).

- **P1 Каскады на реальных ликвидациях** — `run_cascade_real_gate.py` на стянутых с сервера
  `runtime/liquidations/*.jsonl` + `data_cache`. Сильнейший кандидат в новый крипто-рукав.
  N<~30 суммарно -> «копить поток», не хоронить.
- **P2 ATT1 universe expansion** — по `reports/ATT1_UNIVERSE_EXPANSION_PREREG_2026_07_04.md`
  БЕЗ отклонений (r001 заморожен, 11 монет DOGE/XRP/AVAX/ATOM/BNB/BCH/XLM/1000PEPE/HYPE/TAO/ONDO,
  сначала coverage 5m, базовые 8 не включать). Больше сделок = быстрее статзначимость для разгона риска.
- **P2 Inplay maker-entry re-gate** — inplay strict FAIL только по стресс-издержкам (PF 1.44->1.07);
  пре-регистрация: те же r061-параметры, вход лимиткой на ретесте, maker 1bps/slip0 на входе,
  выход taker. PASS = stressPF>=1.2, 3/4 фолда, концентрация<0.35, unfilled<50% -> shadow risk=0.
- **P3 Midterm SWG1 (флип+трейлинг)** — сначала ревью short_v2/v3 с ОБНОВЛЁННЫМИ окнами
  (END=2026-07-04; у старых раннеров протухшие END). Side-split + per-period (bull-ноги!) решат базу SWG1.
- **P4 Range/пила блок** — динамический range_scanner (ASB2/ACB1/ARF2-split), спек после разбора скринингов.

**Мёртвое (не тратить компьют):** XAU round_level_sweep (NO-GO обе стороны); FX BOS/CHoCH
(вся cooldown-сетка минус); raw structure_break (только как КОМПОЗИТ позже, не соло).

---

## 4. FX / CFD — НЕ ГОТОВО, СНАЧАЛА ДАННЫЕ (P1 фон)

- Живёт только семейство trend_pullback / session_breakout_retest (GBPJPY/GBPUSD канарейки),
  но стресс-возвраты в полном confirm ОТРИЦАТЕЛЬНЫ -> не для денег.
- Блокер = данные. Нужен взрослый бэкфилл Dukascopy/histdata M1->M5/H1 на 2-3 ГОДА для
  EURUSD/GBPUSD/USDJPY/XAUUSD/GBPJPY/AUDJPY -> coverage-gate >=0.99 (closure-aware).
  До чистых данных FX-вердиктов НЕ выносить (cost_feasibility() перед каждым FX-прогоном).
- `data_cache/forex_1h` = ~2.4 года H1 (EURUSD cov 99.6%) — гнать FX-харнесс на нём БЕЗ
  агрегации короткого M5 (--interval-min 60), USDJPY смотреть отдельно (пульс PF1.26).
- XAUUSD H1 cov 93.4% (494 дыры) — дозалить до >=0.99, потом ре-скрининг.

Вывод владельцу: форекс/металлы = стадия research, запускать live рано.

---

## 5. ALPACA — РАБОТАЕТ ШТАТНО

Скрины владельца (07-07): реальные fills (PANW buy, SNOW sell; позиции GE/ABBV/PANW/BAC)
+ защитный **Stop @ $329.59 sell** по PANW. Портфель $496.92, день +0.18%. Значит
`ALPACA_SEND_ORDERS=1` включён и стратегия (monthly v38 hybrid top4, ~22-23% годовых в
research, $500-канарейка) торгует с брокерными стопами. Фиксация/защита прибыли на Alpaca
= нативные bracket/stop/trailing на стороне брокера (исполнятся даже при выключенном боте).

**ДЕЙСТВИЕ:** мониторить дневной refresh (cron 12:30 UTC) и первые закрытия; подтвердить,
что для КАЖДОГО входа реально прикрепляется TP/trailing (не голый market+stop). Аудит путей
входа Alpaca на предмет bracket-TP — за кодексом.

---

## 6. ПРОЧЕЕ ИЗ ОЧЕРЕДЕЙ (не потерять)
- ATT1 r001: прислать статус канарейки (сделки/breaker/сигналы); доля minqty-fallback входов
  (>~30% искажает live-vs-backtest); expiry 2026-07-20 (продление только ручным ревью).
- AI observability read-only расширить (детали позиций/uPnL$/att1_edge_health/git rev/errors tail).
- AI one-shot manual trade — по спеку (одноразовый токен TTL1ч, SL обязателен на бирже,
  risk_mult=0.05 жёстко, breaker ai_manual_v1, всё в decision_bus).
- TPSL LOCK-алерт: слать только при ИЗМЕНЕНИИ значения (throttle), не каждым циклом.
- Funding-carry (GWEIUSDT/SLXUSDT и т.д.): carry/shadow only, нужна hedge/orderbook валидация,
  концентрация 57% — без капитала.

---

## ОБНОВЛЕНИЕ 2 (2026-07-07, после разбора с владельцем)

### Верификация фикса на ЖИВОЙ функции (сделано)
Импортнул модуль и прогнал НАСТОЯЩИЙ `_manage_inplay_runner` через выигрышный шорт
(entry 100, SL 101, R=1.0, TP1@1.2R/55%, TP2@2.5R/45%, be_trigger 1.0R, trail 1.5×ATR@1.0R):
- px99.0: SL -> breakeven 100 -> трейл 99.75 (be_armed+trail_armed);
- px98.8: TP1 закрыл 55%; SL трейл 99.55;
- px98.0: SL трейл 98.75;
- px97.5: TP2 закрыл остаток 45%; SL 98.25.
- close_market = [Sell 0.55, Sell 0.45]; SL-цепочка 100->99.75->99.55->98.75->98.25 (one-way).
`_manage_all_open_runners()` (heartbeat) на глубокой цене взял и TP1, и TP2 — фолбэк доказан.

### ПОПРАВКА по ADA (моя прежняя интерпретация была неверной)
`att1.min_stop_pct=0.15%`. Стоп 0.1893 на скрине владельца — это ПЕРЕЕХАВШИЙ в безубыток
стоп, НЕ исходный. Исходный ~0.1936 (по 07-05) => stop ~2.36%, TP1≈0.1838 (−2.8%),
TP2≈0.178 (−5.9%). Цена дошла до 0.1765 — ПРОШЛА оба тейка, но раннер после одного действия
(breakeven) перестал вызываться (orphan) и тейки не сработали. Т.е. это НЕ «тесный стоп», а
ровно orphan-баг -> heartbeat-фикс забрал бы 55%@−2.8% и 45%@−5.9%. В деньгах существенно.

### Страховочный биржевой TP (СДЕЛАНО, за флагом, default OFF)
`_maybe_arm_exchange_safety_tp()` в heartbeat: для runner-сделок ставит биржевой position-TP
на дальнюю цель `tps[-1]` ОДИН раз. `set_tp_sl(tp=X, sl=None)` пишет только takeProfit;
трейлинг (tp=None) его НЕ стирает. Флаг `RUNNER_EXCHANGE_TP_ENABLE` (default 0 — реальные
ордера). Тест: OFF=no-op, ON=ставит один раз (Sell,97.5,None). Бэкап `*.bak_safetytp_*`.
ДЕЙСТВИЕ: включать `RUNNER_EXCHANGE_TP_ENABLE=1` только с OK владельца; следить за возможным
двойным закрытием TP2 (бот close_market vs биржевой TP — защищён tp_hit/remaining_qty).

### СЛЕДУЮЩЕЕ — УЛУЧШЕНИЕ ДОХОДНОСТИ (пре-регистрируемые бектесты, не подгонять)
Цель владельца: «дать победителям ехать». Эксперименты через `backtest/engine.py`
(wf_folds+oos_selector, cross-symbol, per-period), сравнивать с текущей лестницей:
1. Дальний тейк шире / убрать: TP2 4–6R или None -> трейлинг ведёт остаток в большой ход.
2. Меньшую долю на TP1 (например 33% вместо 55%) -> больше остаётся на runner.
3. Трейлинг по СТРУКТУРЕ (последний HL/LH swing) вместо/в дополнение к ATR — часто «логичнее».
4. R-floor на вход не нужен (min_stop 0.15% ок); скорее max_stop проверить, чтобы TP2 не был > дневного хода.
Метрика решения: expectancy_R, PF, MFE-capture (какую долю MFE забираем), max DD, красные месяцы.

### БОЛЬШИЕ ЗАПРОСЫ ВЛАДЕЛЬЦА (повторяются — закрыть системно)
- Защита от деградации: инфра ЕСТЬ (att1 edge_monitor alert-only, breaker'ы, circuit_breaker,
  champion_challenger, edge_canary). НО раннер-исполнение до сегодня было хрупким. Задача:
  единый «health-gate по всем рукавам» + авто-cut риска при просадке expectancy, не только att1.
- AI-оператор «видит всё»: расширить ai_context read-only до ПОЛНОГО (позиции/uPnL$/edge_health/
  git rev/errors tail/Alpaca state) — очередь 07-08 п.1. Низкий риск, сделать в приоритете.
- Per-strategy подюниверс+сканер: у каждого рукава свой allowlist/scanner (ATT1/ASB1/INPLAY/...),
  свести в единый реестр «стратегия -> сканер -> подюниверс -> риск-профиль», чтобы все технологии
  бота (breaker/edge/maker/coverage) работали на каждый рукав единообразно.

---

## ОБНОВЛЕНИЕ 3 (2026-07-07, сессия «всё по очереди»)

### A. AI-ВИДИМОСТЬ ОПЕРАТОРА — УЖЕ РЕАЛИЗОВАНА (нужна операционка, не код)
Продюсер `scripts/build_ai_full_context.py` + потребитель `bot/ai_context.py` +
`bot/live_position_view.py` уже собирают ПОЛНЫЙ read-only контекст: открытые позиции с
`upnl_usd`/SL/TP/runner-детализацией, `pnl_by_sleeve_usd` (45д из trades.db), `git_revision`,
`errors_tail` (80 строк), `att1_edge_health`, `alpaca_account_state`, router/allocator/regime.
Прогнал билдер — собрал валидный `runtime/ai_context/full_context.json` (189КБ, все ключи).
**ДЕЙСТВИЕ (операционное, не код):**
1. Убедиться, что на сервере крон гонит `python3 scripts/build_ai_full_context.py` раз в 5 мин
   (иначе full_context.json протухает и ИИ «слепнет»).
2. Убедиться, что full_context.json ВШИТ в промпт борт-ИИ (deepseek_signal_gate/advisor и web-chat).
   Если не вшит — это и есть причина жалоб «ИИ не видит»: инфра есть, а в промпт не подана.
3. (низкий приоритет) добавить в контекст флаг `runner_heartbeat_active` + `RUNNER_EXCHANGE_TP_ENABLE`,
   чтобы ИИ видел, что фикс раннера активен.

### B. ДОХОДНОСТЬ att1 — НАПРАВЛЕННЫЙ НАМЁК (нужен строгий харнесс)
Прогнал через `backtest/engine.py` на ADA+SOL (~42д, 11 сделок — МАЛО, один оконный срез):
base net −$31.1 PF0.60 | wide_tp2(5R) −$30.8 PF0.60 | pure_trail(без фикс.TP) −$22.6 PF0.71.
Намёк: «дать ехать» (pure_trail) слегка лучше лесенки; wide_tp2 ≈ база. НЕ вердикт (выборка мала,
окно негативное — норма для низкочастотки). **ДЕЙСТВИЕ:** пре-регистрированный прогон на многолетке
(wf_folds+oos_selector, cross-symbol, per-period, fee-stress 10/5): base vs pure_trail vs small_tp1(0.33)
vs структурный трейлинг (swing HL/LH). Метрика: expectancy_R, PF, MFE-capture, красные месяцы.
Структурный трейлинг требует правки engine (сейчас только ATR-чандельер) — сделать как опцию сигнала.

### C. КАСКАДНЫЙ РУКАВ — КОД ГРАМОТНЫЙ, RESEARCH-ONLY (правильно)
`bot/cascade_reversal.py` — причинный детектор (liq-спайк перцентиль + OI-флаш + funding z +
тайминг + направленный ход, side-split, без lookahead). `scripts/run_cascade_real_gate.py` —
корректный гейт на РЕАЛЬНЫХ ликвидациях (align liq/klines/funding/OI, fade-сим SL-first+fees,
4 хроно-фолда, coverage/preflight, пре-регистрированная сетка 16 комбо/сторона). В живой бот
детектор НЕ вшит — и это ПРАВИЛЬНО (не вшивать до гейта). Мёртв он был на PROXY-данных (PF0.26),
на реальном потоке не тестирован.
**ДЕЙСТВИЕ (путь в живой рукав):**
1. scp `runtime/liquidations/*.jsonl` с сервера -> `python3 scripts/run_cascade_real_gate.py
   --liq-jsonl <файл> --crypto-cache data_cache`. N<~30 -> «копить поток», не хоронить.
2. Если пульс -> wf_folds+oos_selector (OOS-символы) + per-period (bear/bull).
3. Только тогда live-wiring по образцу ATT1: `cascade_live.py` engine + entry-фн в боте +
   СВОЙ подюниверс (mid-cap alts, НЕ BTC/ETH — по докстрингу) + runner-выход (stop~1ATR/take~2ATR,
   лестница -> heartbeat-фикс её уже покрывает) + breaker + edge_monitor.

### D. ЗАЩИТА ОТ ДЕГРАДАЦИИ — ИНФРА ЕСТЬ, НО НЕ ВШИТА (P1 wiring)
Есть generic-кирпичи: `edge_monitor.assess_sleeve`/`assess_all`, `bot/sleeve_registry.py`,
`strategy_breaker.breaker_state` (+ хелпер `_sleeve_breaker_state_env`), portfolio allocator
(`global_risk_mult`/`degraded_sleeves`/`hard_block_new_entries`). НО:
- брейкер во входах зовут только 3/16 рукавов (att1, breakdown, range) — остальные без защиты;
- `assess_all`/`sleeve_registry` в живом цикле НЕ вызываются; allocator читает `degraded_sleeves`
  из внешнего файла, а не из живых исходов сделок.
**ДЕЙСТВИЕ (wiring>стройка):**
1. Единый pre-entry breaker-чек по `tr.strategy` во ВСЕХ входах (через `_sleeve_breaker_state_env`),
   env-конфиг на рукав; сначала soft (alert+risk_cut), hard после ревью. Осторожно: мисвайринг
   может заблокировать всю торговлю -> дефолт not-blocked при ошибке (fail-safe как у att1).
2. Живой «portfolio health loop» (в pulse раз в N мин): R по рукавам из trade_events -> assess_all ->
   пишет degraded_sleeves + risk_mult, которые читает allocator и каждый вход. Кирпичи готовы.

### ПОРЯДОК ДЕПЛОЯ (что деплоить прямо сейчас)
1. `smart_pump_reversal_bot.py` (runner heartbeat + safety-tp helper) — рестарт в flat-окно.
   Флаги: `RUNNER_HEARTBEAT_ENABLE=1` (уже дефолт), `RUNNER_EXCHANGE_TP_ENABLE=0` (включать позже с OK).
   Верификация: `[pulse]` лог + события runner_* по открытым позициям.
2. Крон `build_ai_full_context.py` раз в 5 мин + проверить, что JSON подан в промпт борт-ИИ.
3. Дальше по очереди: cascade real-liq гейт (C), portfolio health-gate wiring (D),
   строгий att1 exit-эксперимент (B).

---

## ОБНОВЛЕНИЕ 4 (2026-07-07, «делаем всё сразу»)

### PORTFOLIO HEALTH MONITOR — РЕАЛИЗОВАНО И ПРОВЕРЕНО (P1, защита от деградации)
Раньше здоровье мониторилось только у att1. Теперь — по ВСЕМ рукавам.
- Новый модуль `bot/portfolio_health.py`: R по каждому рукаву из trades.db (actual-risk
  qty*|entry-sl|) -> `edge_monitor.assess_sleeve` -> status (healthy/watch/degraded/halt) ->
  risk_mult (1.0/1.0/0.5/0.0). Юнит-тест зелёный (healthy vs halt).
- В боте: `_maybe_portfolio_health_check()` в pulse (rate-limited, дефолт 1ч) пишет
  `runtime/portfolio_health.json` и шлёт TG-алерт при смене статуса рукава. Функция
  `sleeve_health_risk_mult(strategy)` — fail-safe (любая ошибка -> 1.0).
- Флаги: `PORTFOLIO_HEALTH_ENABLE` (default ON, ALERT-ONLY), `PORTFOLIO_HEALTH_AUTOCUT`
  (default OFF), `PORTFOLIO_HEALTH_INTERVAL_SEC` (3600), `PORTFOLIO_HEALTH_LOOKBACK_DAYS` (45),
  `PORTFOLIO_HEALTH_PATH`. Бэкап `*.bak_health_*`.
- Проверено end-to-end: att1 healthy(1.0), inplay halt(0.0); при AUTOCUT=1 helper отдаёт 0.0,
  при OFF — 1.0. (Пофиксил falsy-zero баг `0.0 or 1.0`.)
- AUTO-CUT rollout (за кодексом, после ревью): в каждом входе домножить effective risk_mult на
  `sleeve_health_risk_mult(tr.strategy)`. Начать с att1/breakdown/range (там risk_mult уже в цепочке),
  потом остальные. Fail-safe гарантирует, что мониторинг-баг не заблокирует торговлю.

### ЧЕСТНАЯ ГРАНИЦА — что НЕ сделано из этой сессии и ПОЧЕМУ
- Каскадный рукав в live НЕ вшит: нельзя до прохождения гейта на РЕАЛЬНЫХ ликвидациях
  (данные только на сервере). Вшивать невалидированную стратегию на реальные деньги = нарушение
  правила проекта. Путь описан в Обновлении 3 (C).
- AI-крон (5 мин) и подача full_context.json в промпт — серверная операционка, не код.
- Структурный трейлинг + строгий многолетний att1 exit-эксперимент — требуют правки engine +
  большого компьюта/данных (не влезает в песочницу); пре-регистрация готова (Обновление 3 B).
- Auto-cut во ВСЕ 16 входов — требует пофайлового ревью и live-теста; helper готов, rollout за кодексом.

### ИТОГОВЫЙ ПОРЯДОК ДЕПЛОЯ
1. `smart_pump_reversal_bot.py` + `bot/portfolio_health.py` — рестарт в flat-окно.
   Флаги live: `RUNNER_HEARTBEAT_ENABLE=1`, `PORTFOLIO_HEALTH_ENABLE=1` (alert-only),
   `RUNNER_EXCHANGE_TP_ENABLE=0`, `PORTFOLIO_HEALTH_AUTOCUT=0`.
   Верификация: `[pulse]`, события runner_*, файл `runtime/portfolio_health.json`, TG health-алерты.
2. Крон `build_ai_full_context.py` (5 мин) + подача JSON в промпт борт-ИИ.
3. Cascade real-liq гейт (scp ликвидаций) -> при пульсе wf_folds/oos -> live-wiring по образцу ATT1.
4. Auto-cut rollout (helper готов) + строгий att1 exit-эксперимент.

---

## ОБНОВЛЕНИЕ 5 (2026-07-07 night queue — Codex)

### НОЧНЫЕ ПРОГОНЫ ЗАПУЩЕНЫ (research-only, no orders)
Создан воспроизводимый runner `scripts/run_codex_overnight_20260707.sh` и запущен в
`screen=codex_overnight_20260707`. Цель — не включать риск, а получить утром конкретные
цифры по ближайшим веткам: флет/отскоки/FX.

Логи: `logs/codex_overnight_20260707/`  
Сводный отчёт: `reports/research/codex_overnight_20260707/SUMMARY.md` после завершения.

Очередь:
1. `fx_native_h1_range_sweep` на `data_cache/forex_1h`: `session_range_fade`,
   `round_level_sweep`, `session_breakout_retest`, `trend_pullback`.
2. `fx_m5_multi_strategy_gate` на `data_cache/forex`: range/sweep/reclaim/session/trend
   семьи с мягкими exploration-порогами.
3. Два MRB/пила repair-варианта: более жёсткий z-score и быстрый mean-reversion выход.
4. `cascade_real_liq_gate` только если локально есть `runtime/liquidations/*.jsonl`;
   иначе шаг честно пишет `blocked` и не подменяет реальные ликвидации proxy-данными.

Первый факт до ухода: H1 FX native уже отработал; `XAUUSD` снова не прошёл coverage gate
на локальном H1-кэше (`coverage≈0.664`, max gap 66), поэтому золото всё ещё data-quality
blocker для строгого вывода. Это не live/no-live verdict по стратегии, а verdict по данным.

Параллельно оставлен существующий `screen=crypto_lm_sweep_reclaim_20260707b`: первые строки
имеют exploration-пульс (например combo 4: 83 trades, +11.8122R, PF 1.2998, 2/4 folds),
но это только билет на strict/OOS, не shadow/live.
