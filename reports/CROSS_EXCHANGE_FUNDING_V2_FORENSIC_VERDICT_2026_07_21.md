# Cross-exchange funding v2 — forensic verdict

Дата аудита: 2026-07-21

Статус: **MODEL INVALIDATED / NO LIVE / NO CAPITAL**

Контур: только публичный research-shadow, без API-ключей и ордеров.

## 1. Итоговый вердикт

228 закрытых циклов `settlement_execution_v2` **нельзя использовать как доказательство
доходности, убыточности или денежную проекцию реального cash-and-carry**. Арифметика
сохранённых строк в основном согласована, но входные данные и их временная связность
нарушены: Binance/Bitget funding-интервалы были захардкожены как 8h, stock/RWA
контракты смешивались с криптой, funding не подтверждался фактическими settlement
receipts, а четыре cron-стадии запускались параллельно без lineage и атомарной
передачи снимков.

Безопасный вывод из старой выборки только один: **текущую v2 нельзя допускать к
капиталу**. Это не доказывает, что сама идея funding carry не имеет edge; её нужно
перепроверить на новой, корректной v3-выборке.

Все прежние денежные прогнозы для этого рукава, включая ориентир `$5–15/month на
$1000`, **отозваны**. Текущий отрицательный p25-прогноз также не является точным
прогнозом будущей доходности — это результат невалидной модели.

## 2. Аудированный серверный снимок

Источник: `/root/by-bot/runtime/arb/*`, read-only snapshot около
`2026-07-21T17:45Z`.

- модель: `settlement_execution_v2`;
- closed: `228`, open: `5`;
- wins/losses: `68 / 160`, WR `29.82%`;
- mean: `-0.045444%` total capital / cycle;
- median: `-0.1078%`;
- p25: `-0.186625%`;
- average hold: `24.2357h`;
- ROI tool показывал `-5.544311%/month` по методу p25;
- validated snapshot: `2` строки (`ESPORTSUSDT`, `SKHYNIXUSDT`).

Локальные и серверные SHA-256 четырёх рабочих файлов совпали:

- scan: `20cd6404cb85a5e4e3d925e31b0ca217754c7fe30654187cc79864c518816399`;
- validate: `bdd5730527d369a296ce664f4931d05ada879a8f337229ef9f434ad3c600041f`;
- shadow: `e34967d494cbb846f7c54da77d5e8073c6c8415a9cf8280d4a0ab299cd76d4d3`;
- ROI: `0074808ad8407b6bddc6b27c0bec7c530683ccbd1f4ed3b8a5152f8c2d6faf92`.

Значит вывод относится именно к исполнявшейся на VPS версии.

## 3. P0 — неверные per-venue funding-интервалы

### Что сломано

В `scripts/cross_exchange_funding_scan.py` Binance и Bitget всегда получали
`funding_interval_hours=8.0`. Реальные интервалы конкретного контракта сейчас часто
равны `1h` или `4h`.

Authoritative public metadata, использованная при аудите:

- Bybit: `v5/market/instruments-info` (`fundingInterval`, `symbolType`);
- Binance: `fapi/v1/fundingInfo` (`fundingIntervalHours`) и `exchangeInfo`;
- Bitget: `api/v2/mix/market/contracts` (`fundInterval`, `isRwa`) и
  `current-fund-rate` (`fundingRateInterval`, `nextUpdate`).

Сравнение сохранённых интервалов с **текущей** официальной метадатой обнаружило хотя
бы одно несовпадение у `202/228` циклов (`88.6%`). Интервалы могли меняться во
времени, а старая raw metadata не сохранялась, поэтому это не точный исторический
пересчёт, а доказательство невоспроизводимости: старую выборку восстановить честно
невозможно.

### Конкретный false positive: ESPORTS

Validated row содержала:

- short Bybit: `+0.031116% / 1h`;
- long Bitget: `+0.0329%`, но v2 ошибочно считала `/8h`;
- projected funding за 24h: `+0.6481%`;
- projected net: `+0.3924%` на one-leg denominator.

Bitget metadata для этого контракта показывает `1h`. При правильном интервале
позиция в записанном направлении получает:

`24 × (0.031116% - 0.0329%) = -0.042816%`

funding на one-leg denominator. После записанных round-trip costs `0.2557%` это
примерно `-0.298516%` pair-sum, или **`-0.149258%` total deployed capital**, ещё до
неучтённых рисков. Старая строка была не edge, а ошибка интервала.

### Исправление, подготовленное локально

