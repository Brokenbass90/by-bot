# Recovery execution status

Дата: 2026-07-26

## Что уже исправлено и запущено

- Коммит `d5c3688` отправлен в `origin/codex/dynamic-symbol-filters`.
- DeepSeek-оператор переведён с снятого `deepseek-chat` на
  `deepseek-v4-flash`. Прямой API smoke на VPS вернул `OK`.
- На live применён точечный патч без `git pull`. Перед рестартом получены три
  прямых подтверждения Bybit flat. После рестарта сервис active, heartbeat
  свежий, `trade_on=true`, `dry_run=false`, открытых позиций 0.
- ATT1 продолжает быть единственным денежным crypto-sleeve на `x0.10`.
  Alpaca Safe Hold и торговая логика ATT1 не менялись.
- Удалены выдуманные уровни 25%/75% диапазона графика. Теперь сигнал при
  отправке ордера создаёт immutable `position_geometry_v1`: фактический
  уровень, наклон, SL/TP, параметры качества, order id и исходный reason.
  Этот snapshot попадает в event ledger, график и post-trade review.
- Полный локальный regression: `1532 passed`.

## Что показали текущие risk-zero процессы

### XSEC

Процесс `xsec_v3_shadow_20260726` работает без ключей и без ордеров. Первый
daily decision: 62 пригодных инструмента, 24 виртуальных изменения позиций,
gross turnover около $333.33, оценка входных затрат $0.252.

V4 остаётся главным кандидатом на следующий crypto-sleeve, но требует:

1. PIT-снимков universe и delisting lifecycle;
2. независимого OOS;
3. нескольких staggered forward-фаз;
4. измеренной bid/ask execution parity;
5. beta/factor neutrality и ограничения концентрации.

Плановый диапазон после haircut: 8–18% годовых на 1x, не обещание.
Ранний shadow-review возможен после 10–15 daily decisions; tiny canary — только
после прохождения capital gate.

### Cross-exchange funding

Shadow больше не пустой. После persistence gate открыты две виртуальные пары:

- ERAUSDT: Binance long / Bybit short;
- GWEIUSDT: Binance long / Bybit short.

Первый markout с учётом входных затрат отрицательный, около -0.10% и -0.21%
общего капитала пары. Это нормальный старт lifecycle: funding должен окупить
четыре исполнения, basis и legging, иначе маршрут будет отклонён.

Первый tiny canary возможен после минимум 20 закрытых paper-пар с положительным
net distribution, нулём stale/legging incidents и воспроизведёнными fee tiers.
Стартовый размер: ориентировочно $25–50 на ногу, если минимумы бирж позволяют.

### Alpaca

$1000 — не магическая граница устойчивости. Она лишь позволит купить целую
акцию части universe. В текущем shadow минимальный капитал для native
broker-side trailing stop различается по цене кандидата; для всех четырёх
текущих picks нужно больше $1000. Fractional execution может работать с меньшим
капиталом, но требует отдельной синтетической защиты и exact parity.

Практичный порядок данных:

1. Massive Stocks Basic, $0, чтобы проверить коннектор и PIT/reference поля;
2. только если coverage достаточен — один месяц Starter, $29, с пятью годами;
3. Developer, $79, не покупать до доказанного требования более длинной истории.

Safe Hold ABBV/SCHW не является новой активной моделью. Новая модель ещё
заблокирована отсутствием PIT/delisting/corporate-action parity и завершённого
forward window, а не размером счёта.

### ATT1

Dynamic selector существует, но live override сознательно держит восемь
проверенных монет. Расширение universe увеличило число сделок, но ухудшило
экономику: base PF около 1.08, stress PF около 0.91. Поэтому механическое
добавление монет сейчас повысит частоту ценой потери edge.

A3/3R short-only остаётся challenger. Proxy на восьми монетах дал 194 сделки,
около +0.18R на сделку и PF 1.263 при 4 bps; при 11 bps среднее осталось
положительным, но один fold провалился. Следующий шаг — exact production replay
и forward labels, а не немедленная замена champion.

Разница порогов:

- 20 live closes — ранний review: можно остановить деградацию, но нельзя
  увеличить риск;
- 30 live closes — первый минимальный scale gate при net PnL > 0, PF >= 1.20,
  DD <= 3R и нуле execution incidents.

Прямая проверка VPS на 2026-07-26:

- весь исторический ATT1: 17 закрытий, -0.9925 USDT, PF 0.733;
- канонический clean cohort после `start_ts=1783162792`: 10 закрытий,
  +0.2902 USDT, 5/5 win/loss, PF 1.123.

Именно clean cohort используется для продвижения; старые семь сделок не
«удаляются», а остаются отрицательным историческим контекстом. До раннего
review нужно ещё 10 clean closes, до первого scale gate — ещё 20. При прежней
скорости это ориентировочно середина августа и начало сентября, но календарь
ничего не разрешает автоматически: текущий PF 1.123 ниже scale-gate 1.20.

Частоту нельзя безопасно «накрутить». Её можно повысить только через новый
независимый sleeve или расширение universe, которое отдельно прошло stress/OOS.

### FX/CFD

Текущий кандидат запускать даже в demo-shadow рано. H4 при мягких затратах
показывал +8.5…+10.8R, но targeted stress сделал все варианты отрицательными.
Нужен broker-specific cost digital twin: spread по сессиям, commission, swap
long/short, contract size, minimum lot, stop distance и limit-fill model.

OANDA practice — бесплатный демо-счёт с виртуальными средствами. Если регион
даёт v20 API, нужны account id и personal access token; реальных денег не
нужно. Если v20 недоступен, достаточно MT5 Specifications выбранного брокера.

## Что требуется от владельца

Сейчас можно ничего не покупать и не передавать торговые ключи.

1. Проверить `/ai ты тут?`: провайдерный путь уже восстановлен.
2. Для Alpaca зарегистрировать бесплатный Massive Basic, но API key не
   присылать в чат — установить через локальный/server setup.
3. Для FX открыть бесплатный OANDA practice только если форма доступна для
   страны проживания; иначе прислать экспорт/скриншоты MT5 Specifications.
4. Для арбитража пока не создавать API. Первый практический набор после paper
   gate: Bybit + Bitget. MEXC добавить следующим адаптером, BingX оставить
   третьим кандидатом. Затем нужны два верифицированных аккаунта, trade-only
   keys без withdrawal/IP whitelist и ориентировочно $100–200 буфера на каждой
   бирже.

## Следующие контрольные точки

- 2026-07-27: первый суточный срез funding shadow и проверка Telegram `/ai`.
- 2026-07-29: завершение текущего event-universe окна и повторный разбор
  funding lifecycle.
- После 10–15 XSEC daily decisions: interim forward-review.
- После 20 закрытых arb paper-пар: решение, можно ли готовить tiny canary.

AI в арбитраже допускается как anomaly/routing analyst. Экономический validator,
лимиты риска, четыре fill и право отправить ордер остаются детерминированными:
LLM не должен обходить capital gate.
