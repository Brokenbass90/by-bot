# Recovery checkpoint — 2026-07-14

Это короткая human-reviewed точка продолжения. Она дополняет, а не переписывает историю 13 июля. При конфликте приоритет неизменен: direct broker/exchange -> свежий heartbeat и effective config -> targeted release receipt/SHA -> immutable preregistered research -> отчёт -> AI interpretation.

## Что сейчас действительно live

- Bybit: единственный денежный crypto sleeve — `ATT1 short-only`, `risk_mult=0.10`. Edge всё ещё не доказан, риск и частоту не повышать. После targeted deploy исправления partial-close PnL сервис был контролируемо перезапущен в flat-окне; после restart broker оставался flat, live risk не менялся.
- Alpaca: реальная денежная ветка — monthly v38 в `SAFE_HOLD`, а не intraday. Защита stale holdings исправлена commit `cc3ef8a`, pushed и адресно deployed. Quantity-aware broker truth/web package `66ffa02` также pushed и targeted deployed. Последний post-action receipt authoritative: `ABBV/ABNB/GE/SCHW`, точное покрытие stop quantity `4/4`, under/over-protection отсутствует; новые входы и принудительная stale-ротация выключены.
- Alpaca post-close Telegram report за 13 июля доставлен; watchdog подтвердил `delivered_today`. Ручной restart `bybot.service` для Alpaca не требуется: monthly manager — отдельный cron one-shot.
- FX/CFD: только research, capital/order authority нет.
- VPS checkout по-прежнему старый и dirty (`f7ed011` на последней проверке). Runtime truth — адресно установленные файлы и receipts; blind pull/reset/cleanup запрещены.

## Git, deploy и локальная работа — не смешивать

| Пакет | Git/origin | VPS/live | Статус |
|---|---|---|---|
| Bybit aggregate partial-close PnL (`3f6278b`, `12a9abd`) | pushed | targeted deployed; core restarted flat | live accounting path обновлён; старую ADA-историю не считать автоматически reconciled |
| Alpaca SAFE_HOLD stale-position stop rearm (`cc3ef8a`) | pushed | targeted deployed; GE stop восстановлен, coverage `4/4` | live protection исправлена без buys/closes |
| Alpaca broker-truth receipt + web truth-first rendering (`66ffa02`) | pushed | targeted deployed; SAFE_HOLD one-shot refreshed authoritative truth; web restarted | quantity coverage `4/4`; login secret replay still pending |
| AI single-mission + feed-bound replay (`41da86d`) | pushed | not deployed; no broker/TG/live wiring | research-only; one mission replay, no promotion authority |
| Event-long uniform dev13 window (`5801cc6`) | pushed | research-only, not deployed | deep integrity PASS; `8` blockers; performance/live forbidden |
| Replayable Bybit L2/publicTrade collector (`4db0f4d`) | pushed | two bounded collectors running locally, not VPS | ONDO L2+trades and 6-symbol trades; data clock only |

На контрольной точке после публикации local/origin HEAD совпадают на `4db0f4dc3aca5bafd115b426f8644049518ddf90`. Полный regression: `1283 passed`. Working tree всё ещё намеренно dirty из-за старых чужих FX edits и большого historical untracked набора; `bot/fx_setups.py` и `tests/test_fx_setups.py` в эти commits не попали.

## Alpaca: monthly и intraday — разные системы

- Real-money authority сейчас у monthly v38 `SAFE_HOLD`. Это низкочастотная ротация; она не должна становиться «более динамичной» только ради количества сделок.
- Intraday v1 — отдельный `$100k` paper ledger с проблемами fill reconciliation; intraday v3 — dry-run/shadow. Ни один из них не является текущей денежной Alpaca-стратегией.
- Первая отрицательная неделя выявила daily-rotation parity defect. Это не исправляется повышением оборота. Следующий допустимый шаг — exact broker-fill/parity replay monthly logic с costs, daily MTM/DD, PIT universe и shared exits.
- Старые сильные backtest-цифры остаются selected historical evidence, не live PnL и не прогноз. `SAFE_HOLD` не снимать до нового gate.

## Crypto: состояние и следующая корзина

### ATT1

- Механика runner/stop/partial/BE/trail целостна, но entry geometry недостаточно строга: two-pivot line делает `R²` малоинформативным; mandatory unbroken interval, first retest, bounded overshoot и достаточное число respects отсутствуют.
- Поэтому AI мог справедливо назвать некоторые входы визуально нелогичными, хотя код формально выполнил свой контракт. Live baseline не править post-hoc; отдельный challenger сначала preregister.
- Canary требует explicit review `2026-07-20`. Bybit API key expires `2026-08-12`; безопасная ротация — до `2026-08-05`, без передачи секрета в чат.

