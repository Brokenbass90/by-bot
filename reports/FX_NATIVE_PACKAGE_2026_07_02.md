# FX/CFD native пакет — под массовый перебор (2026-07-02, Claude)

bot/fx_setups.py (7 тестов): 4 РОДНЫХ FX-сетапа (не порт крипты), каждый композит наших
технологий, сплит long/short, параметризован под свипы тысяч вариаций. Данные — бесплатные
(Dukascopy/yfinance/OANDA demo), zero-risk.

## Сетапы
1. session_range_fade — фейд экстремума сессионного range (range_filter + news/session).
2. round_level_sweep — стоп-хант реверс у КРУГЛОГО уровня (liquidity_sweep + unified round levels).
3. session_breakout_retest — London/NY пробой + ретест (breakout_confirm + retest_quality).
4. trend_pullback — откат к уровню ПО тайду (elder_filter + retest_quality).
Все под news_session_filter (не входим у новостей / тонкой азии).

## Как перебирать ТЫСЯЧИ вариаций (Codex, demo)
Свип по: символы (EURUSD/GBPUSD/USDJPY/GBPJPY/XAUUSD/...), сторона (long/short раздельно),
сессии, edge_zone/tol_frac/min_quality/TP_RR, вкл/выкл фильтры. Каждая комбо ->
preflight_check (GO/NO-GO, не гнать пустые) -> wf_folds (purge+embargo) -> oos_selector
(robust_plateau, N>=40, >=8/фолд, fee-stress). Что прошло -> shadow -> canary.
Это конвейер «перебрать тысячи, отобрать по OOS» — ровно то, что нужно.

## Инвариант
Ничего не в live без OOS. Но ПРОБУЕМ МНОГО и БЫСТРО — offense. FX ranges чище крипты,
структурные эджи (стоп-ханты десков, сессии) реальны и не-публичны. XAU sweep — топ-интерес.
