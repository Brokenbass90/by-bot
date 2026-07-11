# Project Recovery Truth and Roadmap — 2026-07-11

## Executive verdict

Проект не нужно переписывать целиком. В нём есть рабочие торговые и исследовательские рельсы, но кризис возник из-за трёх разрывов: research/live parity, недостоверная отчётность и продвижение слабых гипотез до получения независимых доказательств.

На 11 июля система ещё не является источником стабильного дохода:

- Alpaca защищена, но прибыльность live не доказана;
- Bybit торгует только ATT1 short tiny canary, его edge пока не подтверждён;
- второго денежного crypto-рукава нет;
- FX/CFD/OANDA остаются research-only: все шесть новых V2 сторон отрицательны;
- бортовой ИИ был свежим по runtime, но неполным и мог смешивать старые/грязные метрики с текущей системой.

Сессия дала измеримый результат: fail-closed ATT1 контракт, truth-first AI context, правдивые Alpaca/TG/web отчёты и первый настоящий event-first InPlay successor запушены в Git. В live/VPS эти изменения ещё не выкатывались.

## Текущая денежная правда

| Контур | Фактическое состояние | Решение |
|---|---|---|
| Alpaca LIVE | `$486.93` equity, `$328.45` cash/BP, `ABBV/ABNB/GE/SCHW`, текущий uPnL около `+$1.23`, broker stops `4/4` | SAFE-HOLD; не открывать новые позиции до exact-live parity |
| Bybit crypto | last direct check flat; только `ATT1 short r001`, effective risk `0.10` | оставить tiny canary, не масштабировать |
| Crypto shadow | IVB1 telemetry `risk=0`; текущая версия не прошла symbol-OOS | не продвигать в деньги |
| FX/CFD | капитал отсутствует; V2 `0/6` promotion PASS | не пополнять OANDA |
| DeFi/arbitrage | инфраструктурные заготовки и сбор данных, но не текущий кризисный приоритет | вернуться после двух доказанных core edges |

## Что реально сломалось в Alpaca

Alpaca сейчас не «починена как прибыльная стратегия» — она безопасно остановлена.

- Номинальная monthly v38 фактически вращалась ежедневно: семь roundtrip за три дня, `2W/5L`, около `-$5.716`, PF около `0.44`.
- Это не parity с месячным исследованием. Safe-hold с 10 июля остановил новые входы и stale/mid-month rotation; после его включения новых fills не было.
- Старый headline top4 воспроизводится на старом cache (`33` trades, PF `6.744`, compounded `+50.75%`), но cache заканчивается 27 апреля и выборка мала. Fresh forward top4 дал `+6.38%`, PF `2.22`, но только `N=2`.
- Первая неделя просадки поэтому не доказывает смерть momentum-идеи, но доказывает, что live-исполнение не соответствовало тесту.

Следующий Alpaca bake-off должен на одном источнике сравнить:

1. настоящий monthly top4 с фиксированной датой ротации;
2. ошибочную daily rotation как отрицательный контроль;
3. adaptive/cash-regime challenger;
4. top3 против top4, секторные/корреляционные лимиты и earnings-gap veto как отдельные ablation, а не один пакет.

Возвращать новые live-входы можно только на monthly boundary после свежего exact-live replay, восстановления ledger из broker fills и проверки broker stop/fill parity.

## ATT1: не сломана механически, но edge не доказан

Текущий ATT1 логически целостен: закрытые H1 свечи, подтверждённые pivots, shared research/live strategy class, next available execution, broker stop, runner, breaker и canary expiry.

При этом входная логика слаба в важных местах:

- при двух pivots линия всегда имеет `R²=1`, поэтому R² почти ничего не фильтрует;
- нет обязательного контракта `unbroken/respected/first-touch`;
- нет доказанного HTF/BTC/regime/order-flow meta-gate;
- чистая live-выборка мала: три автономных убыточных закрытия, а прибыль ADA была ручной и загрязняет итог.

Обнаружена live/test parity-разница: VPS effective `ATT1_RSI_SHORT_MIN=40`, а r001 contract требует `45`. Уже произошедшие четыре входа имели RSI выше 45, поэтому эта разница не объясняет прошлые стопы, но может разрешить более слабые будущие входы.

В Git теперь:

- базовый approved config fail-closed: ATT1 short `0.10`, все прочие risks `0`;
- active override содержит RSI `45`;
- heartbeat публикует полный effective ATT1 contract и SHA-256, полученный из реального strategy config;
- `24` ATT1/safety/geometry tests passed.

