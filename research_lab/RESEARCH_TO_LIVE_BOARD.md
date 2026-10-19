# Trading OS — единая доска доведения до первой версии

19 октября 2026. **Единственный общий roadmap и активная очередь:**
[ROADMAP_SELF_IMPROVING.md](../ROADMAP_SELF_IMPROVING.md).
Интегрирующий writer общего roadmap/этой доски — **Codex**; research statuses,
KARTA и passports ведёт **Claude**. Здесь только производные gates стратегий,
не вторая очередь приоритетов и не финансовое разрешение.

Execution receipts подтверждены через92dd3f2, roadmap —451ae69. Research origin
1407fbf подтверждён19Oct07:14UTC;3a349a3/82193fe/3e8f779 опубликованы как его предки.
Claude подтвердил ownership roadmap в опубликованной status delta; изменение
KARTA pointer ещё не подтверждено. Непрерывный Factory runtime UNKNOWN.
Политика/GO определяются owner packets, финансовые факты — broker/journal/native,
research verdicts — замороженными receipts. Свежесть каждой runtime проверки
задаётся её датой. Старые датированные разделы ниже — история, не новая команда.

## Что считаем первой версией

Работающий в разрешённых пределах цикл: причинный сигнал → допустимый размер →
вход → полная native-защита → предусмотренный контрактом трейлинг/выход → точная
сверка денег → освобождение капитала → следующий допустимый отбор и вход.
Рестарт/дубликат не создают повторную заявку; неизвестное состояние блокирует
новый риск и становится видимым владельцу. Один manager и одна финансовая истина.

Новый фиксированный сравнительный прогон Claude0be44ec закрыл прежний пробел:
Weekly, EventReselection и A+G2+gov не прошли prereg правило замены Monthly.
Поэтому основной кандидат первой денежной версии — **Monthly**, с её собственным
календарём повторного отбора. Свободный капитал не требует немедленной покупки.
Новые разработки динамичных вариантов для денег не входят в P0 без новой
исследовательской версии и самостоятельного основания.

**Владелец18Oct явно отменил только SHOP:** future entry timer отключён;
NET manager/его timer/DAY-monitor сохранены. Старый personal-arm receipt —
исторический факт, не разрешение включать timer снова. Новый входSHOP19Oct отменён.
[Research/cancel receipt](../reports/evidence/trading_os_research_intake_20261018/receipt.json).

**19Oct NET safety delta:**13:35 independent window пропущено;16:56 direct GET
подтвердил full native DAY STOP277.69/.325167779. Observer падал на pin уже штатно
архивированного entry HALT; owner отдельно разрешил config-only repair, production
17:04UTC PROTECTION_CONFIRMED/TelegramRECOVERED. После отдельного owner разрешения
убран только пустой вызов cancelled SHOP из wrapper; первый штатный17:15UTC цикл
PASS:1NET child LIVE_PROTECTED/exit0 и отдельный свежийPROTECTION_CONFIRMED.
NET command/6units/financial specs/HALT/lock сохранены.
[Incident/receipt](../reports/ALPACA_NET_DAY_INCIDENT_2026_10_19.md).
Monthly component6ab5d4b опубликован;239exactPASS после4monitor regressions,
тот же1f02fc49 production material. Cash/BP394.91/1x, условный .02fee пример не
утверждённый резерв. Точный blocker `_accounting_net→MONTHLY_ACCOUNTING_PENDING`;
минимальный CR в существующем admission, server runner/handoff/rollback остаются
следующими; нового framework или финансового GO нет.

Первая версия не требует одновременного LIVE всех стратегий или доказанной
полезности Brain. Прибыль не является гарантируемым критерием приёмки;
соответствие исследованной модели, исполнение и реальные расходы — являются.
Цель2–3 крипторукавов сохранена как последовательное развитие после собственных
экономических/execution gates; количество стратегий не создаёт денежного допуска.

