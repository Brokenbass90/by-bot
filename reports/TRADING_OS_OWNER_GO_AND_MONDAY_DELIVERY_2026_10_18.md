# Trading OS: owner GO, KITY300 и понедельничная Alpaca

18 октября 2026. Код: `29b1f90`, `3810890`, `01abb769329ba7235b112b50781a016680ef9732`.
Машинный receipt: [JSON](TRADING_OS_OWNER_GO_AND_MONDAY_DELIVERY_2026_10_18.json).

**Подготовлены два отдельных исполняемых пакета. Оба пока не активированы.**
Прямое разрешение владельца на KITY принято; просьба включить Alpaca в понедельник
учтена в отдельном ограниченном scope. Повторное финансовое GO не запрашивается.
Сохранён личный запуск владельцем: Codex не выполнял и не планировал команды
`--owner-execute` / `--owner-arm`. Установка файлов в новые каталоги — не запуск LIVE.

## KITY — готова новая личная one-shot команда

Свежий аутентифицированный GET **2026-10-18T04:49:22.397000+00:00**: gross **230.121200 USDT**
при cap **300**, все десять исходных инструментов, блокировок расчёта нет.
Возраст общего снимка **485 ms** при лимите 2000;
позиции **0**, открытые linear-USDT ордера **0**, права счёта подтверждены.
**80 GET, 0 broker writes**. Расчётные комиссии немедленного полного оборота
при неизменном рынке 0.24210761575 USDT, наблюдаемый 30-минутный funding-reserve 0E-10.
Цены/стоимость датированы; запуск обязан получить собственный свежий снимок.
Изменение gross с 252.90 вчера до 230.12 сегодня — результат свежих цен и тех же lot/minQty,
не смена пропорций. Потолок300 не является заданием потратить300.

Новая V4 связана с точным owner text hash
`f76de24aa713fad07083c89f23c7a2fbf76cfe983113c7d08c3ae89bdf18379d` и уже рассмотренным
packet `ba243eb8df39041c98639931d538ce4e2f70f6a678b3eb98686586a6b92a81fd`.
Старые V1/V2/V3 не принимают300. Старая215 policy остаётся SPENT/NO_SEND и не переиспользуется.

- Новая policy: `d848a1300ae866bd5d6fcfd49b6dbb196cb6183a12aa71dbb4f8bf6ae77f40a1`.
- Manifest: `3fb44bc0563e1e1bfe1791a76d2e8358e432e8de60881db7e050172a272ebaf1`.
- Новый каталог: `/opt/bybot-research/kity-micro-owner-20261015/cap300-20261017-v1`.
- Новый runtime: `/opt/bybot-research/kity-micro-owner-20261015/runtime/batch-ws-20261017-v2`.
- 23 source files / 159 guards. Policy не claimed, selection отсутствует, experiment namespace пуст.
- Срок личного запуска: **18 октября до18:00 UTC /21:00 Cyprus**, без автоматического продления.
- Ограничения: 5LONG/5SHORT, прежние rounding/shortfall20.3%, CTS2s, IOC50bps,
  entry60s, удержание максимум30min, all-in exit trigger15, native SL и полный owned unwind.
  Нет усреднения, повторного входа, расширения cap, автоматического продолжения или research promotion.

**15USDT — триггер выхода, а не доказанный жёсткий предел итогового убытка.**
Shared cross / гэп / задержки / исполнение стопов допускают превышение.
Подробная арифметика и сценарии — [предыдущий рассмотренный risk packet](KITY_CAP300_OWNER_REVIEW_2026_10_17.md).

