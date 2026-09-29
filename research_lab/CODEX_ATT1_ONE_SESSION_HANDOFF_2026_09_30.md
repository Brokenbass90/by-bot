# ATT1: handoff на одну сессию Codex, 30 сентября 2026

Подготовил Claude, 29 сентября, только чтением. Ни одного изменения
в production-коде, ни одного запуска на VPS. Всё ниже сверено с исходниками
в `bybit-bot-recovery-20260824@codex/recovery-20260824`; у каждого утверждения
указан файл и строка либо поле квитанции.

Цель документа одна: чтобы завтрашняя сессия началась с починки, а не
с выяснения, где мы находимся.

---

## 1. Что осталось до NEW ATT1 canary-ready

Два независимых фронта. Один инженерный, один наблюдательный. Их нельзя
путать: закрытие одного не приближает второй.

**Инженерный — authenticated binding.** По квитанции
`reports/ATT1_AUTHENTICATED_BINDING_2026_09_29.json` готово десять частей
(`completed_code`): пиннингованный подписанный GET-транспорт, идентичность
счёта и полные страницы позиций/ордеров, восстановление входа по точному
`orderLinkId` при потерянном ответе, преflight до записи в журнал, проверка
условного стопа позиции, идентичность и восстановление исполнения
координаторского выхода, фактический кэш против независимого расписания
фандинга, поздний кэш удерживает резервацию, финальность
«брокер плоский + журнал терминальный», идемпотентность перезапуска.
`binding_complete=false`, `canary_ready=false`.

**Наблюдательный — проспективная когорта.** Требуется 2–3 чистых
заполненных проспективных терминальных net-R жизненных цикла
(`CODEX_SESSION_CHECKPOINT_2026_09_06.md`, раздел «Next»). Фактически:
`clean_terminal_count=0`, `real_new_fills=0`. Эпоха
`att1-public-lifecycle-20260928-observation-timing`: 2 сессии,
1 с RECOVERY_GAP. Предыдущая эпоха `20260928-bounded-scan`: 10 полных
H1-циклов × 51/51, 2 заполненных симуляции (TRX/MNT), 2 RECOVERY_GAP,
0 чистых терминалов.

---

## 2. Точный blocker — и главное наблюдение этого разбора

Формулировка из квитанции (`critical_blocker`):

> BROKER_NATIVE_STOP_WITHOUT_COORDINATOR_EXIT_INTENT: exact stop-trigger fill
> cannot currently be adopted without inventing intent/receive timestamps;
> fail closed; do not activate NEW.

**Но алгоритм для этого уже написан.** Коммитом `d3a40ee` добавлена функция
`recover_new_att1_native_stop` — `bot/att1_coordinator_adapter.py:1416`.
Она делает ровно то, чего не хватает, и делает честно: берёт последний
durable `PROTECTION_ACK` через `_att1_saved_protection` (строка 1396),
проверяет, что сырой источник воспроизводит подтверждение, сверяет
идентичность сработавшего ордера с вооружённым по девяти полям
(`orderId, symbol, orderLinkId, createdTime, triggerPrice, stopOrderType,
positionIdx, side, closeOnTrigger, reduceOnly`), строит детерминированный
`exit_order_id = 'broker-stop:' + digest([account, orderId])` и берёт
`first_execution_ms` из фактических исполнений вместо выдуманной отметки.

**Её единственный вызывающий — тест.** Проверено grep-ом по обоим
репозиториям:

    ./tests/test_att1_native_stop_recovery.py:28   вызов
    ./bot/att1_coordinator_adapter.py:1416         определение

Рабочий путь `reconcile_new_att1_authenticated` (строка 1307) обрабатывает
только ветку `pending_exit is not None` (строка 1322). Когда биржевой SL
сработал без координаторского намерения, `pending` равен None, ветка выхода
пропускается целиком, и дальше на строках 1343-1345 (`session.refresh()` →
`receipt['held_qty']!='0'`) возвращается
`blocker='EXPOSURE_STILL_OPEN_ORDERS_OFF'`, резервация остаётся занятой.