Не повышать winrate или частоту ослаблением фильтров. Следующий challenger: минимум три независимых pivots, unbroken/respect/first-touch geometry, frozen level age, regime/BTC-beta и maker/retest execution — каждый компонент отдельным prereg ablation.

## Имбалансы и InPlay

Полноценной стратегии FVG/order-block в проекте раньше не было.

Есть три другие технологии, которые нельзя путать с ней:

- legacy buy/sell trade-flow imbalance;
- snapshot order-book pressure без исторического L2 replay;
- OHLC liquidity sweep/level-memory research, пока без promotion.

FVG/order block разумно добавить позже как deterministic context: closed three-candle gap, ATR minimum, creation/fill/invalidation timestamps и first mitigation. Он остаётся только если ablation улучшает OOS/stress/breadth, а не потому что выглядит убедительно на графике.

Старый InPlay не был стратегией «разгон → истощение → сдутие». Это rolling 4H breakout + M5 retest continuation. Clean short test: `N=42`, stress PF `1.075`, только ETH/AVAX, концентрация `67.7%`; verdict `NO_PROMOTION`.

Создан новый research-only `pump_exhaustion_unwind_short_v1`:

- strictly short-only;
- causal closed bars;
- frozen pre-event horizontal/sloped/liquidity highs;
- FSM `expanded → exhausted → bearish CHoCH → failed reclaim → one next-open plan`;
- immutable event ID, seen/planned ledgers, expiry/invalidation;
- реальные structural contacts без выдуманных touches;
- `58` связанных tests passed.

Cache smoke подтверждает только жизнеспособность механизма, не edge: на последних `9,000` M5 барах BTC дал 0 events, ETH 2 events/1 plan, DOGE 1 event/0 plans.

До shadow обязательны persisted event state и отдельный frozen prereg runner с source SHA, cache gate, next-open gaps, base/stress costs, timestamp occupancy, folds/embargo и untouched holdout.

Второй successor остаётся следующим: `event_expansion_retest_long_v1` — breakout/hold качественного frozen уровня и только первый ретест сверху. Long и short никогда не объединяются в одну статистику.

## Уровни

Отдельные level-компоненты уже есть: `market_context`, `unified_levels`, `level_memory`, liquidity map/sweep и renderer. Но единого обязательного контракта, которым одновременно пользуются research, live, web-chart и AI, пока нет. ATT1 по-прежнему строит собственную trendline geometry.

Целевая level service должна выдавать versioned snapshot с:

- horizontal, sloped, flip и liquidity levels;
- подтверждёнными pivots, touches/respects, broken/invalidation history;
- `created_at`, `valid_at`, `source_bars_sha`, projection timestamp;
- first-retouch/age/distance/quality;
- одинаковым snapshot/hash для backtest, live decision, web drawing и TG/AI explanation.

## FX/CFD/OANDA

Три новые V2 семьи уже написаны причинно и проверены раздельно long/short:

| Sleeve | Stress PF | N | Verdict |
|---|---:|---:|---|
| impulse breakout/retest long | `0.609` | 26 | NO_PROMOTION |
| impulse breakout/retest short | `0.382` | 16 | NO_PROMOTION |
| sweep/reclaim long | `0.747` | 101 | NO_PROMOTION |
| sweep/reclaim short | `0.690` | 101 | NO_PROMOTION |
| range/pila long | `0.394` | 28 | NO_PROMOTION |
| range/pila short | `0.587` | 41 | NO_PROMOTION |

Это не только costs: все base rows также отрицательны. Кроме того, strict data quality сейчас `0/6` promotion-grade symbols; четыре пары diagnostic-only, EURJPY/XAU blocked.

OANDA сейчас не пополнять. Текущий ожидаемый результат по имеющимся доказательствам отрицательный; положительную доходность называть нельзя.

Следующие V3 гипотезы:

1. `failed_break_retest_short_v3` — отдельный retest снизу после failed break;
2. `horizontal_range_rejection_v3` — только flat horizontal range, sloped level как context/veto;
3. `range_edge_expansion_retest_v3` — frozen range/flip edge и first retest.

Перед любым demo gate нужны fresh M5, broker holiday/news calendar, calibrated bid/ask/slippage и native OANDA execution parity. Деньги рассматриваются только после strict PASS и минимум 30 чистых demo closes.

## ИИ-оператор, web и Telegram

