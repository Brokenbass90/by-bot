# Codex handoff и дневник — 2026-08-10

## Итог сессии

Проведён read-only антикризисный аудит кода, свежих отчётов, VPS, Bybit,
Alpaca, web и research supervisors. Live не изменялся. Основной вывод: текущий
binding constraint — не капитал и не количество стратегий, а trust/release/
reconciliation plane.

## Свежая каноническая точка

Время: 2026-08-10 12:26–12:30 UTC.

- Bybit: 0 positions; equity/available $1,021.35.
- `bybot.service`: active; heartbeat свежий; `open_trades=0`.
- Owner: ATT1 short-only risk 0.10 — единственная money-нога.
- ATT1 heartbeat: 9 trades, net −0.2716; promotion count недействителен без
  отдельной clean post-fix cohort.
- `f290463`: в Git, не в live; server monolith SHA отличается.
- Missing bundle dependencies: пять файлов по checkpoint всё ещё отсутствуют.
- Alpaca: ACTIVE, equity $485.06, ABBV/SCHW, static stop coverage 2/2; SAFE_HOLD.
- Web: service active, local ping 200; auth/UX path не проверен.
- Research: 5/5 supervisor sessions healthy.
- VPS: 1 vCPU, около 1 GB RAM, 2 GB swap.
- Worktree: 23 tracked changes + 419 untracked; destructive cleanup запрещён.

## Новые findings

### F-20260810-RETEST3-ENV — likely confirmed by static reproduction

Severity: high, research integrity.
Evidence: `retest3_stop_ladder.sh` сообщает, что stop handle не найдена, затем
условно экспортирует `RETEST3_STOP_MULT`; стратегия читает
`IRV3_STOP_BUFFER_ATR`. Вероятный эффект: четыре одинаковых полноразмерных
прогона вместо ladder.

Next reproduction:

1. вывести resolved config каждого run;
2. задать real handle четырьмя различными значениями;
3. дешёвым smoke сравнить config hash и median stop;
4. запретить full run, если они равны.

### F-20260810-MAKER-CONFLICT — confirmed evidence conflict

Severity: high, promotion integrity.
Simple cost model показывает улучшение; hardened strict post-only smoke
показывает adverse selection и худший результат. Статус maker: shadow research,
не рабочий рычаг.

### F-20260810-SOURCE-DRIFT — confirmed architectural pattern

Severity: critical class.
Git, live SHA, heartbeat, broker, accounting и отчёты могут расходиться. Нужен
автоматический reconciler и generated current snapshot; prose-ledger не должен
быть единственной истиной.

## Сначала сделать

1. Починить/перезапустить retest3 ladder с differentiating smoke.
2. Собрать и проверить atomic dependency bundle для `f290463`.
3. Выполнить no-order startup-smoke и три broker-flat проверки.
4. Атомарно задеплоить, сохранив authority ATT1 0.10 без расширения.
5. Получить market-open Alpaca fractional ratchet receipt.
6. Начать reconciler + conflict-symbol add fail-close.
7. Ввести clean cohort IDs и backtest/live sizing golden fixtures.

## Передача Клоду

Клод может безопасно продолжить только bounded research:

- исправленный retest3 stop-ladder после дешёвого proof-of-difference;
- frozen ATT1 shallow-slope holdout с заранее записанным порогом;
- long-leg family feasibility, начиная с in-play breakout/retest;
- phenotype loss table по ATT1/retest3;
- каждый job обязан иметь config/data/code hashes, budget и stop rule.

Не считать maker PASS и не использовать результаты текущего no-op ladder.

## Передача Codex

- owner-control/reconciliation contracts;
- deterministic atomic release bundle;
- live/backtest sizing parity;
- web/TG broker-grounded truth design;
- independent LEAN replay spike;
- machine inventory и non-secret hybrid code index.

## Дневник проверок

| Проверка | Результат | Мутация |
|---|---|---|
| Git branch/HEAD/status | `codex/dynamic-symbol-filters`, `c5eba1c`, heavily dirty | нет |
| Machine manifest | 90 strategy files; 85 referenced; 5 dead candidates | нет |
| Repo inventory | 1,099 Python files; около 286k строк; 16,557-line monolith | нет |
| Bybit direct broker | flat, $1,021.35 equity | нет |
| Runner/heartbeat/owner | active/fresh; ATT1 risk 0.10 only money | нет |
| Server SHA/dependencies | f290 not deployed; five modules absent | нет |
| Alpaca live env | two positions; two matching static stops | нет |
| Web ping | 200 | нет |
| Research supervisors | 5/5 healthy | нет |
| Retest3 code trace | wrong/no stop env binding | нет |
| OSS inventory | VectorBT/Optuna already installed research-only | нет |

## Артефакты этого среза

- `reports/CODEX_ANTICRISIS_VISION_2026_08_10.md`
- `reports/CODEX_ANTICRISIS_ROADMAP_2026_08_10.md`
- `reports/CODEX_PROJECT_VISUAL_MAP_2026_08_10.md`
- `reports/CODEX_HANDOFF_AND_DIARY_2026_08_10.md`

## Продолжение работ — 13:05–13:12 UTC

