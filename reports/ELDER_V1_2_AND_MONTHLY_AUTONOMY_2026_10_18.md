# Elder V1.2 acceptance / следующий конкретный gate Monthly

18 октября. **Elder f1 engineering blocker CLOSED локально ORDERS_OFF.**
**Monthly standing autonomy NOT_IMPLEMENTED**; это следующий P0, отдельно от уже
завершённого single-scope E2E. Финансового standing GO нет.

## Выполнено: опубликованное уточнение Elder

Origin `research/fabrika-v1` проверен как
`4b1af408f7c75a8a95257633a197f11fce145b1d`. Контракт
`6a618d243112676fed4cc361fc63f309b4d97b58` — его предок. Предыдущий
`PENDING_PUBLICATION` снят. Пинованный текст:
[published-contract.md](evidence/elder_v1_2_20261018/published-contract.md), SHA
`be98b1aa842d293889123334833e109eb87aa272b8fbb5c1b00cf732ad7df091`.

Изменены только существующие adapter/intake:

- Геометрия хеджа сохраняет `target_fraction_1=0.55` и прежний geometry contract SHA.
- Фактическое поле producer сохраняется как `f1_istochnika`; отличие маркируется
  `F1_SOURCE_MISMATCH_INFO`, без подмены геометрии стратегии.
- Некорректный тип/нечисловое значение по-прежнему отвергается. Stop multiplier,
  max leverage, RR, stop fraction, причинные timestamps и остальные gates прежние.
- Новые intake receipts сохраняют это уточнение. Уже записанные receipts не
  переписываются и не получают задним числом разрешения/проспективного credit.

Сохранённая реальная первая XAI-запись с `f1=0.50` проходит adapter acceptance;
та же запись со `stop_x=3` отвергается. Context/risk/instrument в этом тесте явно
fixture: это **не fresh account/source eligibility** и не исторический торговый
сигнал для отправки. [Receipt](evidence/elder_v1_2_20261018/actual_fixture_acceptance.json).

**79 targeted PASS**, включая существующий Brain read-only bridge. RED до fix:
два ожидаемых отказа по f1/классификации intake; прочие negative guards проходили.
Полный repo suite не запускался, независимый financial signoff не заявляется.
[Verification](evidence/elder_v1_2_20261018/verification.json),
[tests](evidence/elder_v1_2_20261018/targeted.xml).

Ничего не развёрнуто/перезапущено на VPS, producer не менялся; старые source,
records, outcomes и окно900 сохранены. **0 broker requests/writes, 0 new authority,
0 prospective credit.** Следующий Elder gate — реальные причинные context/risk/
instrument и исходные prospective/parity/restart условия. Outcome CONTROL с0.55
остаётся исследовательской задачей Claude; Codex judge/PnL не запускал.

## Monthly: принята цель одного ограниченного согласования

Цель владельца: согласовать постоянные ограниченные торговые правила один раз;
далее система сама выполняет предусмотренные месячные циклы и ежедневную защиту.
Не выдавать новую финансовую команду для каждой плановой сделки. Это утверждение
инженерной задачи, **не финансовый GO**.

Сохраняются existing Monthly58 source/frozen selector/calendar/ratchet/cooldown,
один owned book, один manager, исходный account lock, существующие accounting и
notification interfaces. Monthly не ждёт полезности Brain. Factory/Brain research
идёт параллельно на существующей инфраструктуре, без автоматического изменения
денежных правил. Gold/FX/new crypto не получают денежный допуск по одному запросу.

### Точный выявленный блокер

`MonthlyNativeBinding._live_custody` принимает только
`ALPACA_MONTHLY_OWNER_SCOPE_V1`, привязанный к конкретным `selection_id`/`symbol`.
`_admit_new_entry` отвергает другой отбор; `MonthlyManager.opening` ограничивает
LIVE тем же symbol. CLI `run_alpaca_monthly_cycle_v1.py` имеет только source/preview,
не applying daemon. Уже доставленные135 exact E2E tests доказывают компоненты и
изолированный цикл, **не запущенную бессрочную автономную торговлю**.

### Следующая реализация на существующих компонентах

1. Отдельный versioned standing scope, default OFF: account/runtime/lock/source/
   universe/frozen contract pins, ограничения капитала/риска и срок/отзыв. Personal
   согласование привязано к этому scope, не к заранее неизвестной будущей акции.
   Старый exact GO, Dynamic GO и KITY GO не конвертируются автоматически.
2. Разрешённые selections возникают только из sealed причинного Monthly source;
   symbol/вес/объём определяет frozen strategy и текущие account gates. Никакой
   дозакупки после стопа вне месячного календаря или переноса пропущенного окна.
3. Один dispatcher вызывает уже существующие source/opening/maintain/finalize
   методы. Сначала reconcile и защита; неизвестность/истёкшие полномочия/лимит
   блокируют новые покупки. Сопровождение уже открытых owned позиций продолжается.
4. Доказать два последовательных monthly cycles/restart/response loss/capital
   release на одном book и одном standing grant; изменение pins/GO/источника,
   чужая позиция, stale data, CASH, потерянные ответы и незавершённые расходы дают
   явный результат. Покупки/выходы/ошибки получают существующий execution journal
   и notifications, без второго финансового ledger.
5. Подготовить один конкретный owner packet после технического acceptance.
   Текущие487.42/.70/.60/4 — существующие ceiling, не выданный бюджет/standing GO.
   Новые численные полномочия и условия остановки подтверждает владелец отдельно.

Legacy NET не усыновляется и не закрывается новым контроллером. Его действующая
защита19Oct13:30UTC/readback13:35 сохранена; SHOP остаётся отменённым. Перед
первым Monthly входом требуются фактическая finality/свободная custody и безопасная
передача единственному manager. Новая цель не отменяет эти условия.

Реальные будущие30Oct source/selection и2Nov fresh account/market факты ещё нельзя
доказать. **Standing authority implementation не должна ждать этих дат.**
Документ фиксирует следующую инженерную работу; постоянные полномочия и daemon
сегодня не реализованы/не установлены/не активированы. Это не заявление AUTONOMY_PASS.
