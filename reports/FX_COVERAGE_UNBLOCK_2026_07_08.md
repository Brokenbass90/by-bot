# FX разблокирован: coverage-гейт врал на выходных (2026-07-08)

## Что было
Неделю FX не давал вердиктов: coverage EURUSD/GBPUSD/USDJPY ~0.70 -> gate FAIL -> rows:0.
Считалось, что данные грязные и нужен бэкфилл.

## Что на самом деле (проверено на реальных данных)
Данные `data_cache/forex_1h/*_M5.csv` — на самом деле ЧАСОВЫЕ (шаг 3600с), 17266 баров, 2.8 года.
Coverage 0.704 = артефакт: гейт считал ожидаемые бары как 24/7, а форекс закрыт на выходных.
Closure-aware покрытие:
- EURUSD 0.9957, GBPUSD 0.9958, USDJPY 0.9961 (не-выходные дыры ~0.3%). ЧИСТО.
- XAUUSD 0.916, не-выходные дыры 7.0% -> золото реально дырявое, нужен бэкфилл.

## Точная причина в прогоне
Харнесс `run_fx_native_harness.py` УМЕЕТ closure (`_default_market_closure_gap_bars`), но:
1. дефолт `--interval-min 5`, а данные H1 -> надо `--interval-min 60`;
2. дефолт `--min-coverage 0.995` и `--max-gap-bars 12` слишком строги: праздничные разрывы
   13-20 H1 баров (дольше выходных, короче порога закрытия 36) валят гейт.

## РАБОЧАЯ КОМАНДА (даёт цифры)
```
PYTHONPATH=. python3 scripts/run_fx_native_harness.py \
  --data-dir data_cache/forex_1h --pairs EURUSD,GBPUSD,USDJPY \
  --setups trend_pullback,session_breakout_retest,session_range_fade,round_level_sweep \
  --interval-min 60 --min-coverage 0.98 --max-gap-bars 24
```
Проверено: coverage EURUSD ok=True 0.9993, cost_ok True (feeR 0.216<0.25). Пайплайн считает.

## Первый честный вердикт (за неделю первые FX-цифры)
- EURUSD session_range_fade rr2.0 sl1.0 hold120: 154 сделки, netR -64.08, PF 0.55, WR 31.8%,
  0/4 фолда, preflight FAIL (low_quality_pf). Флет-фейд на EUR — ПРОИГРЫШ (ожидаемо).

## ДЕЙСТВИЕ Codex (сегодня, без лимита времени)
1. Прогнать команду выше на ПОЛНОЙ истории, все 4 сетапа × grid (tp_rr, sl_atr, hold),
   EUR/GBP/JPY. Получить вердикты по trend_pullback и session_breakout_retest (прежние канарейки).
   PASS экрана -> строгий wf_folds+oos (как крипта).
2. XAU: НЕ гонять до бэкфилла (7% реальных дыр) — единственный реально грязный.
3. Пофиксить дефолты харнесса/раннера: для H1-данных interval-min=60, min-coverage 0.98,
   max-gap-bars 24 (праздники), либо поднять closure-порог. Чтобы 0.70-артефакт не повторялся.
```
```
