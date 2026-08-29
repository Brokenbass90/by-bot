# Текущий roadmap проекта

Обновлено: 2026-08-29. Это стабильная точка входа между чатами.
Датированные отчеты остаются журналом, но при конфликте планов сначала читать
`CURRENT_HANDOFF.md`, затем этот файл и только потом старые roadmap.

## Latest operational update — 2026-08-29

Авторизованный ATT1/SBR1 reserved diagnostic выполнен ровно один раз и
безвозвратно потреблён. Он завершился `FAIL_CLOSED_AFTER_CLAIM` на технической
ошибке суммаризатора после записи scorer-артефактов; повторного запуска не было.
Независимый failure-forensic audit подтвердил exact inventory, accounting,
research/live и normalized parity, а также нулевое воздействие на live и
деньги.

Предварительно замороженные решения восстановлены без подбора параметров:

- ATT1 — `FAIL_CLOSED`: stress `+19.5021R`, но вторая хронологическая половина
  `-0.3372R`, поэтому promotion gate не пройден;
- SBR1 — `INCONCLUSIVE_LOW_N`: `N16`, stress `-3.6881R`, PF `0.6080`; текущая
  геометрия не продвигается;
- money/risk/order/promotion authority не менялись.

Полная публикация и SHA:
`reports/ATT1_SBR1_RESERVED_OOS_RESULT_2026_08_29.md`. V1 сохраняется
byte-for-byte. Новый формальный v2 возможен только по новой owner authorization,
но сейчас не является разумным использованием времени: forensic результат уже
запрещает promotion. Главная очередь меняется на preregistered
bull-continuation и XSEC PIT rebuild; отдельно — диагностика временной
деградации ATT1 без тюнинга по просмотренному окну.

Целевая система строится шестью связанными контурами:

`idea intake → frozen causal validation → zero-risk shadow/control → allocator + regime governor → degradation monitor → gated release`.

ИИ остаётся proposal-only. Детерминированный governor может только уменьшить
или отключить риск при нарушении; обратное включение и увеличение капитала
требуют нового evidence receipt и owner-approved gate.

Alpaca остаётся отдельным SAFE_HOLD-треком. История должна закрыть
PIT/selector, gap/restart/partial-fill и stop-ratchet stress; затем короткий
prospective paper lifecycle проверяет реальное поведение брокера. История
ускоряет этот путь, но не заменяет его полностью.

## Latest operational update — 2026-08-26 17:05 UTC

`LIVE_CALLER_PARITY` завершён с verdict `PASS` строго в области
`default_off_zero_risk_research_candidate_only`. P1 persisted causal BTC H1,
P2 caller receipts, P3 ATT1 regime ON/OFF replay, P4 fixed-51 coverage и P5
candidate config verification закрыты. Текущий ATT1 money config отдельно
остаётся `FAIL_EXPECTED_MONEY_CONFIG_UNCHANGED`; риск, геометрия, слоты и money
authority не менялись, sealed rows не читались.

P2-код развёрнут в реальном монолите default-off. После рестарта bybot active,
heartbeat fresh, direct Bybit position/stop совпали до/после, DeepSeek paid
background flags остаются `0`. Все critical commits отправлены в
`origin/codex/recovery-20260824`.

Следующая сильная сессия имеет одну цель: `SEALED_RELEASE_PREFLIGHT`. Она
замораживает exact configs/universe/costs/hashes и готовит one-shot команду, но
не открывает sealed period без нового явного owner-разрешения.

Единый подробный отчёт:
`reports/PROJECT_STATE_AND_EXECUTION_PLAN_2026_08_26.md`.

## Canonical operating sequence — 2026-08-24

Это единая последовательность для любой новой ноги и для изменений уже живой
ноги:

`propose → preregister → parity → shadow + random control → paper lifecycle → tiny canary → scale`

ИИ, Ollama и DeepSeek могут индексировать код, искать аномалии, предлагать
гипотезы и готовить reproduction-пакеты. Они остаются `proposal-only`: у них нет
самостоятельного права менять параметры, риск, аллокатор, ордера или переводить
стратегию между стадиями. Переход выполняется только через hash-bound receipt,
детерминированный gate и owner-approved release.

### Разделение вселенных доказательства и денег

Для ATT1 и SBR1 это разные контракты:

- `evidence universe` — широкая фиксированная вселенная для безрискового shadow,
  random control и prospective evidence;
- `money universe` — узкая вселенная с отдельным live-native parity, лимитом
  слотов, корреляционным/exposure gate и собственной money authority.

Текущий ориентир для SBR1 получен прямым подсчётом доступной истории, а не
обещанием частоты: major-8 около `13.4` месяцев до 50 regime-eligible решений,
fixed-51 около `2.5` месяцев, full-137 около `1.9` месяца. Это оценки при
сохранении исторической частоты; они не заменяют parity, контроль случайности,
качество покрытия и фактическую prospective cadence. Для ATT1 те же universe
должны быть пересчитаны отдельным receipt, их нельзя переносить с SBR1.

### Цели ускоренного цикла

**30 дней:** закрыть live-caller parity ATT1/SBR1; запустить широкий
evidence-shadow с предрегистрацией и random control; завершить Alpaca
signal→fill→protection→management→exit paper replay; сделать health auditor
наблюдаемым; получить XAU/MT5 demo paper-tracker без ордеров. Ни один из этих
результатов не расширяет money authority сам по себе.

**90 дней:** получить минимум одну чистую prospective cohort с независимым
контролем, два подтверждённых lifecycle-receipt на каждом money-контуре,
reconciled allocator/regime stack и только затем рассматривать tiny canary;
масштабирование — ступенчато, после стабильной экономики, а не по календарю.
Цели доходности являются управленческими ориентирами, не прогнозом и не
основанием занимать капитал.

### Polymarket — research-only backlog

Идея добавлена в backlog как отдельный data/research контур: проверить API и
историческую доступность, комиссию, spread/liquidity, правила settlement,
oracle/resolve risk, latency и возможность причинного paper-replay. До этого
нет wallet, private key, deposit, order или market-making authority; любые
результаты проходят ту же prereg→replay→shadow последовательность.

## Latest recovery update — 2026-08-15 04:50 UTC

### Решение одним абзацем

ATT1 не начала отсчёт заново: clean live-когорта остаётся `N5/20`, `+2.950R`,
PF(R) `3.289`; новых закрытий за проверенный интервал нет. Но впервые точно
пересчитан именно live-universe из BTC/ETH/SOL/ADA/LINK/LTC/DOT/SUI, а не
похожая восьмёрка с AVAX: current geometry дала `-13.611R/402`, PF `0.944`,
поэтому исторический promotion gate отклонён и риск не повышается. Параллельно
Alpaca entry-relative stop перенесён в реальный paper bridge под default-off
флаг и покрыт тестами; лаборатория получила hash-chained lifecycle и провела
через него ATT1 от идеи до `DECISION_REJECTED`; XAU получил проверяемый маршрут
через OANDA/HistData вместо обхода Dukascopy quarantine guard.

### Что принято из последних работ Claude

- Нового отдельного git-коммита Claude поверх `5cc1b39` за ночь нет; большой
  незакоммиченный хвост остаётся старым общим workbench, а не «новой готовой
  поставкой».
- Идея `research_lab/trial_ledger.py` правильная, но сам файл не принят:
  повреждённые строки пропускаются, разрешение не связано с SHA и возможны
  повторные результаты. Нужная функция реализована заново в
  `research_lab/experiment_lifecycle.py` с fail-close поведением.
- Старые находки Claude не выброшены: `163` code-кандидата уже имеют очередь
  `test-backed / evidence-backed / referenced-review / quarantine`. Массовой
  зачистки и случайного захвата 500+ файлов нет.

### Прямое состояние исследований