Research-only patch оставлен незакоммиченным и не задеплоенным:

- `scripts/cross_exchange_funding_scan.py` получает явный per-symbol interval и
  next settlement из public metadata;
- Binance symbol без authoritative interval теперь fail-closed, без silent 8h;
- Bitget требует совпадения `contracts.fundInterval` и
  `current-fund-rate.fundingRateInterval`;
- Bybit использует paginated instruments metadata;
- focused regression воспроизводит ESPORTS false positive.

## 4. P0 — отсутствует asset taxonomy / contract identity gate

Совпадение строки `SYMBOLUSDT` не доказывает одинаковый underlying. V2 принимала
stock, ETF, commodity и RWA perpetuals как криптовалюты.

Пример `SKHYNIXUSDT`:

- Bybit: `symbolType=stock`;
- Binance: `contractType=TRADIFI_PERPETUAL`, `underlyingType=KR_EQUITY`;
- Bitget: `isRwa=YES`.

По текущей Bybit taxonomy `50/228` старых циклов (`21.9%`) относятся к stock или
commodity symbols. Среди них SKHYNIX, SAMSUNG, SOXL, SOXS, KORU, AVGO, INTC, MSTR,
NBIS и другие. Их mean был `-0.124422%`, median `-0.1265%`.

После исключения current stock/commodity taxonomy и одного ошибочного exit остаётся
`N=178`, mean `-0.023260%`, median `-0.0898%`, p25 `-0.1888%` (`61/117`
wins/losses). Знак старого shadow не объясняется только RWA, но и этот срез всё равно
невалиден из-за funding schedule и settlement accounting.

Локальный patch fail-closed исключает:

- Bybit `symbolType` вне crypto/innovation classes;
- Binance `underlyingType != COIN` и не-`PERPETUAL` контракты;
- Bitget `isRwa != NO` и не-perpetual contracts.

Focused test подтверждает исключение SKHYNIX на всех трёх venues.

## 5. P0 — funding accounting не является settlement accounting

`cross_exchange_funding_shadow.py` не читает фактически опубликованные settlement
rates. Он хранит predicted/current rate и начисляет её при расчётной границе.

Дополнительный дефект: `current_by_key` строится только из текущего списка PASS.
Когда открытая пара исчезает из validator output, код ставит pending funding обеих
ног в `0.0`. Если направление спреда перевернулось, старый `pair_key` тоже исчезает.
Это может как недосчитать положительный funding, так и скрыть отрицательный — bias
не контролируется.

Факты выборки:

- `69/228` циклов имеют zero simulated funding;
- median `simulated_settled / projected_at_entry = 12.64%`;
- p25 capture = `0%`;
- actual exchange settlement receipts в ledger отсутствуют;
- funding-event duplicate keys не найдены, но сами суммы не authoritative.

Старые 228 циклов нельзя «поправить коэффициентом»: нет сохранённой исторической
metadata, raw predicted snapshots и подтверждённых settlement rates для каждой
ноги.

## 6. P0/P1 — несогласованный cron pipeline

Все четыре jobs стоят на одной минуте `*/15` независимо:

1. scan;
2. validate;
3. shadow;
4. ROI.

Фактический цикл 18:00 UTC показал порядок завершения:

- ROI `18:00:11`;
- scan `18:00:13`;
- shadow `18:00:16`;
- validate `18:00:23`.

ROI читал предыдущий shadow, а shadow — предыдущий validated snapshot. У файлов нет
run id, input hash и snapshot lineage. JSON пишется напрямую, без same-filesystem
temp + fsync + atomic rename. При parse error shadow loader молча возвращает default,
что создаёт риск потери/обнуления state.

## 7. P1 — execution parity и bad-cycle eligibility

### Actual entry не проходит повторный gate

Validator проверяет basis/slippage по одному order-book snapshot, затем shadow заново
получает обе книги последовательно и открывает виртуальные ноги, но не пересчитывает
basis, slippage и net gate.

- `6/228` фактических entries превысили configured max basis `1%`;
- их mean return: `-1.715583%`;
- худший HUS cycle вошёл при basis `2.1602%` и закрылся `-7.3326%`.

У entry/exit legs также нет exchange timestamps и max-skew проверки; две
последовательные книги не доказывают одновременно исполнимый pair fill.

### Exit failure ошибочно становится валидным P&L

