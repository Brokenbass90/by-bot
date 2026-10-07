# OS2: что доказано, как измерять пользу и что передать Claude

Контекст проверен 7 октября: origin recovery5791b85, research001f822.
Основания: OS2_SHADOW_BRIDGE_DELIVERY_2026_10_07.md/JSON, утверждённая спецификация,
research/fabrika-v1@001f822:research_lab/os2/B3_TZ.md и B3_KONFIG.json.
Документ уточняет существующий план; не меняет judge, policy, стратегию или LIVE.

## Текущая правда

SHADOW_WIRING_PASS означает локальный инженерный результат на synthetic fixtures.
Реальные источники дают POLICY_UNAPPROVED. Мост не установлен на VPS, не принимает
денежные решения и не интегрирован с действующим Factory controller. Нормализация
rank=fixture/expected_net_r=1 не является измеренным edge. 118targetedPASS и
4046fullPASS/57старыхFAIL подтверждают проверенный код, но не прибыльность.

Восстановлена связь существующих компонентов в изолированном кандидате, а не весь
production Trading OS. Общая политика капитала, реальный источник/паритет и
экономический эффект ещё требуют evidence. Ollama/DeepSeek advisory-only; worker
в рамках этого delivery не запускался. Предыдущие broker/PID snapshots сохраняют
свои даты; здесь нет новой проверки LIVE.

## Не начинать все исследования заново

| Уровень | Повторить | Сохранить |
| --- | --- | --- |
| Замороженная стратегия | Адаптер/parity и затронутый execution contract при подключении | Сигнал, universe, hold, costs, исходный verdict; нет нового judge ради OS2 |
| Общая portfolio policy | Хронологическое сравнение A/B/C, состояние допуска/слотов/exposure отдельно для каждой руки | Одинаковые возможности, риск, капитал и cost assumptions |
| Реальное исполнение | Closed-data parity, venue/account feasibility, lifecycle/recovery, prospective/PAPER | Действующие owners, protection, caps и отдельные money gates |

Нельзя просто отфильтровать таблицу уже независимых доходностей и назвать это
исполнением портфеля. Отказ меняет occupancy, последующие допускаемые сделки,
quantity/costs и idle capital. Replay ведёт отдельное причинное состояние каждой
руки. Криптовалютный BTC regime не становится автоматически правилом для Alpaca,
FX или других рынков. KITY — атомарный frozen long/short basket; выключение его
отдельных short-ног меняет стратегию и требует отдельного challenger.

Новый regime gate меняет торгуемый набор сделок: старая profitability receipt не
доказывает profitability новой версии. Старый baseline остаётся контролем; killed
семейства не возвращаются без нового отдельно зарегистрированного механизма.

## Измерение эффективности

Первый research test уже заморожен в B3, его критерии не меняются:

- A: always_on; B: leg_filter без regime; C: routed по замороженному REZHIM_V1.
- Research contract: одинаковые1R/12слотов/один символ—одна позиция и frozen costs.
  Эти единицы не равны трём fixture-слотам и не являются LIVE капиталом.
- На склеенных test folds C должен быть выше A и B по totalR;
  C≥B минимум в3 из4folds; maxDD C≤1.2×maxDD A.

Контроль B нужен, чтобы отличить пользу regime от простого исключения слабых ног.
FAIL не требует очередной подгонки: сохраняется verdict, baseline продолжается,
а новый механизм/классификатор становится отдельным prereg на пригодных данных.

Для execution/money acceptance нужны также netUSD на одинаковом капитале,
fees/slippage/funding, mark-to-market DD и хвосты открытых позиций, exposure и
concentration, turnover, idle cash/time invested, число независимых сделок и
потерянные прибыльные возможности. Операционные счётчики отдельно: UNKNOWN,
freshness failures, gaps, rejected minimums, protection/finality, restart parity.
Это раскрытие экономического/операционного риска, не новые задние критерии B3.
Дополнительные будущие PASS rules фиксируются до соответствующих новых outcomes.

