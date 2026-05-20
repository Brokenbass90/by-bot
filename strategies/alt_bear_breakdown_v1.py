"""alt_bear_breakdown_v1 — short trend continuation в bear-фазах.

Заполняет gap: bear_trend / Medium-Short — там сейчас почти нет стратегий.

Логика:
    SHORT entry:
        - Regime ∈ {bear_trend, bear_chop} (HARD GATE)
        - Close < 20-bar low (breakdown)
        - Volume > 2× 20-bar avg (capitulation hint)
        - RSI < 45 (не overSold ещё — место падать)
        - EMA50 < EMA200 (структурный downtrend)
        - Close < EMA20 (моментум вниз)
        - Не в panic_mode (там reduce-only)

    Exit:
        - TP1: 1.5×ATR (close 33%, ставим breakeven SL)
        - TP2: 3.0×ATR (close 33%, trail 2×ATR)
        - Hard SL: 1.0×ATR от entry
        - Time stop: 60 баров 5m (5 часов) если не двинулось ≥0.5×ATR

    Sizing:
        - Risk 0.7% (агрессивный setup, меньше дефолта)
        - Max 2 одновременно (BTCUSDT + ETHUSDT обычно коррелируют, опасно)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BearBreakdownSignal:
    side: str  # always "short"
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    rationale: str


class AltBearBreakdownV1:
    NAME = "alt_bear_breakdown_v1"
    DEFAULT_PARAMS = {
        "BREAKDOWN_LOOKBACK_BARS": 20,
        "VOLUME_RATIO_MIN": 2.0,
        "RSI_MAX": 45.0,
        "EMA_FAST": 50,
        "EMA_SLOW": 200,
        "EMA_TREND": 20,
        "SL_ATR_MULT": 1.0,
        "TP1_ATR_MULT": 1.5,
        "TP2_ATR_MULT": 3.0,
        "TRAIL_ATR_MULT": 2.0,
        "TIME_STOP_BARS_5M": 60,
        "RISK_PCT": 0.7,
        "MAX_OPEN_TRADES": 2,
        "ALLOWED_REGIMES": "bear_trend,bear_chop",
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,SUIUSDT",
    }

    def __init__(self, params: Optional[dict] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

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

    def evaluate(self, bars, regime, symbol, open_positions=0, panic_mode=False):
        if len(bars) < 220:
            return None
        if panic_mode:
            return None  # cross-asset hedge already reduce-only

        allowed_regimes = [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]
        if regime not in allowed_regimes:
            return None

        allowlist = [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]
        if symbol not in allowlist:
            return None

        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        lookback = int(self.params["BREAKDOWN_LOOKBACK_BARS"])
        prev_window = bars[-lookback - 1:-1]
        prev_low = min(b["low"] for b in prev_window)
        current_close = closes[-1]

        if current_close >= prev_low:
            return None

        avg_vol = sum(b["volume"] for b in prev_window) / lookback
        if avg_vol <= 0 or bars[-1]["volume"] < float(self.params["VOLUME_RATIO_MIN"]) * avg_vol:
            return None

        r = self._rsi(closes)
        if r > float(self.params["RSI_MAX"]):
            return None

        ema_fast = self._ema(closes, int(self.params["EMA_FAST"]))
        ema_slow = self._ema(closes, int(self.params["EMA_SLOW"]))
        ema_trend = self._ema(closes, int(self.params["EMA_TREND"]))
        if not all([ema_fast, ema_slow, ema_trend]):
            return None

        if ema_fast >= ema_slow:
            return None  # not in downtrend
        if current_close >= ema_trend:
            return None  # not below short EMA

        a = self._atr(highs, lows, closes)
        if a <= 0:
            return None

        sl = current_close + float(self.params["SL_ATR_MULT"]) * a
        tp1 = current_close - float(self.params["TP1_ATR_MULT"]) * a
        tp2 = current_close - float(self.params["TP2_ATR_MULT"]) * a

        rationale = (
            f"Bear breakdown < {lookback}-bar low ({prev_low:.4f}), "
            f"vol×{bars[-1]['volume']/avg_vol:.1f}, RSI {r:.1f}, "
            f"EMA50({ema_fast:.4f}) < EMA200({ema_slow:.4f}), "
            f"close {current_close:.4f} < EMA20 {ema_trend:.4f}, regime={regime}"
        )

        return BearBreakdownSignal(
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
    random.seed(7)
    bars = []
    price = 100.0
    # Симулируем downtrend
    for i in range(250):
        ch = random.gauss(-0.15, 0.4)  # bearish drift
        price = max(20, price + ch)
        bars.append({
            "ts": i,
            "open": price + random.gauss(0, 0.1),
            "high": price + abs(random.gauss(0, 0.2)),
            "low": price - abs(random.gauss(0, 0.2)),
            "close": price,
            "volume": random.uniform(80, 150),
        })
    # Force breakdown на последнем баре
    bars[-1]["close"] = min(b["low"] for b in bars[-21:-1]) * 0.98
    bars[-1]["low"] = bars[-1]["close"]
    bars[-1]["volume"] = 400

    strat = AltBearBreakdownV1()
    sig = strat.evaluate(bars, regime="bear_trend", symbol="BTCUSDT")
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP1 {sig.tp1:.4f} TP2 {sig.tp2:.4f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (smoke test)")
