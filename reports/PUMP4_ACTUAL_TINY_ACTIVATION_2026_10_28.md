# PUMP4: фактическая активация технического TINY — 28 октября 2026

**LIVE_ARMED_HEALTHY / LIVE_FLAT_WAITING_SIGNAL.** Владелец явно утвердил точный
пакет; агент выполнил новый activation helper **один раз**. Независимая сверка
завершена. Последняя GET-сверка: 2026-10-28T20:20:05+00:00
(2026-10-28T22:20:05+02:00 по Кипру). **Первая сделка ещё не совершена.**

## Фактический переход и evidence

|Этап|Результат|
|---|---|
|Точный OWNER GO|`GO на этот пакет PUMP4` после раскрытия сумм, одного входа и cross margin|
|Пакет|`66a7be9cbb134524ee43785e46c79920b05a06a1429a9eeb47e69c25eb8e6340`|
|Финансовый arm|2026-10-28T18:09:38+00:00; DATA epoch не менялся|
|Активация|2026-10-28T18:09:56+00:00, `LIVE_ARMED_HEALTHY`|
|Отдельная независимая GET-сверка|2026-10-28T18:10:11+00:00, `LIVE_FLAT_WAITING_SIGNAL`|
|Файловый/unit postcheck|2026-10-28T18:10:40+00:00, PASS|
|Поздняя GET-сверка|2026-10-28T20:20:05+00:00, тот же PID, 0 рестартов, flat|
|Финансовый процесс|PID 3198429, active/running|
|Исходный единственный account lock|inode818853, подтверждён LIVE health|
|GO-файл|0600, exact scope/config binding|
|Monthly unit / DATA unit+binding|Не изменились; Monthly timer active/waiting|
|Ticket / send-barrier / attempt / flow при postcheck|0 /0 /0 /0, admitted lifecycle отсутствует|

Scope: `fec235e3dea12245d96859a6786d811551f9341d9a860ee4fac88dea4bfcf794`. Config: `fa0b3b2ec893f5167d79e71ef7fcf5a1d3788075105a2732663a8dafec53014a`.
Core: bfbd987d6137f819; исходный DATA7d8ae05d. Исходные журналы/epochs сохранены.
Полная активация не повторялась. Старые личные Monthly/KITY команды не вызывались.

[Публичные квитанции и manifest](evidence/pump4_actual_tiny_activation_20261028/manifest.json):
[активация](evidence/pump4_actual_tiny_activation_20261028/activation-receipt.json),
[независимый GET](evidence/pump4_actual_tiny_activation_20261028/independent-readback.json),
[postcheck](evidence/pump4_actual_tiny_activation_20261028/postcheck.json),
[поздний GET](evidence/pump4_actual_tiny_activation_20261028/latest-readback.json),
[OWNER approval](evidence/pump4_actual_tiny_activation_20261028/owner-approval.json).
Credentials, private packet/before/config и raw account payloads не публикуются.

## Границы действующего разрешения

- 50 USDT программного выделения, gross<=30, резерв20; max1 вход /1 позиция /
  один полный lifecycle во всём пилоте. Cost-inclusive сценарий риска1 USDT;
  day2/week3/drawdown6 admission budgets. Это не гарантированные пределы потерь.
- Новые входы до **1 ноября 2026, 19:26:32.774 UTC**. По истечении ENTRY окна
  сопровождение уже открытой owned позиции продолжается. Продления/повторного GO нет.
- REGULAR_MARGIN/cross margin:50 USDT не изолированы от прочих средств счёта;
  margin mode и leverage не переключались. Экономический вердикт INCONCLUSIVE.
- Только новый допустимый H1-сигнал после arm, 60s deadline/5s source freshness/
  drift10bps; старые сигналы не переименовываются. Возможен пилот без сделки.
- `orders_allowed:false` в health означает отсутствие торговых прав **у наблюдателя**.
  Реальный financial runner выбран в OWNER_TINY_LIVE; это не возврат в ORDERS_OFF.
- `broker_writes:null` в активационной квитанции — неизвестное общее число действий
  runner; не подменяется нулём. Независимый GET доказывает flat на момент снимка;
  postcheck отдельно доказывает отсутствие финансовых tickets/flows в том снимке.
  `broker_writes:0` postcheck относится только к этому read-only скрипту.

## Следующий gate и очередь

Оставить работающую PUMP4 V1 неизменной и использовать существующий health/alert
канал. При новом сигнале нужны фактические receipts entry→full native stop→40/60
или time/stop exit→flat→fees/funding finality. До них нет execution/profit PASS.
Не запускать activation повторно; при неопределённости только GET/reconciliation.
Не останавливать custody вслепую и не включать второй owner.

Monthlyv6 остаётся в прежнем разрешении:30Oct закрытые данные и selection,
2Nov14:30UTC/16:30Кипр условное торговое окно; возможен CASH. Не повторять её arm.
После закрытия этого operational gate следующая самостоятельная инженерная очередь
по каноническому roadmap — Polymarket, затем KITY, без новых денег. SHORT_HVOST может
стать кандидатом после опубликованного полного prereg/evidence:27/30 из сообщения
пользователя не является ни экономическим PASS, ни разрешением. Локальный ref
research/fabrika-v1 при проверке отсутствовал; этот результат не подтверждался.
Brain/Factory/классические стратегии остаются исследовательской линией; V2 не меняет V1.

[Предшествующий reviewed packet и приёмка](PUMP4_EXACT_TINY_ACTIVATION_2026_10_28.md)
сохраняются как история до GO (450/450 core,19/19 activation по ранее опубликованным
квитанциям). В этом цикле код не менялся и эти наборы тестов повторно не запускались.
