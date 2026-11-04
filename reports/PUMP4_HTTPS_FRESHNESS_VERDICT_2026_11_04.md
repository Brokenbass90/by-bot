# SIRENUSDT: вердикт HTTPS-гейта —4Nov2026

**Исторический вердикт: UNKNOWN.** Это не VALID_BLOCK и не доказанный DEFECT.
Факт отказа03Nov03:00:15.697UTC подтверждён immutable supervisor receipt;
конкретный компонент отказа не восстанавливается без утраченных HTTPcaptures.

Проверка ENTRY_SOURCE_STALE объединяет:
`0 <= now_ms - source_ms <= 5000` AND
`0 <= now_ms - available_ms <= 5000`.
Первый timestamp — max Bybit response body.time двух HTTPS-загрузок; второй —
max localreceive. Это не60s H1 deadline и не возраст сигнальной свечи.
Один error string не показывает, какая часть/нижняя или верхняя граница сработала.

## Что проверено сейчас без LIVE-изменений

С actual VPS/pinnedcandidate05f896 выполнено6publicGET по тем же двум точным
историческим query параметрам SIREN; actual время4Nov13:17:51–13:17:59UTC.
Это получение нынешних ответов об исторических барах, не восстановление старых
ответов/входа и не попытка торговать старый сигнал.

| Проба | Загрузка пары | Возраст server time | Возраст localreceive | Проверки0..5s |
|---|---:|---:|---:|---|
|1|342мс|88мс|0мс|PASS|
|2|982мс|406мс|8мс|PASS|
|3|324мс|87мс|1мс|PASS|

Отдельно прочитан immutable newlineprefix SIREN до исходного сигнального бара:
233события, полная исходная LifecycleJournal chain/canonical verification на
in-memoryfd, безsourceflock/ремонтаpartialtail. Точный decision_id воспроизведён
чистым reducer; никаких outcomes/PnL/financialowner не запускалось.
Chainvalidation91.953мс;3replayпрохода96.857/116.893/80.179мс. После трёх проходов
serverage434мс/local335мс. Повторный replay сам по себе здесь превышения5s не дал.

## Предел вывода

В production один и тот же capture участвует в candidate precheck, plan_now и
повторном plan_now после accountGET. Это действительное свойство кода, но не
доказательство дефекта: проверки перед исполнением нужны, а захваченные данные
могут действительно устареть. Полный account/instruments GET путь здесь не
профилировался; private APIs/финансовые конструкторы для этого не запускались.
Факт быстрых нынешних ответов не оправдывает/не опровергает отказ3Nov.

Текущий owner активен3669955/NRestarts0. Не менялись strategy, DATA,5s,60s,
scope,keys,GO,units,locks,HАLT/claims. Минимальный финансовый ремонт не предложен,
потому что DEFECT не доказан. Нужная будущая диагностика существующей ошибки:
stage,request/receive/server/check timestamps и rawSHA, сохранённые при самом
отказе. Это улучшение evidence, а не ослабление freshness; не установлено в LIVE.

[Санитизированные фактические timestamps/SHA](evidence/pump4_https_freshness_20261104/actual-verdict.json).
Репродуцируемые GET-only scripts рядом; полные raw responses только приватно.
Расследование старого эпизода на доступных evidence ограниченно закрытоUNKNOWN;
исправность будущего полного финансового пути этим не подтверждена.

## Сопутствующий статус

E2: последние автоматические вызовы13:22UTC,оба WAITING_REAL_SIGNAL/0measurements/
0joins. Пустые журналы не заменяются тестовыми/старыми сигналами.
Monthly: поиск connected mail4Nov13:15UTC нашёл только прежний autoack; body422
и причина по-прежнемуUNKNOWN, новых POST/GO/переноса окна нет. Почтовые данные
не публикуются. Для текущего Polymarket ORDERS_OFF депозит/кошелёк не требуются;
финансовый запуск исходной V2 запрещён, новое экономическое решение отсутствует.