### Кандидаты, но не live-разрешения

1. `event_expansion_retest_long_v1`: физически long-only, horizontal H1/H4, closed M5 -> M15/H1/H4, exact execution contract. Published uniform-window artifact закрыл один data-identity blocker: deep integrity PASS на `13 x 207241` M5 rows, остаётся `8` blockers. `PERFORMANCE_FORBIDDEN`, `LIVE_FORBIDDEN` сохраняются.
2. Horizontal range rejection: отдельные long-only и short-only sleeves на общем hash-pinned LevelSnapshot. Это правильный successor для «пилы/отскоков»; не возвращать старые ARS1/ASB2 сетки.
3. Microstructure/liquidity: только после replayable L2 deltas + publicTrade tape. Текущие 30-second density summaries не позволяют восстановить книгу и не доказывают imbalance edge.

Strict pump successor уже завершён `NO_PROMOTION`; его gates не ослаблять и grid не повторять. Elder использовать только как filter/ablation. InPlay не возвращать по старым результатам: event-first или tape-based successor должен получить отдельный prereg.

## Event-long: не повторять phase-1

Уже закрыты causal mechanics, LevelSnapshot v1, closed-bar aggregation, MTF sequence, exact next-open execution, stop-first ambiguity, frozen exits, authenticated bridge и atomic single-writer state/outbox. Локальная uniform dev13 virtual crop:

- 13 symbols, одно закрытое contiguous M5 окно;
- input/source hashes PASS, performance не вычислялась;
- blocker `DEV13_UNIFORM_WINDOW_MANIFEST_ABSENT` закрыт только как input identity;
- остаются 8 blockers: performance runner; durable receipt-before-ACK runner; funding completeness; external8 market data, metadata, liquidity, funding; same-window ATT1 reference.

Jul14 amendment опубликован commit `5801cc6`. Он доказывает только identity/contiguity входов, не edge. Performance/live остаются запрещены.

## FX/CFD: данные есть, готового edge нет

- Dukascopy M5 уже существует для шести инструментов примерно за 728 дней. Повторно «разблокировать FX загрузкой M5 с нуля» не нужно.
- Data uniqueness/OHLC hashes пригодны для диагностики, но promotion-grade symbols всё ещё `0`: есть missing/off-schedule runs, snapshot stale, нет pinned macro-news coverage и account-specific bid/ask/commission/financing contract.
- V2 уже честно отрицателен во всех шести side-specific sleeves:

| Sleeve | Base PF | Stress PF | N |
|---|---:|---:|---:|
| impulse long / short | `0.793` / `0.414` | `0.609` / `0.382` | `26` / `16` |
| sweep long / short | `0.832` / `0.859` | `0.747` / `0.690` | `101` / `101` |
| range/pila long / short | `0.566` / `0.747` | `0.394` / `0.587` | `28` / `41` |

- Следующий research scope: failed-break retest short; horizontal range rejection long/short; range-edge expansion/retest long/short. Старый V2 grid не повторять и thresholds после просмотра не ослаблять.
- В локальном окружении обнаружены cTrader/MT5 credential names, но cTrader execution adapter отсутствует; OANDA credentials отсутствуют. Наличие ключей не требуется для historical backtest и не даёт готового broker path. Secrets в отчёты не переносить.

## AI, screener, web и Telegram

- Внутренний AI сейчас полезен как observer/advisor: получает heartbeat, regime, allocator, positions, setup cards, no-signal/PnL/Alpaca/errors и canonical truth. Он не должен сам менять risk или отправлять orders.
- DeepSeek signal gate, AI setup scores и web backtest inbox не имеют доказанного единого live consumer. Нельзя писать в UI, что AI «торгует», пока нет deterministic execution path и immutable receipts.
- Безопасный one-shot AI experiment опубликован commit `41da86d`: `SELECT one frozen deterministic card or ABSTAIN`, closed M5, один active mission, frozen risk/exit, hash-pinned feed, adverse same-bar handling, atomic receipt и kill switch. Entry/exit/timestamps нельзя передать вручную. Он остаётся физически shadow-only: `promotion_authority=false`, post-hoc selection не исключён, broker/TG/live wiring отсутствует.
- Screener сейчас фрагментирован: standalone coin screener, monolith `/coins` и web setup cards не являются одной parity-системой. Standalone path использует forming H1; web cards показывают heuristic setup, а не точный strategy signal. До унификации это context telemetry, не authority для сделки.
- Web truth-first/friendly-auth package `66ffa02` deployed. `trading-journal-web` был явно restarted: PID `2863782`, startup complete, `/ping={"pong":true}` на `127.0.0.1:8765`. Owner user/TOTP config существует, но successful password/TOTP replay после `Unauthorized` не выполнен: patch улучшает сообщение, а не доказывает правильность введённого пароля.
- Telegram delivery имеет историческую фрагментацию `TG_CHAT`/`TG_CHAT_ID`; Alpaca scheduled report на этот раз доставлен, но каналы и delivery receipt нужно унифицировать.

