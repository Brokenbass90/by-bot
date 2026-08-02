# Recovery handoff — 2026-08-01

## Короткий итог

Система не стоит на месте, но расширять money-book раньше доказательств нельзя.
Сегодня исправлена конкретная ложь визуального слоя, завершены два FX-кандидата,
и AI получил реальную, но ограниченную research-only автономию.

## Direct live truth на момент проверки

- `bybot.service=active`, heartbeat около 3 секунд.
- Открыта одна позиция Bybit: `DOTUSDT Sell`, entry `0.7632`, qty `51`.
- На бирже стоит stop `0.7722`; runner активен; TP1 `0.752935` (55%),
  TP2 `0.741597` (45%); breakeven/trailing включены, но ещё не вооружены.
- Core bot не перезапускался из-за открытой позиции. Перезапущен только web.
- Alpaca live small account: ABBV и SCHW, broker-stop coverage 2/2.
  Protective-exits-only manager активен. SCHW достиг порога трейлинга; новая
  стоп-цена `102.05976` будет выставлена, когда рынок открыт. Менеджер не умеет
  покупать, ротировать или market-close — это специально отдельный safety layer.

## Что было неверно в скринере

Скринер рисовал линейную регрессию всех close как будто это торговая наклонная.
На скриншотах владельца R² был `0.17` и `0.02`: это слабая геометрия, которую
нельзя выдавать за trendline. Кроме того, компактный snapshot для AI удалял
геометрию, поэтому AI говорил, что наклонок нет, хотя web уже что-то рисовал.

Исправлено:

- horizontal setup больше не получает нерелевантную regression-line;
- regression скрывается при R² ниже `0.35`;
- swing-pivot support/resistance строятся отдельно и имеют собственные blockers;
- AI snapshot теперь получает тот же geometry truth, что и web;
- карточка в AI-чате содержит краткое описание валидных swing-линий.

После rebuild: 40 geometry snapshots, 18 валидных swing-pivot линий. Это всё ещё
advisory geometry, а не сигнал ATT1. ATT1 пока использует свой точный signal path;
скринер не должен молча становиться вторым источником входа.

## AI autonomy

Добавлена команда `start_research_job`, но только по фиксированному allowlist.
LLM не может передать shell-строку, изменить risk, env или ордера. Разрешены:

- scanner geometry refresh;
- operator snapshot refresh;
- crypto blocker report;
- Alpaca adaptive exit audit;
- FX H4 break/retest sealed run.

Расширять автономию дальше можно через новые preregistered job IDs после теста.
Торговая автономия по-прежнему запрещена до acknowledged live consumer.

## FX/CFD terminal receipts

### D1 Carry + Trend

`FAIL_RESEARCH`: base annualized `−0.514%`, stress `−0.976%`, drawdown `11.69%`,
10 красных месяцев из 20. Конкретная версия закрыта, OANDA KYC не нужен.

### H4 Break + Retest

Новый причинный H4 runner ресемплирует завершённые UTC H4-бары из M5, использует
раздельные public OANDA swap long/short, base и stress costs.

- 135 сделок;
- base `−18.04%`, 21/25 красных месяцев;
- stress `−24.26%`, 22/25 красных месяцев;
- 0/4 положительных folds;
- единственная положительная пара — GBPUSD.

Это terminal FAIL именно этой фиксированной реализации. Следующий FX-кандидат —
H4 Momentum, затем H4 regime mean-reversion. Подгонять break/retest после просмотра
результата запрещено; вернуться к семейству можно только с новой причинной идеей.

## Alpaca: что является стратегией, а что защитой

Protective manager — не замена стратегии. Он обслуживает только две уже купленные
fractional позиции маленького live-счёта. Полная adaptive стратегия пока работает
в shadow/paper: формирует picks, веса, stops и rotation, но не получила право
покупать на этом live-счёте.

Последняя честная историческая картина:

- старый общий tight-exit: отрицательный (`2022 −1.61%`, recent `−3.58%`);
- wide same-shape proxy: combined `+12.58%`;
- 22-session calendar hold proxy: combined `+53.91%`, но survivor-only;
- regime+exit stress: `2022 −0.51%`, recent `+53.52%`; ни один arm не прошёл
  обе эпохи положительно.

Вывод: selector перспективнее старого exit engine, но цифру `+53%` нельзя считать
ожидаемой годовой доходностью. Следующая работа — PIT universe, точный monthly
entry/rotation replay и отладка exit policy. Затем shadow, только затем tiny live.

## Crypto / arbitrage

- ATT1 остаётся единственным money-sleeve; текущая позиция защищена.
- XSEC и Funding Positioning остаются risk-zero prospective candidates.
- Frozen funding shadow сейчас отрицателен; dynamic-вариант показал аномально
  большой плюс на малом N и требует outlier/concentration audit.
- Cross-exchange funding standalone после executable lifecycle отрицателен и не
  получает капитал. Полезные части сохраняются: collector, maker/legging state
  machine, funding feature.

Арбитраж не удаляется, но не является главным источником ближайшего дохода.
Приоритет смещён к directional funding positioning, XSEC и tactical crypto book.

## Следующая очередь

1. XSEC N10 receipt и PIT/fill/cost audit.
2. Funding frozen/dynamic N20, outliers, per-symbol concentration и LOSO.
3. BOUNCE1 exact-SHA virtual lifecycle.
4. BREAKDOWN regime V2.
5. H4 Momentum prereg + OOS; затем H4 regime mean-reversion.
6. Alpaca PIT monthly parity replay.
7. AI job catalog расширять только новыми frozen research packages.

Ориентиры при неизменной частоте данных: XSEC N10 — несколько дней; Funding N20 —
около недели; первые решения по BOUNCE1/BREAKDOWN и Alpaca PIT — 1–3 недели.
Это review dates, не обещание включения денег.