До закрытия этого цикла новые frameworks, broker adapters, managers, альтернативные
финансовые журналы и массовая очистка репозитория не входят в v1. Brain/Factory/
IBIT/LIQ продолжаются в уже существующих независимых контурах с текущими gates.

## Доска: доказательства, блокер, следующий шаг

Brain A/B для перечисленных денежных версий: **INCONCLUSIVE**, не условие допуска
самостоятельной стратегии; общий обязательный risk/ownership контроль сохраняется.

| Strategy / версия | Research status | Execution status | Broker / Owner GO | Конкретный блокер и следующий gate | Ответственный / evidence |
|---|---|---|---|---|---|
| ATT1 / existing frozen candidate | **ECONOMIC_FAIL**, published1c595cf: contemporaneous control n1200/16days, diff−0.0006R/t−0.08; no promotion | Dated engineering/source evidence preserved; no probe restart | ORDERS_OFF, no financial GO | **Убран из денежной очереди**. Не чинить денежный binding под FAIL и не пересчитывать judge для спасения; новая исследовательская версия требует отдельного основания | Claude research; Codex preservation. [publication receipt](../reports/evidence/alpaca_monthly_data_parity_20261018/research_publication_gate.json) |
| KITY_BYBIT / frozen cb47f0e, spent micro V4, safety48020edd | **ECONOMIC_INCONCLUSIVE**;2026dataexists/crypto-filterwithdrawn | 10entry/10native/10exit cash reconciled; normal hold NOT_PROVEN. Fresh flat0/orders0. Safety fault/health48PASS,40exact/0fallback;24fileVPS candidate UNSELECTED | Bybit; d848a130…f40a1 **SPENT**, activeowner TERMINAL/ORDERS_OFF unchanged | Inert rollout proposal/183pins готово; separate owner version-selection decision+freshflat/finality/lock before any cutover. Новый денежный повтор не назначать; frozen research gates retained | Codex + Claude; [safety/source receipt](../reports/KITY_SAFETY_AND_ELDER_EVENT_INTAKE_2026_10_18.md) |
| Alpaca Weekly Dynamic / fe72557b…f400d | **ECONOMIC_FAIL по prereg правилу замены Monthly**:5.76%годовых/DD19.94% при20bps/side, исследованная известная история | Source59/owned lineage/один manager подтверждены; SHOP не запускался | Alpaca; владелец **ОТМЕНИЛ один SHOP18Oct**, entry timer disabled/inactive; NET сопровождение действует | Не расширять и не включать заново.19Oct только full NET DAY stop / readback; отсутствие SHOP — OWNER_CANCELLED, не execution FAIL | Codex; [new verdict/cancel receipt](../reports/evidence/trading_os_research_intake_20261018/receipt.json) |
| Alpaca EventReselection / separate ORDERS_OFF contract | **ECONOMIC_FAIL по правилу замены Monthly**:7.42%годовых/DD23.56%,1из7срезов/0из4кризисов | Существующий ORDERS_OFF candidate/restart tests сохранены | Alpaca; денежного GO нет | Убрать из денежного P0; не дорабатывать финансовый binding ради частоты. Новая гипотеза — отдельная prereg, без ретюнинга текущей истории | Claude: research; Codex: preservation. [intake](../reports/evidence/trading_os_research_intake_20261018/receipt.json) |
| Alpaca Monthly / V4 + standing candidate348690be | Предпочтительна по0be44ec; known-history comparison, не unseenPASS | Single-scope E2E сохранён. Standing components ORDERS_OFF:165exact/34imports/0fallback,2syntheticcycles/1grant.19Oct authorized44file VPS CODE_ONLY_UNSELECTED/hash+43AST PASS; full server runtime не выполнен | Новый Monthly standing GO отсутствует; NET сохранён, SHOP отменён | **Cost producer/source/owned-book реализованы локально ORDERS_OFF; actual GET/fees/cash evidence получено. Следующий gate: exact package/server rehearsal + one production applying wrapper/handoff/rollback.** Прежний staging permission blocker CLOSED;30Octsource→2Novfreshgates, CASH/NO_SEND допустимы | Codex; [19Oct staging/readback](../reports/MONTHLY_STAGING_AND_BRAIN_CONTEXT_2026_10_19.md), [standing delivery](../reports/ALPACA_MONTHLY_STANDING_AUTONOMY_2026_10_18.md) |
| ELDER_CRASH_HEDGE_V1.2 clarification / frozen geometrya25e4af2…fea3a28 | DEV_PASS regime hedge; standalone KILL; original prospective/parity OPEN | **f1 adapter/intake blocker CLOSED locally ORDERS_OFF**: source.50 informational, hedge.55 unchanged; actualfixturePASS/badgeometryrejected;79targetedPASS. NOT_DEPLOYED/0prospective | Bybit preparation; no financial GO | Published6a618d2 confirmed ancestor oforigin4b1af40. Next actualcausal context/risk/instrument + prospective/parity/restart gates. Oldreceipts/producer/900/outcomes unchanged | Codex source; Claude research. [V1.2 acceptance](../reports/ELDER_V1_2_AND_MONTHLY_AUTONOMY_2026_10_18.md) |
| ETF_PREMIYA_BTC / DATA-only contract v1.1 | DEV candidate; Massive/10-session gate OPEN | Первый actual19Oct20:16UTC DATA_ONLY row FRESH/eventfalse;4capture/6sourcepins/row+QA verified.19immutablefiles delivered20Oct02:39Cyprus, repeat0new.81history credit0 | DATA_ONLY, ORDERS_OFF; no financial GO | Check23:35Cyprus MISSED, latecontrol/delivery timestamps retained. Massive=PENDING_SVERKA/0complete; consumer producer ingestion UNKNOWN. Local one-shot PAUSED; server collector active | Codex source; Claude research. [first actual record](../reports/IBIT_FIRST_FORWARD_DELIVERY_2026_10_20.md) |
| LIQ_OTSKOK_4H_V2 / source V2.1 | Raw records не edge; source coverage UNKNOWN | Immutable17/18Oct delivery,25coins; действующий collector/epoch сохранён | DATA_ONLY, ORDERS_OFF | Ежедневная доставка; gap/UNKNOWN handling, warmup и events по замороженному контракту.27010raw18Oct не27010prospective сигналов | Codex: delivery; Claude: source/research. [delivery](../reports/LIQ_RESEARCH_DELIVERY_2026_10_17.md) |
| Brain V2 / existing Shadow | Added value INCONCLUSIVE; currentV2 warmup до31Oct14UTC |19Oct07:13 source свежий:22448opps/68878decisions/V2=1534, hashchains PASS; existing receiver8receipts сохранены | SHADOW only, money authority нет | Catchup **BLOCKED receiver_capacity**:6136/4096receipts,28.2MB/8MiB; safe journal continuity/restart/replay затем paired evaluation. Независимый chain/prefix/unique keys/paired subset PASS; полный market census/feature PIT/outcome attribution UNKNOWN. Source count не delivered receipts/independent trades | Claude + Codex; [actual19Oct readback/capacity](../reports/MONTHLY_STAGING_AND_BRAIN_CONTEXT_2026_10_19.md) |

