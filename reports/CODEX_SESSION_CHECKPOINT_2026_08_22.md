# Canonical project checkpoint — 2026-08-22

Это единственная точка продолжения после сессии 22 августа. При конфликте со
старыми handoff, Telegram-ответами, локальными runtime-файлами или памятью ИИ
верить прямому broker/service readback и фактам ниже. Любые рыночные значения
остаются снимком и перед денежным действием проверяются заново.

## Короткий итог

- Alpaca live-счёт защищён: ABBV и SCHW имеют стопы выше входа на полный точный
  fractional qty. Новые покупки и ротация остаются `SAFE_HOLD`.
- Bybit жив и flat. Отсутствие сделок объясняется фазовой дырой: единственная
  денежная ATT1 — short-only, рынок `bull_trend`, а все свежие проверки дали
  `no_signal`; это не остановка инфраструктуры.
- Платные proactive/trade-review вызовы DeepSeek выключены. Старый weekly cron,
  который мог игнорировать env-лимит, заменён проверенной zero-cost версией.
- Reviewed DeepSeek/WS bundle установлен на live после трёх flat-подтверждений;
  сервис, broker-flat и реальный рост WS проверены после рестарта.
- Полезные public-only collectors работают; wide M5 имеет 137 receipts, но
  только 51 ряд с полным окном, 48 частичных и 38 пустых.
- Второй денежный crypto sleeve всё ещё не разрешён. Pure live-native contract
  и fixture parity готовы, но actual research↔live feasibility завершился
  точным `BLOCKED` receipt: настоящие strategy/fill/outcome boundaries ещё не
  связаны.

## Прямая broker/service truth

### Alpaca live — GET-only 2026-08-22

- Account `ACTIVE`, equity `$490.75`, cash `$391.47`.
- ABBV: qty `0.135734866`, entry `247.55`, last `264.96`, unrealized
  `+$2.363144`, accepted DAY stop `257.37` на полный qty.
- SCHW: qty `0.563776973`, entry `101.552`, last `112.30`, unrealized
  `+$6.059475`, accepted DAY stop `108.20` на полный qty.
- Broker stop coverage `2/2`. Теоретически зафиксированный результат у стопов,
  до gap/slippage, около `+$5.08`; текущий unrealized около `+$8.42`.
- История брокера подтверждает ночное переармирование 20 и 21 августа без
  возврата на старые `235.17/96.47`. Fractional equity stop остаётся `DAY` из-за
  broker contract; защита живёт через подтверждённый monotonic accepted floor.
- `SAFE_HOLD` сохраняется: новые входы, stale sells и mid-cycle rotation нельзя
  открывать до prospective monthly manifest/paper-parity. Следующий контроль —
  GET-only readback после открытия рынка 24 августа.

### Bybit live — direct signed GET и heartbeat 2026-08-22

- Equity около `$1023.79`, позиции `0`, open orders `0`, UPL `0`.
- `bybot.service=active`, `trade_on=true`, `dry_run=false`, regime
  `bull_trend`, WS guard `0`.
- После рестарта WebSocket завершил последовательную подписку: счётчик вырос
  `10,230 -> 14,058` за 25 секунд, позже достиг `93,797`; это живой поток.
- После release-рестарта в `15:56:57 UTC` новый процесс снова завершил
  последовательную подписку; postcheck дал `7,238 -> 13,748`, три connect,
  guard `false`, service `active`, позиции и open orders `0/0`.
- Финальный readback этой сессии: `bybit_msgs=167,960`, service `active`,
  broker positions/orders `0/0`; DeepSeek ledger всё ещё `1` (только legacy
  seed), то есть после deploy фонового расхода не появилось.
- Последние сделки были 18 августа: LTC short `+$0.26695`, BTC short
  `-$0.43039`.
- После последнего close 603 ATT1 evaluations дали 0 signals: cooldown 258,
  invalid short slope 218, low R2 50, direction 35, same bar 26, stale pivot 16.
  Нет отказов breaker/authority/min-qty/infra.
