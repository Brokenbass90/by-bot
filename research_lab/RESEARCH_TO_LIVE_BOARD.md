# Trading OS — единая доска доведения до первой версии

18 октября 2026. Производственные receipts — в этой recovery-ветке; research
Claude сверено с опубликованным `0be44eca1f86929986b48ee77662d91b51a40255`.
Это производная доска: разрешения задаются owner packets, деньги — broker/journal/
native ledger, исследовательские выводы — замороженными research receipts.
Ни одна строка доски не создаёт финансовых полномочий.

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
| ATT1 / existing frozen production candidate | Старый registry не current edge; экономический review уClaude, NO_CURRENT_PROMOTION | REPAIR/BLOCKED_DATA: dated9Oct26sessions/18gaps/1cleanADA; это не свежий count18Oct | NEW ORDERS_OFF/old retirement preserved; отдельного GO нет | Существующий CTS-aware observation/replay и actualaccount/mode/cost gaps;2–3clean terminals unchanged. Не перезапускать завершённые probes/не менять2s | Codex + Claude; [evidence intake](../reports/evidence/alpaca_monthly_closeout_20261018/att1_intake.json) |
| KITY_BYBIT / frozen cb47f0e, spent micro V4, safety48020edd | **ECONOMIC_INCONCLUSIVE**;2026dataexists/crypto-filterwithdrawn | 10entry/10native/10exit cash reconciled; normal hold NOT_PROVEN. Fresh flat0/orders0. Safety fault/health48PASS,40exact/0fallback;24fileVPS candidate UNSELECTED | Bybit; d848a130…f40a1 **SPENT**, activeowner TERMINAL/ORDERS_OFF unchanged | Inert rollout proposal/183pins готово; separate owner version-selection decision+freshflat/finality/lock before any cutover. Новый денежный повтор не назначать; frozen research gates retained | Codex + Claude; [safety/source receipt](../reports/KITY_SAFETY_AND_ELDER_EVENT_INTAKE_2026_10_18.md) |
| Alpaca Weekly Dynamic / fe72557b…f400d | **ECONOMIC_FAIL по prereg правилу замены Monthly**:5.76%годовых/DD19.94% при20bps/side, исследованная известная история | Source59/owned lineage/один manager подтверждены; SHOP не запускался | Alpaca; владелец **ОТМЕНИЛ один SHOP18Oct**, entry timer disabled/inactive; NET сопровождение действует | Не расширять и не включать заново.19Oct только full NET DAY stop / readback; отсутствие SHOP — OWNER_CANCELLED, не execution FAIL | Codex; [new verdict/cancel receipt](../reports/evidence/trading_os_research_intake_20261018/receipt.json) |
| Alpaca EventReselection / separate ORDERS_OFF contract | **ECONOMIC_FAIL по правилу замены Monthly**:7.42%годовых/DD23.56%,1из7срезов/0из4кризисов | Существующий ORDERS_OFF candidate/restart tests сохранены | Alpaca; денежного GO нет | Убрать из денежного P0; не дорабатывать финансовый binding ради частоты. Новая гипотеза — отдельная prereg, без ретюнинга текущей истории | Claude: research; Codex: preservation. [intake](../reports/evidence/trading_os_research_intake_20261018/receipt.json) |
| Alpaca Monthly / V4 E2E candidate14dfa09f…35b4a81 | Предпочтительна по0be44ec:8.48%годовых/DD16.17%/PF1.537 при20bps/side; известная история, не unseenPASS | **ORDERS_OFF E2E PASS**: source→ownedbook→single manager→entry/native/restart→exit/cash/release.44file VPS candidate;135exactPASS/0fallback; actualTelegram15223; disabledschedule/rollback PASS | Новый Monthly financial GO не выдан; NET сохранён; SHOP отменён | Инженерия закрыта.30Oct actual closedsource/selection/risk→точный личный GO→2Nov14:30–14:35UTC при fresh custody/cash/finality/single-manager handoff. CASH допустим; NO_SEND без datecarry | Codex; [завершённый candidate/activation packet](../reports/ALPACA_MONTHLY_E2E_COMPLETION_2026_10_18.md) |
| ELDER_CRASH_HEDGE_V1.1 / SHAa25e4af2…fea3a28 | DEV_PASS regime hedge; standalone KILL; ETS2M900 OPEN | **Actual DATA_ONLY intake/restart PASS**,18813rows/15209firstshort; prospectivecredit0.100timelygeom f1=.50 vs frozen.55 BLOCKED;440late | Bybit preparation; ORDERS_OFF/no financial GO | Claude versioned producer/contract reconciliation, no Codex parameter repair/backfill. Then causal context/risk/instrument into existing adapter and original≥30events/parity/latency/restart gates | Codex: source; Claude: frozen semantics/900. [actual intake/fixture](../reports/KITY_SAFETY_AND_ELDER_EVENT_INTAKE_2026_10_18.md) |
| ETF_PREMIYA_BTC / DATA-only contract v1.1 | DEV candidate; prospective/Massive QA не завершены | Уже установлен существующий IBIT/BTC collector/adapter; historical81 не forward | DATA_ONLY, ORDERS_OFF | Первый actual19Oct decision/QA/hash delivery; Massive=PENDING до настоящей сверки | Codex: source; Claude: research. [existing delivery](../reports/TRADING_OS_NEXT_GATES_DELIVERY_2026_10_17.md) |
| LIQ_OTSKOK_4H_V2 / source V2.1 | Raw records не edge; source coverage UNKNOWN | Immutable17/18Oct delivery,25coins; действующий collector/epoch сохранён | DATA_ONLY, ORDERS_OFF | Ежедневная доставка; gap/UNKNOWN handling, warmup и events по замороженному контракту.27010raw18Oct не27010prospective сигналов | Codex: delivery; Claude: source/research. [delivery](../reports/LIQ_RESEARCH_DELIVERY_2026_10_17.md) |
| Brain V2 / existing Shadow | Added value INCONCLUSIVE | Общие context/journal interfaces уже существуют; money authority нет | SHADOW only | Paired BASELINE/Brain на одних возможностях; реальные execution joins. Не создавать второй Brain и не блокировать им допустимый самостоятельный LIVE | Claude + Codex; [existing delivery](../reports/TRADING_OS_NEXT_GATES_DELIVERY_2026_10_17.md) |

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
Его KARTA/VOROTA/код не редактировались, сообщения не отправлялись. Research-копия
RESEARCH_TO_LIVE_BOARD.md пока физически существует на0be44ec: Claude предложил
заменить её ссылкой сюда, но это ещё не выполнено. Не заявлять устранение дубля. Старые execution
tables в датированных reports — исторические snapshots; эта доска — текущий индекс
следующих gates, без собственной финансовой истины. Full repository suite и новый
independent financial review не заявлены.
