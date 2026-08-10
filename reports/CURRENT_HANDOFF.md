# Текущий handoff между чатами

Обновлено: 2026-08-10 18:35 UTC.

## Читать в новом чате

1. `reports/CURRENT_HANDOFF.md` — текущая операционная точка.
2. `reports/current_project_state.json` — machine-readable snapshot.
3. `reports/CURRENT_PROJECT_ROADMAP.md` — приоритеты и promotion gates.
4. `reports/CODEX_HANDOFF_AND_DIARY_2026_08_10.md` — хронология и receipts.
5. Свежие прямые broker/service/runtime данные — они важнее любого Markdown.

## Критическое обновление 18:35 UTC

- Bybit больше не flat: прямой broker-read подтверждает DOTUSDT short `29.7`,
  entry `0.8023`, stop `0.8205`; service active.
- Исходный ATT1 fill был уже ниже TP1: signal `0.8136`, fill `0.8023`, TP1
  `0.805391`; риск вырос с `$0.4554` до `$1.2012` (`2.6377x`).
- Это execution-contract incident, а не нормальная ATT1 сделка. Остаток
  защищен broker stop; ручного закрытия и рестарта monolith не было.
- Локальный fail-close patch блокирует target-crossed, risk expansion >1.20x
  и adverse drift >25 bps до заявки и после fill. `50 passed`.
- Patch нельзя выпускать до flat. После flat: committed bundle, server-Python
  verify, no-order smoke, три flat receipts, atomic deploy.
- Candidate release commit `d43ecb06197832a8ecb99723d0da5dd0b5f712e5` уже
  pushed. Bundle SHA256 `0886910710f6b9e1fea1a184309c9279267ac24bbd7c0ed7bc9cb5b9279f1a00`,
  manifest `7/7`; server stage `/root/bybot-staging/d43ecb061978` прошел
  server-Python hash/import и bounded 20s no-order main smoke.
- Routine GS `[DRY-RUN]` происходили из Alpaca v3 shadow cron. Telegram noise
  отключен по умолчанию и точечно доставлен на сервер без Bybit restart;
  18:40 UTC shadow cron прошел после deploy, research receipts остаются.
- Запущены screen `bybit_history_150_20260810` и долговечный supervisor
  `six_day_crypto_20260810`; 48 research-only cases, reserved holdout не читается.
- Heartbeat `Six-day trading research guard` проверяет процесс каждые шесть
  часов до 16 августа и не имеет полномочий отправлять/отменять ордера.

Полный incident: `reports/live/ATT1_DOT_EXECUTION_CONTRACT_INCIDENT_20260810.md`.

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

1. Проверить next-session rearm; добавить freshness alert на missing/expired
   DAY stop и stale HWM. Текущий 15-minute cron уже подтвержден после patch.
2. Материализовать PIT/XNYS/corporate-action/cost bundle для Alpaca, сверить
   новый runner вторым engine; SAFE_HOLD не снимать по positive recent proxy.
3. Добавить broker ↔ runner ↔ owner ↔ accounting reconciler и symbol-level
   fail-close новых добавок.
4. Добавить golden test backtest/live sizing parity.
5. Начать чистую ATT1 cohort после фиксов, не меняя `risk_mult=0.10`.
6. Preregister и воспроизвести четыре H4 FX leads на fresh bid/ask+swap с
   chronological OOS; H1 USDJPY не реанимировать без отдельного cost mechanism.
   При освобождении WIP-слота запустить maker shadow и differentiating retest3 smoke.
7. Реализовать edge cards и phenotype loss analysis; второй engine сверяет
   только кандидатов, прошедших первые gates.
8. Разбирать worktree небольшими owner-tagged batches; сначала data/backups,
   затем 61 code candidate.
9. Индексировать несекретный код для Ollama с path/SHA/freshness/provenance.

## Запреты, которые сохраняются

- не повышать ATT1 risk по старым/contaminated сделкам;
- не выдавать shadow/backtest aggregate за live прибыль;
- не включать новые стратегии в деньги только ради количества;
- не чистить грязный worktree массово и не присваивать чужие изменения;
- не читать/печатать secrets в отчеты;
- не давать AI право ордера, credentials или risk mutation;
- не считать старые запреты вечной истиной: каждый пересматривается через
  reproduction, но до опровержения защищает капитал.
