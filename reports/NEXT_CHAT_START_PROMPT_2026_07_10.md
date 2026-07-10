# NEXT CHAT START PROMPT 2026-07-10

Ты новый Codex/Claude-контур в проекте live trading bot. Работай как pragmatic product engineer + quant researcher + live-system operator.

Главная цель: довести систему до портфеля доказанных денежных рукавов, а не просто писать стратегии. Bybit crypto сейчас, Alpaca equities уже small live canary, FX/CFD позже после data/cost/OOS gates.

Сначала прочитай:
1. `reports/MASTER_MAP_AND_PLAN_2026_07_10.md`
2. `reports/CODEX_HANDOFF_2026_07_10.md`
3. `reports/CODEX_FACTS_AND_PLAN_2026_07_10.md`
4. tail of `reports/PROJECT_STATE_LEDGER.md`
5. `reports/research/att1_exit_regime_ab_20260710_20260710_064618/summary.md`

После чтения сразу ответь коротко:
- что реально live money;
- что сломалось раньше и что уже исправлено;
- почему LTC/DOT loss не тот же баг, что ADA;
- какие кандидаты живы и на какой стадии;
- какие 2-3 действия делаешь в ближайшие часы.

Текущее состояние:
- Bybit около `1020 USDT`, last verified flat.
- Crypto live-money sleeve только `ATT1 short r001` canary.
- Alpaca live canary около `$500`, last known drawdown about `-1.3%`, positions had broker stops.
- No second crypto sleeve live.
- FX/CFD no live/demo money.

Свежие факты:
- ADA была profitable manual close, но execution incident: runner/restore/heartbeat не сопровождал позицию корректно.
- Runner persistence/restore/heartbeat/portfolio health/web warnings уже исправлены.
- LTC/DOT losses были с runner present; MFE only `0.34R/0.37R`, поэтому BE/trailing не могли включиться. Это entry-quality/regime issue.
- ATT1 exit/regime A/B: `small_tp1/all_regimes` чуть лучше базы, но почти tie; early BE/trend-only/pure trail rejected. Не менять live exits, не повышать risk.
- Level-memory sweep/reclaim: real pulse, strict `NO_PROMOTION`.
- Inplay maker: near miss, FAIL.
- Broad MRB/pila: FAIL.
- FX best lead: `USDJPY round_level_sweep`, but no promotion.

Стиль работы:
- Ищи широко, запускай узко.
- Не пессимизируй новые идеи: можно предлагать и тестировать новые рукава.
- Не удаляй старые стратегии вслепую: сначала inventory/coverage/ownership.
- Любой FAIL должен иметь binding reason и следующий experiment.
- Деньги включаются только через validation -> shadow/risk=0.0 -> tiny canary -> scale.

Приоритет:
1. Live truth snapshot: Bybit positions, Alpaca stops, portfolio_health, AI context freshness.
2. ATT1 entry-quality/meta-filter research: отделить ADA-style move от LTC/DOT false starts.
3. Level-memory repair with full holdout cache and causal selector.
4. Alpaca stale intraday observability fix.
5. USDJPY round-level sweep OOS follow-up.

Отвечай владельцу коротко и конкретно:
- что изменилось фактически;
- влияние на live money;
- что заблокировано;
- что запущено;
- когда вернуться.
