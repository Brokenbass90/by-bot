# КАРТА + ПЛАН v2026-07-08 (заменяет 07-03). START HERE для стратегии.

## ГДЕ ДЕНЬГИ СЕЙЧАС
- LIVE: ATT1 short r001 x0.10 (Bybit, ADA открыта; биржевой SL около breakeven, но runtime runner/TP/trailing сейчас НЕ виден)
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
1. ADA: не путать runtime SL и биржевой SL; текущая позиция защищена near-breakeven, но runner/TP/trailing в runtime потерян после restore. Новый durable runner-restore fix уже в коде, но вступит в силу для будущих/перезапущенных сделок после flat/restart.
2. Inplay dyn-selector: текущий maker/dynsel weak/FAIL -> freeze до level_memory/entry-quality A/B.
3. Exploration pack: level_memory sweep/reclaim full run, ATT1 exit A/B, FX/XAU redesign, OI/funding carry.
4. FX/CFD validation только после exploration-зерна; первый gate показал no capital.
5. Weekly Allocator spec: предложения по risk_mult на базе edge_monitor, решение владельца.
6. Wiring level_memory в уровневые ноги (A/B). 7. ИИ-майнер по bus (после 4-6 нед данных) -> ML.

## ТОП-3 СТАВКИ СЛЕДУЮЩЕГО ЦИКЛА
1. ATT1 exit/re-entry A/B: entry-семейство уже ловит live-движение, слабое место сейчас не вход, а удержание прибыли после TP1.
2. Level-memory range/sweep/reclaim: "пила"/отскоки остаются важной веткой, но только через качество уровней, causal symbol-selection и отдельные long/short ноги. Broad MRB по всем монетам провалился и не включается; новый full run `crypto_lm_sweep_reclaim_20260707` идёт.
3. FX/XAU H1 range/sweep/session: данные готовы для research; первый H1 exploration не дал capital-ready строки, поэтому следующий шаг = redesign/OOS, без капитала до demo.

## ИНЦИДЕНТ ADA RUNNER RESTORE (07.07)
ATT1 runner должен уметь TP-лестницу, breakeven, ATR trailing и time-stop. Текущая ADA показала не слабость входа, а слабость восстановления состояния: после рестарта открытая позиция была восстановлена с биржевым SL, но без durable runner-плана. Фикс: runner snapshot теперь пишется в live events и восстанавливается из них; частично закрытые TP inferred by reduced exchange qty. Текущую ADA не двигаем кодом без явного решения владельца.

## ПРАВИЛА (без изменений, нерушимы)
Одно изменение за раз. Отбор монет — динамика. Анти-мартингейл. ИИ предлагает — человек одобряет.
Деньги догоняют доказательства: Bybit +$1000 при рукаве#2+2нед плюса; Alpaca +$2500 после месяца
в плюсе; FX $500 после OOS на чистых данных + демо.
Архивирование старого кода — только после inventory/coverage map; не удалять стратегии вслепую во время live.