- Research station: `6/6` процессов healthy, live/order authority отсутствует.
- Inplay ETH: фиксированный код совпадает с замороженным SHA; prospective `N0`.
  После старта причины молчания: `impulse_weak=547`, `no_breakout_side=144`,
  `impulse_body_weak=96`. На четырёх старых 35-дневных срезах тот же код давал
  `0.91–2.31` raw signals/day, но это cadence, не edge; при текущем нулевом
  темпе дата N30 неизвестна.
- Funding shadow: dynamic `13` закрытых и `2` открытых, медиана `-127.8 bps`;
  frozen `11+2`, медиана `-162.1 bps`. Положительные средние вызваны хвостом и
  концентрацией, поэтому это пока не денежная нога.
- Sloped V3 — это не «все наклонки», а один delayed-reclaim контракт:
  4h confirmed break → первый 15m retest/hold → reclaim → BOS. Он дал `18`
  сделок, `-5.371R`, PF(R) `0.521`, особенно слабая short-рука. Следующий тест
  меняет upstream quality самого 4h break либо формулирует отдельный long,
  а не продолжает подгонять момент ретеста.
- XAU Dukascopy остановлен своим guard: `30` completed, `26` market-empty,
  `32` quarantined при лимите `31`; holdout не читался. OANDA официально даёт
  M5 и страницы до 5000 свечей, но требует bearer token/account; HistData
  перечисляет XAUUSD как bulk fallback и требует отдельной проверки качества.
  Resumable OANDA materializer уже реализован и прошёл offline preflight; сеть
  не запускалась без авторизованного market-data token.

### Лаборатория стала честнее в коде, а не только в плане

- Новый lifecycle:
  `idea → hash-bound owner approval → prereg → spec SHA → preflight → passport → result → independent audit → decision`.
- Глобальная SHA256-цепочка, проверка неизменности артефактов, атомарный audit
  receipt; неверный порядок, повтор стадии, испорченный файл или nonzero audit
  дают fail-close.
- Первый полный проход: `9` стадий, артефакты verified, ATT1 завершена как
  `DECISION_REJECTED`; capital/order/promotion authority отсутствует.
- Focused suite: `50 passed`. Остаток: связать 4 idea cards с experiment IDs,
  заменить протухший scheduler receipt и только с повторным owner approval
  мигрировать `30` legacy name-only разрешений на SHA.

### Alpaca: что уже сделано и когда следующий gate

- Proxy-сигнал сохраняется: entry-relative stop `25.65% annualized`, DD
  `14.36%`, PF `1.837`, `5/25` красных месяцев; stress почти такой же.
- Реальный bridge теперь умеет дождаться fill, взять `filled_avg_price` и
  перенести на него замороженную signal-time risk distance. Флаг
  `ALPACA_ENTRY_RELATIVE_STOP_ENABLE` выключен по умолчанию; bracket-путь
  fail-close, допускается только fill-then-protect `simple_stop`.
- Это не включено и не задеплоено. `962/1000` файлов пригодны для bounded
  replay, но promotion всё ещё блокируют PIT membership, 24 after-delist
  conflicts, corporate actions, XNYS calendar и broker lifecycle parity.
- Условный срок: `2–4` инженерных дня до paper replay; решение о bounded
  micro-canary — `1–2` недели только при PASS и явном принятии остаточного PIT
  ограничения. Promotion-grade exact требует внешних PIT/corporate-action
  данных либо нового prospective monthly cycle.

### Следующие 72 часа

1. Alpaca: собрать exact paper lifecycle replay `signal → fill → stop/trail`,
   не снимая SAFE_HOLD и не включая новый флаг в live.
2. Inplay: сохранить контракт; выпускать cadence evidence и отдельно проверить
   входной data path, не ослабляя фильтры ради количества.
3. Crypto long: предзарегистрировать BTC/ETH upstream-break/continuation
   candidate; Sloped V4 — максимум две заранее объявленные руки с учётом
   multiplicity, не параметрический свип.
4. Funding: разложить медиану/хвост/концентрацию и exact spot-perp fees;
   текущий forward не продвигать.
5. XAU: запустить готовый resumable M5 fetcher, когда будет authorized
   OANDA market-data token; иначе валидировать HistData bulk против короткого
   Dukascopy overlap. Только потом frozen annual replay.
6. Лаборатория: закрыть explicit idea-to-experiment bridge и fresh bounded
   scheduler receipt; AI остаётся proposal-only.
7. Dirty workbench: следующий небольшой batch — `trial_ledger`, Alpaca
   validator, sweep-reclaim, portfolio auditor; на каждый файл reproduction
   receipt и решение keep/quarantine.

Полный отчёт с доказательствами: `reports/MORNING_RECOVERY_20260815.md`.

## Latest recovery update — 2026-08-14 15:13 UTC

### Ответ одним абзацем

Шаг большой по качеству системы, но не по числу денежных ног: ATT1 остаётся
единственной tiny-canary, второй подтверждённой ноги пока нет. Зато Sloped V3
за одну сессию прошла полный prereg → passport → causal replay → evidence и
была честно отклонена; ATT1 разложена по отрицательным фенотипам и режимам;
Alpaca state persistence укреплена атомарной записью; 163 кодовых кандидата из
грязного хвоста получили воспроизводимую очередь; исследовательский конвейер
проверен как `PARTIAL`, а не ошибочно объявлен самосовершенствующимся.

### Прямое состояние и денежные контуры

- Read-only Bybit check в `15:02 UTC`: broker flat, service active. За сессию
  не отправлялись/не отменялись заявки, не менялся риск и не было deploy/restart.
- ATT1 short: live risk `0.10`, clean cohort `N5`, `+2.950R`, PF(R) `3.289`;
  corrected pre-holdout `-2.468R/393`. Решение: tiny оставить, не масштабировать.
- ATT1 bull audit: в историческом bull bucket результат не был хуже
  (`+1.263R/91`), основной минус был в сильном 30d падении BTC
  (`-11.356R/35`). Но direct regime gate отсутствует, а доказанного long-аналога
  нет. Long continuation/retest строить отдельной ногой, не инверсией шорта.
- Inplay ETH: prospective shadow жив, `N0`; контракт не ослаблять ради частоты.
- Sloped V2: `-2.739R/18`; V3 delayed reclaim: `-5.371R/18`, PF(R) `0.521`.
  Ретестовый тюнинг остановить; следующая версия должна менять upstream 4h break
  либо формулировать отдельный long-механизм.
- XSEC остаётся orderless shadow. Funding/carry остаётся diagnostic: исторически
  `3.77%` base / `2.55%` stress на двухногий gross capital, а свежие forward
  медианы отрицательны и прибыль сконцентрирована.
- Alpaca остаётся SAFE_HOLD. Entry-relative challenger `25.65% annual / 14.36%`
  DD пока proxy, не exact live contract. HWM, re-entry и TG dedupe state локально
  переведены на atomic write; торговая логика и live не менялись.
- XAU materialization: `12/1734` календарных дней, лишь `3` завершённых
  рыночных дня и `5` quarantine. Текущий источник/скорость недостаточны для
  annual replay; нужен bulk/alternate source с теми же gap/DST guards.

### Что теперь известно про лабораторию

- `6/6` supervised research-only jobs и четыре public L2/tape collectors живы.
- Четыре полные idea cards существуют, но `0/4` связаны явным experiment ID с
  prereg/spec/passport/result.
- Nightly historical scheduler имеет status возрастом около `2231` часов.
- `30` approved specs привязаны к имени, `0` — к SHA256.
- Поэтому текущий verdict:
  `PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP`.

Следующая версия лаборатории: lifecycle ledger
`idea → approval → prereg → code SHA → preflight → passport → result → audit → decision`;
hash-bound owner approval; автоматический запуск только уже существующего
bounded research-кода; любой nonzero independent audit — fail-close. ИИ может
генерировать гипотезы и разбирать фенотипы, но не получает order/risk authority.

