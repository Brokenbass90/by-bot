# KITY: фактические 10/10; Alpaca: личное включение подтверждено

18 октября 2026. Исправление синхронизации:
`8500c97d32a2ae965c2edcd481cc1541627d8364`.
[Машинный receipt](KITY300_EXECUTION_AND_ALPACA_ARMED_2026_10_18.json).
Предыдущий [пакет подготовки](TRADING_OS_OWNER_GO_AND_MONDAY_DELIVERY_2026_10_18.md)
описывает состояние до личных команд владельца и больше не является текущим статусом.

**Владелец лично выполнил обе команды. Codex не повторял их и проверил результат
независимыми GET, чтением файлов и SQLite `mode=ro`.** За проверку: 12 broker GET,
0 broker writes, 0 изменений на VPS. Локальное исправление KITY на VPS не развёрнуто.

## KITY — что действительно произошло

Команда `1792300557626855584`, policy
`d848a1300ae866bd5d6fcfd49b6dbb196cb6183a12aa71dbb4f8bf6ae77f40a1`, plan
`8698042d7cf48fc884f7c3cacec8d38b86d1874d7ea15a98f85b2c487107479c`.
**Policy SPENT; controller TERMINAL / ORDERS_OFF. Повторный запуск запрещён.**

| Проверка | Фактический результат |
|---|---|
| Исходная корзина | Все 5 LONG / 5 SHORT, прежние quantities/rounding/native rules |
| Свежесть единственного post-GO capture | CTS upper 1422 ms, лимит 2000 ms |
| Номинал | reference 232.066580; фактический вход 232.03638 USDT; cap 300 |
| Вход | 10/10 полных исполнений; 14 execution rows, включая partial fills |
| Native SL | 10/10 full-quantity Market/reduce-only; все связаны до первого выхода |
| Выход | 10/10 owned reduce-only; 11 execution rows |
| Финальность | 25 уникальных исполнений = 25 точных денежных проводок |
| Независимый broker GET около 05:18 UTC | 0 позиций, 0 открытых ордеров |
| Торговый cash flow | **+0.02231 USDT** |
| Фактические комиссии | **0.24429250 USDT**; ставки различаются по инструментам |
| Funding | **0 USDT** |
| Итог после расходов | **−0.22198250 USDT** |

Ниже реальные средневзвешенные цены, а не цены отправленных лимитных заявок.

| Инструмент | Вход | Qty | Entry VWAP | Exit VWAP | Комиссии, USDT |
|---|---|---:|---:|---:|---:|
| BTWUSDT | LONG | 10 | 2.44993 | 2.44999 | 0.02694957 |
| XAUUSDT | LONG | 0.005 | 4169.13 | 4169.12 | 0.01146510 |
| LTCUSDT | LONG | 0.4 | 58.95 | 58.94 | 0.02593580 |
| VVVUSDT | LONG | 1.08 | 22.538 | 22.539 | 0.05355149 |
| BNBUSDT | LONG | 0.03 | 720.31 | 720.73 | 0.02377717 |
| XAUTUSDT | SHORT | 0.005 | 4155.77 | 4155.78 | 0.02285677 |
| XPLUSDT | SHORT | 312 | 0.07842 | 0.07841 | 0.02691205 |
| XAGUSDT | SHORT | 0.429 | 57.1 | 57.11 | 0.01347394 |
| GRASSUSDT | SHORT | 39 | 0.6199 | 0.6196 | 0.02658728 |
| SPCXUSDT | SHORT | 0.16 | 145.27 | 145.26 | 0.01278333 |

Фактические native orders созданы биржей в 05:16:15.284–15.285 UTC. После owned
выходов они Deactivated; это не отсутствие защиты во время позиции. Все десять
связаны в журнале до первого EXIT_INTENT. Повторное чтение unit/heartbeat
подтвердило PID 2568196, прежний account-lock inode 818853, error=null.
Статус ответа `BATCH_ACK_RECONCILE_REQUIRED` означает принятие десяти заявок с
обязательным последующим readback; он сам по себе не является ошибкой.

## Почему выход оказался ранним

**Технический оборот 10/10 с защитой и финальностью доказан. Штатное удержание
корзины не доказано: произошёл ранний безопасный выход из-за дефекта синхронизации.**

| UTC | Событие |
|---|---|
| 05:16:14.802 | Один durable batch intent / начало отправки |
| 05:16:15.282 | Биржа исполнила все десять входов |
| 05:16:17.858 | BROKER_SNAPSHOT видит 10 позиций; журнал пока видит fill только VVV |
| 05:16:23.489 | Все десять fills/native IDs уже подтверждены, ownership match восстановлен |
| 05:16:25.623 | Первый owned EXIT_INTENT |
| 05:17:20.490 | Последнее исполнение выхода по broker execTime |
| 05:17:23.490 | FINALITY / полная денежная сверка |