Бортовой ИИ пока не максимальный автономный оператор. Он был свежим по cron, но видел конфликтующие источники: старый approved risk `0.70`, heartbeat `0.10`, stale ATT1 health, смешанный `N=11`, старую Alpaca метрику `+63%` и не видел последние FX/InPlay verdicts.

В Git добавлены:

- human-reviewed canonical machine state;
- per-source filesystem freshness;
- приоритет `fresh heartbeat → broker positions → canonical state → allocator → env`;
- `control_recommendations_allowed=false` при stale/conflicting critical truth;
- ATT1 effective config/hash в compact AI context;
- web trading controls помечены proposal-only, пока нет acknowledged live consumer;
- weekly AI forensics разделяет mixed historical cohort, clean cohort и post-hoc candle cache;
- Alpaca TG показывает LIVE/PAPER, safe-hold, фактические holdings, fractional qty, broker stops, base/DD и `DATA_INVALID` ledger;
- weekday post-close report и delivery watchdog.

ИИ должен искать, объяснять, сравнивать challengers и диагностировать. Он не должен свободно оптимизировать live параметры или сам повышать риск: это путь к автоматизированному overfit.

## Git и VPS truth

- Local/origin: `e286534` на ветке `codex/dynamic-symbol-filters`.
- VPS checkout: `f7ed011`, на 22 commits позади.
- Все изменения этой сессии запушены в Git.
- На VPS они не deployed; действующий сервер продолжает безопасный ATT1 override `risk=0.10` и Alpaca safe-hold, но ещё без RSI45/report/AI truth patches.
- Полный blind pull запрещён: VPS содержит ручные/dirty/untracked файлы. Нужен manifest, backup, clean release checkout, targeted config migration, flat-window restart и post-deploy heartbeat/config-hash verification.
- Untracked archives не удалять вслепую. После проверки ссылок их можно вынести из рабочей копии в датированный quarantine/archive каталог.

## План и сроки

### Следующие 1–2 рабочие сессии

1. Targeted VPS deploy fail-closed ATT1 config/helper/monolith delta; только при flat, затем проверить RSI `45`, risk `0.10`, all other risks `0`, override loaded, expiry и expected SHA.
2. Deploy truth-first AI context и Alpaca reports без изменения trading logic; установить recurring crons и проверить реальную доставку.
3. Восстановить Alpaca intraday v1 ledger из broker fills и провести exact monthly-vs-daily-vs-adaptive replay.

### 3–7 дней

1. Построить frozen prereg runner для pump-exhaustion successor и первый 360–720d data gate.
2. Реализовать long successor с тем же persisted event protocol.
3. Обновить FX M5/news/holiday/bid-ask evidence и заморозить V3 configs до просмотра результатов.

### 1–2 недели

- Возможен только risk-zero shadow у кандидата, прошедшего stress PF `>=1.20`, `N>=40`, `3/4` positive folds, breadth/LOSO/holdout и concentration `<35%`.
- Если PASS нет, фиксируется новый binding NO_GO/repair — дата не превращает FAIL в canary.

### 1–3 месяца

- Tiny-money второй crypto или FX sleeve возможен только после `30` clean shadow/demo closes. Оптимистичное окно — сентябрь–декабрь 2026; при низкой частоте позже.
- Цель периода — один контролируемый money sleeve и два независимых healthy shadows, а не три поспешно включённых money sleeves.

### Доход

Стабильный семейный доход по календарю обещать нельзя. Даже `20%` годовых на `$500` — всего `$100` в год до налогов/издержек. Для дохода нужны одновременно доказанный edge, достаточный капитал и независимость рукавов. Реалистичный ближайший milestone — перестать терять из-за parity/операционных ошибок и доказать два независимых edge. Решение о регулярных выводах принимается только после нескольких месяцев clean live history и portfolio drawdown evidence.

## Протокол продолжения между чатами

Каждый новый чат обязан:

1. прочитать этот файл и `PROJECT_CANONICAL_INDEX_2026_07_10.json`;
2. проверить direct Git/VPS/broker freshness, не доверять старому snapshot;
3. продолжить первый незавершённый `next_action`, а не повторять общий аудит;
4. в конце обновить machine index, этот roadmap при изменении решения и append-only ledger;
5. явно записать: что pushed, что deployed, что live behavior изменилось, что осталось local-only.

Главный принцип: исследовать широко, продвигать узко, считать правдой только воспроизводимое и свежее.