### Грязный worktree и динамический universe

- Недеструктивно классифицировано `163` code-кандидата: `5` test-backed,
  `115` evidence-backed/reproduction, `16` referenced/review, `27` quarantine.
  Остальные 500+ entries в основном данные, отчёты, логи, backup и результаты.
  Удаление только после reference map и quarantine receipt.
- Strategy-specific dynamic selection реален: IVB1 и Inplay прототипы есть.
  IVB1 rolling OOS честно провалился (aggregate PF `0.365`). Общего
  promotion-grade selector API пока нет. Следующая версия выбирает universe
  только из прошлых liquidity/setup-frequency/cost/stability данных и
  замораживает его на следующий месяц.

### Следующие 72 часа

1. Ввести lifecycle ledger и hash-bound approval; восстановить один bounded
   historical scheduler receipt без доступа к sealed holdout.
2. Alpaca: exact replay entry-relative stop на PIT/sector/corporate-action
   контракте; SAFE_HOLD не снимать по proxy.
3. Inplay: продолжать fixed prospective и считать причины молчания; не менять
   правила до первой cadence card.
4. Funding/XSEC: закрыть exact spot/perp mapping, real fees и concentration
   audit; деньги не подключать при отрицательной forward median.
5. Новая crypto long-нога: prereg upstream 4h break/continuation на BTC/ETH и
   major universe, отдельно от отвергнутого Sloped retest.
6. XAU: заменить медленный источник на проверяемый bulk/alternate source и
   только затем заморозить annual session-breakout/retest replay.
7. Dirty batch №1: portfolio engine, XSEC reference, backtest auditor,
   sweep-reclaim, trial ledger и Alpaca validator через reproduction receipts.
8. Server L2 retention: copy на Mac → SHA/decompression verify → receipt →
   только затем prune server source; storage cap вручную не обходить.

Полный новый статус: `reports/LIVE_READINESS_AUDIT_20260814.md`.

## Latest recovery update — 2026-08-13 14:25 UTC

- BTC ATT1 lifecycle закрыт прямыми events: `-1.288638R`; trailing был готов,
  но не активировался, потому что MFE не достиг `1R`. Слабое место — geometry:
  pivots `64477 -> 63690 -> 63994.4` образуют regression-down, но не строгую
  последовательность lower highs.
- Pivot-sequence challenger прошёл passport/audit: baseline `-17.916439R/538`,
  challenger `-2.467991R/393`, лучше на `6/8` symbols. Это repair candidate,
  не edge и не live change.
- Clean ATT1 cohort: `2/20`, total `-0.023897R`, PF `0.981`. Risk `0.10`
  сохраняется. Gate `0.25`: exact parity + N20 + net `>=2R` + PF `>=1.20` +
  DD `<=5R` + zero conflicts.
- Alpaca protection V2: entry-relative stop дал `25.65% annual / 14.36% DD`
  base и `24.87% / 14.43%` stress против current `11.14% / 23.71%`;
  independent audit PASS, capital false. Gap-2% challenger `23.69% / 9.21%`
  отклонён своим gate из-за `29 < 30` trades. Нужна PIT/parity validation.
- Direct Alpaca GET-only: LIVE/ACTIVE `$487.38`, ABBV/SCHW, broker stop coverage
  `2/2`; SCHW stop ratcheted to `106.13` from entry `101.552`.
- Inplay loop теперь single-instance; один research-only collector, N0.
- XAU public Dukascopy backfill `2021-01-01..2025-10-01` активен; holdout не
  читается, disk guard `20 GiB`. Результат только после SHA/validation receipt.
- Web password reset helper установлен/hash-verified; server config обновлён,
  enabled admin/TOTP/hash сохранены, mode `0600`. Остался login smoke новым
  паролем. Chart TF/provenance исправлены локально; live monolith не рестартовал
  и не деплоился.
- Focused tests: `58 passed`; functional commits `2a7ea8c`, `757049c`,
  `f0e9cae`. Полный отчёт:
  `reports/PROJECT_STATE_AND_ACCELERATION_2026_08_13.md`.
- Post-push live: direct broker positions `0`, both services active, heartbeat
  age `6.5s`, `trade_on=true`, `dry_run=false`, `open_trades=0`, WS guard `0`.

### Следующие 72 часа

1. Закончить XAU data receipt; заморозить и прогнать session breakout/retest V3.
2. Провести независимую validation ATT1 pivot-sequence, без live-enforcement.
3. Закрыть Alpaca PIT/sector/corporate-action/15m-manager parity; только затем
   решать, переносить ли stop anchor на actual fill.
4. Продолжать prospective Inplay и L2/tape; не считать отсутствие сигнала
   остановкой процесса.
5. Один fixed legacy batch: sweep-reclaim, sloped-retest, L2-density.
6. Собрать chart/password изменения в staged server bundle только в отдельном
   flat-gated release; монолитный copy/restart запрещён.

## Latest recovery update — 2026-08-13 05:45 UTC

- Direct VPS truth: `bybot.service active/running`, fresh heartbeat,
  `trade_on=true`, `dry_run=false`, `open_trades=0`, `ws_guard_active=0`,
  broker API `retCode=0`, `open_position_count=0`. Единственная money-authority
  — ATT1 short `risk_mult=0.10`; остальные включённые стратегии имеют zero-risk.
- Локальный Bybit checker использовал истёкший ключ (`33004`) и раньше печатал
  ложнопохожее `open_position_count=0`. Теперь API error выдаёт
  `broker_state=NOT_CONFIRMED`, count/positions=`null`; тесты `2 PASS`.
- Research station после reload использует canonical XSEC receipt: `6/6
  healthy`. Inplay ETH prospective по-прежнему `N=0`; историческая частота
  `435 / 556 дней = 0.782 сигнала/день`, оценка N30 `5.5 недели` с диапазоном
  примерно `3.8–7.7` недели.
- Funding spot/perp V2: exact-mapped `74`, quarantined `16`; при spot
  `10+10 bps` и perp `5.5+5.5 bps` selection edge исторически остаётся
  `+2.03%`, но gross two-leg capital CAGR только `3.77%` base / `2.55%`
  stress, половины `4.03%` и `0.15%`. Diagnostic only; forward N4 отрицателен.
- Alpaca clean-962 proxy: `+11.14%` annualized base, `+10.41%` stress, DD около
  `23.8%`, 40 сделок, `8/25` красных месяцев. Это не exact replay: `93%`
  выбранных слотов не получили sector classification, а gap/stop geometry дала
  хвост потерь до `-22..-28%`. Следующий gate — sector/PIT completion и
  entry-relative stop/gap challenger.
- RMR1 SOL: положительный pocket не объяснён режимом; первая половина
  `+0.525R`, вторая `+0.057R`, ни один режим не держится в обеих половинах.
- Inplay BTC portability rejected: 437 сигналов, ни один из 30 фиксированных
  вариантов не положителен в >=3/4 окон. BTC требует отдельной long-механики.
- XAU intraday-flat V2: session breakout/retest `+3.92R` base / `+3.01R`
  stress, `3/4` positive folds, но только 13 сделок; trend pullback и
  round-level sweep отрицательны. Кандидат остаётся research/shadow only.
- Публичные локальные коллекторы свежие: BTC/ETH L2+tape, ONDO L2+tape,
  micro-tape и alt24 density (`157,181` observations); disk guard green,
  свободно `94 GiB`. Резервный VPS collector корректно остановлен собственным
  cap `2 GiB`; guard не переопределять, локальный поток продолжает сбор.
- AI truth и idea intake усилены: stale heartbeat больше не превращается в
  «бот offline»; внешние источники считаются untrusted, идеи допускаются только
  как proposal с mechanism/data/costs/fixed test/death criterion, без ключей,
  запуска и capital authority.

Полный отчёт и ускоренный план:
`reports/PROJECT_STATE_AND_ACCELERATION_2026_08_13.md`.

