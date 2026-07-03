# ARF2 failed-breakout short — пре-регистрация строгого gate (2026-07-03, Claude)

Пишу ДО прогона. Codex-находка: ARF2 failed_breakout short на DOGE/XRP/ONDO — 73 сделки,
+25.87R, PF1.65, fee-stress держит (16bps: +18R PF1.41), обе половины+90d плюс, 3/3 символа.
СЛАБОЕ МЕСТО (Codex сам): символы выбраны ПОСЛЕ анализа = selection bias.

## Independent OOS-symbol чек (Claude, failed_breakout short, cooldown)
- Выбранные DOGE/XRP: + (мало сделок в кэше).
- НЕ выбранные: SOL +1.3, ADA +2.8, AVAX +1, SUI +0.4, BTC/LINK ~0, DOT -3.
- Вывод: НЕ чистый оверфит (слабо+ на свежих), но эдж ТОНЬШЕ хедлайна. +25R раздут выбором символов.

## ПРЕ-РЕГИСТРИРОВАННЫЕ критерии PASS (все обязательны)
1. **OOS-СИМВОЛЫ (главное):** зафиксировать params из DOGE/XRP/ONDO-анализа, прогнать ТОТ ЖЕ
   config на СВЕЖЕМ наборе (BTC/SOL/LINK/ADA/AVAX/DOT/SUI/LTC/...). PASS = >=50% свежих символов
   net>0, агрегат>0, НЕ вытянут 1 символом. Если работает только на выбранных -> оверфит, NO-GO.
2. **Temporal:** purge/embargo фолды, >=3/4 net>0 (обе половины+90d уже плюс — хороший знак).
3. **Fee/slip-stress:** держит (уже: PF1.41@16bps — ок).
4. **Реалистичный размер:** хедлайн +25R = selection-inflated. Ждать ТОНКИЙ cross-symbol
   expectancy (~+0.1..0.4R/сделку по свежим). Считать %/год от РЕАЛЬНОГО cross-symbol, не от +25R.

## Если PASS
- shadow (paper) -> edge_monitor healthy -> tiny canary (первый горизонтальный крипто-рукав).
- ОБЯЗАТЕЛЬНО при live: (а) regime_hmm-гейт — short-alt эджи вероятно bear_chop-зависимы,
  выключать/резать в bull; (б) exposure correlation-cap — ARF2-short + ATT1-short + др. short-alt
  коррелированы, вместе сольются в alt-bull-развороте. Оба модуля готовы (regime_hmm, exposure_gate).

## Если FAIL по OOS-символам
Не хоронить: это симптом symbol-selection. Вернуть с symbol-агностик отбором (условие входа,
не список монет) -> заново.

## Контекст портфеля
Кандидаты: ATT1 short (доказан, редкий) + ARF2 failed-breakout short (в gate). ОБА short, оба
возможно bear_chop-зависимы -> НЕ over-allocate; correlation-cap + regime-гейт обязательны.
