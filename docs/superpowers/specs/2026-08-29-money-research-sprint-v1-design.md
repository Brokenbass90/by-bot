# Money Research Sprint V1 — дизайн

Дата: 2026-08-29

Статус: утверждённое направление, ожидает проверки владельцем после записи
Authority: research-only; без live, broker orders, изменения риска, promotion
или money authority

## 1. Цель и границы

Цель спринта — получить за несколько инженерных дней три независимых и
фальсифицируемых ответа:

1. сохраняется ли XSEC V4 после устранения survivorship bias и добавления
   исполнимых издержек;
2. существует ли отдельная bull-continuation long-нога для крипты;
3. воспроизводится ли положительная XAUUSD session-breakout/retest зацепка на
   более надёжном источнике данных.

Спринт начинается с восстановления единой точки истины исследовательской
станции. Сейчас активные zero-risk процессы работают из
`bybit-bot-clean-v28`, а каноническое дерево и ветка —
`bybit-bot-recovery-20260824` / `codex/recovery-20260824`.

Спринт не:

- повторяет consumed ATT1/SBR1 reserved OOS;
- подбирает ATT1/SBR1 по уже раскрытому окну;
- включает или увеличивает live-риск;
- снимает Alpaca SAFE_HOLD;
- объединяет уровни, order blocks, imbalances и индикаторы в один
  неинтерпретируемый сигнал;
- объявляет исторический PASS доказательством будущей доходности.

## 2. Архитектура спринта

```text
canonical research truth
  -> immutable experiment contract
  -> causal data/feature integrity
  -> bounded development search
  -> frozen chronological validation
  -> independent audit
  -> zero-risk shadow with control
  -> later, separate money-release gate
```

Каждый рукав получает собственные:

- `experiment_id`, preregistration и config fingerprint;
- физически ограниченный input manifest и source SHA;
- decision, intended-fill, exit и cost ledgers;
- base/stress экономику;
- causal/control/concentration checks;
- terminal verdict `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW`, `FAIL_RESEARCH` или
  `BLOCKED_DATA_OR_PARITY`.

Все исторические окна этого спринта считаются ранее затронутыми проектом.
Поэтому даже положительная историческая диагностика не является новым OOS и
не даёт promotion или money authority. Она может только разрешить запуск
заранее зарегистрированной zero-risk shadow. Доказательство для последующего
promotion начинается после preregistration на новых проспективных данных и
потребует отдельного owner-approved gate.

Ни один общий orchestrator или allocator не исправляет отрицательную стратегию.
Сначала рукав должен пройти собственный контракт. Только после этого отдельно
проверяется портфельная совместимость.

### 2.1. Общий matched-control контракт

Там, где ниже требуется matched/random control, используется одна
детерминированная схема:

- 20 draws на каждый decision/episode/rebalance;
- seed: `SHA256(config_fingerprint || event_id || draw_index)`;
- тот же symbol или тот же causal eligible universe, physical side, UTC month,
  causal regime, volatility bucket, holding horizon и gross exposure;
- для time-shift event controls исходный event path и любой пересекающийся
  forward path исключаются; XSEC сохраняет тот же rebalance path и
  рандомизирует только basket membership;
- одинаковые fill/cost/funding/exit правила применяются к стратегии и control;
- недоступный будущий path получает `pending`, а не silently drops;
- draw index формирует один полный control ledger, поэтому итоговая
  distribution содержит 20 сопоставимых aggregate net outcomes; указанное в
  gates стандартное отклонение — sample standard deviation именно этих 20
  aggregate outcomes.

Двадцать matched ledgers используются для понятной оценки величины эффекта и
разброса, но не как единственная проверка значимости. Для каждого семейства
дополнительно строятся 999 детерминированных blocked permutations с теми же
market clusters и costs. Family-wise p-value считается selection-aware и
должен быть `<= 0.05`; seed и полный permutation ledger публикуются.

До scoring создаётся общий machine-readable
`configs/research/money_research_sprint_v1_control_contract.json`. Он пинует
experiment/config/input hashes, eligible units, exclusions и алгоритмы ниже:

- hash RNG не зависит от Python/random: число берётся как unsigned integer из
  первых 16 hex characters SHA-256 и, где нужен индекс, берётся modulo размера
  заранее отсортированного eligible set;
- permutation seed:
  `SHA256("perm_v1" || family_id || config_fingerprint || permutation_index || block_id)`;
- event-family null: внутри каждого заранее записанного market cluster одним
  hash bit одновременно меняются местами paired strategy/control labels для
  всех arms, сохраняя cross-arm и cross-symbol dependence;
- XSEC null не использует sign flip. Для каждого permutation и rebalance
  causal factor-score values каждого arm перераспределяются только внутри
  заранее определённых causal maturity/liquidity/volatility strata по общему
  hash-order symbol mapping; один mapping применяется ко всем 36 arms, после
  чего basket, 20 matched controls, next-open, costs и funding пересчитываются
  с нуля. Outcomes никогда не участвуют в mapping;
- one-sided p-value всегда равен
  `(1 + count(permuted_stat >= observed_stat)) / 1000`;
- maxT — максимум studentized mean excess по всем проверяемым arms в каждой
  permutation; standard error считается по заранее заданным clusters, не по
  отдельным строкам сделок.