Личная команда владельца, ровно один раз:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/owner_go_20261017_300/owner-kity300-once.sh
```

`COMMAND_QUEUED` не является execution PASS. Следующий gate: независимый broker readback
всех10 legs, фактической полной native защиты, полного выхода и реальных расходов.
Если новый fresh gate откажет, сохранить NO_SEND и claim; без повторного запуска.
**10/10 по-прежнему не доказано.** Техническому micro не требуется ждать23 октября;
исследовательские условия дальнейшего допуска стратегии не отменены.

## Alpaca — исходный Weekly Dynamic, один ограниченный понедельничный вход

Dynamic не подменён Monthly. Сохранён policy
`fe72557bd7c7437eda328047e81980ee762ec794ac240494ec47d3de4f6f400d`:
capital487.42USD, gross0.70, max4positions, max1newentry/session,
weekly refresh в первую XNYS-сессию ISO-недели, вход в первые5минут,
21-дневный cooldown, без forced rotation и нового четвёртого funding token.
Свежий перескан после каждого стопа — отдельный ORDERS_OFF research candidate;
он не получил экономический PASS и здесь не активируется.

Реальные устранённые ограничения:

1. Добавлен GET-only reconciler реального LIVE fill в существующую slot lineage.
   NET→исходный CRWD budget больше не должен выглядеть как незавершённая первая резервация.
   Применение записи идемпотентно и только после подтверждения broker + journal + native ledger;
   PAPER fill API не используется. До личного arming производственный book не изменён.
2. Новый assembler использует неизменный planner в временной SQLite-копии и допускает
   уже подтверждённую дочернюю позицию. Исходный first-canary adapter остаётся строгим.
3. Новый вариант существующего OpeningDispatcher принимает только точный ранее подтверждённый
   LIVE child; неизвестные/незавершённые резервации блокируются. Сохраняет T−15/T−1, время,
   durable one-attempt boundary и запрет повторного вызова адаптера после uncertainty.
4. Перед вторым входом runtime проверяет каждую занятую позицию по её исходному binding,
   broker entry/exit history и общей native ledger. Для NET требуется полный принятый
   стоп текущей сессии без снижения floor. Чужой ордер/позиция, partial, stale DAY, HALT,
   неподтверждённая финальность или изменение ownership → NO_SEND.
5. Подготовлено сопровождение NET и новой позиции через **один существующий manager unit**,
   прежний lock и прежний5минутный timer. Сначала исходная команда NET, затем exact owned
   maintenance нового lifecycle. Исходные финансовые команды/источники NET сохранены.

Был найден важный source drift: локальный общий native bridge уже отличается от боевого.
В пакет взят **точный действующий** bridge SHA
`758ca619ecb92d1d729b8ef4fb97e10d417a36e2c5ae5d54c4eaed55a8d038f4`,
manager SHA `2d5243ee52d3857c14fd564cea671f8938dd1cdc7623f360293154c8bce5eea1`.
Финансовая защита не заменена новой Monthly-версией. С этой точной версией — **222 tests PASS**.
Действующий Oct16 NET spec отдельно прочитан: зависимостей от SHA выбранного systemd unit нет,
поэтому новая обёртка сохраняет его original source custody.

### Конкретный scope19 октября

Источник59×200 закрытых сессий до16Oct уже работает отдельно;
source ID `aa97a0132440068a1a9f0928bc989dcda8a6b56b66605c63202a1b9134843b94`.
Не запрашиваем новые недели истории. Исходный selector даёт первым SHOP после исключения
held/cooldown AMD/CRWD/META/NET. Draft сформирован с реальным временем получения;
ranking не будет sealed до фактического открытия19Oct.

- Новый вход **SHOP**, только из подтверждённого свободного AMD slot.
- Максимальный notional **113.60999978874 USD**; модельный первоначальный stop risk
  **9.07098231494 USD**. Это прежние caps AMD, не увеличение капитала/риска.
  Фактические qty/limit/stop заново рассчитывает старый planner по свежему ask;
  стоп-риск не является гарантией итогового финансового убытка.
- Окно исходной стратегии: **19Oct13:30–13:35 UTC /16:30–16:35 Cyprus**.
- Новая попытка запланирована в подготовленном timer на **13:31 UTC /16:31 Cyprus**,
  после первой попытки DAY re-arm NET исходным manager в13:30.
- При неполной защите NET, изменившемся портфеле, неактивном/неfractionable SHOP,
  stale quote/clock, новых fee liabilities, изменившихся source pins или HALT — отказ.
- Ни перенос на следующий день, ни второй вход, ни автоматическое расширение суммы не допускаются.
- Календарь SHOP проверен по [официальному анонсу](https://www.shopify.com/news/shopify-q3-2026-financial-advisory):
  отчёт3Nov до открытия; исходный earnings gate для19Oct проходит.
  Свойства limit/stop проверены по [Alpaca orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca).

Фактический VPS preflight **2026-10-18T04:47:23.025000+00:00**:
`NEXT_SESSION_PREFLIGHT_ORDERS_OFF`, реальная NET lineage подтверждена GET,
нет открытых ордеров в закрытом рынке, HALT присутствует, personal arm отсутствует.
Это не понедельничный broker acceptance или DAY protection PASS.

Новый50file kit: `/opt/bybot-research/alpaca-next-entry-20261019-v1`.
Source spec `d33decac3fe3caff72de798510df6ae74734dd923c0f195d863a6219b67de8c7`.
Control spec `b5a9c752baae49853c42068b0b4c49925094d05eb6a6448023063ddc010b6a26`.
Scope `4630ebe2d63659ed98cf549c3adc8bf1d9cf330de7a7e165e5be051896a7bd1e`.
Manifest `d4fd22de33e016c7a338af063a684362214be2fe2935b3f4764829d30b48405e`.
Inspection PASS /0broker requests; `systemd-analyze verify` PASS; исходные97pins неизменны.
Новые финансовые units **не установлены**, HALT не снят, заявки не отправлялись.

Личная команда владельца для однократного arming, **до19Oct13:15 UTC /16:15 Cyprus**:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/owner_go_20261017_300/owner-alpaca-monday-arm.sh
```

