# Бриф Codex перед отпуском (5 дней) — 2026-07-08

## A. ЧТО УЖЕ СДЕЛАНО (проверено; готово к деплою)
1. **Runner heartbeat fix** (`smart_pump_reversal_bot.py`): TP-лесенка/трейлинг/breakeven/time-stop
   ведутся для ВСЕХ открытых позиций из pulse, не зависят от ленты/detect. Проверено на живой функции.
   Флаг `RUNNER_HEARTBEAT_ENABLE=1` (дефолт). Бэкап `*.bak_runnerfix_*`.
2. **Safety exchange TP** (`_maybe_arm_exchange_safety_tp`): биржевой TP на дальнюю цель как сеть.
   Флаг `RUNNER_EXCHANGE_TP_ENABLE=0` (по умолчанию ВЫКЛ — реальные ордера). Бэкап `*.bak_safetytp_*`.
3. **Portfolio health monitor по ВСЕМ рукавам** (новый `bot/portfolio_health.py` + pulse): здоровье
   каждого рукава из trades.db -> алерт при деградации -> (по флагу) авто-срез риска. Раньше был только
   att1. Флаги `PORTFOLIO_HEALTH_ENABLE=1` (alert-only), `PORTFOLIO_HEALTH_AUTOCUT=0`. Бэкап `*.bak_health_*`.
   Юнит-тест зелёный; пофикшен falsy-zero баг.

## B. ЧТО РАЗОБРАНО (вердикты — в ledger, не переисследовать)
4. **FX РАЗБЛОКИРОВАН**: coverage-гейт считал выходные как дыры (0.70). Реально EUR/GBP/JPY H1
   closure-cov 0.98-0.996 — ЧИСТО. XAU 0.916 (7% реальных дыр) — единственный грязный.
   Первый вердикт: range_fade EUR = проигрыш (PF 0.55). Детали: `reports/FX_COVERAGE_UNBLOCK_2026_07_08.md`.
5. **Каскады = data-starved**: даже window_v1-фикс дал 0 сделок -> биндят OI/funding (нет REST-потока
   на 21-дневном альт-окне) + редкие альт-ликвидации. Долгая ставка. `reports/CASCADE_ZERO_TRADES_DIAGNOSIS`.
6. **level_memory** — единственный живой крипто-пульс (exploration PF1.30). OOS-прогон запущен.

## C. ЧТО ДЕЛАТЬ ПО ВОЗВРАЩЕНИЮ (деплой; ~1 час)
1. Задеплоить `smart_pump_reversal_bot.py` + `bot/portfolio_health.py`, рестарт в flat-окно (с qty-sync).
   Флаги: `RUNNER_HEARTBEAT_ENABLE=1`, `PORTFOLIO_HEALTH_ENABLE=1`, `RUNNER_EXCHANGE_TP_ENABLE=0`,
   `PORTFOLIO_HEALTH_AUTOCUT=0`. Верификация: `[pulse]`, события `runner_*`, `runtime/portfolio_health.json`,
   TG health-алерты.
2. Крон `build_ai_full_context.py` (5 мин) + вшить `full_context.json` в промпт борт-ИИ.
3. Полный FX-грид на сервере (без лимита):
   `PYTHONPATH=. python3 scripts/run_fx_native_harness.py --data-dir data_cache/forex_1h
    --pairs EURUSD,GBPUSD,USDJPY --setups trend_pullback,session_breakout_retest,session_range_fade,round_level_sweep
    --interval-min 60 --min-coverage 0.98 --max-gap-bars 24`
   Вердикты -> ledger. PASS экрана -> строгий wf_folds+oos.
4. Пофиксить дефолты FX-раннера: H1 -> interval-min 60, min-coverage 0.98, max-gap-bars 24 (чтобы 0.70 не повторялся).

## D. ЧТО ДОЛЖНО КРУТИТЬСЯ ПАССИВНО ВСЕ 5 ДНЕЙ (не выключать)
- Коллектор ликвидаций (копим к 60-90д — каскады оживут только на объёме).
- att1-канарейка (набор сделок для статзначимости; heartbeat/health её теперь защищают).
- Alpaca $500-канарейка (проходит цикл; красные дни = норма).
- НЕ повышать live-риск, НЕ включать новые live-рукава, НЕ включать autocut/safety-TP без OK владельца.

## E. НЕ ДЕЛАТЬ (мёртвое — не жечь компьют)
- Broad MRB/«тупая сетка» (FAIL x2). XAU-гейты до бэкфилла. Raw structure_break соло. Каскады до накопления данных.

## F. Я (Cowork) делаю эти 5 дней на кэш-данных
FX-вердикты чанками, разбор level_memory OOS (anti-overfit: концентрация, per-period), att1 exit A/B,
обновление ledger. Тяжёлый полный FX-грид — на сервере за тобой по возвращении.

## G. GUARDRAIL: дампы/шорты в «медвежке»
НЕ крутить шорт-риск руками (дискреционный тайминг = сжигатель счёта). Факт по att1 (кэш, 20 сделок):
LONG PF 1.62 vs SHORT PF 1.12 — эдж в ЛОНГЕ, валидированного bear/short-рукава НЕТ.
Ловить дампы можно только так: отдельный breakdown/short-рукав -> per-period bear-валидация ->
regime_hmm-гейт (сам усиливается в даунтренде, глохнет на развороте) -> health/breaker -> shadow.
Bear-only эдж без regime-гейта НЕ пускать.
