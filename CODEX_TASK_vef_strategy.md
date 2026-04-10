# Codex Task: alt_volume_exhaust_fade_v1 (AVEF1)

## Суть стратегии

**Volume Exhaustion Fade** — фейд объёмного взрыва. Когда рынок делает резкое движение
с аномальным объёмом (3.5× выше среднего), участники, которые купили/продали на панике,
начинают закрывать позиции. Цена откатывает обратно на 40-60% от взрыва.

В отличие от IVB1 (покупает в направлении импульса), AVEF1 **торгует против**:
- Pump с объёмом → шорт
- Dump с объёмом → лонг

Работает в **любом режиме** — объёмные взрывы происходят всегда.

---

## Файлы для создания

### 1. `strategies/alt_volume_exhaust_fade_v1.py`

Создать по образцу `strategies/impulse_volume_breakout_v1.py`. Структура:
- `@dataclass class AltVolumeExhaustFadeV1Config`
- `class AltVolumeExhaustFadeV1Strategy` с методом `maybe_signal()`
- Константа `STRATEGY_NAME = "alt_volume_exhaust_fade_v1"`

---

## Полная логика стратегии

### Таймфрейм

- Основной: **15m** (env key `AVEF1_ENTRY_TF`, default `"15"`)
- Объём: скользящее среднее `SMA(volume, 20)` на тех же 15m барах

### Машина состояний (per-symbol)

```
IDLE → SPIKE_DETECTED → EXHAUSTION → IN_TRADE → COOLDOWN → IDLE
```

- **IDLE**: ищем объёмный взрыв
- **SPIKE_DETECTED**: зафиксировали взрыв, ждём подтверждение истощения (max 3 бара)
- **EXHAUSTION**: сигнал есть, выставляем ордер
- **IN_TRADE**: в позиции, управляем стопом
- **COOLDOWN**: после закрытия, N баров паузы

### Шаг 1: Обнаружение взрыва (переход IDLE → SPIKE_DETECTED)

Условия **одновременно**:
```python
# Объём
vol_spike = current_volume > AVEF1_VOL_SPIKE_MULT * sma_volume_20  # default 3.5

# Размер тела (настоящий импульс, не шум)
body = abs(close - open)
bar_range = high - low
body_frac = body / max(bar_range, 1e-12)
real_impulse = body_frac >= AVEF1_MIN_BODY_FRAC  # default 0.60

# Минимальный ход цены
price_move_pct = body / max(open, 1e-12)
min_move = price_move_pct >= AVEF1_MIN_MOVE_PCT  # default 0.010 (1.0%)

# ATR фильтр — взрыв должен быть значимым
bar_range_vs_atr = bar_range / max(atr14, 1e-12)
atr_ok = bar_range_vs_atr >= AVEF1_MIN_RANGE_ATR  # default 1.5
```

При срабатывании записать:
```python
spike_data = {
    "direction": "up" if close > open else "down",
    "spike_open": open,
    "spike_close": close,
    "spike_high": high,
    "spike_low": low,
    "spike_body": body,
    "spike_ts": ts,
    "wait_bars": 0,
    "atr": atr14,
}
```

### Шаг 2: Подтверждение истощения (SPIKE_DETECTED → EXHAUSTION или IDLE)

На каждом следующем баре (максимум `AVEF1_MAX_WAIT_BARS=3`):

**Для SHORT entry (spike_direction == "up"):**
```python
# Хотя бы ОДНО из:
exhaust_ok = any([
    # 1. Бар закрылся ниже open спайка (разворот)
    close < spike_data["spike_open"],
    # 2. Дожи / нерешительность (маленькое тело)
    abs(close - open) / max(bar_range, 1e-12) < 0.30,
    # 3. Верхний хвост > 50% диапазона (rejection)
    (high - max(open, close)) / max(bar_range, 1e-12) > 0.50,
])
# И RSI не глубоко в oversold (нет смысла шортить то что уже упало)
rsi_ok = rsi14 >= AVEF1_RSI_SHORT_MIN  # default 52
```