Все 95% uncertainty intervals используют ровно 9999 cluster bootstrap
replicates с replacement. Для replicate `b` и draw `j` cluster index равен
`uint64(SHA256("bootstrap_v1" || experiment_id || config_fingerprint || b || j)[0:16]) mod N_clusters`.
Interval — percentile `[2.5%,97.5%]` распределения заранее указанного primary
effect statistic. Project-specific cluster unit фиксируется ниже; individual
trades/rows никогда не bootstrap-ятся как независимые.

Любая пустая eligible set, несовпавший hash, невозможный draw или изменение
cluster membership после появления outcome блокирует run. Машинный контракт,
20 matched ledgers и 999 permutation ledgers входят в independent audit.

Для XSEC draw заменяет ranked basket случайной eligible корзиной с теми же
long/short counts и gross weights. Для single-asset Bull/XAU draw заменяет
момент decision причинно доступным matched timestamp; геометрия выхода и риск
не меняются.

## 3. Подпроект A: каноническая исследовательская станция

### 3.1. Текущее расхождение

Семь detached screen-сессий существуют, а минимум XSEC, funding, Inplay и
Alpaca adaptive пишут свежие zero-risk артефакты в старое дерево. В
каноническом дереве `runtime/local_research_station/status.json` устарел и не
видит эти evidence paths.

### 3.2. Миграционный контракт

Миграция выполняется без удаления старых данных:

1. Снять receipt старой эпохи: screen name/PID/cwd, strategy/config identity,
   доступные code/config/state/output SHA, последние counters и timestamps.
2. Если command/config identity нельзя восстановить, пометить процесс
   `NOT_CONFIRMED` и не останавливать его автоматически.
3. Запустить каноническую копию только с `research_only=true`, новым уникальным
   evidence epoch и отдельным runtime path в каноническом дереве.
4. Получить минимум один свежий heartbeat/evidence receipt и проверить точные
   поля manifest: `authority=research_only_no_live_or_promotion`,
   `promotion_authority=false`, `network_authority=false`,
   `private_api_authority=false`, `order_authority=false` и
   `live_write_authority=false`. Отсутствующее либо отличающееся поле — FAIL.
5. Выполнить сравнение по типу процесса:
   - deterministic decision loop: одинаковые source timestamp/config/input
     дают точное совпадение decision ID и всех экономических полей;
   - market-snapshot loop: сравнивается общий закрытый source timestamp; если
     рынок уже сдвинулся и общий snapshot недоступен, старый процесс остаётся
     запущенным со статусом `NOT_CONFIRMED`;
   - collector/supervisor: на одном immutable filesystem snapshot должны
     совпасть source identities, counts и hashes; freshness timestamps могут
     отличаться, но не содержимое snapshot.
6. Только после PASS штатно остановить старую zero-risk screen-сессию. Старые
   runtime-файлы остаются read-only историческим evidence; удаления нет.

Station V3 остаётся общим immutable runner через
`research_lab/station_v3.py`. Completion доказывается только
`completion.json`, связанной с manifest и ledger tail; текст лога не считается
состоянием.

### 3.3. Gate

Канонизация проходит, только если:

- свежий station status перечисляет фактические evidence paths;
- source code/config/input hashes присутствуют;
- один и тот же run ID не получает две несовместимые идентичности;
- нет credential, network, order, risk или promotion authority;
- старые и новые эпохи разделены и не смешиваются в одной статистике.

## 4. Подпроект B: XSEC PIT V5

### 4.1. Гипотеза

Широкая кросс-секционная относительная сила может давать независимый от
ATT1/SBR1 результат, но старый V4 измерен на survivor-only universe. Сильная
старая семья (`36/36` positive при 15 bps) конфликтует с более свежим causal
V1 (`stress 30 bps = -5.82%`) и отрицательной предыдущей shadow-фазой. Поэтому
V5 — быстрый falsification/rebuild, а не почти готовая денежная стратегия.

### 4.2. Замороженная семья

- Повторяется ровно опубликованная V4 36-cell family из
  `configs/preregistered/xsec_v4_family_landscape_20260728.json`.
- Новые параметры после просмотра PIT-результатов не добавляются.
- Family-level verdict оценивает устойчивость всей заранее известной
  окрестности; из V5 нельзя выбрать нового чемпиона для денег.
- Published champion фиксирован как trial 8:
  `lookbacks=[7,14,21,30,45]`, `rebalance_days=3`, `basket_k=5`,
  `target_annual_vol=0.15`.
- Centre/reference arm фиксирован до PIT scoring:
  `lookbacks=[7,14,30]`, `rebalance_days=3`, `basket_k=3`,
  `target_annual_vol=0.10`. Оба показываются отдельно, но не дают обход
  family-level gate.

### 4.3. PIT membership и исполнение

Universe для каждого rebalance timestamp строится только из известной к тому
моменту истории:

- listing/launch timestamp уже наступил;
- накоплено минимум 390 закрытых daily bars — ровно опубликованное правило V4;
- ex-post liquidity winner filter не добавляется: причинный daily turnover
  сохраняется для executable sizing/cost audit, а отсутствие этой истории
  блокирует конкретный rebalance с reason code;
- delisted/исчезнувшие инструменты остаются в исторических периодах, где были
  доступны;
- отсутствие цены, funding или instrument metadata имеет явный reason code и
  не превращается в нулевую доходность;
- веса формируются на закрытых данных, исполнение — на следующей разрешённой
  цене;
- funding, turnover, taker/maker assumption, spread/slippage и executable
  minimum/step constraints входят в ledger.