## Git и deploy

- Geometry/web commit: `371e692` pushed.
- Web target deploy выполнен без рестарта core bot.
- Новый FX runner, AI research allowlist и этот handoff закоммичены и pushed:
  `d7c31ac`.
- Чужие dirty/untracked архивы, Claude WIP и historical data не удалялись и не
  добавлялись пачкой.

## Checkpoint 1 августа 12:53 UTC — scanner/advisory/FX wave

- Найдена подтверждённая ошибка качества линий: 2 pivot давали формальное
  `R²=1.00`, хотя это не оценка качества. Теперь такие линии diagnostic-only;
  валидная swing-линия требует минимум 3 pivot.
- Карточка получает только релевантную сторону swing-геометрии. SHORT
  resistance fade больше не показывает support, LONG bounce — resistance.
- Создан атомарный `scanner_strategy_advisory_v1`: risk-zero подсказка может
  поднять приоритет native scan, но `may_open_trade=false` и native strategy
  confirmation обязателен.
- Setup chart и live position chart получили zoom/pan/reset.
- Локальный geometry QA: 26 snapshots, 52 line candidates, 17 valid 3+ pivot,
  64 cards, 0 wrong-role cards, 64 risk-zero advisories.
- H4 Momentum terminal FAIL: stress `−29.20%`, 18/25 красных месяцев,
  1/4 folds, 0/5 пар.
- H4 Regime Mean Reversion terminal FAIL: stress `−10.58%`, 16/24 красных
  месяцев, 1/4 folds, 0/5 пар.
- Следующая FX-ветка должна менять источник edge; подготовлен independent brief
  `DEEPSEEK_FX_RESEARCH_BRIEF_2026_08_01.md`.
- Детальный контракт: `SCANNER_ADVISORY_AND_RESEARCH_STACK_2026_08_01.md`.

### Deploy truth 13:07 UTC

- `cd6bf0f` и `9321508` pushed; web/snapshot пакет задеплоен узко.
- Web service действительно перезапущен в `13:03:09 UTC`; core `bybot.service`
  не перезапускался, risk/orders не менялись.
- Server QA: 63 authoritative cards, 0 valid two-pivot lines, 0 wrong-role
  lines, AI operator sees advisory, `trade_authority=none`.
- Direct Bybit after deploy: DOTUSDT Sell 51, entry `0.7632`, exchange stop
  `0.7722`; защита не изменилась.
- Четыре local risk-zero supervisor screen остаются активны: Alpaca adaptive,
  XSEC V3, funding dynamic и funding frozen V4.
- Funding dynamic на N12 выглядит положительно, но все outcomes пока только
  COTI/BANK и стороны противоположны; это concentration warning, не PASS.
- Funding frozen V4: N11, 5 winners, median `−6.29 bps`, mean `−7.45 bps`.
- Alpaca adaptive: 13 unique shadow decisions; LIVE по-прежнему SAFE_HOLD.
- Полный receipt:
  `releases/SCANNER_ADVISORY_INTERACTIVE_CHART_DEPLOY_RECEIPT_2026_08_01.json`.

## Checkpoint 2 августа — live runner, ATT1 geometry, research truth

- Последние DOT/LTC lifecycle проверены по broker fills. DOT `−0.51013418`,
  LTC partial TP + final stop `−0.18590756`; вместе `−0.69604174 USDT`.
  Статистика сохраняет один lifecycle на сигнал и не должна считать partial TP
  отдельной стратегической победой.
- ATT1 не использует незавершённую часовую свечу. Он касается/rejects линию на
  закрытом H1 и входит по close. Текущий `ATT1_MAX_ENTRY_DIST_ATR=2.0` разрешает
  визуально поздний вход; preregistered single-variable OOS ablation записан в
  `configs/research/att1_entry_distance_ablation_prereg_20260802.json`.
- Signal chart хранит точную проекцию линии, но ещё не хранит pivot anchors.
  Полный аудит: `ATT1_TRADE_AND_LEVEL_QUALITY_AUDIT_2026_08_02.md`.
- Исправление runner qty-step из `69ac253` задеплоено узко после трёх direct-flat
  подтверждений. Server `14 passed`, py_compile PASS, service active, Bybit flat,
  `trade_on=1`, `dry_run=0`, `ws_guard=0`. Receipt:
  `releases/RUNNER_QTY_STEP_TARGETED_DEPLOY_RECEIPT_69AC253_2026_08_02.json`.
- Frozen Funding V4: N15, mean `−1.67 bps`, no capital; до N20 осталось 5
  закрытий. Dynamic Funding: N16, mean `+243.53 bps`, но результат всё ещё
  заблокирован концентрацией старых COTI/BANK outcomes. XSEC: 8 решений,
  последний previous-phase markout `−2.84%`; promotion рано.
- Alpaca adaptive shadow свежий и выбирает SNOW/PANW/DDOG/BAC без ордеров.
  Live остаётся ABBV/SCHW с broker-stop 2/2. Protective manager для SCHW
  рассчитал ratchet до `102.05976`, но рынок был закрыт; фактический broker stop
  пока старый и прибыль ещё не зафиксирована.
- В monthly Alpaca report исправлено zero-padding portfolio history, которое
  могло показывать ложные `+48466%` в начале месяца. Локальный suite: 26 passed;
  reporting-only patch задеплоен без рестарта core. Receipt:
  `releases/ALPACA_MONTHLY_REPORT_ZERO_PADDING_DEPLOY_RECEIPT_2026_08_02.json`.
- Remote branch всё ещё отстаёт от local HEAD на 3 коммита. Live targeted patch
  выполнен, но Git remote не следует объявлять синхронизированным до отдельного
  разрешённого push.
