> **Superseded by actual owner-approved activation:** [LIVE readbacks and receipts](PUMP4_ACTUAL_TINY_ACTIVATION_2026_10_28.md). The preparation state below is historical; do not activate again.

# PUMP4: точный пакет включения технического TINY — 28 октября

**READY_FOR_EXACT_OWNER_GO. Сейчас ORDERS_OFF; активация и реальные ордера не выполнялись.**
Пакет: `66a7be9cbb134524ee43785e46c79920b05a06a1429a9eeb47e69c25eb8e6340`.
Каталог VPS: `/opt/bybot-research/pump4-server-orders-off-20261023/tiny-activation-20261028-v1`.

## Что именно будет разрешено

|Параметр|Значение|
|---|---:|
|Программное выделение|50 USDT|
|Расчётная максимальная экспозиция|30 USDT|
|Резерв внутри выделения|20 USDT|
|Стоп + модель комиссий/проскальзывания/funding при admission|до1 USDT|
|Позиции / входы на весь пилот|1 /1|
|Day / week / drawdown admission budgets|2 /3 /6 USDT|
|Допустимый reference drift / slippage scenario|10 /10 bps|
|Deadline / свежесть источника|60s /5s|
|Новые входы до|1Nov2026 19:26:32.774 UTC|

Новый финансовый epoch создаётся в момент подтверждённого включения. Старые H1
и сигналы до включения не становятся новыми; DATA epochs/журналы не меняются.
После первого допуска повторный вход этим пакетом невозможен. После окончания
окна новых входов сопровождение уже открытого owned lifecycle продолжается.
Покупка не принудительная: только новый сигнал, прошедший исходные causal/one-way/
qty40/60/native/cash/cost/funding проверки. Возможно отсутствие сделки.

**1 USDT — расчётный сценарий, не гарантированный предел потерь.** Сохраняется
`REGULAR_MARGIN`, то есть [cross margin по Bybit](https://bybit-exchange.github.io/docs/v5/account/set-margin-mode).
50 USDT не отделяются биржей от остальных средств счёта. Стоп/Market fill могут
проскользнуть; при гэпе, изменении funding/caps или сбое native stop потери могут
превысить расчёт и программное выделение. Margin mode и leverage не переключаются.
При неподтверждённой защите исполнитель/наблюдатель требуют сверки и тревоги;
автоматический повтор заявки или произвольное компенсирующее закрытие не добавлены.
Это отдельное решение о техническом пилоте; экономика остаётся INCONCLUSIVE.

## Фактическая приёмка

- Новый financial core bfbd987d6137f819:450local/те же450VPS PASS, network denied,
  no fallback,0failures/skips и0real broker requests/writes. Не450реальных сделок.
- Новый LIVE health: exact GO/unit/lease, authenticated GET, native stop на весь
  остаток, принадлежность fills/orders; не создаёт owner/lease/lifecycle.
- Реальный GET показал scoped lossless archive4010bytes вместо старых3199888bytes.
  Первичная диагностическая assertion пропустила существующее полеbroker_writes;
  архив сохранён и независимо проверен по исходному имени-digest, без перезаписи.
- Activation/rollback:19local/те же19VPS/19independent PASS. Закрыты0600/umask и
  python-O findings. Current helper SHA b64ab4a177de3dc88e28e972966849547022e2a4bab57a503de8a90cd5d2dd16.
- Exact staged packet реально прошёл source/unit/lock guards, systemd-analyze
  неподключённого unit и LIVE-health GET rehearsal. Счёт flat/orders0; live root,
  GO и финансовые units не создавались/не менялись.
- Предыдущая фактическая DATA приёмка:7H1,945frozen parity,135available/137census,
  publication max43.218s, исходные hashes/epochs сохранены.

## Применение после точного решения владельца

Однократный agent-safe helper принимает только exact reviewed packet GO; он не
является прежним персональным KITY/Monthly launcher. Обычный запуск ничего не делает.
Используется текущий счёт, source-bound credentials и исходный lock818853.
Проверка flat выполняется до и после остановки старого OFF owner; затем создаются
новые exact scope/config/GO, меняется только PUMP financial unit и его health shim.
DATA/Monthly/SHOP/NET/KITY units не переключаются. Дальше независимый GET/health.
Текст технического аргумента после явного решения владельца:
`GO PUMP4_TINY_PACKET 66a7be9cbb134524ee43785e46c79920b05a06a1429a9eeb47e69c25eb8e6340`.

При ошибке/неопределённости activation не повторять. Сначала только независимая
сверка unit/config/GO/lease/account. Revoke/rollback сохраняет claims/GO/журналы;
при admitted/reserved/ticket/custody не останавливает менеджер вслепую. Новые ENTRY
revoked; существующая custody остаётся под прежним разрешением. До GO запущены
только tests и GET-rehearsal; точная команда активации агентом не выполнялась.

Реальные first fill/native stop/40-60 exits/restart-under-custody/net costs остаются
результатами будущего технического пилота, а не выводом из этой приёмки.
