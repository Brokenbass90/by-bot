# Bybit cash-and-carry shadow v2 — durable public mechanics

Дата: 2026-07-15
Статус: **RESEARCH ONLY / DEFAULT DISABLED / NO LIVE AUTHORITY / EDGE НЕ ДОКАЗАН**

## Итог

Замороженный v1 не изменён. Вокруг него добавлен v2-слой, который закрывает следующий ограниченный инфраструктурный этап:

- получает только публичные Bybit market-data receipts;
- фиксирует реальные `tickSize`, `qtyStep`, `minOrderQty`, `minOrderAmt/minNotionalValue` и `fundingInterval`;
- выбирает одну общую базовую quantity для spot и linear perp, округляя вниз до общего шага обеих ног;
- детерминированно проходит несколько уровней книги в ценовом приоритете;
- либо подтверждает полный объём обеих ног, либо отказывает целиком до изменения paper-state;
- перед открытием требует, чтобы консервативный funding до `max_hold` покрывал четыре комиссии, фактический walked spread/slippage, basis-stress и минимальный остаточный запас;
- хранит observation, v2-план, economics gate, шаг frozen-v1 и состояние открытого цикла одной checksummed JSONL-записью;
- после restart полностью проигрывает журнал и требует байтово-эквивалентного решения/state;
- одинаковый observation повторно не пишет; конфликт одного symbol/timestamp блокируется.

Это не daemon и не торговый executor. Никакой процесс не запущен, сеть в ходе проверки не использовалась, live/VPS не менялись.

## Экономический gate

Формула до открытия paper-cycle:

`min(projected funding, последние обязательные completed rates) × число settlements до max_hold`

должно быть не меньше:

`walked round-trip spread/slippage + 2×spot fee + 2×perp fee + 10 bps basis stress + 5 bps edge reserve`.

При frozen v1 параметрах абсолютная нижняя граница ещё без bid/ask spread составляет:

- fees: `2×10 + 2×5.5 = 31 bps`;
- четыре slippage: `4×2 = 8 bps`;
- basis stress: `10 bps`;
- минимальный запас: `5 bps`;
- итого минимум: **54 bps + реальный book spread/depth impact**.

Для 14 дней и funding раз в 8 часов максимум 42 settlement. По свежему публичному экрану этой сессии:

| Символ | Rate за settlement | Условный carry за 42 settlements | Вердикт до учёта spread |
|---|---:|---:|---|
| XRPUSDT | 0.0076% | 31.92 bps | FAIL |
| BTCUSDT | 0.001875% | 7.875 bps | FAIL |
| ETHUSDT | 0.002511% | 10.5462 bps | FAIL |
| SOLUSDT | persistence не подтверждён | — | FAIL |

Это оптимистичная верхняя оценка при неизменной ставке все 14 дней, а не прогноз. Уже она ниже 54 bps. Следовательно, текущие ставки нельзя превращать даже в paper-open лишь потому, что они положительные.

Synthetic fixture использует заведомо сильные `0.03%` за settlement, чтобы проверить механику. Там expected carry = 126 bps, а walked requirement около 86.95 bps; третий completed settlement открывает shadow, restart восстанавливает открытое состояние, отрицательный settlement закрывает его. Это тест механики, не доходность и не рыночный результат.

## Durable/recovery контракт

Один journal record включает:

1. нормализованный multi-level snapshot и instrument receipt;
2. observation SHA-256;
3. exact common-quantity execution plan или явную причину отказа;
4. break-even economics receipt;
5. frozen-v1 step/receipt;
6. состояние после шага, включая активный quantized open plan;
7. номер sequence, hash предыдущей записи и checksum текущей.

Файл и lock создаются с mode `0600`, запись выполняется одним writer под `flock`, каждый append завершается `fsync`. Оборванный tail, повреждённый checksum, разрыв hash-chain, изменение config или недетерминированный replay блокируют recovery.

## Public-only и безопасный default

Default preflight подтвердил:

- collector disabled;
- shadow disabled;
- network calls = false;
- daemon started = false;
- environment/key reads = false;
- private API = false;
- broker/execution authority = false.

Единственный opt-in HTTP adapter допускает метод `GET` только к:

- `/v5/market/instruments-info`;
- `/v5/market/orderbook`;
- `/v5/market/tickers`;
- `/v5/market/funding/history`.

Нет `.env`, API key/secret, account/position/order/transfer/withdrawal endpoint или POST-кода.

## Проверка

Focused v2:

```text
11 passed in 0.10s
```

Совместно frozen v1 + v2:

```text
25 passed in 0.16s
```

Проверены:

- disabled/no-write default;
- common-grid quantization;
- проход двух уровней каждой книги;
- отказ при недостаточной глубине без partial fill;
- tick и minimum-notional refusal;
- fail-closed economics на текущеподобном положительном funding;
- append-only open/close state;
- restart recovery;
- duplicate idempotency;
- torn/tampered journal refusal;
- parsing public instruments-info;
- строгий URL/method allowlist и отсутствие execution authority.

## Оставшиеся блокеры

1. V2 пока библиотека и single-shot/offline runner; durable daemon намеренно не создан и не запускался.
2. Frozen v1 receipt использует equal USD notional ног, а v2 executable-plan — одну common base quantity. Оба состояния записаны явно, но exact P&L parity пока не заявляется.
3. Нет account fee-tier receipt, balance/margin/liquidation/transfer/reconciliation/outage модели.
4. Partial fills не восстанавливаются — они fail-closed запрещены до paper-state. Для live-дизайна потребуется отдельная двухногая recovery state machine.
5. REST snapshot не атомарен; stale/skew по-прежнему обязан блокироваться.
6. Локальная hash-chain без внешнего anchor не доказывает отсутствие удаления корректного хвоста.
7. Нет 10 закрытых public paper cycles для mechanics evidence и тем более 30+ циклов/3 symbols для edge screen.

## Разрешённый следующий этап

После code review можно отдельно спроектировать безопасный public collector schedule с lifecycle receipt и external journal anchor. Он не должен включать shadow-open по текущим ставкам: economics gate ожидаемо оставит их в `observe/refuse`. Сначала нужен сбор реальных funding persistence, walked depth и cost receipts; капитал и live permission не требуются.

Замороженный v2 контракт: `configs/preregistered/bybit_cashcarry_shadow_v2_20260715.json`.
