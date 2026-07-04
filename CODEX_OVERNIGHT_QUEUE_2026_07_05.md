# НОЧНАЯ ОЧЕРЕДЬ ПРОГОНОВ (владелец отошёл ~12ч; 2026-07-05, Claude)

Правила ночи: гнать ПОСЛЕДОВАТЕЛЬНО (Mac не задыхается), каждый прогон в screen с логом,
пороги НЕ ослаблять под результат, вердикты — строки в ledger. Сервер = только live +
коллекторы (проверить, что bus/health/densities растут). Mac не давать засыпать.

## A. Каскады на реальных ликвидациях (приоритет #1, ~1-2ч)
1. Стянуть с сервера runtime/liquidations/*.jsonl на Mac (scp), НЕ гонять на VPS.
2. python3 scripts/run_cascade_real_gate.py --liq-jsonl <файл> --crypto-cache data_cache
   (funding/OI подтянет с Bybit REST сам; coverage-гейт встроен; грид пре-регистрирован — НЕ расширять).
3. Вердикт в ledger: N сделок, per-symbol/side, фолды. Если N < ~30 суммарно -> «копить поток», не хоронить.

## B. Юниверс ATT1 (приоритет #2, часы)
По reports/ATT1_UNIVERSE_EXPANSION_PREREG_2026_07_04.md БЕЗ отклонений:
r001-параметры замороженные, 11 монет (DOGE,XRP,AVAX,ATOM,BNB,BCH,XLM,1000PEPE,HYPE,TAO,ONDO),
сначала coverage-чек 5m, базовые 8 НЕ включать. Отчёт: группа+per-symbol+фолды+fee-stress 10/5.

## C. FX-тренд полный (приоритет #3, часы; харнесс теперь быстрый)
scripts/run_fx_native_harness.py на data_cache/forex_1h (2.4 ГОДА, --interval-min 60):
- setups: trend_pullback + session_breakout_retest (сильнейшее семейство: трендовые, частые);
- pairs: EURUSD,GBPUSD,USDJPY,AUDUSD; cost+coverage гейты включены (уже в раннере);
- USDJPY смотреть отдельно (там пульс PF1.26) — если на 2.4г держит PF>1.15 и 3/4 фолда -> строгий oos_selector.

## D. Среднесрок крипта (приоритет #4, часы) — ВАЖНО обновить окна!
Старые раннеры имеют протухшие END (v3: 2026-03-31; short_v2: 2024-12-31!). Гнать с:
- bash scripts/run_midterm_short_v2_backtests.sh с END=2026-07-04 DAYS=1095 (WF-окна оставить);
- bash scripts/run_midterm_v3_backtest.sh с END=2026-07-04 (Test 1 и 2 достаточно, Test 4 пропустить);
- Разрез обязательный: side-split + per-period (bull-ноги!). Это ревью сильнейшего среднесрока
  (short_v2 = bear-ориентированный D+H4; v3 = MACD-pullback BTC/ETH) ПЕРЕД постройкой SWG1
  (флип+трейлинг): результаты скажут, какую базу SWG1 брать.

## E. XAU backfill + ре-скрининг (приоритет #5, если время осталось)
1. Дозалить XAUUSD H1 (yfinance GC=F / дукас) до coverage>=0.99 (сейчас 0.9336, 494 дыры).
2. После чистых данных: round_sweep + structure_break short на 876d+ через тот же харнесс.

## УТРОМ владельцу (сводка одним сообщением):
статус live (сделки ATT1? bus-записи?), вердикты A-D, что прошло в следующий этап.
Claude утром разбирает всё честно: cross-symbol, per-period, красные месяцы.
