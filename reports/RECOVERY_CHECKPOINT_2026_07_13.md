# Recovery checkpoint — 2026-07-13

Это human-reviewed точка продолжения. При конфликте приоритет: direct broker -> fresh heartbeat/effective config -> targeted release receipt -> immutable/preregistered research -> summary -> AI interpretation.

## Итог на сейчас

- Live не сломан и не требует слепого restart: 2026-07-13 09:04 UTC `bybot.service` и web были active, heartbeat свежий, Bybit positions `0`, regime `bear_chop`, failed units `0`.
- Единственный money crypto sleeve остаётся `ATT1 short-only`, risk multiplier `0.10`. Edge не доказан, risk/frequency не повышать.
- Ночная ADA-сделка была прибыльной по направлению и корректно прошла partial TP -> breakeven/trailing exit. Но бот записал только последнюю Bybit close row и занизил итог сделки. Root cause исправлен и полностью протестирован в Git; existing ADA history ещё нужно broker-reconcile.
- Alpaca не требует restart core bot. Она остаётся SAFE-HOLD; scheduled weekday Telegram report впервые должен отработать 13 июля в 22:10 UTC, watchdog — 23:00 UTC.
- Pump-exhaustion data gate закрыт, runner и authorization были committed до outcome, строгий 720d performance завершён `NO_PROMOTION`: stress `N=39`, PF `1.234`, return `+1.228%`, conservative DD `3.015%`; holdout `N=6`. Не пройдены только frozen minimum-sample gates, но ослаблять их после просмотра нельзя.
- Следующий независимый crypto-long больше не существует только на уровне идеи: phase-1 теперь hash-pin фиксирует horizontal `LevelSnapshot v1`, closed M5 -> M15/H1/H4, причинный long-only MTF, exact next-open execution, authenticated bridge и атомарный single-writer state/outbox. Phase-1 integrity PASS, но performance и live намеренно заблокированы девятью явными prerequisite-блокерами.
- FX M5 данные уже есть почти за два года. Level respect теперь fail-closed, H1 явно закреплён, news/cost schemas усилены. Jul11 contract остаётся историческим и останавливается до source gate; для первых V3 figures нужен новый versioned prereg после внешних inputs.
- Никакой второй crypto sleeve, FX/CFD demo/live money или Alpaca scale в этой сессии не включались.

## Git versus VPS truth

| Изменение | Исследовано/тесты | Commit | Origin | VPS live |
|---|---|---|---|---|
| aggregate Bybit partial closes into one logical trade PnL | 1038 full regression PASS; 7-day API boundary focused PASS | `3f6278b` + `12a9abd` | pushed | **не развёрнуто**; targeted manifest готов |
| immutable pump snapshots 13/13 + provenance manifest | 18 focused + full regression PASS | `693ffa3` | pushed | research-only, deploy не требуется |
| strict pump runner -> hash-bound authorization -> immutable verdict | 55 pump tests; artifact manifest 11/11; full suite 1070 PASS | `c282ff6`, `55d00cc`, `a8d8bb8` | pushed | research-only; `NO_PROMOTION` |
| causal levels + event-expansion long mechanics + closed-bar aggregation | 18 new mechanics tests; 25 aggregation tests; full suite 1088 PASS before phase-0 prereg | `a98b640`, `f07dd01` | pushed | research-only; no live wiring |
| event-expansion long phase-0 prereg/preflight | 57 focused PASS; identity/data hashes PASS; nine blockers retained | `526492a` | pushed | `PERFORMANCE_FORBIDDEN`, `LIVE_FORBIDDEN` |
| causal level evidence + exact event-long execution | approach/reaction/unbroken evidence, next-open/gap/stop-first/partial costs/funding contract | `7249b45`, `dd427c4` | pushed | research-only; no performance |
| MTF orchestrator + atomic state/outbox + execution bridge | downtime replay freezes at first plan; durable ACK barrier; end-to-end exact-open conformance | `6dfd263`, `d7608d8`, `1f95e85`, `72c273d` | pushed | research-only; no registry/live wiring |
| event-expansion long phase-1 freeze | `97` exact related tests; integrity PASS; nine runner/data blockers | `e05f7b3` | pushed | `PERFORMANCE_FORBIDDEN`, `LIVE_FORBIDDEN` |
| historical phase-0 regression semantics | old immutable hashes now expected to reject strengthened level code; phase-1 is current authority | `7e93150` | pushed | no live effect |
| FX V3 fail-closed level/news/cost contract | 82 combined focused/FX/Alpaca tests PASS | `864b054` | pushed | research-only; no performance |
| exact Alpaca four-arm parity prereg + blocked evidence | 7 focused; sources/fingerprint PASS | `bb377bc`, `997f205` | pushed | no live change; outcome access blocked |
| прежний ATT1 RSI45/AI/Web/Alpaca reporting package | verified ранее | ancestors HEAD | pushed | targeted-deployed ранее |