Источники — физически bounded public archives под `research_lab/data/`.
Историческая оценка классифицируется diagnostic, а не pristine untouched OOS,
потому что пересекающиеся периоды уже изучались.

Перед любым scoring создаются immutable membership и liquidity manifests.
Одна строка membership содержит как минимум:

- `instrument_id`, `symbol`, `listed_at_utc`, `delisted_at_utc|null`;
- `source_as_of_utc`, `source_uri_or_record_id`, `status`, `contract_type`,
  `quote`;
- `min_qty`, `qty_step`, `tick_size` и reason code для любого отсутствия.

Одна строка daily liquidity содержит timestamp, causal value, unit и source,
известные до rebalance. As-of join audit доказывает, что decision не видит
более позднюю строку. Если источник не позволяет восстановить delisted
universe, V5 заканчивается `BLOCKED_DATA_OR_PARITY`, а не survivor-only
приближением.

### 4.4. Controls и verdict

Обязательные сравнения:

- cash и equal-weight eligible universe;
- time-matched random long/short baskets с той же gross exposure;
- base 15 bps и stress 30 bps плюс фактический funding ledger;
- chronological folds/halves, regime splits, LOSO и top-5%-trim;
- HHI и доля крупнейшего положительного symbol/episode;
- target-weight versus executable-order parity.

Для каждого rebalance и draw causal eligible symbols сортируются по
`SHA256(config_fingerprint || rebalance_ts || draw_index || symbol)`; первые
`basket_k` получают long, следующие `basket_k` short с теми же gross weights,
volatility targeting и executable constraints, что strategy arm. Ranked
strategy constituents исключаются только из собственного event path, но не
из universe. Недостаточный eligible count, funding path или next-open path
блокирует весь paired rebalance; draw не заменяется после просмотра outcome.

Для 36-cell family primary statistic — median stress excess всех 36 arms над
matched control. Published champion и reference проверяются maxT-поправкой
внутри той же семьи; выбирать нового победителя по V5 запрещено.

XSEC paired unit — один closed rebalance-to-rebalance portfolio return. Эти
returns агрегируются в UTC calendar-month clusters. Для каждого arm monthly
stress excess — сумма strategy net log returns минус среднее из 20 matched
control net log-return ledgers за тот же месяц. Arm annualized excess равен
`100 * (exp(12 * mean(monthly_excess)) - 1)` percentage points; family statistic
— median этих 36 arm-level annualized excess. Bootstrap uncertainty использует
общие 9999 cluster resamples UTC months с replacement, а внутри каждого
sampled month дополнительно resamples 20 control-ledger indices с replacement
и пересчитывает их mean; так uncertainty control draws не считается
фиксированной. Помимо raw rows отчёт показывает число rebalance units и число
независимых UTC months.

Analysis calendar содержит каждый полный UTC month от первого месяца после
390-bar warmup всех 36 arms до последнего полного месяца bounded input. Каждый
scheduled rebalance обязан дать terminal strategy и 20 terminal controls;
месяц/arm без terminal unit не превращается в ноль и не пропускается, а
блокирует family run.

Inference не предполагает симметрию strategy-control differences. Для каждого
из 999 permutations и каждого rebalance causal factor scores каждого arm
переназначаются eligible symbols по
`SHA256("xsec_rank_perm_v1" || config_fingerprint || permutation_index || rebalance_ts || stratum_id || symbol)`.

Stratum формируется только из данных, известных до rebalance:

- maturity: `390..729` либо `>=730` закрытых daily bars;
- causal 30-day median dollar-turnover tercile внутри eligible universe;
- causal 30-day realized-volatility tercile внутри eligible universe.

Tercile rank разрешает ties лексикографическим symbol. Factor scores
перемешиваются только внутри exact Cartesian stratum. Stratum с менее чем
четырьмя symbols остаётся fixed; rebalance блокируется, если менее 80%
eligible symbols находятся в permutable strata либо у любого arm ни long, ни
short basket не содержит permutable symbol. Один mapping используется всеми
36 arms, сохраняя cross-arm dependence. Полный portfolio/cost/funding path и
20 matched controls затем пересчитываются для каждой permutation; control
seed дополнительно включает `permutation_index`.

Тестируются две заранее объявленные гипотезы:

1. family-rank null: observed median arm-level annualized **stress excess над
   собственными 20 matched controls** не выше той же метрики, полностью
   пересчитанной в stratified score permutations; one-sided family p-value;
2. arm-rank null: annualized stress excess каждого arm не выше permutations;
   maxT family включает все 36 arms, а gate читает adjusted p-values published
   champion и reference.

Обе гипотезы используют ту же primary excess metric, что effect-size gate, и
должны пройти. Это intersection-union gate; отдельная поправка
между family test и maxT family не применяется, а внутри arm family maxT уже
контролирует 36 сравнений. Двадцать matched baskets остаются effect-size и
bootstrap control, но permutation inference каждый раз строит null portfolios
заново и не считает эти 20 ledgers фиксированными.

После 390-bar warmup preflight делит общий доступный календарный интервал на
четыре максимально равных последовательных UTC-calendar folds; точные
границы и SHA записываются до первого return scoring и затем неизменны.

Минимальный `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW`:

- PIT/data/execution checks PASS;
- median stress family result, published champion stress result и фиксированный
  centre/reference stress result каждый строго положителен;
- минимум 3/4 chronological folds положительны;
- минимум 24/36 заранее фиксированных arms положительны в stress, median
  stress family result положителен, а published champion и фиксированный
  centre/reference arm оба положительны;