## Latest recovery update — 2026-08-12 11:55 UTC

### Решение одним абзацем

Проект ещё не стал диверсифицированной денежной станцией: в crypto есть одна
tiny-canary ATT1, Alpaca остаётся защищённым SAFE_HOLD, остальные ноги только
в research/shadow. Но за сессию закрыты три системных риска: LIVE/PAPER truth
Alpaca, откат raised stop между сессиями и непрослеживаемые кандидаты из грязной
рабочей области. Одновременно завершены два больших набора данных и честно
отклонены TPB1/RMR1. Следующий денежный шанс — не «ещё один случайный модуль», а
три параллельные дорожки: Inplay prospective, funding/carry economics и exact
Alpaca replay на чистом subset.

### Новая фактическая база

- Git functional commits запушены в `codex/dynamic-symbol-filters`:
  `206c6cf` (Alpaca LIVE truth + persistent GTC stops) и `df51ed6`
  (passported dirty-candidate batch + wide public-data runner).
- Direct Alpaca GET-only: LIVE account `ACTIVE`, equity `$485.91`, cash
  `$391.27`, ABBV/SCHW, broker stop coverage `2/2`.
- SCHW raised stop `105.32` был `DAY`, затем rearm восстановил `96.47`.
  Локальный контракт исправлен на `GTC`; текущий ордер и live-сервер не
  изменялись. Нужен отдельный protection-only deploy receipt.
- ATT1 post-release clean cohort: `1/20` закрытая сделка на последней прямой
  сверке. Risk остаётся `0.10`; ориентир решения `0.10 → 0.25` при прежнем
  темпе — конец сентября, только если выполнены все cohort/parity gates.
- Alpaca archive: `1000/1000`, download failures `0`; full-pool validator
  `FAIL_CLOSED` из-за `24` ticker-identity conflicts и `14` пустых историй.
  Clean research subset `962`, quarantined `38`, promotion authority `false`.
- RMR1 wide major8: `733` сделки, PF `0.789`, `-0.209R/сделку` при `16 bps`;
  при `8 bps` PF `0.892`, `-0.106R/сделку`. TPB1 ETH: PF `0.828`,
  `-0.046R/сделку`. Обе формулировки не идут в shadow.
- Inplay prospective ETH остаётся `N=0`; дата N30 неизвестна до измерения
  фактической частоты. Funding dynamic/frozen: по `3` открытых shadow trials,
  закрытых `0`. Это процесс, не edge.
- Dirty worktree не чистится массово: осталось `166` code candidates, из них
  `6` test-backed, `117` evidence-backed/reproduction, `16` referenced-review,
  `27` quarantine. Следующая пачка — 5–10 файлов.

### Условные сроки, не обещания доходности

| Контур | Следующий доказательный результат | Возможный money-gate |
|---|---|---|
| ATT1 | exact lifecycle parity + clean N20 | конец сентября 2026 при прежней частоте и положительной cohort |
| Inplay ETH | первая недельная cadence card и измеренная signal rate | сентябрь–октябрь, только если N/edge/stress проходят shadow gates |
| Funding/carry | closed forward trials + spot/perp exact economics | 2–6 недель до содержательного shadow verdict; money позже |
| Alpaca | clean-subset base/stress exact live-contract replay | tiny new-selection canary не раньше начала сентября при PASS; scale после 1–2 monthly cycles |
| FX/CFD | XAUUSD data/cost/swap/news contract и annual replay | demo/shadow 3–6 недель; tiny money не раньше октября при PASS |

### Приоритет на следующие 72 часа

1. Подготовить protection-only Alpaca bundle с `GTC`, server-Python smoke и
   точным diff; не менять текущие ордера без отдельного owner-approved окна.
2. Построить exact Alpaca replay, который принимает только clean subset `962`,
   использует next-open, live weights/exposure, shared stop/trail, daily MTM и
   base/stress costs. Selection bias оставить отдельным blocker, не замазывать.
3. Не тюнить Inplay; раз в 7 дней выпускать forward cadence card. Funding
   закрыть до net markout и exact spot/perp mapping.
4. Следующий dirty batch: strategy adapter / sweep-reclaim / backtest auditor;
   каждый кандидат проходит passport → reproduction → accept/reject.
5. Key rotation: Alpaca — в ближайшей авторизованной сессии (целевой SLA
   24–48 часов), Massive — следом. До признаков компрометации это P0 hygiene,
   но не причина аварийно отключать защищённые позиции.

### Шкала пути к цели (управленческая оценка)

Это не статистическая метрика готовности, а WIP-карта: operational truth
`~75%`, research integrity `~65%`, Alpaca money contour `~40%`, crypto
portfolio `~25%`, FX/CFD `~15%`, AI-assisted autonomy `~25%`. Минимально
работоспособная станция по owner-определению (3–4 crypto legs + полноценная
Alpaca) находится примерно на `40–45%`; полный автономный multi-market vision —
на `20–25%`. Главный прогресс сейчас — скорость отбраковки ложных результатов,
а не число включённых стратегий.

## Latest reprioritization — 2026-08-11 17:08 UTC

1. **ATT1:** сохранять tiny canary `0.10`; считать только сделки после release
   `475745108b5e`. Перед повышением риска: exact parity + N20 clean + cohort
   gates. Сегодняшние DOT/ADA положительны, но contaminated.
2. **Second crypto leg:** построить fixed `inplay_breakout ETH 0.75/24h`
   risk-zero collector. Не включать в monolith до отдельного shadow contract;
   maker-entry тестировать как challenger, не default.
3. **Neutral crypto:** продолжать XSEC forward shadow; funding dynamic/frozen
   начали новую clean epoch после карантина перекрывающихся legacy trials.
4. **Research integrity:** reserved holdout больше не раскрывать; любой explicit
   symbol mismatch и timeout fail-close; каждое число несет cutoff/passport.
5. **BTC-state:** один prereg interaction test для support bounce/strong-up;
   не превращать descriptive table в live switch.
6. **Alpaca:** SAFE_HOLD ABBV/SCHW сохранять; закончить live-contract backtest
   parity перед новыми среднесрочными деньгами. PAPER intraday отделять в TG.
7. **FX/CFD:** четыре terminal fail не перезапускать; следующий gate — XAUUSD
   contract/cost validation. Index CFD остается blocked-data.
8. **AI/research:** пять supervisor screens продолжают proposal/risk-zero
   работу. AI не имеет secrets/order/risk authority; тяжелый новый run только
   после освобождения WIP и с preregistration.

Очередь `configs/research/strategy_promotion_queue_20260730.json` снова валидна:
`13 crypto`, `6 FX/CFD`, `active=4/max=5`, `capital_authorized=false`.

## Update 2026-08-11 — что изменилось и что делать дальше

### Завершено сейчас

1. **ATT1 execution release:** atomic revision `475745108b5e` находится в live,
   broker flat, service/heartbeat живы. Clean N20 начинается только после этого
   receipt; DOT/ADA положительны, но contaminated.
2. **Автономная матрица:** terminal `48/48`; ни одного money-кандидата.
   Reserved holdout не читался.
3. **Лаборатория отрицательных сделок:** первая reproducible версия готова.
   Она отличает negative gross edge от cost-killed edge, строит exit-path и
   market/context buckets, а AI получает только proposal packet.
4. **Скрытый universe contract:** стандартная ручка добавлена в
   `inplay_retest_v3`, preflight теперь обязан доказать различие universe.
5. **XSEC shadow integrity:** maturity, entry attribution и anomaly gate
   добавлены без broker/order authority.

### Новые измеренные границы

- **ATT1 major-only:** остается единственной money-canary, но еще не доказана
  clean live cohort. Не экстраполировать на весь рынок.
- **ATT1 wide:** `823` trades, gross `+19.34R`, costs `48.11R`, net `-28.77R`,
  `t=-0.99`; отклонена как широкий контур.
