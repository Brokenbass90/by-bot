# Project Recovery Truth and Roadmap — 2026-07-11

## Executive verdict

Проект не нужно переписывать целиком. В нём есть рабочие торговые и исследовательские рельсы, но кризис возник из-за трёх разрывов: research/live parity, недостоверная отчётность и продвижение слабых гипотез до получения независимых доказательств.

На 11 июля система ещё не является источником стабильного дохода:

- Alpaca защищена, но прибыльность live не доказана;
- Bybit торгует только ATT1 short tiny canary, его edge пока не подтверждён;
- второго денежного crypto-рукава нет;
- FX/CFD/OANDA остаются research-only: все шесть новых V2 сторон отрицательны;
- бортовой ИИ был свежим по runtime, но неполным и мог смешивать старые/грязные метрики с текущей системой.

Сессия дала измеримый результат: fail-closed ATT1 контракт, truth-first AI context, правдивые Alpaca/TG/web отчёты и первый настоящий event-first InPlay successor запушены в Git. ATT1/AI/report/web изменения затем установлены на VPS адресно, без blind pull; бот и web перезапущены, отчётные cron-задачи установлены. VPS Git checkout при этом намеренно не выравнивался и остаётся старым/грязным: deployed disk truth и `git rev-parse` на сервере теперь нельзя считать одним и тем же.

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
- Сравнимая 24-месячная annualization для exact top4 равна `22.7804%` CAGR при условной 100%-ной инвестиции кривой; свежий overlap дал `25.7291%`, но это не untouched OOS. При фактическом target allocation `70%` грубое масштабирование даёт около `15.64–17.60%` до проскальзывания, гэпов и налогов. Отдельный 12m OOS raw `+27.9496%` масштабируется примерно до `19.08%`, но там только `N=15`. Это диапазон исследовательских сценариев, не прогноз live-дохода.
- Первая неделя просадки поэтому не доказывает смерть momentum-идеи, но доказывает, что live-исполнение не соответствовало тесту.
- Exit parity также не готова: текущие fractional holdings защищены простыми broker `DAY` stops `4/4`; native trailing для fractional позиций отсутствует. В live настроен poll-dependent software trail с фиксированным arm `+3.5%` и drawdown `3.5%`, тогда как research-модель использует `BE 0.8R + ATR 1.5`. Нельзя утверждать, что live трейлинги воспроизводят тест.

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

Обнаруженная live/test parity-разница `ATT1_RSI_SHORT_MIN=40` против r001 `45` адресно исправлена. После рестарта 11:13 UTC heartbeat подтвердил short-only, risk `0.10`, RSI `45`, выключенные flat/range, expiry `2026-07-20` и contract SHA-256 `fd8048f7b6fd483a6d246969ec5f72782c780a1dcbb9df373f2d6a966161eeb6`; direct Bybit был flat. Это подтверждает effective configuration, но не edge стратегии.

В Git теперь:

- базовый approved config fail-closed: ATT1 short `0.10`, все прочие risks `0`;
- active override содержит RSI `45`;
- heartbeat публикует полный effective ATT1 contract и SHA-256, полученный из реального strategy config;
- `24` ATT1/safety/geometry tests passed.

После этого был закрыт отдельный P0 в runtime watcher: `auto_apply_params.env` раньше мог применяться после старта даже при `ALLOW_AUTO_APPLY_OVERRIDES=0`, а dynamic allowlist мог менять не только symbols. Commit `f459e9f` требует две отдельные авторизации для auto-apply hot reload, по умолчанию разрешает dynamic overlay только для universe/router metadata и сохраняет приоритет operator override. Патч установлен адресно, бот повторно перезапущен 11:18:48 UTC; direct Bybit снова подтвердил `open_position_count=0`, новый heartbeat появился в 11:19:13 UTC. Полный ATT1 field/hash dump после именно второго рестарта не был повторён из-за tool-usage limit; точная проверка выше относится к рестарту 11:13 UTC.

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
- restart-safe atomic state envelope с schema/version, source fingerprint, payload checksum и отдельными bounded seen/planned ledgers;
- corrupt/schema/source/hash/symlink mismatch закрывается fail-closed и не сбрасывает state в пустой;
- frozen 720d prereg фиксирует `13` symbols, short-only, next-open, base/stress costs, `4` folds, `7d` embargo, untouched `120d` holdout, breadth/LOSO/concentration gates;
- полный regression после persistence/preflight: `1019 passed`.

Cache smoke подтверждает только жизнеспособность механизма, не edge: на последних `9,000` M5 барах BTC дал 0 events, ETH 2 events/1 plan, DOGE 1 event/0 plans.

