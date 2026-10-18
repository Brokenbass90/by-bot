# Trading OS — единая доска доведения до первой версии

18 октября 2026. Производственные receipts — в этой recovery-ветке; research
Claude сверено с опубликованным `3856bbba94ef141aac88be54c8e73b17bf78aa0e`.
Это производная доска: разрешения задаются owner packets, деньги — broker/journal/
native ledger, исследовательские выводы — замороженными research receipts.
Ни одна строка доски не создаёт финансовых полномочий.

## Что считаем первой версией

Работающий в разрешённых пределах цикл: причинный сигнал → допустимый размер →
вход → полная native-защита → предусмотренный контрактом трейлинг/выход → точная
сверка денег → освобождение капитала → следующий допустимый отбор и вход.
Рестарт/дубликат не создают повторную заявку; неизвестное состояние блокирует
новый риск и становится видимым владельцу. Один manager и одна финансовая истина.

Для пользовательского требования Dynamic нужен законченный повторный отбор
после подтверждённого выхода. Существующий event-reselection кандидат делает его
к следующему допустимому regular opening по предыдущей закрытой сессии; мгновенная
внутридневная повторная покупка этим контрактом не разрешена. Сначала фиксированное
сравнение с Weekly, затем принятие версии и ограниченный owner scope.

**Один SHOP по таймеру — приёмка одного входа, а не готовый автономный повторяемый
денежный контур.** Первая версия не требует одновременного LIVE всех стратегий
или доказанной полезности Brain. Прибыль не является гарантируемым критерием
приёмки; соответствие исследованной модели, исполнение и реальные расходы — являются.

До закрытия этого цикла новые frameworks, broker adapters, managers, альтернативные
финансовые журналы и массовая очистка репозитория не входят в v1. Brain/Factory/
IBIT/LIQ продолжаются в уже существующих независимых контурах с текущими gates.

## Доска: доказательства, блокер, следующий шаг

Brain A/B для перечисленных денежных версий: **INCONCLUSIVE**, не условие допуска
самостоятельной стратегии; общий обязательный risk/ownership контроль сохраняется.

| Strategy / версия | Research status | Execution status | Broker / Owner GO | Конкретный блокер и следующий gate | Ответственный / evidence |
|---|---|---|---|---|---|
| KITY_BYBIT / frozen cb47f0e, micro V4, fix8500c97 | C2/source membership MATCH; экономическая переносимость расходов/округлений и семидневного удержания не подтверждена этим micro | 10входов/10native/10выходов и cash LIVE_RECONCILED; ранний unwind. Исправленный code-only candidate проверен на точных исходниках; NORMAL_HOLD_NOT_PROVEN | Bybit; d848a130…f40a1 **SPENT**, ORDERS_OFF | Проверка incomplete/unknown fallback и alert delivery; безопасный guarded rollout. Claude: экономическая идентичность исполняемой версии. Дополнительный платный micro не назначен | Codex + Claude; [actual cycle](../reports/KITY300_EXECUTION_AND_ALPACA_ARMED_2026_10_18.md), [candidate receipt](../reports/evidence/kity_20261018/fix_exact_dependency_acceptance.json) |
| Alpaca Weekly Dynamic / fe72557b…f400d | Нет найденного подтверждённого like-for-like NET backtest точного Weekly. Это явный пробел, не перенос Monthly PASS | Source59/owned lineage/один manager и timer подтверждены; фактический19Oct entry ещё FUTURE | Alpaca; лично ARMED **один SHOP19Oct13:31UTC**, ≤113.61USD/risk≤9.07 |19Oct13:30UTC actual full NET DAY stop →13:31SHOP admission/fill/native →13:35 GET readback. Новый цикл/расширение scope не подразумеваются | Codex: actual lifecycle; Claude: фиксированное экономическое сравнение. [arm receipt](../reports/KITY300_EXECUTION_AND_ALPACA_ARMED_2026_10_18.json) |
| Alpaca EventReselection / separate ORDERS_OFF contract | ECONOMIC_INCONCLUSIVE: сопоставимое сравнение с Weekly и Monthly отсутствует | Существующий candidate и restart/slot/cash тесты есть; финансового binding нет | Alpaca; нового денежного GO нет | Принять точную семантику после выхода и сравнить фиксированные версии на одинаковых допустимых данных/расходах, без ретюнинга. Затем end-to-end выход→капитал→новый causal ranking→следующий вход | Claude: research verdict; Codex: existing adapter integration. [contract](../reports/evidence/trading_os_dynamic_kity_20261017/dynamic_candidate_contract.json), [readiness](../reports/ALPACA_DYNAMIC_EXECUTION_READINESS_2026_10_17.md) |
| Alpaca Monthly / 8f6d1fd2…277c799 | Исторический baseline воспроизведён; независимый implementation parity507f782. Новая forward доходность не доказана | Source58/selection/schedule/ratchet ORDERS_OFF; отдельный disabled binding | Alpaca; financial activation не выдана | Сохранить самостоятельную ветвь:30Oct close selection →2Nov14:30UTC условное окно. Не заменять ею Weekly и не требовать этого календаря для Dynamic | Codex; [parity](../reports/ALPACA_PARITY_ACCEPTED_DAY_NEXT_2026_10_17.md), [readiness](../reports/ALPACA_MONTHLY_ACTIVATION_READINESS_2026_10_17.md) |
| ELDER_CRASH_HEDGE_V1.1 / contract SHAa25e4af2…fea3a28 | DEV_PASS режимного hedge с тонким запасом; standalone KILL; исходная ETS2M900 проверка OPEN | Source geometry/fill anchor reconciled; disabled adapter. Последний receipt:0 real events credited, не утверждение об отсутствии новых сигналов сейчас | Bybit preparation; ORDERS_OFF/no financial GO | Подключить реальные first-decision/context records к существующему adapter/journal, получить ≥30 events и frozen P1–P5, actual-fill protection/recovery. Никаких новых «двух недель» ожидания | Codex: source/execution; Claude: source/parity/900. [v1.1](../reports/ELDER_HEDGE_V1_1_SOURCE_PARITY_2026_10_17.md) |
| ETF_PREMIYA_BTC / DATA-only contract v1.1 | DEV candidate; prospective/Massive QA не завершены | Уже установлен существующий IBIT/BTC collector/adapter; historical81 не forward | DATA_ONLY, ORDERS_OFF | Первый actual19Oct decision/QA/hash delivery; Massive=PENDING до настоящей сверки | Codex: source; Claude: research. [existing delivery](../reports/TRADING_OS_NEXT_GATES_DELIVERY_2026_10_17.md) |
| LIQ_OTSKOK_4H_V2 / source V2.1 | Raw records не edge; source coverage UNKNOWN | Immutable17/18Oct delivery,25coins; действующий collector/epoch сохранён | DATA_ONLY, ORDERS_OFF | Ежедневная доставка; gap/UNKNOWN handling, warmup и events по замороженному контракту.27010raw18Oct не27010prospective сигналов | Codex: delivery; Claude: source/research. [delivery](../reports/LIQ_RESEARCH_DELIVERY_2026_10_17.md) |
| Brain V2 / existing Shadow | Added value INCONCLUSIVE | Общие context/journal interfaces уже существуют; money authority нет | SHADOW only | Paired BASELINE/Brain на одних возможностях; реальные execution joins. Не создавать второй Brain и не блокировать им допустимый самостоятельный LIVE | Claude + Codex; [existing delivery](../reports/TRADING_OS_NEXT_GATES_DELIVERY_2026_10_17.md) |

