# Bitget cash-carry public adapter v1

Дата: 2026-07-16  
Статус: **PREFLIGHT READY / NORMALIZATION ONLY / NOT STATION-COMPATIBLE / NO LIVE AUTHORITY**

## Итог

Добавлен отдельный Bitget-native public adapter и schema contract. Он сознательно не меняет frozen Bybit v2, не создаёт `PublicMarketSnapshotV2` и никогда не маркирует Bitget payload как `bybit_public_v5`.

Immutable identity:

- adapter: `bitget_public_v2_cashcarry_v1`;
- exchange: `bitget`;
- source: `bitget_public_v2`;
- snapshot: `bitget_public_cashcarry_snapshot_v1`;
- station compatibility: `BLOCKED_SEPARATE_SOURCE_ENGINE_REQUIRED`.

## Public data contract

Runner допускает HTTPS GET только к `api.bitget.com` и семи точным public paths:

1. spot symbols;
2. spot unmerged orderbook;
3. USDT perpetual contracts;
4. USDT perpetual unmerged depth;
5. current funding;
6. historical funding;
7. server time, который запрашивается последним.

Неизвестные/повторные query keys, другой host/path, URL credentials и private/account/order paths блокируются до HTTP-вызова. `.env`, API key/sign/passphrase, account, balance, position, order, transfer и withdrawal кода нет.

Контракт основан только на официальных схемах Bitget: [spot symbols](https://www.bitget.com/api-doc/spot/market/Get-Symbols), [spot orderbook](https://www.bitget.com/api-doc/spot/market/Get-Orderbook), [contract config](https://www.bitget.com/api-doc/contract/market/Get-All-Symbols-Contracts), [perpetual depth](https://www.bitget.com/api-doc/contract/market/Get-Merge-Depth), [current funding](https://www.bitget.com/api-doc/contract/market/Get-Current-Funding-Rate), [funding history](https://www.bitget.com/api-doc/contract/market/Get-History-Funding-Rate), [server time](https://www.bitget.com/api-doc/common/public/Get-Server-Time).

## Нормализация

- spot tick: `10^-pricePrecision`;
- spot quantity step: `10^-quantityPrecision`;
- официальный `minTradeAmount` помечен Bitget как obsolete, поэтому минимальная положительная base quantity выводится только как один quantity step, а реальный минимум проверяется отдельно через `minTradeUSDT`;
- perpetual tick: `priceEndStep × 10^-pricePlace`, обязательно совпадает с `scale0` book scale;
- perpetual step/minimum: `sizeMultiplier` / `minTradeNum`;
- contract `fundInterval` обязан совпасть с current `fundingRateInterval`;
- spot должен быть `online`, perpetual — `normal`, `perpetual`, USDT-quoted и USDT-margined;
- книги должны быть causal, уникальными, отсортированными, не crossed и tick-aligned;
- funding history дедуплицируется по timestamp и сортируется по возрастанию;
- public perp-mid используется как settlement price proxy только при lag не более 120 секунд;
- public default `takerFeeRate` сохраняется как evidence, но не считается account-specific fee receipt.

## Почему это ещё не station

Frozen Bybit journal детерминированно проверяет source `bybit_public_v5` и Bybit-specific receipts. Ослаблять эту проверку ради Bitget было бы опасной ложной parity.

Перед Bitget station нужны:

1. отдельный Bitget hash-chain journal/replay;
2. Bitget-native common-quantity book-walk и economics engine;
3. account-specific fee-tier receipt;
4. margin/liquidation/transfer/outage/reconciliation/two-leg recovery contract;
5. 10 закрытых public paper cycles для mechanics и 30 cycles / 3 liquid symbols для ручного edge review.

Точный blocker receipt: `reports/research/bitget_cashcarry_public_v1_20260716/blocker_receipt.json`.

## Безопасные команды

No-network/no-write preflight:

```bash
.venv/bin/python scripts/run_bitget_cashcarry_public_v1.py preflight
```

Offline fixture parity:

```bash
.venv/bin/python scripts/run_bitget_cashcarry_public_v1.py normalize-fixture
```

Опциональный одиночный public normalization probe, не journal и не trading:

```bash
.venv/bin/python scripts/run_bitget_cashcarry_public_v1.py collect-once \
  --symbol BTCUSDT \
  --allow-public-network \
  --acknowledge-normalization-only
```

В этой сессии Bitget network probe не запускался.

## Проверка

Bitget focused: `13 passed`.  
Совместно Bitget + station + frozen Bybit v1/v2: `46 passed in 0.70s`.

Проверены official-shape fixture, precision/minimum/fee/funding normalization, deterministic observation hash, schema drift, status, interval, scale, off-tick и causal-time refusal, строгий URL/query allowlist, explicit network opt-ins и физическая несовместимость с Bybit snapshot/journal.

Frozen Bybit v2 spec остался неизменным: `f2b9b7b7e24a42074333b115d61a461ded3ebe34c3879284cb82055a38e08246`.