Persistence и strict preflight теперь готовы, но performance ещё не запускался. Preflight source SHA и state fingerprint проходят; permission=`BLOCKED_FAIL_CLOSED`, потому что immutable 720d snapshots для всех `13` symbols ещё не materialized/hash-pinned. До shadow обязательны data-freeze commit, evaluator с gap/exit/timestamp-occupancy parity и полный frozen outcome gate. Нельзя трактовать data blocker как результат стратегии.

Второй successor остаётся следующим: `event_expansion_retest_long_v1` — breakout/hold качественного frozen уровня и только первый ретест сверху. Long и short никогда не объединяются в одну статистику.

## Уровни

Отдельные level-компоненты уже есть: `market_context`, `unified_levels`, `level_memory`, liquidity map/sweep и renderer. Но единого обязательного контракта, которым одновременно пользуются research, live, web-chart и AI, пока нет. ATT1 по-прежнему строит собственную trendline geometry.

Целевая level service должна выдавать versioned snapshot с:

- horizontal, sloped, flip и liquidity levels;
- подтверждёнными pivots, touches/respects, broken/invalidation history;
- `created_at`, `valid_at`, `source_bars_sha`, projection timestamp;
- first-retouch/age/distance/quality;
- одинаковым snapshot/hash для backtest, live decision, web drawing и TG/AI explanation.

## Частая crypto-торговля: честный прогон завершён отрицательно

Аудит не подтвердил, что «пила, Elder и отскоки» можно просто включить вместе. Текущая полезная очередь ограничена двумя причинными вопросами:

1. `alt_range_scalp_v1` / ARS1 — Bollinger-range «пила», физически раздельные `long-only` и `short-only`, один ablation `ADX off → ADX <= 25`;
2. `alt_support_bounce_v2` / ASB2 — long-only от shared horizontal/channel supports, один ablation: запрет descending channels.

Elder не поставлен в новую сетку: его V2 live и V3 research не имеют parity, а существующие результаты отрицательны/хрупки. ARF1/ARF2 и legacy ASB1/ASR1 также не переиспытываются без нового причинного дефекта: это сократило бы время, но увеличило selection bias.

Frozen prereg находится в `configs/preregistered/frequent_crypto_20260711.json`; данные — `13` заранее выбранных symbols, coverage `>=98%`, max internal gap `<=12` M5 bars, `360d + fresh 90d`, next-open execution, base/stress costs и side-specific gates. Run `20260711_111740` помечен `ABORTED_BEFORE_OUTCOME`, run `20260711_111943` — `INVALID_INCOMPLETE_RUN`; их цифры нельзя использовать.

Единственная immutable очередь была запущена в detached screen `93788.frequent_crypto_prereg_20260711`; canonical output — `reports/research/frequent_crypto_prereg_20260711/20260711_112429/`. Она frozen на code head `f459e9f`, содержит `15` prereg cases, risk-zero, без broker calls. Все `15` cases завершились, runner записал `COMPLETE` в `2026-07-11 11:58:49 UTC`; data/execution/side-purity gates прошли.

Итог зафиксирован в `reports/FREQUENT_CRYPTO_VERDICT_2026_07_11.md`: `NO_PROMOTION` для всех трёх sleeves. ARS1 long ADX25 дал PF `0.374` base, `0.292` stress и `0.821` на fresh 90d stress; ARS1 short ADX25 — `0.682`, `0.550`, `0.514`; ASB2 no-descending long — `0.754`, `0.524`, `0.639`. Short ADX-off control оказался лишь около нуля: PF `1.139` base и `1.005` stress, ниже frozen gates. Ни один кандидат не допускается даже в shadow; threshold-grid на этом же окне запрещён.

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

Эти три V3 семьи уже реализованы и заморожены в commit `ba53710`:

- `failed_break_retest_short_v3` — только short;
- `horizontal_range_rejection_v3` — long и short считаются отдельно;
- `range_edge_expansion_retest_v3` — long и short считаются отдельно.

Текущий preflight корректно завершился статусом `DATA_DIAGNOSTICS_ONLY`: performance research запрещён; promotion-grade symbols `0`; diagnostic-only `EURUSD/GBPJPY/GBPUSD/USDJPY`; historical macro news artifact отсутствует/не закреплён hash, target OANDA cost calibration отсутствует/не закреплена, strict data gate не пройден. Runner не создавал strategy PnL, demo orders или live orders. Поэтому наличие V3-кода не означает готовность OANDA или положительные цифры.

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

