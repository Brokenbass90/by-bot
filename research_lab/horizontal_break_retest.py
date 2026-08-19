"""RESEARCH-ONLY: horizontal break -> retest (сетапы POLYX/ESPORTS владельца, 2026-07-20).

LONG: закрепление ЗАКРЫТЫМ 5m баром над мульти-тач сопротивлением (1h кластеры
пивотов) -> короткий ретест уровня СВЕРХУ (держится) -> вход по продолжению.
SHORT зеркально: слом мульти-тач поддержки -> ретест снизу -> шорт.
Отличие от проваленного Pattern-Atlas 72h: вход не на пробое, а ТОЛЬКО после
удержанного ретеста; уровень обязан иметь >=min_touches касаний; reclaim = отмена.
Каузально: закрытые бары, вход next-open (в станции).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from level_dca_v1 import build_levels  # мульти-тач кластеры на 1h + ATR
from strategies.signals import TradeSignal


class HorizontalBreakRetest:
    def __init__(self, side="long", min_touches=2, lookback_1h=500,
                 break_buf=0.25, retest_tol=0.30, sl_buf=0.60, rr=2.0,
                 max_wait_h=36.0, time_stop_bars=192, refit_bars=12,
                 min_risk_pct=0.004):
        if side not in ("long", "short"):
            raise ValueError("side")
        self.side = side
        self.min_touches = int(min_touches)
        self.lookback_1h = int(lookback_1h)
        self.break_buf = float(break_buf)
        self.retest_tol = float(retest_tol)
        self.sl_buf = float(sl_buf)
        self.rr = float(rr)
        self.max_wait_ms = float(max_wait_h) * 3600_000.0
        self.time_stop_bars = int(time_stop_bars)
        self.refit_bars = max(1, int(refit_bars))
        self.min_risk_pct = float(min_risk_pct)
        self._bars = 0
        self._sup = []
        self._res = []
        self._atr = 0.0
        self._armed = None      # dict(level, break_ts)
        self._consumed = set()  # уровни, по которым уже был цикл

    def _refit(self, store):
        rows = store.fetch_klines(store.symbol, "60", self.lookback_1h) or []
        if len(rows) < 60:
            self._sup, self._res, self._atr = [], [], 0.0
            return
        h1 = [(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
              for r in rows]
        self._sup, self._res, self._atr = build_levels(
            h1, min_touches=self.min_touches, lookback=self.lookback_1h)

    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
        self._bars += 1
        ts_ms = float(ts_ms)
        if self._bars % self.refit_bars == 1:
            self._refit(store)
        atr = self._atr
        if atr <= 0:
            return None

        if self._armed is None:
            levels = self._res if self.side == "long" else self._sup
            for L_ in levels:
                key = round(L_, 10)
                if key in self._consumed:
                    continue
                if self.side == "long" and c > L_ + self.break_buf * atr and o <= L_ + self.break_buf * atr:
                    self._armed = {"level": L_, "key": key, "break_ts": ts_ms, "atr": atr}
                    return None
                if self.side == "short" and c < L_ - self.break_buf * atr and o >= L_ - self.break_buf * atr:
                    self._armed = {"level": L_, "key": key, "break_ts": ts_ms, "atr": atr}
                    return None
            return None

        ar = self._armed
        L_, atr0 = ar["level"], ar["atr"]
        if ts_ms - ar["break_ts"] > self.max_wait_ms:
            self._consumed.add(ar["key"]); self._armed = None
            return None

        if self.side == "long":
            if c < L_ - self.break_buf * atr0:      # провалились обратно = ложный пробой
                self._consumed.add(ar["key"]); self._armed = None
                return None
            touched = l <= L_ + self.retest_tol * atr0
            held = c > L_
            if touched and held:
                entry = c
                sl = min(l, L_ - self.sl_buf * atr0)
                risk = entry - sl
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry + self.rr * risk
                self._consumed.add(ar["key"]); self._armed = None
                return TradeSignal(strategy="hbr", symbol=store.symbol, side="long",
                                   entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                   time_stop_bars=self.time_stop_bars,
                                   reason="horizontal_break_retest_long")
        else:
            if c > L_ + self.break_buf * atr0:
                self._consumed.add(ar["key"]); self._armed = None
                return None
            touched = h >= L_ - self.retest_tol * atr0
            held = c < L_
            if touched and held:
                entry = c
                sl = max(h, L_ + self.sl_buf * atr0)
                risk = sl - entry
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry - self.rr * risk
                self._consumed.add(ar["key"]); self._armed = None
                return TradeSignal(strategy="hbr", symbol=store.symbol, side="short",
                                   entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                                   time_stop_bars=self.time_stop_bars,
                                   reason="horizontal_break_retest_short")
        return None
