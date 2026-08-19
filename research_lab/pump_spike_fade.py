"""RESEARCH-ONLY: pump spike fade для movers (2026-07-21).

SHORT: вертикальный памп (ret за lookback > spike_pct) + признаки выдоха на ЗАКРЫТОМ
5m баре (верхний фитиль + закрытие ниже открытия ИЛИ откат от хая >= retrace) -> фейд
с коротким стопом за хай. LONG зеркально после дампа. Анти-нож: не входим, пока бар
обновляет экстремум. Один вход на спайк, кулдаун.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from strategies.signals import TradeSignal


class PumpSpikeFade:
    def __init__(self, side="short", lookback_bars=36, spike_pct=0.15,
                 retrace_min=0.25, sl_pad_pct=0.004, rr=1.8,
                 time_stop_bars=96, cooldown_bars=72, min_risk_pct=0.004):
        if side not in ("short", "long"):
            raise ValueError("side")
        self.side = side
        self.lb = int(lookback_bars)
        self.spike = float(spike_pct)
        self.retrace_min = float(retrace_min)
        self.sl_pad = float(sl_pad_pct)
        self.rr = float(rr)
        self.time_stop_bars = int(time_stop_bars)
        self.cooldown = int(cooldown_bars)
        self.min_risk_pct = float(min_risk_pct)
        self._bars = 0
        self._last = -10**9

    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
        self._bars += 1
        if self._bars - self._last < self.cooldown:
            return None
        rows = store.fetch_klines(store.symbol, "5", self.lb + 2) or []
        if len(rows) < self.lb + 1:
            return None
        base = float(rows[0][4])
        if base <= 0:
            return None
        if self.side == "short":
            hi = max(float(r[2]) for r in rows)
            ret = hi / base - 1.0
            if ret < self.spike:
                return None
            rng = max(h - l, 1e-12)
            retr = (hi - c) / max(hi - base, 1e-12)
            exhausted = (c < o and (h - max(o, c)) > 0.3 * rng) or retr >= self.retrace_min
            making_high = h >= hi  # бар ещё обновляет хай — нож
            if exhausted and not making_high:
                entry = c
                sl = hi * (1 + self.sl_pad)
                risk = sl - entry
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry - self.rr * risk
                self._last = self._bars
                return TradeSignal(strategy="psf", symbol=store.symbol, side="short",
                                   entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                   time_stop_bars=self.time_stop_bars, reason="pump_fade")
        else:
            lo = min(float(r[3]) for r in rows)
            ret = 1.0 - lo / base
            if ret < self.spike:
                return None
            rng = max(h - l, 1e-12)
            retr = (c - lo) / max(base - lo, 1e-12)
            exhausted = (c > o and (min(o, c) - l) > 0.3 * rng) or retr >= self.retrace_min
            making_low = l <= lo
            if exhausted and not making_low:
                entry = c
                sl = lo * (1 - self.sl_pad)
                risk = entry - sl
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry + self.rr * risk
                self._last = self._bars
                return TradeSignal(strategy="psf", symbol=store.symbol, side="long",
                                   entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                   time_stop_bars=self.time_stop_bars, reason="dump_fade")
        return None