## 19Oct — cost finality / новые опубликованные запросы

[Cost producer + actual receipts + Brain integrity](../reports/MONTHLY_COST_FINALITY_AND_BRAIN_INTEGRITY_2026_10_19.md).
Read-only сборщик и producer связаны с существующим Monthly finalizer, без второго
финансового ledger. Actual account-day fees/cash proof отдельно от simulated
Monthly execution. Новая серверная версия не активирована; standing GO отсутствует.
Обнаружен admission conflict: и NET handoff, и обычная monthly rotation требуют
продажи/замены в одном5min окне, тогда как full-day posted fees приходят позднее.
Нужен конкретный owner-reviewed bounded pending-cost admission CR; текущий strict
guard сохранён и выдаст NO_SEND. Это не закрывается перестановкой таймеров.

Origin6826315 подтверждён;4587a34 — опубликованный ancestor. U2/H2b ежедневный
1Day SIP/split остаётся DATA_BLOCKED и принят в очередь источников. U58 использует
собственную Yahoo hourly→daily поставку: не смешивать их в paired experiment.
BIL/SGOV H5B_DEV_PASS → CR, не money PASS; текущий foreign-position gate Monthly
отвергнет дополнительный fund sleeve. Account type, cash interest, actual fund
execution costs и единственное ownership нужно закрыть до любого изменения.
Polymarket QA опубликован; документ говорит5 tests, поздние коммиты9reported,
Codex их не запускал. NO-shadow сохраняет DATA_ONLY/исследовательскую границу.

