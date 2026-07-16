# Public cash-carry research station v1

Дата: 2026-07-16  
Статус: **RESEARCH ONLY / DEFAULT DISABLED / PUBLIC GET ONLY / LIVE AUTHORITY FORBIDDEN**

## Результат

Вокруг frozen cash-carry v2 добавлена отдельная долговечная исследовательская станция. Она не является торговым процессом и не получает ключей, баланс, позиции или право на ордер.

Станция:

- наблюдает `BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, SUIUSDT`;
- использует только четыре уже замороженных публичных Bybit V5 market-data path;
- хранит отдельный hash-chain/fsync journal на каждый символ, потому что frozen v2 engine моделирует один цикл;
- восстанавливает журналы после restart и сверяет checksummed lifecycle state;
- планирует обычный снимок раз в 30 минут и дополнительный снимок через 30 секунд после ближайшего `nextFundingTime`;
- при короткой ошибке после settlement повторяет попытку внутри frozen 120-секундного valuation window;
- применяет без изменения v2 gate: консервативный funding обязан покрыть walked spread/slippage, четыре комиссии, 10 bps basis stress и 5 bps остаточного edge;
- может открыть только локальный research-shadow cycle, никогда broker position;
- останавливается, не удаляя данные, через 7 суток, 2304 observations, 64 MiB на symbol, 512 MiB суммарно, при free disk ниже 80 GiB или после 24 часов полной недоступности источника;
- резервирует 1 MiB до каждого append, поэтому не пересекает cap одним неожиданно крупным record.

## Restart/resume

`station_state.json` записывается atomic replace + fsync и защищён SHA-256. На resume все per-symbol journals проигрываются заново, а durable count/hash сверяются с состоянием. Повторный процесс на том же root блокируется `flock`. Существующий root требует явный `--resume-existing`; terminal root нельзя оживить молча.

Detached launcher использует `screen`, а supervisor — `caffeinate` на macOS, если он доступен. Неожиданный process failure получает не более шести попыток restart; штатный completion/block не превращается в бесконечный цикл.

## Adapter boundary и Bitget

Есть явный `PublicCashCarryAdapter` protocol с immutable `adapter_id`, `exchange_id`, `source_id`, `public_only` и `fetch`. Сейчас спецификация принимает только `bybit_public_v5_cashcarry_v1`. Подстановка Bitget-адаптера fail-closed.

Это создаёт правильное место для будущего Bitget, но не делает ложную совместимость: Bitget потребует отдельной preregistered source/spec, нормализатора instrument/book/funding и parity-тестов. Bitget data запрещено выдавать за `bybit_public_v5`.

## Безопасный запуск

Preflight без сети и записи:

```bash
.venv/bin/python scripts/run_public_cashcarry_station_v1.py preflight
```

Detached bounded launch после доступности public network:

```bash
bash scripts/launch_public_cashcarry_station_v1.sh
```

Read-only status/replay:

```bash
.venv/bin/python scripts/run_public_cashcarry_station_v1.py status \
  --run-root runtime/research/public_cashcarry_station_v1_20260716_public1
```

Внутренний runner требует четыре явных opt-in: public network, durable collector, research shadow и acknowledge research-only. Launcher передаёт только их; execution-флага не существует.

## Проверка

Совместный focused regression station + frozen v1/v2:

```text
33 passed in 0.69s
```

Проверены disabled/no-write preflight, обязательные opt-in, отдельные journals, restart/reconcile, immutable launch receipt, funding-aware schedule/retry, byte/free-space stop, corrupt-state refusal, Bitget identity refusal и отсутствие key/environment/private/order paths.

Финальные hashes:

- spec: `40b608ac40074821b6a4b3c773bdcd108d894cd5e1092aff5c926f39487000e1`;
- station module: `9aeb050cbe6d7043dba1840534ac877a78f20da3c9d42320af210bb125902b13`;
- runner: `a189cb7221993a156ead1cb0c69ed2ebe16443a5f623336354f3406b05a46adc`;
- supervisor: `7d7bf1103a15e5c5ae2897097793b01f25f4db4ccbbe1a5169ca436bb503e8cc`;
- launcher: `ef0623465940b21309fac8475d7ce44629921b55733717e527e4666de934f85b`.

## Launch truth этой сессии

Предфинальный bounded connectivity probe был fail-closed: sandbox DNS не вернул ни одного public payload по шести символам. Запрос на разрешение внешнего public GET был отклонён из-за лимита tool usage, после чего обход не предпринимался. Поэтому **долгий collector не запущен**, public observations `0`, shadow positions `0`, live/VPS/ключи/ордера не менялись.

Точный sanitized receipt: `reports/research/public_cashcarry_station_v1_20260716/blocked_launch_receipt.json`.

Повторный ровно один bounded probe в `04:37 UTC` после запуска через detached launcher также не получил ни одного DNS/public payload: `6` попыток, `0` observations, `0` shadow positions. Долгий screen не оставлен. Supervisor теперь всегда пишет `supervisor.log`, чтобы detached startup больше не исчезал без операционного следа. Receipt: `reports/research/public_cashcarry_station_v1_20260716/blocked_launch_retry_receipt.json`.

## Что даст недельный clock

Он ответит не на вопрос «сколько обещано процентов», а на проверяемые вопросы:

1. как часто funding persistence вообще проходит frozen gate;
2. сколько carry остаётся после реального walked book + четырёх fee + basis reserve;
3. бывают ли полноценные paper open/close cycles;
4. выдерживает ли механика settlement capture, restart и длительный сбор;
5. есть ли после 10 cycles основание обсуждать механику и после 30 cycles / 3 liquid symbols — только ручной edge review.

До account-specific fee receipt и этих ворот капитал добавлять нельзя. ИИ позже может ранжировать already-safe observations, но не должен ослаблять economics gate или самостоятельно давать live authority.

## Bitget portability checkpoint

Добавлен отдельный preflight-ready Bitget V2 public adapter с immutable source `bitget_public_v2`, official-shape fixture и строгой нормализацией spot/perpetual instruments, books и funding. Он намеренно не подключён к этой Bybit station и не может попасть в frozen Bybit journal. Подробности и blocker receipt: `reports/BITGET_CASHCARRY_PUBLIC_ADAPTER_V1_2026_07_16.md`.