Эти observability-патчи установлены на VPS. Human-reviewed canonical state и итоговые frequent-crypto/FX V3 verdicts адресно установлены в `16:25 UTC`, после чего `runtime/ai_context/full_context.json` пересобран: canonical `as_of=2026-07-11T16:15:00Z`, critical blockers пусты, analysis recommendations разрешены, но live control остаётся proposal-only.

Web-auth отдельно усилен в commits `c307085` и `18050bf`: дефолтный JWT заменён атомарно на новый 256-bit server-only secret в `/root/by-bot/.env.local` с mode `600`, а стартовый скрипт больше не пишет даже префикс секрета в journal. Перезапущен только `trading-journal-web`; новый PID `2761068`, `/ping={pong:true}`, `/auth/me` и `/api/health` без cookie возвращают `401`, listener остаётся только `127.0.0.1:8765`. `WEB_COOKIE_SECURE=0` сейчас необходим для plain HTTP через SSH tunnel, поскольку HTTPS reverse proxy и listeners `80/443` отсутствуют. Реальный password/TOTP login после ротации не replayed — если UI продолжит отвечать `Unauthorized`, следующая проверка должна быть owner login, а затем безопасный password reset без передачи пароля в чат.

Alpaca broker-truth dry-run прошёл. Установлены weekday post-close report `22:10 UTC`, monthly day-1 report `22:20 UTC` и weekday delivery watchdog `23:00 UTC`. Watchdog dry-run в субботу законно вернул `not_due`; первый автоматический post-close ожидается в понедельник 13 июля. Manual real Telegram digest успешно доставлен в `11:22 UTC`.

Два truth-refinement commits также проверены на VPS по SHA: `4de548b` различает order-submit mode report process и scheduled position-manager poll; `115d032` сохраняет source mtime и делает atomic replace при live-mirror sync, чтобы копирование stale payload не делало его визуально fresh. Последний файл установлен с backup `/root/by-bot-backups/live_mirror_115d032_20260711T161011Z`.

ИИ должен искать, объяснять, сравнивать challengers и диагностировать. Он не должен свободно оптимизировать live параметры или сам повышать риск: это путь к автоматизированному overfit.

## Git и VPS truth

- Current implementation/research head перед этим документационным checkpoint: `202aead` ветки `codex/dynamic-symbol-filters`, совпадает с origin. Новые ops/research commits: `3818a0a` (targeted release manifest), `f95cd3e` (first web/canonical manifest), `e919ec3` (persisted pump state + strict preflight), `202aead` (frozen prereg + blocked evidence).
- VPS Git checkout остаётся `f7ed011`, dirty; Git там не pull/advance. Адресно установленные disk files новее server HEAD, поэтому `git status`/`rev-parse` не описывают deployed runtime полностью.
- Первый targeted пакет ATT1/AI/Alpaca reporting/web установлен с backup `/root/by-bot-backups/targeted_580d845_20260711T111235Z`. `bybot` после него подтвердил точный ATT1 contract/hash и flat.
- Watcher P0 пакет (`bot/allowlist_watcher.py`, `configs/approved_strategy_params.env`) установлен с staging PASS и backup `/root/by-bot-backups/watcher_f459e9f_20260711T111848Z`. Read-only проверка в `16:10 UTC` после второго restart подтвердила direct Bybit positions `0`, ATT1 short-only, risk `0.10`, RSI `45`, expiry `2026-07-20`, exact hash `fd8048f7…`; единственный money sleeve — ATT1.
- Web restart и report cron install подтверждены отдельно; auth login не replayed, первый scheduled Alpaca delivery ещё не наступил. Manual TG delivery прошла.
- SHA всех адресно развёрнутых ATT1/AI/Web/Alpaca-reporting файлов, включая `4de548b` и `115d032`, совпал с локальным implementation checkpoint. Это не делает старый server checkout чистым: VPS Git HEAD всё ещё `f7ed011` и dirty.
- Canonical AI/report bundle установлен с backup `/root/by-bot-backups/ai_canonical_3c26464_20260711T162537Z`. Web code backup: `/root/by-bot-backups/web_auth_code_20260711T162806Z`; JWT-файл создан впервые, поэтому старого `.env.local` для backup не существовало.
- Full local regression после всех изменений: `1019 passed`.
- Первый explicit-file manifest записан в `reports/releases/targeted_web_canonical_4c7f645_20260711.json`; он фиксирует SHA/size/mode семи точно известных web/canonical файлов и честно помечает dirty source tree. Полный blind pull по-прежнему запрещён. Следующий ops этап — расширить manifest на весь deployed set и перенести server-only state вне tracked tree, не удаляя архивы/backup-env/ручные файлы без reference audit.

