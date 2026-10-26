# PUMP4: native stop OFF и узкое исправление CURRENT —26Oct

**Текущий блок исполняется. Native mapping и84 memory protocol приняты локально;
пакет70d4a1009c13eccf staged наVPS, ещё не выбран.303 local /303 VPS network-denied PASS;
фактическая новая H1 — следующая проверка после DATA handoff. Денежного GO нет.**

## Закрытый кодовый дефект стопа

Новый versioned `pump4_native_stop_v1` сохраняет reference plan/hash. Для SHORT
native stop округляется вниз к tick, для LONG — вверх; геометрия проверяется
относительно reference entry, LastPrice и исполнимой стороны quote. Цена должна
оставаться положительной, в допустимых metadata пределах, строго на защитной
стороне. Количество по-прежнему считается от исходного reference/adverse риска
и расходов. Более близкий стоп не увеличивает qty.

Mapping со снимками/hashes инструмента и quote сохраняется в execution-config
только для off-tick планов, участвует в CID/config/admission hashes и проверяется
на resume. Свежий tick/native повторно сверяется до admission; новое metadata
время само по себе не заменяет mapping. Для mapped-потока readback требует
точно его native stop; чужой даже более близкий stop не усыновляется. Старые
exact-tick configs/поведение не переписаны. Новый mapping разрешён только OFF;
ни старый GO, ни `apply=True` не могут включить его денежную отправку.

119 целевых проверок, включая native/adapter/account/lifecycle/selected runner;
81 по prefix/stream/intake. Независимый actual `gpt-6-astra/high`:0Critical/
Important по production diff и отдельно по84-harness/prefix. Проверены partial
entry/partialTP, native-stop race, restart, tamper, stale quote/tick drift и
неизменность qty/reference. Новые partial/race tests дополнительно root-verified.

84/84 reference geometries прошли adapter→lifecycle→native stop→TP1/TP2→
send-once→restart/readback/reconcile на **MemoryBybit**. Reply-loss и crash-after-
reservation не породили повторных отправок; ровно3 fictional requests/case,
финиш `FLAT_COSTS_PENDING`, реальных запросов0.
Это **не84 фактических допуска счёта**: отдельно проверяемый неизменный sizing
R1/gross30/funding-cap даёт2 fixturePASS,51 CAPACITY_BLOCKED,31 COST_CAPACITY.
Остальные82 проходят только явно отмеченную protocol-only геометрию с testqty.
Настоящий риск не увеличен ради теста или допуска.
[Evidence](evidence/pump4_native_off_20261026/).

## Измеренное узкое место CURRENT

Actual09H1 уже сохранил priorityPASS, но только20/133 публикаций≤60s.
Оценка служебного prefix составляла26.069s. Advisory classifier повторно читал
и проверял весь journal даже для обычного CURRENT перед неизменной настоящей
приёмкой. Теперь bounded≤8KB **непроверенный** tail может только выбрать
IMMEDIATE. Он не разрешает публикацию: `_stream_symbol/_symbol` сохраняют все
capture hash/source/journal/producer проверки. Поддельный current-tail проверен
тестом: фактическая приёмка остаётся BLOCKED. CATCHUP по-прежнему полностью
проверяется, откладывается до seal и повторно сверяет journal/epoch/batch.

Добавлены отдельные classification start/end timestamps: новый замер отделяет
эту работу от ожидания предыдущих notices в одном прочитанном pipe chunk.
Новый рыночный latencyPASS ещё не заявляется. Intake/producer/epochs/cursors,
timer,60s и бюджет не изменены. Пакет includes native code, но DATA selection
не означает выбор нового финансового исполнителя: старый app306 остаётся OFF.

## Funding: единая бухгалтерия и правильная трактовка

Origin проверен на `b3516e34f940099dde98465dfecc16461c25df46`;29366fb,76c9041,
99da9ef и economic-note KITY ee305dd входят в опубликованную ветку.
76c9041 **добавляет** непрерывный replay в ежедневный hook; старый pereschet
остаётся там описательным. Это не подтверждение его deployment или создания
своевременных opportunities: ежедневный replay не заменяет поток Codex.

99da9ef JSON SHA256 `ab9b4c02c55c0a3353b13ef1e0e809e087b0453733ce9d15691aca68eeeef465`:
точные84 ключа совпали, опубликованные R совпали с reference. Перезапуска
оценщика/PnL/judge и второй загрузки funding не было. Код действительно использует
остаток0.60 после TP1;0.45 в prose — описка, исправлять арифметику на её основании
нельзя. Средний опубликованный funding scenario +0.00235357R.

Одинаковые84 записи, одинаковые наблюдаемые account/symbol fees13:19:41UTC,
slippage **на сторону**, плюс funding-сценарий Claude:

| bps/side | meanR | сентябрь | октябрь |
|---:|---:|---:|---:|
|2|+0.06030|−0.06916|+0.31921|
|5|+0.05656|−0.07291|+0.31549|
|10|+0.05031|−0.07918|+0.30929|

Таким образом старые +0.04796R при10bps/side **до** funding превращаются в
+0.05031R при добавлении именно этого scenario, без смешения с5bps и6bps fees.
[Построчная арифметика](evidence/pump4_funding_bridge_20261026/bridge.json).

Это исторические ставки, а не фактические проводки гипотетических сделок.
Расчёт использует entry notional; Bybit использует qty×settlement mark price.
Исполнение в±5s от settlement не имеет гарантированного порядка:
[Bybit Funding calculation](https://www.bybit.com/en/help-center/article/Funding-fee-calculation?category=cd60af6303161fd598).
В scoped inputs9 входов и25 exit-bar boundaries совпадают с funding timestamps;
H1 не даёт точного порядка. Снимки исходных файлов/settlement ledger в JSON не
закреплены, исторические gaps полностью не аттестованы. Поэтому статус остаётся
INCONCLUSIVE; стресс current-cap и исторический sample отвечают разным вопросам.

Для отдельного технического micro устойчивый годовой доход не требуется доказать
одним исполнением. Но нужны принятые технические gates, конкретные лимиты и
отдельный точный финансовый GO владельца. Ничего из этих результатов его не
создаёт; прибыльный массовый LIVE также не объявляется.

## Открытые исполнительные условия

Новая реальная H1 нужна после установки prefix, не replay старого часа.
Также старый lifecycle сохраняет≤5s/exact-reference-open entry check, при внешнем
consumer proposal≤60s. Его здесь не ослабляли. До готового денежного пакета нужен
явный версионный контракт реального входа/отклонения и проверка текущего пути,
включая уже пройденные TP/stop во время задержки. Это конкретное существующее
условие кода, а не новое требование к экономической доходности.

Monthly v6 и её финансовый календарь не изменены. KITY не поднимается как
замена первому денежному тесту PUMP: её дваPASS не являются economicPASS.