**Для LONG entry (spike_direction == "down"):**
```python
exhaust_ok = any([
    # 1. Бар закрылся выше open спайка
    close > spike_data["spike_open"],
    # 2. Дожи
    abs(close - open) / max(bar_range, 1e-12) < 0.30,
    # 3. Нижний хвост > 50% (hammer)
    (min(open, close) - low) / max(bar_range, 1e-12) > 0.50,
])
rsi_ok = rsi14 <= AVEF1_RSI_LONG_MAX  # default 48
```

Если за MAX_WAIT_BARS подтверждение не пришло → вернуться в IDLE.

### Шаг 3: Вычисление уровней

**SHORT (фейд апп-спайка):**
```python
entry_price = close  # рыночный вход при закрытии exhaust бара

# Стоп — выше хая спайка
sl_price = spike_data["spike_high"] + AVEF1_SL_BUFFER_ATR * atr14  # default 0.4

# TP — 50% ретрейс тела спайка от spike_close вниз
retrace_target = spike_data["spike_close"] - AVEF1_TP_RETRACE * spike_data["spike_body"]  # default 0.55
# Но не дальше 1.5×ATR от entry
tp_by_atr = entry_price - AVEF1_TP_ATR * atr14  # default 1.5
tp_price = max(retrace_target, tp_by_atr)  # берём ближний

# Проверка RR минимум
rr = (entry_price - tp_price) / max(entry_price - sl_price, 1e-12) -- нет, это неверно
# Правильно:
risk = sl_price - entry_price  # для шорта risk = sl выше entry
reward = entry_price - tp_price
rr_actual = reward / max(risk, 1e-12)
if rr_actual < AVEF1_MIN_RR:  # default 1.2
    return None  # отказ от сигнала
```

**LONG (фейд даун-спайка):**
```python
entry_price = close
sl_price = spike_data["spike_low"] - AVEF1_SL_BUFFER_ATR * atr14
retrace_target = spike_data["spike_close"] + AVEF1_TP_RETRACE * spike_data["spike_body"]
tp_by_atr = entry_price + AVEF1_TP_ATR * atr14
tp_price = min(retrace_target, tp_by_atr)
risk = entry_price - sl_price
reward = tp_price - entry_price
rr_actual = reward / max(risk, 1e-12)
if rr_actual < AVEF1_MIN_RR:
    return None
```

### Шаг 4: Режимный фильтр

```python
def _direction_allowed(self, direction: str, regime: str) -> bool:
    """
    bull_trend  → только LONG (фейдим дампы на тренде)
    bull_chop   → LONG полный, SHORT с пониженным риском (0.5×)
    bear_chop   → оба, SHORT немного сильнее
    bear_trend  → только SHORT (фейдим отскоки на даунтренде)
    """
    if regime == "bull_trend":
        return direction == "long"
    if regime == "bear_trend":
        return direction == "short"
    return True  # chop: оба разрешены
```

Режим берётся из `store.orchestrator_regime` или из env `AVEF1_FORCE_REGIME`.

### Шаг 5: Дополнительные фильтры

```python
# 1. Не торгуем если объём слишком маленький на текущем баре (нет ликвидности)
if current_volume < AVEF1_MIN_ABS_VOL:  # default 0 (отключён)
    return None

# 2. Cooldown после последней сделки
if self._cooldown > 0:
    self._cooldown -= 1
    return None

# 3. Максимум N сигналов в 24 часа на символ
if self._signals_today >= AVEF1_MAX_SIGNALS_PER_DAY:  # default 4
    return None

# 4. Не входить если спред > 0.3% (для мем-коинов)
# Проверить через store если доступно
```

---

## Конфиг класс

