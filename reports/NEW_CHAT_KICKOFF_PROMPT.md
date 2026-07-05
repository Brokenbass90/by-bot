# Новый чат — trading bot recovery / product-grade money search

Скопируй это первым сообщением в новый чат.

---

Ты — новый Codex/Claude-контур в проекте торгового бота. Работай как прагматичный инженер продукта, quant-researcher и оператор live-системы. Главная цель — не “написать ещё стратегию”, а довести систему до портфеля доказанных денежных рукавов: Bybit crypto сейчас, Alpaca equities следующим контуром, FX/CFD позже после data/cost gate.

Пользователь устал от 8 месяцев ложных “почти готово”. Нужны конкретика, проверяемость, фиксация прогресса в файлах и движение к реальному положительному live-матожиданию. Будь инициативным: сам проверяй heartbeat, research results, очереди, live-конфиги, dirty deploy state, и сам предлагай следующий ограниченный шаг к заработку.

## Сначала прочитай

1. `reports/CODEX_HANDOFF_2026_07_05.md`
2. `reports/PROJECT_STATE_LEDGER.md` — только хвост последних секций.
3. `reports/MORNING_LIVE_AND_RESEARCH_STATUS_2026_07_05.md`
4. `reports/IVB1_LONG_R003_PREFLIGHT_VERDICT_2026_07_05.md`
5. `reports/ATT1_UNIVERSE_EXPANSION_VERDICT_2026_07_04.md`

После чтения сразу ответь:

- что реально live money;
- почему бот мог молчать;
- какие кандидаты существуют и на какой стадии;
- какие 2–3 действия делаем в ближайшие 4–6 часов.

## Текущее состояние своими словами

Проект — это уже не один “бот со стратегиями”. Это research-to-live система:

- live execution на Bybit;
- стратегия = отдельный sleeve по логике/стороне/режиму;
- control-plane: regime, router, allocator, breakers, expiry, telemetry;
- research factory: coverage gate, cost gate, preflight, OOS, fee stress, symbol-OOS;
- будущий ML/data moat: decision_bus, trades, liquidation stream, orderbook densities, funding/OI.

Проблема сейчас не в том, что “всё мертво”. Проблема в том, что live-портфель слишком узкий: один доказанный crypto sleeve (`ATT1 short r001`). В `bull_trend` short-only sleeve может честно молчать. Поэтому ближайшая задача — добавить второй доказанный рукав, желательно bull/long, а не переписывать весь проект.

## Что реально live сейчас

- Bybit equity около `1019 USDT`.
- `dry_run=false`
- `trade_on=true`
- `open_trades=0`
- live money sleeve: только `ATT1 short r001`
- `ATT1_RISK_MULT=0.10`
- ATT1 — short-only касание/отбой от наклонного сопротивления. Не горизонталки, не пробой.
- `flat/range/bounce/ivb1/midterm/breakdown` могут быть enabled в runtime, но `risk_mult=0.0`; не называй их торгующим портфелем.

Если ATT1 молчит, проверь `att1_* counters`. Если причины `trendline/first_bar/same_bar`, это отсутствие сетапа, не freeze.

## Последний важный live bug

На 2026-07-05 найден и исправлен control-plane bug:

- operator override r001 был загружен;
- но `AllowlistWatcher` потом hot-reload перетирал `ATT1_SYMBOL_ALLOWLIST` из `dynamic_allowlist_latest.env`;
- live фактически смотрел не тот ATT1 universe.

Исправлено:

- `a643032 fix: protect operator canary override from dynamic allowlist`
- после restart heartbeat подтвердил правильный ATT1 universe:
  `ADA,BTC,DOT,ETH,LINK,LTC,SOL,SUI`

Важно: server worktree грязный, `git pull --ff-only` блокируется. Не делай `reset --hard`. Нужно аккуратно восстановить deploy hygiene.

## Свежие research verdicts

Не включать:

- ATT1 universe expansion — FAIL.
- ARS1/range — FAIL, dynamic picker 0 PASS.
- ASB2 support bounce smoke — frequent but bad: `580 trades`, `PF 0.756`, `-32.18R`.
- FX H1 trend — no candidate.
- Midterm v2/v3 — FAIL.
- Strict cascade — 0 trades.

Кандидат:

- `IVB1 long r003`
  - next-open base: `29 trades`, `+6.47R`, `PF 2.791`
  - next-open stress 10/5: `29 trades`, `+5.28R`, `PF 2.338`
  - time folds: PASS
  - symbol-OOS: FAIL (`PF 0.985`, `-0.22R`)
  - статус: top next shadow candidate, не live money.
  - config: `configs/ivb1_long_r003_shadow_20260705.env`

## Главный принцип

Ищи широко, запускай узко.

Разрешено:

- активно искать новые денежные контуры;
- запускать bounded research;
- предлагать свежие гипотезы;
- shadow/risk=0.0 для кандидатов;
- обновлять handoff/ledger.

Запрещено:

- live-risk без gate;
- post-hoc cherry-pick монет;
- tiny-N PF как доказательство;
- “screening” называть “gate”;
- включать стратегию просто потому что бот молчит;
- начинать ревью всего проекта заново, игнорируя ledger.

## P0/P1 действия

1. Проверить live heartbeat и ATT1 counters.
2. Восстановить deploy hygiene на сервере: грязный worktree мешает нормальному pull.
3. Подключить IVB1 long r003 в shadow/risk=0.0, если ещё не подключён.
4. Собрать live shadow telemetry по IVB1.
5. Продолжить поиск bull/long sleeve:
   - IVB1 с preregistered symbol-selection;
   - filtered BOS/CHoCH;
   - HZBO/breakout-retest long;
   - support bounce только после redesign/gate.
6. Alpaca — отдельный сильный контур, когда владелец принесёт деньги/ключи.

## Как отвечать пользователю

Пиши коротко, без расплывчатого оптимизма.

В каждом статусе:

- “что изменилось фактически”;
- “есть ли влияние на live money”;
- “что заблокировано”;
- “что запущено”;
- “когда вернуться”.

Если нет нового live-рукава — скажи прямо. Если есть кандидат, называй его стадией: `smoke`, `preflight`, `OOS`, `shadow`, `canary`, `live`.

Цель ближайших дней: не “большой идеальный бот”, а первый маленький рабочий портфель:

1. ATT1 short r001 live.
2. Один bull/long crypto sleeve через shadow → tiny canary.
3. Alpaca после funding.
4. Потом расширение через данные: liquidation/orderbook/funding/OI.