- **Squeeze long 2023H2:** `620` trades, gross `-40.37R`, costs `90.97R`, net
  `-131.34R`, `t=-6.74`; отклонена в текущем виде. Причина не сводится к fees.
- **XSEC:** `SHADOW`, zero risk; forward evidence еще не накоплена.
- **Alpaca:** live SAFE_HOLD/protective-exit contour, но стратегия selection
  остается diagnostic, не доказанным источником дохода.

### Следующие P0/P1 — без календарного простоя

1. **Live truth loop:** на каждом цикле reconcile broker ↔ runner ↔ owner ↔
   accounting; конфликт символа fail-closes только новые добавки, protection
   продолжает работать.
2. **Clean ATT1:** собирать N20, одновременно завершить exact
   backtest↔live parity для rounding/fees/partial fills. Gate риска остается
   `20 clean closed`, `netR>=+2`, `PF>=1.20`, drawdown `<=5R`, zero unresolved
   execution conflicts; ориентир при прежней частоте — конец сентября.
3. **Second-leg lane A — XSEC:** держать V3 в shadow, ежедневно валидировать
   maturity/markout attribution/anomalies. До forward sample капитал нулевой.
4. **Second-leg lane B — retest/level reaction:** провести differentiating
   wide-universe smoke после освобождения compute slot; затем time/symbol OOS.
   Для возвратных сетапов maker моделировать отдельно; импульсным breakout
   maker не навязывать из-за adverse selection.
5. **Negative lab experiments:** preregister три отдельных falsification-теста:
   delayed/confirmed entry для `entry_failed_fast`; state-aware entry для
   `stopped_no_reversal_yet`; exit redesign для `gave_back_profit`. Не смешивать
   три изменения в одном варианте и не читать reserved holdout.
6. **Data lane:** после освобождения слота расширить public funding history и
   получить PIT-aware equities daily universe. Текущие 8-symbol funding data и
   yfinance/survivor equity data недостаточны для финального вердикта.
7. **Elder:** построить один contract manifest V2/V3 и replay на одинаковом
   universe/data/cost/exits; обе версии остаются risk zero до результата.
8. **AI/graph analysis:** AI имеет read-only timestamped snapshots, OHLC cards,
   regime probabilities и proposal-only findings. Он не включает модули, не
   меняет risk и не отправляет ордера. Visual pattern claim обязан иметь
   machine reproduction и preregistered test.

### Что не считать прогрессом

- `141 symbols downloaded` — это coverage, не edge и не live activation.
- `85 modules indexed` — inventory coverage, не доказанная полезность.
- старый красивый backtest без exact universe/weights/exits/cost contract;
- один положительный shadow markout или две contaminated live сделки;
- AI-объяснение причины без воспроизводимого finding и source receipt.

## Emergency execution update — 18:55 UTC

ATT1 временно не может начать clean cohort: DOT fill исполнился уже за TP1 и
расширил stop risk в `2.64x`. Исправление stale/current/fill contract готово и
прошло focused tests, но монолит не перезапускается при открытой позиции.
Затем старый live-код допустил ADA fill с расширением риска `1.56x`. Поэтому
первый P0 gate теперь не пассивное ожидание, а горячая остановка только новых
ATT1-входов командой `/strategy_pause att1 execution_fix_release`. Сопровождение
и broker stops текущих позиций сохраняются. После broker flat — три прямые
проверки flat и atomic release; resume только после полной сверки release.

Обе incident-сделки и все события до release receipt исключаются из N20. При
наблюдаемом темпе ATT1 `9 сделок / 21 день` двадцать чистых сделок займут около
`47 дней` после release, то есть реалистичный decision window для
`risk 0.10 -> 0.25` — конец сентября 2026, а не 2–3 недели. Ускорение возможно
только если фактическая чистая частота вырастет примерно до одной сделки в день.

Gate `0.10 -> 0.25`:

1. exact release/hash/service/broker receipt и ни одного execution incident;
2. golden backtest-live size/entry/stop/TP parity;
3. 20 clean closed trades одной post-fix cohort, без contamination;
4. cohort `netR >= +2`, `PF(R) >= 1.20`, peak-to-trough `<= 5R`;
5. broker ↔ runner ↔ owner ↔ accounting reconciliation без unresolved conflict.

## Six-day autonomous research lane — RUNNING

- downloader: top-150 current surviving Bybit contracts, 5m from 2023;
- explicit limitation: survivor/turnover-biased discovery universe, promotion
  forbidden;
- queue: ATT1 current/shallow, horizontal break long/short, support reclaim
  strict/relaxed, squeeze long/short;
- design: 3 chronological pre-2025 windows × base/stress costs = 48 cases;
- every varied strategy handle passes executable preflight;
- every run uses next-open execution, coverage gate, R metrics and audit;
- 2025-10..2026-06 holdout is code-blocked from reading;
- host idle sleep блокируется ограниченным шестью сутками `caffeinate` assertion;
  это не защита от power loss, reboot или network outage;
- status: `reports/research/six_day_crypto_pipeline_20260810/status.json`.

This lane searches a second leg and failure mechanisms. It cannot promote a
strategy, change risk or touch a broker.

Визуальная архитектура и promotion flow:
`reports/CODEX_PROJECT_VISUAL_MAP_2026_08_10.md`.

## Решение после сравнения планов

План Клода правильно начинает с экономики ноги: издержек, качества входа,
избирательности, карточек эджа и поиска рабочей long-ноги. Антикризисный план
Codex правильно ставит раньше них операционную истину: broker truth, безопасный
release, reconciliation, чистые когорты и независимую проверку. Итоговый порядок:

1. не потерять капитал и доказать, что live исполняет именно тот код;
2. сделать измерения воспроизводимыми и независимыми;
3. улучшать экономику каждой ноги одним изменением за эксперимент;
4. только затем давать капитал нескольким независимым контурам;
5. отображать ту же истину в Web, Telegram и AI-ассистенте.

Цель не «запустить побольше стратегий», а получить несколько независимых
контуров, в каждом из которых есть минимум две отдельно доказанные ноги,
понятные издержки, ограничения риска и механизм автоматического отключения.

## Нулевая шкала статусов

- `PROCESS_OK`: процесс жив и выпускает свежие receipts.
- `MEASURED`: есть корректный результат на заявленном окне.
- `REPRODUCED`: результат повторен независимым способом или движком.
- `SHADOW`: работает на текущем рынке без права ордеров.
- `CANARY`: имеет явно ограниченное право на минимальный риск.
- `MONEY`: прошел promotion gates и имеет капитал.

`PROCESS_OK` никогда не подменяет `MONEY`, а положительный shadow PnL не
считается заработком счета.

## P0. Безопасность и операционная истина — сейчас

### P0.1 RUNNER TP1 dependency bundle — DONE

- bundle собран из Git revision `c5eba1ccb244584bb432dd902d22599290fca900`;
- архив SHA256 `5c7b4be781aed95b5df9f9f2a38b5912b70a1d523ade7896806b329490702e46`;
- server-Python import и bounded no-order startup smoke прошли вне live;
- direct Bybit flat подтвержден до остановки, после остановки и после старта;
- шесть файлов заменены атомарно, пять отсутствовавших зависимостей добавлены;
- live manifest `6/6 PASS`, service и heartbeat восстановлены;
- money authority не расширена: ATT1 short-only, `risk_mult=0.10`.

Следующий контроль: периодически сверять live manifest/deployed receipt, service,
heartbeat и прямого брокера; Git-коммит сам по себе не считать деплоем.

### P0.2 Retest3 research-integrity — REPAIRED, RESULT NOT PROVEN

Старый ladder был no-op: экспортировал неиспользуемую переменную. Скрипт теперь
передает реальную ручку `IRV3_STOP_BUFFER_ATR`, выполняет preflight четырех
разных конфигураций и запрещает интерпретацию, если stop distributions не
различаются. Старые результаты изолированы новыми тегами.