Implementation local/origin HEAD до текущего canonical update: `7e93150`. VPS checkout по-прежнему намеренно старый/dirty (`f7ed011` на последней проверке); blind pull/reset/cleanup запрещены. Внешний server tool достиг usage quota во время этой сессии, поэтому P0 accounting нельзя честно назвать live. Release receipt: `reports/releases/targeted_bybit_partial_pnl_12a9abd_20260713.json`.

## Что произошло с ночной crypto сделкой

Свежий runtime evidence показывает один логический `ADAUSDT Sell` ATT1, а не обязательно две независимые позиции:

- signal slope примерно `-1.883%/day`, RSI `56.9`;
- entry примерно `0.1636`, initial qty `249`;
- partial close примерно `136.95` около `0.1614`;
- remaining qty примерно `113` закрыта trailing около `0.1622`;
- старый finalizer записал только residual closedPnl `+0.13795153`.

Bybit API возвращает `closedSize/closedPnl/openFee/closeFee` на уровне close order. Поэтому partial TP и final trail являются несколькими rows одной позиции. Новый aggregator фильтрует symbol, closing side, entry lifecycle/price, deduplicates order IDs и ждёт, пока сумма `closedSize` достигнет initial qty; только затем единый PnL идёт в trade event, DB, breaker, edge monitor и AI. Отдельный follow-up делит запросы на разрешённые Bybit окна не более семи суток: ATT1 time stop равен семи суткам, а старые timestamp buffers могли превысить API limit. Exact net ADA PnL будет восстановлен из broker rows после возврата server access; грубую оценку нельзя подменять broker truth.

## ATT1: логика и причина «нелогичных входов»

Механика целостна: confirmed swing pivots, closed H1 decision, touch/rejection candle, RSI, next execution, broker stop, partial targets, BE/trail/time stop, breaker/expiry. Последняя прибыльная ADA показывает, что trade-management path способен работать.

Но геометрия входа остаётся слабым местом:

- live `min_pivots=2`; две точки всегда дают `R²=1`, поэтому `min_r2=0.55` ничего не доказывает для таких линий;
- нет обязательного доказательства, что projected line не была сломана между pivots и текущим touch;
- нет отдельного first-touch/number-of-respects gate;
- short допускает слегка rising resistance;
- touch условие не ограничивает слишком глубокий overshoot над линией;
- regime/BTC context не является доказанным обязательным gate.

Поэтому вход может быть code-valid, но визуально/экономически слабым — именно это внутренний AI называл нелогичным. Старое объяснение AI про `missing_candles` было слишком сильным: это post-hoc forensic cache completeness, а не доказательство, что live bot не видел свечи и не управлял позицией.

Текущий ATT1 не переписывать в live после одной удачной сделки. Замороженный challenger должен проверять только заранее выбранные causal guards: минимум три подтверждённых respects либо отдельный two-pivot class, unbroken line, bounded overshoot, first retest и measured costs. `pure_trail` отвергнут: строгий 4x90 test дал только 2/4 positive folds, 68 trades, net `+1.43`, PF `1.165`; base дал 4/4, 379 trades, net `+18.78`, PF `1.277`.

Отдельный ATT1 canary expiry — `2026-07-20`; это не API-key expiry. Bybit key monitor на 10 июля показывал expiry `2026-08-12` (около 30 дней осталось на 13 июля). План: explicit canary review до 20 июля и безопасная ротация API key до начала августа, без передачи secrets в чат.

## Следующие crypto sleeves