## 19Oct — запросы Claude по независимым данным

BIL/SGOV SIP all/split фактически доставлены,2713/1606 bars each, calendar QA и
immutable replay PASS. Research overlay/PnL/Monthly changes отсутствуют.
Polymarket40-market pilot:20752points/62of80tokens; interval=max empty issue
исправлен запросами explicit historical windows. **PARTIAL /
NOT_SCREEN_READY**, не full2023–2026 census/lifetime или economicPASS.
SEC request принят в отдельную очередь. Origin7a80470 подтверждён; Factory verdicts
не пересчитывались. [Данные/receipts/границы](../reports/RESEARCH_SOURCE_DELIVERY_2026_10_19.md).
Monthly realcostfinality+oneproductionrunner остаютсяP0; новые source не меняют LIVE.

## 18Oct — закрыт source-parity delivery gate

Строго57+SPY/noQQQ: actual16Oct capture → та же existing hourly aggregation →
260daily view/полныеcore200 → frozen selection/ranking → immutableVPSseal → Claude.
Неполныестарые3сессии сохранены/отмечены; не260полных.19exactPASS/25imports/0fallback,
same19targeted не складываются. Новые DATAONLY server timer и ежедневная23:40Cyprus
доставка ACTIVE; повторный SCP не перезаписал seal. Будущий19Oct report PENDING.
[Receipt/QA/все57ranks](../reports/ALPACA_MONTHLY_DATA_PARITY_2026_10_18.md).
Никаких финансовых запросов/изменений;77oldpins/NET/SHOPcancel сохранены.

## Проверенное сравнение Alpaca — новое основание приоритета

Prereg7198e1b — предок результата0be44ec в Git. Codex прочитал опубликованный
JSON и пересчитал четыре условия решения; **не запускал backtest/judge**.
Период2016-01-04…2026-09-04,58акций/ETF+SPY, daily proxy,20bps **на сторону**.

| Версия | Годовых | MaxDD | PF | Сделок | По правилу замены Monthly |
|---|---:|---:|---:|---:|---|
| Monthly |8.484%|16.167%|1.537|325|Контроль/выбранный кандидат |
| Weekly Dynamic |5.759%|19.939%|1.328|378|FAIL:0из4условий |
| EventReselection |7.416%|23.563%|1.209|841|FAIL:0из4условий |
| A+G2+gov |10.014%|18.743%|1.348|709|FAIL:1из4условий |

Monthly не имеет самой высокой годовой доходности: A+G2+gov выше, но нарушает
ограничение DD+2п.п. и критерии срезов/кризисов. Weekly имеет положительный модельный
результат, но **не прошла правило выбора денежного кандидата**, что не тождественно
доказанной убыточности каждой будущей сделки.