Дешевый 90d smoke честно заблокирован: две конфигурации дали ноль сделок, две —
по одной. Это доказательство работы fail-close, но не результат стратегии.
Следующее действие — differentiating smoke на достаточном окне после
освобождения одного из пяти исследовательских слотов.

### P0.3 Alpaca protective exits — LIVE RECEIPT PASS, MONITORING REQUIRED

На сервере обнаружены действующие protective-only authority и cron каждые 15
минут. Последовательно исправлены два broker-contract дефекта: fractional
`qty` больше не отправляется в PATCH, а stop-price округляется вниз на
разрешенную Alpaca сетку (2 decimals при цене >= `$1`, 4 ниже `$1`). Staged
server-Python smoke и 26 focused tests прошли.

2026-08-10 14:44 UTC Alpaca приняла replace SCHW `96.47 -> 105.03`, точный
защищенный qty `0.563776973`, статус нового ордера `new`. Прямое broker-read:
equity `$485.87`, cash `$391.27`, ABBV/SCHW, stop coverage `2/2`; SCHW stop
находится примерно на `+3.42%` к entry до gap/slippage. ABBV пока не достигла
порога arm и сохраняет stop `235.17`. Новых покупок, ротаций и market-close не
было; SAFE_HOLD сохраняется.

Этот старый вывод теперь уточнён: зависимость от `DAY` действительно привела к
откату SCHW `105.32 → 96.47`. Локальный контракт standalone stop исправлен на
`GTC` в commit `206c6cf`, но server/live ещё не обновлён и текущий broker stop
остаётся `DAY`; поэтому риск сохраняется до отдельного deploy receipt.
Stop/trailing в любом случае не устраняет overnight gap risk.
Автоматический cron 14:45 UTC уже перечитал новый stop `105.03` и корректно
вернул `hold/no_material_stop_raise` без повторного PATCH. Следующие проверки:
rearm на следующей сессии, freshness alert и восстановление HWM после рестарта.
Для будущих входов отдельно сравнить fractional DAY с whole-share
GTC/native-trailing контрактом.

Routine PAPER HOLD/dry-run Telegram отключен по умолчанию в paper-launcher;
paper broker receipts и логи сохранены. Отдельные live/actionable сообщения не
отключались.

### P0.4 Грязная рабочая область — INVENTORIED, TRIAGE OPEN

Read-only inventory на HEAD `c5eba1c`: `1,138` paths (`27` tracked changes,
`1,111` untracked). Крупные классы: `429` document/metadata, `344` reports,
`100` archive/backup, `61` manual-code candidates, `29` runtime/log и `14`
secret/env-looking names. Контент секретов не печатался. Подробный порядок —
`reports/WORKTREE_CLEANUP_PLAN_2026_08_10.md`.

До owner/reference/test triage массово не удалять и не архивировать. Работа
Клода и параллельные research artifacts считаются чужими до доказательства
обратного. Первый безопасный выигрыш — вынести bulk data/runtime и backups из
code checkout по manifest, затем разбирать 61 code candidate малыми batches.

## P1. Control plane — неделя 1–2

### P1.1 Broker ↔ runner ↔ owner ↔ accounting reconciliation — PURE CORE READY

`bot/position_reconciliation.py` теперь строит единый deterministic receipt из
четырех position views, проверяет freshness, broker stop, qty/side/strategy,
missing и duplicate/hedged rows. Stale/malformed source означает глобальный
fail-close новых входов; локальный конфликт блокирует только затронутый символ,
не мешая защитному TP/SL и runner management. Совместный focused suite:
`18 passed`.

Открытый gate: материализовать четыре runtime adapters, durable receipt и
подключить `entry_allowed()` ко всем реальным submit paths отдельным релизом.
До этого pure core — проверенный контракт, но не live protection. Incident
должен попадать в очередь `finding -> reproduction -> patch -> tests -> deploy`.

### P1.2 Backtest ↔ live sizing parity — CORE WIRED, EXCHANGE LAYER OPEN

Live stop-percent sizing теперь проходит через тот же pure
`bot/risk_sizing_contract.py`, что и backtest fixed-R sizing. Golden fixtures
доказывают одинаковые pre-round notional и effective risk для uncapped,
notional-capped и reject cases, включая геометрию DOT. Остается проверить
exchange qty-step/min-qty rounding, fees, partial fills и запрет legacy-DCA.
Любое расхождение — fail-fast, не предупреждение.

### P1.3 Clean cohort registry

Каждая правка signal/sizing/execution/accounting начинает новую когорту с code
SHA, config hash, data version и timestamp. ATT1 promotion использует только
чистые post-fix сделки; старые contaminated события сохраняются как evidence.

### P1.4 Maker execution shadow и slope shadow

- ATT1/BREAKDOWN: frozen post-only grid, fill/nonfill markout, opportunity cost,
  adverse selection, symbol/time folds;
- ATT1 slope `0.7`: только shadow, поскольку порог выбран на просмотренном окне;
- не включать maker в деньги по одному улучшению комиссии.

### P1.5 `sloped_break_retest_v1` — UNIT FIX DONE, REACHABILITY OPEN

Повторная проверка показала, что пункт старого roadmap уже частично устарел:
`_retest_expiry_ms()` переводит секунды в миллисекунды, а два contract tests
проходят; последняя история файла указывает на commit `2d04e3f`. Повторно чинить
код не нужно. Остались reachability proof, bounded smoke, geometry receipt и
shadow gate; старые нулевые результаты до unit fix не использовать как приговор.

### P1.6 Alpaca selection/exit exact parity

Текущий live — SAFE_HOLD старых ABBV/SCHW, а adaptive shadow выбирает
SNOW/BAC/PANW/CRWD. Это разные cohort и не доказательство работы одной стратегии.
Старые красивые v38 цифры не совпадали с intended live contract по universe,
70% exposure, weighting, exit и daily MTM. Новый preregistered diagnostic
`alpaca_honest_diagnostic_v1_20260810` уже исправляет next-open, единый cash
ledger, fractional qty, hard weight cap, per-fill costs, retained positions,
deployable fractional stop/ratchet proxy и daily drawdown.

Первый результат после независимой проверки арифметических invariants:

| окно / arm | 5 bps/side | 10 bps/side | daily DD stress | статус |
|---|---:|---:|---:|---|
| 2022 v38 successor + SPY200 | `-2.75%` | `-2.89%` | `4.00%` | bear edge не доказан |
| 2024-05..2026-04 v38 successor + SPY200 | `+31.88%` | `+30.16%` | `7.84%` | promising diagnostic |
| 2022 Adaptive V1 + SPY200 | `-5.38%` | `-5.63%` | `6.58%` | bear edge не доказан |
| 2024-05..2026-04 Adaptive V1 + SPY200 | `+20.66%` | `+18.75%` | `4.94%` | lower-DD diagnostic |

Старое v38 `+50.77% / DD 2.28%` больше не является рабочей оценкой: новый
cash-aware replay дает ниже доход и выше честную дневную просадку. Средняя
реальная экспозиция v38 получилась лишь `26.6%`, потому что cash, hard cap,
защитные выходы и reentry blocks больше не скрываются нормализацией до 100%.
В live bridge найден и исправлен тот же sizing-defect: прежний cap 60% затем
повторно нормализовался и мог стать 100%. Теперь остаток остается cash; текущий
SAFE_HOLD не затронут, поскольку new entries выключены. Focused suite `34 PASS`.

Validator: `16/16` result invariants, `6/6` source pins и `8/8` cost-stress
monotonicity PASS. Data quality всё ещё `NEEDS_REVISION`: universe survivor-only,
XNYS ledger не authoritative, corporate actions/delistings и broker cost bundle
не pinned, daily proxy не воспроизводит 15-minute HWM path; XYZ имеет лишь
`63.9%` покрытия двухлетнего окна из-за своей более короткой истории. Forward
с 2026-08-03 не читался. Поэтому promotion остается `BLOCKED_FAIL_CLOSED` до
PIT/input bundle, второго engine и трех sealed monthly forward cycles.