## План и сроки

### Ближайшие 0–24 часа

1. Не перезапускать завершённую frequent-crypto queue и не тюнить ADX/ASB2 по увиденному окну: verdict уже `3/3 NO_PROMOTION`.
2. Проверить первый scheduled Alpaca post-close/watchdog в понедельник; manual delivery уже доказана, schedule delivery ещё нет.
3. Начать release-manifest/reproducible-checkout план для VPS; не делать blind pull и не удалять server-only файлы до reference audit.
4. Обновлять canonical AI state и project map после каждого frozen verdict/deploy ACK.
5. Владельцу повторить реальный password+TOTP login после JWT-ротации; при `Unauthorized` выполнить локальный password reset, не отправляя пароль в чат.

### Следующие 1–3 рабочие сессии

1. Materialize и hash-pin `13` immutable 720d M5 snapshots для уже замороженного pump-exhaustion short prereg; затем повторить только preflight, не performance, пока data gate не PASS.
2. Восстановить Alpaca intraday v1 ledger из broker fills и провести exact monthly-vs-daily-vs-adaptive replay с одинаковой exit model.
3. Получить и hash-pin fresh FX M5, historical macro-news и OANDA spread/commission/financing calibration; только после этого разрешить V3 performance runner.
4. Реализовать первый vertical slice из `ARCHITECTURE_PARITY_AND_MONEY_PATH_2026_07_11.md`: Market/Level/Decision snapshots + side-specific ID + Operator Truth receipt.

### 3–7 дней после снятия data/parity blockers

1. Реализовать frozen performance evaluator для pump-exhaustion successor только после data-freeze commit: next-open gaps, base/stress costs, timestamp occupancy, folds/embargo/holdout/LOSO и zero-duplicate event receipts.
2. Реализовать long successor с тем же persisted event protocol.
3. Запустить замороженный FX V3 performance gate только если preflight сменится с `DATA_DIAGNOSTICS_ONLY` на strict PASS.

### 1–2 недели

- Возможен только risk-zero shadow у кандидата, прошедшего stress PF `>=1.20`, `N>=40`, `3/4` positive folds, breadth/LOSO/holdout и concentration `<35%`.
- Если PASS нет, фиксируется новый binding NO_GO/repair — дата не превращает FAIL в canary.
- Реалистичный engineering milestone этого окна — один canonical snapshot/receipt path для выбранного crypto challenger и один exact Alpaca replay; не обещание прибыли.

### 2–4 недели

- Risk-zero shadow возможен только у стороны, прошедшей frozen research, live/backtest class parity, closed-bar execution replay и data freshness checks.
- FX demo не начинается, пока отсутствуют historical news и broker cost calibration; после data PASS ему всё равно нужны независимые folds/holdout.

### 6–12 недель и далее

- Tiny-money второй crypto или FX sleeve возможен только после `30` clean shadow/demo closes. Даже при немедленном research PASS meaningful clean sample обычно требует `6–12` недель; при низкой частоте — дольше. Это gate, не обещанная дата.
- Цель периода — один контролируемый money sleeve и два независимых healthy shadows, а не три поспешно включённых money sleeves.

### Доход

Стабильный семейный доход по календарю обещать нельзя. Даже `20%` годовых на `$500` — всего `$100` в год до налогов/издержек. Для дохода нужны одновременно доказанный edge, достаточный капитал и независимость рукавов. Реалистичный ближайший milestone — перестать терять из-за parity/операционных ошибок и доказать два независимых edge. Решение о регулярных выводах принимается только после нескольких месяцев clean live history и portfolio drawdown evidence.

## Протокол продолжения между чатами

Каждый новый чат обязан:

1. прочитать этот файл и `PROJECT_CANONICAL_INDEX_2026_07_10.json`;
2. прочитать `ARCHITECTURE_PARITY_AND_MONEY_PATH_2026_07_11.md` и не подменять target architecture перечнем существующих модулей;
3. проверить direct Git/VPS/broker freshness, не доверять старому snapshot;
4. продолжить первый незавершённый `next_action`, а не повторять общий аудит;
5. в конце обновить machine index, этот roadmap при изменении решения и append-only ledger;
6. явно записать: что pushed, что deployed, что live behavior изменилось, что осталось local-only.

Главный принцип: исследовать широко, продвигать узко, считать правдой только воспроизводимое и свежее.
