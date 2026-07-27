# Задание Claude: доказуемая фабрика стратегий, а не новый пакет обещаний

Дата: 2026-07-27

Роль Claude: независимый quant-аудитор и автор research-only артефактов.

Следующий владелец проверки: Codex.

Live authority: отсутствует. Никаких рестартов, ордеров, risk/env-изменений и deploy.

## Цель

Превратить `CLAUDE_FULL_STRATEGY_PACKAGE_2026_07_27.md` в воспроизводимую
очередь экспериментов и каноническую карту будущего портфеля.

Нельзя считать идею рабочей по наличию модуля, красивому single-window PF,
текущему составу символов или агрегату long+short. Каждый кандидат должен
оставить causal trade-ledger, точный data manifest, side split, costs,
train/OOS/holdout и отрицательный контроль.

## Уже установленные факты, которые нельзя переоткрывать

1. Гипотезы `ATT1_MAX_PIVOT_AGE=24` как причины тишины и семикратного
   недосемплирования отменены.
2. ATT1 live short tiny-canary не менять и не останавливать.
3. `portfolio_equity_guard` и полный ATT1 parity/source hash уже исправлены
   Codex; повторная реализация не нужна.
4. Funding-arbitrage уже имеет автоматический N=20/N=30 gate и получает только
   малую долю исследовательского бюджета.
5. `PF 2.52` для `retest_quality + level_entry` — только smoke:
   22 сделки на ADA/DOGE/SUI. На LINK/SOL/ADA было `PF 0.908`; сохранённая
   OOS-оценка доходности порядка 0.4–1.3% годовых. Нельзя называть 2.52
   общим доказанным улучшением.
6. XSEC V4 не является live-ready: текущий universe survivorship-biased,
   Sharpe в validator считается через `sqrt(n)`, threshold post-hoc,
   funding/slippage отсутствуют, split не лечит PIT-дефект.
7. Текущие BTC/ETH/SOL/BNB/XRP/LINK также нельзя объявлять
   survivorship-free только потому, что сейчас это майоры.
8. Funding time нельзя жёстко считать `00/08/16 UTC` для всех символов:
   использовать PIT `fundingInterval`/settlement timestamps каждого инструмента.

## WIP-правило

Одновременно выполняется только один пакет ниже. Следующий начинается после
закрытия предыдущего receipt с `PASS`, `FAIL` или `BLOCKED_DATA`.

## Пакет A — верификация карты стратегий

Создать:

- `reports/research/strategy_factory_20260727/canonical_strategy_matrix.csv`
- `reports/research/strategy_factory_20260727/module_wiring_matrix.csv`
- `reports/research/strategy_factory_20260727/claim_audit.json`
- `reports/research/strategy_factory_20260727/VERDICT.md`

### Поля canonical strategy matrix

- `family_id`
- `human_name`
- `side` (`long`/`short`, физически раздельно)
- `geometry` (`horizontal`/`sloped`/`none`/`liquidity_cluster`)
- `regime`
- `signal_tf`
- `execution_style`
- `dynamic_universe_required`
- `data_requirements`
- `existing_strategy_modules`
- `live_wired`
- `research_status`
- `last_authoritative_run`
- `trades`
- `net_r`
- `profit_factor`
- `annualized_after_cost_pct`
- `red_months`
- `oos_folds_positive`
- `known_blockers`

Семейства минимум:

1. level rejection/bounce;
2. break-and-retest;
3. impulse breakout;
4. pump/dump exhaustion;
5. liquidity sweep/reclaim;
6. liquidity-density/large-order reaction;
7. medium-term trend/pullback;
8. cross-sectional relative strength;
9. token-unlock event;
10. funding/OI positioning event.

Elder записать как regime/confluence filter, а не самостоятельный money-sleeve,
пока отдельный OOS не докажет обратное.

### Поля module wiring matrix

- `module`
- `imported_by_live_runner`
- `called_by_live_entry_path`
- `called_by_live_exit_path`
- `research_only_callers`
- `feature_flag`
- `default_effective_state`
- `runtime_receipt_available`

Не считать импорт или наличие файла доказательством рабочего live-пути.

### Claim audit

Перепроверить минимум:

- ATT1 r005 aggregate и side split;
- ATT1 r001 strict short OOS;
- level-entry smoke и сохранённый OOS;
- XSEC V4 headline;
- количество реально подключённых learning/control modules;
- текущий midterm universe и его authoritative verdict.

Каждый claim получает:

- `VERIFIED`;
- `PARTIAL`;
- `CONTRADICTED`;
- `NOT_REPRODUCIBLE`.

## Пакет B — ATT1 seasonality и owner-label pack

### B1. Seasonality

Исходный ledger и его SHA фиксируются до расчёта.

Проверить net R после costs по:

- часу UTC;
- funding-relative minute bucket;
- Asia/Europe/US session;
- weekday;
- regime;
- side.

Требования:

- не подбирать лучшие часы и затем считать их OOS;
- первые 60% времени — discovery, следующие 20% — validation,
  последние 20% — sealed holdout;
- корректировать multiple testing;
- сравнить `NO_ENTRY_HOURS_UTC` с неизменённым baseline;
- сохранить все bins, включая отрицательные;
- результат только `filter_candidate`, не live env.

Артефакты:

- immutable input manifest;
- bin table;
- discovery/validation/holdout trade ledgers;
- exact command;
- `PASS/FAIL` verdict.

### B2. Owner-label pack

Подготовить 30 графиков без раскрытия результата сделки владельцу:

