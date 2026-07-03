# HANDOFF ДЛЯ НОВОГО ЧАТА — START HERE (2026-07-03, evening)

Чат переполнен. Новый ассистент должен начать отсюда, не с нуля. Код, тесты и reports — настоящая память проекта.

Роль: прагматичный антикризисный инженер/со-основатель. Цель — довести бота до реального положительного live-матожидания. Не обещать деньги без OOS/live-доказательств. Не хоронить идеи без корректных данных. Сначала качество данных, потом стратегии.

## 0. Прочитать первым делом

1. `reports/PROJECT_STATE_LEDGER.md` — единая точка правды; читать хвост.
2. `reports/MASTER_MAP_AND_PLAN_2026_07_03.md` — карта технологий и фаз.
3. `reports/LIVE_FORENSICS_CANDLE_COVERAGE_2026_07_03.md` — почему range/pila нельзя размораживать без coverage.
4. `reports/ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md` — следующий P1 для единственного live-рукава.
5. `reports/ARF2_FAILED_BREAKOUT_OOS_SYMBOL_VERDICT_2026_07_03.md` — пример пойманного selection bias.
6. `reports/STRUCTURE_AND_FX_SCREENING_FAST_FAIL_2026_07_03.md` — raw BOS/FX fast-fail, но с важной поправкой ниже.

## 1. Live-статус

- Live crypto включён, `DRY_RUN=False`, глобального hard-block нет.
- Реальный live-risk сейчас только: `ATT1 short r001`, `risk_mult=0.10`.
- Сделок нет/мало — это ожидаемо для ATT1: он ждёт валидную short-наклонку. ATT1 не торгует горизонтальные уровни.
- Горизонтальные/range/pila/flat/bounce/ivb1/midterm сейчас должны оставаться `risk=0.0`, пока не пройдут data coverage + OOS.
- Серверный research сейчас не должен грузить live-VPS. На live-сервере живут bot/web/liquidation collector; тяжёлые sweep/WF — Mac или отдельный research-host.

## 2. Главная новость 2026-07-03: сначала данные, потом вердикты

Коммит `60af08f` добавил P0-защиту от ложных research-вердиктов:

- `bot/candle_coverage.py` + `tests/test_candle_coverage.py` — coverage gate: покрытие, гэпы, flat/dead bars, дубли, немонотонность. Для FX учитывает market closures/weekend как закрытие рынка, не как дырку.
- `bot/fx_harness.py::cost_feasibility()` + `tests/test_fx_cost_feasibility.py` — cost guard: если комиссия/слип в R слишком высоки, прогон помечается `cost_infeasible`, PF не читаем.
- Тесты после этого: `737 passed`.

Почему это критично:

- EURUSD M5 `PF=0.00` на 1111 сделках аннулирован как исследовательский вердикт: stop ≈ 2 pips, комиссия+slippage ≈ `1.78R` на сделку. Это не “рынок плохой”, это некорректный таймфрейм/стоимость относительно стопа.
- Live forensics ранее показал `missing_candles` 31/41 сделок; range = 20/20 `missing_candles`.
- Локальный замер кэша: EURUSD/AUDUSD M5 имеют 14.6–14.8% dead/flat bars; XAUUSD H1 coverage 93.4% и 494 gap. Поэтому XAU заслуживает re-screen после backfill, старые XAU-вердикты не считаем окончательными.

Жёсткое правило: любой новый screening/WF начинается с `candle_coverage` + `cost_feasibility`. Если данные/стоимость не проходят — стратегию не судим.

## 3. Что доказано и что не доказано

### Доказано/может жить

- `ATT1 short r001` — первый честный крипто-эдж:
  - strict rolling OOS 4/4 фолда;
  - 239+ сделок, не tiny-N;
  - fee/slippage stress выживает;
  - live уже стоит на risk 0.10.
