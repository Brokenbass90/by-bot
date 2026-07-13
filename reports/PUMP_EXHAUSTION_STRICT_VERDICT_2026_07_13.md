# Pump exhaustion strict verdict — 2026-07-13

## Решение

`pump_exhaustion_unwind_short_v1` получил итог **NO_PROMOTION**. В money-live, tiny canary и risk-zero shadow его не включать: frozen gate не пройден по общему числу сделок и числу сделок в нетронутом holdout. Близость к порогу не является основанием менять порог после просмотра результата.

## Достоверность данных и исполнения

- Immutable M5 snapshots: `13/13` прошли frozen gate, всего `2,695,442` строк; source hashes, runner hash и девять runtime dependencies закреплены до outcome. У BTC/ETH нет внутренних gaps, но отсутствуют по 119 последних M5 bars общего окна; при результате `39/40` это дополнительная причина не называть sample полностью исчерпанным.
- Сигнальный funnel: `1,038` event IDs -> `39` plans -> `39` закрытых candidate trades.
- Duplicate event/plan IDs: `0`; invalid/censored candidates: `0`; capacity rejections: `0`; side identity: только `short`.
- Execution: completed M5 signal -> exact next M5 open; adverse gaps; stop-first; TP1 50% at 1R, TP2 50% at 2R; max hold 96 bars; base и stress costs.
- Portfolio: не более четырёх одновременных позиций, chronological 4-fold, 7-day embargo, final 120-day holdout, LOSO, breadth и concentration.
- Drawdown gate использует большее из exit-realized DD и консервативной simultaneous-overlap M5-MAE оценки. Tick-level MTM по OHLC доказать нельзя.

## Результаты

| Метрика | Base | Stress |
|---|---:|---:|
| Trades | 39 | 39 |
| Win rate | 56.41% | 51.28% |
| Profit factor | 1.410 | 1.234 |
| Net R | +4.768R | +2.922R |
| Frozen-sizing return за 720d | +2.143% | +1.228% |
| Conservative max DD | 2.660% | 3.015% |

Stress folds: `3/4` positive, но распределение истончается: `N=15/12/4/2`; первый fold отрицательный, PF `0.614`. Final 120-day holdout: `N=6`, PF `6.300`, `+1.027R`, 4W/2L. Это позитивный pulse, но слишком малая выборка для вывода.

Frequency funnel: `1,038` expansion events -> `607` exhaustion confirmations -> `166` bearish CHoCH -> `39` failed-reclaim plans. Частота — около `19.8` trades/year, одна сделка на `18.5` дня по всему портфелю; максимальный межсделочный простой около `113.9` дня. Этот sleeve не может сам обеспечить несколько сделок ежедневно.

Breadth прошёл: все `13` symbols торговались, `8` положительны. Frozen concentration metric равен `30.84%`: это доля крупнейшего положительного symbol net среди суммы положительных symbol nets. Но более жёсткая интерпретация выявляет хрупкость: ONDO дал `2.730R`, то есть `93.4%` итогового stress net `2.922R`; LOSO без ONDO оставляет PF `1.018` и return `-0.127%`. Самые слабые stress symbols: SOL, AVAX, SUI, 1000PEPE и TAO; самые сильные по net R: ONDO, BNB, ADA и WIF. Исключать проигравшие symbols или менять concentration definition после просмотра нельзя.

## Годовые и месячные цифры

Stress calendar-period returns под frozen sizing:

- 2024 partial (15 Jul–Dec): `-1.491%`, 15 trades;
- 2025: `+1.835%`, 17 trades;
- 2026 partial (Jan–5 Jul): `+0.909%`, 7 trades.

Base: `-1.137%`, `+2.198%`, `+1.096%` соответственно. Это не CAGR и не прогноз годовой прибыли: первый и последний годы неполные, общий sample всего 39 сделок.

Чисто механический CAGR всей 720d frozen curve — примерно `1.08%` base и `0.62%` stress. Он относится к симуляции `$100 equity`, `0.5%` risk и `$30` notional cap; это не ожидаемая live-доходность и не доказательство масштабируемости.

В окне 25 calendar months: 16 active, 9 без сделок; 7 красных active months из 16. Поэтому sleeve не решает задачу ежедневной частоты и может быть только редким компонентом будущей корзины.

## Какие gates не пройдены

- `min_trades`: `39 < 40`;
- `holdout_min_trades`: `6 < 10`.

Остальные frozen gates формально прошли, включая stress PF, 3/4 folds, holdout PF, breadth, LOSO calculation, frozen concentration, drawdown, side purity и execution integrity. При этом gate требовал вычислить LOSO, но не требовал положительности каждого LOSO, а fold gate не требовал minimum N на каждом fold; зависимость от ONDO и folds `N=4/2` — дополнительные robustness-причины не продвигать sleeve. Итог остаётся `NO_PROMOTION`, а не «почти PASS».

## Следующий честный шаг

1. Не ослаблять текущие параметры/gates и не удалять проигравшие symbols.
2. Следующий независимый crypto sleeve — физически отдельный `event_expansion_retest_long_v1` с persisted event IDs и тем же causal execution protocol.
3. Для short pump допускается только заранее зарегистрированный external-cohort replication: point-in-time правило листинга/ликвидности/coverage, полностью новые PnL-непросмотренные symbols, те же параметры/exits/costs/gates. Нельзя выбирать symbols по этому PnL. В новом gate заранее добавить minimum 8 trades на fold и worst-LOSO stress PF >=1 с положительной доходностью; это усиление, не rescue текущего результата.
4. Horizontal range rejection строить отдельными long-only/short-only sleeves на общем frozen Level Snapshot; Elder использовать только как ablation/filter.

Полный неизменяемый результат: `reports/research/pump_exhaustion_unwind_short_v1_20260713_strict_gate`.