- крупнейший положительный symbol contribution не превышает 35%;
- median stress family excess над matched controls не только положителен, но и
  эквивалентен минимум 2 percentage points annualized;
- family-median permutation p-value `<= 0.05`; published champion и reference
  имеют maxT-adjusted p-value `<= 0.05`, а stress excess centre/reference arm
  больше одного стандартного отклонения distribution соответствующих control
  outcomes.

Любой PIT, funding или execution blocker даёт
`BLOCKED_DATA_OR_PARITY`, а не приблизительный PnL.

Этот verdict означает только право начать zero-risk shadow. Более сильный
`PROSPECTIVE_SHADOW_EVIDENCE_PASS` невозможен раньше 90 UTC days, 30 terminal
reference-arm rebalance intervals и 12 UTC weeks, а также требует
положительного stress excess над одновременно работающим control, 95%
cluster-bootstrap lower bound выше нуля и ни одного integrity incident.
Promotion/money authority после этого всё равно требует отдельного решения.

## 5. Подпроект C: Crypto Bull Continuation V1

### 5.1. Физическая гипотеза

Вход разрешён только после последовательности, известной на момент решения:

1. causal H4/D1 bull trend;
2. directional impulse или structure break;
3. первая контролируемая коррекция/retest;
4. acceptance/reclaim в направлении тренда;
5. план на next-open, а не на уже закрывшейся сигнальной цене.

BTC и ETH считаются отдельными фиксированными cohorts. Alt cohort использует
ровно существующий fixed-51 universe SHA
`fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19`
из `configs/research/sbr1_fixed51_evidence_manifest_v1.json`, за вычетом
BTC/ETH при cohort-отчёте. До scoring exact 49-symbol list записывается в
`configs/research/bull_continuation_fixed51_alt_cohort_v1.json` с собственным
SHA; causal gates никогда не меняют этот список, а только дают reason codes.
Минимум 30 alt symbols должны иметь полное causal coverage одновременно в
development и diagnostic holdback, иначе alt-cohort результат блокируется.
Символ допускается только после собственного
causal listing/maturity/coverage gate; отсутствующий исторический symbol не
заменяется будущим победителем. Это current-universe diagnostic с явно
опубликованным survivorship caveat, а не PIT доказательство.

Bull regime V1 фиксируется причинно: последняя закрытая D1 свеча выше EMA200,
наклон D1 EMA200 за 20 закрытых D1 баров положителен, последняя закрытая H4
свеча выше EMA50, а наклон H4 EMA50 за 12 закрытых H4 баров положителен. Все
EMA должны быть полностью прогреты; отсутствие истории даёт `not_admitted`, а
не подстановку. Режимные D1/H4 данные управляют admission. Геометрия уровня и
импульс строятся на закрытых H1 данных, hold/retest/confirmation — на строго
последующих закрытых M15, intended fill — первый точный M5 open после
confirmation. Все три агрегации требуют contiguous closed M5 source.

Исторические границы замораживаются до scoring:

- development: `[2023-01-01T00:00:00Z, 2024-07-01T00:00:00Z)`;
- purge/embargo: `[2024-07-01T00:00:00Z, 2024-08-01T00:00:00Z)`;
- chronological diagnostic holdback: `[2024-08-01T00:00:00Z,
  2025-10-01T00:00:00Z)`.

Эти интервалы уже могли быть затронуты другими исследованиями проекта, поэтому
holdback не называется OOS/validation и не заменяет prospective evidence.

### 5.2. Горизонтальные и наклонные уровни

Оба типа входят в научный контракт, но физически раздельно:

#### Arm H — horizontal first retest

- Использует immutable `LevelSnapshotV1` из `bot/level_snapshot_v1.py`.
- Level строится до импульса и не перерисовывается сигнальными или будущими
  барами.
- Базовая state machine переиспользует причинную модель
  `strategies/event_expansion_retest_long_mtf_v1.py` и исполнение
  `bot/event_long_execution_v1.py`: closed H1 expansion -> later M15 hold ->
  first M15 retest -> confirmation -> exact next M5-open plan.
- Frozen `LevelSnapshotConfigV1`: `lookback_bars=120`, `atr_period=14`,
  `pivot_left=2`, `pivot_right=2`, `min_confirmed_pivots=2`,
  `cluster_tolerance_atr=0.30`, `zone_half_width_atr=0.18`,
  `max_distance_atr=5.0`, `approach_lookback_bars=3`,
  `min_approach_bars=2`, `min_approach_depth_atr=0.30`,
  `reaction_lookahead_bars=3`, `min_reaction_atr=0.30`,
  `close_break_tolerance_atr=0.0`, `require_contiguous_source=true`.
- V1 использует причинную H1/H4 horizontal resistance, которая после
  подтверждённого H1 breakout становится `flip_support`. Exact frozen defaults
  `EventExpansionRetestLongMTFConfigV1` сериализуются целиком в config manifest.
  При нескольких eligible levels текущий tie-break сохраняется точно:
  минимальное расстояние `abs(zone_high-prior_H1_close)`, затем H4 перед H1.

#### Arm S — sloped pullback hold

- Использует immutable `SlopedLevelSnapshotV1` из
  `bot/sloped_level_snapshot_v1.py`.
- Минимум три confirmed pivots, подтверждённые правыми барами; exact source
  prefix, as-of timestamp и config SHA входят в snapshot identity.