То есть **blocker — это разрыв проводки, а не отсутствующий алгоритм.**
Завтрашняя работа сводится к тому, чтобы сделать `recover_new_att1_native_stop`
достижимой из аутентифицированного прохода: при `pending is None` и ненулевом
`held_qty` запросить страницы ордеров и исполнений по вооружённому
`orderId` из `PROTECTION_ACK` и передать их в существующую функцию.
Это оценка объёма работы, а не предписание, как её делать: контракт и
условия отказа ваши.

Оставшаяся часть цепочки из формулировки владельца
(`broker event → costs/funding → net-R → finality`) уже реализована и
переиспользуется: `recover_new_att1_native_stop` намеренно НЕ освобождает
резервацию и возвращает управление в
`reconcile_new_att1_lifecycle_receipts`, а расчёт стоимости и фандинга
идёт через `reconcile_new_att1_broker_finality` (строка 1127), который
вызывается из того же аутентифицированного прохода, строки 1386–1391.

---

## 3. Что открыть первым

    1  bot/att1_coordinator_adapter.py:1307   reconcile_new_att1_authenticated
                                              ветка pending is None — сюда
    2  bot/att1_coordinator_adapter.py:1416   recover_new_att1_native_stop
                                              готовая функция, нужен вызов
    3  bot/att1_coordinator_adapter.py:1396   _att1_saved_protection
                                              откуда берётся вооружённый стоп
    4  tests/test_att1_native_stop_recovery.py
                                              4 теста, уже покрывают чужой/
                                              изменённый ордер, отсутствие
                                              источника защиты, крах до финала
    5  bot/att1_coordinator_adapter.py:768    map_execution(native_stop=True)
                                              уже допускает пустой orderLinkId
                                              только для этого режима

Четвёртый пункт важен отдельно: `tests/test_att1_native_stop_recovery.py`
**отсутствует в `candidate_manifest.tests`** квитанции от 29 сентября —
там девять файлов, и этого среди них нет. Если проводка делается завтра,
тест стоит внести в манифест, иначе доказательство останется вне
верифицируемого списка.

---

## 4. Что уже PASS и что нельзя считать доказательством

**PASS и означает то, что написано:**

    166 focused-тестов локально и на целевом Python 3.12.3, 13 файлов
        сверены по хэшу
    прямая сверка главного счёта GET: 0 позиций, 0 открытых ордеров,
        transaction-log пустой список с явным null-курсором
    orders-off структурно: SEND_ENABLED=False, только GET, mutation-endpoint
        не в allowlist, NEW-сервис не установлен, реальных ордеров 0
    OLD PID 2150553 и публичный PID 2768300 не менялись, NRestarts=0

**PASS, но НЕ доказывает проспективный жизненный цикл** — это прямо написано
в самой квитанции, поле `verification.fixtures_are_prospective_evidence=false`,
и перечислено в `verification.synthetic_checks`:

    entry lost response            синтетика
    exit lost response             синтетика
    native SL unsupported          синтетика, и проверяет ОТКАЗ, а не приём
    protection identity            синтетика
    cash delayed then terminal     синтетика
    restart journal identity       синтетика
    reservation locked             синтетика

Отдельно: `17 полных H1-циклов × 51/51` и `heartbeat 0.62s` — это здоровье
сканирования, а не непрерывность под открытой позицией. Единственная сессия
MNT была `ENTRY_FINAL=CANCELLED` без `ENTRY_FILL` (книга cts 1790672484426
опережает submit 1790672484786 на 360 мс, правило причинности вернуло
ноль исполнений). Подтверждённый незаполненный вход — не чистый терминал,
и нулевое число новых гэпов при нём ничего не говорит о непрерывности.

---

## 5. Acceptance criteria на конец завтрашней сессии

Реалистично закрываемое за одну сессию:

    A1  recover_new_att1_native_stop достижима из аутентифицированного
        прохода: биржевой SL без координаторского намерения приводит
        к BROKER_STOP_TRIGGER + EXIT_FILL + EXIT_FINAL, а не к
        EXPOSURE_STILL_OPEN_ORDERS_OFF
    A2  фиксация отказа сохранена: чужой ордер, изменённая вооружённая
        идентичность и отсутствующий источник защиты по-прежнему
        AdapterViolation, слот остаётся заперт
    A3  после A1 путь доходит до reconcile_new_att1_broker_finality,
        то есть costs/funding/net-R/finality считаются на том же событии
    A4  tests/test_att1_native_stop_recovery.py внесён в
        candidate_manifest.tests, полный focused-набор PASS на 3.12.3
    A5  SEND_ENABLED=False, реальных ордеров 0, OLD не тронут,
        публичный 2s-гейт не ослаблен

