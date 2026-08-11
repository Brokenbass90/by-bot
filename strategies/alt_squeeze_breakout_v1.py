"""alt_squeeze_breakout_v1 — Bollinger Band squeeze breakout, multi-regime.

Универсальная стратегия. Ловит переход chop→trend в обе стороны.

Идея: когда BB width сжимается до низов последних 50 баров (squeeze) — рынок
накапливает энергию для импульса. Первый бар breakout с подтверждением
volume — это вход в направлении прорыва.

Эффективна потому что:
- Squeeze = периоды низкой волатильности, после которых обычно follows expansion
- Direction breakout даёт чистый signal без guessing
- Работает в любом regime (просто разные mults в allocator policy)

Логика:
    Entry (both sides):
        - BB width(20, 2σ) < min(BB width) последних 50 баров (squeeze)
        - Close пробивает BB upper (long) или lower (short)
        - Volume > 1.5× average последних 20 баров
        - ATR > N×typical_atr (рынок начал двигаться)
        - НЕ panic_mode

    Direction filter:
        - LONG в bull_trend / bull_chop ✅
        - LONG в bear_trend / bear_chop — только если EMA50 > EMA200 на 60m (false bull breakout)
        - SHORT в bear_trend / bear_chop ✅
        - SHORT в bull_trend / bull_chop — только если EMA50 < EMA200 на 60m

    Exit:
        - TP1: 1.5×ATR — close 40%, breakeven SL
        - TP2: BB middle (return-to-mean) — close 30%, trail 1.5×ATR
        - Hard SL: BB middle from другой стороны (если long — BB lower)
        - Time stop: 36 баров 5m (3 часа) если нет движения

    Sizing:
        - Risk 1.0% (стандартный — выскокий conviction)
        - Max 2 одновременно
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SqueezeBreakoutSignal:
    side: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    trail_atr_mult: float
    bb_width: float
    squeeze_pct: float  # как сильно сжато (% от max)
    rationale: str


class AltSqueezeBreakoutV1:
    NAME = "alt_squeeze_breakout_v1"
    DEFAULT_PARAMS = {
        "BB_PERIOD": 20,
        "BB_STD": 2.0,
        "SQUEEZE_LOOKBACK": 50,
        "VOLUME_RATIO_MIN": 1.5,
        "ATR_PERIOD": 14,
        "MIN_ATR_PCT": 0.3,  # минимум 0.3% движения
        "TP1_ATR_MULT": 1.5,
        "TRAIL_ATR_MULT": 1.5,
        "TIME_STOP_BARS_5M": 36,
        "RISK_PCT": 1.0,
        "MAX_OPEN_TRADES": 2,
        "ALLOW_LONGS": 1,
        "ALLOW_SHORTS": 1,
        "ALLOWED_REGIMES": "bull_trend,bull_chop,bear_trend,bear_chop",
        "SYMBOL_ALLOWLIST": "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,AVAXUSDT,SUIUSDT",
    }

    def __init__(self, params=None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        # 2026-08-05 (Claude): ДВА ДЕФЕКТА, из-за которых стратегию никогда
        # не удавалось проверить.
        #
        # 1) Гармошка не настраивалась из харнесса вообще: run_portfolio.py
        #    создаёт класс как AltSqueezeBreakoutV1() без params, поэтому
        #    SYMBOL_ALLOWLIST оставался жёстким списком из 8 символов,
        #    а свипы параметров были невозможны. Добавлен разбор env SQB1_*.
        #
        # 2) Сжатие проверялось на ТОМ ЖЕ баре, что и пробой. Но пробойный
        #    бар сам расширяет полосы, поэтому условие
        #    `bb_width <= min(последние 50) * 1.05` его же и отсекает.
        #    Замер на SOLUSDT, 39 928 баров:
        #        сжатие(текущий) И пробой   179
        #        сжатие(предыдущий) И пробой 557   <- втрое больше
        #    SQB1_SQUEEZE_CHECK_OFFSET=1 переносит проверку сжатия на бар
        #    ПЕРЕД пробоем. По умолчанию 0 — прежнее поведение не меняется.
        import os as _os
        for _k in list(self.params.keys()):
            _v = _os.getenv(f"SQB1_{_k}")
            if _v is not None and str(_v).strip() != "":
                self.params[_k] = _v
        _off = _os.getenv("SQB1_SQUEEZE_CHECK_OFFSET", "0")
        try:
            self.squeeze_check_offset = max(0, int(float(_off)))
        except Exception:
            self.squeeze_check_offset = 0

    @staticmethod
    def _sma(values, period):
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _std(values, period):
        if len(values) < period:
            return None
        sub = values[-period:]
        m = sum(sub) / period
        var = sum((v - m) ** 2 for v in sub) / period
        return var ** 0.5

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

    def _bb_width_at(self, closes, idx):
        """BB width на конкретном index (для расчёта squeeze history)."""
        period = int(self.params["BB_PERIOD"])
        if idx + 1 < period:
            return None
        sub = closes[:idx + 1]
        mid = self._sma(sub, period)
        std = self._std(sub, period)
        if mid is None or std is None:
            return None
        std_mult = float(self.params["BB_STD"])
        return (mid + std_mult * std) - (mid - std_mult * std)

    def evaluate(self, bars, regime, symbol, htf_60m_bias="neutral",
                 open_positions=0, panic_mode=False):
        period = int(self.params["BB_PERIOD"])
        lookback = int(self.params["SQUEEZE_LOOKBACK"])
        min_bars = max(period + lookback + 10, 100)
        if len(bars) < min_bars:
            return None
        if panic_mode:
            return None

        if regime not in [r.strip() for r in str(self.params["ALLOWED_REGIMES"]).split(",")]:
            return None
        if symbol not in [s.strip() for s in str(self.params["SYMBOL_ALLOWLIST"]).split(",")]:
            return None
        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        # Current BB
        std_mult = float(self.params["BB_STD"])
        bb_mid = self._sma(closes, period)
        bb_std = self._std(closes, period)
        if bb_mid is None or bb_std is None:
            return None
        bb_upper = bb_mid + std_mult * bb_std
        bb_lower = bb_mid - std_mult * bb_std
        bb_width = bb_upper - bb_lower

        # Historical BB widths
        off = int(getattr(self, "squeeze_check_offset", 0))
        anchor = len(closes) - 1 - off          # бар, на котором проверяем сжатие
        widths_history = []
        for idx in range(anchor - lookback, anchor):
            w = self._bb_width_at(closes, idx)
            if w is not None:
                widths_history.append(w)
        if not widths_history:
            return None
        min_width = min(widths_history)

        # Squeeze condition — при off>0 меряем ширину ДО пробойного бара,
        # иначе пробойный бар сам расширяет полосы и отсекает свой же сигнал
        squeeze_width = bb_width if off == 0 else self._bb_width_at(closes, anchor)
        if squeeze_width is None or squeeze_width > min_width * 1.05:
            return None
        max_width = max(widths_history)
        # A perfectly flat synthetic/listing segment has zero BB width across
        # the whole lookback.  It is not a squeeze breakout opportunity and
        # must not crash a portfolio-wide research run with 0/0.
        if max_width <= 0:
            return None
        squeeze_pct = squeeze_width / max_width * 100

        current_close = closes[-1]

        # ATR check
        a = self._atr(highs, lows, closes, int(self.params["ATR_PERIOD"]))
        atr_pct = a / current_close * 100 if current_close > 0 else 0
        if atr_pct < float(self.params["MIN_ATR_PCT"]):
            return None

        # Direction detection
        side = None
        if int(self.params["ALLOW_LONGS"]) and current_close > bb_upper:
            side = "long"
        elif int(self.params["ALLOW_SHORTS"]) and current_close < bb_lower:
            side = "short"
        else:
            return None

        # Volume confirmation
        avg_vol = sum(b["volume"] for b in bars[-period:-1]) / (period - 1)
        if avg_vol <= 0 or bars[-1]["volume"] < float(self.params["VOLUME_RATIO_MIN"]) * avg_vol:
            return None

        # Counter-regime direction filter
        # LONG breakout в bear regime → требуем bull bias на 60m
        if side == "long" and regime in ("bear_trend", "bear_chop"):
            if htf_60m_bias != "long":
                return None
        if side == "short" and regime in ("bull_trend", "bull_chop"):
            if htf_60m_bias != "short":
                return None

        # Build signal
        if side == "long":
            sl = bb_mid  # SL = середина BB
            tp1 = current_close + float(self.params["TP1_ATR_MULT"]) * a
            tp2 = current_close + 2.5 * a
        else:
            sl = bb_mid
            tp1 = current_close - float(self.params["TP1_ATR_MULT"]) * a
            tp2 = current_close - 2.5 * a

        rationale = (
            f"BB squeeze breakout {side}: width {bb_width:.4f} (min50 {min_width:.4f}, "
            f"squeeze {squeeze_pct:.0f}% of max), vol×{bars[-1]['volume']/avg_vol:.1f}, "
            f"ATR {atr_pct:.2f}%, regime={regime}, htf={htf_60m_bias}"
        )

        return SqueezeBreakoutSignal(
            side=side,
            entry=current_close,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            trail_atr_mult=float(self.params["TRAIL_ATR_MULT"]),
            bb_width=bb_width,
            squeeze_pct=squeeze_pct,
            rationale=rationale,
        )


if __name__ == "__main__":
    import random
    random.seed(13)
    bars = []
    price = 100.0
    # Сначала сжатие
    for i in range(80):
        ch = random.gauss(0, 0.1)  # очень тихо
        price = max(50, price + ch)
        bars.append({
            "ts": i,
            "open": price + random.gauss(0, 0.05),
            "high": price + abs(random.gauss(0, 0.08)),
            "low": price - abs(random.gauss(0, 0.08)),
            "close": price,
            "volume": random.uniform(80, 120),
        })
    # Затем сильный breakout
    last = bars[-1]["close"]
    bars.append({
        "ts": 80,
        "open": last,
        "high": last * 1.025,
        "low": last,
        "close": last * 1.024,
        "volume": 300,
    })

    strat = AltSqueezeBreakoutV1()
    sig = strat.evaluate(bars, regime="bull_chop", symbol="BTCUSDT", htf_60m_bias="long")
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP1 {sig.tp1:.4f} TP2 {sig.tp2:.4f}")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal (smoke test)")