- Базовый quality floor: `R² >= 0.80`, contiguous source и отсутствие
  closed-bar break до решения.
- Frozen `SlopedLevelConfigV1`: `lookback_bars=240`, `pivot_left=2`,
  `pivot_right=2`, `min_confirmed_pivots=3`, `min_r_squared=0.80`,
  `require_contiguous_source=true`, `require_unbroken_closes=true`. Допускается только
  восходящая support line с `slope_per_interval > 0`. Если builder когда-либо
  начнёт возвращать несколько линий, tie-break фиксирован: последний
  `valid_at`, затем больший `r_squared`, затем больше pivots, затем
  лексикографически меньший `line_id`.
- Line snapshot строится на prefix, заканчивающемся до candidate expansion H1.
  Candidate H1 обязан пройти те же frozen expansion thresholds, что Arm H:
  range `>=1.25ATR`, bullish body fraction `>=0.45`, close return от prior close
  `>=1%`, volume `>=1.25x` mean последних 24 H1. Дополнительно open и close
  выше projection support, а close выше максимального high предыдущих 20 H1
  bars плюс `0.08ATR`. Иначе sloped event не создаётся.
- Отдельный adapter `SlopedContinuationEventV1` принимает H1 snapshot с
  canonical millisecond timestamps, `interval_ms=3_600_000` и
  `as_of_ms=last_closed_H1_open_ms+3_600_000`. ATR фиксируется как ATR14
  закрытого H1 prefix в момент event creation. Для M15 bar с close boundary
  `t` projection равна
  `intercept_at_anchor + slope_per_interval*((t-anchor_ts_ms)/3_600_000)`.
  Сначала нужны два последовательных M15 closes не ниже
  `projection+0.03ATR`; touch до этого hold инвалидирует event.
  `touch` требует `projection-0.20ATR <= M15_low <= projection+0.10ATR` и
  `M15_close >= projection`; любой subsequent M15 close ниже projection
  инвалидирует event. Event expiry — 48 M15 bars.
- `close acceptance` требует M15 close минимум на `0.03ATR` выше projection и
  выше предыдущего M15 close. `structure break` использует ту же причинную
  структуру, что Arm H: higher-low pivot `left=1/right=2`, минимум `0.02ATR`
  выше first-retest low, затем строго более поздний bullish close выше
  pre-retest structure high плюс `0.05ATR`. Decision известен на M15 close,
  intended fill — exact next M5 open. Event/config fingerprint включает ATR,
  projection, pivot, expiry и все aggregation hashes. Event не может перейти
  между Arm H и S.
- Arm S имеет отдельные event IDs, trades, controls и verdict. Его результат
  нельзя суммировать с Arm H, чтобы скрыть отрицательную геометрию.

Order blocks и imbalances не входят в эти две версии. Они получат отдельную
версию только после PIT passport, non-overlap engine, matched random control и
нового sealed либо prospective окна, которое не использовалось для их
разработки. Это предотвращает незаметное добавление ещё десятков степеней
свободы и повторное доказательство на уже просмотренной истории.

### 5.3. Поиск входа и выхода без подгонки

На development history допускается bounded matrix не более восьми контрактов:

- geometry: `H` или `S`;
- confirmation: close acceptance либо confirmed structure break;
- exit: full size at 2R либо 50% at 1R + 50% at 2R; обе версии имеют
  deterministic time exit после 96 M5 bars.

Partial arm переиспользует неизменный `bot/event_long_execution_v1.py`.
Full-2R arm требует отдельный research-only
`bot/event_long_full_2r_execution_v1.py`: тот же exact M5 fill, frozen stop,
stop-gap, stop-first, costs/funding и max-hold=96, но `tp1_fraction=0` и
`tp2_fraction=1`. Он получает отдельные schema/config/code hashes и
conformance suite; его нельзя передавать существующему executor, который
правильно отклоняет такую геометрию.

Для каждого контракта заранее фиксируются:

- entry timestamp/fill rule;
- stop source и stop-first intrabar rule;
- target/partial fractions;
- time stop;
- funding и base/stress costs;
- maximum event overlap и cooldown.

Stop замораживается на decision: для H это
`min(first_retest_low, zone_low)-0.10*H1_ATR`, для S —
`min(first_retest_low, projected_support_at_decision)-0.10*H1_ATR`. Actual M5
open re-anchors R и targets; gap open на/ниже stop исполняется как adverse
`stop_gap`, а не отбрасывается. В обеих exit arms действует stop-first,
base costs `6 fee + 2 slippage bps` на сторону, stress `10 + 5 bps` на сторону,
funding credits обнуляются в stress, positive debit не меньше 5 bps на funding
event, missing funding блокирует run. На symbol одновременно допускается один
event; cooldown продолжается до terminal exit. Максимальное окно от H1 event
creation до terminal outcome — 20 часов (48 M15 expiry + 96 M5 holding).

Development ranking детерминирован и использует только development portion.
В chronological diagnostic holdback переходят максимум два контракта — не более одного
на geometry. Сначала arm должен иметь development stress net `> 0`, не менее
3/4 положительных folds, положительный top-5%-trimmed result, положительное
превышение над matched control и концентрацию крупнейшего положительного
symbol contribution `<= 35%`. Внутри одной geometry выбирается arm с
максимальным худшим fold stress net R; при равенстве — меньший drawdown, затем
лексикографически меньший config fingerprint. После freeze entry/exit не
меняются. Holdback FAIL закрывает контракт; он не возвращается в поиск на
том же окне.

