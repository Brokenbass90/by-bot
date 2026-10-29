# PUMP4 TINY-2 — проект серийного пилота ORDERS_OFF

29 октября 2026. Статус MODEL_SERIAL_GATE_PASS / PRODUCTION_SERIAL_INTEGRATION_OPEN /
NOT_READY_FOR_OWNER_GO. Основание — запрос владельца подготовить продолжение
работы и переданное PM-ревью. Текущий pilot66a7be9c неизменён и не продлевается.

## Задача и ограничения

Проверить несколько последовательных новых допустимых сигналов frozen PUMP4 V1
при одной одновременной позиции через существующий account owner. Это продолжение
проверки исполнения и расходов, не экономический PASS по10/20 сделкам. Изменения
сигнала/порогов/40-60/hold168h, V2-фильтры и режимный Brain не входят в этот этап.

Текущий Pump4AccountOwner.__init__ требует max_entries==max_positions==1;
advance/post_reserved используют единственный immutable admitted-lifecycle.json.
Просто увеличить конфиг или стереть этот файл — нарушение send-once/custody.

## Варианты и выбранное инженерное направление

- Новый универсальный multi-strategy engine: лишняя новая система; не выбран.
- Перезапуск нынешнего one-shot с удалением claims: разрушает идемпотентность;
  недопустим.
- Версионное продолжение существующего owner + неизменные lifecycle/source/lease
  primitives: выбранный проект для изолированной ORDERS_OFF реализации. V1 scopes
  продолжают требовать один lifecycle и не получают серию из версии кода.

## Предлагаемые финансовые условия — только для расчёта кандидата

Allocation50USDT/gross30/reserve20, одна позиция, initial scenario risk1USDT;
существующие day2/week3/drawdown6 как отправная точка сравнения. Вариант первого
серийного пакета: не более10входов, lifetime loss-admission3USDT и7дней для НОВЫХ
входов, завершение по первому достигнутому ограничению. Конкретные даты и вся
финансовая конфигурация фиксируются только в финальном review packet.
Эти числа — предложение Codex, не принятое владельцем расширение текущего GO.
Иные число/срок/loss budget требуют такого же отдельного решения. Цель эксперимента
не оправдывает ожидание10сделок или трактовку INCONCLUSIVE как FAIL.

Cross margin сохраняется:50USDT не изолированы, stop/loss budgets не гарантируют
предел потерь. Не меняем margin mode, leverage, Bybit account или риск остальных
средств. Не гарантируем минимальную частоту или доход.

## Требуемое поведение и повторное использование

1. Новый отдельный scope/root/version, старые GO/claims/barriers/flow history
   неизменяемы. Тот же исходный account lock и единственный финансовый writer.
2. Долговечный последовательный admission ledger связывает scope, ordinal,
   immutable plan и flow. Номер резервируется ДО send; потерянный ответ, отказ,
   частичный fill или рестарт не освобождают неопределённый admission.
3. Следующий вход возможен только после source-backed terminal reconciliation
   предыдущего lifecycle, отсутствия живых owned orders/exposure и известных либо
   отдельно обоснованно ограниченных обязательств. Нет активности != нулевая fee.
4. Стратегический cursor/cooldown и дедупликация сохраняются между lifecycle;
   каждый план исполняется максимум один раз. Текущий/live H1 не проигрывается как
   новый сигнал при handoff. Лишь одна позиция одновременно.
5. Общие day/week/drawdown/lifetime метрики и loss latches охватывают всю серию,
   включая открытый mark-to-market/расходы по выбранной точной метрике. Они не
   сбрасываются новым flow или рестартом. Связь USD/USDT валют явная.
6. Entry expiry/max entries/loss/source/stop/custody failures запрещают новые
   входы; сопровождение уже открытого owned lifecycle сохраняется. Unknown
   accounting blocks admission, but cannot silently abandon protection.
7. До реальной активации все transport/send проверки — memory wire/fixtures и
   изолированный ORDERS_OFF. Никаких production constructors/claims/POST.
8. Источник execution quality — существующие receipts, execution/observations и
   risk journals. Отчёт до первой сделки NO_LIVE_TRADES, пустой net не прибыль.

## Acceptance перед финансовым пакетом

- Исходный one-shot scope и его все guards неизменны; новый scope не принимает
  старый GO/marker. Replay первого immutable плана не второй entry.
- Два синтетических terminal lifecycle последовательно,0overlap; ограничение
  количества и cumulative loss переживает restart/UTC day-week boundary.
- Crash после admission/после send, lost ACK, partial entry/40-60/stop/weekly hold,
  late fees/funding, foreign exposure, missing tail и duplicate H1 => reconcile,
  no blind resend/no reset; не требовать фактической недели от модельных часов.
- Неопределённые pending costs не становятся нулём; модельное резервирование
  не выдаётся за окончательную broker finality.
- Сначала actual первый V1 lifecycle и независимая сверка исполнения/расходов;
  затем точный serial scope + независимая приёмка + новый OWNER GO. Если V1 не
  получил сигнал до expiry, не продлевать его; отдельно решить дальнейшую цель
  пилота по частоте возможностей и готовности, не имитировать выполненный цикл.
- Безопасный future handoff одного writer, broker/current scopes/no foreign
  positions/native custody/rollback проверяются отдельно; сейчас ни один unit
  или активный runner не меняется. Rollback не восстанавливает spent GO и не
  останавливает защиту owned позиции.

## Следующая реализация

Рабочие файлы: research_lab/pump4_account_owner_v1.py и существующие
pump4_execution_supervisor_v1/lifecycle/source adapters; конкретный diff только
после воспроизводимых failing isolated tests. Начать со сценария второго admission
в чистом test root: V1 отказывает, versioned ORDERS_OFF candidate обязан принять
его лишь после подтверждённого terminal первого; restart не открывает дубликат.
Затем targeted suite tests/test_pump4_account_owner_v1.py и supervisor regressions
по затронутым путям, один независимый review. Существующий LIVE V1 не переключать.

## Выполненный первый инженерный этап —29Oct

Реализован отдельный fixture-only `research_lab/pump4_serial_orders_off_v1.py`,
переиспользующий неизменный V1 owner/lifecycle/journal/lease. Он намеренно не
принимает реальные account fingerprints/LIVE и не содержит отправки ордеров.
Два memory-exchange lifecycle последовательно +restart +89targetedPASS; нет
реальной broker acceptance/finality или готового LIVE scope. Это локальная
модель серийного admission, а не исполненный production handoff.

Ruling: неизвестные расходы остаются неизвестными; только явная синтетическая
оценка/reserve разрешает завершить МОДЕЛЬНЫЙ цикл. Она не может быть перенесена
в финансовый GO или автоматически освобождать реальный бюджет. Next: versioned
production owner/source accounting +supervisor intake binding; существующий V1
не изменялся. Evidence: reports/PUMP4_TINY2_SERIAL_GATE_2026_10_29.md.
