"""
custom_indicators.py
====================
Кастомные индикаторы для 4 стратегий:
  1. inplay / breakout
  2. pump_fade
  3. adaptive_range_short
  4. bounce

Зависимости: pandas, numpy
Входные данные: pd.DataFrame с колонками [open, high, low, close, volume]
                индекс — datetime (UTC), таймфрейм передаётся явно где нужно.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ─────────────────────────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """True Range → ATR (Wilder)."""
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _rolling_vwap(df: pd.DataFrame, period: int) -> pd.Series:
    """Скользящий VWAP за последние `period` баров."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).rolling(period).sum() / df["volume"].rolling(period).sum()


def _z_score(series: pd.Series, period: int) -> pd.Series:
    mu = series.rolling(period).mean()
    sigma = series.rolling(period).std(ddof=0)
    return (series - mu) / sigma.replace(0, np.nan)


# ─────────────────────────────────────────────────────────────────────────────
# 1. INPLAY / BREAKOUT INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def breakout_quality(
    df: pd.DataFrame,
    vol_period: int = 20,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Оценка качества пробоя — ключевой фильтр ложных сигналов.

    Возвращает DataFrame с колонками:
      vol_ratio      — объём свечи / средний объём (>1.5 = хороший пробой)
      candle_speed   — размер тела свечи / ATR  (>0.6 = сильная свеча)
      breakout_score — комбо-скор [0..1], чем выше тем лучше пробой
      is_strong_breakout — bool, рекомендуемый фильтр входа

    Использование:
        bq = breakout_quality(df)
        # Входить только если is_strong_breakout == True
    """
    atr = _atr(df, atr_period)
    avg_vol = df["volume"].rolling(vol_period).mean()

    vol_ratio = df["volume"] / avg_vol.replace(0, np.nan)

    body = (df["close"] - df["open"]).abs()
    candle_speed = body / atr.replace(0, np.nan)

    # Нормализуем оба компонента в [0,1] через скользящий перцентиль
    vol_pct   = vol_ratio.rolling(vol_period).rank(pct=True)
    speed_pct = candle_speed.rolling(vol_period).rank(pct=True)

    breakout_score = 0.6 * vol_pct + 0.4 * speed_pct

    is_strong = (vol_ratio >= 1.5) & (candle_speed >= 0.5) & (breakout_score >= 0.65)

    return pd.DataFrame({
        "vol_ratio":           vol_ratio,
        "candle_speed":        candle_speed,
        "breakout_score":      breakout_score,
        "is_strong_breakout":  is_strong,
    }, index=df.index)


def inplay_entry_filter(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    atr_period: int = 14,
    min_atr_pct: float = 0.003,
) -> pd.DataFrame:
    """
    Фильтр для входа в inplay: не лезть в FOMO и не входить поздно.

    Колонки:
      ema_fast, ema_slow — для определения тренда
      trend_up / trend_down — направление тренда
      atr_pct            — ATR / close, фильтр волатильности
      dist_from_ema_pct  — насколько цена ушла от fast EMA (анти-FOMO)
      anti_fomo_ok       — True если цена не слишком далеко от EMA
      entry_allowed      — итоговый фильтр

    Использование:
        filt = inplay_entry_filter(df)
        long_ok  = filt["trend_up"] & filt["entry_allowed"]
        short_ok = filt["trend_down"] & filt["entry_allowed"]
    """
    ema_f = df["close"].ewm(span=ema_fast, adjust=False).mean()
    ema_s = df["close"].ewm(span=ema_slow, adjust=False).mean()
    atr   = _atr(df, atr_period)

    atr_pct          = atr / df["close"]
    dist_from_ema    = (df["close"] - ema_f).abs() / ema_f
    anti_fomo_ok     = dist_from_ema < (atr_pct * 2.5)   # не дальше 2.5 ATR от EMA

    trend_up   = ema_f > ema_s
    trend_down = ema_f < ema_s

    entry_allowed = anti_fomo_ok & (atr_pct >= min_atr_pct)

    return pd.DataFrame({
        "ema_fast":         ema_f,
        "ema_slow":         ema_s,
        "atr_pct":          atr_pct,
        "dist_from_ema_pct": dist_from_ema,
        "trend_up":         trend_up,
        "trend_down":       trend_down,
        "anti_fomo_ok":     anti_fomo_ok,
        "entry_allowed":    entry_allowed,
    }, index=df.index)


def dynamic_exit_levels(
    df: pd.DataFrame,
    atr_period: int = 14,
    sl_atr_mult: float = 1.5,
    tp1_rr: float = 1.0,
    tp2_rr: float = 2.5,
    tp3_rr: float = 4.0,
) -> pd.DataFrame:
    """
    Динамические уровни SL и TP на основе ATR + структуры рынка.

    Колонки:
      atr           — текущий ATR
      sl_long/sl_short   — стоп-лосс уровни
      tp1/tp2/tp3_long   — цели для лонга
      tp1/tp2/tp3_short  — цели для шорта
      trail_stop_long/short — ATR-трейлинг от текущего close

    Использование:
        exits = dynamic_exit_levels(df)
        # При входе в лонг на баре i:
        #   sl    = exits["sl_long"].iloc[i]
        #   tp1   = exits["tp1_long"].iloc[i]
    """
    atr   = _atr(df, atr_period)
    close = df["close"]

    sl_dist = atr * sl_atr_mult

    result = pd.DataFrame(index=df.index)
    result["atr"] = atr

    for side in ("long", "short"):
        sign = 1 if side == "long" else -1
        sl = close - sign * sl_dist
        result[f"sl_{side}"] = sl

        for tp_name, rr in [("tp1", tp1_rr), ("tp2", tp2_rr), ("tp3", tp3_rr)]:
            result[f"{tp_name}_{side}"] = close + sign * sl_dist * rr

        result[f"trail_stop_{side}"] = close - sign * atr * 2.0

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. PUMP_FADE INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def pump_detector(
    df: pd.DataFrame,
    vol_period: int = 30,
    price_period: int = 5,
    vol_spike_mult: float = 5.0,
    price_spike_pct: float = 0.05,
    time_of_day_norm: bool = True,
) -> pd.DataFrame:
    """
    Детектор аномального памп-движения с нормализацией по времени суток.

    Колонки:
      vol_spike       — объём / средний объём за `vol_period` баров
      price_chg_pct   — изменение цены за `price_period` баров
      vwap_dev        — отклонение close от VWAP (>0 = выше VWAP)
      tod_vol_ratio   — объём / средний объём того же часа (учёт ночного затишья)
      pump_score      — взвешенный скор [0..∞], >1.0 = вероятный памп
      is_pump         — bool детектор входа

    Параметры:
      vol_spike_mult  — множитель объёма для детекции (5x по умолчанию)
      price_spike_pct — минимальный рост цены за price_period баров (5%)
      time_of_day_norm — учитывать ли час суток при нормализации объёма

    Использование:
        pd_res = pump_detector(df_5m)
        # Шортить fade когда is_pump == True и цена начинает откатывать
    """
    avg_vol   = df["volume"].rolling(vol_period).mean()
    vol_spike = df["volume"] / avg_vol.replace(0, np.nan)

    price_chg = df["close"].pct_change(price_period)

    vwap      = _rolling_vwap(df, vol_period)
    vwap_dev  = (df["close"] - vwap) / vwap

    # Нормализация по времени суток
    if time_of_day_norm and isinstance(df.index, pd.DatetimeIndex):
        hour = df.index.hour
        tod_mean = df.groupby(hour)["volume"].transform("mean")
        tod_vol_ratio = df["volume"] / tod_mean.replace(0, np.nan)
    else:
        tod_vol_ratio = vol_spike.copy()
        tod_vol_ratio.name = "tod_vol_ratio"

    # Скор: объём (60%) + цена (25%) + VWAP-девиация (15%)
    vol_norm   = (vol_spike / vol_spike_mult).clip(0, 3)
    price_norm = (price_chg / price_spike_pct).clip(0, 3)
    vwap_norm  = (vwap_dev / 0.03).clip(0, 3)

    pump_score = 0.60 * vol_norm + 0.25 * price_norm + 0.15 * vwap_norm

    is_pump = (
        (vol_spike >= vol_spike_mult) &
        (price_chg >= price_spike_pct) &
        (vwap_dev  >= 0.02)
    )

    return pd.DataFrame({
        "vol_spike":     vol_spike,
        "price_chg_pct": price_chg,
        "vwap_dev":      vwap_dev,
        "tod_vol_ratio": tod_vol_ratio,
        "pump_score":    pump_score,
        "is_pump":       is_pump,
    }, index=df.index)


def pump_fade_entry(
    df: pd.DataFrame,
    pump_col: pd.Series,          # is_pump Series из pump_detector()
    confirmation_bars: int = 3,
    reversal_threshold: float = 0.4,  # откат от локального хая
) -> pd.DataFrame:
    """
    Определяет оптимальную точку входа в fade (шорт после памп-пика).

    Логика:
      - После детекции памп-сигнала ждём `confirmation_bars` баров
      - Ищем локальный хай в этом окне
      - Вход в шорт когда цена откатилась от хая на `reversal_threshold` * ATR

    Колонки:
      pump_high       — локальный хай после памп-детекции
      atr             — ATR на момент памп-детекции
      fade_entry_px   — предлагаемая цена входа (шорт)
      fade_sl_px      — стоп-лосс (выше локального хая + 0.5 ATR)
      fade_tp1_px     — первая цель (50% отката)
      fade_tp2_px     — вторая цель (80% отката)
      fade_signal     — True = можно входить в шорт

    Использование:
        pd_res  = pump_detector(df_5m)
        fade    = pump_fade_entry(df_5m, pd_res["is_pump"])
        entry   = fade[fade["fade_signal"]]
    """
    atr       = _atr(df)
    close     = df["close"]

    pump_high    = pd.Series(np.nan, index=df.index)
    fade_signal  = pd.Series(False, index=df.index)
    fade_entry   = pd.Series(np.nan, index=df.index)
    fade_sl      = pd.Series(np.nan, index=df.index)
    fade_tp1     = pd.Series(np.nan, index=df.index)
    fade_tp2     = pd.Series(np.nan, index=df.index)

    pump_indices = df.index[pump_col.fillna(False)]

    for pi in pump_indices:
        loc = df.index.get_loc(pi)
        end = min(loc + confirmation_bars + 1, len(df))
        window = df.iloc[loc:end]

        local_high = window["high"].max()
        entry_px   = local_high - reversal_threshold * atr.iloc[loc]
        sl_px      = local_high + 0.5 * atr.iloc[loc]
        prev_base  = df["close"].iloc[max(0, loc - 5)]   # уровень до памп
        tp1_px     = local_high - 0.5 * (local_high - prev_base)
        tp2_px     = local_high - 0.8 * (local_high - prev_base)

        # Сигнал: текущая цена упала к entry_px после взятия хая
        for j in range(loc + 1, end):
            if df["close"].iloc[j] <= entry_px:
                idx = df.index[j]
                pump_high[idx]   = local_high
                fade_entry[idx]  = entry_px
                fade_sl[idx]     = sl_px
                fade_tp1[idx]    = tp1_px
                fade_tp2[idx]    = tp2_px
                fade_signal[idx] = True
                break

    return pd.DataFrame({
        "pump_high":    pump_high,
        "atr":          atr,
        "fade_entry_px": fade_entry,
        "fade_sl_px":   fade_sl,
        "fade_tp1_px":  fade_tp1,
        "fade_tp2_px":  fade_tp2,
        "fade_signal":  fade_signal,
    }, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ADAPTIVE RANGE SHORT INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def market_regime(
    df: pd.DataFrame,
    adx_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
    adx_threshold: float = 20.0,
    bb_width_threshold: float = 0.04,
) -> pd.DataFrame:
    """
    Определение режима рынка: TREND vs RANGE.
    Критически важен для adaptive_range_short — не торговать в тренд.

    Колонки:
      adx             — Average Directional Index
      bb_width        — ширина Bollinger Bands относительно цены
      bb_upper/lower/mid — полосы Боллинджера
      is_range        — True = рынок в диапазоне (можно торговать range)
      is_trend        — True = рынок в тренде (range стратегию отключить)
      regime          — строка: 'range' | 'trend' | 'neutral'

    Параметры:
      adx_threshold       — ADX ниже этого = range режим (обычно 20-25)
      bb_width_threshold  — BB width ниже этого = сжатие = range (0.03-0.05)

    Использование:
        reg = market_regime(df_1h)
        # Разрешать range-шорты только если reg["is_range"]
    """
    # ADX
    high, low, close = df["high"], df["low"], df["close"]
    atr = _atr(df, adx_period)

    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm   = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm  = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s  = pd.Series(plus_dm,  index=df.index).ewm(alpha=1/adx_period, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1/adx_period, adjust=False).mean()

    plus_di  = 100 * plus_dm_s  / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm_s / atr.replace(0, np.nan)
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx      = dx.ewm(alpha=1/adx_period, adjust=False).mean()

    # Bollinger Bands
    bb_mid   = close.rolling(bb_period).mean()
    bb_std_s = close.rolling(bb_period).std(ddof=0)
    bb_upper = bb_mid + bb_std * bb_std_s
    bb_lower = bb_mid - bb_std * bb_std_s
    bb_width = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)

    # Режим
    is_range  = (adx < adx_threshold) & (bb_width < bb_width_threshold)
    is_trend  = adx >= adx_threshold + 5
    regime    = pd.Series("neutral", index=df.index)
    regime[is_range] = "range"
    regime[is_trend] = "trend"

    return pd.DataFrame({
        "adx":       adx,
        "plus_di":   plus_di,
        "minus_di":  minus_di,
        "bb_upper":  bb_upper,
        "bb_lower":  bb_lower,
        "bb_mid":    bb_mid,
        "bb_width":  bb_width,
        "is_range":  is_range,
        "is_trend":  is_trend,
        "regime":    regime,
    }, index=df.index)


def range_short_signal(
    df: pd.DataFrame,
    regime_df: pd.DataFrame,      # из market_regime()
    rsi_period: int = 14,
    rsi_overbought: float = 68.0,
    bb_touch_pct: float = 0.002,  # насколько близко к BB upper
    min_rr: float = 1.5,
    atr_period: int = 14,
    cooldown_bars: int = 10,
    max_signals_per_day: int = 3,
) -> pd.DataFrame:
    """
    Сигнал для short в range-режиме: цена у верхней BB + RSI overbought.

    Колонки:
      rsi             — RSI
      near_bb_upper   — цена близко к верхней полосе
      short_signal    — итоговый сигнал после всех фильтров
      entry_px        — предлагаемая цена входа
      sl_px           — стоп выше BB upper + 0.5 ATR
      tp_px           — цель у BB mid (mean reversion)
      rr              — фактическое RR для этого сигнала

    Защиты:
      - cooldown_bars: не генерировать сигналы N баров после последнего
      - max_signals_per_day: cap по сигналам в день
      - min_rr: не брать сделку если RR ниже порога
      - kill_switch: не торговать если is_trend == True

    Использование:
        reg = market_regime(df_1h)
        sig = range_short_signal(df_1h, reg)
        entries = sig[sig["short_signal"]]
    """
    # RSI
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)

    atr       = _atr(df, atr_period)
    close     = df["close"]
    bb_upper  = regime_df["bb_upper"]
    bb_mid    = regime_df["bb_mid"]
    bb_lower  = regime_df["bb_lower"]

    near_bb_upper = (bb_upper - close) / close < bb_touch_pct

    # Сырой сигнал
    raw_signal = (
        regime_df["is_range"] &
        near_bb_upper &
        (rsi >= rsi_overbought)
    )

    # RR расчёт
    sl_dist = (bb_upper + 0.5 * atr) - close
    tp_dist = close - bb_mid
    rr      = tp_dist / sl_dist.replace(0, np.nan)
    good_rr = rr >= min_rr

    entry_px = close
    sl_px    = bb_upper + 0.5 * atr
    tp_px    = bb_mid

    # Cooldown и дневной cap
    short_signal = pd.Series(False, index=df.index)
    last_signal_bar = -cooldown_bars - 1
    daily_counts: dict = {}

    for i, (idx, val) in enumerate(raw_signal.items()):
        if not val or not good_rr.iloc[i]:
            continue
        if i - last_signal_bar < cooldown_bars:
            continue

        day_key = idx.date() if isinstance(idx, pd.Timestamp) else i
        count   = daily_counts.get(day_key, 0)
        if count >= max_signals_per_day:
            continue

        short_signal.iloc[i] = True
        last_signal_bar = i
        daily_counts[day_key] = count + 1

    return pd.DataFrame({
        "rsi":          rsi,
        "near_bb_upper": near_bb_upper,
        "short_signal": short_signal,
        "entry_px":     entry_px,
        "sl_px":        sl_px,
        "tp_px":        tp_px,
        "rr":           rr,
    }, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# 4. BOUNCE INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def support_resistance_levels(
    df: pd.DataFrame,
    lookback: int = 72,       # баров для поиска уровней
    merge_pct: float = 0.005, # объединять уровни ближе чем 0.5%
    min_touches: int = 2,
) -> dict:
    """
    Детекция уровней поддержки и сопротивления через локальные экстремумы.

    Возвращает dict:
      supports     — список уровней поддержки (цены)
      resistances  — список уровней сопротивления (цены)
      all_levels   — все уровни отсортированные

    Параметры:
      lookback    — сколько баров назад смотреть
      merge_pct   — объединять уровни ближе чем N% (убирает дубли)
      min_touches — минимум касаний уровня для валидации

    Использование:
        levels = support_resistance_levels(df_1h.tail(200))
        # Проверить близость к уровню:
        # any(abs(price - lvl) / price < 0.003 for lvl in levels["supports"])
    """
    window = df.tail(lookback)
    highs  = window["high"].values
    lows   = window["low"].values
    close  = window["close"].values

    # Локальные экстремумы (простой pivot detector)
    pivot_highs = []
    pivot_lows  = []
    n = len(window)

    for i in range(2, n - 2):
        if highs[i] >= highs[i-1] and highs[i] >= highs[i+1]:
            pivot_highs.append(highs[i])
        if lows[i] <= lows[i-1] and lows[i] <= lows[i+1]:
            pivot_lows.append(lows[i])

    def _merge_levels(raw_levels, current_price):
        if not raw_levels:
            return []
        levels = sorted(raw_levels)
        merged = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - merged[-1]) / merged[-1] < merge_pct:
                merged[-1] = (merged[-1] + lvl) / 2  # усредняем
            else:
                merged.append(lvl)

        # Считаем касания
        valid = []
        for lvl in merged:
            touches = sum(
                1 for h, l in zip(highs, lows)
                if abs(h - lvl) / lvl < merge_pct or abs(l - lvl) / lvl < merge_pct
            )
            if touches >= min_touches:
                valid.append(round(lvl, 6))
        return valid

    cp = close[-1]
    resistances = _merge_levels([h for h in pivot_highs if h > cp], cp)
    supports    = _merge_levels([l for l in pivot_lows  if l < cp], cp)

    return {
        "supports":    supports,
        "resistances": resistances,
        "all_levels":  sorted(supports + resistances),
    }


def bounce_signal(
    df: pd.DataFrame,
    levels: dict,             # из support_resistance_levels()
    atr_period: int = 14,
    proximity_atr: float = 0.5,   # насколько близко к уровню (в ATR)
    rsi_period: int = 14,
    rsi_oversold: float = 35.0,
    rsi_overbought: float = 65.0,
    min_rr: float = 1.5,
    confirm_candle: bool = True,  # требовать подтверждающую свечу
) -> pd.DataFrame:
    """
    Генерирует сигналы отскока от уровней поддержки и сопротивления.

    Колонки:
      near_support    — цена близко к уровню поддержки
      near_resistance — цена близко к уровню сопротивления
      closest_support / closest_resistance — ближайшие уровни
      rsi             — RSI
      bounce_long     — сигнал лонга (отскок от поддержки)
      bounce_short    — сигнал шорта (отскок от сопротивления)
      entry_px / sl_px / tp_px — уровни для позиции
      rr              — расчётное RR

    Параметры:
      proximity_atr   — насколько близко к уровню считается "касанием" (в ATR)
      confirm_candle  — требовать бычью/медвежью свечу как подтверждение

    Использование:
        levels = support_resistance_levels(df_1h.tail(200))
        sig    = bounce_signal(df_5m, levels)
        longs  = sig[sig["bounce_long"]]
        shorts = sig[sig["bounce_short"]]
    """
    atr   = _atr(df, atr_period)
    close = df["close"]

    # RSI
    delta    = close.diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1/rsi_period, adjust=False).mean()
    avg_loss = (-delta).clip(lower=0).ewm(alpha=1/rsi_period, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)

    supports    = levels.get("supports", [])
    resistances = levels.get("resistances", [])

    def _nearest(price, lvl_list):
        if not lvl_list:
            return np.nan
        return min(lvl_list, key=lambda x: abs(x - price))

    nearest_sup = close.apply(lambda p: _nearest(p, supports))
    nearest_res = close.apply(lambda p: _nearest(p, resistances))

    near_support    = (close - nearest_sup).abs() < atr * proximity_atr
    near_resistance = (nearest_res - close).abs() < atr * proximity_atr

    # Подтверждающая свеча
    bullish_candle = df["close"] > df["open"]  # бычья свеча
    bearish_candle = df["close"] < df["open"]  # медвежья свеча

    if confirm_candle:
        long_confirm  = bullish_candle
        short_confirm = bearish_candle
    else:
        long_confirm  = pd.Series(True, index=df.index)
        short_confirm = pd.Series(True, index=df.index)

    bounce_long  = near_support    & (rsi < rsi_oversold)   & long_confirm
    bounce_short = near_resistance & (rsi > rsi_overbought) & short_confirm

    # Уровни для позиции
    entry_px = close.copy()

    # Лонг: SL под уровнем поддержки, TP к ближайшему сопротивлению
    sl_long  = nearest_sup - atr * 0.5
    tp_long  = nearest_res.where(nearest_res > close, close + atr * 2)
    rr_long  = (tp_long - entry_px) / (entry_px - sl_long).replace(0, np.nan)

    # Шорт: SL над уровнем сопротивления, TP к ближайшей поддержке
    sl_short = nearest_res + atr * 0.5
    tp_short = nearest_sup.where(nearest_sup < close, close - atr * 2)
    rr_short = (entry_px - tp_short) / (sl_short - entry_px).replace(0, np.nan)

    # Финальный фильтр по RR
    bounce_long  = bounce_long  & (rr_long  >= min_rr)
    bounce_short = bounce_short & (rr_short >= min_rr)

    return pd.DataFrame({
        "rsi":               rsi,
        "nearest_support":   nearest_sup,
        "nearest_resistance": nearest_res,
        "near_support":      near_support,
        "near_resistance":   near_resistance,
        "bounce_long":       bounce_long,
        "bounce_short":      bounce_short,
        "entry_px":          entry_px,
        "sl_long":           sl_long,
        "tp_long":           tp_long,
        "rr_long":           rr_long,
        "sl_short":          sl_short,
        "tp_short":          tp_short,
        "rr_short":          rr_short,
    }, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# ПРИМЕР ИСПОЛЬЗОВАНИЯ
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Генерируем тестовые данные
    np.random.seed(42)
    n = 500
    idx = pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC")
    price = 100 + np.cumsum(np.random.randn(n) * 0.3)
    df_test = pd.DataFrame({
        "open":   price + np.random.randn(n) * 0.1,
        "high":   price + np.abs(np.random.randn(n)) * 0.4,
        "low":    price - np.abs(np.random.randn(n)) * 0.4,
        "close":  price,
        "volume": np.abs(np.random.randn(n)) * 1000 + 500,
    }, index=idx)

    print("=== BREAKOUT QUALITY ===")
    bq = breakout_quality(df_test)
    print(bq.tail(5))

    print("\n=== INPLAY ENTRY FILTER ===")
    filt = inplay_entry_filter(df_test)
    print(filt[["ema_fast","ema_slow","atr_pct","anti_fomo_ok","entry_allowed"]].tail(5))

    print("\n=== PUMP DETECTOR ===")
    pd_res = pump_detector(df_test, vol_spike_mult=3.0, price_spike_pct=0.01)
    print(pd_res[pd_res["is_pump"]].head(5) if pd_res["is_pump"].any() else "No pumps detected")

    print("\n=== MARKET REGIME ===")
    reg = market_regime(df_test)
    print(reg[["adx","bb_width","regime"]].tail(10))

    print("\n=== RANGE SHORT SIGNAL ===")
    sig = range_short_signal(df_test, reg)
    print(sig[["rsi","short_signal","rr"]].tail(10))

    print("\n=== SUPPORT/RESISTANCE + BOUNCE ===")
    levels = support_resistance_levels(df_test, lookback=100)
    print("Supports:", levels["supports"][:5])
    print("Resistances:", levels["resistances"][:5])
    bounce = bounce_signal(df_test, levels)
    print(bounce[["rsi","bounce_long","bounce_short","rr_long","rr_short"]].tail(10))

    print("\nВсё ок, индикаторы загружены.")
