# CODEX HANDOFF — 2026-07-04 PM

Цель ближайшего цикла: не писать новые модули ради модулей, а довести портфель до 2–3 доказанных live-рукавов. Текущий live-рукав уже есть (`ATT1 r001`), но он редкий. Нужны: телеметрия, второй крипто-рукав, чистый FX/CFD research и сбор уникальных данных.

## Что реально live сейчас

- Bybit live account funded: последний подтверждённый equity около `1019 USDT`.
- `bybot.service=active`, `dry_run=false`, `trade_on=true`, `open_trades=0`.
- Единственный денежный рукав: `ATT1 short r001`, `ATT1_RISK_MULT=0.10`, `MAX_POSITIONS=3`.
- ATT1 — это short-only отбой/касание наклонного сопротивления, не горизонталки и не пробой.
- Молчание ATT1 сейчас не является freeze: основная причина reject — нет валидной short trendline.
- `flat/range/ivb1/midterm/bounce/breakdown` видны в коде, но `risk_mult=0.0`, деньгами не торгуют.

## Что сделано сегодня на сервере

- ATT1 telemetry включена в `configs/att1_short_r001_canary_20260702.env`:
  - `ATT1_DECISION_BUS_ENABLE=1`
  - `ATT1_EDGE_MONITOR_ENABLE=1`
  - `ATT1_EDGE_INTERVAL_SEC=900`
  - `DECISION_BUS_PATH=runtime/decision_bus.jsonl`
  - `ATT1_EDGE_HEALTH_PATH=runtime/att1_edge_health.json`
  - `ATT1_EDGE_BASELINE_EXPECTANCY_R=0.054`
- Перед рестартом проверено `open_trades=0`; после рестарта `bybot.service=active`.
- `edge_monitor` alert-only; он не должен сам останавливать торговлю. Автостоп остаётся за breaker.
- Orderbook density collector поставлен на сервер точечно без `git pull`, потому что server worktree грязный.
- Collector запущен в `screen=orderbook_density_20260704` рядом с liquidation collector.
- Подтверждено, что `runtime/orderbook/bybit_densities.jsonl` начал наполняться. Первые строки уже есть.

## Важный баг, найденный перед деплоем collector

- `scripts/collect_bybit_orderbook_density.py --help` падал из-за `%` в `argparse` help.
- Исправлено локально: `%` экранирован как `%%`.
- Добавлен тест `test_parser_help_formats_percent_sign`.
- Локально: `tests/test_orderbook_density_collector.py` → `6 passed`.
- На сервере после установки: `tests/test_orderbook_density_collector.py` → `6 passed`.

## FX/CFD research — актуальный статус

Старый FX H1 runner был остановлен как неэффективный: он висел на тяжёлом setup и не доходил до главного кандидата.

Найден и исправлен performance-баг:

- `bot/fx_harness.py`: setup теперь получает precomputed `atr_value`, если явно поддерживает этот аргумент.
- `bot/fx_setups.py::round_level_sweep`: принимает `atr_value` и не пересчитывает ATR на каждом баре.
- Это убрало O(n²)-поведение на длинной H1 истории.
- Тесты: `tests/test_fx_harness.py tests/test_fx_harness_fast_equivalence.py tests/test_fx_setups.py tests/test_fx_cost_feasibility.py` → `20 passed`.

Ускоренный H1 round sweep завершён:

- Output: `reports/research/fx_h1_round_sweep_20260704_fast/`
- EURUSD/GBPUSD дают красивые PF только на tiny-N (`3–8 trades`) — не использовать.
- USDJPY H1 даёт слабый research-pulse:
  - лучшие строки около `30 trades`, `+5.98R`, `PF≈1.26`, `3/4 folds+`
  - preflight всё ещё `False` из-за тонкого fold / недостаточной устойчивости.
- XAUUSD H1 заблокирован coverage gate:
  - `coverage=0.933627`, `494 gaps`, `gap_over_35_bars`
  - XAU не пересматривать до backfill/clean cache.

Вывод: FX round sweep не live-grade, но USDJPY заслуживает отдельного расширения истории/параметров/quality filter. XAU сначала чистить данные.

## Research decisions — не возвращать в live без нового PASS

- ARS1/range: dynamic range picker `216/216`, `0 PASS`; live запрещён.
- ARF2 failed-breakout: OOS-symbol gate провален (`-15.48R`, `PF 0.83`); не повторять post-hoc pockets.
- ATT1 long-only: около нуля; не включать “для активности”.
- Raw crypto BOS/CHoCH и raw FX range-fade: отрицательные/неустойчивые; только как компоненты после фильтров.

## P0 queue

1. Проверить live после включения ATT1 telemetry:
   - `runtime/decision_bus.jsonl`
   - `runtime/att1_edge_health.json`
   - heartbeat: `open_trades`, `dry_run`, `regime`, `att1_* counters`
2. Следить, что `orderbook_density_20260704` жив и JSONL растёт.
3. Запустить серверный `cascade real-data gate` на реальном `runtime/liquidations/*.jsonl`, не на proxy.
4. Прогнать ATT1 universe expansion по prereg, без подбора монет после результата.
5. FX:
   - backfill/clean XAU H1;
   - USDJPY round sweep расширить/проверить deeper OOS;
   - не гонять тяжёлые FX setup без performance sanity.

## Процессные правила

- `git pull` на сервере сейчас не делать вслепую: server worktree грязный и старее локального HEAD.
- Серверные изменения — точечно, с бэкапом, без тяжёлых research jobs рядом с live.
- Любой второй live-рукав: только после coverage/cost gate → preflight → OOS/wf → breaker+expiry → tiny risk.
- Screening ≠ gate. Tiny-N PF не является кандидатом.
- Новый чат не должен начинать “ревью всех стратегий заново”; сначала читать ledger tail и этот handoff.
