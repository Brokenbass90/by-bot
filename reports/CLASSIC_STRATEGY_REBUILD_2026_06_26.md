# Classic Strategy Rebuild — 2026-06-26

Цель: не архивировать классические стратегии, а восстановить перенос ручной
логики владельца в код и доказать/опровергнуть каждую ногу через проверяемый
контракт: стратегия → бэктест → replay → shadow → canary.

## 1. Текущий live-факт

Серверный `proof_of_life` на 2026-06-26:

- bot alive, `dry_run=False`, `open_trades=0`
- live risk: только `flat_resistance_fade x0.3`
- shadow/risk=0: `att1`, `bounce1`, `breakdown`, `ivb1`, `midterm`, `range`
- off: `asb1_slope_break`, `elder`, `hzbo1`

Вывод: в live сейчас НЕ весь набор классики. Это защитная конфигурация после
серии стопов и OOM/research-инцидентов. Это не запрет на заработок; это защита
счёта до восстановления доказательного контура.

## 2. Карта классики в коде

| Ручная/классическая логика | Текущий файл | Статус |
|---|---|---|
| Отскок от горизонтального сопротивления во флете | `strategies/alt_resistance_fade_v1.py` | live small risk через `flat_resistance_fade` |
| Отскок от поддержки | `strategies/alt_support_bounce_v1.py` | shadow/risk=0 |
| Отскок от наклонной | `strategies/alt_trendline_touch_v1.py` | shadow/risk=0 |
| Флет/диапазон BB | `strategies/alt_range_scalp_v1.py` | shadow/risk=0 |
| Ретест сильного уровня | `strategies/inplay_retest_v3.py` | код есть, но `ENABLE_INPLAY/RETEST=0` |
| Пробой после уровня/зоны | `strategies/inplay_breakout.py`, `strategies/alt_horizontal_break_v1.py` | код есть, HZBO off |
| Импульс/разгон на объёме | `strategies/impulse_volume_breakout_v1.py` | shadow/risk=0 |
| Памп/дамп fade | `strategies/pump_fade_smart_v1.py`, `strategies/spike_fade_v3.py` | не в live |
| Elder | `strategies/elder_triple_screen_v2.py`, `strategies/elder_crypto_v1.py` | off; требует редизайн |
| Ликвидационные заколы | `strategies/liquidation_cascade_entry_v1.py`, `backtest/liquidation_sweep_run.py` | текущая простая модель FAIL |

## 3. Главный разрыв с ручной логикой владельца

Ручной подход из `reports/OWNER_STRATEGY_SPEC_2026_06_25.md`:

1. сначала найти inplay-монету, куда прямо сейчас идут объёмы;
2. на 1H найти сильный горизонтальный или наклонный уровень;
3. на 5m взять коррекцию/ретест;
4. тянуть к следующему сильному уровню, но выйти раньше, если объём гаснет;
5. если цена дошла до уровня и проторговалась — взять пробой на импульсе.

Что есть в коде:

- `inplay_retest_v3` хорошо покрывает: сильный уровень, ретест, tight stop,
  TP перед следующим уровнем, runner.
- `inplay_retest_v3` НЕ покрывает полностью:
  - dynamic volume-inflow отбор монет;
  - выход по затуханию объёма до цели;
  - отдельный setup B “проторговка у уровня → пробой на импульсе” как часть одной
    канонической стратегии.
- `scripts/dynamic_allowlist.py` отбирает по turnover/ATR/listing age и
  strategy_score, но это НЕ то же самое, что “в монету сейчас идут объёмы”.
- `min_listing_days` в allowlist-профилях обычно `60-120`, поэтому новая listing
  edge-стратегия должна быть отдельным профилем, а не частью обычного allowlist.

## 4. Почему нельзя просто включить всё в live

Причина `shadow/risk=0` — не внешний запрет и не “ломание ради ломания”.
Причина техническая:

- часть стратегий имеет отрицательный live-tail;
- часть старых красивых результатов исчезла после более честного исполнения;
- package runner на 1GB live-VPS оказался слишком тяжёлым даже для
  `IVB1/BTCUSDT --max-symbols 1`;
- были реальные проблемы parity: closed/open candles, execution model,
  runner import path, OOM рядом с live.

Правильное действие: не отключить навсегда, а восстановить канонический тестовый
контур и вернуть стратегию в риск только после прохождения gate.

## 5. Что переписывать первым

### P0 — Owner Inplay Canonical

