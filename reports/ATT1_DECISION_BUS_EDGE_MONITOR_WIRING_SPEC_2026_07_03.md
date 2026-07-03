# СПЕК: wiring decision_bus + edge_monitor в ATT1-ногу (2026-07-03, Claude -> Codex)

Цель: живая канарейка ATT1 с первого дня пишет ПОЛНУЮ атрибуцию решений (decision_bus)
и находится под онлайн-надзором здоровья (edge_monitor). Это фундамент Ф3/Ф4: без этих
данных мы не сможем доказательно улучшать винрейт технологиями. Качество > скорость:
всё за флагами, с тестами, деплой только после OK владельца.

## Принципы (рельсы)
- v1 = НАБЛЮДЕНИЕ: decision_bus пишет, edge_monitor оценивает и алертит в TG.
  НИКАКИХ авто-действий по риску в v1 — единственный автостоп остаётся ATT1-breaker
  (уже в бою). Двойную автоматику не городим, иначе не поймём, кто из них сработал.
- Существующий _append_signal_decision (signal trace JSONL) НЕ трогаем и НЕ заменяем —
  он для live-vs-backtest parity. decision_bus — отдельный, более богатый контракт.
- Ошибка записи в bus НИКОГДА не блокирует торговлю (try/except + log_error, как в trace).

## 1. decision_bus в ATT1-ногу (smart_pump_reversal_bot.py, обработчик ~10510-10700)

Флаги env:
- ATT1_DECISION_BUS_ENABLE (bool, default 0) — включаем после деплоя и OK владельца.
- DECISION_BUS_PATH (default runtime/decision_bus.jsonl) — с ротацией по размеру,
  как SIGNAL_DECISION_TRACE_MAX_BYTES (тот же паттерн ротации .1).

Что писать (bot.decision_bus.build_decision -> DecisionBus.append):
a) decision="skip" в КАЖДОЙ точке отказа ПОСЛЕ появления сигнала (не на no_signal —
   иначе зальём файл; no_signal остаётся в trace):
   skip_rounding, skip_breaker (reason из breaker.reason), skip_notional_small,
   skip_minqty, skip_open_risk, skip_symbol_lock, skip_reserve, shadow_signal.
b) decision="enter" при постановке ордера (точка tr.strategy="att1_trendline_touch",
   ~10692), с контекстом:
   - side, signal_strength (если есть у sig), timeframe
   - extra: {"regime": ORCH_REGIME, "breaker_mult": breaker_mult,
             "effective_risk_mult": effective_att1_risk_mult,
             "minqty_fallback": bool(использован fallback),
             "fallback_stretch": notional_real/dyn_usd если fallback, иначе 1.0,
             "stop_pct": stop_pct, "open_trades": n}
   - plan: entry/stop/tp из sig (поля есть: sig.entry/sig.sl/sig.tp)
   ВАЖНО: minqty_fallback/fallback_stretch обязательны — это ответ на вопрос
   «насколько горячее номинала бежит канарейка» (аудит 07-03: cap 1.8x).
c) outcome на закрытии: в точке _db_log_event("CLOSE", ...) (~7345), только для
   tr.strategy == "att1_trendline_touch": attach_outcome(filled=True,
   r_multiple=pnl_closed/риск_сделки_в_USDT, pnl=pnl_closed, exit_reason=_close_r).
   r_multiple считать от ФАКТИЧЕСКОГО риска (|entry-sl|*qty), не от номинального —
   иначе fallback-сделки исказят R-статистику.
   Реализация связки: хранить decision_id (ts+symbol) в tr (новое поле tr.bus_id),
   на close перечитывать не надо — писать ОТДЕЛЬНУЮ outcome-запись с тем же bus_id
   (append-only, join по bus_id при анализе; не редактируем историю).

## 2. edge_monitor поверх ATT1 (периодическая оценка)

Флаги env:
- ATT1_EDGE_MONITOR_ENABLE (bool, default 0)
- ATT1_EDGE_BASELINE_EXPECTANCY_R (default 0.054) — из fee-stress 10/5bps:
  +16.53R / 307 сделок (КОНСЕРВАТИВНАЯ база, не 6/2bps). Источник:
  reports/ATT1_SHORT_FEE_STRESS_2026_07_02.md.
- Пороги = дефолты assess_sleeve: min_trades=20, decay_ratio=0.5, max_dd_R=6.0,
  max_losing_streak=8. НЕ менять без пре-регистрации.

Где крутить: в heartbeat-цикле (~15100, рядом с strategy-stats pulse), раз в
EDGE_MONITOR_INTERVAL_SEC (default 3600):
- читать R-мультипли закрытых att1_trendline_touch из trades.db (CLOSE-события,
  r от фактического риска — тот же расчёт, что в п.1c),
- assess_sleeve(...) -> писать HealthReport в runtime/att1_edge_health.json
  (+ в bot_heartbeat.json компактно: status/n/expectancy/reason),
- при смене status (healthy->watch/degraded/halt) — TG-алерт (throttled, cooldown
  30 мин, паттерн tg_trade_throttled).
- status=halt в v1 = ГРОМКИЙ алерт владельцу + Claude, НЕ авто-стоп (breaker сам
  остановит по своим порогам; сверим, кто сработал раньше — это данные).

## 3. Тесты (обязательны, паттерн существующих)
- test_att1_decision_bus_wiring.py:
  * enter-запись содержит effective_risk_mult/minqty_fallback/plan;
  * skip_breaker пишет reason breaker'а;
  * outcome-запись join'ится по bus_id и r_multiple считан от фактического риска;
  * при ATT1_DECISION_BUS_ENABLE=0 — ни одной записи;
  * сломанный путь (нет прав на файл) НЕ роняет обработчик (торговля продолжается).
- test_att1_edge_monitor_loop.py:
  * n<20 -> watch/insufficient;
  * синтетическая просадка 6R -> halt + алерт-хук вызван;
  * baseline из env подхватывается;
  * при ENABLE=0 ничего не пишется.

## 4. Приёмка и деплой
1) Тесты зелёные локально (вся сетка, не только новые).
2) Деплой на сервер с флагами =0 (мёртвый код), рестарт, сутки стабильности.
3) OK владельца -> включить оба флага -> проверить: первая же skip/enter запись
   появилась в runtime/decision_bus.jsonl, health в heartbeat.
4) Rollback = выключить флаги (кода не касаемся).

## 5. Что НЕ делаем в v1 (чтобы не расползтись)
- Не подключаем decision_bus к другим ногам (они без риска — пустые данные).
- Не даём edge_monitor крутить риск (это smart_risk, отдельный шаг после 10-20 сделок).
- Не строим дашборды — JSONL+heartbeat достаточно, research_orchestrator прочитает.
