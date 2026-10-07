# INVENTAR_SISTEM — основа бота: вспомогательные системы по слоям Trading OS v2 (07.10, Claude)

Источник: `bot/` (141 модуль). «LIVE» = импортируется живым ботом `smart_pump_reversal_bot.py` (контур Codex; Claude не трогает).
«ref» = на модуль ссылаются research/scripts. Решение по каждому: ВЗЯТЬ (в OS v2 как есть) / ПРОВЕРИТЬ (сначала тест/история) / АРХИВ.
Правило: ничего не переписываем с нуля, пока существующее не проверено.

## L2 Режим рынка (кандидаты для B2 — выбирается ОДИН основной до прогона)
| модуль | что определяет | статус | решение |
|---|---|---|---|
| research_lab/orchestrator.py (regime_name) | BTC H1: отклонение от EMA200 — тренд−/флет−/флет+/тренд+ (±2%) | тестировался 08.2026 (исходы ATT1/SBR1 по нему уже видели) | кандидат B2 №1 (простой, есть история) |
| bot/regime_orchestrator.py (406) | BTC 4h: MACD-hist ≥3 бара + EMA20/50 → BULL_TREND/BEAR_TREND/NEUTRAL; пишет runtime/regime.json + overrides по стратегиям | не LIVE, тестов нет | кандидат B2 №2; нужен тест |
| docs/REGIME_ORCHESTRATOR_SPEC_20260402.md | 4 режима bull_trend/bull_chop/bear_chop/bear_trend: 4h EMA21/55 + ER (эффективность хода) + ширина рынка | спецификация, полного кода нет | кандидат B2 №3 (лучше всего совпадает с целью) |
| bot/regime_hmm.py (126) | bull/bear/range/high_vol, «липкие» вероятности, гейт high_vol | не LIVE, тест есть | кандидат B2 №4 / оверлей волатильности |
| bot/live_native_regime_gate.py, regime_side_gate.py (LIVE), strategy_regime_gate.py (LIVE) | потребители режима: разрешить/запретить сторону/ногу, fail-closed | LIVE (breakdown gate) | ВЗЯТЬ как исполнитель решений оркестратора |
| bot/market_context.py (436), adaptive_context | уровни/линии/VWAP/HVN (контекст сетапа, не режим) | ref 11 | ВЗЯТЬ для ног (L1) |

## L3 Оркестратор / портфель / риск
| модуль | что делает | статус | решение |
|---|---|---|---|
| bot/strategy_priority_router.py (175) | детерминированный роутер: ранжирует готовые кандидаты, ограниченные слоты, риск не повышает; режим money требует money_authorized | не LIVE, тест есть | ВЗЯТЬ — ядро L3 |
| bot/exposure_gate.py (114) | не задваивать коррелированные ставки | не LIVE, тест | ВЗЯТЬ (корреляция/экспозиция) |
| bot/sleeve_registry.py, strategy_catalog.py | реестр рукавов (стратегия × сторона) | не LIVE, тест | ВЗЯТЬ, связать с os2/INVENTAR_NOG |
| bot/portfolio_health.py, portfolio_equity_guard.py | здоровье портфеля, страж эквити | LIVE | ВЗЯТЬ |
| bot/circuit_breaker.py, strategy_breaker.py, live_loss_cooldown.py, entry_guard.py | аварийные остановы / паузы после убытков | LIVE | ВЗЯТЬ (аварийный стоп по CEL_SISTEMY) |
| bot/risk_sizing_contract.py (LIVE), position_sizing, risk_manager, confidence_risk, dd_throttle | размер позиции, снижение при просадке | частично LIVE | ПРОВЕРИТЬ: рост риска автоматом запрещён |

## L4 Исполнение (контур Codex)
maker_execution / maker_entry / order_link / tpsl_policy (LIVE); limit_execution, level_entry, trailing_stop, slippage_model,
position_reconciliation, smart_grid — инструменты. Claude не трогает; слиппедж-модель берём в бэктест B3.

## L5 Журнал решений и монитор edge
| модуль | что делает | статус | решение |
|---|---|---|---|
| bot/decision_bus.py (200) | след каждого решения | LIVE, флаги по умолчанию OFF (att1_live_wiring) | ВЗЯТЬ — центр L5; включение — Codex |
| bot/edge_monitor.py, edge_canary.py | распад edge онлайн | LIVE (ATT1), флаги OFF | ВЗЯТЬ + страж fabrika/strazh_kity.py (советник) |
| bot/strategy_shadow_ledger.py (LIVE), strategy_health_timeline.py | тени и таймлайн здоровья ног | LIVE/ref | ВЗЯТЬ |
| bot/champion_challenger.py (107) | промоут/демоут по A/B | не LIVE, тест | ВЗЯТЬ для L5/L7 (решение → GO владельца) |
| bot/health_gate.py, health_truth.py (LIVE), diagnostics | здоровье данных/процессов | LIVE | ВЗЯТЬ (источник аварийного стопа) |