Она сама не покупает акции сейчас. Проверяет pins/lock/реальную NET lineage,
записывает только доказанный child в прежний source book, меняет обёртку одного manager,
версионирует GET monitor spec, архивирует только точный прежний HALT, создаёт отдельный
личный arm и включает однодатный timer. Новый HALT всегда блокирует вход.
При ошибке timer отключается, claims не стираются; требуется read-only reconciliation,
а не повторное выполнение команды. Нормальный ответ:
`MONDAY_PERSONALLY_ARMED_PENDING_FRESH_OPENING`.

Будущий exact-intake GO является **машинным производным** личного arming/этого scope.
Он не выдаётся за дословную человеческую команду: actual text hash и derivation receipt
сохраняются отдельно. Внешний неперсональный scope-файл сам по себе не разрешает вход.
Личный запуск Codex не выполняет. Оба новых пакета проверены на пересечение guards:
изменения Alpaca не затрагивают159KITY guards, Alpaca не закрепляет KITY unit.

## Execution board

| Приоритет / направление | Сейчас доказано | Следующий реальный gate |
|---|---|---|
| P0 KITY | cap300 код/реальный GET/пакет/личная команда готовы; attemptunused | личный старт→10/10fills+защита→полныйвыход→fees/readback |
| P0 Dynamic19Oct | source59 + bound next-entry code + actualVPSpreflight + stagedpacket | личныйarming→13:30NETre-arm→13:31freshgates→1guardedentry |
| P0 NET | прежнийmanager/lock/floor277.69 сохранены; weekendDAYexpired | реальный19Oct13:30re-arm полногоостатка, readback16:35local |
| P0 Monthly | отдельныйacceptedparity/source58/schedules сохранены | 30Octselection→2Nov14:30UTC/16:30Cyprus; отдельныйfinancialbinding/owneractivation |
| P1 LIQ | 18Oct27010raw/all25 immutable импортированы; hashes17/18Oct совпали; collector/epochнеизменны | Claude gap/UNKNOWN handling, prospectiveBASE по исходному контракту |
| P1 IBIT | работающий DATA-onlysource/81historicalseed из предыдущегоreceipt | первыйactual19Octforward+QA+journal; MassivePENDING |
| P1 Brain/Reporting/Accounting | один существующий Shadow/journalreceiver; новая LIVEистина остаётсяbroker+journal+nativeledger | воспроизводимый multi-strategycontext→risk→decision→pairedoutcome, без moneyauthority |
| P1 Elder | v1.1 source/rounding contractreconciled,candidateisolated | настоящая prospectiveparity/restart/latency gates; нет автоматическогоLIVE |

LIQ18Oct seal `34db1a86d7c77f14ef84ea9025df0f117b18ff40d5353d2463e8c2539fdfba99`,
epoch `0688909d05884004b991bec76c6e4847`. Повторная проверка17Oct сохранённого seal PASS.
Coverage `UNKNOWN_NO_SEQUENCE_OR_BACKFILL`, source gate false, prospective decisions0.
27010raw не являются27010BASE или сделками. Collector/export не перезапускались;
код/KARTA/VOROTA Claude не изменялся, judge/PnL/новые research outcomes не запускались.

## Проверки и практический путь дальше

- **1293 focused PASS:** выбранный Alpaca financial/source/guard контур и все KITY tests.
- **222 PASS** отдельно с точным native bridge действующего VPS.
- End-to-end controller test: существующая NET + новый SHOP, native защита обеих,
  оригинальный NET maintenance после нового входа, рестарт без повторной покупки.
- Проверены отказ при wrong GO/HALT/потере полного стопа/старом DAY/foreign order/
  изменении source/slot/binding, закрытые временные окна и сохранение originalbook preview.
- Оба local launcher только `bash -n`; **ни один не выполнялся**.
- Полный репозиторий заново не прогонялся; исторические60FAIL полного suite не объявляются исправленными.
- Независимый financial reviewer ранее исчерпал allowance; повтор/подмена не делались.
  Финальный анализ root-only, без независимого financial signoff.
- Foreign `configs/allowlist_change_log.json` сохранён SHA365ff7d6…cc2e0e и исключён из commits.

Ближайшая цель — два измеримых сквозных результата, а не новый архитектурный обзор:
закрытый KITY technical micro с точными расходами и один original Dynamic entry с полной
защитой/повторным maintenance. Затем — фактический stop/exit→settledcash→новый допустимый
slot и отдельная проверка свежего перескана по согласованному research контракту.
Этот пакет не является неограниченной торговой автономией. Повторные сессии, свежий
рескан после каждого стопа, перенос scope и повышение риска автоматически не разрешены.

**Дата устойчивого выхода в плюс пока не доказана.** Исправление проводки и успешный
micro не доказывают net edge. Фиксируем реальные расходы и сопоставимые закрытые циклы;
никакого масштабирования по числу модулей, одному удачному fill или незавершённой прибыли.
OS Lane развивается параллельно и не является предварительным условием первого LIVE.