## P2. Исследовательский завод — неделя 2–6

### P2.1 Карточка эджа для каждой ноги

Единый `strategy_edge_report`: вход signal/next-open/limit; выход MFE/MAE и
отданный ход; отбор по измеримым признакам; gross edge, costs, net edge,
uncertainty, data/PIT coverage и failure phenotypes. Один эксперимент меняет
только один рычаг.

Порядок: liveness -> ablation -> edge card -> one-change experiment ->
preregistered fold -> independent replay -> shadow -> canary.

### P2.2 Независимый replay

VectorBT — быстрый prefilter, causal harness — основной исследовательский
движок, LEAN или второй независимо реализованный engine — сверка ключевых
кандидатов. Два движка не должны разделять одну и ту же реализацию signal/exit.

### P2.3 Анализ отрицательных сделок по фенотипам

Кластеризовать по regime, slope, geometry, liquidity/spread, fill path,
markout, symbol age, volatility, funding/basis и времени. LLM может назвать
кластер и предложить тест, но не имеет права объявлять причинность или promotion.

### P2.4 Данные и честные окна

150–200 perpetual symbols с listing dates, 5m history с 2023-01 и funding
history в parquet. Любой тест хранит data hash, coverage, exclusions и PIT
ограничения. Holdout squeeze `2025-10..2026-06` не расходовать на другие ноги.

### P2.5 Long family и slot arbitration

Приоритет поиска: `inplay -> breakout -> continuation -> retest`, потому что у
книги нет доказанной long-ноги. `strategy_priority_router` сначала проверяется
в shadow на opportunity cost; не подключать к live только по старому aggregate.

### P2.6 Load-aware night queue

Пять постоянных research loops остаются `5 healthy / 0 degraded`. Load-aware
очередь `research_backlog_guard_20260810` завершила два risk-zero fixed probes,
без broker calls и live authority. USDJPY H1 полностью заблокирован cost gate:
`feeR=0.515 > 0.35`, сделок не симулировали. На H4 лучшие диагностические
строки: EURJPY trend pullback `+3.366R` (13 сделок, 2/4 positive folds), GBPUSD
trend pullback `+1.732R` (9, 3/4), USDJPY breakout/retest `+1.321R` (10, 2/4),
EURUSD breakout/retest `+1.221R` (4, 2/4). Все `preflight=false`: это очередь
для prereg reproduction с fresh bid/ask, swap и news exclusions, не promotion.

## P3. Несколько контуров дохода — неделя 3–12+

| Контур | Сейчас | Следующий falsifiable gate | Условие капитала |
|---|---|---|---|
| Crypto directional | ATT1 `CANARY 0.10`; остальные zero-risk | clean N20/N30, maker/slope shadow, size parity | по ступеням `0.10 -> 0.25 -> 0.50`, только после gates |
| Crypto long/retest | research-integrity repaired, edge не доказан | liveness + geometry + independent folds | отдельная доказанная нога, затем shadow/canary |
| Funding/basis | два `PROCESS_OK` shadow; capital false | concentration, adverse selection, realistic costs, frozen N20–30 | только reproduced net edge |
| XSEC market-neutral | `PROCESS_OK`, risk zero | outlier-resistant/median analysis, costs, independent replay | только stable folds и broker-ready controls |
| Alpaca equities | SAFE_HOLD + verified daily diagnostic: v38 recent `+30.16%`, 2022 `-2.89%` stress | PIT/XNYS/corp-actions/cost bundle, second engine, sealed Aug-Nov forward | текущий cap не расширять; SAFE_HOLD не ротировать по proxy |
| FX/CFD medium-term | USDJPY H1 rejected by cost gate; H4 has four thin diagnostic leads, all preflight false | prereg H4 reproduction, fresh bid/ask+swap/news, chronological OOS | сначала shadow/demo; money только после stable folds и broker-cost parity |
| Arbitrage/volatility | inventory/research only | executable quotes, transfer/borrow/funding risks, kill switches | отдельный canary после end-to-end shadow |

Желаемое состояние: в каждом денежном контуре минимум две независимо
проверенные стратегии/ноги. Но недоказанная нога не является диверсификацией:
она отнимает слоты и добавляет неизвестный риск.

## P4. Web, Telegram и AI — параллельно после P1 truth model

Один источник состояния для Web/TG/assistant: broker positions/equity,
protected exposure, money sleeves, strategy authority, deployed revision,
heartbeat freshness, reconciliation conflicts и research-only статус.

AI/Ollama индексирует весь несекретный код по path/SHA/chunk, извлекает source
и свежие receipts, отвечает `NOT_CONFIRMED` при stale/conflict. AI предлагает
finding и experiment, но не получает credentials, право ордера или изменение
риска. Web/TG ручные действия требуют подтверждения и immutable receipt.

## Метрики движения

1. число ног с reproduced net edge на независимом окне;
2. число clean live lifecycles с broker/runner/accounting parity;
3. защищенная экспозиция и число reconciliation conflicts;
4. maker fill rate, nonfill opportunity cost и adverse selection;
5. число findings, прошедших reproduction, а не число сырых предупреждений;
6. число денежных контуров с отдельной authority и kill switch.

Сроки — окна получения доказательств, не обещание доходности.

## Recovery session — 2026-08-12 07:50–08:15 UTC

### Live truth и последняя сделка

Direct Bybit read после закрытия подтвердил flat и equity
`1022.06789312 USDT`. Последний DOTUSDT short: average entry `0.7944`, average
exit `0.78884968`, qty `75.9`, broker closed PnL `+0.35517723 USDT`. Позиция
сначала получила breakeven, затем биржевой trailing stop; ручного закрытия,
submit/cancel или изменения риска в этой сессии не было. Текущая authority не
расширялась: ATT1 short-only `risk_mult=0.10`, effective risk около `0.044%`
equity на сделку.

Actual DOT order теперь имеет golden sizing receipt:
`reports/evidence/ATT1_DOT_ORDER_SIZE_PARITY_20260812.json`. Shared fixed-R
contract дал тот же pre-round notional и после qty-step `0.1` ровно тот же
submitted qty `75.9`; `5/5 PASS`. Для будущих live events добавлена non-secret
телеметрия `sizing_contract`, но monolith с этой телеметрией не деплоился.

### Что из работы Claude принято, а что отозвано

- MPL — идея принята, но исходный holdout-контракт был неисполняемым и
  неоднозначным. Он пересобран: exact `[2025-10-01, 2026-07-01)`, next-15m-open,
  no-overlap, causal liquidity/slippage, time-matched random control, exact 62
  symbols, input integrity, write-once manifest/result. Изолированный bundle
  готов, focused tests `6 PASS`, immutable local commit `2811242`. Холдаут не
  вскрыт: push этого commit заблокирован security review до явного разрешения
  владельца на конкретный Git remote/branch.
- Inplay `+0.2352R` отозван: `research_lab/path_sim.py` видел close сигнального
  5m бара и входил по тому же close. Исправлено на next-open и conservative
  stop-first; `2 PASS`. До causal pre-holdout replay shadow не запускать.
- XSEC `Sharpe 0.65` — сильный research lead, не `ГОТОВО К ДЕНЬГАМ`: clean
  symbol-holdout имеет слабый `t=0.60`, funding cashflows ещё не включены, а
  closed-contract PIT universe не восстановлен. Modern keys в старом JSON
  quarantined; сценарий использует только pre-holdout search.
- Два заявленных live-багa про runtime env и отсутствие try/except не
  воспроизведены: open `TradeState` хранит stop/runner fields, async signal и
  runner pulse уже имеют exception boundaries. Код live по этим утверждениям
  не менялся.