Чтобы отличить пользу geometry, confirmation и exit, development отчёт
обязательно публикует полный 2x2x2 factorial и три marginal contrasts при
неизменных остальных осях. Это attribution, а не причинное доказательство:
holdback проходит только точный frozen bundle, а хороший усреднённый
contrast не спасает отрицательный bundle.

Selection по восьми development contracts учитывается через deterministic
Westfall-Young/maxT по 999 blocked permutations. На holdback два заранее
выбранных geometry arms проверяются Holm-adjusted one-sided p-values (либо
эквивалентным maxT) с family-wise порогом `0.05`.

### 5.4. Проверка работоспособности стратегии

Каждая стратегия проходит пять слоёв:

1. **Causal/unit integrity.** Future-append invariance, closed-bar-only,
   timestamp grid, gap/duplicate rejection, stable snapshot/event/config IDs.
2. **Mechanical replay.** Ровно один event/episode, next-open fill,
   stop-first, target/partial/time exit, end-of-window censoring и полный
   decision-to-exit ledger.
3. **Economic validation.** Base/stress costs, funding, chronological folds,
   controls, concentration, MFE/MAE, DD и top-tail removal.
4. **Portfolio compatibility.** Symbol/side overlap, BTC/alt beta,
   correlation/cluster exposure и конфликт с SBR1/range-long.
5. **Prospective parity.** Zero-risk shadow сравнивает signal timestamp,
   intended and observable next fill, latency, gaps, stop/target lifecycle и
   decision reason codes. Исторический PASS разрешает только этот слой.

Mechanical suite обязан содержать golden и отрицательные fixtures: будущий
бар не меняет прошлый snapshot; неподтверждённый pivot не входит в линию;
breakout без first retest не создаёт entry; H и S дают разные event IDs;
close ниже support инвалидирует S; сигнал на H1 close не может исполниться до
завершения M15 confirmation и следующего M5 open; одновременное касание SL/TP
разрешается stop-first; time stop и partial targets не используют бар после
exit. Дополнительно строится
fragility report со сдвигом fill на один бар позже и разумным ухудшением costs.
Это не новый parameter search: сдвиги не могут стать победившей конфигурацией,
они только показывают, исчезает ли эффект от минимальной ошибки исполнения.

Episode independence определяется до scoring:

- event window равен `[H1_event_known_at, terminal_outcome]` и ограничен
  максимум 20 часами frozen expiry+holding contract; overlapping windows
  одного symbol/side — один symbol episode, остаётся самый ранний causal event;
- события разных symbols с decision в одной UTC calendar date образуют один
  market cluster; `cluster_id=YYYY-MM-DD` и membership входят в config
  fingerprint до outcome scoring;
- отчёт показывает raw N, symbol-episode N и market-cluster N, а uncertainty
  пересчитывается cluster bootstrap по market clusters.

Для каждого Bull episode 20 matched timestamps выбираются hash-ranking из
того же symbol, UTC month, bull-regime state и H1 ATR decile. Timestamp не
может попадать ни в один frozen event window; ему применяются тот же intended
M5 fill, frozen stop-distance R, exit, costs и funding. Если eligible set имеет
меньше 20 непересекающихся paths, episode получает `control_unavailable` и
весь arm блокируется. Westfall-Young меняет paired strategy/control labels
одним bit на весь UTC-date cluster одновременно для всех восьми contracts;
primary statistic one-sided — mean stress excess R на symbol episode, maxT
учитывает все восемь development contracts.

Минимальный diagnostic-holdback `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` для
bull-continuation arm:

- не менее 40 закрытых symbol episodes и 20 market clusters;
- base и stress net R строго положительны;
- обе chronological halves и минимум 3/4 folds положительны в stress;
- top-5%-trimmed stress result положителен;
- среднее stress excess над matched control не менее `0.05R` на symbol episode,
  PF не менее `1.20`, adjusted permutation p-value `<= 0.05`, а нижняя граница
  95% cluster-bootstrap interval для excess строго выше нуля;
- превышение над matched control больше одного стандартного отклонения
  distribution контрольных результатов;
- крупнейший положительный symbol contribution `<= 35%`;
- ни один causal/mechanical/portfolio check не имеет fail.

Этот historical holdback даёт только право на zero-risk shadow. Более сильный
`PROSPECTIVE_SHADOW_EVIDENCE_PASS` требует минимум 60 UTC days после
preregistration, 50 terminal symbol episodes, 20 UTC-date market clusters,
положительный stress excess и 95% cluster-bootstrap lower bound выше нуля без
integrity incident. Проспективные параметры не меняются по результатам
historical diagnostic.

## 6. Подпроект D: XAUUSD unchanged replication

### 6.1. Что проверяется

Повторяется один существующий контракт `session_breakout_retest`:

- XAUUSD;
- H1 из M5;
- 2R target;
- 1.5 ATR stop;
- максимум шесть H1 bars;
- setup kwargs: `sessions=(london,london_ny_overlap,newyork)` и
  `level_lookback=120`;
- exact static-UTC expansion: London `[07:00,12:00)`, overlap
  `[12:00,16:00)`, New York `[16:00,21:00)`; DST не сдвигает эти labels;
  `events=None`, поэтому unchanged history не притворяется, что имеет news
  calendar;
