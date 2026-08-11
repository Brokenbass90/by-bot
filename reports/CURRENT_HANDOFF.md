# Текущий handoff между чатами

Обновлено: 2026-08-11 13:16 UTC.

## Читать в новом чате

1. `reports/CURRENT_HANDOFF.md` — текущая операционная точка.
2. `reports/current_project_state.json` — machine-readable snapshot.
3. `reports/CURRENT_PROJECT_ROADMAP.md` — приоритеты и promotion gates.
4. `reports/CODEX_HANDOFF_AND_DIARY_2026_08_10.md` — хронология и receipts.
5. Свежие прямые broker/service/runtime данные — они важнее любого Markdown.

## Codex recovery update — 2026-08-11 12:42–13:10 UTC

- После двух положительно закрытых incident-сделок Bybit напрямую снова
  подтвержден flat: `open_position_count=0`. Service активен на PID `2334168`,
  свежий heartbeat сообщает `open_trades=0`; atomic ATT1 release остается
  `475745108b5e7ff0668011694646181ba6d9bd00`. Money authority не расширялась.
  Последняя read-only перепроверка: `13:16 UTC`, heartbeat age `0.4s`,
  `bybit_msgs=152536`, receipt `DEPLOYED`, WS guard inactive/streak `0`.
- DOT принес `+0.1072467 USDT` после TP1+TP2. ADA принес `+0.4193142 USDT`:
  TP1, перевод stop к breakeven и ATR-trail; остаток закрыт биржевым stop.
  Значит profit protection реально исполнилась. Обе сделки начаты старым кодом
  и навсегда остаются contaminated, а не входят в clean post-release N20.
- WS transport guard сейчас не активен. Alert `ACTIVE` означал fail-close новых
  входов после серии reconnect/handshake failures; `RECOVERED` — нормализацию
  контрольных окон. Existing exchange stops при этом сохранялись. Причина
  обрывов не доказана: без `mtr`/host metrics нельзя объявлять ее внешней сетью.
- Six-day research matrix завершена `48/48`, failures пусты; reserved
  `2025-10..2026-06` holdout не читался. Пять постоянных research/shadow screen
  живы; шестой тяжелый процесс не добавлялся поверх занятых слотов.
- Добавлен `research_lab/negative_trade_lab.py`: deterministic research-only
  разложение net/gross/cost в R, фенотипы losses/exits и proposal-only packet
  для AI без секретов, ордеров, code-write или promotion authority.
- Squeeze-long case `620` сделок: gross `-40.37R`, costs `90.97R`, net
  `-131.34R`, `t=-6.74`, PF `0.537`. Это не только комиссия: исходный сигнал
  отрицателен. Plain `TRAIL_SL` дал `-206.48R`, но сделки с `TP1+TRAIL_SL`
  дали `+24.91R`, а `TP1+TP2+TRAIL_SL` — `+127.15R`; следующий тест должен
  менять entry/confirmation и exit-path раздельно, а не просто «расширить stop».
- 5m forensics получил полное `MFE_R/MAE_R 620/620`: `276` stop-then-reversed,
  `175` stopped-no-reversal-yet, `133` gave-back-profit, `36`
  entry-failed-fast. Это описательная диагностика, не causal proof.
- ATT1 wide run: `823` сделки на `64` фактически торговавшихся символах, gross
  `+19.34R`, costs `48.11R`, net `-28.77R`, `t=-0.99`. Wide rollout отклонен;
  major-only ATT1 остается отдельной узкой гипотезой, а прежние заявления о
  широком `--symbols` universe недействительны из-за скрытых allowlists.
- `inplay_retest_v3` получил discoverable standard universe handle с
  сохранением legacy aliases и прежнего default поведения; preflight теперь
  доказывает, что два CSV universe действительно различаются до дорогого run.