```python
@dataclass
class AltVolumeExhaustFadeV1Config:
    entry_tf: str = "15"             # AVEF1_ENTRY_TF
    atr_period: int = 14             # AVEF1_ATR_PERIOD
    vol_period: int = 20             # AVEF1_VOL_PERIOD
    vol_spike_mult: float = 3.5      # AVEF1_VOL_SPIKE_MULT — минимум 3.5× avg vol
    min_body_frac: float = 0.60      # AVEF1_MIN_BODY_FRAC — тело ≥ 60% диапазона
    min_move_pct: float = 0.010      # AVEF1_MIN_MOVE_PCT — ход ≥ 1.0%
    min_range_atr: float = 1.5       # AVEF1_MIN_RANGE_ATR — диапазон ≥ 1.5×ATR
    max_wait_bars: int = 3           # AVEF1_MAX_WAIT_BARS — ждать истощения
    rsi_period: int = 14             # AVEF1_RSI_PERIOD
    rsi_long_max: float = 48.0       # AVEF1_RSI_LONG_MAX — RSI для лонга
    rsi_short_min: float = 52.0      # AVEF1_RSI_SHORT_MIN — RSI для шорта
    sl_buffer_atr: float = 0.4       # AVEF1_SL_BUFFER_ATR — буфер стопа
    tp_retrace: float = 0.55         # AVEF1_TP_RETRACE — 55% ретрейс тела
    tp_atr: float = 1.5              # AVEF1_TP_ATR — или 1.5×ATR, что ближе
    min_rr: float = 1.2              # AVEF1_MIN_RR — минимум R:R
    max_stop_pct: float = 0.05       # AVEF1_MAX_STOP_PCT — стоп не больше 5%
    min_stop_pct: float = 0.006      # AVEF1_MIN_STOP_PCT — стоп не меньше 0.6%
    time_stop_bars: int = 16         # AVEF1_TIME_STOP_BARS — 16 × 15m = 4 часа max
    cooldown_bars: int = 4           # AVEF1_COOLDOWN_BARS — 4 × 15m = 1 час между сделками
    max_signals_per_day: int = 4     # AVEF1_MAX_SIGNALS_PER_DAY
    allow_longs: bool = True         # AVEF1_ALLOW_LONGS
    allow_shorts: bool = True        # AVEF1_ALLOW_SHORTS
    regime_mode: str = "orchestrator" # AVEF1_REGIME_MODE
```

---

## `maybe_signal()` скелет

```python
def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
    self._refresh_runtime_allowlists()
    sym = str(getattr(store, "symbol", "")).upper()
    
    # Allowlist/denylist check
    if self._allow and sym not in self._allow:
        self.last_no_signal_reason = "not_in_allowlist"
        return None
    if sym in self._deny:
        self.last_no_signal_reason = "in_denylist"
        return None
    
    # Cooldown
    if self._cooldown > 0:
        self._cooldown -= 1
        return None
    
    # Fetch bars
    bars_needed = max(self.cfg.vol_period, self.cfg.atr_period) + 30
    rows = store.fetch_klines(sym, self.cfg.entry_tf, bars_needed) or []
    if len(rows) < bars_needed // 2:
        self.last_no_signal_reason = "not_enough_bars"
        return None
    
    opens = [float(r[1]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows  = [float(r[3]) for r in rows]
    closes = [float(r[4]) for r in rows]
    volumes = [float(r[5]) if len(r) > 5 else 0.0 for r in rows]
    
    atr14 = _atr_from_rows(rows, self.cfg.atr_period)
    vol_base = _sma(volumes[:-1], self.cfg.vol_period)  # среднее без текущего бара
    rsi14 = _rsi(closes, self.cfg.rsi_period)
    
    # State machine
    if self._spike is None:
        self._try_arm_spike(rows, atr14, vol_base)
    else:
        self._spike["wait_bars"] += 1
        if self._spike["wait_bars"] > self.cfg.max_wait_bars:
            self._spike = None
            self.last_no_signal_reason = "exhaust_timeout"
            return None
        
        # Check exhaustion
        sig = self._check_exhaustion(rows, atr14, rsi14)
        if sig:
            self._cooldown = self.cfg.cooldown_bars
            self._spike = None
            return sig
    
    return None
```

