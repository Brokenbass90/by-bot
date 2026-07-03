# CODEX QUEUE 2026-07-03 (Claude, новый чат)

Приоритет сверху вниз. Одно изменение за раз, всё в ledger.

## 1. Гейты — статус и терминология (СРОЧНО)
- Диры `crypto_structure_break_cd_gate_20260703` и `fx_native_gate_20260703` пустые с 09:33-09:34.
  Подтверди: бегут или умерли? Если умерли — перезапусти с run_checkpoint.
- Также пустые (умерли?): `xau_structure_break_long_20260703`, `structure_break_crypto_short_20260703`,
  `structure_break_crypto_cooldown_overnight_20260702`.
- ВАЖНО (аудит Claude): оба сегодняшних раннера — СКРИНИНГ, не гейт:
  * `run_structure_break_diagnostic.py` = in-sample свип (cooldown-грид/per-symbol/preflight есть, wf_folds/oos_selector НЕТ);
  * `run_fx_native_harness.py` = 4 грубых хроно-фолда без purge/embargo.
  => Их PASS = билет на СТРОГИЙ путь (wf_folds + oos_selector 40/8/robustness>0 + OOS-symbol набор,
  как ARF2), НЕ на shadow/canary. В отчётах называть их screening, не gate.

## 2. По результатам скрининга (когда добегут)
- Позитивные комбо -> строгий wf_folds+oos_selector прогон + независимый OOS-symbol набор
  (тот же список, что ловил ARF2: BTC/SOL/LINK/ADA/AVAX/DOT/SUI/LTC/ATOM/BNB/BCH/XLM/1000PEPE/HYPE/TAO,
  минус те, что были в скрининге).
- Short-кандидаты: обязателен per-period разрез (bull-ноги!) — bear-only эдж без regime_hmm-гейта не пускаем.

## 3. ATT1 r001 live
- Прислать статус канарейки: журнал сделок / breaker state / есть ли сигналы (локальный trades.db устарел, ноябрь 2025).
- Проверить долю входов через minqty-fallback (diag `att1_*fallback*`): при risk 0.10 fallback растягивает
  эффективный риск до ~1.8x на мелких сделках. Если fallback > ~30% входов — сообщить, это исказит
  live-vs-backtest parity и статистику для решения о разгоне риска.
- Expiry 2026-07-20 — в календарь: продление только через ручной ревью.

## 4. Закрыто, не тратить компьют
- XAU round_level_sweep: NO-GO обе стороны (37 сделок, все 18 long-комбо минус, short PF 0.26-0.56).
- FX BOS/CHoCH: вся cooldown-сетка минус. FX-надежда — только trend_pullback/session в бегущем скрининге.

## 5. Следующее после гейтов (Ф2 частота)
- range/пила блок на динамическом range_scanner (ASB2/ACB1/ARF2-split) — Claude подготовит спек
  прогона после разбора скринингов. Новые модули НЕ строим (правило: wiring > стройка).

## Статус Claude
- Тестовая сетка верифицирована: 726 passed, 0 красных (3 «падения» = отсутствие websockets в песочнице).
- Live-путь ATT1 отаудирован: shadow/breaker/expiry/sizing корректны, fail-safe при ошибке breaker'а.

## ДОПОЛНЕНИЕ (после fast-fail разбора, Claude)
1. P0 ГОТОВ К WIRING: bot/candle_coverage.py (9 тестов) — вставить в начало КАЖДОГО скрининг/гейт-скрипта
   (crypto: market_closure_gap_bars=None; FX M5: 500; FX H1: 40) + в forensics. Юниверс go=False -> прогон
   не стартует, сначала backfill. Backfill-скрипт по failed-символам (APE/APT/.../RENDER = 0 файлов) — за тобой.
2. fx_harness.cost_feasibility() — вызывать ПЕРЕД каждым FX-прогоном; cost_infeasible -> не гнать, чинить
   таймфрейм/данные. EURUSD M5 вердикт аннулирован (fee_r 1.78R), детали в ledger.
3. EURUSD/AUDUSD M5: 14.6-14.8% flat-баров — почистить/перекачать источник. XAUUSD H1: cov 93.4% —
   backfill, потом ре-скрининг XAU round_sweep/BOS (NO-GO пока в силе).
4. Raw structure_break: согласен, мёртв. Следующая итерация только как КОМПОЗИТ (structure_break +
   retest_quality/regime + cooldown) и только ПОСЛЕ range-блока — не соло-сырьё.
5. Порядок: coverage backfill -> range/bounce repair (dynamic scanner) -> строгий OOS. Параллельно P1 wiring
   ATT1 по спеку ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md.
