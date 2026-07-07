# КАРТА + ПЛАН v2026-07-08 (заменяет 07-03). START HERE для стратегии.

## ГДЕ ДЕНЬГИ СЕЙЧАС
- LIVE: ATT1 short r001 x0.10 (Bybit, первые сделки идут, ADA под трейлингом ~breakeven)
  + Alpaca v38 $495 (первые заявки с открытия рынка США). Телеметрия/сводка/breaker'ы в бою.
- Кандидат #2 (крипта): inplay_breakout_retest — эдж есть (PF 1.44 base / 2.0 maker-cost),
  maker-fill strict FAIL близко к порогу (stress PF 1.173, 2/4 folds) -> ждём dyn-selector; без PASS не live.
- FX/CFD: данные 730d Dukascopy готовы для research (6 инструментов прошли M5 preflight). Первый gate не дал live-кандидата;
  лучшее зерно = EURJPY liquidity_sweep_bounce, но нужен exploration/redesign, не капитал.

## МАТРИЦА ПОКРЫТИЯ РЫНКА (цель = рукав в каждой клетке; заполнено ~15%)
Режимы:  bear-тренд=ATT1(live) | bull-тренд=inplay(ремонт fill) | флет гориз.=после 15m+scanner |
         флет наклонный=channel-bounce(композит готов) | паника=каскады(копим liq-поток)
Горизонты: минуты=плотности(датасет с 04.07) | часы=ATT1/inplay | дни=SWG1 среднесрок(очередь) |
           недели=Alpaca
Рынки:   крипта=live | акции=live | FX=research-data-ready | CFD/золото=research-data-ready, no capital
Механизмы в ящике (ждут формы+ворот): отскоки(failed_breakout+exhaustion+level_memory),
  заколы(liquidity_sweep+реальный liq), сетка(smart_grid, дом=золото/мажоры), пампы(pump_exhaustion).

## СТАНОК (проверка кандидата = ~день)
coverage+cost gates -> backtest -> stress -> time-OOS -> symbol-OOS/каузальный селектор ->
shadow -> телеметрия -> tiny canary(breaker+expiry) -> лестница smart_risk. Пороги пре-рег до прогона.

## ДВА ТРЕКА ПОСЛЕ ВНЕШНЕГО РЕВЬЮ 2026-07-07
- Exploration: быстрый поиск зацепок, мягкие пороги, цель = понять "есть ли жизнь". Примерные критерии:
  PF > 1.0, trades > 40/год, stress не катастрофический, без tiny-N и без lookahead. PASS -> Validation или shadow/risk=0.0,
  но НЕ live money.
- Validation/Promotion: текущие строгие ворота остаются для canary/live: stress, time folds, symbol-OOS/causal selector,
  concentration, clean shadow telemetry, breaker+expiry. Смягчать live-порог ради скорости запрещено.

## НОВЫЕ ТЕХНОЛОГИИ (07.07-07.08, все под тестами, ждут wiring через A/B)
level_memory (уважение уровней per-symbol, H1-уровни/M5-исполнение) | daily_digest (сводка в TG,
в бою) | ai_context_brief (правила дома+память в голову бортового ИИ) | ai_manual_v1 (одноразовая
ИИ-сделка по токену владельца, риск 0.05, SL обязателен — меряем винрейт ИИ как рукав).

## БЛИЖАЙШИЕ ИТЕРАЦИИ (порядок)
1. ADA: не путать runtime SL и биржевой SL; profit-lock fix применится после flat/restart.
2. Inplay dyn-selector: если 3/4 folds и PF>1.15 -> shadow/risk=0.0; иначе freeze до level_memory A/B.
3. Exploration pack: MRB crypto basket, FX H1 trend/session breakout, XAU range-bounce, OI/funding carry.
4. FX/CFD validation только после exploration-зерна; первый gate показал no capital.
5. Weekly Allocator spec: предложения по risk_mult на базе edge_monitor, решение владельца.
6. Wiring level_memory в уровневые ноги (A/B). 7. ИИ-майнер по bus (после 4-6 нед данных) -> ML.

## ПРАВИЛА (без изменений, нерушимы)
Одно изменение за раз. Отбор монет — динамика. Анти-мартингейл. ИИ предлагает — человек одобряет.
Деньги догоняют доказательства: Bybit +$1000 при рукаве#2+2нед плюса; Alpaca +$2500 после месяца
в плюсе; FX $500 после OOS на чистых данных + демо.
Архивирование старого кода — только после inventory/coverage map; не удалять стратегии вслепую во время live.