- ATT1 остаётся tiny canary `risk_mult=0.10`; effective nominal risk около
  `0.044%` equity на сделку. Breaker открыт, 21d cohort `N=14`, 10 wins,
  net `+$1.7249`. Это малая выборка, не повод масштабировать.
- Старые предупреждения ложны: canary не истёк 5 августа — действует owner
  `CONTINUE_UNTIL_EXPLICIT_PAUSE`; Bybit key подтверждён до
  `2026-11-06 08:43:37 UTC`, не до 12 августа.

## AI, Telegram и расходы

### Что уже изменено на VPS

- Env-only, с backup и flat-gated restart:
  `DEEPSEEK_OPERATOR_USE_API=0`,
  `DEEPSEEK_OPERATOR_TRADE_REVIEW_ENABLE=0`, daily cap `8`, history `4/30m`,
  max completion `400`, retries `0`, continuation `1`.
- `scripts/post_trade_ai_review.py` установлен с explicit
  `POST_TRADE_AI_ENABLE=0`; реальный smoke вернул `disabled`.
- `scripts/deepseek_weekly_cron.py` установлен; env weekly cap `0`. Dry-run
  показал `Would tune: none`. Старый воскресный путь до восьми вызовов закрыт.
- Backup cost-control release:
  `/root/by-bot/runtime/deploy_backups/deepseek_cost_control_20260822T153600Z`.

### Исправление старых дат — live с 2026-08-22 15:56:57 UTC

- Источник найден: свежий snapshot смешивался с canonical от 21 июля и
  отдельным cached brief с дедлайнами 5/12 августа.
- Targeted overlay вводит явный UTC/date/weekday/source-age contract,
  исключает cached dynamic payload, ограничивает prompt и считает provider
  usage без сохранения prompt/answer/key.
- Независимый review нашёл и затем подтвердил закрытие обходов размера,
  concurrent daily budget, `history=0`, missing brief marker и неправильной
  интерпретации shadow flags как money authority: `37` independent focused
  tests плюс target adversarial/import smoke PASS.
- Установлены exact hashes: `bot/deepseek_usage.py`
  `5cc482026c9e6a254ccfe3e615e373dc7aa477f8e054cead80f08d37dad5c3f4`,
  затем `bot/deepseek_overlay.py`
  `6f6c124c65c0e1f5cdfb21b69e8142a7f5c42b9509c2cfd83de091d4e178f35e`.
- Durable SQLite-ledger резервирует каждый provider attempt до HTTP. Production
  `/ai_budget` после миграции: `used_today=1`, `daily_cap=8`, `remaining=7`.
- Offline production-smoke после deploy, без API-вызова: `now_utc`
  `2026-08-22T16:07:49Z`, дата `2026-08-22`, weekday `Saturday`, свежий snapshot
  age `166s`; canonical `2026-07-21` помечен `historical_only`, cached dynamic
  payload отсутствует, serialized snapshot `5,367 < 8,000` chars.
- Ограничение: direct web/weekly/post-trade paths ещё не объединены этим ledger;
  сейчас они code-aware выключены, поэтому это не текущий расход, но при будущем
  включении потребуется отдельная интеграция.

### WS-сообщение `CRITICAL 2/3/2`

- Это ложная ratio-эскалация на выборке всего из двух connect; guard не был
  активен, а сообщения продолжали расти.
- Минимальный exact-server patch установлен: при `connect < 3` статус
  `LOW_SAMPLE`, no-connect остаётся fail-closed; fallback уведомление будет
  честно называться `Rule-based operator`, а не `AI operator`.
- Live hash `smart_pump_reversal_bot.py`:
  `e7e159be1fc5239ea84c46e65bb85e1e4af2d231a41345bb9d0c96c40d415b9e`;
  target `py_compile` и 7 focused tests PASS.
- Atomic rollback bundle:
  `/root/by-bot/runtime/deploy_backups/ai_ws_20260822T160000Z`.