Первичный read-only срез выше больше не является текущим состоянием. Стабильные
точки входа теперь:

- `reports/CURRENT_HANDOFF.md`;
- `reports/current_project_state.json`;
- `reports/CURRENT_PROJECT_ROADMAP.md`.

### RUNNER TP1 доставлен в live

Собран deterministic atomic bundle из revision
`c5eba1ccb244584bb432dd902d22599290fca900`, включающего `f290463`. Archive
SHA256: `5c7b4be781aed95b5df9f9f2a38b5912b70a1d523ade7896806b329490702e46`.

Вне live-каталога server Python прошел import/py_compile и bounded no-order
startup smoke. Direct Bybit flat подтвержден трижды до deploy и еще раз после.
Bundle применен при остановленном service атомарно с автоматическим rollback:

- backup: `/root/by-bot/backups/atomic_live_c5eba1ccb244_20260810T130547Z`;
- receipt:
  `/root/by-bot/runtime/deploy_receipts/atomic_live_c5eba1ccb244_20260810T130547Z.json`;
- live manifest: `6/6 PASS`;
- service: active, post-deploy PID при проверке `2276002`;
- authority не расширена: ATT1 short-only `risk_mult=0.10`, остальные risk zero.

Добавлены повторно используемые инструменты:

- `scripts/build_atomic_live_bundle.py`;
- `scripts/verify_atomic_live_bundle.py`;
- `scripts/staged_live_import_smoke.py`;
- `scripts/apply_staged_live_bundle.py`;
- focused tests для builder/apply.

### Retest3 no-op устранен

Старые процессы exact ladder остановлены, официальные пять research supervisors
не затронуты. `scripts/retest3_stop_ladder.sh` теперь использует реальную ручку
`IRV3_STOP_BUFFER_ATR`, preflight четырех конфигураций, чистые теги и
proof-of-difference gate. Дешевый 90d smoke дал `0/0/1/1` сделки; audit корректно
запретил интерпретацию. Это `RESULT NOT PROVEN`, а не FAIL стратегии.

Focused suite: `18 passed`.

Повторная проверка задачи `sloped_break_retest_v1` показала, что ms/sec patch
уже присутствует: `_retest_expiry_ms()` сохраняет миллисекундную шкалу, два
focused tests проходят, history файла указывает на `2d04e3f`. Roadmap обновлен:
дальше требуется reachability/geometry/shadow proof, а не повторная правка.

### Research station и Alpaca

Research station: `5 healthy / 0 degraded`, все процессы research-only без
права ордеров. Прямая Alpaca dry-run сверка в 13:11 UTC: market closed,
account not blocked, две позиции и два защитных ордера. Direct account report
в 13:16 UTC: equity `$484.74`, cash `$391.27`, stop coverage `2/2`. Для SCHW
планируется монотонный raise stop `96.47 -> 103.07165` с точным fractional qty
`0.563776973`; broker mutation не выполнялась.

В 13:30 UTC market-open dry-run повторен: `market_open=true`, account not
blocked, positions/orders `2/2`. SCHW plan обновился до монотонного raise
`96.47 -> 103.4673`, protected qty по-прежнему точно `0.563776973`, lock около
`+1.886%` к entry. Broker replace не отправлен, потому что явная
protective-only apply-authority не задана.

Финальная Bybit direct check в 13:31 UTC: service active с PID `2276002`,
broker flat, heartbeat fresh, `open_trades=0`, authority complete, единственный
money sleeve `att1` с `risk_mult=0.10`.

## Продолжение работ — 14:39–14:46 UTC

### Alpaca protective loop доведен до broker receipt

Server cron показал, что protective manager уже вызывается каждые 15 минут и
имеет durable authority `PROTECTIVE_EXITS_ONLY`. После прежнего исправления
fractional `qty` broker выявил второй contract defect: stop `105.0306`
отвергался как sub-penny. По официальному price-grid contract добавлено
округление sell stop вниз: 2 decimals при цене >= `$1`, 4 ниже `$1`.

Проверки: server stage compile/contract PASS, локально `26 passed`. Два файла
заменены атомарно с backup
`/root/by-bot/backups/alpaca-protection-20260810T1445Z`:

- `scripts/alpaca_protective_exit_manager.py` SHA256
  `a54fb471aee3f0272174e96044c78c2a9f19b133e73184583d88339c487e3b9e`;
- `scripts/run_alpaca_adaptive_paper.sh` SHA256
  `77290ea731b34329648e90d97a403d22a851fbafbca2650c1485fe3dafd111fa`.

14:44 UTC dry-run дал target `105.03`; apply receipt принят Alpaca. Прямой
broker-read: SCHW order `27473b37-9c6d-4a2c-b3a9-493c04cef21b`, status `new`,
qty `0.563776973`, stop `105.03`, TIF `day`; ABBV stop `235.17`; account equity
`$485.87`, cash `$391.27`, coverage `2/2`. Покупок/ротаций/market-close не было.

Paper launcher теперь отключает routine Telegram по умолчанию, сохраняя paper
orders, receipts и logs. Read-only worktree inventory: `1,138` paths, из них
`27` tracked и `1,111` untracked; массовой очистки не выполнялось.