## L6–L7 Лаборатория и ИИ
| модуль | что делает | статус | решение |
|---|---|---|---|
| bot/wf_folds.py, oos_selector.py, loso_concentration.py, preflight_check.py, run_checkpoint.py | purge+embargo WF, отбор по плато, концентрация, переживание сна Mac | ref, тесты | ВЗЯТЬ в B3 (wf_folds — сгибы) |
| bot/research_orchestrator.py (103) | еженедельный Proposal на аппрув | не LIVE, тест | ВЗЯТЬ для L7 |
| bot/deepseek_overlay / deepseek_operator (LIVE: OPERATOR_ENABLE=True по умолчанию, USE_API=False, TRADE_REVIEW=False), deepseek_action_executor, deepseek_autoresearch_agent | ИИ-оператор в живом боте | LIVE-импорт | **ПРОВЕРИТЬ (Codex): может ли action_executor менять .env/риск без GO** — по CEL_SISTEMY ИИ только предлагает |
| bot/ai_context, ai_trade_mission, trade_learning_loop | контекст/миссии/обучение по сделкам | частично LIVE | ПРОВЕРИТЬ |

## L1 Детекторы сетапов (для ног, не для режима)
range_filter, range_scanner, failed_breakout, structure_break, breakout_confirm, retest_quality, liquidity_sweep, pump_exhaustion,
cascade_reversal, elder_filter, level_memory, unified_levels, liquidity_map, chart_geometry, geometry_cache — ВЗЯТЬ как библиотеку;
технология добавляется к ноге только по A/B на OOS (правило MASTER_MAP 07.2026).

## Прочее
FX (fx_*), Alpaca (alpaca_*), cash-carry (bybit/bitget/public_cashcarry_*), event_* — по своим дорожкам; в OS v2 V1 не входят.

## Проверка 07.10 (что реально работает)
Тесты 20 модулей управления: **133 PASS** (`python3 -m pytest -q -p no:cacheprovider tests/test_{champion_challenger,confidence_risk,dd_throttle,decision_bus,edge_monitor,exposure_gate,live_native_regime_gate,oos_selector,portfolio_equity_guard,portfolio_health,position_sizing,regime_hmm,regime_side_gate,risk_manager,sleeve_registry,strategy_breaker,strategy_priority_router,strategy_regime_gate,wf_folds,health_gate_freshness}.py`).
test_sleeve_breaker_generic не собирается в исследовательской VM (импортирует живой бот, нужен websockets) — проверяет Codex.
bot/regime_orchestrator.py своих тестов не имел → покрыт os2/test_rezhim_v1.py (детерминизм, причинность, прогрев, замок истории).
scripts/build_regime_state.py (V2 4-режимный, гистерезис 3) — существующий исполнимый код; в B2 не прошёл K3 (доля пил 58%).

## Карта соединений (что есть → чего не хватает)
| связь | есть | не хватает |
|---|---|---|
| режим → оркестратор | REZHIM_V1 (замок), regime_orchestrator пишет runtime/regime.json | исследовательская метка = живая метка: Codex сверяет compute_regime на одних барах |
| ноги → кандидаты роутера | StrategyCandidate/rank_candidates; os2/replay.py уже кормит роутер потоками | живые ноги не публикуют кандидатов в роутер (сейчас каждая решает сама) |
| роутер → исполнение | strategy_regime_gate/regime_side_gate в LIVE (fail-closed) | один вход «разрешение оркестратора» для всех рукавов, а не флаги по стратегиям |
| исполнение → журнал | decision_bus (LIVE, флаг OFF) | включить в тени/PAPER; поля: режим, решение роутера, причина |
| журнал → монитор edge | edge_monitor (ATT1), strategy_health_timeline, страж KITY | общий монитор по всем рукавам на decision_bus |
| монитор → улучшение | champion_challenger, research_orchestrator (тесты есть) | не подключены; решение — только GO владельца |
| ИИ-оператор | deepseek_operator ON по умолчанию (API OFF), action_executor импортирован | **проверка Codex: не может ли менять .env/риск/стратегии без GO** |
