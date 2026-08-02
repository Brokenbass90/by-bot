# ATT1: аудит последних сделок и качества уровней — 2026-08-02

## Решение

ATT1 механически исполняет текущий контракт: использует только завершённые
часовые свечи, строит сопротивление по swing-high, требует касание/прокол и
закрытие обратно под линией, затем входит на закрытии часовой свечи. Look-ahead
в этом пути не найден.

Но текущий контракт не является идеальным. `ATT1_MAX_ENTRY_DIST_ATR=2.0`
разрешает вход далеко от спроецированной линии после сильной rejection-свечи.
Последние DOT/LTC визуально показали именно этот компромисс. Слепо ужесточать
live нельзя: нужен preregistered OOS-разрез качества входа.

## Direct broker truth последних lifecycle

### DOTUSDT short

- entry: `51 @ 0.7632`;
- signal trendline projection: `0.7671`, slope `−0.726%/day`;
- exchange stop: `0.7722`;
- close: `0.7724`;
- closed PnL: `−0.51013418 USDT`.

### LTCUSDT short

- entry: `1.2 @ 44.12`;
- signal trendline projection: `44.4158`, slope `−1.874%/day`;
- TP1 execution: `0.6 @ 43.81`, closed PnL `+0.15820420 USDT`;
- final stop execution: `0.6 @ 44.65`, closed PnL `−0.34411176 USDT`;
- lifecycle total: `−0.18590756 USDT`.

Сумма этих двух завершённых lifecycle: `−0.69604174 USDT` до отдельного
учёта funding cashflow. Статистика не сломана: частичный TP и финальный stop
должны агрегироваться в один lifecycle, а не считаться двумя стратегическими
сделками.

## Что график показывает правильно

- жёлтая линия — точная проекция `tl=` и `slope=` из причины сигнала;
- голубая линия — фактическая средняя цена брокерского входа;
- exit и PnL берутся из broker fills;
- поэтому расстояние между trendline и entry не является ошибкой рендера.

## Что график пока не умеет доказать

Стратегия сохраняет `R²`, число pivot, возраст, `entrydist`, `touchdist`,
`reject`, размер тела и ATR, но не сериализует timestamps/prices самих pivot.
Из-за этого chart знает точную проекцию в момент сигнала, но не может показать
якоря, по которым линия была построена. Ограничение уже маркируется как
`pivot_points_not_serialized_by_strategy`.

Следующая behavior-neutral версия geometry должна сохранить:

1. каждый pivot: timestamp/index/price;
2. R² и число pivot;
3. entry/touch/rejection distance в ATR;
4. freshness и причину invalidation;
5. SHA параметров и source стратегии.

## Preregistered ablation качества входа

Замораживается текущий ATT1 short-only baseline и одинаковый PIT-universe.
Меняется только `ATT1_MAX_ENTRY_DIST_ATR`:

`0.35, 0.50, 0.75, 1.00, 2.00`.

Обязательные разрезы: train/untouched time-OOS, symbol-LOSO, bull/bear/chop,
base/stress costs, trades/PF/DD/red months и markout после касания. OOS не
является objective. Победитель должен быть плато, а не одиночный максимум.
До receipt live остаётся `2.0` и risk `0.10`.

## Как довести Setup Scanner до рабочей аналитической поверхности

Scanner остаётся advisory и не открывает сделки. Следующий пакет качества:

- единый snapshot horizontal zones, 3+ pivot sloped lines и native strategy
  geometry;
- filters: timeframe, LONG/SHORT, стратегия, режим, horizontal/sloped, minimum
  touches, minimum R², maximum distance ATR, minimum RR, liquidity/spread,
  dynamic-universe, live/shadow/blocked;
- карточка обязана показывать source/provenance, freshness и blocker;
- outcome ledger каждой карточки: invalidation/1R/2R и maximum favorable/adverse
  excursion без hindsight;
- score калибруется на prospective outcomes, а не на красоту линии;
- advisory может ускорить native scan, но native стратегия повторно подтверждает
  сигнал тем же decision hash.

## Verdict

`ATT1=ACTIVE_TINY_UNPROVEN`, `visualization=TRUTHFUL_BUT_MISSING_EXACT_PIVOTS`,
`entry_distance=RESEARCH_REQUIRED`, `live_change=NONE`.