1. `pump_exhaustion_unwind_short_v1` — честно завершён `NO_PROMOTION`, а не готовый второй рукав. Stress: 39 trades, PF `1.234`, `+2.922R`, `+1.228%` при frozen sizing, conservative DD `3.015%`; 3/4 positive folds. Holdout позитивен, но только 6 trades против gate 10. За 25 calendar months было 16 active, 9 нулевых и 7 красных active months. ONDO дал 93.4% итогового net; без него LOSO PF `1.018` и return `-0.127%`, что добавляет robustness-риск. Подробно: `reports/PUMP_EXHAUSTION_STRICT_VERDICT_2026_07_13.md`.
2. `event_expansion_retest_long_v1` — следующий физически отдельный long-only successor, а не механическая инверсия short sleeve. Phase-1 уже соединяет immutable horizontal H1/H4 level, H1 expansion, строго более поздние M15 hold/first-retest/higher-low/BOS, exact next M5 open, frozen stop, 1R/2R, costs/funding policy, authenticated bridge и restart-safe outbox. Критический downtime case теперь останавливает replay ровно на первом плане и не пропускает next-open до durable ACK. Статус всё равно `BLOCKED_RESEARCH_RUNNER_DATA`: нет performance/receipt runner, доказательства полноты funding, uniform dev13 manifest, external8 data/metadata/liquidity/funding и ATT1 additivity reference. Поэтому цифр и live-разрешения пока нет. Текущий authority: `reports/EVENT_EXPANSION_RETEST_LONG_V1_PHASE1_FREEZE_2026_07_13.md`.
3. Horizontal range rejection — отдельные long-only и short-only sleeves на общем Level Snapshot. Это правильный наследник «пилы/отскоков»; старые ARS1/ASB2/ARF формы не включать, потому что свежие gates отрицательны.

Elder использовать как side-specific context/filter, а не самостоятельный двигатель. Breakdown — только bear-only и ниже по приоритету. FVG/imbalances пока не production sleeve: deterministic context можно тестировать только отдельной ablation после общего уровня/события, а не добавлять как красивую эвристику.

Сегодня нет второго честного performance-run из уже frozen artifacts. Это не простой вычислительной мощности: phase-1 специально запрещает outcomes до runner/data freeze. `pump_fade_simple_meme` — 486-combo autoresearch на selected microcaps, не prereg/nested OOS; ARS1/ASB2/InPlay/level-memory уже провалены на просмотренных окнах. ARF2 unified-level replay уже оживлял частоту, но дал только PF `0.588`, поэтому одного wiring provider недостаточно. После phase-2 runner/data freeze event-long получит первый допустимый performance gate; затем та же рама пойдёт в отдельные horizontal range rejection long и short. Sloped levels остаются отдельным будущим versioned contract, а не тихим расширением текущего v1.

Текущий order-book density collector хранит lossy 30-second wall snapshots без sequence IDs, exchange timestamps, full deltas и public trades. Это context telemetry, не replayable imbalance edge. Для честного InPlay/L2 исследования нужен новый reconstructible publicTrade + L2 collector и примерно 60–90 дней tape.

Старый `pump_fade_simple` baseline (`PF 1.883`, `+7.81%` за 240d, `DD 3.77%`, `N=19`) был на выбранных microcaps и не является строгим OOS кандидатом. Его нельзя выдавать за ожидаемую годовую доходность нового sleeve. У строгого successor теперь есть цифры, но не promotion: stress partial-year returns `-1.491%` (Jul-Dec 2024), `+1.835%` (2025), `+0.909%` (Jan-Jul 2026); это не CAGR/forecast.

## Alpaca

Ручной restart `bybot.service` не нужен: monthly manager запускается cron как one-shot и читает код/конфиг на следующем invocation. Если scheduled report не придёт после 22:10/23:00 UTC, проверять нужно cron receipt/report command, не перезапускать торговое ядро вслепую.

Первая отрицательная неделя главным образом тестировала ошибочную daily rotation: 7 round trips за 3 торговых дня, 2W/5L, около `-$5.716`, PF около `0.44`, тогда как monthly research ожидала примерно 15 OOS trades/year. Это parity defect, но не доказательство будущей прибыли.

Самый защитимый exact top4 replay: 2024-05..2026-04, `N=33`, `PF=6.7439`, compounded `+50.7502%`, max monthly DD `-3.856%`, 8 positive/2 negative active months; только 10 active months из 24. Это selected historical replay без явных fees/slippage и daily DD, не forecast. Live approximation exits (fixed 5% stop + software +3.5%/+3.5% trail) не равны research BE0.8R+ATR1.5. SAFE-HOLD сохраняется до broker-fill reconstruction и exact parity replay. Подробно: `reports/ALPACA_TRUTH_AND_NEXT_TEST_2026_07_13.md`.

## FX/CFD

Шесть Dukascopy M5 snapshots существуют примерно за 728.4 дня. Повторный preflight: diagnostic `EURUSD, GBPUSD, USDJPY, GBPJPY`; promotion-grade `0`. Старый V2 under base/stress отрицателен для всех шести side-specific sleeves, поэтому переписывать thresholds нельзя.

Ближайшая V3 система — пять физических sleeves:

- failed-break retest short;
- horizontal range rejection long;
- horizontal range rejection short;
- range-edge expansion/retest long;
- range-edge expansion/retest short.