- XSEC V3 продолжает zero-risk shadow. Добавлены maturity audit `>=390` дней,
  immutable entry prices и per-symbol markout contributions, anomaly flags и
  запрет использовать phase return `|r|>25%` в leverage history. Текущий
  universe: `62/62` mature, но старые экстремальные markout нельзя считать
  доказательством без сохраненных entry contributions.
- Совместный focused suite: `40 passed`; py_compile/diff checks прошли. Новый
  код не задеплоен в money-live и не расширяет order authority.
- Elder-verдикт Клода не подтвержден: monolith импортирует V2, но policy
  держит его на risk zero после плохих OOS; V3 research-only и давала zero
  annual trades. Нужен exact parity-replay, не включение одной из версий.

Полный фактический отчет этой сессии:
`reports/CODEX_RECOVERY_SESSION_2026_08_11.md`.

Scoped implementation commit `1bf5293` и machine-state commit `9702162`
запушены в `origin/codex/dynamic-symbol-filters`; чужие dirty changes в них не
попали.

## Heartbeat update — 2026-08-11 12:36–12:42 UTC

- Six-day matrix осталась terminal и неизменной: `complete`, `48/48`,
  `failed_cases=[]`, 48 уникальных case keys. Оба временных screen завершены;
  пять постоянных research/shadow sessions присутствуют. Reserved holdout не
  читался. Диск: `83 GiB` free; caffeinate active.
- Direct Bybit перешел в flat. Broker REST подтвердил `open_position_count=0`
  трижды, затем еще раз непосредственно перед остановкой сервиса. Ордера не
  отправлялись/отменялись, позиции вручную не закрывались.
- Candidate `475745108b5e7ff0668011694646181ba6d9bd00` повторно прошел server-venv
  manifest `8/8`, archive SHA256
  `01eebc0541c77be78df496b3b261e76ab03e583fed4f2d91d3beaf944e7f4a01`,
  import smoke и bounded 20-second no-order main smoke.
- Atomic ATT1 stale-fill/fixed-R release задеплоен в `12:40:41–12:40:46 UTC`.
  Receipt: `/root/by-bot/runtime/deploy_receipts/atomic_live_475745108b5e_20260811T124041Z.json`;
  backup: `/root/by-bot/backups/atomic_live_475745108b5e_20260811T124041Z`;
  receipt status `DEPLOYED`, error пустой.
- После deploy stage-verifier подтвердил live hashes `8/8`; bybot active,
  PID `2334168`. Свежий heartbeat: `trade_on=true`, `dry_run=false`,
  `open_trades=0`, `ws_guard_active=0`; direct broker также flat.
- Effective money authority не расширялась: только ATT1 short-only
  `risk_mult=0.10`; midterm/bounce1/IVB1 и остальные sleeves без money risk.
  Старые DOT/ADA incidents навсегда исключены из clean N20. Следующая clean
  ATT1 cohort начинается только с этого release receipt.
- Локальная ветка перед записью этого handoff ahead upstream на пять scoped
  commits; чужой dirty worktree сохранен без очистки или захвата.

## Heartbeat update — 2026-08-11 06:36–06:38 UTC

- Six-day repair завершен строго: status `complete`, `48/48`,
  `failed_cases=[]`; summary имеет 48 уникальных cases. Detached watchdog
  штатно завершился после exact gate.
- Append-only ledger содержит 88 complete events из-за повторных receipts для
  40 переиспользованных runs, но только 48 уникальных keys. Восемь старых
  failed events сохранены как история zero-width incident и не являются
  текущими failures.
- Coverage selected universe: `27/27`, `30/30`, `30/30`, везде `100%` и zero
  gaps. Это current-survivor data, не PIT; holdout не читался.
- Денежных кандидатов нет. ATT1/horizontal дали zero trades и требуют liveness
  trace; support reclaim сломался на replication/OOS; squeeze отрицателен во
  всех окнах, направлениях и costs. Полный verdict:
  `reports/research/SIX_DAY_CRYPTO_MATRIX_VERDICT_20260811.md`.
