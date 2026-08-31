# Codex checkpoint — 2026-08-31

## Итог сессии

Каноническая ветка проекта — `codex/recovery-20260824` в дереве
`bybit-bot-recovery-20260824`. Проверенный и запушенный code floor Task 5:

`482a536f1b734361c42720744243465b3f033a69`

Сам checkpoint публикуется следующим документационным коммитом, поэтому его
собственный SHA намеренно не встраивается в файл.

Task 5 canonical-station migration завершён, независимо атакован тестами,
закоммичен и запушен. Live, broker, ордера, позиции, риск, money authority и
старые screen-сессии в этой сессии не менялись.

Это завершение кода безопасной миграции, а не сама live-миграция. Последний
реальный запуск был только `--dry-run`; его терминальный результат —
`NOT_CONFIRMED`, поэтому ни одна legacy-сессия не остановлена.

## Что доказано по Task 5

Commit:

`482a536 feat: fail closed during canonical station migration`

Изменены только:

- `scripts/canonical_station_migration.py`;
- `tests/test_canonical_station_migration.py`.

Реализовано:

1. Отдельные hash-bound receipts для inventory, launch, parity, durable
   authorization, stop и terminal migration result.
2. Stop возможен только для exact screen из свежего CONFIRMED inventory.
3. Canonical launch обязан быть реальным `dry_run=false`, exact one-to-one с
   manifest, с живыми PID, source/config/input hashes и единым evidence epoch.
4. ATT1/SBR1 здесь не имеют особого пути: процессный comparator выбирается по
   `process_kind` и заново исполняется на embedded receipts.
5. Comparator inputs привязаны к заново прочитанным legacy/canonical evidence
   files; изменение любого evidence после inventory/parity закрывает gate.
6. Непосредственно перед `screen -X quit` повторно проверяются:
   canonical screen/PID всех replacements, legacy screen PID, child PID,
   command, cwd и evidence.
7. Строгие allowlist-схемы действуют отдельно для top receipt, launch job,
   parity job, heartbeat/evidence payload и embedded process receipt. Любой
   неизвестный ключ закрывает gate независимо от имени и типа значения.
8. Dry-run не вызывает `screen`, `ps` или `lsof`, не создаёт stop authorization
   и не останавливает процессы.
9. Output directory обязан быть новым/пустым; старый PASS нельзя подложить.
10. JSON с duplicate keys, non-finite numbers, stale timestamps, hash drift,
    расширенным scope или неполным stop receipt отклоняется.

Verification:

- связанный suite: `157 passed`;
- `py_compile`: PASS;
- `git diff --check`: PASS;
- независимый red-team: GO;
- 24 комбинации неизвестных capability fields: все `FAIL_CLOSED`, stop=0;
- canonical отсутствует, legacy PID/command/cwd изменён, evidence изменён:
  stop не вызывается.

Последний factual dry-run:

`runtime/local_research_station/migrations/dryrun_20260831_task5_v9/`

- 5/5 canonical jobs: `DRY_RUN`;
- PID: 5/5 `null`;
- terminal state: `NOT_CONFIRMED`;
- `legacy_stop=[]`;
- `stop_receipts=[]`;
- `authorization_sha256=null`;
- `migration_authorization.json` отсутствует;
- 4/4 receipt hashes валидны.

## Стратегии и путь к деньгам

### ATT1/SBR1

Reserved OOS diagnostic уже израсходован 2026-08-29 и повторяться как v1 не
может.

- ATT1: `FAIL_CLOSED`. Base/stress положительны целиком, но stress second half
  `-0.3372R`; temporal stability gate не пройден.
- SBR1: `INCONCLUSIVE_LOW_N`, `N=16`; base и stress отрицательны.
- Ни одна из этих двух конфигураций не получает новое money authority.

Полный результат:
`reports/ATT1_SBR1_RESERVED_OOS_RESULT_2026_08_29.md`.

Следствие: нельзя переключать пять найденных live/research расхождений прямо в
деньги. Их можно использовать только как входы для нового preregistered
эксперимента, не как команду увеличить риск.

