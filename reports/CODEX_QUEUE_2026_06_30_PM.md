# Codex queue — переприоритет (2026-06-30, день/вечер)

Контекст: ночной WF-батч из CODEX_QUEUE_2026_06_29_PM ЕЩЁ НЕ ВЕРНУЛСЯ (нет артефактов
30-06). Плюс открылась проблема: carry dry-run на 125 циклах НЕТТО ОТРИЦАТЕЛЕН.
Подробности: reports/WF_AND_LIVE_HONEST_READ_2026_06_30_PM.md.

## P0 — carry: НЕ live, диагностировать и ре-гейтнуть
Факт: `runtime/live_mirror/arb_roi_estimate.json` (settlement_execution_v2, 125 closed):
WR 35.2%, mean −0.021%/цикл, p25 −0.19%, проекция −5.7%/мес. Хедлайн APR не выживает.
- Ре-гейт входа по NET-ЗА-ЦИКЛ: (купон за hold) − (round-trip costs обеих ног) − buffer > 0,
  а НЕ по spread_apr.
- Жёсткий delta-neutral (`bot/carry_neutral.py`) + проверка фактического баланса обеих
  ног до плана (dry-run сейчас ловит insufficient_balance на short-leg → недохедж).
- Пересчитать `arb_roi_estimate` на тех же 125 циклах после ре-гейта. Вернуть: net-за-цикл
  ДО/ПОСЛЕ. Если остаётся ≤0 — carry в архив гипотез, не в live.

## P0 — выдать обещанный WF-батч (всё ещё нет результатов)
По CODEX_QUEUE_2026_06_29_PM обновлению: вернуть цифры в первую очередь по:
- pair-arb cointegration (`walkforward_pair_arb`/`validate_pair_arb`) на ETH/BTC, SOL/ETH,
  ARB/OP и пр. — OOS-плато, не пик.
- InPlay V4 (вход 1m/лимит у уровня, свежесть, tp2.5/sl1).
- ASB2/ACB1 (вкл. adaptive) 240d, next-open, честные издержки.
Формат: OOS по ≥3/4 окон + число сделок + красные месяцы. PF-выбросы (оверфит) — мимо.

## P0 — Alpaca $500 live (к открытию рынка)
Без изменений: dry-run `ALPACA_SEND_ORDERS=0` → пики/стопы/cap≤$500 → OWNER OK → SEND_ORDERS=1.
v38: PF 6.47, 9/11 зелёных, maxDD −3.86%. Это первый реальный плюс — приоритет.

## P1 — форекс honest pass
- lookahead-чек ВСЕХ ~20 стратегий (слайс candles[:i+1]); проверить `london_open_breakout`
  SMA[i] (жёлтый флаг из FOREX_AUDIT).
- добавить slippage в `forex/engine.py` (сейчас только разовый спред).
- честный WF range/bounce/mean-reversion с асимметр. R:R (tp∈{2,2.5,3}R, sl~1R), отбор по OOS.

## P1 — закоммитить набор Claude
adaptive_context, market_context апгрейды, render v2, ASB2/ACB1 adaptive, ARF2 fix,
strategy_breaker/volume_exit/carry_neutral + тесты, inplay_retest_v4, market_survey,
WF_AND_LIVE_HONEST_READ_2026_06_30_PM, этот queue.

## Вернуть в первую очередь
1) net-за-цикл carry ДО/ПОСЛЕ ре-гейта; 2) WF pair-arb; 3) Alpaca dry-run лог.

## ДОБАВЛЕНО 2026-06-30 (день, Claude, локально — без сервера)
- FOREX lookahead-чек ВСЕХ 18 стратегий: чисто, lookahead НЕ найден; london_breakout жёлтый флаг СНЯТ. См. reports/FOREX_LOOKAHEAD_FULL_AUDIT_2026_06_30.md. Остаётся Codex: slippage в forex/engine.py + WF.
- CARRY re-gate SPEC готов (привязан к коду): reports/CARRY_REGATE_SPEC_2026_06_30.md. Корень минуса = гейт кредитует полный APR на hold (фандинг затухает). Фикс: capture-haircut + эмпирич. deploy-гейт по arb_roi_estimate + full-funded both legs + delta-neutral. Внедрить — Codex.

## ДОБАВЛЕНО 2026-06-30 (range_filter wiring)
- НОВОЕ P1: подключить bot/range_filter.py ко всем bounce/fade ногам (крипто+форекс) по reports/RANGE_FILTER_WIRING_2026_06_30.md, убрать самодельные range-гейты, закоммитить модуль+тест, затем WF с асимметр R:R и require_all как параметром.