- Direct Bybit REST в 06:37 UTC неизменен: DOT short `29.7` stop `0.8205`, ADA
  short `53` stop `0.1992`, service active. Operator pause по-прежнему
  отсутствует (`exists=false`, `paused_sleeves=[]`). Deploy/restart запрещены.
- Пять постоянных research screens присутствуют; downloader и temporary
  pipeline screens штатно завершены. Диск `93 GiB` free, caffeinate active.
- Локальная ветка ahead upstream на пять scoped commits после этого handoff;
  чужой dirty worktree сохранен.

## Heartbeat update — 2026-08-11 00:35–00:41 UTC

- Direct Bybit REST: две позиции, service active. DOTUSDT Sell `29.7`, entry
  `0.8023`, stop `0.8205`; ADAUSDT Sell теперь `53`, entry `0.1931`, stop
  `0.1992`. Оба stop присутствуют, account не flat.
- Operator-control read подтвердил, что ATT1 pause **не установлена**:
  `exists=false`, `paused_sleeves=[]`. Поэтому первым ручным действием остается
  `/strategy_pause att1 execution_fix_release`; deploy/restart запрещены.
- Six-day pipeline ложно сообщил `complete` при `40/48`: ledger содержал
  `8 case_failed`. Все восемь — squeeze discovery/replication, одна причина:
  `ZeroDivisionError` на полностью нулевой BB-width history.
- Исправлено: нулевая история теперь означает no-signal; terminal status больше
  не может быть `complete` при failed/missing case. Commit `25bcb57`, focused
  suite `11 passed`.
- Research-only repair resume запущен: supervisor PID `29789` держит lock.
  Первый missing case уже восстановлен: squeeze-long discovery/base `620`
  сделок, `-131.34R`, `-0.212R/trade`, `t=-6.74`, PF `0.537`; считается stress.
  `TRADE_ON=0`,
  private API/order authority отсутствуют. Detached screen
  `six_day_crypto_20260810` служит watchdog: после освобождения lock он требует
  exact `48/48` и пустой failed list, иначе безопасно повторяет resume. Reserved
  holdout не читался.
- Пять постоянных screen-процессов healthy; downloader завершен и его screen
  штатно исчез. Свободно `92 GiB`, six-day `caffeinate` assertion активен.
- Git branch локально ahead upstream на четыре scoped commits; чужой dirty
  worktree не очищался и не попадал в commits.

## Критическое обновление 18:55 UTC

- Bybit больше не flat: последний прямой broker-read подтверждает две
  защищенные позиции: DOTUSDT short `29.7`, entry `0.8023`, stop `0.8205`, и
  ADAUSDT short `116`, entry `0.1931`, stop `0.1992`; service active.
- Исходный ATT1 fill был уже ниже TP1: signal `0.8136`, fill `0.8023`, TP1
  `0.805391`; риск вырос с `$0.4554` до `$1.2012` (`2.6377x`).
- Это execution-contract incident, а не нормальная ATT1 сделка. Остаток
  защищен broker stop; ручного закрытия и рестарта monolith не было.
- Старый live-код после этого допустил ADA fill `0.1931` вместо signal entry
  `0.1953`: stop-distance выросла в `1.5641x`, выше нового лимита `1.20x`.
  ADA также является execution-contract incident и исключается из N20.
- Локальный fail-close patch блокирует target-crossed, risk expansion >1.20x
  и adverse drift >25 bps до заявки и после fill. Shared sizing parity и
  полный focused suite: `60 passed`.
- Просто ждать flat уже недостаточно: старый процесс может открыть следующую
  позицию. Первый ручной шаг в Telegram —
  `/strategy_pause att1 execution_fix_release`. Он блокирует только новые
  входы, но не сопровождение и защиту существующих позиций.
- Patch нельзя выпускать до flat. После operator pause и flat: committed bundle, server-Python
  verify, no-order smoke, три flat receipts, atomic deploy.
