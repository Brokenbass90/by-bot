# PUMP4: узкое ускорение чтения журнала — 3 ноября 2026

Предыдущая установленная Warm-оптимизация не обеспечила стабильный допуск:
15:00 UTC — 134/134 вовремя, 58,750 с; 16:00 — 134/134, 56,629 с;
17:00 — 123/134, 66,274 с; 18:00 — 127/134, 63,500 с.
Все четыре часа полные, без разрывов, raw signals=0. Это не пропущенная прибыль.
DATA PID4126455 и финансовый owner3669955/NRestarts0 сохранялись.

## Что исправлено

В полном чтении каждого journal event удалено повторное преобразование уже
строго разобранного JSON. Одни canonical event bytes используются для SHA и
identity. Каждый read по-прежнему проверяет весь prefix, границы, ASCII,
duplicate keys, schema/eventID, последовательность, hash chain и canonical row.
Кэша доверенных хвостов нет. Исходные `_append`, `_locked`, `_event`, fsync и
Python-event validation наследуются без изменения.

Новый bootstrap сначала проверяет overlay/base/original hashes, затем заменяет
только `pump4_closed_bar_intake_v1.LifecycleJournal`. Финансовые журналы,
производитель сигналов, его source paths/pins и правила допуска не изменены.
Он делегирует запуск принятому Warm-bootstrap59f6639e. Исходные файлы не переписаны.

## Проверка и измерение

133 существующих/новых теста с DATA injection PASS локально и на VPS. VPS-тесты
запрещали socket connections. Начальные ошибки тестовой упаковки (namespace path,
недостающие test module/fixture) исправлены только внутри отдельного /tmp;
ни одна из этих попыток не меняла работающий DATA. Финальный переносимый public
fixture закреплён SHA; 38 parser/overlay PASS локально, 33 parser PASS на VPS.
10 точных handoff fixture tests PASS локально/на VPS. Bounded critical review
parser, injection и handoff delta не оставило материальных замечаний.

Сравнение использует ОДИН принятый Warm-reducer и публичный BTC-prefix224rows,
sourceSHA f41c50d88a0cc407dc2a0e55ff1a59b7c64076521ab9881e0c9cb030acdb16a7.
9 чередующихся повторов: Mac22,913→16,172мс (29,42%); VPS133,354→95,958мс
(28,04%). Полные bytes, decision, restart/state совпали. Это benchmark операции,
не результат будущего H1 и не доказательство отсутствия иных задержек.

## Установка: назначена, ещё не подтверждена

Native `pump4-data-strict-handoff-20261103.timer` назначен на 3Nov19:00:30UTC
(21:00:30Кипр). Helper ждёт полный19H, границу+65..80s, проверяет прежний DATA
PID4126455/unit0e227 и отдельный неиспользованный claim. Только затем переключает
DATA. Принятые cleanup/rollback/900s preload и запас до следующей WS-подписки
сохранены. Старые попытки/часы не повторяются. Rollback возвращает принятый Warm,
а не более старый reader. При неопределённом spent attempt самовосстановления нет.

Folder: /opt/bybot-research/pump4-data-throughput-20261103/strict-read-6f65581e0f6615de
Manifest: 746f35af071b7383f387afc9ca9ec1766a185cf74d2a10de1ec0e9145c016ba8
Helper: 5be1055772b51f94562540be6fe57bb4b632974cfbfb74b4a2e686f6dea26e7b
Parser: 6f65581e0f6615de7ee52ae1acca60471bd76e61020aa2c7131f66f1fb639967
New DATA unit: 9c7ff89367ba1a69c419fc5ffc8260f078e998a2886bbc6373148bc06f7bbcbe
Actual new20H proof — после20:02:05UTC/22:02:05Кипр; пока PENDING.

Helper сам сохранит strict-v1-handoff-result/failed и actual-h1-after/unconfirmed.
App heartbeat `pump4-strict-h1` читает только эти факты/проверенные hashes/status;
при ожидании молчит, после фактического результата/сбоя сообщает один раз и
удаляет только себя. Native worker сохраняет результат независимо от сна Mac.
Только actual H1 может подтвердить 134/134 within60 и последнюю публикацию.

Финансовый PID3669955/NRestarts0/lock818853, Monthly125 unitf167c6cc, ключи,
GO/scope2de0b6ec…d0970, 50/30/20, max1entry и deadline8Nov19:26:32.774UTC
не меняются. Polymarket не отключён. Broker requests/orders=0 для этого этапа.
SOURCE_PASS не означает сделку, PnL, экономическое преимущество или TINY-2 GO.

## Фактическое переключение и серия — обновление3Nov19:04UTC

Nativehandoff завершён19:03:53.875UTC/21:03:53.875Кипр. Независимый GET19:04:42UTC
подтвердил DATA4191832/unit9c7ff893,136epochs+136journals/data-lock4294867,
финансовыйowner3669955/NRestarts0/lock818853, прежниеMonthlyunits.
HandoffreceiptSHA6a86a107ecfd3cba7983ad9adcce2a1158b13da45f65dc120060d1d2cf7a840e.
Последний19H ЕЩЁ СТАРОГО Warm:134/134,last57.145s,0rawsignals; он не засчитывается
новому strict-parser. Первыйactual20H остаётся будущим, SOURCE_PASS не заявлен.

По принятому PM дополнению первичная инженерная проверка —6фиксированных часов:
20/21/22/23UTC3Nov и00/01UTC4Nov; после01:02:05UTC(03:02Кипр)полнаясерия доступна.
Первыйfailed/missing/UNKNOWN останавливает эту приёмку и новые слепые journal
оптимизации; следующий шаг — ограниченный профиль всего критического пути.
Это не изменение финансовых gates/GO, сроков входов или стратегии.
GET-only observe-series-readonly.py проверяет pinned overlay/helper, исходный
handoff/nativeactual20H proof, текущиеunit/PID/lock и immutableчасовыеreceipts.
Не запускает helper/стратегию/судей/брокерские API и не исправляет источники.
Существующий heartbeat pump4-strict-h1 расширяется на эту серию: первыйactualH1
и окончательнаясерия/новыйсбой сообщаютсяоднократно, промежуточныеожиданиятихо;
послеитога удаляетсятолькоэтотheartbeat, исходныеслужбы/журналысохраняются.

## Итог фиксированной серии —4 ноября01:07:55UTC

SERIES_SIX_H1_PASS.20/21/22/23UTC3Nov и00/01UTC4Nov: каждый134/134within60,
безdisconnect; последниеpublication offsets41.730/44.372/44.076/39.939/47.648/
45.700s. Максимум47.648s, минимальныйнаблюдавшийсязапас12.352s. Rawsignals0.
ТотжеDATA4191832/unit9c7ff893, финансовыйowner3669955/NRestarts0/lock818853.
Immutableactualreceipt сохранён; appheartbeatpump4-strict-h1 удалён послеитога,
nativeDATA/PUMP/Monthly/Polymarket/таймеры/журналы сохранены. Первичнаяинженерная
приёмказакрыта; это не гарантия будущейбезотказности/сделка/экономическийPASS.
Новые слепые локальныеоптимизации не продолжать. При новомопоздании—ограниченный
профильполного criticalpath. Текущийфинансовыйscope/deadline не изменялся.
