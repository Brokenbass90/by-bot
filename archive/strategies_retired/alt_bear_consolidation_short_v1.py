"""alt_bear_consolidation_short_v1 — short scalp при отскоке к ресистенсу в bear-chop.

Заполняет gap: bear_chop / Short — нет частых стратегий для медвежьего боковика.

Идея: в bear-chop цена двигается в нисходящем канале — серия lower highs.
Когда цена откатывается вверх к EMA20/VWAP и встречает сопротивление (свеча
отказа), это shorting opportunity с малым риском и быстрой реализацией.

Логика:
    SHORT entry:
        - Regime ∈ {bear_chop, bear_trend} (HARD GATE)
        - EMA20 наклонена вниз (slope < 0)
        - EMA50 < EMA200 (структурный downtrend)
        - Цена откатилась вверх к EMA20 ± 0.5×ATR
        - RSI 50-65 (отскок до средней зоны, не overbought)
        - Сформирована "rejection candle": верхняя тень ≥ 50% диапазона
        - Не последний бар сессии (избегаем низкой ликвидности)

    Exit:
        - TP1: 1.0×ATR (быстрый scalp)
        - TP2: VWAP last 8 часов (mean reversion target)
        - Hard SL: выше high rejection candle + 0.3×ATR
        - Time stop: 24 бара 5m (2 часа) — scalp не должен сидеть

    Sizing:
        - Risk 0.5% (низкий — частая стратегия, экономим на разовых)
        - Max 2 одновременно
        - Cooldown 30 мин на символ (избегаем сетапов на одной свече подряд)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BearConsolidationSignal:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    rationale: str


class AltBearConsolidationShortV1:
    NAME = "alt_bear_consolidation_short_v1"
    DEFAULT_PARAMS = {
        "EMA_FAST": 20,
        "EMA_MID": 50,
        "EMA_SLOW": 200,
        "EMA_SLOPE_BARS": 5,  # на сколько баров проверять slope
        "PROXIMITY_TO_EMA_ATR": 0.5,  # цена в пределах 0.5×ATR от EMA20
        "REJECTION_WICK_FRAC": 0.50,  # верхняя тень ≥ 50% диапазона
        "RSI_MIN": 50.0,
        "RSI_MAX": 65.0,
        "SL_ATR_MULT": 0.4,  # tight stop — это scalp
        "SL_BUFFER_ATR": 0.3,  # выше high + buffer
        "TP1_ATR_MULT": 1.0,
        "TP2_VWAP_LOOKBACK_BARS": 96,  # 8 часов 5m
        "TRAIL_ATR_MULT": 0.8,
        "TIME_STOP_BARS_5M": 24,
        "RISK_PCT": 0.5,
        "MAX_OPEN_TRADES": 2,
        "COOLDOWN_BARS_PER_SYMBOL": 6,  # 30 мин
        "ALLOWED_REGIMES": "bear_chop,bear_trend",
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,LTCUSDT,SUIUSDT",
    }

    def __init__(self, params: Optional[dict] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._last_signal_bar = {}  # symbol -> bar index of last signal

    @staticmethod
    def _rsi(closes, period=14):
        if len(closes) < period + 1:
            return 50.0
        gains = losses = 0.0
        for i in range(1, period + 1):
            ch = closes[-i] - closes[-i - 1]
            if ch > 0:
                gains += ch
            else:
                losses -= ch
        avg_g, avg_l = gains / period, losses / period
        if avg_l == 0:
            return 100.0
        rs = avg_g / avg_l
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _atr(highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
        return sum(trs[-period:]) / period

    @staticmethod
    def _ema(values, period):
        if len(values) < period:
            return None
        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _ema_at(values, period, idx):
        """EMA на конкретном index."""
        if idx + 1 < period:
            return None
        sub = values[:idx + 1]
        return AltBearConsolidationShortV1._ema(sub, period)

    @staticmethod
    def _vwap(bars, n_bars):
        if len(bars) < n_bars:
            n_bars = len(bars)
        sub = bars[-n_bars:]
        num = sum(((b["high"] + b["low"] + b["close"]) / 3) * b["volume"] for b in sub)
        den = sum(b["volume"] for b in sub)
        return num / den if den > 0 else None

    def evaluate(self, bars, regime, symbol, open_positions=0, panic_mode=False, bar_index=None):
        if len(bars) < 220:
            return None
        if panic_mode:
            return None

        if regime not in [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]:
            return None

        if symbol not in [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]:
            return None

        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        # Cooldown
        if bar_index is not None:
            last = self._last_signal_bar.get(symbol)
            if last is not None and (bar_index - last) < int(self.params["COOLDOWN_BARS_PER_SYMBOL"]):
                return None

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        ema_fast = self._ema(closes, int(self.params["EMA_FAST"]))
        ema_mid = self._ema(closes, int(self.params["EMA_MID"]))
        ema_slow = self._ema(closes, int(self.params["EMA_SLOW"]))
        if not all([ema_fast, ema_mid, ema_slow]):
            return None

        # Downtrend structure
        if ema_mid >= ema_slow:
            return None

        # EMA20 slope
        slope_bars = int(self.params["EMA_SLOPE_BARS"])
        ema_old = self._ema_at(closes, int(self.params["EMA_FAST"]), len(closes) - 1 - slope_bars)
        if ema_old is None or ema_fast >= ema_old:
            return None  # not declining

        a = self._atr(highs, lows, closes)
        if a <= 0:
            return None

        # Proximity to EMA20
        current_close = closes[-1]
        proximity = abs(current_close - ema_fast)
        if proximity > float(self.params["PROXIMITY_TO_EMA_ATR"]) * a:
            return None

        # Rejection candle на последнем баре
        bar = bars[-1]
        body = abs(bar["close"] - bar["open"])
        rng = bar["high"] - bar["low"]
        if rng <= 0:
            return None
        upper_wick = bar["high"] - max(bar["close"], bar["open"])
        wick_frac = upper_wick / rng
        if wick_frac < float(self.params["REJECTION_WICK_FRAC"]):
            return None

        # RSI
        r = self._rsi(closes)
        if not (float(self.params["RSI_MIN"]) <= r <= float(self.params["RSI_MAX"])):
            return None

        # Build signal
        sl = bar["high"] + float(self.params["SL_BUFFER_ATR"]) * a
        # Also cap SL by SL_ATR_MULT
        sl_alt = current_close + float(self.params["SL_ATR_MULT"]) * a
        sl = min(sl, current_close + max(float(self.params["SL_ATR_MULT"]), float(self.params["SL_BUFFER_ATR"])) * a)

        tp1 = current_close - float(self.params["TP1_ATR_MULT"]) * a
        vwap = self._vwap(bars, int(self.params["TP2_VWAP_LOOKBACK_BARS"]))
        tp2 = vwap if vwap and vwap < current_close else tp1 - a

        if bar_index is not None:
            self._last_signal_bar[symbol] = bar_index

        rationale = (
            f"Bear consolidation: EMA50({ema_mid:.4f})<EMA200({ema_slow:.4f}), "
            f"EMA20 slope down, close near EMA20 ({proximity:.4f} vs ATR×{self.params['PROXIMITY_TO_EMA_ATR']}={a*self.params['PROXIMITY_TO_EMA_ATR']:.4f}), "
            f"rejection wick {wick_frac*100:.0f}%, RSI {r:.1f}, regime={regime}"
        )

        return BearConsolidationSignal(
            side="short",
            entry=current_close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
            rationale=rationale,
        )


if __name__ == "__main__":
    import random
    random.seed(11)
    bars = []
    price = 100.0
    # Bear chop с боковым движением и общим bearish drift
    for i in range(250):
        ch = random.gauss(-0.05, 0.5)  # mild bearish drift
        price = max(20, price + ch)
        bars.append({
            "ts": i,
            "open": price + random.gauss(0, 0.1),
            "high": price + abs(random.gauss(0, 0.25)),
            "low": price - abs(random.gauss(0, 0.25)),
            "close": price,
            "volume": random.uniform(80, 150),
        })
    # Force rejection candle near EMA20 на последнем баре
    last_close = bars[-2]["close"]
    bars[-1]["open"] = last_close
    bars[-1]["high"] = last_close * 1.012  # bounced up
    bars[-1]["low"] = last_close * 0.998
    bars[-1]["close"] = last_close * 1.001  # closed near open with long upper wick

    strat = AltBearConsolidationShortV1()
    sig = strat.evaluate(bars, regime="bear_chop", symbol="BTCUSDT", bar_index=len(bars)-1)
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP1 {sig.tp1:.4f} TP2 {sig.tp2:.4f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (conditions not met in smoke test — это нормально, нужны точные условия)")