## ДОБАВЛЕНО 2026-06-30 (pump_exhaustion wiring)
- НОВОЕ P1: подключить bot/pump_exhaustion.py к pump_fade_simple/pump_fade_v2/pump_fade_v4r/pump_fade_smart_v1 и spike_fade — фейд только при short_ok/long_ok (подтверждённый разворот). Убрать старый вход-без-подтверждения. Закоммитить модуль+тест. Затем WF с асимметр R:R, отбор по OOS.

## ДОБАВЛЕНО 2026-06-30 (retest_quality wiring)
- НОВОЕ P1: подключить bot/retest_quality.py как общий грейдер ретеста к level-ногам (IRV4, support_bounce, channel_bounce, breakout-retest, forex retests). entry_ok/quality как гейт, long_ok/short_ok для сплита. Закоммитить модуль+тест. Затем WF.

## ДОБАВЛЕНО 2026-06-30 (elder_filter wiring)
- НОВОЕ P1: подключить bot/elder_filter.py как конфлюэнс-гейт ко всем рукавам (крипта+форекс). Рукав AND-ит свой сигнал с allow_long/allow_short. Закоммитить модуль+тест. В свипе require_with_tide как параметр (с тайдом vs не против тайда), отбор по OOS.

## ДОБАВЛЕНО 2026-06-30 (breakout + ночной деплой)
- НОВОЕ P1: подключить bot/breakout_confirm.py к пробойным ногам (confirmed long_ok/short_ok; ретест через retest_quality). Полный тёрнкей-план ночи: reports/DEPLOY_OVERNIGHT_2026_06_30.md (коммит 5 модулей -> wiring -> WF OOS асимметр R:R -> carry re-gate -> pair-arb WF -> Alpaca dry-run).

## ДОБАВЛЕНО 2026-07-01 (InPlay V4 реворк-спек)
- НОВОЕ P1: реворк InPlay V4 через helper-слои (не разморозка). reports/INPLAY_V4_REWORK_2026_07_01.md: Setup A -> retest_quality.score_retest (градуированный вход), Setup B -> breakout_confirm + ретест, конфлюэнс elder allow_long/short + range_filter, сплит сохранён. Свип IRV4_MIN_QUALITY/tp_rr/require_with_tide, отбор по OOS-плато, лестница валидации до canary.

## ДОБАВЛЕНО 2026-07-01 (OOS-selector в пайплайн)
- НОВОЕ P0: bot/oos_selector.py — прогонять результаты КАЖДОГО свипа через select_robust/evaluate_candidate; в canary только passes==True (robust_plateau). Закоммитить модуль+тест. Заменяет ручной отбор по in-sample пику.

## ДОБАВЛЕНО 2026-07-01 (level_entry в исполнение)
- НОВОЕ P1: bot/level_entry.py — планировщик maker-лимита У уровня. Подключить к level-ногам вместо market-входа по закрытию; в бэктестах использовать simulate_fill (честный maker-филл + validity). Закоммитить модуль+тест.

## ДОБАВЛЕНО 2026-07-01 (sizing + КРИТИЧНО про тесты)
- НОВОЕ P1: bot/position_sizing.py — единый sizer (fixed-R + бюджет + leverage-cap + vol-target). Подключить во все ноги.
- КРИТИЧНО: WF ДОЛЖЕН гонять РЕВОРКНУТЫЕ ноги (с range_filter/retest_quality/breakout_confirm/elder_filter/level_entry/position_sizing), иначе цифры = старая логика. В движке: maker-fill через level_entry.simulate_fill, sizing через position_sizing, отбор через oos_selector. Без этого "тест с учётом технологий" не выполнен.

## ДОБАВЛЕНО 2026-07-01 (decision_bus + CPCV)
- НОВОЕ P1: подключить bot/decision_bus.py — каждая нога пишет запись (helper-контекст+plan+outcome) в JSONL; summarize для ИИ-аналитика. P1: WF-харнесс -> purging+embargo (CPCV-lite) вместо вложенных окон.

## ДОБАВЛЕНО 2026-07-01 (H4-тест каскадов + purge/embargo)
- НОВОЕ P1: честный H4-тест через bot/cascade_reversal.py на MID-CAPS (SOL/AVAX/LINK/MATIC, НЕ BTC/ETH), реальные liq-данные коллектора, вход +2 бара, SL1/TP2 ATR, PF>1.3 -> canary $50. Реализовать purge+embargo в WF (gap>=max-hold). См. reports/DEEPSEEK_RESPONSE_ACTIONS_2026_07_01.md

## ДОБАВЛЕНО 2026-07-01 (edge_monitor)
- НОВОЕ P1: bot/edge_monitor.py — governor против деградации. Подключить: assess_all(decision_bus records, baselines) периодически -> degraded=throttle, halt=stop рукав. Baselines брать из WF-ожиданий. Часть champion/challenger цикла.