Fail-open level respect закрыт, current H1 semantics явны, news/cost validators требуют measurable currency coverage, unique typed symbol/session rows и confirmed OANDA account type. Старый Jul11 config намеренно не редактировался: он теперь выдаёт actionable blockers и не создаёт output. До outcome остаются новый prereg/source hashes, fresh/resumable bid/ask data и реальные pinned news/cost artifacts. Текущий CFD scope — только XAUUSD; индексные CFD ещё не имеют data/spec. Подробно: `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`.

От владельца нужен не депозит:

1. OANDA v20 `fxTrade Practice` account.
2. Локально сохранённые `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID`, `OANDA_ENV=practice`; secrets не отправлять в чат.
3. Регион/regulatory division, pricing model и желаемые инструменты.
4. Лицензированный источник historical macro calendar с UTC/currency/numeric impact/event.

После inputs первые честные approximate V3 figures — ориентир 2–4 дня; полный пяти-sleeve verdict — около 7 дней; XAU/прочие CFD отдельно 5–10+ дней. Demo только после strict PASS, деньги — после минимум 30 clean demo closes и owner approval.

## Аудит пакета Claude 12 июля

Принято: level parity, exact Alpaca replay, FX data/cost/news gates, pump event-first, отдельные long/short sleeves и запрет promotion по autoresearch/smoke PASS.

Исправлено/отклонено:

- `pure_trail` не сильнее base по строгому evidence;
- old pump grid не true OOS и не может promotion-rerun после просмотра winners;
- FX M5 не отсутствуют полностью;
- `wf_folds`/`oos_selector` оценивают уже созданные trades, но сами не создают train-select-test separation;
- Level Snapshot нужен, но пока не доказан как единственная root cause ARF failure;
- adaptive Alpaca стабилизирует DD, но не доказал income edge.

Jul12 Claude reports остаются advisor input, а не canonical state. Эта точка и её evidence имеют приоритет.

## Реалистичные сроки выхода из кризиса

- Эта recovery-сессия: P0 accounting Git fix, immutable pump verdict, FX/Alpaca fail-closed gates, strengthened `LevelSnapshot v1`, closed-bar aggregation, exact execution, restart-safe MTF/outbox/bridge и event-long phase-1 freeze выполнены. Финальный полный suite: `1191 passed`; phase-1 exact suite: `97 passed`.
- Pump verdict уже получен: слабоположительный, но недостаточно частый `NO_PROMOTION`; live timing от него не начинается.
- 2–4 дня после OANDA/news inputs: первые честные V3 FX figures.
- 1–3 рабочих сессии: event-long phase-2 runner/receipt journal и uniform dev13/funding manifests; только затем первый допустимый performance-run.
- Около 1 недели после необходимых данных: Alpaca frozen parity replay + FX five-sleeve verdict + решение по risk-zero crypto shadow.
- 2–4 недели: возможен первый маленький диверсифицированный canary только если хотя бы два независимых sleeves реально пройдут gates.
- Стабильный семейный доход нельзя обещать сроком: нужен минимум десятки clean shadow/demo/live closes в разных regimes и месяцы наблюдения. Цель этой рамы — перестать терять месяцы на ложные PASS и быстро получать проверяемые `PASS/FAIL`, а не гарантировать прибыль.

## Нельзя без новых ворот/owner approval

- повышать ATT1/Alpaca/live risk;
- включать второй money sleeve по одной удачной сделке или selected backtest;
- автоматически продлевать ATT1 canary 20 июля;
- запускать FX demo/live при `DATA_DIAGNOSTICS_ONLY`;
- чистить dirty VPS или делать blind pull/reset;
- смешивать long/short physical identity;
- выдавать Git push за VPS deploy.

## Следующая исполнимая очередь

1. После восстановления server access адресно deploy P0 partial-PnL package при flat, без risk change; reconcile ADA broker rows.
2. После 22:10/23:00 UTC проверить Alpaca scheduled report/watchdog receipt; затем материализовать девять prereg artifacts, не запускать performance при BLOCKED.
3. Получить owner OANDA/news inputs; создать новый FX V3 prereg с fresh source/artifact hashes и только потом считать PnL.
4. Не повторять уже закрытый phase-1 MTF. Следующий шаг: single-owner phase-2 runner, который durable-пишет bridge/trade receipts до ACK, доказывает funding coverage, использует uniform dev13 window и фиксированные folds/embargo/LOSO/additivity. До нового freeze performance запрещён; затем materialize fixed external8 без замен символов.
5. После первого честного event-long verdict использовать horizontal v1 для отдельных horizontal-range rejection long и short. Sloped levels — отдельный versioned contract; Elder только как ablation/filter.
6. Обновлять AI canonical state/index/ledger после каждого verdict; оператор остаётся observer/proposal-only.