- stop-first intrabar;
- forced flat на первой H1 свече в/после 20:55 UTC;
- base costs `fee/spread proxy=1.0 bps + slippage=0.5 bps` на сторону и stress
  `2.0 + 1.0 bps` на сторону до получения broker-calibrated costs.

Unchanged означает exact engine replication, а не только одинаковое имя
setup. Preflight пинует SHA-256 следующих файлов и machine-readable arguments:

- `scripts/run_fx_native_harness.py`;
- `bot/fx_harness.py`;
- `bot/fx_setups.py`;
- preregistration JSON/MD;
- data manifest и coverage/closure receipt.

Текущий harness вызывает setup на prefix, включающем текущий закрытый H1 бар, и
исполняет diagnostic entry по `rows[i][CLOSE]`. Это close-fill proxy, а не
next-open и не broker-fill. Stop/target разрешаются только на последующих
барах, stop-first. Forced flat срабатывает на open первого последующего H1
бара, у которого изменилась UTC calendar date либо UTC minute `>=20:55`; на
часовой сетке это обычно 21:00 UTC. Unchanged replay обязан воспроизвести
именно эту механику и явно маркировать её diagnostic. До shadow отдельно
строится next-open/bid-ask repricing parity; close-fill нельзя выдавать за
исполнимый результат.

H1 open ровно 20:55 на часовой сетке невозможен. Если 21:00 bar отсутствует по
scheduled closure/holiday, force-flat исполняется на open первого следующего
полного H1 bar и принимает весь gap; если следующего полного bar нет до конца
bounded input, outcome остаётся `censored`, а не закрывается последним close.

Его текущий diagnostic: base `N=13`, `+3.915R`, PF `1.730`; stress
`+3.012R`, PF `1.526`, 3/4 folds. `N<30` остаётся binding failure.

### 6.2. Данные

Новая data identity выбирается в фиксированном порядке:

1. user-authorized OANDA market-data fetch через уже существующий resumable
   materializer;
2. при отсутствии OANDA authority — deterministic XAUUSD M5 export с
   Bullwaves MT5 demo после ротации токена и подтверждения demo identity;
3. если ни один источник не доступен, результат
   `BLOCKED_DATA_OR_PARITY`; текущий локальный CSV не объявляется независимой
   репликацией.

До scoring обязательны:

- monotonic timestamps, no duplicates, OHLC validity;
- weekly/holiday/DST-aware closure map;
- expanded static session schedule и holiday/closure rows в immutable manifest;
- coverage и gap report;
- overlap reconciliation с текущим bounded CSV;
- symbol digits, contract size, timezone, bid/ask, typical spread, swap и
  session specification.

Raw M5 row имеет строгую схему
`[open_ts_utc_seconds, open, high, low, close, volume]` и представляет полуоткрытый
интервал `[open_ts, open_ts+5m)`. H1 bucket равен
`floor(open_ts/3600)*3600`; bucket допускается только при наличии ожидаемых
M5 constituents либо при явном scheduled-closure reason из closure map.
Неполный обычный час не заполняется и не интерполируется.

### 6.3. Уровни XAU

Первая репликация сохраняет горизонтальные session levels, потому что иначе
она перестанет быть репликацией. Наклонные уровни, order blocks и imbalances
не добавляются постфактум.

После data/parity gate допускается отдельный prereg `XAU Trend Pullback V1`:
D1/H4 trend -> causal H1 horizontal **или отдельно sloped** structure -> M15
entry. Это новый эксперимент, а не спасение session-breakout результата.

### 6.4. Gate

Сначала unchanged proxy выдаёт только `DIAGNOSTIC_REPLICATION_PASS/FAIL`.
Перейти к `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` можно лишь после
broker-calibrated spread/slippage/swap contract и отдельной next-open/bid-ask
repricing parity.

Минимальный исторический `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW`:

- независимая feed/data parity PASS;
- base и stress net R строго положительны;
- `N >= 30`;
- не менее 20 различных UTC entry-session dates и четырёх UTC calendar months;
- минимум 3/4 chronological folds положительны;
- PF не менее `1.20`, среднее stress excess над time-matched random-entry
  control не менее `0.05R` на trade, one-sided blocked-permutation p-value
  `<= 0.05`, а нижняя граница 95% bootstrap interval для excess выше нуля;
- превышение над control больше одного стандартного отклонения distribution
  контрольных результатов;
- top-5%-trimmed stress result положителен, а крупнейшая положительная
  UTC-session-date contribution не превышает 35%;
- costs/session/swap assumptions полностью опубликованы.

После PASS разрешён только zero-order MT5 demo journal с signal, bid/ask,
intended fill, SL/TP, outcome, costs, heartbeat и reconciliation.

Для XAU matched timestamp выбирается на том же XAUUSD, в том же UTC month,
static session label, physical side и H1 ATR decile, вне любого event/forward
path. Из заранее отсортированного eligible set выбираются первые 20 уникальных
paths по общему hash-ranking; меньше 20 блокирует experiment. Exit
horizon/costs идентичны. Primary effect — mean stress excess R на
trade; cluster — UTC entry-session date. Permutation меняет paired labels
одновременно для всех trades одной session date. XAU manifest обязан пиновать
SHA общего control contract и буквально использовать его 999 permutations и
9999 cluster-bootstrap resamples; локальная замена seed/unit запрещена. Более сильный
`PROSPECTIVE_SHADOW_EVIDENCE_PASS` требует минимум 60 UTC days, 30 terminal
demo signals, 20 session dates, положительный broker-cost stress excess и ни
одного reconciliation/integrity incident; money authority по-прежнему нет.

