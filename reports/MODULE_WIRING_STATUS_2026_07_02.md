# Статус вписывания модулей — построено vs подключено (2026-07-02, Claude)

Честный факт: построено 24 модуля (244 юнит-теста), но реально ВПИСАНЫ в ноги только 2
стратегии (inplay_retest_v4, ARF2) + limit-логика в portfolio_engine. Остальное лежит
провалидированным на уровне юнитов, но НЕ в торговле/управлении. ВЫВОД: стройку ставим на
паузу, приоритет = wiring + прогон через гейты. Ниже backlog для Codex.

## Вписано (в стратегии/движок)
- level_entry, retest_quality -> inplay_retest_v4 (gate FAIL по частоте; wide gate идёт).
- range_filter, retest_quality, level_entry, elder_filter, unified_levels, breakout_confirm
  -> ARF2 (за флагами; NO-GO, нужна логика exhaustion/failed-breakout).
- portfolio_engine: pending limit-fill (для level_entry). ЧЕСТНО, без lookahead (проверено).

## НЕ вписано (юнит-тесты есть, в торговле/управлении нет) — backlog
Детекторы-рукава (нужна нога + preflight + gate):
- smart_grid — новый частый механич. рукав (range-only). Прогнать backtest/OOS ПЕРВЫМ (кандидат «каждый день»).
- cascade_reversal (H4) — ждёт реальные liq/OI/funding (сервер).
- liquidity_sweep — охотник за ликвидностью; вписать в ногу + gate.
- pump_exhaustion — fade пампа после разворота; в pump_fade ноги + gate.
- breakout_confirm — расширить на пробойные ноги (сейчас только ARF2 как confluence).
Управляющий слой (нужен orchestrator + live-loop):
- decision_bus — каждая нога должна писать записи (сейчас не пишет в live).
- edge_monitor, champion_challenger, sleeve_registry — не в live-петле; обернуть портфель.
- regime_hmm — гейт/риск-скейл по режиму; вписать поверх ног.
- news_session_filter — в FX-ноги (когда появятся).
Риск/издержки:
- position_sizing, exposure_gate, slippage_model, trailing_stop — вписать в движок/риск-менеджер
  (сейчас движок считает qty по-своему; trailing частично есть в Position).
Инструменты (не для live, для процесса):
- oos_selector, wf_folds — используются в gate-скриптах (ОК).
- preflight_check — ОБЯЗАТЕЛЬНО перед каждым дорогим gate (не пускать пустые прогоны).
- run_checkpoint — оборачивать длинные прогоны.

## Приоритет wiring (по шансам на заработок/частоту)
1. smart_grid -> backtest -> preflight -> OOS gate (частый, «каждый день»).
2. InPlay V4 wide gate (идёт) -> вердикт.
3. ARF2 логика exhaustion/failed-breakout -> заново (не грид, а логика).
4. liquidity_sweep + H4 (когда данные) — механика.
5. Управляющий orchestrator (decision_bus->regime->edge_monitor->champion_challenger) — когда ≥1 рукав живой.

## Правило
НЕ строить новые модули, пока эти не вписаны и не прогнаны. Built >> validated — закрываем разрыв.