## Research clock

- Активного overnight performance backtest/autoresearch нет: `configs/research_nightly_queue.json` и `configs/research_priority_24h_20260626.json` имеют `enabled=false`; случайный grid не запускался.
- Replayable data clock запущен локально: screen `l2_ondo_v1_20260714` пишет ONDO depth-50 L2+publicTrade с cap `20 GiB`; `trades_micro_v1_20260714` пишет publicTrade для `ONDO/WIF/SUI/DOGE/1000PEPE/FIL` с cap `8 GiB`; `tape_keepawake_20260714` удерживает открытый Mac от idle-sleep максимум семь суток. Оба collector-процесса public-only, без keys/orders, retention=`stop`, min-free=`80 GiB`. Первый read-only replay ONDO: snapshot `1`, deltas `354`, trades `18`, gaps `0`, valid PASS. Это сбор данных, не performance verdict.
- Не запускать случайную широкую сетку «чтобы компьютер не простаивал». Следующий долгий запуск обязан иметь prereg, pinned data/costs, progress/receipt и автоматический stop on failed integrity.

## Следующая исполнимая очередь

1. Event-long: single-owner completed-bar runner с durable bridge/trade receipts before ACK, ambiguous-write recovery и funding-completeness proof. Outcomes до нового hash-pinned authorization не открывать.
2. Проверять freshness/coverage и суточный объём двух tape collectors; после первых полных суток подтвердить compression ratio и скорректировать disk horizon. Старый density collector не подменяет tape.
3. Материализовать девять Alpaca exact-parity inputs и прогнать monthly/adaptive/daily-control на одной broker-fill/cost/exit механике. До verdict сохранять SAFE_HOLD.
4. Создать новый FX V3 prereg после pinning news/cost/account contract; использовать существующий M5 cache, сначала repair/refresh data, потом performance.
5. Провести ATT1 canary review 20 июля по broker-reconciled logical trades. Geometry challenger preregister отдельно; не масштабировать автоматически.
6. После verdict event-long — отдельные horizontal range rejection long и short; только прошедшие strict gate могут перейти в risk-zero shadow.
7. Подключать реальный model call к AI mission только после deterministic screener parity; сначала shadow batch с frozen prereg, затем сравнение AI SELECT против механического baseline.

## Реалистичный календарь до трёх рукавов

- До `2026-07-20`: ATT1 review, Alpaca parity inputs, проверка первых полных суток tape. Это не обещание второго money sleeve.
- `2026-07-20`–`2026-08-07`: первые честные verdicts event-long/horizontal range и FX V3 при наличии pinned news/cost inputs; прошедшие кандидаты идут только в risk-zero shadow.
- Август–сентябрь: возможен второй tiny-money sleeve после strict OOS + shadow/demo sample. Три независимых денежных рукава реалистичнее ожидать в августе–октябре, только если минимум два кандидата реально пройдут ворота.
- Частая microstructure/liquidity торговля требует накопления `60–90` дней tape; ранний честный research — после `7–14` дней, promotion-grade вывод — не раньше сентября–октября.

## Запрещено без нового gate и owner approval

- повышать ATT1/Alpaca risk, включать второй money sleeve или торговать «на всю котлету»;
- выдавать local/Git change за live deploy;
- запускать event-long/FX outcomes при `PERFORMANCE_FORBIDDEN`/data blockers;
- снимать Alpaca `SAFE_HOLD`;
- считать web heuristic card или AI opinion исполнимым signal;
- blind pull/reset/cleanup dirty VPS;
- смешивать long/short physical identities;
- обещать доход или использовать selected backtest как прогноз.

## Source of truth

- текущая карта: `reports/PROJECT_CANONICAL_INDEX_2026_07_14.json`;
- продолжение: `reports/NEXT_CHAT_START_PROMPT_2026_07_14.md`;
- подробная предыдущая точка: `reports/RECOVERY_CHECKPOINT_2026_07_13.md`;
- Alpaca evidence: `reports/ALPACA_TRUTH_AND_NEXT_TEST_2026_07_13.md`;
- FX evidence: `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`;
- event phase-1: `reports/EVENT_EXPANSION_RETEST_LONG_V1_PHASE1_FREEZE_2026_07_13.md` и published Jul14 uniform amendment (`5801cc6`);
- tape start receipt: `reports/L2_TAPE_COLLECTION_START_2026_07_14.md`;
- immutable project history: `reports/PROJECT_STATE_LEDGER.md`;
- AI-consumable state: `configs/ai_operator_canonical_state.json`.
