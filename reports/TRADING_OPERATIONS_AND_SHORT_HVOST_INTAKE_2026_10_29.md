# PUMP4 / Monthly / SHORT_HVOST — фактический контроль 29 октября 2026

**PUMP4 LIVE_ARMED_HEALTHY, первая сделка отсутствует. Monthly operational PASS,
торговое окно ещё впереди. SHORT_HVOST NOT_LIVE_READY, черновик разобран без реализации.**
Снимки: PUMP4 2026-10-29T09:14:16+02:00; Alpaca 2026-10-29T09:18:20+02:00.

## PUMP4: текущий LIVE и автоматические записи

- Отдельный authenticated GET health: LIVE_FLAT_WAITING_SIGNAL, PID3198429,
  0 рестартов, scopefec235e3/configfa0b3b2e, исходный account lock818853.
- Последние16 immutable H1 receipts (28Oct16UTC–29Oct07UTC):137 census,
  135 доступных, все135<=60s каждый час. Это проверка квитанций, не новый
  независимый replay2160 сигналов. DATA PID3152955,0 рестартов.
- Три последние financial receipts: OWNER_TINY_LIVE / NO_NEW_SIGNAL. Нет admission,
  tickets, send barriers, attempts, flows и loss/revoke latch. Это ожидание сигнала,
  а не выявленный sizing/admission отказ. GO не повторялся.
- Entry/native stop/40-60/time exit ещё не проверены реальной сделкой. Пока позиции
  нет, `actual_protection_proven:false` ожидаемо и не означает незащищённую позицию.
- Автоматический журнал уже существует: `supervisor/receipts`, flow `execution.jsonl`
  и `observations.jsonl`, account `risk.jsonl`. Они фиксируют заявки/ответы, actual
  fills/fees/funding и предварительный net. Новый дублирующий журнал не создавался.
  Code review `pump4_account_owner_v1._record_risk` показывает `final_costs_proven:false`;
  lifecycle flat-costs verdict имеет `CALLER_DECLARED_NOT_BROKER_FINALITY`. Не объявлять
  flat или предварительный net окончательной прибылью; первая сделка требует отдельной
  source-backed сверки fees/funding completeness. Автоматическая broker finality НЕ доказана.
- Ранее согласованные50/30/20/risk-scenario1/maxoneentry и expiry1Nov19:26UTC не менялись.
  Shared cross margin сохраняется, новые стратегии/режимы в этот owner не добавлялись.

## Alpaca Monthly: готовность к ближайшему календарному gate

Шесть свежих broker GET через существующий transport с `writes_enabled=False`:
account ACTIVE, cash/equity/buying_power496.31 USD, accrued/pending fees0 в обоих
снимках, positions0/openorders0, broker clock доступен. Это текущее наблюдение,
а не окончательная гарантия будущих расходов. Credentials/account identifier не опубликованы.
Source/spec/scope pins проверены; scopeaf7a1159, unit9d94467d и исходный lock813893.
Последний реальный dispatcher: OUTSIDE_MONTHLY_WINDOW, issues[], source
ORDERS_OFF_OPERATIONAL_PASS; Monthly timer и DATA export timer активны.

На calendar из immutable28Oct snapshot выполнена отдельная **offline диагностика**:
30Oct close+20m => monthly_selection_due=true, entry2Nov14:30UTC /16:30Кипр.
Два изолированных CASH fixture случая (gate=false и пустой selection при gate=true)
дают new_symbols=[], без брокерских вызовов. Первый локальный harness был отклонён
из-за symlink temp path; использован `/private/tmp`, production код не менялся.
Это не будущий source/selection/market PASS. Бюджет400/280/40 и loss admission8
подтверждены прежним неизменным scope, cash сейчас покрывает резерв. Реальный30Oct
закрытый снимок/selection и2Novfresh account/native acceptance остаются будущими gates.

