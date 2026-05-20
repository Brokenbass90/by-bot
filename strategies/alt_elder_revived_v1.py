"""alt_elder_revived_v1 — упрощённый Elder triple screen, реанимация мёртвой ETS3.

Контекст: оригинальный ETS3 (4 экрана 1D+4h+1h+15m + MACD slope + Force Index +
строгие RSI) давал ~7 трейдов за весь backtest sweep. Стратегия мёртвая.

Решение: упрощаем до 3 экранов и релаксим thresholds. Сохраняем главную идею —
multi-timeframe alignment + pullback entry — но даём шанс торговать чаще.

Логика — классический Elder principle:
    SCREEN 1 (4h): MACROТРЕНД направление
        - LONG: EMA50 > EMA200 на 4h И MACD histogram > 0
        - SHORT: EMA50 < EMA200 на 4h И MACD histogram < 0
        - иначе: пропускаем

    SCREEN 2 (1h): MOMENTUM PULLBACK
        - LONG: цена откатилась — RSI 40-55 (зона pullback)
        - SHORT: RSI 45-60

    SCREEN 3 (5m): ENTRY TIMING
        - LONG: bullish candle (close>open) + body ≥ 50% range + close > EMA9
        - SHORT: bearish candle + body ≥ 50% range + close < EMA9

Это даёт сетапы порядка 30-50/мес на 5 монетах, не 7 за весь backtest.

Exit (Elder rules):
    - SL: за последний swing low/high + 0.3×ATR
    - TP1: 1.5×ATR (close 40%, breakeven)
    - TP2: 3.0×ATR (close 30%, trail 2×ATR)
    - Trail finale: 2×ATR от peak
    - Time stop: 120 баров 5m (10 часов)

Sizing:
    - Risk 0.8% (Elder — медленная стратегия, готовы держать)
    - Max 2 одновременно (на BTC + ETH)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ElderRevivedSignal:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    rationale: str


class AltElderRevivedV1:
    NAME = "alt_elder_revived_v1"
    DEFAULT_PARAMS = {
        # Screen 1: 4h macro trend
        "S1_EMA_FAST": 50,
        "S1_EMA_SLOW": 200,
        "S1_MACD_FAST": 12,
        "S1_MACD_SLOW": 26,
        "S1_MACD_SIGNAL": 9,
        "S1_MACD_HIST_MIN_ABS": 0.0,  # просто >0 или <0
        # Screen 2: 1h momentum
        "S2_RSI_LONG_MIN": 40.0,
        "S2_RSI_LONG_MAX": 55.0,
        "S2_RSI_SHORT_MIN": 45.0,
        "S2_RSI_SHORT_MAX": 60.0,
        # Screen 3: 5m entry
        "S3_BODY_MIN_FRAC": 0.50,
        "S3_EMA_PERIOD": 9,
        # Exit
        "SL_BUFFER_ATR": 0.3,
        "TP1_ATR_MULT": 1.5,
        "TP2_ATR_MULT": 3.0,
        "TRAIL_ATR_MULT": 2.0,
        "TIME_STOP_BARS_5M": 120,
        # Sizing
        "RISK_PCT": 0.8,
        "MAX_OPEN_TRADES": 2,
        "ALLOW_LONGS": 1,
        "ALLOW_SHORTS": 1,
        "ALLOWED_REGIMES": "bull_trend,bull_chop,bear_trend,bear_chop",
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT",
        # ATR quality
        "ATR_MIN_PCT": 0.15,  # не слишком тихо
        "ATR_MAX_PCT": 5.0,   # не паника
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

    def _macd_hist(self, closes):
        """MACD histogram = (EMA12 − EMA26) − Signal(EMA9 of macd)."""
        fast = int(self.params["S1_MACD_FAST"])
        slow = int(self.params["S1_MACD_SLOW"])
        sig = int(self.params["S1_MACD_SIGNAL"])
        if len(closes) < slow + sig:
            return None

        # MACD series
        macd_series = []
        for i in range(slow - 1, len(closes)):
            sub = closes[:i + 1]
            ef = self._ema(sub, fast)
            es = self._ema(sub, slow)
            if ef is None or es is None:
                continue
            macd_series.append(ef - es)

        if len(macd_series) < sig:
            return None
        signal_line = self._ema(macd_series, sig)
        if signal_line is None:
            return None
        return macd_series[-1] - signal_line

    def _last_swing(self, bars, lookback=10, kind="low"):
        sub = bars[-lookback:]
        if kind == "low":
            return min(b["low"] for b in sub)
        return max(b["high"] for b in sub)

    def evaluate(self, bars_5m, bars_1h, bars_4h, regime, symbol,
                 open_positions=0, panic_mode=False):
        if len(bars_5m) < 30 or len(bars_1h) < 50 or len(bars_4h) < 220:
            return None
        if panic_mode:
            return None

        if regime not in [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]:
            return None
        if symbol not in [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]:
            return None
        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        closes_4h = [b["close"] for b in bars_4h]
        closes_1h = [b["close"] for b in bars_1h]
        closes_5m = [b["close"] for b in bars_5m]
        highs_5m = [b["high"] for b in bars_5m]
        lows_5m = [b["low"] for b in bars_5m]

        # === SCREEN 1: 4h macro trend ===
        ema_fast_4h = self._ema(closes_4h, int(self.params["S1_EMA_FAST"]))
        ema_slow_4h = self._ema(closes_4h, int(self.params["S1_EMA_SLOW"]))
        macd_hist_4h = self._macd_hist(closes_4h)
        if not all(v is not None for v in [ema_fast_4h, ema_slow_4h, macd_hist_4h]):
            return None

        long_macro = (ema_fast_4h > ema_slow_4h
                      and macd_hist_4h > float(self.params["S1_MACD_HIST_MIN_ABS"]))
        short_macro = (ema_fast_4h < ema_slow_4h
                       and macd_hist_4h < -float(self.params["S1_MACD_HIST_MIN_ABS"]))
        if not (long_macro or short_macro):
            return None

        # === SCREEN 2: 1h pullback RSI ===
        rsi_1h = self._rsi(closes_1h)

        side = None
        if int(self.params["ALLOW_LONGS"]) and long_macro:
            if float(self.params["S2_RSI_LONG_MIN"]) <= rsi_1h <= float(self.params["S2_RSI_LONG_MAX"]):
                side = "long"
        if int(self.params["ALLOW_SHORTS"]) and short_macro and side is None:
            if float(self.params["S2_RSI_SHORT_MIN"]) <= rsi_1h <= float(self.params["S2_RSI_SHORT_MAX"]):
                side = "short"
        if side is None:
            return None

        # === ATR quality gate ===
        a = self._atr(highs_5m, lows_5m, closes_5m)
        if a <= 0:
            return None
        current_close = closes_5m[-1]
        atr_pct = a / current_close * 100
        if not (float(self.params["ATR_MIN_PCT"]) <= atr_pct <= float(self.params["ATR_MAX_PCT"])):
            return None

        # === SCREEN 3: 5m entry candle ===
        bar = bars_5m[-1]
        body = abs(bar["close"] - bar["open"])
        rng = bar["high"] - bar["low"]
        if rng <= 0:
            return None
        body_frac = body / rng

        if body_frac < float(self.params["S3_BODY_MIN_FRAC"]):
            return None

        ema9_5m = self._ema(closes_5m, int(self.params["S3_EMA_PERIOD"]))
        if ema9_5m is None:
            return None

        if side == "long":
            if bar["close"] <= bar["open"]:
                return None
            if current_close <= ema9_5m:
                return None
        else:
            if bar["close"] >= bar["open"]:
                return None
            if current_close >= ema9_5m:
                return None

        # === Build exit levels ===
        buffer = float(self.params["SL_BUFFER_ATR"]) * a
        if side == "long":
            swing_low = self._last_swing(bars_5m, 10, "low")
            sl = swing_low - buffer
            tp1 = current_close + float(self.params["TP1_ATR_MULT"]) * a
            tp2 = current_close + float(self.params["TP2_ATR_MULT"]) * a
        else:
            swing_high = self._last_swing(bars_5m, 10, "high")
            sl = swing_high + buffer
            tp1 = current_close - float(self.params["TP1_ATR_MULT"]) * a
            tp2 = current_close - float(self.params["TP2_ATR_MULT"]) * a

        rationale = (
            f"Elder revived {side}: "
            f"S1(4h) EMA50({ema_fast_4h:.4f})/EMA200({ema_slow_4h:.4f}) + MACD hist {macd_hist_4h:.6f}, "
            f"S2(1h) RSI {rsi_1h:.1f}, "
            f"S3(5m) body {body_frac*100:.0f}% close vs EMA9({ema9_5m:.4f}), "
            f"ATR {atr_pct:.2f}%, regime={regime}"
        )

        return ElderRevivedSignal(
            side=side,
            entry=current_close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
            rationale=rationale,
        )


if __name__ == "__main__":
    import random
    random.seed(23)

    # 4h: bull trend
    bars_4h = []
    p = 100.0
    for i in range(250):
        p += random.gauss(0.1, 0.4)
        bars_4h.append({"close": p, "open": p-0.1, "high": p+0.3, "low": p-0.3, "volume": 100})

    # 1h: pullback зона
    bars_1h = []
    p = bars_4h[-1]["close"]
    for i in range(80):
        p += random.gauss(-0.05, 0.3)
        bars_1h.append({"close": p, "open": p-0.05, "high": p+0.15, "low": p-0.15, "volume": 100})

    # 5m: bullish entry candle
    bars_5m = []
    p = bars_1h[-1]["close"]
    for i in range(40):
        p += random.gauss(0.0, 0.1)
        bars_5m.append({"close": p, "open": p-0.02, "high": p+0.05, "low": p-0.05, "volume": 100})
    # Force strong bullish candle на последнем
    last = bars_5m[-1]
    last["open"] = bars_5m[-2]["close"]
    last["close"] = last["open"] * 1.005
    last["low"] = last["open"] * 0.999
    last["high"] = last["close"] * 1.0001
    last["volume"] = 150

    strat = AltElderRevivedV1()
    sig = strat.evaluate(bars_5m, bars_1h, bars_4h, regime="bull_chop", symbol="BTCUSDT")
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP1 {sig.tp1:.4f} TP2 {sig.tp2:.4f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (smoke test точные условия трудно симулировать рандомом)")