Один KORU cycle получил финальный exit error
`invalid bitget KORUUSDT sell close request`. Код заменил обе exit prices на нули,
price P&L на `0`, закрыл цикл по времени и включил `+0.0577%` в ROI. ROI eligibility
проверяет только model version и finite result, но не `last_update.error`.

## 8. Что в формулах корректно

Цена и fee units сами по себе не являются главным багом:

- price P&L sign корректен: `long_return + short_return`;
- funding sign корректен: positive rate получает short, платит long;
- при `6 bps` за fill четыре taker fills стоят `0.24%` на one-leg denominator;
- после деления pair-sum на два это `0.12%` total deployed capital.

Поле `fee_cost_pct_per_leg` названо неудачно: оно хранит сумму четырёх fees,
нормированную на notional одной ноги. `estimated_net_pct_for_hold` тоже является
pair-sum на one-leg denominator; для доходности всего капитала его нужно делить на
два.

Остаются model gaps: одна fee для всех venues вместо account-specific tier, exit fee
не масштабируется точным exit notional, а sequential books не моделируют legging
latency.

## 9. Дубликаты и статистическая зависимость

Положительный факт: среди 228 cycles нет duplicate IDs, duplicate natural cycle
keys или duplicate `(leg, settlement_ts)` events.

Но `N=228` не равно 228 независимым наблюдениям:

- период всего `47.2` дня, обычно ровно пять concurrent cycles в день;
- `129` pair routes, `78` symbols;
- найдено `44` пересечения cycles по одному symbol во времени;
- persistence history содержит `96,342` rows, включая `636` повторов одного pair
  ближе чем через пять минут; gate считает raw rows, а не distinct scheduled runs.

ROI gate `N>=10` не учитывает day/symbol clusters и слишком слаб даже после починки
данных.

## 10. Почему текущая ROI projection не является прогнозом

`arb_roi_calculator.py` математически правильно получил:

`p25_cycle × 720 / average_hold = -5.544311%/month`.

Но это не estimate expected portfolio return: p25 одного cycle линейно повторяется
каждый день, зависимость concurrent positions игнорируется, а invalid/data-error
cycles допускаются. Для сравнения mean той же невалидной выборки дал бы около
`-1.3501%/month`, а не `-5.54%`.

Статус `projection_available` означает только `closed_count >= 10`; он не означает
`model_valid`, `edge_proven` или `ready_for_live`.

## 11. Minimal v3 sequential + atomic station spec

Новая модель должна иметь отдельный id `settlement_execution_v3` и отдельные paths.
V2 не смешивается с v3 ни в state, ни в ROI.

### 11.1 Один последовательный supervisor

Один research-only process под `flock` выполняет строго:

1. `metadata_snapshot`;
2. `funding_snapshot`;
3. `scan`;
4. `validate`;
5. `update_open_positions_and_settlements`;
6. `close_due_positions`;
7. `open_new_positions`;
8. `commit_state_and_append_receipts`;
9. `build_roi`;
10. `publish_latest_manifest`.

При падении любой стадии downstream stages не запускаются, старый `latest` остаётся
нетронутым. Четыре параллельных v2 cron jobs после готовности v3 заменяются одним
supervisor job. Сейчас cron/deploy не менять.

### 11.2 Snapshot lineage

Каждый run создаёт immutable manifest:

- `run_id`, `started_at_utc`, `completed_at_utc`;
- code git SHA и SHA-256 scanner/validator/shadow/ROI modules;
- config SHA-256;
- для каждой public response: venue, endpoint class, exchange/server timestamp,
  local received timestamp, normalized payload SHA-256;
- для каждой stage: input artifact hashes, output hash, row counts, reject counters;
- previous state hash и committed state hash;
- explicit schema/model version.

Ни одна stage не читает просто `latest.json` без совпадения ожидаемого input hash из
текущего manifest.

### 11.3 Atomic storage

State/latest files пишутся в temp file на том же filesystem:

1. serialize;
2. flush + `fsync` file;
3. `os.replace`;
4. `fsync` parent directory.

Funding и cycle receipts пишутся append-only с idempotency keys. Mutable state —
только производная view, не единственный источник истории.

### 11.4 Metadata and taxonomy gate

До scan обязательны:

- explicit funding interval и next settlement для каждой venue/symbol;
- contract status, perpetual type, quote/settle asset;
- Bybit `symbolType`, Binance `underlyingType/contractType`, Bitget `isRwa`;
- exact underlying identity/version mapping для обеих ног;
- unknown/missing/conflicting metadata => reject, не default;
- stock, ETF, commodity, RWA/tokenized equity => отдельный будущий sleeve, но не
  crypto carry v3.

