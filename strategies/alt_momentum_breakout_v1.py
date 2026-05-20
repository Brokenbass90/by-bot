"""alt_momentum_breakout_v1 — ловим сильные bull-импульсы которые ATT1 режет RSI-фильтром.

Контекст: ATT1 не торгует когда RSI > 55, потому что считает это перекупленностью.
Но 30-40% самых жирных bull-движений происходят именно при RSI 60-80 (TSLA, NVDA, MEME-pumps).
Эта стратегия — намеренно ловит «прорывающийся momentum» с wide trailing stop.

Логика:
    LONG entry:
        - Close > 20-bar high (breakout)
        - Volume > 2.5× average 20 bars
        - RSI 60-80 (sweet spot для пробоя)
        - Bull regime ONLY (bull_trend или bull_chop) — иначе skip
        - Не во время earnings/FOMC blackout
        - close > EMA50 (тренд цел)

    Exit logic:
        - Scaling-out:
            - TP1 на 1.5×ATR — закрыть 33%, ставим SL в безубыток (entry)
            - TP2 на 3×ATR — закрыть ещё 33%, тащим trailing
            - Остаток (33%) — trailing stop 2×ATR от peak
        - Hard SL: 1.2×ATR от entry
        - Time stop: 96 баров 5m (8 часов) если не движется ±0.5×ATR

    Position sizing:
        - Risk per trade = 0.7% equity (меньше чем дефолт 1%, потому что entry агрессивный)
        - Max 1 momentum trade одновременно
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MomentumBreakoutSignal:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    size_frac: float
    rationale: str


class AltMomentumBreakoutV1:
    """Strategy class — соответствует интерфейсу остальных alt_* стратегий бота.

    Ожидает что caller передаёт OHLCV bars и контекст (regime, allow_long, allow_short, atr).
    """

    NAME = "alt_momentum_breakout_v1"
    DEFAULT_PARAMS = {
        "BREAKOUT_LOOKBACK_BARS": 20,
        "VOLUME_RATIO_MIN": 2.5,
        "RSI_MIN": 60.0,
        "RSI_MAX": 80.0,
        "SL_ATR_MULT": 1.2,
        "TP1_ATR_MULT": 1.5,
        "TP2_ATR_MULT": 3.0,
        "TRAIL_ATR_MULT": 2.0,
        "TIME_STOP_BARS_5M": 96,
        "RISK_PCT": 0.7,
        "ALLOW_LONGS": 1,
        "ALLOW_SHORTS": 0,  # эта стратегия только longs
        "ALLOWED_REGIMES": "bull_trend,bull_chop",
        "MIN_PRICE_ABOVE_EMA50_PCT": 0.0,  # close должен быть >= EMA50
        "MAX_OPEN_TRADES": 1,
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,AVAXUSDT,SUIUSDT,DOGEUSDT,PEPEUSDT",
    }

    def __init__(self, params: Optional[dict] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}

    # === Indicators ===

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
        avg_g = gains / period
        avg_l = losses / period
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
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
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

    # === Main signal ===

    def evaluate(self, bars: list[dict], regime: str, symbol: str,
                 open_positions: int = 0) -> Optional[MomentumBreakoutSignal]:
        """Возвращает signal или None.

        bars — список dict с keys: ts, open, high, low, close, volume (oldest → newest).
        """
        if not bars or len(bars) < 60:
            return None

        if not int(self.params["ALLOW_LONGS"]):
            return None

        allowed_regimes = [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]
        if regime not in allowed_regimes:
            return None

        allowlist = [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]
        if allowlist and symbol not in allowlist:
            return None

        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        volumes = [b["volume"] for b in bars]

        lookback = int(self.params["BREAKOUT_LOOKBACK_BARS"])
        current_close = closes[-1]
        prev_window = bars[-lookback - 1:-1]
        if len(prev_window) < lookback:
            return None

        prev_high = max(b["high"] for b in prev_window)
        if current_close <= prev_high:
            return None  # no breakout

        # Volume check
        avg_vol = sum(b["volume"] for b in prev_window) / lookback
        if avg_vol <= 0:
            return None
        if bars[-1]["volume"] < float(self.params["VOLUME_RATIO_MIN"]) * avg_vol:
            return None

        # RSI window
        r = self._rsi(closes)
        if not (float(self.params["RSI_MIN"]) <= r <= float(self.params["RSI_MAX"])):
            return None

        # Trend filter
        ema50 = self._ema(closes, 50)
        if ema50 is None:
            return None
        if current_close < ema50 * (1.0 + float(self.params["MIN_PRICE_ABOVE_EMA50_PCT"]) / 100.0):
            return None

        # All checks passed — build signal
        a = self._atr(highs, lows, closes)
        if a <= 0:
            return None

        sl = current_close - float(self.params["SL_ATR_MULT"]) * a
        tp1 = current_close + float(self.params["TP1_ATR_MULT"]) * a
        tp2 = current_close + float(self.params["TP2_ATR_MULT"]) * a

        rationale = (
            f"Breakout > {lookback}-bar high ({prev_high:.2f}), "
            f"vol×{bars[-1]['volume']/avg_vol:.1f}, "
            f"RSI {r:.1f}, "
            f"close {current_close:.2f} > EMA50 {ema50:.2f}, "
            f"regime={regime}"
        )

        return MomentumBreakoutSignal(
            side="long",
            entry=current_close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
            size_frac=1.0,  # full size — sizing решает risk manager на основе RISK_PCT
            rationale=rationale,
        )

    # === Position management (called by bot's order manager) ===

    def manage_position(self, position: dict, current_bar: dict, atr_value: float,
                        bars_in_position: int) -> Optional[str]:
        """Возвращает action: 'partial_close_33' / 'breakeven_sl' / 'trail' / 'time_stop' / None."""
        entry = position["entry"]
        sl = position["sl"]
        tp1 = position.get("tp1")
        tp2 = position.get("tp2")
        tp1_done = position.get("tp1_done", False)
        tp2_done = position.get("tp2_done", False)
        high = current_bar["high"]
        low = current_bar["low"]

        # TP1
        if not tp1_done and tp1 and high >= tp1:
            return "partial_close_33_and_set_breakeven"

        # TP2
        if tp1_done and not tp2_done and tp2 and high >= tp2:
            return "partial_close_33_and_start_trail"

        # Time stop
        if bars_in_position >= int(self.params["TIME_STOP_BARS_5M"]):
            move_pct = abs(current_bar["close"] - entry) / entry * 100
            atr_pct = atr_value / entry * 100
            if move_pct < 0.5 * atr_pct:
                return "time_stop"

        # Trail (если уже в TP2 fase)
        if tp2_done:
            peak = position.get("peak", entry)
            new_peak = max(peak, high)
            new_stop = new_peak - float(self.params["TRAIL_ATR_MULT"]) * atr_value
            if new_stop > sl:
                return f"trail_to_{new_stop}"

        return None


# === Самотест ===

if __name__ == "__main__":
    # Минимальный smoke test
    import random
    random.seed(42)
    bars = []
    price = 100.0
    for i in range(100):
        ch = random.gauss(0, 0.5)
        price = max(50, price + ch)
        bars.append({
            "ts": i,
            "open": price,
            "high": price * (1 + abs(random.gauss(0, 0.005))),
            "low": price * (1 - abs(random.gauss(0, 0.005))),
            "close": price + random.gauss(0, 0.3),
            "volume": random.uniform(100, 200),
        })
    # Имитируем breakout на последнем баре
    bars[-1]["close"] = max(b["high"] for b in bars[-21:-1]) * 1.02
    bars[-1]["high"] = bars[-1]["close"]
    bars[-1]["volume"] = 600

    strat = AltMomentumBreakoutV1()
    sig = strat.evaluate(bars, regime="bull_chop", symbol="BTCUSDT")
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.2f}, SL {sig.sl:.2f}, TP1 {sig.tp1:.2f}, TP2 {sig.tp2:.2f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (smoke test)")
