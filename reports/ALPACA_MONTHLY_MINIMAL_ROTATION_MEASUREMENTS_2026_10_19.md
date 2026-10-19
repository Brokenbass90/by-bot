# Monthly: минимальное исправление ротации, измерения19Oct

**Поправки PM приняты. Новый framework не требуется; резерв$4 не утверждён.**
[Source-backed measurements](evidence/net_day_incident_20261019/monthly-minimal-measurements.json).
Завершённый cost-source компонент опубликован как
`6ab5d4bd46560256dac2a920050163b0061cf9ea`; это ORDERS_OFF component, не автономный LIVE.

## Счёт и деньги

Account GET16:56UTC: cash, buying_power, regt/effective и non-marginable BP равны
**$394.91**, multiplier1, equity$492.21, accrued_fees0, pending_reg_taf_fees0,
trading/account blocked=false. Единственные позиция/открытый ордер — NET/её STOP.
Это наблюдаемый режим1x, не доказательство доступного кредитного плеча.

В этом payload нет `account_type` и `settled_cash`; приравнивать cash к отдельно
доказанному settled cash нельзя. Официальная документация direct Alpaca говорит,
что счета открываются margin, а equity<$2000 ограничивает BP до1x. Это внешнее
общее правило, не отдельная квитанция юридического типа именно этого счёта.
[Account](https://docs.alpaca.markets/us/docs/account-plans),
[margin](https://docs.alpaca.markets/us/docs/margin-and-short-selling).
Допуск в любом случае использует фактически возвращённые cash и non-marginable BP;
из слова margin никаких послаблений не следует.

## Расходы: известная часть и её пределы

Свежий официальный [тариф](https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf)
имеет revision12Oct, raw SHA `814767d3dbd44d89bfbf5448eb5eac85a894740bf1974db2294aae448a6fed94`.
Он отличается bytes от сохранённой версии8Oct, но NMS retail CAT.000003/share,
SEC.0000206/sell value и TAF0 совпадают. Каждый fee type суммируется за account/day,
затем округляется вверх до цента. Семь прошлых fills и шесть списаний на$0.06 уже
сверены по quantities/amounts, не по равенству количества строк.

На текущем снимке hypothetical NET exit даёт известные CAT$0.01+SEC$0.01=$0.02.
Это расчёт по snapshot price, не отправленный выход или гарантированный будущий fee.

Для иллюстрации полного sell+buy при$487.42×70%=$341.194 на каждой стороне,
одном execution day и ценах не ниже minimum close16Oct Monthly57 (**NKE$37.1300010681**)
known retail fees также составляют$0.02. Этот пример **не будущий верхний предел**:
фактические цены, exit notional, новые quantities, дни исполнения и прочие операции
могут отличаться. Universe57+SPY/источник Yahoo не изменялись; этот старый снимок
не стал свежими котировками или prospective решением.

В tariff отдельно существуют ADR/corporate-action/прочие charges. Нельзя объявлять
их покрытыми двумя центами или$4 без source classification. Поэтому резерв пока
не выдан. Верхнюю оценку перед конкретной ротацией следует вычислять **после
подтверждённого sell fill** из его actual qty/value и capped новых buy quantities,
полного account-day оборота и независимо известных обязательств. Тогда не нужен
выдуманный предел будущей market sell price. Уже отражённые accrued liabilities
нельзя считать повторно; отсутствие activity не означает нулевой расход.

## Что блокирует код, точно

1. `_admit_new_entry()` сначала вызывает `_accounting_net()`: любой exited Monthly
   lifecycle без принятого finality даёт `MONTHLY_ACCOUNTING_PENDING` **до** account
   GET. Это точный бухгалтерский blocker будущей same-window rotation.
2. Отдельно broker positions должны совпасть с owned book. Текущая legacy NET
   не является Monthly owned position: `MONTHLY_FOREIGN_OR_UNRECONCILED_POSITION`.
3. Отдельно проверяются exact full native STOP, ownership, посторонние ордера,
   свежесть, общий gross, slots и `min(cash, non_marginable_BP)−liability`.
   Ни резерв, ни delayed entry не должны обходить эти проверки.

Минимальный proposal: расширить **существующее** liability/admission правило для
подтверждённых выходов с ограниченным source-classified pending fee; net-loss
admission использует консервативную нижнюю оценку результата, accounting остаётся
PENDING до actual finality. Unknown/out-of-bound charge блокирует новый риск.
Не создавать второй ledger или модуль полномочий. Это пока CR, финансовый код
и полномочия не изменены.

## REMAINING

- Зафиксированный sensitivity comparison задержек1/2/3/5 sessions на одном frozen
  Monthly baseline ещё **не выполнен**. Не выдавать его за уже принятый выбор даты.
- Local candidate минимального admission fix + target fault/restart/loss tests,
  затем независимая проверка и конкретное owner решение по изменённому допуску.
- Server ORDERS_OFF runner, один manager, NET handoff и rollback acceptance.
-30Oct actual closed source и2Nov fresh window/действующий GO — будущие факты.

Окно2Nov14:30–14:35UTC сохраняется. Окончательная PnL-бухгалтерия не должна незаметно
стать новой стратегией с delayed entry. Пока исправление не принято, действующий
guard остаётся строгим и может выдать NO_SEND; обещания покупки или прибыли нет.