### GMGN-карточка

- Строки и referral `vqZJ5uw2` отсутствуют в коде, runtime и логах бота. Это
  Telegram sponsored/recommended card, не действие нашего AI и не компрометация
  TG-бота.
- GMGN — реальный внешний meme-trading terminal. Код в рекламе выгоден
  рефереру; trading fee не включает gas/priority/slippage. Не подключать к нему
  основной кошелёк, seed или production order authority. Если исследовать —
  только изолированный read-only API/одноразовый кошелёк и отдельный gate.

## Research capacity и доказательства

### Что работает сейчас

- 10 local screen jobs, включая ATT1 limit-paper, Alpaca adaptive shadow,
  funding frozen/dynamic, XSEC, Inplay, project audit и три новых public
  collectors.
- ONDO L2+trades: `collecting`, public-only, no order capability, snapshot
  synced, lag единицы ms, storage allowed; около `976 MB`.
- Six-symbol trade tape: `collecting`, public-only, no order capability;
  около `480 MB`.
- Alt24 density: `collecting`, 24 symbols, public-only, no order capability;
  около `1.5 GB`.
- Свободно около `81 GiB`, collector floor `50 GiB`.
- VPS дополнительно продолжает public liquidation и 12-symbol density сбор;
  density-файл обновляется, хотя старый reconnect-log не является текущим
  heartbeat.
- Найдены два старых дублирующих Mac-окна `project_audit` и `funding_frozen`
  внутри multi-window screen. После проверки точных PID/process groups и lock
  owner они остановлены; канонические отдельные supervisor-процессы, dynamic
  funding и все данные сохранены.

### Wide M5 data-quality truth

- Receipts `137/137`, `state=complete`, total `11,659,228` M5 rows, sealed rows
  decoded `0`.
- Full fixed-window rows: `51`; partial/listing-window rows: `48`; zero rows:
  `38`; всего nonzero symbols: `99`.
- Нельзя объявлять universe `137` пригодным. Fixed-window cross-sectional run
  обязан заранее использовать exact 51-symbol eligible manifest; partial rows
  требуют отдельного listing-aware contract.

### Текущие результаты

- ATT1 limit-paper: `N=3`, maker fills `2/3`, mean saving `+2.48 bps`. Механизм
  интересный, статистика недостаточна для live.
- Inplay prospective ETH: `N=0`, public-only/zero-risk. Конфликт старого startup
  cadence и текущего raw count остаётся `NOT_CONFIRMED`.
- Order blocks: causal context snapshot восстановлен на 137 H1 bundles,
  `18 passed`, immutable receipt. Он имеет только context authority. Старый
  return-to-zone результат остаётся FAIL_CLOSED: хуже random в 8/12 cells и
  старый control engine имеет overlap/window/multiplicity дефекты.
- Новый impulse-continuation v1 diagnostic на 8 физически изолированных public
  preholdout symbols завершил `580` matched triplets, overlap/window escapes
  `0/0`, но independent review дал `NO_GO/BLOCKED`. Даже при event stress mean
  `+14.65 bps` провалены event>A Holm (`p=0.11425`), early half
  (`-16.91 bps`) и concentration (`43.90% > 35%`). Дополнительно найдены три
  P1: path-dependent matcher сохранил лишь `580/9,420` events, sign-test не
  учитывает cross-symbol time clusters, evaluator SHA не был pinned до score.
  Эти diagnostic цифры не доказывают ни наличие, ни отсутствие общего edge.
  BLOCKED receipt file SHA-256
  `80ef238674c39ec1931dc40afa814fb584b90311ea5295fac8c3e431ba854c4c`,
  focused suite `27 passed`, sealed rows decoded `0`.
