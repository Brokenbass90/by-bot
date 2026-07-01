# Интеграционный референс — как модули соединяются в ОДНОЙ ноге (2026-07-01)

Чтобы Codex вписал 19 технологий ЕДИНООБРАЗНО во все ноги, а не по-разному. Это
канонический конвейер решения. Каждый шаг — гейт: не прошёл -> no_signal + decision_bus.

## Порядок вызовов в maybe_signal(rows, ...) любой directional-ноги
```
1. regime = regime_hmm.regime_probs(rows, prior=prev_regime)
   g = regime_hmm.regime_gate(regime)               # high_vol -> стоп
   if not g["allow"]: -> skip("blocked_regime"); risk_scalar = g["risk_scalar"]

2. СИГНАЛ НОГИ (сторона + уровень). Источник уровня по типу ноги:
   - bounce/fade:  retest_quality.best_retest(rows)         -> level, side, entry_ok
   - пробой:       breakout_confirm.breakout_confirm(rows)  -> confirmed, side
   - охотник ликв: liquidity_sweep.liquidity_sweep(rows)    -> sweep_reversal/break_hold, side
   - пампы:        pump_exhaustion.impulse_exhaustion(rows) -> confirmed, side
   - каскады H4:   cascade_reversal.cascade_reversal(rows,funding,oi,liq) -> long/short_ok
   if not side_ok: -> skip(reason)

3. РЕЖИМ-КОНТЕКСТ фейд-ног: range_filter.range_state(rows)
   bounce/fade торгует только при is_range ИЛИ свежий сильный уровень.

4. КОНФЛЮЭНС: elder = elder_filter.elder_bias(rows, htf_rows)
   long только если elder.allow_long; short только если elder.allow_short.

5. ФОРЕКС: news_session_filter.entry_allowed(ts, events, price)
   if not allow: -> skip("news_blackout"/"low_liq_session").

6. ВХОД: plan = level_entry.plan_level_entry(rows, level, side)   # maker-лимит У уровня
   if not plan.place: -> skip("would_chase"/...); стоп = plan.stop (тайт, ~1R).

7. РАЗМЕР: size = position_sizing.plan_size(equity, plan.limit_price, plan.stop,
             risk_pct=base*risk_scalar, atr_pct=..., open_risk_pct=..., ...)
   if not size.place: -> skip("budget/leverage").

8. КОРРЕЛЯЦИЯ: exp = exposure_gate.check_exposure({symbol,side,risk_pct:size.risk},
             open_positions, correlations)
   if not exp.allow: -> skip; risk = exp.scaled_risk_pct (может урезать).

9. ЗАПИСЬ: decision_bus.build_decision(...,range_state,retest,elder,breakout,exposure,size,entry=plan)
   -> append в JSONL (и enter, и skip — для ИИ и meta).

10. УПРАВЛЕНИЕ ПОЗИЦИЕЙ (после входа):
    trailing_stop.update_trail(pt, high, low, atr) каждый бар -> breakeven+chandelier.
    volume_exit / strategy_breaker — как есть.
```

## Бэктест/WF (движок)
- Филл: level_entry.simulate_fill (maker) + slippage_model.estimate_bps(context="inplay" для каскадов).
- Исход сделки -> decision_bus.attach_outcome(r_multiple).
- Фолды: wf_folds.purge_embargo_folds -> oos_selector.select_robust (только robust_plateau).
- Лайв-здоровье: edge_monitor.assess_all(decision_bus) -> champion_challenger (промоушен/демоут).
- Длинные прогоны: run_checkpoint + caffeinate + screen.

## Инвариант
Каждый рукав ОДНОНАПРАВЛЕН (long_ok XOR short_ok на каждом слое). Уровни — наклонные
И горизонтальные (market_context). ИИ видит всё через decision_bus. Отбор — только OOS.