## ДОБАВЛЕНО 2026-07-01 (slippage + Mac-параллель)
- НОВОЕ P1: bot/slippage_model.py — писать live-fills (expected vs actual), калибровать по символу, кормить WF-движок (context inplay для каскадов/инплэя). P0-инфра: reports/RESEARCH_PARALLELIZATION_2026_07_01.md — Mac шардинг+caffeinate для H4-данных/WF параллельно.

## ДОБАВЛЕНО 2026-07-01 (trailing/liquidity/regime/checkpoint)
- НОВОЕ: trailing_stop -> подключить к элдеру/трендовым (breakeven+chandelier); liquidity_sweep -> охотник за ликвидностью (sweep-фейд vs break-follow); regime_hmm+regime_gate -> блок торговли в high_vol, risk_scalar; run_checkpoint -> ВСЕ длинные свипы оборачивать (caffeinate+screen+checkpoint) для устойчивости к сну Mac. Закоммитить 4 модуля+тесты.

## ДОБАВЛЕНО 2026-07-01 (InPlay gate FAIL -> next)
- InPlay V4 gate FAIL (2/4 фолда, N мал, fold3=1 сделка). НЕ canary. НЕ хоронить: фикс = РАСШИРИТЬ юниверс (больше mid-caps -> больше сделок -> стат.мощность) ИЛИ принять как редкий диверсификатор в мульти-ноге. Следующее: H4 cascade test на mid-caps (потенциально чаще/сильнее). Alpaca $500 = реальное семя.
- TG: gitignore+refresh stale reports/PROOF_OF_LIFE_*.txt (показывают bull_trend/flat/ivb1 — устарело); Alpaca-TG метить paper/dry-run.

## ДОБАВЛЕНО 2026-07-01 (preflight + runbook)
- НОВОЕ: bot/preflight_check.py — ОБЯЗАТЕЛЬНО прогонять ПЕРЕД любым OOS-gate (dry signal-run -> preflight -> GO/NO-GO). reports/RANGE_BOUNCE_EXECUTION_RUNBOOK_2026_07_01.md — довести ARF2/ASB2/ACB1: ARF2 на общий контракт -> pre-flight 4 сторон на 7-8 mid-caps -> gate только GO -> champion_challenger. Не запускать дорогие прогоны без GO.

## ДОБАВЛЕНО 2026-07-01 (unified_levels + sleeve_registry)
- НОВОЕ: bot/unified_levels.py — единый level-provider (все типы одним вызовом); подключить ко ВСЕМ ногам как источник уровней, ARF2 первым. bot/sleeve_registry.py — управлять рукавами как (strategy x side): side-specific stats/health/risk/lifecycle, демоут плохой стороны независимо. Регистрировать directional ноги через register_bidirectional.

## ДОБАВЛЕНО 2026-07-01 (DeepSeek hardening)
- PRE-FLIGHT: использовать обновлённый `bot/preflight_check.py` с quality sanity (`r/pnl_r/net_r` -> PF). `quality_pf <0.80` = NO-GO до дорогого OOS; 0.80..1.00 = caution.
- LEVELS: использовать обновлённый `bot/unified_levels.py` с lookback/max_age/merge/best_level. Не включать `liquidity` как полноценную heatmap: текущий тип = recent_extreme, годится только как слабый confluence.
- RANGE/BOUNCE: перед gate сделать ARF2 OLD vs NEW A/B и sequential filter analysis; если helper-фильтр режет >50% сигналов без улучшения PF/R, он не обязателен для этой ноги.
- H4: перед WF обязателен data-quality gate (liq/OI/funding coverage, OI approximation, 1m/5m aggregation, slippage/hybrid execution, crash-day stress).

## ДОБАВЛЕНО 2026-07-01 (ARF2 flag wiring)
- ARF2 уже получил флаги общего контракта, все OFF по умолчанию: `ARF2_USE_UNIFIED_LEVELS/RANGE_FILTER/RETEST_QUALITY/ELDER_FILTER/LEVEL_ENTRY`.
- Следующий шаг: A/B sequential dry-run по флагам, не OOS сразу. Порядок: OLD baseline -> +LEVEL_ENTRY -> +UNIFIED_LEVELS -> +RANGE_FILTER -> +RETEST_QUALITY -> +ELDER_FILTER. На каждом шаге: signal count, cheap PF/R, symbol coverage, filter drop rate.

## ДОБАВЛЕНО 2026-07-02 (smart_grid + orchestrator идея)
- НОВОЕ: bot/smart_grid.py — режим-осознанный сеточник (range-only + kill-switch на пробой). Прогнать через backtest/OOS как частый механич. рукав (кандидат «торгует каждый день»). Затем orchestrator: цикл decision_bus->regime_hmm->edge_monitor->champion_challenger->sleeve_registry для AI-supervised портфеля В РЕЛЬСАХ (риск/режим/цикл, НЕ live-оптимизация параметров).