---

## Вспомогательная функция RSI

```python
def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [abs(d) for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss < 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
```

---

## Регистрация в системе

### 2. `configs/portfolio_allocator_policy.json`

Добавить sleeve в конец массива `"sleeves"`:
```json
{
  "name": "vol_fade",
  "enable_env": "ENABLE_AVEF1_TRADING",
  "symbol_env_key": "AVEF1_SYMBOL_ALLOWLIST",
  "risk_env": "AVEF1_RISK_MULT",
  "strategy_names": ["alt_volume_exhaust_fade_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 0.7,
    "bull_chop": 0.9,
    "bear_chop": 0.95,
    "bear_trend": 0.7
  }
}
```

Логика: в chop самый высокий risk (объёмные взрывы в боковике — лучший сигнал),
в trend чуть меньше (направленный фильтр делает работу).

### 3. `configs/strategy_profile_registry.json`

Добавить профиль:
```json
{
  "profile_id": "avef1_core_v1",
  "strategy_name": "alt_volume_exhaust_fade_v1",
  "description": "Volume exhaustion fade — лонги и шорты против объёмных взрывов на 15m",
  "sleeve": "vol_fade",
  "bt_require_history": false,
  "fallback_mode": "anchor_only",
  "anchor_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
  "regime_profiles": {
    "bull_trend": {
      "profile": "avef1_core_v1",
      "source": "anchor",
      "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    },
    "bull_chop": {
      "profile": "avef1_core_v1",
      "source": "anchor",
      "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    },
    "bear_chop": {
      "profile": "avef1_core_v1",
      "source": "anchor",
      "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    },
    "bear_trend": {
      "profile": "avef1_core_v1",
      "source": "anchor",
      "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    }
  }
}
```

### 4. `configs/avef1_live.env`

Создать файл:
```bash
# alt_volume_exhaust_fade_v1 — production config
ENABLE_AVEF1_TRADING=1

# Символы
AVEF1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT

# Объём
AVEF1_VOL_SPIKE_MULT=3.5
AVEF1_VOL_PERIOD=20

# Тело свечи
AVEF1_MIN_BODY_FRAC=0.60
AVEF1_MIN_MOVE_PCT=0.010
AVEF1_MIN_RANGE_ATR=1.5

# Ожидание истощения
AVEF1_MAX_WAIT_BARS=3

# RSI фильтры
AVEF1_RSI_LONG_MAX=48
AVEF1_RSI_SHORT_MIN=52

# Риск
AVEF1_SL_BUFFER_ATR=0.4
AVEF1_TP_RETRACE=0.55
AVEF1_TP_ATR=1.5
AVEF1_MIN_RR=1.2
AVEF1_MAX_STOP_PCT=0.05
AVEF1_MIN_STOP_PCT=0.006

# Частота
AVEF1_TIME_STOP_BARS=16
AVEF1_COOLDOWN_BARS=4
AVEF1_MAX_SIGNALS_PER_DAY=4

# Направление
AVEF1_ALLOW_LONGS=1
AVEF1_ALLOW_SHORTS=1
AVEF1_REGIME_MODE=orchestrator

# Risk multiplier (применяется поверх sleeve)
AVEF1_RISK_MULT=1.0
```

### 5. `smart_pump_reversal_bot.py` — интеграция

Найти паттерн интеграции Elder (добавленный Codex) и добавить AVEF1 аналогично:

```python
# ── AVEF1 store ──────────────────────────────────────────────
class _AVEF1Store:
    """Per-symbol state store for AltVolumeExhaustFadeV1Strategy."""
    def __init__(self, symbol: str, fetcher):
        self.symbol = symbol
        self._fetcher = fetcher

    def fetch_klines(self, sym: str, tf: str, limit: int):
        return self._fetcher(sym, tf, limit)

    @property
    def orchestrator_regime(self) -> str:
        return _get_current_regime()  # существующая функция


# ── Init ──────────────────────────────────────────────────────
if os.getenv("ENABLE_AVEF1_TRADING", "0") == "1":
    from strategies.alt_volume_exhaust_fade_v1 import AltVolumeExhaustFadeV1Strategy
    _avef1_strategies: dict[str, AltVolumeExhaustFadeV1Strategy] = {}

    def _get_avef1(symbol: str) -> AltVolumeExhaustFadeV1Strategy:
        if symbol not in _avef1_strategies:
            _avef1_strategies[symbol] = AltVolumeExhaustFadeV1Strategy()
        return _avef1_strategies[symbol]


async def try_avef1_entry_async(symbol: str, ts_ms: int, o, h, l, c, v=0.0):
    if os.getenv("ENABLE_AVEF1_TRADING", "0") != "1":
        return
    strat = _get_avef1(symbol)
    store = _AVEF1Store(symbol, fetch_klines_sync)
    sig = strat.maybe_signal(store, ts_ms, o, h, l, c, v)
    if sig:
        await _place_signal(sig, symbol, source="avef1")
```

Добавить вызов `await try_avef1_entry_async(...)` в основной 15m scheduler loop
рядом с вызовами других 15m стратегий.

---

## Ожидаемые метрики

На бэктесте (цель для walk-forward валидации):

| Метрика | Цель |
|---------|------|
| Сделок/месяц | 8-16 на 5 символов |
| Win Rate | 42-52% |
| Profit Factor | 1.35-1.65 |
| Avg R:R | 1.3-1.6:1 |
| Max DD | < 12% |

Стратегия зарабатывает не на WR > 50%, а на **асимметрии R:R** — редкие большие откаты
после взрывов перекрывают малые стопы.

---

## Тест перед live

```bash
# 1. Unit test логики на исторических данных
python3 -m pytest tests/test_avef1.py -v

# 2. Бэктест 180 дней
python3 scripts/run_backtest.py \
  --strategy alt_volume_exhaust_fade_v1 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --tf 15 \
  --days 180 \
  --env configs/avef1_live.env \
  --output backtest_runs/avef1_initial_180d/

# 3. Проверить что min 30 сделок на символ за 180d
# (меньше — недостаточно данных для валидации)

# 4. Если PF > 1.3 и DD < 15% → добавить в live
```

---

## Чеклист Codex

- [ ] Создать `strategies/alt_volume_exhaust_fade_v1.py` — полная реализация
- [ ] Добавить `_rsi()` helper (или переиспользовать из signals.py если есть)
- [ ] Добавить sleeve `vol_fade` в `configs/portfolio_allocator_policy.json`
- [ ] Добавить профиль `avef1_core_v1` в `configs/strategy_profile_registry.json`
- [ ] Создать `configs/avef1_live.env`
- [ ] Добавить `_AVEF1Store` и `try_avef1_entry_async()` в `smart_pump_reversal_bot.py`
- [ ] Добавить вызов в 15m scheduler loop бота
- [ ] Запустить бэктест 180d, убедиться PF > 1.3
- [ ] Добавить в `configs/strategy_health.json` запись:
  ```json
  "alt_volume_exhaust_fade_v1": {
    "status": "WATCH",
    "total_pnl": 0.0,
    "30d_pnl": 0.0,
    "trades_30d": 0,
    "note": "new — initial monitoring period"
  }
  ```

## Приоритет: HIGH

Причина: это первая двусторонняя стратегия на объёме, не зависящая от режима рынка.
Должна добавить 8-16 сделок/месяц при минимальном конфликте с другими стратегиями
(разные триггеры, разные символы могут пересекаться но логика несовместима).