## SHORT_HVOST: шесть оставшихся вопросов перед реализацией

Проверен опубликованный research ref `e1e173efb773b6b27640bb867f0c348ade854c23`. Черновик28Oct прямо говорит n27/30,
НЕ ПЕРЕДАЁТСЯ до полного вердикта/GO. Текущий запрос владельца разрешает этот
ограниченный инженерный review, но не финансовую активацию и не изменение prereg.

1. **Режим счёта.** Draftisolated несовместим с текущим PUMP4 account binding
   REGULAR_MARGIN. Bybit меняет mode через account-level API; это не безопасный
   локальный флаг новой стратегии. [Официальный margin API](https://bybit-exchange.github.io/docs/v5/account/set-margin-mode).
2. **Владение.** PUMP4 требует отсутствия чужих позиций; запрета только той же монеты
   недостаточно. Второй runner для short+BTC создаст foreign exposure. Нужен отдельный
   проверенный способ account isolation либо явная будущая интеграция общего owner;
   никакой новый framework, второй writer или переключение LIVE сейчас не создавались.
3. **Стоп/ликвидация.** Формула draft1.80×1.05=1.89, то есть89% убытка short notional
   до расходов, а не84%. Историческое отсутствие срабатываний не доказывает защиту при
   гэпе. Approxliq+95…97% не является текущим exchange расчётом для каждого символа;
   нужны MMR/risk tier/fees/funding/trigger source и реальные acceptance receipts.
   [Bybit native stop API](https://bybit-exchange.github.io/docs/v5/position/trading-stop).
4. **Две ноги и капитал.** Three short50 + matching BTC150 = gross300.
   Margin~200 в вариантеB предполагает short1x, но BTC3x. Это не единый1x и не предел
   совокупного убытка. Новые leverage/budgets/max3 здесь не утверждались.
5. **Экономика.** Свежий Claude `ISTORIYA_2025_ITOG_2026_10_29.md` сообщает
   приблизительную reconstructV1:190 событий, mean−40bps; V2:55,−62bps. Выжившие
   монеты/open-hour entry/нет maker execution ограничивают переносимость. Это не
   точный replay текущего forward и не его formalFAIL; но оснований заранее ставить
   SHORT_HVOST следующим денежным приоритетом нет. Судья/исходы Codex не запускались.
6. **Execution acceptance.** Остались event parity, частично исполненная пара,
   потерянный ответ/stop rejection/restart, lot+hedge mismatch, fees/funding обеих ног,
   BTC aggregation/ownership, correlated loss budgets. Сначала опубликованный полный
   frozen verdict, затем узкий существующий executor intake и точный owner packet.

Claude также опубликовал положительную historical2025 проверку PUMP4 V1 и
неподтверждение фильтра>=6%. Числа research SOURCE_REPORTED, не повторный Codex
экономический расчёт. PUMP4 V1 и её thresholds не изменялись.

## Следующие действия без расширения работы

Действующая PUMP4: существующий health/alerts и первый полный factual lifecycle.
Monthly:30Octactualsource/selection→2Novconditionalentry/CASH, без повторногоarm.
Независимая инженерная очередь остаётся Polymarket→KITY, по опубликованным gates;
SHORT_HVOST остаётся подготовленным research intake, не новый financial priority.
Brain/Factory: причины пропуска/реальные расходы/сводный риск в тени; будущие
улучшения — один фиксированный кандидат и отдельная проверка, без замены LIVE V1.
Ускорение оценивается по принятым денежным циклам и net после фактических расходов,
а не по количеству новых стратегий или тестов. TINY капитал проверяет исполнение;
он не даёт основания обещать значительный доход.

[Evidence manifest](evidence/trading_ops_short_intake_20261029/manifest.json).
Новых orders/GO/units/risk/margin/strategy/research-code изменений0. Код не менялся;
большие ранее принятые test suites не повторялись. Изолированная CASH проверка2/2PASS.