## 7. Общие error handling и fail-closed правила

- Missing, stale, malformed или hash-mismatched input останавливает run.
- Exception не превращается в `no signal` или пустой положительный результат.
- Future bar, open bar, non-causal membership или boundary row создаёт
  terminal integrity receipt.
- Один decision/event не может появиться несколько раз в статистике.
- Незакрытый outcome остаётся `pending/censored` по заранее заданному правилу.
- Любой результат публикуется, включая отрицательный и техническую неудачу.
- AI/Ollama не выбирает параметры, не переписывает verdict и не получает
  order/risk authority.

## 8. Артефакты и независимая проверка

Каждый подпроект публикует:

- preregistration и machine-readable config;
- input/code/config manifest с SHA-256;
- integrity/preflight receipt;
- raw decision/trade/control ledgers;
- compact base/stress metrics;
- independent audit, пересчитывающий ключевые значения из raw ledgers;
- terminal verdict и reopen condition.

В канонический roadmap попадают только terminal receipts или явно
`IN_PROGRESS` run IDs. Наличие screen/process без свежего evidence не считается
работающим исследованием.

## 9. Распределение работы

- Сильная модель: causal contracts, leakage, multiple-testing boundary,
  integration design и final verdict review.
- Лёгкие агенты: inventory, hashes, deterministic reports, focused tests,
  source reconciliation и independent arithmetic.
- Ollama: proposal-only классификация логов, missing explanations и
  concentration anomalies по уже материализованным данным.
- Владелец: authority на external market-data credentials и любые будущие
  money-release decisions.

## 10. Последовательность и ожидаемые checkpoints

1. **Canonical truth:** migration receipt и свежий канонический station status.
2. **XSEC:** PIT V5 prereg/preflight, затем bounded family run и audit.
3. **Bull continuation:** feature/mechanics tests, bounded development matrix,
   freeze максимум Arm H/Arm S survivors, chronological diagnostic holdback и audit.
4. **XAU:** independent data manifest/parity, unchanged replay и audit.
5. **Shadow:** только прошедшие кандидаты получают zero-risk shadow + control.

Ориентиры при отсутствии новых data blockers:

- canonical research truth: несколько инженерных часов;
- первые XSEC/bull diagnostics: 2–5 рабочих дней;
- XAU replication: 3–5 рабочих дней после доступности независимого источника;
- money integration в этот спринт не входит.

### 10.1. Декомпозиция реализации

Этот документ — общий архитектурный контракт. Он не превращается в один
гигантский implementation plan. После его утверждения создаются четыре
отдельных исполнимых плана с собственным review/test/commit циклом:

1. canonical research routing/migration;
2. XSEC PIT V5;
3. Crypto Bull Continuation V1;
4. XAUUSD unchanged replication.

Первым исполняется canonical routing. XSEC и Bull Continuation могут идти
параллельно после его PASS. XAU data preparation может идти параллельно, но
scoring начинается только после собственного data/parity preflight.

## 11. Критерий завершения спринта

Спринт завершён успешно не только при положительной стратегии. Он завершён,
если:

- research station снова имеет одну проверяемую точку истины;
- каждый из трёх кандидатов имеет воспроизводимый terminal verdict;
- хотя бы один кандидат с `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` запущен в
  zero-risk shadow **или** все кандидаты
  честно закрыты с конкретным failure mode и освободили слоты следующей
  очереди;
- live/risk/order authority не изменилась без отдельного owner-approved gate.

## 12. Следующий архитектурный подпроект: Research Conveyor

Конвейер не входит в реализацию этого спринта, но фиксируется следующей
архитектурной задачей, чтобы поиск не вернулся к ручному «тыканию».

Его базовый поток:

```text
idea intake + source/provenance
  -> normalized hypothesis/market/phenotype registry
  -> cheap broad screen with a declared multiplicity budget
  -> frozen candidate preregistration
  -> causal replay + matched control + stress + concentration
  -> diagnostic holdback
  -> zero-risk prospective shadow
  -> separate portfolio and money-release gate
```

Ключевой принцип: тысячи вариантов разрешены только в discovery layer и
публикуются полным search landscape. Победитель такого перебора не получает
право на shadow или деньги; он становится новой гипотезой и проходит отдельную
замороженную проверку. Это сохраняет скорость, не превращая поиск в p-hacking.

Конвейер должен иметь:

- единый idea registry для ручных идей, market-pattern miner, Ollama/LLM
  proposals и внешних источников с provenance;
- market adapters для crypto, equities/Alpaca, XAU/Forex и позднее DeFi/
  prediction markets, но один общий evidence/verdict protocol;
- deterministic scheduler с CPU/disk/data freshness budget и fail-closed
  resource guard;
- библиотеку отрицательных фенотипов: failure mode, regime, entry/exit
  attribution, costs, concentration, data defect и разрешённый следующий
  falsifiable experiment;
- mutation/ablation tests логики входа, выхода, режима, уровней и исполнения;
- prospective shadow/control registry и портфельный conflict graph;
- AI/Ollama в proposal/classification роли без verdict, code-merge, order или
  risk authority.

Отдельный design Research Conveyor создаётся после письменного approval этого
документа. Первая реализация конвейера должна оркестрировать уже существующие
детерминированные runners и receipts, а не переписывать их в новый монолит.