### XSEC PIT V5

Утверждённый план:
`docs/superpowers/plans/2026-08-29-xsec-pit-v5-implementation-plan.md`.

Первым создаётся общий deterministic control contract. Затем строятся 36
frozen arms и PIT preflight. Критический текущий факт: provider inventory знает
936 закрытых контрактов, но локальные daily/funding archives покрывают только
137 текущих символов и ноль историй закрытых контрактов. Поэтому честный XSEC
V5 обязан вернуть `BLOCKED_DATA_OR_PARITY`, пока delisted history не получена.
Подмена current-137 universe запрещена: это survivorship bias.

### Crypto Bull Continuation V1

Утверждённый план:
`docs/superpowers/plans/2026-08-29-crypto-bull-continuation-v1-implementation-plan.md`.

После shared XSEC control contract параллельно реализуются:

- frozen bull-continuation preregistration;
- sloped-continuation event detector;
- long-only full-2R execution model;
- eight-contract scoring, random controls, stress and holdback gates.

Горизонтальные и наклонные уровни входят в дизайн. Cooldown действует до
terminal exit, а не фиксированные 20 часов. Это research-only до прохождения
всех gates.

### XAU/USD и Forex

Инженерный план уже существует:
`docs/superpowers/plans/2026-08-29-xauusd-unchanged-replication-implementation-plan.md`.

Он не выполнялся в этой сессии. Правильный порядок: сначала общий control
contract XSEC, затем unchanged replication XAU на демо/public data. Никакого
MT5 money authority до PIT/data parity, costs, matched controls и paper
lifecycle.

### Alpaca

Последний канонический документ оставляет новые входы в `SAFE_HOLD` до
selector/PIT, gap/restart/partial-fill stress, tested/deployed SHA reconciliation
и чистого prospective paper lifecycle. Task 5 это состояние не менял.

Исторические replay/stress могут закрыть большую часть инженерных вопросов,
но не доказывают broker session transitions. Перед разморозкой нужен отдельный
актуальный broker/service/deployed-SHA read, потому что сведения из старых
checkpoint могут быть устаревшими.

## Карта канонической системы

Целевой pipeline:

`idea intake → preregistration → causal replay → random/matched control → stress + concentration → zero-risk shadow → paper lifecycle → tiny canary → allocator/regime governor → degradation monitor → scale/disable`

Главные слои:

1. `smart_pump_reversal_bot.py`, `bot/` — денежный runtime и adapters.
2. `research_lab/live_native_*`, `research_lab/adapter_parity.py` — единый
   research/live decision and fill contract.
3. `research_lab/`, `backtest/`, `strategies/` — hypothesis and replay layer.
4. `research_lab/canonical_station.py`,
   `scripts/canonical_station_migration.py`,
   `configs/research/canonical_station_v1.json` — evidence routing and migration.
5. `scripts/build_regime_state.py`, `scripts/build_symbol_router.py`,
   `scripts/build_portfolio_allocator.py` — regime/router/allocator control plane.
6. `web/`, Telegram operator and receipts — observability, not money truth.
7. Broker positions/orders/fills + deployed hashes + heartbeat — final live
   truth; Git alone никогда не доказывает deploy.

ИИ/Ollama/DeepSeek остаются proposal-only и secret-free. Они могут искать
аномалии, классифицировать failures, готовить prereg и отчёты. Они не имеют
права включать стратегию, менять риск или отправлять ордера.

## Два рабочих дерева и сохранность 11 дней

### Каноническое дерево

`bybit-bot-recovery-20260824` — единственное дерево для новой интеграции.

Core parity, live-native adapters, SBR1/ATT1 shadow, reserved OOS, Alpaca floor,
canonical station и связанные tests/receipts уже сохранены в Git и upstream.

### Старое активно меняющееся дерево

`bybit-bot-clean-v28`, branch `codex/dynamic-symbol-filters`, HEAD `76fc63c`.

Read-only audit зафиксировал плавающий snapshot:

- 58 modified tracked;
- 15 deleted tracked;
- 0 staged;
- 491 untracked status entries / около 1205 фактических untracked files;
- writers продолжали создавать research output во время аудита.

