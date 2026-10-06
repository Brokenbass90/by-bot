# INVENTAR_NOG — все ноги проекта (вид; правится через inventar.py)
Сгенерировано 2026-10-06T19:16:23+00:00.

| нога | рынок | что ловит | сторона | режим | edge | исполнение | статус |
|---|---|---|---|---|---|---|---|
| KITY_M3_POTOK | крипта Binance USDT-M | продолжение за агрессивным потоком тейкеров d−1, недельно, PIT топ-50 | long+short (дециль k=n//10) | UNKNOWN (по годам 2023 +30, 2024 +37, 2025 +183, 2026 +185 bps — режимный разбор B3) | PRIMARY +103 bps/нед t2.59; репл. SAME_SIGN +74 | orders-off у Codex, паритет 251 вектора PASS; тень с 08.10 | READY_FOR_BUILD → canary-ворота 09.10 |
| REBALANCING_PRESSURE | индексы US30 (FxPro CFD) | конец месяца против перекоса акции−облигации | long/short индекса | не крипто-режим; календарный | PRIMARY +42.7 bps/соб t2.06; HOLDOUT +12.5 SAME_SIGN | тень rebal_ten; пакет Codex после 30.10 | READY_FOR_BUILD (на грани), вперёд 26–30.10 |
| ALPACA | акции США | v38/SPY200 селектор, месячный → динамическая замена | long | фильтр SPY200 внутри | история 14.48%/г DD 7.57% PF 1.81 | LIVE (CRWD, META) с защитой | LIVE; Dynamic V1 → PAPER/LIVE GO |
| ETS2M | крипта Bybit | Elder triple screen, исполнимая версия ETS2S | long+short | UNKNOWN | ETS2S информация +0.0668R 4.22σ; деньги — вердикт ETS2M | тень ядра | вердикт 10.10 19:00 UTC |
| ATT1 | крипта Bybit | касание наклонной линии тренда, шорт | short | аудит 14.08: bull +1.26R/91 PF1.03, neutral +5.57R/252 PF1.04, bear −11.36R/35 PF0.51; оркестратор 08: флет- | слабый: PF ≈1.03–1.04 в хороших режимах; reserved OOS 29.08 FAIL_CLOSED | BLOCKED_DATA (транспорт CTS; 48ч-терминал 06.10) | CONDITIONAL_CANDIDATE: edge по режиму и исполнение — раздельно |
| SBR1 | крипта Bybit major8 | пробой наклонного уровня с ретестом, лонг | long | флет+ (оркестратор 08) | история 2023–25 64 сделки +24.26R PF2.06; reserved OOS 16 сделок −3.31R (LOW_N) | тень на VPS с 24.08, журнал 40 768 событий, сделок 0 | INCONCLUSIVE_LOW_N |
| BOUNCE1 | крипта BTC/ETH | отскок от уровня | long? | UNKNOWN | 3 окна по 120 дн. все +, 41 сделка, PF 1.86/3.35/2.39 | тень не развёрнута (02.08) | PASS_TO_PROSPECTIVE_RISK_ZERO |
| alpaca_adaptive_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (25 упом.) |
| alpaca_dynamic_v3_event | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| alpaca_dynamic_v4_event | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| alt_bear_regime_continuation_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (26 упом.) |
| alt_channel_bounce_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (20 упом.) |
| alt_elder_revived_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (28 упом.) |
| alt_horizontal_break_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (27 упом.) |
| alt_inplay_breakdown_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (72 упом.) |
| alt_inplay_breakdown_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (20 упом.) |
| alt_liquidity_sweep_reversal_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (19 упом.) |
| alt_momentum_breakout_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| alt_pullback_continuation_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| alt_range_reclaim_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| alt_range_scalp_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (52 упом.) |
| alt_resistance_fade_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (63 упом.) |
| alt_resistance_fade_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (19 упом.) |
| alt_slope_break_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (27 упом.) |
| alt_sloped_channel_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (44 упом.) |
| alt_sloped_momentum_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (26 упом.) |
| alt_squeeze_breakout_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (24 упом.) |
| alt_support_bounce_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (50 упом.) |
| alt_support_bounce_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (25 упом.) |
| alt_support_reclaim_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (19 упом.) |
| alt_trendline_touch_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (17 упом.) |
| alt_volume_spike_momentum_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (20 упом.) |
| asb1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| asm1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (11 упом.) |
| att1_v2_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (12 упом.) |
| basis_arb_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| breakdown_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| breakdown_retest_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (19 упом.) |
| btc_cycle_continuation_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| btc_cycle_level_target_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| btc_cycle_pullback_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| btc_eth_midterm_pullback | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (57 упом.) |
| btc_eth_midterm_short_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (16 упом.) |
| btc_eth_midterm_short_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| btc_eth_midterm_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (22 упом.) |
| btc_regime_flip_continuation_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| btc_regime_retest_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| btc_sloped_reclaim_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| elder_crypto_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| elder_triple_screen_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (32 упом.) |
| equities_swing_active_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (16 упом.) |
| event_expansion_retest_long_mtf_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (9 упом.) |
| event_expansion_retest_long_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (27 упом.) |
| flat_resistance_fade_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| funding_hold_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (17 упом.) |
| funding_rate_reversion_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (20 упом.) |
| grid_smart_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| gs1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (11 упом.) |
| hzbo1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| impulse_volume_breakout_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (51 упом.) |
| inplay_breakout | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (111 упом.) |
| inplay_retest_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (45 упом.) |
| inplay_retest_v4 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (27 упом.) |
| inplay_wrapper | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| liquidation_cascade_entry_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (24 упом.) |
| live_kline_utils | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (11 упом.) |
| micro_scalper_breakout_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| micro_scalper_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (11 упом.) |
| micro_scalper_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (26 упом.) |
| pair_arb_executor_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (17 упом.) |
| pair_stat_arb_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| pfs1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (10 упом.) |
| pump_exhaustion_unwind_short_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (26 упом.) |
| pump_fade_simple | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (27 упом.) |
| pump_fade_smart_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (20 упом.) |
| pump_fade_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| pump_fade_v4r | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (32 упом.) |
| pump_momentum_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| range_mean_reversion_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (21 упом.) |
| sbr1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (7 упом.) |
| sc1_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| scalper_bounce_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| scalper_breakout_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (14 упом.) |
| scalper_classic_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| scalper_sweep_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (12 упом.) |
| session_open_breakout_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (10 упом.) |
| signals | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (127 упом.) |
| sloped_break_retest_v2 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (15 упом.) |
| sloped_break_retest_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (10 упом.) |
| sloped_channel_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (17 упом.) |
| sloped_resistance_choch_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (19 упом.) |
| smart_grid | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (44 упом.) |
| smart_grid_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (18 упом.) |
| spike_fade_v3 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (28 упом.) |
| support_reclaim_live | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (10 упом.) |
| trend_pullback_v1 | ? | ? | ? | ? | ? | ? | NE_PROVERENO (B1) (13 упом.) |
| ETS2S | ? | Элдер, три экрана, шорт по лимиту | ? | ? | информация PASS: +0.0668R к контролю режима, 4.22σ на 2803; деньги −329.9R; избыток по половинам +0.1207/+0.0153 | ? | SHADOW |
| ARB_EGLD | ? | Кросс-биржевой арбитраж как повторяемая нога | ? | ? | повторяемого нет: из 2882 пар за 7 суток выжила одна, 4 $ за круг | ? | NEGATIVE |
| ALPACA_INTENDED | ? | Намеренный контракт Alpaca, v38 successor | ? | ? | 14.48% годовых, DD 7.57%, PF 1.81 — история | ? | READY_FOR_BUILD |
| ATT1_KASANIE | ? | Номер касания линии у ATT1 | ? | ? | (3+)−(1) = −0.0456R, −2.55σ на 232 решениях: лестница перевернулась | ? | NEGATIVE |
| GOLD | ? | Золото, H1 через мост MT5 | ? | ? | Элдер на золоте 2019–22: +4.79R, 0.93σ (ЧАСТИЧНО); фабрика 21.09: 13 из 14 LOW_N на 2 годах H1 | ? | POSITIVE_LEAD |
| ATT1_AGG | ? | ATT1 целиком, агрегат тени | ? | ? | +0.055R к контролю режима при sigma 0.27; по деньгам -10.2R | ? | SHADOW |
| UROVNI_OTBOY | ? | Отбой от уровня как самостоятельный вход | ? | ? | -2.6% к плацебо на геометрии ATT1, отрицательно во всех трёх эпохах | ? | NEGATIVE |
| ATT1_FILTER | ? | Фильтр ATT1 по одному признаку | ? | ? | все признаки провалили проверку по трём эпохам | ? | NEGATIVE |
| ALPACA_A_G2 | ? | Челленджер A+G2 у Alpaca | ? | ? | 30.26% годовых на замере, но провалил все четыре кризисных среза | ? | NEGATIVE |
| ARB_EVENT_CLASS | ? | Премия монеты с закрытым вводом на одной бирже | ? | ? | EGLD: 39.6-58.4 бп чистыми, жив в 100% срезов 11 суток | ? | POSITIVE_LEAD |
| OI_RASHOZHDENIE | ? | Расхождение открытого интереса и цены | ? | ? | все 12 клеток не прошли; четыре значимо ОТРИЦАТЕЛЬНЫ до -3.3 сигмы | ? | NEGATIVE |
| CS_OBOROT | ? | Кросс-секция по обороту: пришёл ли объём вместе с ценой | ? | ? | лестницы нет: середина минус, края около нуля, порог не пройден | ? | NEGATIVE |
| VOZRAST_MONETY | ? | Возраст монеты от листинга | ? | ? | знак не монотонен, Q4 хуже Q5; порог не пройден | ? | NEGATIVE |
| RAZBROS_RYNKA | ? | Разброс доходностей как режим рынка | ? | ? | не измерен | ? | HYPOTHESIS |
| RAZMAH_SVECHI | ? | Размах дневной свечи как плата за ликвидность | ? | ? | КАРМАН: лестница ровная во всех трёх горизонтах, 7 дн: -53.5 / -48.0 / -47.2 / +1.0 / +93.9 бп, Q5 +2.1 сигмы. Порог Бонферрони 3.02 НЕ пройден — по объявленному правилу это NEGATIVE. ПОДТВЕРЖДАЮЩИЙ ТЕСТ ПРОВАЛЕН: после нормировки на волатильность карман исчез. | ? | NEGATIVE |
| RAZMAH_NORM | ? | Размах свечи, нормированный на волатильность | ? | ? | карман исчез: сырой Q5 на 7 дн был +93.9 бп при 2.1 сигмы, после нормировки на волатильность +33.9 при 1.1 | ? | NEGATIVE |
| OTKAT_KRIPTA | ? | Откат от максимума 30 дней на крипте | ? | ? | середина значимо отрицательна, края не проходят порог | ? | NEGATIVE |
| RAZVOROT_1D | ? | Короткий разворот: вчерашняя доходность | ? | ? | лестницы нет, края не проходят порог | ? | NEGATIVE |
| IMPULS_7D | ? | Продолжение движения за 7 дней | ? | ? | лестницы нет, Q5 +1.3 сигмы при пороге 3.02 | ? | NEGATIVE |
| BETA_BTC | ? | Бета к биткоину за 30 дней | ? | ? | края симметрично около нуля, середина в минусе | ? | NEGATIVE |
| OI_KVINTIL | ? | Изменение открытого интереса, квинтили | ? | ? | все квинтили отрицательны или у нуля | ? | NEGATIVE |
| TELO_SVECHI | ? | Тело свечи к размаху | ? | ? | лестницы нет | ? | NEGATIVE |
| NOCHNOY_RAZRYV | ? | Ночной разрыв на стыке суток | ? | ? | НЕ ИЗМЕРЕН | ? | HYPOTHESIS |
| SBR1_MAJOR8 | ? | SBR1 родной sloped_break_retest_v1, 8 мажоров | ? | ? | история 2023–25: 64 сделки +24.26R PF 2.06; reserved OOS 2025-10…07: 16 сделок −3.31R PF 0.64 (INCONCLUSIVE_LOW_N) | ? | SHADOW |
| SBR1_ISSLED | ? | SBR1 исследовательский: лонг ×4, флет+, 137 монет | ? | ? | печать 3.09: 415 сделок −23.3R, эдж −0.0145R, −0.33σ | ? | NEGATIVE |
| XSEC_V3_TEN | ? | XSEC v3: ранг моментума + волатильности, рыночно-нейтральный | ? | ? | тень 57 дн: +$88.9 валовых на $1000, половины +45.6/+43.3, t≈0.35; PIT-упрощённый в фабрике t=1.65 | ? | SHADOW |
| ATT1_LONG_TREND | ? | trendline_touch · crypto137 · {'mod': 'alt_trendline_touch_v1', 'cls': 'AltTrendlineTouchV1Strategy', 'pfx': 'ATT1', 'side': 'long', 'mult': 6, 'hold': 336, 'regime': 'тренд+', 'cd': '8'} | ? | ? | ? | ? | NEGATIVE |
| ATT1_SHORT_TREND | ? | trendline_touch · crypto137 · {'mod': 'alt_trendline_touch_v1', 'cls': 'AltTrendlineTouchV1Strategy', 'pfx': 'ATT1', 'side': 'short', 'mult': 6, 'hold': 336, 'regime': 'тренд-', 'cd': '8'} | ? | ? | ? | ? | NEGATIVE |
| SBR1_LONG_TREND | ? | sloped_retest · crypto137 · {'mod': 'sloped_break_retest_v1', 'cls': 'SlopedBreakRetestV1Strategy', 'pfx': 'SBR1', 'side': 'long', 'mult': 4, 'hold': 168, 'regime': 'тренд+', 'cd': '0'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__gold__long | ? | breakout · gold · {'meh': 'PROBOY_55', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__gold__short | ? | breakout · gold · {'meh': 'PROBOY_55', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| SZHATIE_BB__gold__long | ? | volatility_expansion · gold · {'meh': 'SZHATIE_BB', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| SZHATIE_BB__gold__short | ? | volatility_expansion · gold · {'meh': 'SZHATIE_BB', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| OTKAT_V_TRENDE__gold__long | ? | trend_pullback · gold · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| OTKAT_V_TRENDE__gold__short | ? | trend_pullback · gold · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| PROBOY_55__crypto137__long | ? | breakout · crypto137 · {'meh': 'PROBOY_55', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__crypto137__short | ? | breakout · crypto137 · {'meh': 'PROBOY_55', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| SZHATIE_BB__crypto137__long | ? | volatility_expansion · crypto137 · {'meh': 'SZHATIE_BB', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| SZHATIE_BB__crypto137__short | ? | volatility_expansion · crypto137 · {'meh': 'SZHATIE_BB', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| OTKAT_V_TRENDE__crypto137__long | ? | trend_pullback · crypto137 · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| OTKAT_V_TRENDE__crypto137__short | ? | trend_pullback · crypto137 · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__crypto137__long | ? | mean_reversion · crypto137 · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__crypto137__short | ? | mean_reversion · crypto137 · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__gold__long | ? | mean_reversion · gold · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| VOZVRAT_K_SREDNEY__gold__short | ? | mean_reversion · gold · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| KAPITULYACIYA__gold__long | ? | liquidation_reversal · gold · {'meh': 'KAPITULYACIYA', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| KAPITULYACIYA__gold__short | ? | liquidation_reversal · gold · {'meh': 'KAPITULYACIYA', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| OBEM_IMPULS__gold__long | ? | flow_continuation · gold · {'meh': 'OBEM_IMPULS', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| OBEM_IMPULS__gold__short | ? | flow_continuation · gold · {'meh': 'OBEM_IMPULS', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| MOMENTUM_30D__gold__long | ? | ts_momentum · gold · {'meh': 'MOMENTUM_30D', 'rynok': 'gold', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| MOMENTUM_30D__gold__short | ? | ts_momentum · gold · {'meh': 'MOMENTUM_30D', 'rynok': 'gold', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| KAPITULYACIYA__crypto137__long | ? | liquidation_reversal · crypto137 · {'meh': 'KAPITULYACIYA', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| KAPITULYACIYA__crypto137__short | ? | liquidation_reversal · crypto137 · {'meh': 'KAPITULYACIYA', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| OBEM_IMPULS__crypto137__long | ? | flow_continuation · crypto137 · {'meh': 'OBEM_IMPULS', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| OBEM_IMPULS__crypto137__short | ? | flow_continuation · crypto137 · {'meh': 'OBEM_IMPULS', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| MOMENTUM_30D__crypto137__long | ? | ts_momentum · crypto137 · {'meh': 'MOMENTUM_30D', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| MOMENTUM_30D__crypto137__short | ? | ts_momentum · crypto137 · {'meh': 'MOMENTUM_30D', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__fx7__long | ? | breakout · fx7 · {'meh': 'PROBOY_55', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__fx7__short | ? | breakout · fx7 · {'meh': 'PROBOY_55', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SZHATIE_BB__fx7__long | ? | volatility_expansion · fx7 · {'meh': 'SZHATIE_BB', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SZHATIE_BB__fx7__short | ? | volatility_expansion · fx7 · {'meh': 'SZHATIE_BB', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_AKC_MOM_6_1 | ? | xs_momentum · akcii_pit · {'signal': 'AKC_MOM_6_1', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_AKC_MOM_6_1_LONG | ? | xs_momentum_long · akcii_pit · {'signal': 'AKC_MOM_6_1_LONG', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_AKC_REVERSAL_5D | ? | xs_reversal · akcii_pit · {'signal': 'AKC_REVERSAL_5D', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_AKC_LOW_VOL_60 | ? | low_volatility · akcii_pit · {'signal': 'AKC_LOW_VOL_60', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_KR_XSEC_V3 | ? | xs_momentum_vol · kripto_pit · {'signal': 'KR_XSEC_V3', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_KR_FANDING_KERRI | ? | funding_carry · kripto_pit · {'signal': 'KR_FANDING_KERRI', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| OTKAT_V_TRENDE__fx7__long | ? | trend_pullback · fx7 · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| OTKAT_V_TRENDE__fx7__short | ? | trend_pullback · fx7 · {'meh': 'OTKAT_V_TRENDE', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_AKC_BLIZ_MAX_126 | ? | high_proximity · akcii_pit · {'signal': 'AKC_BLIZ_MAX_126', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__fx7__long | ? | mean_reversion · fx7 · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__fx7__short | ? | mean_reversion · fx7 · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| KAPITULYACIYA__fx7__long | ? | liquidation_reversal · fx7 · {'meh': 'KAPITULYACIYA', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| OBEM_IMPULS__fx7__long | ? | flow_continuation · fx7 · {'meh': 'OBEM_IMPULS', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| OBEM_IMPULS__fx7__short | ? | flow_continuation · fx7 · {'meh': 'OBEM_IMPULS', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| MOMENTUM_30D__fx7__long | ? | ts_momentum · fx7 · {'meh': 'MOMENTUM_30D', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| MOMENTUM_30D__fx7__short | ? | ts_momentum · fx7 · {'meh': 'MOMENTUM_30D', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| KAPITULYACIYA__fx7__short | ? | liquidation_reversal · fx7 · {'meh': 'KAPITULYACIYA', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| crypto_bull_continuation_v1 | ? | event_continuation · crypto137_m5 · {'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| XSEC_EXACT_TARGET_WEIGHTS_PIT | ? | xs_momentum_vol_exact · kripto_pit50 · {'vselennaya': 'pit50', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_XSEC_3D_REVERSAL | ? | xs_reversal · kripto_pit50 · {'signal': 'XSEC_3D_REVERSAL', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_BULL_LEADER_PULLBACK_BASE | ? | bull_leader_pullback · kripto_pit50 · {'signal': 'BULL_LEADER_PULLBACK_BASE', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_BULL_LEADER_PULLBACK_FILTERED | ? | bull_leader_pullback_f · kripto_pit50 · {'signal': 'BULL_LEADER_PULLBACK_FILTERED', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_BULL_VOL_EXPANSION_BASE | ? | bull_vol_expansion · kripto_pit50 · {'signal': 'BULL_VOL_EXPANSION_BASE', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_BULL_VOL_EXPANSION_FILTERED | ? | bull_vol_expansion_f · kripto_pit50 · {'signal': 'BULL_VOL_EXPANSION_FILTERED', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| POLY_SBOR | ? | Polymarket: сборщик только на чтение + сенсор POLY_SENTIMENT_V1 | ? | ? | данных ещё нет | ? | HYPOTHESIS |
| P_BULL_VOL_EXPANSION_POLY | ? | bull_vol_expansion_poly · kripto_pit50_poly · {'signal': 'BULL_VOL_EXPANSION_POLY', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| POLY_SENSOR_INFO_3D | ? | poly_sensor · kripto_pit50_poly · {'gorizont': 3, 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_BULL_NOVYY_MAKSIMUM | ? | bull_new_high · kripto_pit50 · {'signal': 'BULL_NOVYY_MAKSIMUM', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_BULL_OTSTAYUSHCHIY | ? | bull_laggard · kripto_pit50 · {'signal': 'BULL_OTSTAYUSHCHIY', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_BULL_SILA_K_BTC | ? | bull_rs_btc · kripto_pit50 · {'signal': 'BULL_SILA_K_BTC', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| S_MAKS_MINUS_MIN | ? | novye_maksimumy · kripto_pit50 · {'rynok': 'kripto_pit50', 'priznak': 'MAKS_MINUS_MIN', 'gorizont': 5, 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| S_OBOROT_TOLCHOK | ? | oborot_tolchok · kripto_pit50 · {'rynok': 'kripto_pit50', 'priznak': 'OBOROT_TOLCHOK', 'gorizont': 5, 'etap': 'discovery'} | ? | ? | ? | ? | POSITIVE_LEAD |
| S_SHIRINA_TOLCHOK | ? | shirina_tolchok · kripto_pit50 · {'rynok': 'kripto_pit50', 'priznak': 'SHIRINA_TOLCHOK', 'gorizont': 5, 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| S_OBOROT_TOLCHOK__PODTV | ? | oborot_tolchok · kripto_pit50 · {'rynok': 'kripto_pit50', 'priznak': 'OBOROT_TOLCHOK', 'gorizont': 5, 'etap': 'confirmation'} | ? | ? | ? | ? | NEGATIVE |
| P_AKC_NOVYY_MAKSIMUM | ? | new_high · akcii_pit · {'signal': 'AKC_NOVYY_MAKSIMUM', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_AKC_SILA_K_INDEKSU | ? | rs_vs_etalon · akcii_pit · {'signal': 'AKC_SILA_K_INDEKSU', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_KR_BETA_LS | ? | beta_k_btc · kripto_pit50 · {'signal': 'KR_BETA_LS', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_KR_SILA_K_BTC_LS | ? | rs_vs_etalon_ls · kripto_pit50 · {'signal': 'KR_SILA_K_BTC_LS', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| TEN_SILA | ? | Тень: сечение по 20-дневной инерции, лонг-шорт (бывш. «обгон BTC») | ? | ? | на истории t 1.61 при n_eff 190; порог 2.5 не взят. Калибровка 24.09: линейка честная (на нуле |t|≥2.5 в 1.1% из 89 прогонов), но эдж воспроизводится на данных с порванной связью между монетами (+0.01256 против +0.01181) — значит, берётся инерция каждой монеты, а не отношение монет друг к другу | ? | SHADOW |
| P_KR_ASIMMETRIYA_VOL | ? | asimmetriya_vol · kripto_pit50 · {'signal': 'KR_ASIMMETRIYA_VOL', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| P_KR_OI_NAKOPLENIE | ? | oi_nakoplenie · kripto_pit50 · {'signal': 'KR_OI_NAKOPLENIE', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| P_KR_OSTATOCHNYY_MOMENT | ? | ostatochnyy_moment · kripto_pit50 · {'signal': 'KR_OSTATOCHNYY_MOMENT', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| S_ROTACIYA_IZ_BTC | ? | rotaciya_iz_btc · kripto_pit50 · {'rynok': 'kripto_pit50', 'priznak': 'ROTACIYA_IZ_BTC', 'gorizont': 5, 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| LONDON_PROBOY__fx7__long | ? | sessiya_proboy · fx7 · {'meh': 'LONDON_PROBOY', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__fx7__long | ? | lozhnyy_proboy · fx7 · {'meh': 'SVIP_UROVNYA', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| GEP_VYHODNYH__fx7__long | ? | gep_pereocenka · fx7 · {'meh': 'GEP_VYHODNYH', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| LONDON_PROBOY__fx7__short | ? | sessiya_proboy · fx7 · {'meh': 'LONDON_PROBOY', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| LONDON_PROBOY__crypto137__long | ? | sessiya_proboy · crypto137 · {'meh': 'LONDON_PROBOY', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__crypto137__long | ? | lozhnyy_proboy · crypto137 · {'meh': 'SVIP_UROVNYA', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| SVIP_UROVNYA__fx7__short | ? | lozhnyy_proboy · fx7 · {'meh': 'SVIP_UROVNYA', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| GEP_VYHODNYH__fx7__short | ? | gep_pereocenka · fx7 · {'meh': 'GEP_VYHODNYH', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| GEP_VYHODNYH__crypto137__long | ? | gep_pereocenka · crypto137 · {'meh': 'GEP_VYHODNYH', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| NOCHNOY_DREYF__crypto137__long | ? | premiya_za_chas · crypto137 · {'meh': 'NOCHNOY_DREYF', 'rynok': 'crypto137', 'side': 'long'} | ? | ? | ? | ? | HYPOTHESIS |
| LONDON_PROBOY__crypto137__short | ? | sessiya_proboy · crypto137 · {'meh': 'LONDON_PROBOY', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| SVIP_UROVNYA__crypto137__short | ? | lozhnyy_proboy · crypto137 · {'meh': 'SVIP_UROVNYA', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__fx7__long | ? | premiya_za_chas · fx7 · {'meh': 'NOCHNOY_DREYF', 'rynok': 'fx7', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__fx7__short | ? | premiya_za_chas · fx7 · {'meh': 'NOCHNOY_DREYF', 'rynok': 'fx7', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| GEP_VYHODNYH__crypto137__short | ? | gep_pereocenka · crypto137 · {'meh': 'GEP_VYHODNYH', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | HYPOTHESIS |
| NOCHNOY_DREYF__crypto137__short | ? | premiya_za_chas · crypto137 · {'meh': 'NOCHNOY_DREYF', 'rynok': 'crypto137', 'side': 'short'} | ? | ? | ? | ? | NEGATIVE |
| LONDON_PROBOY__gold__long | ? | sessiya_proboy · gold · {'meh': 'LONDON_PROBOY', 'rynok': 'gold', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__gold__long | ? | lozhnyy_proboy · gold · {'meh': 'SVIP_UROVNYA', 'rynok': 'gold', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| GEP_VYHODNYH__gold__long | ? | gep_pereocenka · gold · {'meh': 'GEP_VYHODNYH', 'rynok': 'gold', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| NOCHNOY_DREYF__gold__long | ? | premiya_za_chas · gold · {'meh': 'NOCHNOY_DREYF', 'rynok': 'gold', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| LONDON_PROBOY__gold__short | ? | sessiya_proboy · gold · {'meh': 'LONDON_PROBOY', 'rynok': 'gold', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__gold__short | ? | lozhnyy_proboy · gold · {'meh': 'SVIP_UROVNYA', 'rynok': 'gold', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| GEP_VYHODNYH__gold__short | ? | gep_pereocenka · gold · {'meh': 'GEP_VYHODNYH', 'rynok': 'gold', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| NOCHNOY_DREYF__gold__short | ? | premiya_za_chas · gold · {'meh': 'NOCHNOY_DREYF', 'rynok': 'gold', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| GEP_VYHODNYH__fx7_glub__short | ? | gep_pereocenka · fx7_glub · {'meh': 'GEP_VYHODNYH', 'rynok': 'fx7_glub', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| PROBOY_55__gold_glub__short | ? | breakout · gold_glub · {'meh': 'PROBOY_55', 'rynok': 'gold_glub', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SZHATIE_BB__gold_glub__long | ? | volatility_expansion · gold_glub · {'meh': 'SZHATIE_BB', 'rynok': 'gold_glub', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__gold_glub__long | ? | mean_reversion · gold_glub · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'gold_glub', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SZHATIE_BB__gold_glub__short | ? | volatility_expansion · gold_glub · {'meh': 'SZHATIE_BB', 'rynok': 'gold_glub', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| VOZVRAT_K_SREDNEY__gold_glub__short | ? | mean_reversion · gold_glub · {'meh': 'VOZVRAT_K_SREDNEY', 'rynok': 'gold_glub', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| LONDON_PROBOY__gold_glub_utc__long | ? | sessiya_proboy · gold_glub_utc · {'meh': 'LONDON_PROBOY', 'rynok': 'gold_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| LONDON_PROBOY__fx7_glub_utc__long | ? | sessiya_proboy · fx7_glub_utc · {'meh': 'LONDON_PROBOY', 'rynok': 'fx7_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__gold_glub_utc__long | ? | premiya_za_chas · gold_glub_utc · {'meh': 'NOCHNOY_DREYF', 'rynok': 'gold_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__fx7_glub_utc__long | ? | premiya_za_chas · fx7_glub_utc · {'meh': 'NOCHNOY_DREYF', 'rynok': 'fx7_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | POSITIVE_LEAD |
| SVIP_UROVNYA__gold_glub_utc__long | ? | lozhnyy_proboy · gold_glub_utc · {'meh': 'SVIP_UROVNYA', 'rynok': 'gold_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__fx7_glub_utc__long | ? | lozhnyy_proboy · fx7_glub_utc · {'meh': 'SVIP_UROVNYA', 'rynok': 'fx7_glub_utc', 'side': 'long', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| LONDON_PROBOY__gold_glub_utc__short | ? | sessiya_proboy · gold_glub_utc · {'meh': 'LONDON_PROBOY', 'rynok': 'gold_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| LONDON_PROBOY__fx7_glub_utc__short | ? | sessiya_proboy · fx7_glub_utc · {'meh': 'LONDON_PROBOY', 'rynok': 'fx7_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__gold_glub_utc__short | ? | premiya_za_chas · gold_glub_utc · {'meh': 'NOCHNOY_DREYF', 'rynok': 'gold_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| NOCHNOY_DREYF__fx7_glub_utc__short | ? | premiya_za_chas · fx7_glub_utc · {'meh': 'NOCHNOY_DREYF', 'rynok': 'fx7_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__gold_glub_utc__short | ? | lozhnyy_proboy · gold_glub_utc · {'meh': 'SVIP_UROVNYA', 'rynok': 'gold_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | NEGATIVE |
| SVIP_UROVNYA__fx7_glub_utc__short | ? | lozhnyy_proboy · fx7_glub_utc · {'meh': 'SVIP_UROVNYA', 'rynok': 'fx7_glub_utc', 'side': 'short', 'etap': 'discovery'} | ? | ? | ? | ? | HYPOTHESIS |
| NOCHNOY_DREYF__fx7_glub_utc__long__PODTV | ? | premiya_za_chas · fx7_glub_utc · {'meh': 'NOCHNOY_DREYF', 'rynok': 'fx7_glub_utc', 'side': 'long', 'etap': 'confirmation'} | ? | ? | ? | ? | CANDIDATE |
| TOLPA_XS | bybit+binance | толпа ошибается на краях (доля лонг-аккаунтов) | ? | ? | Binance L1 +20 bps/нед t0.27 | ? | KILL |
| KITY_POZICII | binance metrics | позиции топ-трейдеров | ? | ? | −53.6 bps/нед t−1.41 | ? | PNL_FAIL |
| REZHIMNYY_CARRY | binance funding | carry при высоком рыночном фандинге | ? | ? | ON 8.8%, 1.29%/год | ? | KILL |
| LONG_TREND_MAJORS | binance klines | моментум BTC/ETH 28 дн. | ? | ? | t0.76/1.11 | ? | KILL |
| PUSTOY_HOD | binance klines taker | разворот хода без потока | ? | ? | −55 bps/нед; корр. с сырым разворотом 0.88 | ? | KILL |
| NOVYE_DENGI | binance metrics | ход при росте OI в контрактах | ? | ? | +43 bps/нед t0.95 | ? | KILL |
| FX_MESYAC_HEDZH | MT5 FxPro D1: EURUSD, US30 (#US30), GER40 (#Germany40) | иностранные держатели акций США хеджируют валютный риск в конце месяца: если акции США обогнали европейские, продают USD (EURUSD вверх) | ? | ? | {"PRIMARY": {"mesyacev": 107, "srednee_bps": -5.39, "t": -0.65, "polovinki_bps": [-6.62, -4.18], "dolya_plyus": 0.5}, "HOLDOUT": {"mesyacev": 97, "srednee_bps": -5.88, "t": -1.02, "polovinki_bps": [-14.74, 2.8], "dolya_plyus": 0.51, "status": "OPPOSITE"}} | ? | KILL |