Сокращение количества сделок может улучшить риск и net return, но само по себе
не является успехом. Система не создаёт long/range edge из одного short sleeve.
Статистическая неопределённость и недостаточный sample должны быть видны в отчёте.

Четыре research defects исправляются до доверия B3: equity/DD с начальным нулём;
train только по доступным terminal outcomes; ровно четыре закрытых H1 в4h;
непрерывный portfolio DD между folds. Требуются прозрачные old/new code/source
locks и проверка prior consumption. Известные SEALED_V2 leg aggregates не
доказывают строгую независимость; при её отсутствии нужен frozen prospective test.

## Связь с Factory

Существующий путь остаётся hypothesis→falsification→frozen judge→READY_FOR_BUILD/KILL,
WIP=1 outcome slot. Factory подтверждает edge самого замороженного механизма;
portfolio acceptance отдельно оценивает добавленную пользу при текущих рукавах.
Без standalone evidence нельзя спасать стратегию одним подобранным regime фильтром.
Условный режимный механизм оформляется самостоятельным frozen challenger.

Целевой intake уже следует из спецификации: immutable strategy/version/code pins,
signal/source prefix hashes, closed-data cutoff и availability, universe/hold/cost
contract, направление либо атомарная корзина, исходный verdict/limitations и
execution requirements. Дополнительные portfolio diagnostics: дублирование
экспозиции, корреляция, capacity, tails и ограниченность sample. Пакет является
evidence/proposal, не разрешением приказа брокеру и не собственным risk authority.

OS2 возвращает Factory source-bound decision/rejection/terminal/health diagnostics
как повод для нового prereg. UNKNOWN, operational gap, недостаточный sample и
statistical degradation различаются. Auto-patch, auto-retune и auto-promotion
денег отсутствуют. Реальное соединение intake/diagnostics — следующий bounded
adapter после денежного P0, а не уже работающий факт.

## Готовый текст для Claude — непосредственная отправка не выполнялась

> KITY raw23:55OI и08–09Oct frozen forward parity остаются P0. OS2 не должен их задерживать.
> Прочитай OS2_FOUNDATION_AUDIT_2026_10_07.md/JSON в recovery-ветке и устрани четыре
> B3 causal/DD findings до доверенного judge: initial equity0, available terminal
> train, complete closed4h, continuous cross-fold DD. Проверь prior consumption;
> сохрани прозрачный old/new implementation amendment и hashes, не меняя frozen
> legs/regime/affinity/folds/costs/PASS criteria. Не перезапускай уже consumed judge.
> Сравни A/B/C по frozen B3, выдай источник/denominators/limits и один honest verdict.
> Отдельно обозначь independence SEALED_V2; при отсутствии untouched evidence не
> называй его независимым подтверждением. Не обещай LIVE из исторического PASS.
> Для следующих Factory пакетов сохраняй immutable signal/available-time/code/source/
> hold/cost/basket metadata. Portfolio contribution — отдельный acceptance stage;
> не встраивай новый regime filter в KITY/ATT1 и не переоткрывай killed families.
> Codex подключит один canonical real closed-data source в orders-OFF и независимо
> проверит parity/causality. Реальные orders остаются отдельным owner GO.

## Ближайший порядок и ожидаемый результат

Сегодня original Alpaca window13:30–13:35UTC/PAPER/protection; затем KITY rawOI и
08–09Oct actual basket/account execution packet. Параллельно Claude repairs B3.
После этого bounded real-source adapter и causal parity→валидная frozen policy→
shadow/PAPER execution evidence→отдельный ORCHESTRATOR_POLICY_V1 GO. Ожидаемый
результат — доказуемые причины выбора/отказа, согласованная экспозиция и ранняя
диагностика проблем; улучшение net portfolio performance должно быть измерено.
Включение/выключение относится к новым входам; exits/protection остаются у owners.