- Funding/XSEC/Alpaca adaptive остаются shadow/research, не money authority.
- Exact-51 wide M5 preregistered RMR1 cost gate завершён
  `FAIL_CLOSED_NO_WIDE_RMR1_EDGE`: base 16 bps `N=3,840`, PF `0.804`,
  expectancy `-0.682R`, положительны `17/51` symbols и `4/19` месяцев;
  stress 24 bps PF `0.715`, expectancy `-1.026R`, `13/51` и `4/19`.
  Holdout rows decoded `0`, network/private API/orders/risk mutations `0`.
  Terminal receipt:
  `research_lab/results/m5_fixed51_rmr1_cost_gate_20260822/terminal_receipt.json`,
  file SHA-256
  `0418f7b25b7f1a68994b254dda3e0b9b8004d5732a32a40460a4dc7a947d37f0`.
  Нельзя post-hoc выбирать 17 плюсовых символов; следующая гипотеза должна быть
  отдельным regime-based prereg, а не случайным sweep.

## Engineering gates, сделанные локально

- Alpaca write-once monthly cycle manifest: single-read hashes, calendar-gap
  gate, exact inline OHLC hash/cutoff, SPY+QQQ requirement, finite weights,
  manifest-before-entry и fingerprinted order IDs; `9 passed`. Не wired/live.
- Alpaca monthly paper-lifecycle runner теперь покрывает broker-free цепочку
  `signal -> adverse next-open fill -> exact ATR stop -> monotonic management ->
  exit`, fingerprinted IDs и SHA-chain. Agent relevant suite `30 passed`,
  независимый focused repeat `15 passed`; runner SHA-256
  `37d396cf3d204479c09b3eba49260b55c2148b40fc21f2cfc14d7b76b8b9733c`.
- Readiness честно `BLOCKED_WAITING_PROSPECTIVE_MONTH_END_EVIDENCE`:
  prospective manifests `0`, текущий adaptive-файл только `shadow_no_orders`,
  а 59 local parity OHLC заканчиваются `2026-07-10`. SAFE_HOLD/broker/orders/risk
  не затронуты. Receipt file SHA-256
  `ba50f1b707fb4e86e29ff702c7285374e75692092aa64b0ae3dd9c0fd8c10c31`.
- OrderBlockSnapshotV1: known-at/decision-at, lifecycle, continuity/OHLCV and
  stable hashes; `18 passed`. Context-only.
- ATT1/SBR1 live-native contract: exact sleeve profiles, geometry/config/source/
  data fingerprint, finalized fill/age gates, tick-rounded positive targets,
  durable rebase receipt; combined contract/comparator `32 passed`.
- Separate research/live fixture emitters и strict parity schema v2: ATT1+SBR1
  JSONL byte-identical fixture, mismatch fail-closed; targeted `42 passed`.

Эти тесты доказывают контракт и fixture, но не actual strategy adapter parity.
Реальный pre-sealed feasibility gate дал точный `BLOCKED` receipt:
`research_lab/results/att1_sbr1_live_native_parity_feasibility_20260822/blocked_receipt.json`,
SHA-256
`e3e398e6e85d15c69126a6f34c4c5a3813a00195e1b19dce2331ca02ff06c8af`.
Sealed rows decoded/emitted/metricized `0`; comparator не запускался. Binding
initial blockers: отсутствуют реальный SBR1 live boundary, полный ATT1
evaluation/drop hook, finalized-fill adapter, exact hash-bound
config/closed-H1 gate и actual base/stress outcome-cost boundary. Последующий
follow-up ниже закрыл два pure-adapter слоя, но не их production callers. До
полного устранения seams SBR1 не получает даже zero-risk shadow authority.

Follow-up закрыл две pure normalization seams, но не снял gate:

- `bot/live_native_signal_adapters.py` (`a153c12e...d0b21`) строго преобразует
  реальный ATT1 `TradeSignal` + effective runtime self-hash + exact source/H1
  bytes в `LiveNativeDecisionPlan`; SBR1 live намеренно падает
  `sbr1_live_boundary_absent`.
- `bot/live_native_fill_adapter.py` (`98d895ca...0324b`) принимает только
  terminal `Filled` order и полный reconciled execution aggregate; position
  summary не считается доказательством finality.