- Candidate release commit `475745108b5e7ff0668011694646181ba6d9bd00` уже
  pushed. Bundle SHA256 `01eebc0541c77be78df496b3b261e76ab03e583fed4f2d91d3beaf944e7f4a01`,
  manifest `8/8`; server stage `/root/bybot-staging/475745108b5e` прошел
  server-Python hash/import и bounded 20s no-order main smoke.
- Routine GS `[DRY-RUN]` происходили из Alpaca v3 shadow cron. Telegram noise
  отключен по умолчанию и точечно доставлен на сервер без Bybit restart;
  18:40 UTC shadow cron прошел после deploy, research receipts остаются.
- Запущены screen `bybit_history_150_20260810` и долговечный supervisor
  `six_day_crypto_20260810`; 48 research-only cases, reserved holdout не читается.
- На host подтвержден отдельный `caffeinate` idle-sleep assertion на `518400`
  секунд с 18:58 UTC; экран не удерживается включенным. Power loss/reboot/network
  outage он не переживает, поэтому heartbeat остается вторым уровнем контроля.
- Heartbeat `Six-day trading research guard` проверяет процесс каждые шесть
  часов до 16 августа и не имеет полномочий отправлять/отменять ордера.

Полные incidents:

- `reports/live/ATT1_DOT_EXECUTION_CONTRACT_INCIDENT_20260810.md`;
- `reports/live/ATT1_ADA_EXECUTION_CONTRACT_INCIDENT_20260810.md`.

## Истина всегда четырехслойная

Никогда не писать «live обновлен» по одному Git-коммиту. Отдельно проверять:

1. Git revision и содержимое bundle;
2. deploy receipt и фактические live file hashes;
3. service + свежий heartbeat + effective authority;
4. прямые broker positions/orders/fills и accounting reconciliation.

При расхождении этих слоев статус — `CONFLICT`, новые добавки по затронутому
символу закрываются, защитные действия продолжаются.

## Состояние на handoff

### Bybit live

- atomic bundle revision: `c5eba1ccb244584bb432dd902d22599290fca900`;
- включает ancestor `f290463` с исправлением owner label для TP/time-stop;
- bundle archive SHA256:
  `5c7b4be781aed95b5df9f9f2a38b5912b70a1d523ade7896806b329490702e46`;
- server stage: `/root/bybot-staging/c5eba1ccb244`;
- backup: `/root/by-bot/backups/atomic_live_c5eba1ccb244_20260810T130547Z`;
- deploy receipt:
  `/root/by-bot/runtime/deploy_receipts/atomic_live_c5eba1ccb244_20260810T130547Z.json`;
- staged server-Python imports, py_compile и bounded no-order main smoke: PASS;
- live manifest: `6/6 PASS`;
- bybot service после deploy: active; новый PID при проверке `2276002`;
- 13:31 UTC: direct broker flat; heartbeat свежий, `open_trades=0`,
  `trade_on=true`, `dry_run=false`, authority complete;
- authority: ATT1 short-only `risk_mult=0.10`; BOUNCE1/IVB1/midterm risk zero;
- риск не увеличивался, новые sleeves не получали деньги.

Перед следующей live mutation повторно проверить все четыре слоя — эти данные
временные и уже могут устареть.

### Retest3

- прежний прогон остановлен как no-op;
- `scripts/retest3_stop_ladder.sh` связан с `IRV3_STOP_BUFFER_ATR`;
- contract preflight требует четыре разные resolved configurations;
- 90d smoke дал `0/0/1/1` сделки и был заблокирован audit gate;
- это не отрицательный вердикт стратегии и не разрешение на полный sweep;
- focused suite: 18 tests passed.

Отдельно: старый пункт Клода про ms/sec bug в `sloped_break_retest_v1` уже
закрыт в коде (`_retest_expiry_ms`, commit history `2d04e3f`); 2 focused tests
passed. Следующий gate для этой ноги — reachability/geometry/shadow, не еще один
patch того же defect.

### Исследовательская станция

- пять официальных процессов: `5 healthy / 0 degraded`;
- все research-only, `live_order_authority=false`;
- dynamic funding: 975 trials, 55 fills, 52 closed, 3 open,
  raw mean 480.17 bps, capital false;
