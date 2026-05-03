# Code Review — alt_liquidity_sweep_reversal_v1
**Дата:** 2026-05-03
**Автор:** Claude
**Версия Codex:** v1 (252 строки, написан 30 апреля)
**Smoke results:** strict 30d=0 trades, relaxed 90d 49 trades PF=0.7 net=−2.53%

## Что хорошо ✅

1. **Pool detection корректный.** `pool = candles[i - lookback_bars : i]` — НЕ включает текущий бар, это правильно для anti-repaint и для sweep detection: если текущий бар пробивает min/max, то именно он будет «sweep'ом».
2. **Sweep + reclaim + rejection wick — классическая ICT/SMC логика.** Все три условия проверяются:
   - `sweep_atr ∈ [min, max]` — пробитие должно быть значимым, но не gap'ом
   - `c >= pool_low + reclaim_atr*atr` — реально закрылись внутри
   - `wick >= max(min_reject_wick_atr*atr, min_wick_to_body*body)` — нужен явный отказ
3. **EMA-gap filter `max_ema_gap_atr`** — защита от чрезмерно растянутых трендов, где fade рискован.
4. **Volume-confirmation** — `cur_vol/avg_vol >= min_vol_mult`. Стандартно.
5. **Body limit `max_body_atr`** — защита от gap-сделки.
6. **SL/TP correct math** — SL за свип-фитиль с pad'ом, TP по RR. Risk validation `risk > 0 and risk <= max_risk_atr*atr` — есть.
7. **Symmetry long/short** — обе ветки одинаковые по структуре, разница только в направлении.

## Что вызывает вопросы ⚠️

### 1. `low_touches` / `high_touches` неинформативные при `min_pool_touches < 3`
```python
high_touches = sum(1 for x in pool if abs(float(x.h) - pool_high) <= cfg.pool_touch_atr * atr)
```
`pool_high = max(...)` — сам этот максимум всегда попадает в touches. То есть `min_pool_touches=2` фактически означает «всего 1 дополнительный touch». В случайных шумовых барах это банально срабатывает — pool «детектится» там, где его нет.

**Fix:** убрать сам экстремум из счёта или поднять `min_pool_touches=3+` дефолтом. Или считать touches только в окне ±N баров от того бара, что задал экстремум.

### 2. Cooldown — global per-instance, не per-symbol (потенциально)
```python
self._last_signal_i = -10**9
...
if i - self._last_signal_i < cfg.cooldown_bars:
    self.last_no_signal_reason = "cooldown"
```
Если этот класс инстанциируется как **один instance на все символы** (типично для нашего bot loop, надо проверить bot/symbol_state и `BreakdownLiveEngine` и иже), то после одного сигнала на BTC стратегия молчит на ВСЕХ остальных символах в течение `cooldown_bars*5m = 2 часа` (default 24).

**Это критически режет частоту.** Это объясняет 49 сделок за 90d × 3 символа: ~5 сделок в неделю на 3 символа = чрезмерно тонко.

**Fix:** держать `dict {symbol → last_signal_i}` вместо одной переменной. Или вынести cooldown на bot-level (как в других стратегиях через `_throttle_gate`).

### 3. Нет regime gate
Стратегия работает в любом режиме. Логика sweep+reclaim наиболее полезна в `bear_chop`/`bull_chop`. В сильных трендах (`bear_trend`/`bull_trend`) свипы не fade'ятся, а продолжаются.

**Fix:** добавить `LQH_REGIME_MODE` env, по умолчанию `chop_only` — пускать только когда orchestrator говорит chop.

### 4. Нет partial TP / trailing
`tp = entry + RR*risk` — full position one-shot. У других стратегий (ATT1, ARF1) есть `TP1_FRAC`, partial fills, breakeven trigger. Это даёт +5-10% PF на тех же сигналах.

**Fix:** добавить `LQH_TP1_RR=0.8 LQH_TP1_FRAC=0.5` (50% при +0.8R) + `LQH_TRAIL_AFTER_TP1=1`.

### 5. Sweep_atr range слишком уже
`min_sweep_atr=0.10, max_sweep_atr=0.90` — пробитие от 0.1 до 0.9 ATR. Reality: реальные stop-hunt-свипы часто 0.3-1.5 ATR. Default range отрезает крупные «панические» свипы, которые часто и есть лучшие entry.

**Fix:** `max_sweep_atr=1.5` дефолтом, или sweep делить на 2 sub-сигнала: `tight_sweep` (0.1-0.5) и `panic_sweep` (0.5-1.5) с разными pool_touches требованиями.

### 6. Pool width vs ATR — слабая защита
`min_pool_width_atr=1.2` — pool должен быть шириной минимум 1.2 ATR. Это исключит маленькие консолидации, но в bull/bear trend всё равно подпустит pool, который фактически уходит в trend, не chop.

**Fix:** добавить «pool persistence»: проверка что pool существует не менее N баров (не только что появился), плюс horizontal slope checking (что pool reasonably horizontal).

## Что я бы предложил для v2

```python
# strategies/alt_liquidity_sweep_reversal_v2.py
# Diff from v1:
# 1. Per-symbol cooldown
# 2. Regime gate (chop_only default)
# 3. TP1 partial + breakeven + trailing
# 4. min_pool_touches=3 default
# 5. max_sweep_atr=1.5 default + panic_sweep mode
# 6. pool_persistence_min_bars=10 default
# 7. HTF confirmation: 1h candle close back inside pool
```

И сразу запустить **autoresearch sweep** на 360d по 200+ комбинациям — не угадывать параметры, а найти их. Создаю spec для ночи (см. ниже).

## Что НЕ делать

- Не пускать в live до WF-22 + portfolio additivity vs canary v2.1
- Не строить liquidation-cascade интеграцию пока edge не доказан на чистом OHLCV
- Не trust standalone PF без proper out-of-sample test

## Время

- v2 strategy patch: 1-2 часа моей работы
- Autoresearch v2 sweep: 30-60 мин (200+ runs параллельно на сервере)
- WF-22 + additivity: ещё 2-3 часа Codex'у на сервере

## Acceptance gate

Стандартный (как у Pair 1-2):
- standalone 360d: PF ≥ 1.20, DD ≤ 10%, net ≥ +5
- WF-22: ≥ 13/22 окон pass
- portfolio additivity vs canary v2.1: net ≥ baseline, DD ≤ +1.5pp
- 1 неделя shadow в live до риска