- Adjacent suite агента `105 passed`; независимый повторный набор `81 passed`,
  `py_compile`/diff-check PASS. Follow-up receipt file SHA-256:
  `0193358cbc48d7aeb1fd5231ba6edff1793bc96baf4f93b412ed4af25c45924b`.
- Решение остаётся `STILL_BLOCKED_BOUNDARY_SEAMS_PARTIAL`: adapter callers,
  durable actual research ledger/rebase receipt, SBR1 live wrapper, closed-H1
  BTC EMA200 gate, полный universe/tick/cost manifest и actual outcome
  base/stress boundary ещё отсутствуют.

## Что намеренно не сделано

- Не включены новые Alpaca покупки и не увеличен капитал.
- Не добавлена вторая денежная crypto-нога и не повышен ATT1 risk.
- Не открыты sealed данные 2025-10..2026-06.
- Не задеплоен целиком грязный local monolith.
- Не сделан обычный Git push: ветка `ahead 6, behind 2`, сотни WIP-файлов и
  security incident требуют тематических bundles и отдельной истории.
- Forex/CFD/XAU money authority отсутствует; данные/идеи не равны готовой ноге.

## Security blockers

- Во время read-only grep был выведен существующий Telegram bot credential из
  ignored local env. Значение не повторять. Владелец должен ротировать токен
  через BotFather и обновить secret env; это нельзя закрыть кодовым тестом.
- Старый MT5 token остаётся в remote Git history. После ротации потребуется
  отдельное owner-разрешение на `push --force-with-lease`; обычный push не
  исправит историю.
- Bybit key без withdrawal scope, но IP unrestricted; позже ограничить IP после
  стабильного operational endpoint.

## Следующие обязательные gates

1. 24 августа проверить Alpaca стопы прямым broker GET до/после открытия и
   после 20:30 UTC; floor не должен падать ниже `257.37/108.20`.
   После завершения августовского month-end материализовать write-once
   prospective manifest до следующего XNYS open и провести один полный
   broker-free paper lifecycle с нулём инцидентов.
2. Подключить готовые default-off signal/fill adapters к реальным ATT1
   wrapper/replay callers, перестать глотать evaluation exceptions, построить
   настоящий SBR1 live wrapper и оставшиеся ledger/regime/manifest/outcome
   seams; затем повторить pre-sealed parity. Только PASS разрешает zero-risk
   shadow.
3. На exact-51 manifest формулировать только отдельную causal regime-гипотезу;
   generic wide RMR1 закрыт отрицательным base/stress verdict. Не выбирать
   победителей post-hoc и не тратить CPU на случайные sweeps.
4. Order-block v2: до нового score закрепить evaluator/runner/tests/input manifest,
   заменить matching на outcome-free chronological maximum-cardinality и
   cluster-aware inference; затем только новый public-preholdout prereg. Отдельно
   продолжить XAU frozen base/stress.
5. Через следующий operational цикл проверить, что WS alert при малой выборке
   показывает `LOW_SAMPLE`/`Rule-based operator`, а durable `/ai_budget` не
   расходуется без manual запроса.
6. Owner actions: ротация Telegram и MT5 tokens; затем тематические clean commits
   и решение по remote history.

## Как делегировать и экономить сильную модель

- Сильная модель: live incidents, broker reconciliation, capital gates,
  архитектурные контракты, independent review и финальный promotion verdict.
- Более лёгкие Codex/Claude: frozen backtest execution, collectors, data QA,
  тестовые fixture, документация, UI и механические scoped commits по готовому
  контракту.
- Локальная модель: proposal-only triage/audit без секретов и без права менять
  risk/orders. DeepSeek — manual advisory и максимум один действительно
  полезный weekly forensic, а не фоновые no-trade сообщения.

Каждая делегация должна иметь file ownership, входные hashes, запрет live
mutation, точную команду проверки и конечный PASS/BLOCKED receipt. Это позволит
использовать сильную модель как архитектора и ревьюера, а не как дорогой cron.