- frozen funding: 196 trials, 12 fills, 9 closed, 3 open,
  raw mean 606.09 bps, capital false;
- XSEC: latest decision risk zero/orders false; aggregate требует
  outlier-resistant и cost-aware проверки;
- Alpaca adaptive: `shadow_no_orders`, picks SNOW/BAC/PANW/CRWD;
- project audit: process healthy, но raw precision низкая — 279 findings,
  205 current, 4 actionable, 2 confirmed, 117 dismissed.

Вывод: scheduler/liveness работает. Контур доказательства работает частично;
ручная трассировка и независимый replay еще обязательны. Временные jobs
добавлены по прямому запросу владельца с `nice +10`: downloader и шестидневная
очередь. Они не меняют пять официальных supervisors, имеют
`live_order_authority=false`, deadline и resumable ledger.

Load-aware backlog watcher `research_backlog_guard_20260810` завершился
`complete`: он последовательно выполнил два bounded задания и исчез из screen,
не затронув пять постоянных supervisors:

1. USDJPY H1 `session_breakout_retest + round_level_sweep` под stress costs;
2. H4 fixed probe для major/JPY/XAU.

Оба задания research-only, `risk_pct=0`, без broker calls и live authority.
USDJPY H1 был честно остановлен cost gate: `feeR=0.515 > 0.35`, поэтому все
8 комбинаций имеют ноль симулированных сделок. H4 дал четыре слабых lead:
EURJPY trend pullback `+3.366R/13 trades/2 of 4 folds`, GBPUSD trend pullback
`+1.732R/9/3 of 4`, USDJPY breakout/retest `+1.321R/10/2 of 4`, EURUSD
breakout/retest `+1.221R/4/2 of 4`. Все строки `preflight=false`; ни одна не
готова к shadow или капиталу без prereg reproduction и реальных costs.

### Alpaca honest diagnostic

Создан новый причинный daily-portfolio runner и preregistration. Он не читает
sealed forward с 2026-08-03 и не меняет SAFE_HOLD. Исправлены: calendar-month
signal -> next-open, cash/70% exposure, fractional qty, true hard cap, costs на
каждом fill, retained positions, deployable simple-stop/ratchet daily proxy и
daily MTM/DD с initial capital.

Ключевой stress `10 bps/side`:

- v38 successor + SPY200: 2022 `-2.89%`, DD `4.00%`, PF `0.363`; recent
  live-universe 2024-05..2026-04 `+30.16%`, DD `7.84%`, PF `1.863`;
- Adaptive + SPY200: 2022 `-5.63%`, DD `6.58%`; recent `+18.75%`, DD `4.94%`.

Independent receipt validation: results `16/16`, source pins `6/6`, cost stress
`8/8` PASS. Promotion false, data rating `NEEDS_REVISION`: survivor bias,
authoritative XNYS/PIT/corporate actions/cost calibration и intraday exit path
остаются blockers; XYZ coverage `63.9%`. Старые v38 `+50.77% / DD 2.28%` не
использовать для капитала. Новый replay — repaired diagnostic, не money proof.

Дополнительно исправлен будущий live sizing path: bridge больше не делает
cap 60% -> renormalize обратно до 100%; при недостатке имен unused sleeve
остается cash. SAFE_HOLD не изменен, new entries по-прежнему off. Совместный
Alpaca focused suite: `34 passed`, включая golden backtest↔live weight parity.

### Alpaca live

- SAFE_HOLD активен, новые входы и ротация запрещены;
- server truth: protective-only `APPLY=1`, exact ACK и cron каждые 15 минут;
- старый PATCH с fractional `qty` уже был исправлен, но свежий broker receipt
  выявил второй дефект: `105.0306` отвергался как sub-penny stop-price;
