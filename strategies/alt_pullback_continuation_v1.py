"""alt_pullback_continuation_v1 — функциональная замена мёртвого Elder triple screen.

Idea: подтверждённый тренд → откат к MA21 → отскок в направлении тренда → entry.
Работает в обе стороны в зависимости от тренда. Multi-timeframe фильтр encoded.

Elder работал на 1D + 4h + 1h + 15m с RSI + MACD + Force Index — слишком строго,
давал ~7 трейдов за весь sweep. Здесь упрощаем до 2 TF (60m тренд + 5m entry),
оставляем strict structural rules.

Логика:
    LONG entry:
        - Regime ∈ {bull_trend, bull_chop} ИЛИ htf_60m_bias=long
        - EMA50_60m > EMA200_60m (макротренд long)
        - На 5m: цена откатилась к EMA21 на 5m (within 0.3×ATR)
        - Bullish reversal candle: lower wick ≥ 50% range
        - RSI 35-55 (откат не overSold)
        - Vol ratio > 1.0× avg (подтверждение)

    SHORT entry: зеркально для bear

    Exit:
        - TP1: 2×ATR от entry — close 40%, breakeven
        - TP2: 4×ATR — close 30%, trail 2×ATR
        - SL: за reversal candle ± 0.3×ATR
        - Time stop: 96 баров 5m (8 часов)

    Sizing:
        - Risk 0.8% (медленная стратегия, готовы держать)
        - Max 3 одновременно
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PullbackContinuationSignal:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    rationale: str


class AltPullbackContinuationV1:
    NAME = "alt_pullback_continuation_v1"
    DEFAULT_PARAMS = {
        "EMA_ENTRY_PERIOD": 21,
        "EMA_FAST_HTF": 50,
        "EMA_SLOW_HTF": 200,
        "PROXIMITY_TO_EMA_ATR": 0.3,
        "REVERSAL_WICK_FRAC": 0.50,
        "RSI_LONG_MIN": 35.0,
        "RSI_LONG_MAX": 55.0,
        "RSI_SHORT_MIN": 45.0,
        "RSI_SHORT_MAX": 65.0,
        "VOL_RATIO_MIN": 1.0,
        "SL_BUFFER_ATR": 0.3,
        "TP1_ATR_MULT": 2.0,
        "TP2_ATR_MULT": 4.0,
        "TRAIL_ATR_MULT": 2.0,
        "TIME_STOP_BARS_5M": 96,
        "RISK_PCT": 0.8,
        "MAX_OPEN_TRADES": 3,
        "ALLOW_LONGS": 1,
        "ALLOW_SHORTS": 1,
        "ALLOWED_REGIMES": "bull_trend,bull_chop,bear_trend,bear_chop",
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,AVAXUSDT,SUIUSDT,LTCUSDT",
    }

    def __init__(self, params=None):
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

    def _detect_reversal_candle(self, bar, side):
        rng = bar["high"] - bar["low"]
        if rng <= 0:
            return False
        body = abs(bar["close"] - bar["open"])
        if side == "long":
            wick = min(bar["close"], bar["open"]) - bar["low"]
            # bullish: close > open AND lower wick > N% range
            if bar["close"] <= bar["open"]:
                return False
        else:
            wick = bar["high"] - max(bar["close"], bar["open"])
            # bearish: close < open AND upper wick > N% range
            if bar["close"] >= bar["open"]:
                return False
        return (wick / rng) >= float(self.params["REVERSAL_WICK_FRAC"])

    def evaluate(self, bars_5m, bars_60m, regime, symbol,
                 open_positions=0, panic_mode=False):
        if len(bars_5m) < 100 or len(bars_60m) < 220:
            return None
        if panic_mode:
            return None

        if regime not in [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]:
            return None
        if symbol not in [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]:
            return None
        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        closes_60m = [b["close"] for b in bars_60m]
        ema_fast_htf = self._ema(closes_60m, int(self.params["EMA_FAST_HTF"]))
        ema_slow_htf = self._ema(closes_60m, int(self.params["EMA_SLOW_HTF"]))
        if not ema_fast_htf or not ema_slow_htf:
            return None

        htf_long = ema_fast_htf > ema_slow_htf
        htf_short = ema_fast_htf < ema_slow_htf

        closes_5m = [b["close"] for b in bars_5m]
        highs_5m = [b["high"] for b in bars_5m]
        lows_5m = [b["low"] for b in bars_5m]

        ema_entry = self._ema(closes_5m, int(self.params["EMA_ENTRY_PERIOD"]))
        if ema_entry is None:
            return None

        a = self._atr(highs_5m, lows_5m, closes_5m)
        if a <= 0:
            return None

        current_close = closes_5m[-1]
        proximity = abs(current_close - ema_entry)
        if proximity > float(self.params["PROXIMITY_TO_EMA_ATR"]) * a:
            return None  # цена не у MA

        avg_vol = sum(b["volume"] for b in bars_5m[-21:-1]) / 20
        if avg_vol <= 0 or bars_5m[-1]["volume"] < float(self.params["VOL_RATIO_MIN"]) * avg_vol:
            return None

        r = self._rsi(closes_5m)
        bar = bars_5m[-1]

        # Try LONG
        if int(self.params["ALLOW_LONGS"]) and htf_long:
            if float(self.params["RSI_LONG_MIN"]) <= r <= float(self.params["RSI_LONG_MAX"]):
                if self._detect_reversal_candle(bar, "long"):
                    sl = bar["low"] - float(self.params["SL_BUFFER_ATR"]) * a
                    tp1 = current_close + float(self.params["TP1_ATR_MULT"]) * a
                    tp2 = current_close + float(self.params["TP2_ATR_MULT"]) * a
                    return PullbackContinuationSignal(
                        side="long",
                        entry=current_close,
                        sl=sl,
                        tp1=tp1,
                        tp2=tp2,
                        trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
                        rationale=f"HTF long bias (EMA50>EMA200 на 60m), 5m pullback к EMA21, "
                                  f"bullish reversal candle, RSI {r:.1f}, regime={regime}",
                    )

        # Try SHORT
        if int(self.params["ALLOW_SHORTS"]) and htf_short:
            if float(self.params["RSI_SHORT_MIN"]) <= r <= float(self.params["RSI_SHORT_MAX"]):
                if self._detect_reversal_candle(bar, "short"):
                    sl = bar["high"] + float(self.params["SL_BUFFER_ATR"]) * a
                    tp1 = current_close - float(self.params["TP1_ATR_MULT"]) * a
                    tp2 = current_close - float(self.params["TP2_ATR_MULT"]) * a
                    return PullbackContinuationSignal(
                        side="short",
                        entry=current_close,
                        sl=sl,
                        tp1=tp1,
                        tp2=tp2,
                        trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
                        rationale=f"HTF short bias (EMA50<EMA200 на 60m), 5m pullback к EMA21, "
                                  f"bearish reversal candle, RSI {r:.1f}, regime={regime}",
                    )

        return None


if __name__ == "__main__":
    import random
    random.seed(17)

    # Bull HTF — 60m bars
    bars_60m = []
    price = 100.0
    for i in range(250):
        ch = random.gauss(0.05, 0.3)  # bullish drift
        price += ch
        bars_60m.append({"close": price, "open": price - 0.1, "high": price + 0.3, "low": price - 0.3, "volume": 100})

    # 5m pullback to EMA21 with bullish reversal
    bars_5m = []
    price = bars_60m[-1]["close"]
    for i in range(100):
        ch = random.gauss(0.01, 0.15)
        price += ch
        bars_5m.append({"open": price, "high": price+0.05, "low": price-0.05, "close": price, "volume": 100})
    # Pullback last 5 bars
    for j in range(95, 100):
        bars_5m[j]["close"] *= 0.997
    # Final bullish reversal candle
    last = bars_5m[-1]
    last["open"] = bars_5m[-2]["close"]
    last["low"] = last["open"] * 0.9985
    last["close"] = last["open"] * 1.002
    last["high"] = last["close"] * 1.0005
    last["volume"] = 150

    strat = AltPullbackContinuationV1()
    sig = strat.evaluate(bars_5m, bars_60m, regime="bull_chop", symbol="BTCUSDT")
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP1 {sig.tp1:.4f} TP2 {sig.tp2:.4f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (smoke test, точные условия трудно симулировать рандомом)")