- Alpaca v38 — бумажный/бэктест-контур с доказанным edge, ждёт $500 от владельца. Не смешивать с crypto live.

### No-go / не live

- ARF2 failed-breakout selected symbols выглядел хорошо, но OOS-symbol gate провалил: selection bias. Не canary.
- SpikeFade LINK short, InPlay V4, smart_grid, pair-arb/carry, raw H4-naive — не canary-grade.
- Raw structure_break/BOS/CHoCH screening был broadly negative. Вернуть можно только как композит с качественными фильтрами и после coverage/cost gate.
- FX range-fade на M5/EURUSD no-go вердикт аннулирован из-за cost/ATR issue; пересматривать на H1+clean data+cost guard.

## 4. P0/P1 очередь

### P0 — data coverage / backfill

1. Вписать `candle_coverage` в начало всех screening/WF:
   - crypto range/pila/bounce/flat;
   - FX/CFD;
   - XAU;
   - любые новые structure/range прогоны.
2. Backfill дырявых символов/таймфреймов до прохождения coverage gate.
3. Только после clean coverage:
   - rerun range/bounce repair на динамическом range scanner;
   - rerun FX H1/H4, особенно XAU и majors, через cost guard.

### P1 — ATT1 live observability

Реализовать wiring по `reports/ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md`:

- `ATT1_DECISION_BUS_ENABLE=0` default;
- `ATT1_EDGE_MONITOR_ENABLE=0` default;
- enter/skip/outcome в `decision_bus` с контекстом фактического риска, minqty fallback, breaker, stop_pct, regime;
- edge_monitor v1 только алертит, не автостопит. Единственный auto-stop остаётся breaker.

Цель: когда ATT1 наконец войдёт, мы должны видеть качество каждого решения и не спорить “почему он молчит/сливает”.

### P2 — clean re-screen после backfill

- Range/pila: только после 0% missing на canary-universe.
- FX: H1/H4, не M5 с микростопом; XAU round/sweep/session только на чистом кэше.
- ARF2/ASB2/ACB1: side-specific + symbol×side×regime, не общий bidirectional PF.

## 5. Что НЕ делать

- Не размораживать range/pila по TG RANGE scan. Scan = scout/universe, не сигнал и не gate.
- Не читать PF на дырявых свечах или cost-infeasible сетке.
- Не запускать тяжёлые свипы на live-VPS.
- Не повышать ATT1 risk до live-outcome подтверждения; сначала decision_bus/edge_monitor и 10–20 живых сделок.
- Не “архивировать навсегда” идеи только из-за старого кривого теста. Но live — только после чистого OOS.

## 6. Про ноут/локальные прогоны

Если Mac засыпает, локальные screen/background jobs обычно ставятся на паузу, а сетевые процессы/backfill могут отвалиться. Перед уходом:

- проверить `screen -ls`;
- если нужен ночной прогон — отключить sleep или запускать на research-host;
- вечером первым делом проверить, не умерли ли процессы, а не верить ожиданию “оно крутилось”.

## 7. Как говорить с владельцем

Тон: конкретно, без воды. Пользователь устал от 8 месяцев ложного прогресса. Нужно давать:

- что live сейчас реально торгует;
- что доказано;
- что заблокировано;
- какая следующая команда/проверка;
- когда вернуться.

Не подменять негатив “мотивацией”. Позитив сейчас не в красивых PF, а в том, что система начала ловить ложные вердикты до live: `missing_candles`, cost-infeasible M5, OOS-symbol selection bias.

## 8. Ответ на “когда вернуться”

Если запущен backfill/coverage + clean re-screen:

- через 4–6 часов — проверить статус backfill/coverage;
- если Mac спал — сначала `screen -ls`, затем лог последнего процесса;
- до clean coverage не ждать meaningful strategy verdict.

Следующий корректный milestone: clean coverage report + cost-feasible FX/crypto candidate list. Только после этого — новые OOS цифры.