- исправлена price-grid quantization, server stage smoke PASS, `26 passed`;
- 14:44 UTC apply receipt: SCHW stop `96.47 -> 105.03`, qty
  `0.563776973`, new order `27473b37-9c6d-4a2c-b3a9-493c04cef21b`;
- 14:45 UTC automatic cron receipt: SCHW `hold/no_material_stop_raise`,
  current stop `105.03`, errors/results отсутствуют;
- 14:44 UTC direct broker-read: equity `$485.87`, cash `$391.27`, positions
  ABBV/SCHW, stop coverage `2/2`, account/trading not blocked;
- ABBV qty `0.135734866`, stop `235.17`, trail not armed;
- SCHW current около `108.70`, entry `101.552`, stop `105.03`, теоретический
  lock около `+3.42%` до gap/slippage;
- оба stop имеют `DAY`; нужна проверка daily rearm/next-session coverage и
  freshness, overnight gap risk остается;
- paper launcher теперь по умолчанию не отправляет routine PAPER HOLD/dry-run
  Telegram, но продолжает paper orders, receipts и логи;
- adaptive shadow picks SNOW/BAC/PANW/CRWD не совпадают с live ABBV/SCHW:
  selection/rotation parity остается `BLOCKED_FAIL_CLOSED`;
- не называть adaptive shadow живой торговлей.

### Worktree cleanup

- read-only inventory: `1,138` paths, `27` tracked, `1,111` untracked;
- `61` manual-code candidates нельзя терять или удалять без reference/tests;
- `100` archive/backup и крупные data/runtime artifacts — первые кандидаты на
  manifest-backed quarantine вне code checkout;
- ничего массово не удалялось из-за параллельной работы Клода;
- план: `reports/WORKTREE_CLEANUP_PLAN_2026_08_10.md`.

## Следующие действия в точном порядке

1. В Telegram выполнить `/strategy_pause att1 execution_fix_release` и
   подтвердить receipt: запрет только новых ATT1-входов, сопровождение текущих
   ADA/DOT и broker stops продолжает работать.
2. После естественного broker flat получить три прямых flat receipt, применить
   staged bundle `4757451`, сверить hashes/service/heartbeat/broker и только
   затем разрешать ATT1 resume и новую clean cohort.
3. Проверить next-session rearm; добавить freshness alert на missing/expired
   DAY stop и stale HWM. Текущий 15-minute cron уже подтвержден после patch.
4. Материализовать PIT/XNYS/corporate-action/cost bundle для Alpaca, сверить
   новый runner вторым engine; SAFE_HOLD не снимать по positive recent proxy.
5. Pure broker ↔ runner ↔ owner ↔ accounting contract готов и имеет 18 passed;
   добавить runtime adapters/durable receipt и подключить symbol-level
   `entry_allowed()` ко всем submit paths отдельным release.
6. Общий pre-round sizing contract и golden fixtures готовы; завершить
   parity exchange-слоя: qty-step/min-qty, fees, partial fills, legacy-DCA.
7. Preregister и воспроизвести четыре H4 FX leads на fresh bid/ask+swap с
   chronological OOS; H1 USDJPY не реанимировать без отдельного cost mechanism.
   При освобождении WIP-слота запустить maker shadow и differentiating retest3 smoke.
8. Реализовать edge cards и phenotype loss analysis; второй engine сверяет
   только кандидатов, прошедших первые gates.
9. Разбирать worktree небольшими owner-tagged batches; сначала data/backups,
   затем 61 code candidate.
10. Индексировать несекретный код для Ollama с path/SHA/freshness/provenance.

## Запреты, которые сохраняются

- не повышать ATT1 risk по старым/contaminated сделкам;
- не выдавать shadow/backtest aggregate за live прибыль;
- не включать новые стратегии в деньги только ради количества;
- не чистить грязный worktree массово и не присваивать чужие изменения;
- не читать/печатать secrets в отчеты;
- не давать AI право ордера, credentials или risk mutation;
- не считать старые запреты вечной истиной: каждый пересматривается через
  reproduction, но до опровержения защищает капитал.
