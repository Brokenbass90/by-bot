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