НЕ закрывается завтра и не должно ставиться целью:

    canary_ready — требует 2-3 чистых заполненных проспективных терминала,
    а их появление зависит от рынка и от непрерывности наблюдения,
    а не от объёма работы за сессию.

---

## 6. Post-resize VPS truth

Зафиксировано со слов владельца 29 сентября после расширения машины:

    было (замер 29.09 17:37 UTC)        стало (после resize)
    ядер                 1              2 vCPU
    RAM всего            961 Mi         2 GB
    RAM доступно         33 Mi          ~1.5 GB
    своп занят           1.0 Gi из 2    0
    PSI cpu some avg300  39.08 %        резко ниже
    PSI io full avg300   10.05 %        резко ниже
    PSI memory full a300  6.09 %        резко ниже

Числа «до» сняты мной и сохранены в `VPS_DIAGNOZ_2026_09_29.md`. Числа
«после» пока со слов; чек-лист раздела 7 превращает их в замер.

Что из этого следует и чего НЕ следует. Не следует, что гэп ATT1 вылечен:
измеренная причина гэпа — `request_io 1691.766 мс` плюс 400 мс между
предыдущим наблюдением и стартом запроса, а это время round-trip,
а не голодание по CPU. Следует лишь то, что исчезла одна правдоподобная
альтернативная причина, и появилась возможность померить заново на чистой
машине. Никаких research-процессов на эту машину сегодня не переносится
именно для того, чтобы baseline был чистым.

---

## 7. Read-only чек-лист сравнения гэпов до и после resize

Только чтение. Ни одного рестарта, ни одного редеплоя.

**Шаг 0, обязательный первым.** Была ли перезагрузка при resize.

    uptime -p; who -b; systemctl show att1-lifecycle-zero-risk-v2 \
      -p NRestarts -p ExecMainStartTimestamp

Если машина перезагружалась, любой гэп сразу после подъёма нужно читать
как `restart lost public observation continuity` — драйвер эмитит
RECOVERY_GAP по этой причине сам, `run_att1_lifecycle_zero_risk.py:735`.
Не сравнивать такой гэп с дорезайзовыми как равный.

**Шаг 1. Что считает сам драйвер.** Порог зашит: гэпом считается разрыв
наблюдения больше 2000 мс, `_mark_observation_gap`, строка 653–658.
Вместе с гэпом теперь сохраняются `operation_timings` — это добавлено
коммитом `f3a2a42`, ради чего эпоха и разворачивалась.

**Шаг 2. Медленные операции без ожидания гэпа.** В heartbeat лежит
`recent_slow_operations` — последние 8 операций с `elapsed_ms >= 250`,
строка 924. Это и есть дешёвый датчик «стало ли быстрее»:

    jq -c '.recent_slow_operations' <heartbeat.json>

**Шаг 3. Гэпы в журналах эпохи.** Каталог
`/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/20260928-observation-timing`.
Для каждой сессии: события `kind=RECOVERY_GAP`, поле `observation_gap_ms`,
и файл источника по `source_sha256` в `sources/`, где лежат
`operation_timings` на момент гэпа.

**Шаг 4. Эталон для сравнения — ровно эти числа до resize:**

    gap_ms                                   2091
    orderbook request_io_ms                  1691.765551
    между наблюдением и стартом запроса      400 мс
    gap_source_sha256  cfe230979c51ad53ea5ca8195c06e20c80d7a6c702f86cf04cef05020277b70e
    ограниченный зонд 30 GET: макс           653.6 мс/запрос, один book age 2514 мс
    epoch_id     att1-public-lifecycle-20260928-observation-timing
    driver sha256 00b25de88c1601174e4f5ae1de90cd3913d2186ab808e9a086c1bf40736ae48f

