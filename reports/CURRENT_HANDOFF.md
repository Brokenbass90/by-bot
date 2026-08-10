# Текущий handoff между чатами

Обновлено: 2026-08-10 14:46 UTC.

## Читать в новом чате

1. `reports/CURRENT_HANDOFF.md` — текущая операционная точка.
2. `reports/current_project_state.json` — machine-readable snapshot.
3. `reports/CURRENT_PROJECT_ROADMAP.md` — приоритеты и promotion gates.
4. `reports/CODEX_HANDOFF_AND_DIARY_2026_08_10.md` — хронология и receipts.
5. Свежие прямые broker/service/runtime данные — они важнее любого Markdown.

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
ручная трассировка и независимый replay еще обязательны. Не добавлять шестой
долгий research job до освобождения WIP-слота.

### Alpaca live

- SAFE_HOLD активен, новые входы и ротация запрещены;
- server truth: protective-only `APPLY=1`, exact ACK и cron каждые 15 минут;
- старый PATCH с fractional `qty` уже был исправлен, но свежий broker receipt
  выявил второй дефект: `105.0306` отвергался как sub-penny stop-price;
- исправлена price-grid quantization, server stage smoke PASS, `26 passed`;
- 14:44 UTC apply receipt: SCHW stop `96.47 -> 105.03`, qty
  `0.563776973`, new order `27473b37-9c6d-4a2c-b3a9-493c04cef21b`;
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

1. Проверить следующий Alpaca protective cron receipt и next-session rearm;
   добавить freshness alert на missing/expired DAY stop и stale HWM.
2. Завершить Alpaca exact selection/exit parity; SAFE_HOLD не снимать по одному
   успешному protective receipt.
3. Добавить broker ↔ runner ↔ owner ↔ accounting reconciler и symbol-level
   fail-close новых добавок.
4. Добавить golden test backtest/live sizing parity.
5. Начать чистую ATT1 cohort после фиксов, не меняя `risk_mult=0.10`.
6. При освобождении WIP-слота запустить preregistered maker shadow и
   differentiating retest3 smoke.
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
