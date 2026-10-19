# IBIT19Oct: первая DATA_ONLY запись и закрытие одноразового контроля

**Получена и доставлена одна новая серверная DATA_ONLY запись.**
Massive остаётся **PENDING_SVERKA**, экономический и10-session verdict не получены.
[Receipt](evidence/ibit_first_forward_20261020/receipt.json).

## Время — без переноса окна

Контроль был назначен19Oct23:35Asia/Nicosia /20:35UTC. Heartbeat поступил с
`current_time_iso=2026-10-19T23:35:15.538Z`, то есть уже20Oct02:35 по Кипру.
Фактическое серверное чтение —20Oct02:37:23.112Asia/Nicosia; первый local decision
файл —02:39:08.127. **Окно проверки пропущено**, результат не объявляется
своевременным. Причина задержки scheduler/Mac в этом контроле не установлена.

Сам сервер создал запись вовремя по своему контракту:19Oct20:16:06.128572UTC /
23:16:06.128572Asia/Nicosia. Эти source timestamps при поздней доставке сохранены.

## IBIT / BTC — факты и QA

| Поле | Значение |
|---|---|
| Session |2026-10-19, обычное закрытие20:00UTC |
| IBIT SIP close |46.30 |
| Raw provider daily timestamp |2026-10-19T04:00:00Z, сохранён отдельно от effective close |
| Первое получение SIP |20:16:03.530802UTC, lag963.530802s |
| Freshness |FRESH, внутри30min |
| Binance spot / Bybit linear BTC reference |81880.82 /81842.10, frozen19:00–20:00UTC interval |
| Cross-source discrepancy |0.04728824%, ниже0.2% |
| Сохранённый z |−1.4744970667140285 |
| Сигнальное событие |false, знак0, event_ts null |
| Massive QA |PENDING_SVERKA; независимой сверки нет |
| Execution |NO_SEND /orders_enabled=false |

Ровно один завершённый decision и один QA record. Их row/QA hashes, source hashes,
все четыре network body/metadata/request identities, receive/decision/session
timestamps и шесть deployed source pins независимо проверены. RuleSHA
`48d57d4c…7c48906`; rowSHA`abeebfb7…d4d99a5`; qaSHA`1f6e3e67…4094385`.
Формулу/сигнал заново не запускали; z/event взяты из исходного immutable record.

История82 строки = **81 historical warmup +1 новая запись**, не82 prospective
решения. SeedSHA`bbdc5ece…9ab2694` и его исходные hashes/timestamps проверены;
historical prospective credit0. Полностью сверенных Massive сессий0;10-session
gate OPEN. `data_eligible=true` не является допуском к торговле или полным QA PASS.

## Доставка и сохранность

Destination:
`/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/ibit_adapter_v1`.

Decision и QA сохранены отдельными файлами с identity session+rowSHA/qaSHA;
дополнительно исходные raw responses/capture bodies/metadata, historical seed и
commit-last receipt. **19 новых файлов**, повторный импорт —**0 новых файлов**,
все bytes/hash/inode/mtime и первый receipt неизменны. Consumer/Claude producer
ingestion не проверялся и не подразумевается одной файловой доставкой.

Production Adapter/Collector не создавались, `_read`, `decisions`, `qa_records`
не вызывались. Journals прочитаны обычным O_RDONLY; проверен только завершённый
newline prefix. В наблюдавшихся обоих журналах partial tail0bytes; код не обрезает
и не восстанавливает хвост. Source files/marker/locks/seed/timestamps на сервере
не менялись. Нового source fetch/outcome/judge/strategy execution не было.

## Финансовый readback — локальное хранение

NET и отменённый SHOP проверены отдельно. Текущие позиции, цены входа, PnL,
stop/order IDs и состояние финансовых units исключены из публичного отчёта.
Полная квитанция и отчёт сохранены локально в
`.private/ibit_first_cycle_20261020/full-control-receipt-private.json` и
`full-operational-report-private.md`. Никаких финансовых изменений этот контроль
не выполнял. Старые даты проверок не подменялись текущими.

## Закрытие heartbeat и следующие gates

`19-net-ibit` переведён в **PAUSED**, подтверждено чтением настроек. Название/prompt,
исходные даты/rrule/target сохранены; переносов/новых запусков не создавалось.
Это пауза локального одноразового контроля: серверный IBIT source timer остаётся
active/enabled. LIQ и Monthly58 automations не менялись.

IBIT next: фактическая Massive QA при разрешённом источнике и новые causal sessions,
без выдуманного PASS. Финансовые followups продолжаются по существующим owner scopes. Money P0 Monthly admission/runner не изменён. KITY
SPENT/ORDERS_OFF, новой денежной попытки нет; research code/KARTA/VOROTA/ten_ETF/
ishody не менялись, сообщений Claude не отправляли.