**Шаг 5. Давление на машине в момент замера**, чтобы сравнение было
осмысленным: `cat /proc/pressure/{cpu,io,memory}` и `free -h`.

**Чего этот чек-лист НЕ доказывает.** Даже если медленные операции исчезли,
это не чистый терминал и не когорта. Гейт canary остаётся 2–3 чистых
заполненных проспективных терминала.

---

## 8. collect_bybit_orderbook_density.py — владелец и механизм запуска

Разобрано по обоим репозиториям.

**Что это.** WS-коллектор стакана Bybit orderbook.50. Держит книгу
(snapshot/delta, size=0 удаляет уровень), раз в 30 секунд пишет плотности
(стенки ≥ 4× медианы уровня, в пределах 3 % от мида, top-5 на сторону,
≥ $10k) в `runtime/orderbook/bybit_densities.jsonl`, около 3 тысяч строк
в сутки на 10 символов. Источник — `reports/PROJECT_STATE_LEDGER.md:521`.

**Чей.** Продакшн-контур: файл лежит в `scripts/` основного бота,
задокументирован в ledger Codex, в research_lab его нет. Это не мой процесс.

**Каким механизмом стартует.** Юнита нет и cron-строки нет. В обоих
репозиториях `*.service` только два — `deploy/systemd/sbr1-zero-risk-shadow.service`
и `deploy/liquidation-collector.service`; density среди них отсутствует.
В снимке 9 сентября (`.private/att1_handoff_20260909/second_incident.json`)
процесс 1277982 имеет PPID 1277979 и состояние `Sl+`; плюс означает
передний план терминальной группы. Это ручной запуск в screen или tmux.
Отсюда два следствия: перезагрузку он не переживёт и никто его не поднимет,
а значит после resize его, вероятно, уже нет.

**И отдельно — то, что стоит проверить.** У этого файла нет читателя.
Единственное упоминание `bybit_densities` во всём дереве — собственный
аргумент `--out` коллектора (`scripts/collect_bybit_orderbook_density.py:308`).
Ни одна стратегия, ни один скрипт, ни один конфиг его не читает. При этом
процесс работал 87 суток подряд, в снимке 29 сентября занимал 12.6 % CPU
на одноядерной машине и держал постоянное WS-соединение к той же бирже,
куда ходит ATT1 своими GET.

Прямой причинности я не утверждаю: гэп измерен как `request_io`, и
соседство процессов причиной не является. Но producer без consumer,
без супервизии, на 12.6 % ядра, рядом с процессом, у которого порог 2
секунды — это стоит одной минуты внимания завтра. Решение ваше,
я ничего не останавливал и не буду.

---

## Итог

    must fix tomorrow   Проводка recover_new_att1_native_stop в
                        reconcile_new_att1_authenticated: ветка pending is None
                        при held_qty > 0 должна доходить до готовой функции,
                        а не возвращать EXPOSURE_STILL_OPEN_ORDERS_OFF.
                        Затем costs/funding/net-R/finality через
                        существующий reconcile_new_att1_broker_finality.
                        Внести tests/test_att1_native_stop_recovery.py
                        в candidate_manifest.tests. Ордера OFF.

    must verify tomorrow Read-only чек-лист раздела 7, начиная с вопроса
                        «была ли перезагрузка при resize». Сравнить
                        recent_slow_operations и observation_gap_ms
                        с эталоном 2091 мс / request_io 1691.766 мс.
                        Проверить, жив ли collect_bybit_orderbook_density
                        и нужен ли он кому-нибудь.

    do not touch        OLD ATT1 LIVE и его позиции/риск. Публичный 2s-гейт.
                        Замороженный профиль
                        79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050.
                        Грязные RECOVERY_GAP-журналы v1 и v2 — они евиденция.
                        SEND_ENABLED. Alpaca LIVE. Research-процессы Claude
                        на этот VPS сегодня не переносятся.

    canary gate         2-3 чистых заполненных проспективных терминальных
                        net-R цикла. Сейчас 0. Плюс binding_complete=true,
                        плюс свежая точная правда по абсолютному риску OLD,
                        плюс отдельное письменное разрешение владельца.
                        Завтрашняя сессия этот гейт закрыть не может
                        и не должна пытаться.
