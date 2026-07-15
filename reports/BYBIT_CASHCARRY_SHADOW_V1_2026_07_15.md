# Bybit cash-and-carry shadow v1 — операторская записка

Дата: 2026-07-15
Статус: **RESEARCH ONLY / DISABLED / НЕ ДОКАЗЫВАЕТ EDGE / НЕ УМЕЕТ ТОРГОВАТЬ**

## Что теперь реально есть

Собран изолированный детерминированный движок для одной конструкции: **long spot + short USDT linear perpetual на Bybit с равным долларовым номиналом ног**. Он принимает только нормализованные публичные котировки и завершённые funding-события.

Модель включает:

- вход только после минимум трёх различных завершённых положительных funding-наблюдений;
- четыре исполнимых paper-fill: spot buy по ask, perp short по bid, spot sell по bid, perp cover по ask — каждый с неблагоприятным slippage;
- отдельные комиссии spot и perp на каждом fill;
- funding только после фактического settlement timestamp; событие после входа без близкого по времени публичного perp-price proxy не начисляется, а блокируется;
- P&L двух ног, изменение basis, остаточный delta drift, execution cost, fees, funding и итоговый net P&L;
- выход при funding flip, расширении basis против позиции, чрезмерном абсолютном basis, delta drift или max hold;
- отказ при stale/skewed/crossed/missing quote и недостаточном top-of-book объёме; частичный fill не выдумывается;
- checksum receipt ровно с четырьмя fills; JSONL ledger append-only, identical replay идемпотентен, конфликт одного cycle id блокируется.

В коде отсутствуют чтение `.env`/ключей, приватный API и order endpoints. Единственный opt-in network adapter допускает GET только к публичным:

- `/v5/market/orderbook`
- `/v5/market/tickers`
- `/v5/market/funding/history`

## Безопасный запуск

Preflight без сети и без записи:

```bash
.venv/bin/python scripts/run_bybit_cashcarry_shadow_v1.py
```

Детерминированный synthetic replay (только in-memory shadow):

```bash
.venv/bin/python scripts/run_bybit_cashcarry_shadow_v1.py replay \
  --input tests/fixtures/bybit_cashcarry_shadow_v1_replay.json \
  --enable-research-shadow \
  --receipt-ledger runtime/research/bybit_cashcarry_shadow_v1/cycles.jsonl
```

Один публичный snapshot без запуска state machine:

```bash
.venv/bin/python scripts/run_bybit_cashcarry_shadow_v1.py snapshot \
  --symbol BTCUSDT \
  --allow-public-network
```

Без `--enable-research-shadow` replay не открывает даже бумажную позицию. Snapshot не сохраняет state и не является коллектором.

## Что показал fixture

Fixture проверяет механику, а не доходность: после трёх положительных settlements открывается одна бумажная пара, следующее положительное funding начисляется, затем отрицательное funding начисляется и вызывает exit. Receipt содержит ровно четыре fill. Итог synthetic-цикла около **−$0.431 на $100 каждой ноги** после spread/slippage/fees/funding. Отрицательный результат здесь полезен: он подтверждает, что издержки не спрятаны и «арбитражная прибыль» не рисуется автоматически.

## Чего v1 намеренно не делает

- нет долговечного collector/daemon и restart-safe состояния открытого paper cycle;
- нет quantization по реальным lot step/tick size/min notional;
- нет walk по нескольким уровням книги и recovery частичного fill;
- нет account/margin/liquidation/transfer/reconciliation модели;
- fee tier задан консервативными prereg-константами, а не broker receipt;
- публичные REST snapshots не атомарны; чрезмерный timestamp skew только блокируется;
- точный settlement mark Bybit funding history не отдаёт, поэтому нужен near-time публичный perp-mid proxy;
- нет разрешения на live и нет основания переносить/добавлять капитал.

## Следующий честный gate

1. Добавить однописательский public collector с durable observation/state log и контролируемым restart-replay.
2. Добавить public instruments-info receipt и quantization, затем multi-level book walk.
3. Собрать минимум 10 закрытых paper cycles — только для проверки механики и recovery.
4. Для проверки edge: минимум 30 закрытых cycles на минимум трёх ликвидных монетах; median и p25 net P&L должны быть положительными в base и stress-cost сценариях, без концентрации на одной монете.
5. Даже PASS этого экрана даёт только ручной review, не автоматическое разрешение live.

Замороженный контракт: `configs/preregistered/bybit_cashcarry_shadow_v1_20260715.json`.