## Что именно показывают бэктесты Alpaca

Проверен существующий [пинованный reference manifest](../reports/evidence/alpaca_parity_repair_20261016/etalon_reference_manifest.json),
research981b62f / runner `simulate_live_protection_daily_proxy` /
trade core`2347a7ec606cd845`. Новый прогон или sealed judge не запускался.

| Метрика baseline Monthly/daily | Сохранённый воспроизведённый результат |
|---|---:|
| Период |2024-08-01…2026-07-11, правая граница исключена |
| Начальный / конечный модельный капитал |1000 /1299.710379 USD |
| Доходность за весь период |+29.971038% |
| MaxDD по дневной equity |7.569155% |
| Profit factor реализованных сделок |1.810942 |
| Закрытые сделки |64 |
| Отрицательные месяцы |9 из24 |
| Худший месяц |−4.244579% |
| Средняя gross exposure |26.134854% |
| Модельные расходы |10bps на сторону; параметры отдельно фиксируют market_gap10bps |

Это daily proxy с заданной моделью исполнения, не гарантия внутридневного
drawdown, будущего результата или точной экономической эквивалентности Weekly.
Два воспроизведения одной истории не образуют два независимых экономических
эксперимента. Для Weekly и EventReselection новые числа не выдуманы.

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

До рынка: KITY fallback/alert и rollout acceptance; fixed-version comparison
handoff Claude; causal source intake Elder. Это работы без ожидания торговой даты.
Недостающая численная safety policy не выводится из одного инцидента5.631s;
paid retry не используется как замена fault injection и code review.

19Oct:13:30UTC NET full DAY protection;13:31UTC лично разрешённый SHOP;
13:35UTC independent actual readback. Existing heartbeat16:35Cyprus также проверяет
SHOP,23:35Cyprus — первый IBIT; затем pause. Серверный timer не зависит от Mac,
локальный heartbeat при сне Mac может сообщить позже; своевременный отчёт не выдумывать.

После фактического входа: полное сопровождение разрешённого lifecycle и cash
reconciliation. Для непрерывного повторного отбора сначала экономическая приёмка
точной версии и отдельный bounded owner envelope; текущий one-shot не продлевать.

Новые paid attempts, две предложенные PM попытки, новые бюджеты и постоянная
автономия этим документом не разрешены. Корзина micro не доказывает семидневную
KITY: source membership/C2 уже MATCH, расходы/rounding/horizon — отдельный gate.
Фактический micro имел LONG114.87529/SHORT117.16109USDT и fees10.5282bps от entry
gross; эти значения нельзя молча заменить точными равными весами или нулевыми расходами.

Research owner получает [файловый status delta](../reports/STATUS_DELTA_FOR_CLAUDE_2026_10_18.md).
Его KARTA/VOROTA/код не редактировались, сообщения не отправлялись. Старые execution
tables в датированных reports — исторические snapshots; эта доска — текущий индекс
следующих gates, без собственной финансовой истины. Full repository suite и новый
independent financial review не заявлены.
