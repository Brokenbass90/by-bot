# NEXT CHAT START PROMPT 2026-07-10

> Superseded by `reports/NEXT_CHAT_START_PROMPT_2026_07_11.md` and
> `reports/PROJECT_RECOVERY_TRUTH_AND_ROADMAP_2026_07_11.md`.

Ты новый Codex/Claude-контур в проекте live trading bot. Работай как pragmatic product engineer + quant researcher + live-system operator.

Главная цель: довести систему до портфеля доказанных денежных рукавов, а не просто писать стратегии. Bybit crypto сейчас, Alpaca equities уже small live canary, FX/CFD позже после data/cost/OOS gates.

Сначала прочитай:
1. `reports/PROJECT_SYSTEM_AND_ROADMAP_2026_07_10.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_10.json`
3. `reports/MASTER_MAP_AND_PLAN_2026_07_10.md`
4. tail of `reports/PROJECT_STATE_LEDGER.md`
5. текущий `git status` и свежий direct runtime/server snapshot

Не повторяй уже завершённый аудит. Сравни `last_session` и `next_actions`, проверь freshness и продолжай первый незавершённый action. В конце обнови canonical index и append-only ledger.

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
- Поправка: это big-figure/decade-handle sweep; side split short positive, long negative. Нужен новый short-only prereg.
- TG AI ошибочно истолковал `missing_candles`: это post-hoc forensic cache gap, не доказательство сломанных live candles/exits.
- Local P0 truth/Alpaca/web/FX fixes готовы, но ещё не deployed; live risk/orders не менялись.
- Latest Jul 11 implementation checkpoint: `e286534`; documentation commits follow it. VPS `f7ed011` was 22 implementation commits behind. Resolve current HEAD and use the superseding Jul 11 prompt above.
- FX V2 prereg tested impulse breakout/retest, sweep/reclaim bounce and range/pila as separate long/short sleeves. All six are negative in base and stress -> `NO_PROMOTION`; do not tune the same frozen run.
- Strict FX data has zero promotion-valid symbols; four pairs are diagnostic-only after complete-H1 and gap/censor controls; EURJPY/XAU blocked.
- Clean independent InPlay short also `NO_PROMOTION` (PF `1.075`, concentration `67.7%`). Build event-first pump exhaustion short and event expansion long successors.
- Alpaca is safe-hold at `$486.93`, stops `4/4`; safety changed, proven profitability did not. Rebuild idempotent fill ledger baseline before deploy.
- Read `reports/MORNING_RECOVERY_CHECKPOINT_2026_07_11.md` and continue its first unfinished action.

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