## ДОБАВЛЕНО 2026-07-02 (gate threshold fix)
- НОВОЕ: ужесточить oos_selector в gate-скриптах под пре-регистрацию (min_trades_per_fold>=8, min_trades_total>=40, reject robustness<=0). InPlay wide gate PASS был маргинальный (fold 2-3 сделки) -> в shadow, не canary.

## ДОБАВЛЕНО 2026-07-02 (weekly orchestrator)
- НОВОЕ: bot/research_orchestrator.py — недельный ИИ-ревью (weekly_review->Proposal, format_proposal). Codex: scheduled раз/неделю -> собрать running sleeves (из decision_bus/edge_monitor) + новые кандидаты (из shadow-свипов) -> Proposal в TG на аппрув владельца. Ничего не авто-применять.
- smart_grid: поставить в backtest->preflight->OOS gate (кандидат «каждый день»).

## ДОБАВЛЕНО 2026-07-02 (smart_grid v2 + приоритеты)
- НОВОЕ: bot/smart_grid.py v2 fee-aware+strong-flat. Codex: обновить адаптер strategies/smart_grid.py под новый API (grid step_pct/n_levels/kill-flatten/мульти-ордер) и RE-TEST backtest. НО приоритет выше: (1) ARF2 exhaustion/failed-breakout rewrite, (2) ATT1 strict OOS перед повышением риска. Сетка — ниже (тяжёлый эдж). Alpaca $500 = ближайший real-money.

## ДОБАВЛЕНО 2026-07-02 (FX native — свипать)
- НОВОЕ: bot/fx_setups.py — 4 FX-сетапа под массовый свип на demo-данных (Dukascopy/yfinance/OANDA). Codex: свип символы×сторона×сессии×параметры -> preflight -> wf_folds -> oos_selector; что прошло -> shadow. XAU round_level_sweep + session_breakout_retest первыми. reports/FX_NATIVE_PACKAGE_2026_07_02.md

## ДОБАВЛЕНО 2026-07-02 (range_scanner + приоритеты)
- НОВОЕ: bot/range_scanner.py — подбор правильных инструментов для сетки/range-ног (scan/best_ranging). Сетку запускать ТОЛЬКО на top-tradeable флетах. Приоритет: (1) дождаться ATT1 revalidate -> strict rolling-OOS (первый реальный earner?), (2) ARF2 exhaustion, (3) FX harness+свип (XAU round-sweep+session breakout, + smart_grid по мажорам/золоту с range_scanner+side-split), (4) H4 real-data. Сетке добавить range_scanner фильтр перед свипом.

## ДОБАВЛЕНО 2026-07-02 (smart risk)
- НОВОЕ: bot/risk_manager.py — умный анти-мартингейл риск (regime/health/drawdown/vol scalars + hard-cap). Вписать поверх position_sizing во все ноги; ATT1 после rolling-OOS повышать риск через smart_risk, а не фикс процентом.

## ДОБАВЛЕНО 2026-07-02 (FX разблокирован — параллельный трек)
- НОВОЕ: bot/fx_harness.py готов. FX БОЛЬШЕ НЕ В КОНЦЕ. Параллельно с ATT1 rolling-OOS: подать реальные FX-данные (EURUSD/GBPUSD/USDJPY/GBPJPY/XAUUSD) в fx_harness, свипать 4 fx_setups + smart_grid(мажоры/золото, side-split, range_scanner) -> preflight -> wf_folds -> oos_selector. XAU round_sweep + session_breakout первыми. Demo/zero-risk.

## ДОБАВЛЕНО 2026-07-02 (ATT1 r001 миграция)
- P0: мигрировать ATT1 canary на r001-геометрию (точные params из strict-grading r001 ranked), риск ОСТАВИТЬ 0.10, breaker+expiry как есть. Деплой после OK владельца. НЕ поднимать риск при миграции. reports/ATT1_R001_MIGRATION_DECISION_2026_07_02.md
- Далее: 10-20 live healthy -> smart_risk ramp. Параллельно FX harness real-data + ARF2 exhaustion.

## ДОБАВЛЕНО 2026-07-02 (ARF2 exhaustion через failed_breakout)
- НОВОЕ: bot/failed_breakout.py — логика для ARF2 rewrite. ARF2: фейд ТОЛЬКО при failed_breakout.short_ok/long_ok (не «at resistance») + range_filter + level_entry -> preflight -> wf_folds -> oos_selector. Side-split. Следующий крипто-кандидат после ATT1 r001.
