"""RESEARCH-ONLY: sloped break -> retest strategy (запрос владельца 2026-07-20).

Идея: наклонный уровень (поддержка из растущих lows или сопротивление из
падающих highs), подтверждённый минимум ТРЕМЯ пивотами, ломается закрытым
баром -> ждём ретест сломанной линии -> вход по отбойной свече от линии.

Каузальность:
- линии фитятся ТОЛЬКО на закрытых 1h барах (KlineStore отдаёт closed-only);
- пивот подтверждается только после `pivot_lr` правых закрытых баров
  (гарантируется тем, что pivot_highs/lows не берут края);
- >=3 пивотов, r2-порог, unbroken-проверка до пробоя (контракт
  bot/sloped_level_snapshot_v1, упрощённый для скорости массового поиска);
- вход на СЛЕДУЮЩЕМ open (entry_on_next_open в станции).

НЕ live. НЕ прод. Только research_lab поиск с тройным гейтом.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.market_context import fit_line, pivot_highs, pivot_lows
from strategies.signals import TradeSignal

TS, O, H, L, C = 0, 1, 2, 3, 4
_HOUR_MS = 3600_000.0


def _f(row, i):
    return float(row[i])


class SlopedBreakRetest:
    """Одна сторона на инстанс: side='short' (пробой поддержки вниз)
    или side='long' (пробой сопротивления вверх)."""

    def __init__(
        self,
        side: str = "short",
        pivot_lr: int = 3,
        lookback_1h: int = 240,
        min_pivots: int = 3,
        max_pivots: int = 4,
        min_r2: float = 0.85,
        min_slope_atr: float = 0.03,   # |наклон|/час >= доля ATR: реально наклонная, не горизонталь
        break_buf: float = 0.25,       # пробой = close за линию на buf*ATR
        retest_tol: float = 0.30,      # ретест = экстремум бара в tol*ATR от линии
        sl_buf: float = 0.60,
        rr: float = 2.0,
        wick_frac: float = 0.25,
        max_wait_h: float = 36.0,
        time_stop_bars: int = 96,
        refit_bars: int = 12,          # рефит линии раз в час (12 x 5m)
        min_risk_pct: float = 0.004,
        entry_style: str = "reject",   # reject=отбойная свеча | touch=касание+закрытие на нашей стороне
        sl_mode: str = "line",         # line=за линией | tight=0.8*ATR от входа
    ):
        if side not in ("short", "long"):
            raise ValueError("side must be short|long")
        self.side = side
        self.pivot_lr = int(pivot_lr)
        self.lookback_1h = int(lookback_1h)
        self.min_pivots = int(min_pivots)
        self.max_pivots = int(max_pivots)
        self.min_r2 = float(min_r2)
        self.min_slope_atr = float(min_slope_atr)
        self.break_buf = float(break_buf)
        self.retest_tol = float(retest_tol)
        self.sl_buf = float(sl_buf)
        self.rr = float(rr)
        self.wick_frac = float(wick_frac)
        self.max_wait_ms = float(max_wait_h) * _HOUR_MS
        self.time_stop_bars = int(time_stop_bars)
        self.refit_bars = max(1, int(refit_bars))
        self.min_risk_pct = float(min_risk_pct)
        self.entry_style = entry_style
        self.sl_mode = sl_mode

        self._bars = 0
        self._line = None          # dict: slope_h, b, t0, atr, pivot_key
        self._armed = None         # dict: line + break_ts
        self._consumed = set()     # pivot_key линий, по которым уже был пробой/сделка

    # ---- line fitting on closed 1h bars ----
    def _refit(self, store):
        rows = store.fetch_klines(store.symbol, "60", self.lookback_1h) or []
        if len(rows) < max(40, self.pivot_lr * 2 + self.min_pivots * 3):
            self._line = None
            return
        # ATR(14) на 1h
        trs = []
        for i in range(len(rows) - 14, len(rows)):
            hi, lo, pc = _f(rows[i], H), _f(rows[i], L), _f(rows[i - 1], C)
            trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        atr = sum(trs) / 14.0
        if atr <= 0:
            self._line = None
            return

        if self.side == "short":
            pivots = pivot_lows(rows, left=self.pivot_lr, right=self.pivot_lr)
        else:
            pivots = pivot_highs(rows, left=self.pivot_lr, right=self.pivot_lr)
        if len(pivots) < self.min_pivots:
            self._line = None
            return
        sel = pivots[-self.max_pivots:]
        if len(sel) < self.min_pivots:
            self._line = None
            return

        t0 = float(sel[0]["ts"])
        pts = [((float(p["ts"]) - t0) / _HOUR_MS, float(p["price"])) for p in sel]
        slope, b, r2 = fit_line(pts)
        if not (slope == slope and b == b):  # NaN guard
            self._line = None
            return
        if r2 < self.min_r2 or abs(slope) < self.min_slope_atr * atr:
            self._line = None
            return
        # линия должна быть НЕ сломана closed-close до текущего момента
        first_idx = sel[0]["idx"]
        tol = 0.05 * atr
        for i in range(first_idx, len(rows)):
            x = (_f(rows[i], TS) - t0) / _HOUR_MS
            lv = slope * x + b
            cl = _f(rows[i], C)
            if self.side == "short" and cl < lv - tol:
                self._line = None
                return
            if self.side == "long" and cl > lv + tol:
                self._line = None
                return

        key = tuple(int(p["ts"]) for p in sel)
        if key in self._consumed:
            self._line = None
            return
        self._line = {"slope_h": slope, "b": b, "t0": t0, "atr": atr, "key": key}

    def _line_value(self, line, ts_ms: float) -> float:
        return line["slope_h"] * ((float(ts_ms) - line["t0"]) / _HOUR_MS) + line["b"]

    # ---- per closed 5m bar ----
    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
        self._bars += 1
        ts_ms = float(ts_ms)

        if self._armed is None:
            if self._bars % self.refit_bars == 1 or self._line is None:
                self._refit(store)
            line = self._line
            if line is None:
                return None
            lv = self._line_value(line, ts_ms)
            atr = line["atr"]
            if self.side == "short" and c < lv - self.break_buf * atr:
                self._armed = dict(line, break_ts=ts_ms)
                self._line = None
            elif self.side == "long" and c > lv + self.break_buf * atr:
                self._armed = dict(line, break_ts=ts_ms)
                self._line = None
            return None

        # состояние armed: ждём ретест сломанной линии
        ar = self._armed
        atr = ar["atr"]
        lv = self._line_value(ar, ts_ms)

        if ts_ms - ar["break_ts"] > self.max_wait_ms:
            self._consumed.add(ar["key"])
            self._armed = None
            return None

        rng = max(h - l, 1e-12)
        if self.side == "short":
            # reclaim обратно над линию = отмена сетапа
            if c > lv + self.break_buf * atr:
                self._consumed.add(ar["key"])
                self._armed = None
                return None
            touched = h >= lv - self.retest_tol * atr
            if self.entry_style == "touch":
                rejected = c < lv
            else:
                rejected = c < lv and (h - max(o, c)) >= self.wick_frac * rng
            if touched and rejected:
                entry = c
                if self.sl_mode == "tight":
                    sl = entry + 0.8 * atr
                else:
                    sl = max(h, lv + self.sl_buf * atr)
                risk = sl - entry
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry - self.rr * risk
                self._consumed.add(ar["key"])
                self._armed = None
                return TradeSignal(
                    strategy="sbr", symbol=store.symbol, side="short",
                    entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                    time_stop_bars=self.time_stop_bars,
                    reason="sloped_support_break_retest",
                )
        else:
            if c < lv - self.break_buf * atr:
                self._consumed.add(ar["key"])
                self._armed = None
                return None
            touched = l <= lv + self.retest_tol * atr
            if self.entry_style == "touch":
                rejected = c > lv
            else:
                rejected = c > lv and (min(o, c) - l) >= self.wick_frac * rng
            if touched and rejected:
                entry = c
                if self.sl_mode == "tight":
                    sl = entry - 0.8 * atr
                else:
                    sl = min(l, lv - self.sl_buf * atr)
                risk = entry - sl
                if risk <= 0 or risk / entry < self.min_risk_pct:
                    return None
                tp = entry + self.rr * risk
                self._consumed.add(ar["key"])
                self._armed = None
                return TradeSignal(
                    strategy="sbr", symbol=store.symbol, side="long",
                    entry=entry, sl=sl, tp=tp, tps=[tp], tp_fracs=[1.0],
                    time_stop_bars=self.time_stop_bars,
                    reason="sloped_resistance_break_retest",
                )
        return None