Ни одна рука не получила здесь независимого unseen экономического подтверждения:
история уже использовалась, universe выбран по современной ликвидности.
Пререгистрация этого сравнения не делает старые данные новыми. Старый baseline
+29.971%/DD7.569%/64сделки относится к другому короткому окну; он сохранён в
[reference manifest](../reports/evidence/alpaca_parity_repair_20261016/etalon_reference_manifest.json),
не заменяет и не опровергает приведённое длинное сравнение.

Источники: [прогон/все варианты](https://github.com/Brokenbass90/by-bot/blob/0be44eca1f86929986b48ee77662d91b51a40255/research_lab/ALPACA_SRAVNENIE_DINAMIKI_ITOG_2026_10_18.md),
[prereg](https://github.com/Brokenbass90/by-bot/blob/7198e1b6c3bb240ef21e3451dd2b7b394e3858a7/research_lab/prereg/PREREG_ALPACA_SRAVNENIE_DINAMIKI_2026_10_18.md).

## Уже закрыто / что делаем до и после ближайшего рынка

18Oct выполнено: пинованный code-only KITY candidate23files, ровно один module diff;
все23 исходных production SHA и159 guards сверены чтением VPS.95tests на самом
candidate,16 импортированных KITY modules строго из его каталога,0 fallback в
локальные KITY modules. Ничего на VPS не установлено, новой policy/GO нет.
[Receipt](../reports/evidence/kity_20261018/fix_exact_dependency_acceptance.json).

Также исправлен существующий Health assessor: активный ownership conflict или
неподтверждённая native-защита теперь UNHEALTHY вместо process-only HEALTHY.
Source uncertainty не становится нулевой позицией.12новыхhealthcases;20Health+
8incident tests PASS. Notification code не отправлялся, реальная доставка тревоги
не заявляется. Локальный commit5820bac, **NOT_DEPLOYED**. Нет новых таймаутов,
денежных действий, restart authority или второго монитора.

Текущий результат: Monthly ORDERS_OFF E2E завершён и stageddisabled; KITY fallback/health
протестированы и stagedUNSELECTED; фактический Elder intake выявил frozen f1 mismatch.
[Новый receipt](../reports/KITY_SAFETY_AND_ELDER_EVENT_INTAKE_2026_10_18.md) заменяет
прежнюю LOCAL-only формулировку ниже/выше; действующий KITY owner не менялся.
Недостающая численная safety policy не выводится из одного инцидента5.631s;
paid retry не используется как замена fault injection и code review.

19Oct:13:30UTC NET full DAY protection;13:35UTC independent actual readback.
**SHOP13:31UTC отменён владельцем.** Existing heartbeat16:35Cyprus проверяет NET
и сохранение отмены SHOP,23:35Cyprus — первый IBIT; затем pause. Серверный timer не зависит от Mac,
локальный heartbeat при сне Mac может сообщить позже; своевременный отчёт не выдумывать.

Следующий денежный кандидат — Monthly, по исходному календарю и после конкретного
нового owner packet. Поддержание NET продолжается независимо от новых входов.
Запрет новых Weekly/Event money scopes не означает выключение действующего NET.

Новые paid attempts, две предложенные PM попытки, новые бюджеты и постоянная
автономия этим документом не разрешены. Корзина micro не доказывает семидневную
KITY: source membership/C2 уже MATCH, расходы/rounding/horizon — отдельный gate.
Фактический micro имел LONG114.87529/SHORT117.16109USDT и fees10.5282bps от entry
gross; эти значения нельзя молча заменить точными равными весами или нулевыми расходами.

Research owner получает [файловый status delta](../reports/STATUS_DELTA_FOR_CLAUDE_2026_10_18.md).
Его KARTA/VOROTA/код не редактировались, сообщения не отправлялись. Published4129fed
уже заменил research-копию доски указателем на эту execution board; один источник
текущего статуса подтверждён наorigin31ccd113. Старые execution
tables в датированных reports — исторические snapshots; эта доска — текущий индекс
следующих gates, без собственной финансовой истины. Full repository suite и новый
independent financial review не заявлены.
