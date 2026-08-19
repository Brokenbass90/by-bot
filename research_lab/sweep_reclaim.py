"""RESEARCH-ONLY: sweep -> reclaim (вынос стопов и возврат) — 2026-07-20.

LONG: фитиль ЗАКРЫТОГО 5m бара выносит мульти-тач поддержку (low < level - sweep*ATR),
но закрытие возвращается НАД уровень (reclaim) -> лонг с коротким стопом под фитиль.
SHORT зеркально над сопротивлением. Один цикл на уровень, каузально, next-open.
Это «умный флет» из ledger: реакция на снос ликвидности от КАЧЕСТВЕННЫХ уровней.
"""
from __future__ import annotations
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from level_dca_v1 import build_levels
from strategies.signals import TradeSignal


class SweepReclaim:
    def __init__(self, side="long", min_touches=2, lookback_1h=500,
                 sweep_atr=0.30, reclaim_buf=0.05, sl_buf=0.30, rr=2.0,
                 confirm_close=True, time_stop_bars=96, refit_bars=12,
                 min_risk_pct=0.003, cooldown_bars=36):
        if side not in ("long", "short"):
            raise ValueError("side")
        self.side = side; self.min_touches = int(min_touches)
        self.lookback_1h = int(lookback_1h); self.sweep_atr = float(sweep_atr)
        self.reclaim_buf = float(reclaim_buf); self.sl_buf = float(sl_buf)
        self.rr = float(rr); self.confirm_close = bool(confirm_close)
        self.time_stop_bars = int(time_stop_bars); self.refit_bars = max(1, int(refit_bars))
        self.min_risk_pct = float(min_risk_pct); self.cooldown_bars = int(cooldown_bars)
        self._bars = 0; self._sup = []; self._res = []; self._atr = 0.0
        self._last_trade_bar = -10**9

    def _refit(self, store):
        rows = store.fetch_klines(store.symbol, "60", self.lookback_1h) or []
        if len(rows) < 60:
            self._sup, self._res, self._atr = [], [], 0.0
            return
        h1 = [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows]
        self._sup, self._res, self._atr = build_levels(h1, min_touches=self.min_touches,
                                                       lookback=self.lookback_1h)

    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
        self._bars += 1
        if self._bars % self.refit_bars == 1:
            self._refit(store)
        atr = self._atr
        if atr <= 0 or self._bars - self._last_trade_bar < self.cooldown_bars:
            return None
        if self.side == "long":
            for L_ in self._sup:
                swept = l < L_ - self.sweep_atr * atr
                reclaimed = c > L_ + self.reclaim_buf * atr
                if swept and reclaimed and (not self.confirm_close or c > o):
                    entry = c
                    sl = l - self.sl_buf * atr
                    risk = entry - sl
                    if risk <= 0 or risk / entry < self.min_risk_pct:
                        continue
                    tp = entry + self.rr * risk
                    self._last_trade_bar = self._bars
                    return TradeSignal(strategy="swr", symbol=store.symbol, side="long",
                                       entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                       time_stop_bars=self.time_stop_bars,
                                       reason="sweep_reclaim_long")
        else:
            for L_ in self._res:
                swept = h > L_ + self.sweep_atr * atr
                reclaimed = c < L_ - self.reclaim_buf * atr
                if swept and reclaimed and (not self.confirm_close or c < o):
                    entry = c
                    sl = h + self.sl_buf * atr
                    risk = sl - entry
                    if risk <= 0 or risk / entry < self.min_risk_pct:
                        continue
                    tp = entry - self.rr * risk
                    self._last_trade_bar = self._bars
                    return TradeSignal(strategy="swr", symbol=store.symbol, side="short",
                                       entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                       time_stop_bars=self.time_stop_bars,
                                       reason="sweep_reclaim_short")
        return None
