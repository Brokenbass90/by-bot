# Recovery execution update — 2026-07-26

## Короткий итог

Система не «заморожена»: одновременно работают ATT1 live-canary и четыре
risk-zero процесса — XSEC, cross-exchange funding, Alpaca adaptive shadow и
event-universe collection. Ответ AI-оператора о том, что единственный новый
кандидат — event expansion retest, неполон: он видит live-сервер, но не видит
несинхронизированные локальные research-процессы.

## Ближайшие денежные кандидаты

| Приоритет | Контур | Текущее доказательство | Следующее решение |
|---|---|---|---|
| 1 | ATT1 champion | clean live `N=10`, net `+0.2902 USDT`, PF `1.123`, risk `x0.10` | пересмотр после `N=30`, без скачка на весь депозит |
| 2 | XSEC V4 | backtest `+49.1%`, DD `6.8%`, Sharpe `2.73`; PIT/survivorship haircut обязателен | 10–15 daily decisions: 5–10 августа; 20–30: конец августа |
| 3 | ATT1 A3/3R short challenger | proxy `N=194`, `+0.180R/trade`, PF `1.263` при 4 bps; один fold нестабилен | exact-universe shadow/champion comparison |
| 4 | Cross-exchange funding | механизм существует, но первые lifecycle-циклы выявили churn-дефект | минимум 20 чистых post-fix cycles, ориентир 3–7 дней |
| 5 | Event expansion retest long | data collection only до конца публичного clock | отдельный scorer после закрытия data seal |

Для планирования XSEC следует использовать не `49.1%` как обещание, а
haircut-диапазон порядка `8–18% годовых` до PIT и реального исполнения.
Диапазон станет прогнозом только после PIT-universe, 20–30 shadow decisions и
измеренных costs/fills.

## Cross-exchange funding: найденный дефект и ремонт

Первые 16 закрытых shadow-циклов дали 1 выигрыш и 15 проигрышей; среднее
изменение одного цикла `-0.1414%`. Сумма по перекрывающимся циклам не является
доходностью портфеля.

Причина оказалась не только в economics: validator возвращает top-N кандидатов,
а shadow считал отсутствие пары в top-N явным провалом. Это принудительно
закрывало позиции примерно через 2 часа и повторно входило в те же пары,
оплачивая новый круг комиссий.

Исправление:

- отсутствие в top-N теперь считается `missing`, а не `fail`;
- закрытие требует трёх последовательных **явных** validator failures;
- после закрытия действует шестичасовой re-entry cooldown;
- lifecycle сохраняет отдельные missing/fail streaks и точное время закрытия.

Это не превращает арбитраж автоматически в прибыльный. Оно удаляет
искусственный churn и позволяет честно измерить funding, basis, legging и fees.

## FX/CFD: новый воспроизводимый прогон

Пройден frozen source-hash preflight и заново запущены три H1 causal family,
каждая отдельно long/short, со stress spread, folds, holdout и LOSO.

Результат diagnostic:

| Семейство | Side | N | stress netR | PF |
|---|---:|---:|---:|---:|
| impulse breakout/retest | long | 26 | -8.606 | 0.609 |
| impulse breakout/retest | short | 16 | -9.056 | 0.382 |
| sweep reclaim bounce | long | 101 | -18.559 | 0.747 |
| sweep reclaim bounce | short | 101 | -23.557 | 0.690 |
| regime range reversion | long | 28 | -16.865 | 0.394 |
| regime range reversion | short | 41 | -15.177 | 0.587 |

Это честный `NO_PROMOTION`, но не остановка FX. Точный вывод: эти три V2
реализации не лечатся простым снижением spread. Следующим слоем запущен широкий
9-family scan на шести инструментах: trend retest v1/v2, range bounce,
breakout continuation, Asia range reversion, failure reclaim, grid reversion,
liquidity sweep bounce и trend pullback rebound, с двойным spread/swap stress.

Data blockers:

- snapshot старше 120 часов;
- большие разрывы в части M5/H1 рядов;
- нет исторического PIT news calendar;
- нет OANDA/MT5 account-specific costs и native bid/ask parity;
- нет portfolio MTM drawdown/correlation layer.

## Alpaca Safe Hold и trailing

Прямой broker-read показывает:

- equity около `$483.96`, cash около `$391.27`;
- позиции ABBV и SCHW;
- обе позиции полностью покрыты брокерскими `stop`-ордерами с точным
  fractional qty;
- это `type=stop`, `time_in_force=day`, а не broker-native trailing.

В коде есть software trailing с activation `+3.5%` и retrace `3.5%`, а также
native trailing, но текущие позиции fractional и native-ветка их сознательно
пропускает. Поэтому правильная формулировка: **защитные стопы работают;
broker-native trailing сейчас не активен; software trailing существует, но
зависит от периодического runner cycle**.

Менять существующие live-ордера без отдельного owner approval нельзя. Для
следующей активной Alpaca-модели нужен проверяемый exit-manager heartbeat и
тест восстановления trailing state после рестарта.

## Уровни и графики сделок

Новый путь уже сохраняет геометрию сигнала в момент входа: горизонтальный
уровень либо sloped-line anchor/slope, entry, SL и TP. Telegram/web renderer
рисует именно эту геометрию поверх свечей и использует старый reason-parser
только как fallback для исторических сделок.

Это качественная архитектура для анализа, потому что уровень больше не
пересчитывается задним числом по будущим свечам. Но «полностью готово» можно
сказать после первой новой реальной ATT1-сделки, открытой уже после deploy:
нужно визуально проверить timestamp anchor, масштаб, подписи и соответствие
receipt. Старые сделки, где точная геометрия никогда не сохранялась, нельзя
восстановить идеально — только приблизительно из `reason`.

## Масштабирование ATT1 и общий депозит

`N=30` — не команда поставить `$500–1000` в одну позицию. Если clean cohort
сохранит положительный net, PF не ниже `1.20`, приемлемую просадку и отсутствие
execution anomalies, следующий шаг — малое увеличение `x0.10 -> x0.15/0.20`.
Следующая ступень рассматривается после новой независимой выборки.

Несколько стратегий могут использовать один Bybit account, но не получают весь
депозит каждая. Sleeve — это лимит риска и полномочий, а allocator должен
ограничивать:

- суммарный открытый риск;
- число одновременных позиций;
- коррелированные позиции на одинаковой стороне;
- дневной/недельный loss budget;
- риск каждой стратегии отдельно.

Одобрение ATT1 не переносится автоматически на XSEC или другой алгоритм.

## Реалистичный месяц

Цель на ближайшие 30 дней — не обещание прожиточного дохода, а:

1. сохранить ATT1 без разрыва clean cohort;
2. принять первое решение по его `N=30`, если статистика успеет накопиться;
3. довести XSEC до 20–30 risk-zero решений и решить tiny-canary/no-go;
4. получить 20+ post-fix funding lifecycle cycles;
5. завершить широкий FX scan и сформировать V4 preregistration только из
   причинно отличающейся логики, а не подгонки V2;
6. материализовать бесплатный Alpaca PIT input.

При капитале около `$1500` даже `20% годовых` — примерно `$25` в средний месяц.
Положительный PnL в течение месяца возможен, но стабильный жизненный доход
нельзя честно обещать. Правильное ускорение — параллельно довести до tiny
money два независимых контура, а не резко увеличить риск одного.