Один account-wide execution capture был получен раньше, чем остальные endpoints
стали согласованы. Order/history уже сообщали terminal cumulative qty по десяти
входам, но execution capture/WS ещё давали только VVV. Более поздний position
readback показывал десять позиций и девять ещё не связанных native IDs. Поэтому
BROKER_SNAPSHOT установил ownership_conflict и sticky entry_blocked. Через
5631 ms snapshot уже полностью совпал с журналом, но entry_blocked правильно
не сбросился сам: начался полный owned выход.

Это воспроизведено чистым reducer replay всех исходных событий. Причина не в
cap300, свежести первоначальных цен или срабатывании loss trigger15. Все 11
RISK_OBSERVATION давали MONITOR. Первое расхождение обнаружено на event index34,
не придумано из конечного controller receipt. От первой отправки до финальности
68.688 секунды; 30 минут — максимальная длительность, а не реально выдержанный срок.

## Что исправлено локально

В существующий ACCOUNT_READBACK_V2 adapter добавлен ограниченный GET barrier:
если известный owned terminal entry имеет cumulative qty больше подтверждённых
execution rows, перед custody snapshot выполняется **один** свежий полный account
order/execution readback вне старого cycle cache. Затем связываются только точно
доказанные native SL и выполняется обычный свежий position snapshot.

Новые fills не выводятся из количества позиции; конфликт не игнорируется;
существующий entry block не снимается. Нет ожидания до PASS, повторных отправок,
изменения deadline, комиссии, размера или risk policy. Если свежий readback не
даёт доказательств либо содержит чужую позицию/ордер, сохраняется fail-closed.

- RED до исправления: измеренная последовательность даёт 1 FAIL / 6 PASS.
- После исправления: 8 новых incident cases, включая missing/foreign/incomplete,
  restart replay, сохранение существующего block и исходного deadline.
- Финальный запуск `.venv/bin/python -m pytest -q tests/test_kity*.py`:
  **859 PASS, 0 FAIL, 26.39 s**. Полный suite репозитория не запускался.
- [Reduced fixture](evidence/kity_20261018/entry_readback_race.json) содержит
  измеренные количества/цены/порядок событий и pseudonymized IDs. Это производный
  offline fixture с явным обозначением восстановленного pre-exit native status,
  а не опубликованные сырые broker captures. Оригиналы сохранены приватно и
  зафиксированы hashes в receipt; их журнал и события не изменены.
- SHA deployed adapter остаётся
  `8500b50d89e19fa3435e60ad78da9fb19fdc6995a4c6679d2518213f38bc128d`.
  Никакого финансового deployment или нового GO этим commit не создано.

Root review выполнен; независимый финансовый review недоступен и не заявляется.
Этот оборот не засчитывается в C1/C2/C3, research edge или разрешение на регулярную торговлю.

Локальный rollout dossier: единственный production-module diff —
`research_lab/kity_micro_account_readbacks_v2.py`, old SHA8500b50d…bc128d →
**bcc72d6d53aef674ecbc899033dd46e1bd994046fa3b5c7ef0a7d16afe604906**.
Исходные policy, reducer, broker writer и риск-лимиты не меняются. Перед будущим
rollout требуются точное совпадение старых source pins, тот же account lock,
TERMINAL/flat readback и отдельный неактивный candidate с пересчитанными полными
source guards. Запущенный каталог не перезаписывать; spent journal/claims не
переносить в новый эксперимент и не сбрасывать. Новый pin/переключение owner
должны войти в отдельный личный пакет. Пока статус **LOCAL_VERIFIED / NOT_DEPLOYED**.
Новая платная попытка автоматически не назначается: сперва rollout/replay;
если отдельный micro потребуется, для него нужен новый ограниченный OWNER GO.

## Alpaca — что включено владельцем

Личный receipt в **05:16:06.059 UTC**:
`MONDAY_PERSONALLY_ARMED_PENDING_FRESH_OPENING`, broker_writes=0,
entry_executed=false. Codex независимо проверил действующие unit pins,
личный arm, точный архив прежнего HALT, реальную NET lineage и таймеры.