### Данные и лаборатория

- Bybit funding/listing archive: `137/137`, `413,356` observations, `0` failed,
  public/read-only. Integrity PASS, но PIT `NOT_READY`: provider inventory
  содержит `936 Closed`, тогда как OHLC/funding set выбран из текущих 137.
- Alpaca/Massive PIT candidate pool: `1000` symbols, resumable, GET-only,
  текущий прогресс сохраняется в
  `research_lab/data/alpaca_pit_daily_v1/status.json`. Добавлен независимый
  validator hashes/timestamps/delist dates и membership intervals. Он может
  доказать PIT только внутри выбранного пула и fail-close запрещает называть
  current-liquidity selection полным историческим PIT universe.
- Bybit L2: BTC/ETH, ONDO, public trades и новый density denominator по `24`
  альтам собираются непрерывно. На 08:15 UTC alt24 имел `4,999` observations,
  `5.3 MB`, public-only, order-capability false, storage guards green.
- Audit registry loop закрыт полями confirmation evidence/resolution note и
  fail-closed validator: `298` total, `211` current, `3` actionable, `0`
  lifecycle violations.
- Шестидневный wide rerun больше нельзя называть завершённым успешным:
  текущий status `48/48`, но `24` cases invalid после исправления universe
  contract. Ранее terminal `complete` относится к старому узкому контракту.

### $1,000 mechanical matrix — не прогноз

Canonical artifact:
`reports/analytics/trading_recovery_20260812/report.html` и machine-readable
`artifact.json`.

| sleeve | mechanical evidence | допустимость |
|---|---:|---|
| ATT1 current tiny canary | `$1,008.86` | только перевод старого narrow anchor при 0.044% risk; не forecast |
| XSEC | no estimate | старые 7.5–9.5% отозваны: same-close execution; funding/PIT unresolved |
| Alpaca monthly | `$971–1,141` | bear/recent survivor proxies; SAFE_HOLD cap не расширять |
| FX H4 basket | `$1,007–1,031` | 1–7 trades/variant, all preflight false; не использовать для allocation |
| MPL/inplay | no estimate | executable accepted replay отсутствует |

Эти строки нельзя складывать как обещанную portfolio return. Новый money sleeve
не продвинут; продвижение этой сессии — достоверность измерений, данные и
готовые gates.

### Следующий порядок

1. Получить явное разрешение push `2811242` в указанный remote/branch и только
   затем один раз вскрыть MPL V3 holdout.
2. Дождаться `1000/1000` Alpaca, запустить независимый validator и repaired
   monthly replay; текущий сбор займёт часы, аналитика 1–2 рабочих дня.
3. Построить funding-adjusted XSEC и closed-contract PIT universe; затем
   prospective shadow, а не money.
4. Выполнить causal pre-holdout replay inplay; shadow только если переживёт.
5. Продолжать ATT1 clean cohort: при наблюдаемой частоте N20 ориентировочно
   около 47 календарных дней после release, не искусственно ускорять риском.

Дополнительный causal-аудит после записи матрицы нашёл в XSEC тот же дефект,
что в inplay: веса рассчитывались по завершённому daily close и доходность
начиналась с цены этого же close. Поэтому сохранённые `7.5–9.5%` больше не
являются даже research-сценарием. Добавлен pure contract
`research_lab/xsec_causal_contract.py`: next-day-open entry, open-to-open hold,
фактические crossed funding cashflows со знаком `-weight*rate`, fail-close при
отсутствующей исполнимой цене. Отдельный физический pre-holdout funding archive
до `2025-10-01` запущен public-only; основной sealed outcome не читается.

## Continuity receipt — 2026-08-12 08:29–08:38 UTC

- Пять supervisor jobs подтверждены текущим status как `5 healthy / 0
  degraded`: Alpaca adaptive shadow, XSEC shadow, funding dynamic/frozen и
  project audit. Три локальных public Bybit tape-контура свежие и продолжают
  запись: BTC/ETH `2.19 GB`, ONDO `849 MB`, micro-trades `368 MB`; у всех
  `public_only=true`, `authentication=false`, `order_capability=false`,
  disk guards green. Alt24 density также жив: `8,092` observations.
- Изолированный `/root/research-l2` на сервере подтверждён read-only:
  heartbeat `collecting`, lag `1 ms`, BTC/ETH snapshot synchronized,
  `921.9 MB` tape при cap `2 GiB`, свободно `7.2 GB` при guard `5 GiB`.
  Storage guard не переопределялся.
- Найдена причина двух молча завершавшихся запусков daily pre-holdout:
  direct-file import не видел пакет `scripts`. После исправления CLI и focused
  suite `11 PASS`; архив дневных Bybit bars завершён `137/137`, `0 failed`,
  end-exclusive `2025-10-01`, `sealed_holdout_rows_decoded=0`.
- Независимый funding validator сначала корректно fail-closed, затем в нём
  исправлена собственная zero-observation ошибка для контрактов, запущенных
  после границы окна. Повторная проверка: integrity PASS, `213,109` funding
  observations, но verdict `INTEGRITY_PASS_PIT_NOT_READY`, 26 coverage warnings
  и survivorship unresolved. Это не разрешает promotion.
- Один write-once XSEC causal V1 завершён с валидным passport
  `63201839a44f06710840526f49c076bf632b921b97a751eb8e99aaa0b45f8971`.
  Verdict `REJECT`: base 15 bps `+9.08%` total / `3.81%` CAGR / Sharpe `0.41` /
  DD `25.72%`, но 2023 `-7.80%`, одна phase `-11.18%`; stress 30 bps
  `-5.82%` total / `-2.54%` CAGR. Красных месяцев `15/31` base и `17/31`
  stress. Старый XSEC shadow остаётся только процессным наблюдением, не ногой с
  доказанным net edge.
- Alpaca PIT daily materialization продолжает GET-only сбор: на 08:37 UTC
  завершены первые 133 из 1000, failures `0`. Direct Bybit position checker
  один раз подтвердил broker flat (`open_position_count=0`). Это не deploy gate:
  live monolith не перезапускался, risk/order state не менялся.

## Superseding recovery update — 2026-08-12 11:05 UTC

Полная сводка и приоритеты находятся в
`reports/PROJECT_STATE_AND_RESEARCH_REPORT_20260812.md`. Этот раздел заменяет
устаревшие выше формулировки «MPL не вскрыт» и «Inplay ждёт causal replay».

- MPL V4/V3 вскрыт один раз после freeze/push: обе руки `REJECT`, independent
  audit PASS. Текущую формулировку закрыть, капитал/shadow не давать.
- Causal Inplay ETH replay на физически изолированном pre-holdout input:
  `N=455`, `3/4` positive folds, median `+0.1705R`, один fold `-0.4602R`.
  Вердикт только `CAUSAL_VIABLE_SHADOW_ONLY`.
- Prospective public-only Inplay collector запущен в screen
  `research_inplay_prospective_20260812`; local research supervisor теперь
  `6/6 healthy`. Collector не имеет authentication/order/risk authority.
- Dirty worktree разобран read-only на `176` code candidates: 15 test-backed,
  118 evidence-backed/reproduce, 16 referenced/review, 27 quarantine. Ничего
  не удалено; ATT1 live-risk diff не принят без reproduction.
- Alpaca PIT progress на срезе `783/1000`, failures `0`; честный v38 replay
  только после validator. Spot Bybit pre-holdout: 67 symbols с данными из 74
  поддерживаемых, 46,742 bars; частичное покрытие не скрывать.
- Server Bybit checker вернул broker flat (`retCode=0`, positions `0`). Local
  checker key expired и отдельно требует replacement. Server L2 collector:
  collecting, lag `2ms`, tape `1.31GB`, free `6.4GB` при guard `5GB`.
- Focused suite: `41 passed`. Live monolith, orders и risk не менялись.