- 8 winner;
- 8 loser;
- 7 no-signal;
- 7 false-break/sweep.

Порядок перемешать и ослепить. На каждом графике показать только доступные
в момент решения данные, уровни, объём и timestamp. Ответ владельца:
`взял бы / не взял бы / не уверен` плюс короткий reason tag.

Не обучать модель до получения меток. Сначала заранее описать, как именно
метки будут проверяться на отдельном holdout.

## Пакет C — token unlock short event study

Это исследование, не готовая стратегия.

### Universe

- все Bybit perpetual symbols, существовавшие на дату события;
- PIT launch/delist/shortability;
- минимальная PIT-ликвидность;
- исключить события, где short-инструмента тогда не существовало;
- не использовать сегодняшний список выживших как исторический universe.

### Event data

Для каждого unlock:

- источник и timestamp публикации;
- первоначально известная дата;
- изменения даты;
- cliff/linear;
- unlocked USD и проценты от circulating supply;
- recipient category, если достоверна;
- время, когда эти данные стали известны рынку.

Запрещено использовать post-event исправленные календарные данные без
`known_at`.

### Designs

- pre-event short;
- event-window short;
- post-event drift;
- BTC-beta-neutral and equal-weight market-neutral controls;
- matched non-event control;
- placebo dates;
- cliff vs linear;
- size buckets preregistered до просмотра результата.

Учитывать taker/maker costs, slippage, funding, borrow/short availability,
delisting, gaps и liquidation-safe stop.

Минимум 50 событий для первого вывода. Если их нет — `BLOCKED_DATA`, а не
ослабление gate.

## Пакет D — funding settlement + OI positioning

Это направленный event/filter research, не возврат funding-arbitrage.

### Data contract

- фактический `fundingInterval` и settlement timestamp для каждого symbol;
- funding history;
- mark/index/basis;
- open interest в сопоставимых notional units;
- volume, spread и top-of-book;
- PIT instrument metadata.

### Проверяемые гипотезы

1. continuation перед settlement;
2. reversal после settlement;
3. interaction: extreme funding × OI growth × price stall;
4. interaction: extreme funding × order-flow exhaustion;
5. funding/OI только как filter для pump exhaustion и sweep/reclaim.

Обязательны event-time plots, non-overlapping samples, placebo timestamps,
multiple-testing correction и after-cost ledger. Нельзя предполагать, что
экстремальный funding сам по себе означает reversal.

## Пакет E — единый level contract, без переписывания 97 файлов

Подготовить design-only спецификацию `LevelSnapshotV2`:

- `level_id`;
- `geometry`;
- `side`;
- `known_at`;
- `source_tf`;
- `price_now`;
- `slope`;
- `r2`;
- `touch_count`;
- `last_touch_at`;
- `broken_at`;
- `first_retest_at`;
- `freshness`;
- `strength`;
- `invalidation`;
- `source_hash`.

Шесть price-action логик могут потреблять общий контракт, но остаются
раздельными sleeves. Нельзя:

- незаметно добавить horizontal signals в живой ATT1;
- считать horizontal ATT1 тем же validated sleeve;
- смешивать long/short verdict;
- удалять старые стратегии до parity replay;
- выбирать геометрию по результату будущей сделки.

Horizontal ATT1-like logic оформляется отдельным challenger с новым strategy id.

## Пакет F — midterm universe

Baseline: BTC/ETH отдельно.

Challenger: PIT top-liquid majors, где SOL/BNB/XRP/LINK являются кандидатами,
а не заранее гарантированными членами.

Нужны:

- historical eligibility by date;
- per-symbol and leave-one-symbol-out results;
- long/short split;
- bull/bear/chop split;
- costs and funding;
- portfolio additivity against ATT1;
- max one medium-term position under the global three-slot policy.

Нельзя переносить параметры ATT1 H1 на H4/D1 без отдельной revalidation.

## Общие promotion gates

Ни один пакет не разрешает деньги.

Минимально:

- exact input/data SHA;
- causal `known_at`;
- next-open or measured limit-fill execution;
- fees, slippage, funding;
- train/OOS/sealed holdout;
- side split;
- PIT universe;
- no symbol contributes more than 35% of positive net R;
- no single regime explains more than 60% of positive net R;
- annualized return and red months reported alongside PF;
- portfolio replay with max 3 positions;
- independent negative control;
- no post-hoc threshold marked as preregistered.

Результат каждого пакета: `PASS_NEXT_RESEARCH_GATE`, `FAIL`, или
`BLOCKED_DATA`. Слово `LIVE_READY` запрещено.

## Разрешённые изменения

- research-only scripts;
- tests;
- reports under `reports/research/strategy_factory_20260727/`;
- immutable manifests and ledgers.

## Запрещённые изменения

- `smart_pump_reversal_bot.py`;
- live env/config;
- service/screen/cron;
- broker/exchange private API;
- risk multipliers;
- order execution;
- strategy deletion/cleanup;
- deploy/restart/push без отдельного owner/Codex review.

## Handoff Codex

Claude отдаёт:

1. список изменённых файлов;
2. commit SHA либо точный dirty diff manifest;
3. команды воспроизведения;
4. test receipt;
5. data manifest;
6. все отрицательные результаты;
7. один краткий verdict на пакет.

Codex независимо:

1. проверяет причинность и отсутствие утечки;
2. пересчитывает headline numbers;
3. проверяет код и тесты;
4. решает, что сохранять;
5. только после отдельного promotion receipt проектирует shadow/canary deploy.
