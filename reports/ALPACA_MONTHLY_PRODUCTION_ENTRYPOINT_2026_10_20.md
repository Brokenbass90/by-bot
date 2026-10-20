# Alpaca Monthly — production entrypoint, 20 October 2026

**ENTRYPOINT_COMPONENT_PASS — LOCAL + VPS ORDERS_OFF**. Продолжение принятого pending-fee компонента
`230106b`; frozen Monthly, исходный календарь и финансовые лимиты не изменены.
Новый код не выбран действующими службами и не даёт финансового разрешения.

## DONE

- Существующий CLI связан с `MonthlyManager.tick`, native custody, единственным
  owned book, restricted transport и автоматическим источником расходов. Нет
  второго manager, selector, ledger или повторной реализации стратегии.
- Default/source остаётся ORDERS_OFF. Новый явный `--dispatch` требует отдельного
  standing GO, полной source closure и SHA операционной конфигурации. Старые
  Dynamic/KITY/exact grants непригодны. Profile загружается после custody;
  исходный profile directory, LIVE host и account lock обязательны.
- Source service и manager имеют разные pinned specs; templates не установлены
  и не включены. Источник57+SPY, фактический frozen ranking и monthly timing.
- После уже выполненной отправки ошибка записи receipt больше не сообщает
  «0 заявок»: значение UNKNOWN/null, источник — существующий dispatch journal.
  Неутверждённый GO не получает доступ к notification config.

## TESTED

**29 local PASS / 545.54s и те же29 VPS PASS / 375.76s**;52source files,
13test files/helpers,39source imports,0checkout fallback,5E2E receipts.
Network запрещён в harness и дополнительно VPS `unshare --net`; реальных
broker requests/writes в репетициях0. Новый source material:
`8a48663fbd195491705fa2aa127fb4b1962e7cddb9aa84cd5ff3fd9ef0e5659b`.
Кандидат `candidate-8a48663fbd195491` staged UNSELECTED. Независимый GET сверил
52source/13test hashes и пять receipts;93nonsecret static pins без изменений,
проверенные financial/observer units кандидата не выбирают.

[Local acceptance](evidence/monthly_production_20261020/local-acceptance.json),
[VPS acceptance](evidence/monthly_production_20261020/server-acceptance.json),
[five CLI/lifecycle receipts](evidence/monthly_production_20261020/server-rehearsal-receipts.json),
[GET preservation](evidence/monthly_production_20261020/ops-preservation.json),
[reproduction](evidence/monthly_production_20261020/README.md).

Полный новый сценарий вызывает настоящий CLI/argparse/main и default source
loader; инъекция только memory transport и fixture clock. Frozen58 selection →
вход/потерянный ответ → native stop/потерянный ответ → restart → следующая месячная
rotation → bounded pending fee admission → replacement → native protection →
повторный restart без дублей → daily close → поздние фактические fixture fees →
finality. Это искусственный календарь и время, не рыночное forward/SLO/доходность.
Другие сквозные сценарии проверяют полный выход, сверку и освобождение капитала.

Независимый review: один компонентный astra/high, фактическая модель/effort
проверены по runtime; прерывание квотой и продолжение тем же reviewer записаны.
Важная ошибка ложного нуля воспроизведена и исправлена; отдельная root-находка
notification authority также исправлена.15 targeted +13 boundary PASS перекрывают
основную приёмку; их нельзя суммировать. Полный E2E/server выполнял root;
reviewer их повторно не запускал. [Review](evidence/monthly_production_20261020/review.md).

## BLOCKERS

Для принятого entrypoint-компонента незакрытых Critical/Important замечаний нет.
**Общий LIVE/автономный Monthly ещё не принят:** transfer legacy ownership,
entry-only retirement guard и standing packet остаются инженерной работой;
их можно закончить до30Oct. Это не календарное ожидание.

## REMAINING / NEXT

1. **NET handoff и rollback перед LIVE.** Проверить прекращение legacy writer и
   его расписания, exact identity/flat/orders/costs. На следующем изменении
   guard должен входить в final validator нового входа; его отказ не останавливает
   owned maintenance/recovery. Свежий read-only preflight сохранён приватно;
   передача управления не выполнялась. Общий account lock и запрет
   foreign exposure не доказывают, что старый timer не запустится позже. Пока OPEN.
   При owned exposure/неясной отправке/неокончательных расходах нельзя отключать
   owned manager ради rollback; disabled-pointer rollback уже проверен.
2. Конкретный standing packet: реальный бюджет, резерв и его достаточность,
   loss trigger/срок/отзыв, account/config/source SHA и личный GO. Ничего не выдано;
   `.03` — только fixture, не новый денежный резерв.
3. 30Oct actual completed source/selection и2Nov14:30–14:35UTC fresh account,
   market, native custody и handoff facts. Их нельзя получить заранее. CASH/
   NO_SEND допустимы; новая покупка не обещана и дата не переносится автоматически.

Сегодняшний scheduled NET read-only контроль выполнен своевременно; raw evidence
оставлен приватным. Он не является проверкой будущего Monthly handoff или
текущим непрерывным брокерским снимком. Нет новых broker writes/NET/SHOP/HALT/unit
изменений от этой инженерной работы.

После закрытия handoff/standing — непосредственно PUMP4 V1 по опубликованным
`b138735`/`7b0a961`; KITY остаётся SPENT, safety/data/research, без нового micro.