### 11.5 Funding settlement receipts

Predicted funding используется только для entry ranking. Earned funding берётся
только из public history endpoints после settlement:

- Bybit funding history;
- Binance funding rate history;
- Bitget history fund rate.

Receipt key: `(cycle_id, venue, symbol, side, settlement_ts)`. Начислять событие можно
только если обе ноги были полностью виртуально открыты до settlement timestamp.

Если settlement receipt ещё не опубликован или endpoint недоступен:

- status `settlement_pending`/`data_missing`;
- не подставлять `0`;
- не включать cycle в ROI;
- повторять получение по bounded retry policy.

### 11.6 Entry execution parity

Перед virtual open повторно получить обе книги и пересчитать gate на фактических
execution averages:

- обе books достаточно свежие;
- receive/server timestamp skew не больше preregistered bound (например, `2s`);
- обе ноги полностью fillable по одинаковому USD notional;
- actual basis и slippage проходят limits;
- corrected funding schedule minus four venue-specific fees, slippage and buffer
  всё ещё проходит;
- не более одной open route на symbol.

Если любая проверка не прошла — position не создаётся.

### 11.7 Exit failure handling

При невозможности получить обе executable exit books:

- position переходит в `close_pending_data`, но не получает нулевой price P&L;
- bounded retries, например до `30m`, с сохранением каждой ошибки;
- после deadline cycle становится `invalid_exit_data`;
- invalid cycle сохраняется в ledger, но исключается из edge/ROI sample.

### 11.8 Fees and denominator

Хранить отдельно:

- `long_entry_fee_bps`, `long_exit_fee_bps`;
- `short_entry_fee_bps`, `short_exit_fee_bps`;
- source/valid_at для fee contract;
- P&L в USD и `% total deployed capital` как primary metric.

Для public-only clock до account fee receipt использовать preregistered conservative
per-venue fee, явно помеченный `assumed`, а не выдавать его за account-specific.

### 11.9 Reset/freeze ledger

Перед первым v3 run:

1. сохранить immutable hash/receipt текущего v2 state и ROI;
2. пометить v2 `model_invalidated`, `projection=null`, reason codes:
   `funding_interval_wrong`, `taxonomy_missing`, `settlement_receipt_missing`,
   `pipeline_unordered`;
3. не удалять 228 rows, но исключить их из любых v3 aggregates;
4. создать пустые v3 state/ledger paths;
5. старые денежные forecasts пометить `withdrawn`;
6. не добавлять капитал и не включать order authority.

## 12. Минимальный эксперимент после v3

### Phase A — 72h correctness clock, не ROI

Public-only, `$100 virtual per leg`, максимум три разных crypto symbols.

PASS только если:

- `0` unknown/default funding intervals;
- `0` stock/RWA/commodity contracts;
- `0` missing или duplicate settlement receipts;
- `0` stale/hash-mismatched stage inputs;
- `0` cycles закрыты с book error;
- `100%` P&L rows воспроизводятся из immutable receipts до малого округления;
- ESPORTS regression со старым snapshot не проходит старый false-positive gate;
- SKHYNIX полностью исключён crypto taxonomy gate.

Phase A доказывает только корректность машины, не edge.

### Phase B — первая проверка edge

После Phase A: минимум `30` valid closed cycles, не менее `10` отдельных UTC days,
distinct-symbol cap и никаких overlapping routes одного symbol. Считать daily
portfolio cohorts и cluster-aware uncertainty, а не считать cycles IID.

К tiny live canary можно возвращаться только если после всех fees/slippage:

- rolling mean и median > 0;
- preregistered lower-confidence/daily guard не отрицателен;
- результат не держится на одном symbol/venue/day;
- нет missing settlement/data-quality flags;
- отдельно подтверждены account balances, exact fee tiers и full-funded обе ноги.

До этого: **NO CAPITAL**.

## 13. Проверки локального P0 patch

- focused tests: `11 passed`;
- `py_compile`: PASS;
- public API smoke без записи/ордеров: `1514` normalized rows
  (`Bybit 517 / Binance 528 / Bitget 469`);
- ESPORTS получил реальные `1h` intervals на всех трёх venues в smoke;
- SKHYNIX отсутствует в crypto rows;
- patch не коммитился, не пушился и не деплоился.

Оставшиеся обязательные P0 до нового shadow: settlement-history receipts,
sequential/atomic station, entry revalidation, bad-exit eligibility и v2→v3 reset.