Создать/достроить одну каноническую ногу поверх `inplay_retest_v3`:

- universe: динамический inplay-volume scorer;
- setup A: retest/correction to strong level;
- setup B: consolidation near level → impulse breakout;
- exit: target before next strong level + early exit when volume decays;
- evidence: per-trade features in CSV: volume_z, inflow_rank, level_score,
  level_type, distance_to_level, consolidation_score, decay_exit_flag.

Это главный мост от ручной торговли владельца к коду.

### P1 — Flat/Range Bounce Canonical

Отдельная нога для флетов:

- universe: “rangeable coins” — умеренный ATR, высокая ликвидность, bounded range,
  несколько касаний границ, без трендового расширения;
- вход: только у верхней/нижней границы, не в середине;
- фильтр: режим флет/наклонный флет допускается;
- выход: середина/противоположная граница, но с сокращением при объёмном отказе.

### P1 — New Listing Playbook

Новая листинг-стратегия должна быть отдельной, потому что обычный allowlist
специально отсекает молодые монеты.

Минимальная логика:

- age bucket: `< 1d`, `1-7d`, `7-30d`;
- не торговать первые X минут хаоса;
- строить VWAP/opening range;
- setup A: reclaim VWAP/opening range после первого сброса;
- setup B: breakout из opening range с volume confirmation;
- setup C: blow-off fade только после exhaustion/rejection и spread/depth gate;
- обязательно: spread/depth/min-notional/funding/halts guard.

### P2 — Pump/Dump и заколы

Текущие простые liquidation/pump fade модели пока не дают edge. Их надо
переписывать как event-playbook:

- событие: pump/dump/liquidation cluster;
- контекст: был ли уровень рядом, была ли проторговка, был ли объёмный exhaustion;
- вход: только после rejection/reclaim, не сразу на “большую свечу”;
- выход: быстрый, с жёстким time stop.

## 6. Как проверять, где поломка

Для каждой стратегии вводится один `strategy_truth_table`:

1. **Unit tests:** искусственные свечи должны генерировать именно тот сигнал, который
   ждёт ручная логика.
2. **Golden chart replay:** 20-50 размеченных вручную кейсов владельца: вход должен
   быть там же или объяснимо пропущен.
3. **Backtest parity:** тот же сигнал в backtest и live adapter на закрытых свечах.
4. **Execution replay:** комиссии, next-open, spread/slippage, runner/TP/SL/time stop.
5. **Monthly/WF:** не меньше нескольких OOS-окон; цель — стабильность, не лучший пик.
6. **Shadow:** реальные live-сигналы с risk=0 и последующей оценкой missed PnL.
7. **Canary:** только после прохождения всего выше.

Если стратегия “не работает”, её нельзя сразу считать мусором. Сначала определить
тип поломки:

- wrong universe;
- wrong levels;
- wrong entry timing;
- wrong exit;
- fees/slippage;
- live/backtest mismatch;
- strategy truly has no edge.

## 7. Tooling

Уже есть:

- `scripts/run_strategy_autoresearch.py` — “тулза Карпатого” / autoresearch grid;
- `backtest/regime_affinity_profiler.py` — bucket/regime/WF анализ;
- `backtest/package_efficiency_run.py` — быстрый package signal replay, но не для
  1GB live-VPS;
- `scripts/dynamic_allowlist.py` и `scripts/build_symbol_router.py` — universe/router.

Что стоит добавить:

- Optuna для constrained multi-objective tuning: не “максимум PF”, а PF/DD/monthly
  stability/trade count constraints;
- vectorbt-like быстрый research слой для массовой проверки идей на локальной или
  отдельной research-машине;
- отдельный event dataset для listing/pump/dump/liquidation/funding.

Что НЕ делать:

- не ставить новый торговый фреймворк вместо live-монолита прямо сейчас;
- не включать все рукава в деньги “чтобы проверить”;
- не искать параметры на одном периоде без WF.

## 8. Ближайшее действие Codex

1. Сделать `inplay_volume_universe`/scorer: volume_z, turnover spike, recent
   relative volume, age/listing bucket, spread proxy.
2. Достроить `inplay_retest_v3` или новый wrapper `owner_inplay_v1`:
   - setup A retest;
   - setup B consolidation breakout;
   - volume-decay exit flag.
3. Собрать golden review packet для владельца/ревьюера: 20 графиков/кейсов, где
   видно, соответствует ли сигнал ручной логике.
4. Только потом запускать WF и решать про shadow/canary.