Поэтому blind commit там запрещён. Из 58 modified tracked 20 уже byte-identical
каноническому HEAD, 2 есть в истории recovery, 36 содержат уникальные blobs.
Из untracked 31 уже совпадают с recovery HEAD, ещё 4 есть в истории; остальное
требует классификации.

Локальная страховка:

`_snimki/KOD_I_DOKUMENTY_20260831_0720.tar.gz`

- size: `182269917` bytes;
- SHA-256: `ad810ccc2564fa5c1e32e7179fe1c54255c398049afb12abc553ab0a554c8d37`;
- gzip integrity: PASS;
- 35189 members;
- 76 filename-level secret-risk members.

Этот архив нельзя коммитить или отправлять как есть.

Никогда не добавлять в Git:

- `_snimki/`;
- `_to_delete/`;
- `*.bak*`;
- `.env*`, credentials, sessions, histories, corpus, runtime logs;
- raw datasets и массовые generated results без отдельного evidence policy.

Старый `.git/index.lock` выглядит stale, но дерево активно меняется. Его не
удалять и не использовать старый index до quiesced snapshot и отдельного
разрешения.

Уникальную работу переносить только из чистого isolated worktree на recovery
HEAD, отдельными группами:

1. archive relocations;
2. web/observability;
3. Alpaca monthly + order-block lab;
4. AI/runtime safety;
5. signal-copy core;
6. signal-copy tests/harness;
7. August 30–31 exploratory lab;
8. reconciled documentation.

Каждая группа: exact file list → secret scan → tests → independent review →
scoped commit → push. Никакого `git add -A`.

## Следующий исполняемый порядок

### Параллельный старт лёгкими моделями

1. XSEC Task 1: shared controls + 36-arm preregistration, отдельный commit.
2. Одновременно Bull Task 2: `sloped_continuation_event_v1.py` + tests.
3. Одновременно Bull Task 3: `event_long_full_2r_execution_v1.py` + tests.
4. Canonical Station Task 6: status/audit gate and operator documentation,
   без запуска миграции и без остановки screens.
5. Read-only source-preservation manifest для первой уникальной группы старого
   дерева; перенос только после stable two-snapshot check.

### После shared controls

1. Bull Task 1 frozen contract/preregistration.
2. XSEC PIT preflight. Ожидаемый честный исход до данных closed symbols —
   `BLOCKED_DATA_OR_PARITY`.
3. Отдельный public-only acquisition/import closed-contract histories.
4. Bull event/execution integration и frozen replay.
5. XAU unchanged replication на том же shared control contract.

### Что оставить сильной модели

- независимый review shared controls и causal/PIT semantics;
- решение по delisted-data provenance;
- interpretation XSEC/Bull/XAU results и promotion gates;
- интеграция high-risk unique runtime/signal-copy changes;
- любые решения о money authority, risk или live deploy.

## Запреты и reopen conditions

- Не открывать и не повторять consumed ATT1/SBR1 OOS v1.
- Не менять live risk, geometry, slots или money authority по текущим findings.
- Не останавливать старые screen-сессии, пока новый live launch и exact
  comparator parity не дали свежий PASS. Dry-run `NOT_CONFIRMED` не является
  разрешением.
- Не использовать current-137 как PIT replacement для closed-contract XSEC.
- Не коммитить всё старое дерево одним коммитом.
- Не считать research/shadow/paper PnL доказательством будущей доходности.

## Стартовая фраза следующему чату

> Продолжай строго с `reports/CODEX_SESSION_CHECKPOINT_2026_08_31.md` в
> `bybit-bot-recovery-20260824`. Task 5 уже commit/push `482a536`; live migration
> не выполнялась. Сначала XSEC Task 1 shared controls, параллельно Bull Tasks 2
> и 3, затем Task 6 canonical audit gate. Не трогай live/orders/risk и не
> останавливай legacy screens без actual parity PASS. Старое clean-v28 только
> read-only и scoped preservation; никакого `git add -A`.
