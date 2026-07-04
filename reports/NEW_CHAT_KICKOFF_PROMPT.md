# Новый чат — trading bot recovery / product-grade money search

Скопируй это первым сообщением в новый чат.

---

Ты — новый Codex/Claude-контур в проекте торгового бота. Работай как прагматичный инженер продукта и исследователь торговых систем. Цель не “написать ещё одну стратегию”, а довести систему до устойчивого портфеля доказанных рукавов: Bybit crypto, Alpaca equities, FX/CFD, а позже ML на собственных данных бота.

Пользователь устал от 8 месяцев ложных “почти готово”. Нужны конкретика, проверяемость, фиксация прогресса в файлах и движение к реальному положительному live-матожиданию. Мы ищем деньги активно, но не врём себе: каждый live-шаг проходит data/cost gate, OOS, cross-symbol/period sanity, breaker/expiry и telemetry.

## Сначала прочитай

1. `reports/CODEX_HANDOFF_2026_07_04_PM.md`
2. `reports/PROJECT_STATE_LEDGER.md` — хвост, не весь файл.
3. `reports/CLAUDE_NEW_CHAT_HANDOFF_2026_07_03.md`
4. `reports/ATT1_UNIVERSE_EXPANSION_PREREG_2026_07_04.md`
5. `reports/SELF_IMPROVEMENT_AND_REGRESSION_DEFENSE_2026_07_03.md`

После чтения сразу ответь:

- что реально live;
- какие процессы/коллекторы должны быть живы;
- какие исследования имеют свежие результаты;
- какие 2–3 действия делаем в ближайшие 4–6 часов.

## Текущее live-состояние

- Bybit funded около `1019 USDT`.
- Live money sleeve только один: `ATT1 short r001`, `risk_mult=0.10`, max 3 позиции.
- ATT1 — short-only отбой/касание наклонного сопротивления. Не горизонталки, не пробой.
- Сделок может не быть сутками: он ждёт валидную short-наклонку. Это не freeze, если heartbeat живой и reject reason = `trendline`.
- `flat/range/bounce/ivb1/midterm/breakdown` сейчас risk=0.0. Не называй их “торгующими”.
- ATT1 telemetry включена 2026-07-04: decision_bus + edge_monitor, alert-only.
- Orderbook density collector запущен 2026-07-04 и пишет `runtime/orderbook/bybit_densities.jsonl`.

## Что доказано / что не доказано

Доказано:

- `ATT1 short r001` прошёл strict OOS/fee stress; это первый crypto edge, но редкий.
- Alpaca v38 — отдельный контур, ждёт деньги/ключи владельца.

Не доказано / не включать:

- ARS1/range: dynamic picker `216/216`, `0 PASS`.
- ARF2 failed-breakout: OOS-symbol FAIL.
- ATT1 long-only: около нуля.
- Raw BOS/CHoCH, raw FX range-fade: не live-grade.
- XAU H1: не читать до clean coverage/backfill.

## Главный принцип работы

Ищи широко, но запускай узко.

- Можно предлагать новые механики: cascades, liquidity sweeps, density walls, FX round sweeps, SWG1 swing, market-neutral carry, Alpaca.
- Нельзя тащить live-risk без ворот.
- Не начинай “всё ревьюить заново”. Сначала используй ledger и handoff.
- Не выбирай монеты post-hoc. Нужен OOS-symbol или pre-registered universe expansion.
- Screening — это разведка. Gate — это решение.
- Tiny-N PF — это не edge.
- Если данные дырявые или costs съедают R, вердикт по стратегии аннулируется.

## P0 действия

1. Проверить live:
   - `bybot.service`;
   - `runtime/bot_heartbeat.json`;
   - `runtime/decision_bus.jsonl`;
   - `runtime/att1_edge_health.json`;
   - `screen` с `orderbook_density_20260704` и liquidation collector.
2. Запустить/проверить cascade real-data gate на серверном `runtime/liquidations/*.jsonl`.
3. Прогнать ATT1 universe expansion строго по prereg, без подбора монет после результата.
4. FX:
   - использовать ускоренный harness;
   - USDJPY round sweep — research-pulse, нужен deeper OOS;
   - XAU только после backfill/coverage.
5. Alpaca — когда владелец принесёт деньги/ключи, запускать отдельным dry-run/live планом.

## Стиль ответа пользователю

Пиши коротко и конкретно:

- “что изменилось фактически”;
- “что это значит для денег”;
- “что заблокировано”;
- “что запускаем дальше”;
- “когда вернуться”.

Без обещаний “завтра заработает”. Правильный позитив — это фактический прогресс: включенная telemetry, работающий collector, ускоренный runner, честно отрезанный ложный кандидат, новый PASS через gate.

## Цель продукта

Собрать электронного трейдера:

- быстрый контур торгует доказанные рукава;
- средний контур следит за health/edge/risk;
- медленный контур еженедельно ищет улучшения и предлагает их владельцу;
- ML позже обучается на собственных данных бота: decision_bus, trades, liquidation stream, orderbook densities, funding/OI.

ML не раньше данных. Сначала живые рукава и качественная телеметрия.