- Scope `4630ebe2d63659ed98cf549c3adc8bf1d9cf330de7a7e165e5be051896a7bd1e`.
- Manifest `d4fd22de33e016c7a338af063a684362214be2fe2935b3f4764829d30b48405e`.
- Control `b5a9c752baae49853c42068b0b4c49925094d05eb6a6448023063ddc010b6a26`.
- Выбраны четыре финансовых unit-файла из рассмотренного пакета, предыдущий
  точный HALT архивирован владельцем; новый HALT по-прежнему блокирует вход.
- Реальный NET child зарегистрирован один раз; прежний общий lock inode813893.
- Один существующий manager/timer: исходное NET сопровождение, затем новый owned
  lifecycle. Автоматический tick **05:20 UTC** завершился с кодами 0/0:
  `LIVE_WAITING_REGULAR_SESSION`, затем `NO_NEXT_OWNED_INTENT`.
- Новый entry timer **active/waiting**, следующий запуск:
  **понедельник 19 октября, 13:31 UTC / 16:31 по Кипру**.
  Сам entry service пока inactive/dead с Result=success: он ещё не выполнялся.
- GET monitor timer активен на **13:30 UTC /16:30 по Кипру**; manager остаётся
  на прежнем пятиминутном расписании.

Broker GET около05:18 UTC: NET **0.325167779**, открытых ордеров0, рынок закрыт.
Последний принятый native floor277.69 сохранён. DAY-защита прошлой сессии истекла;
это **не** доказательство действующего воскресного стопа или защиты понедельника.
Фактический full DAY re-arm19Oct остаётся обязательным P0 перед покупкой.

Scope — один вход **SHOP ≤113.60999978874 USD**, модельный первоначальный
stop risk≤9.07098231494 USD из исходного AMD slot. Сохраняются исходный Weekly
Dynamic, capital487.42, gross0.70, cooldown, первый пятиминутный интервал и
max1entry/session. Это не Monthly и не новая трактовка перескана после каждого
стопа. Реальные qty/цена/стоп зависят от свежих проверок открытия.

Нет полного current-session NET stop, изменились ownership/позиция/ордер, HALT,
cash/gross/source/asset/quote/clock gates — **NO_SEND**, без второй попытки и
переноса даты. Включённый таймер не доказывает broker fill или прибыль.

## Дальнейшая execution board

| Приоритет | Готово | Следующий реальный gate |
|---|---|---|
| P0 KITY | Фактические 10 входов/10 защит/10 выходов; flat/cash сверены; локальная race regression исправлена | Проверенный rollout dossier локального исправления; новый ограниченный micro только после отдельного OWNER GO |
| P0 NET | Original manager активен, floor/ownership сохранены | 19Oct13:30UTC фактический full DAY stop либо точный отказ/terminal status |
| P0 Alpaca Dynamic | Владелец лично включил одноразовый вход; source59, lineage, manager tick и timer проверены | 19Oct13:31UTC fresh admission→SHOP fill→native; затем независимый readback |
| Alpaca Monthly | Ранее поставленный source58/selection/ratchet кандидат сохранён отдельно | 30Oct selection, 2Nov14:30UTC ближайшее окно; отдельные financial gates |
| P1 IBIT | Ранее поставленный DATA-only adapter сохранён | Первый actual prospective19Oct и доставка; Massive PENDING до реальной сверки |
| P1 LIQ | Ранее доставлены immutable17/18Oct snapshots, 27010raw/all25 для18Oct | Следующий ежедневный snapshot; coverage UNKNOWN/source gate false, raw не prospective/PnL |
| P1 Brain/Reporting/Accounting | Один существующий Shadow / общие журналы | Воспроизводимый multi-strategy context→risk→decision с сопоставлением исходов |
| P1 Elder | Предыдущая prospective parity инфраструктура сохранена | Реальные неизменённые prospective gates, без автоматического LIVE |

Существующий heartbeat `19-net-ibit` расширен read-only проверкой фактического
Alpaca entry/controller/broker/native результата. Расписание сохранено:
19Oct **16:35 и23:35 Cyprus**; после вечернего контроля pause. Это локальный
контроль в приложении: сон/выключение Mac может задержать отчёт, но серверный
entry timer от Mac не зависит. При задержке фиксируется фактическое время,
а не вымышленная своевременная проверка. LIQ heartbeat/collector/epoch не менялись.

Дополнительных действий владельца для уже включённого понедельничного scope
сейчас не требуется. Для новой попытки KITY старый launcher/claim не использовать.
Полные private captures и ключи не коммитились; посторонний allowlist файл
сохранён с SHA365ff7d6…cc2e0e и исключён из commit. Claude получает файловый
status delta; сообщения ему и изменения его KARTA/VOROTA не отправлялись.
