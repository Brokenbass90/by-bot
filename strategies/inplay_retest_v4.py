"""InPlay Retest V4 — clean rebuild of the owner's manual edge.

Fixes the V3 failures (PF 0.87): V3 entered LATE (on bar close, far from the
level -> wide stop -> broken RR). V4:
  - enters only when price is STILL AT the level (tight dist band) -> small stop;
  - asymmetric R:R (tp ~2.5R, sl ~1R) -> one win covers ~2-3 losses (owner's rule);
  - fresh levels only (age filter), volume confirm on the rejection/retest;
  - two setups: (A) bounce/retest off a fresh strong level; (B) retest of a
    recently BROKEN level (flip) in the breakout direction.

Thin: consumes bot.market_context (real levels, broken-level, freshness) +
adaptive params. Anti-lookahead via closed-bar contract. Research-only until WF.
Namespace IRV4_*.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .signals import TradeSignal
from bot import market_context as mc
from bot.adaptive_context import adaptive_params as _adaptive_params


def _f(n, d):
    v = os.getenv(n)
    try:
        return float(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _i(n, d):
    v = os.getenv(n)
    try:
        return int(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _b(n, d):
    v = os.getenv(n)
    return d if v is None else str(v).strip().lower() in {"1", "true", "yes", "on"}


def _cset(n):
    raw = os.getenv(n, "") or ""
    return {x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()}


@dataclass
class InplayRetestV4Config:
    signal_tf: str = "60"
    lookback: int = 120
    atr_period: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    min_touches: int = 3
    tol_atr: float = 0.40
    entry_band_atr: float = 0.30      # price must be THIS close to the level (tight = small stop)
    max_age_bars: int = 48            # freshness
    min_wick_frac: float = 0.20       # rejection wick
    require_reject_close: bool = True
    vol_avg_period: int = 20
    vol_mult: float = 1.3             # volume confirm on retest
    # asymmetric R:R (owner's edge): tight stop, runner take
    sl_atr_buffer: float = 0.5        # stop = level -/+ buffer*ATR (~1R)
    tp_rr: float = 2.5                # take at 2.5R
    tp1_rr: float = 1.5              # partial at 1.5R
    tp1_frac: float = 0.5
    min_stop_pct: float = 0.001
    max_stop_pct: float = 0.20
    enable_setup_b: bool = True       # broken-level retest (breakout continuation)
    allow_long: bool = True
    allow_short: bool = True
    adaptive: bool = False
    trail_atr_mult: float = 1.0
    trail_activate_rr: float = 1.5
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.2
    cooldown_bars: int = 0
    config_refresh_bars: int = 50


def _load_cfg() -> InplayRetestV4Config:
    c = InplayRetestV4Config()
    for name, attr, fn in [
        ("IRV4_SIGNAL_TF", "signal_tf", str), ("IRV4_LOOKBACK", "lookback", int),
        ("IRV4_ATR_PERIOD", "atr_period", int), ("IRV4_PIVOT_LEFT", "pivot_left", int),
        ("IRV4_PIVOT_RIGHT", "pivot_right", int), ("IRV4_MIN_TOUCHES", "min_touches", int),
        ("IRV4_TOL_ATR", "tol_atr", float), ("IRV4_ENTRY_BAND_ATR", "entry_band_atr", float),
        ("IRV4_MAX_AGE_BARS", "max_age_bars", int), ("IRV4_MIN_WICK_FRAC", "min_wick_frac", float),
        ("IRV4_VOL_AVG_PERIOD", "vol_avg_period", int), ("IRV4_VOL_MULT", "vol_mult", float),
        ("IRV4_SL_ATR_BUFFER", "sl_atr_buffer", float), ("IRV4_TP_RR", "tp_rr", float),
        ("IRV4_TP1_RR", "tp1_rr", float), ("IRV4_TP1_FRAC", "tp1_frac", float),
        ("IRV4_MIN_STOP_PCT", "min_stop_pct", float), ("IRV4_MAX_STOP_PCT", "max_stop_pct", float),
        ("IRV4_TRAIL_ATR_MULT", "trail_atr_mult", float), ("IRV4_TRAIL_ACTIVATE_RR", "trail_activate_rr", float),
        ("IRV4_BE_TRIGGER_RR", "be_trigger_rr", float), ("IRV4_BE_LOCK_RR", "be_lock_rr", float),
        ("IRV4_COOLDOWN_BARS", "cooldown_bars", int),
    ]:
        if fn is str:
            setattr(c, attr, os.getenv(name, getattr(c, attr)))
        elif fn is int:
            setattr(c, attr, _i(name, getattr(c, attr)))
        else:
            setattr(c, attr, _f(name, getattr(c, attr)))
    c.require_reject_close = _b("IRV4_REQUIRE_REJECT_CLOSE", c.require_reject_close)
    c.enable_setup_b = _b("IRV4_ENABLE_SETUP_B", c.enable_setup_b)
    c.allow_long = _b("IRV4_ALLOW_LONG", c.allow_long)
    c.allow_short = _b("IRV4_ALLOW_SHORT", c.allow_short)
    c.adaptive = _b("IRV4_ADAPTIVE", c.adaptive)
    return c


class InplayRetestV4Strategy:
    def __init__(self, cfg: Optional[InplayRetestV4Config] = None):
        self.cfg = cfg or _load_cfg()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._bar_count = 0
        self.last_no_signal_reason = ""
        self._allow = _cset("IRV4_SYMBOL_ALLOWLIST")
        self._deny = _cset("IRV4_SYMBOL_DENYLIST")

    def _no(self, r):
        self.last_no_signal_reason = r

    def _build(self, side, entry, sl, tp1, tp2, reason):
        cfg = self.cfg
        sig = TradeSignal(
            strategy="inplay_retest_v4", symbol=self._sym, side=side,
            entry=float(entry), sl=float(sl), tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[min(0.9, max(0.1, cfg.tp1_frac)), max(0.05, 1.0 - min(0.9, max(0.1, cfg.tp1_frac)))],
            be_trigger_rr=max(0.0, cfg.be_trigger_rr), be_lock_rr=max(0.0, cfg.be_lock_rr),
            trailing_atr_mult=max(0.0, cfg.trail_atr_mult), trailing_atr_period=cfg.atr_period,
            trail_activate_rr=max(0.0, cfg.trail_activate_rr), reason=reason)
        return sig if sig.validate() else None

    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v, ts_ms)
        self.last_no_signal_reason = ""
        self._bar_count += 1
        if self._bar_count % max(1, self.cfg.config_refresh_bars) == 0:
            self.cfg = _load_cfg()
            self._allow = _cset("IRV4_SYMBOL_ALLOWLIST"); self._deny = _cset("IRV4_SYMBOL_DENYLIST")
        cfg = self.cfg
        self._sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and self._sym not in self._allow:
            self._no("symbol_not_allowed"); return None
        if self._sym in self._deny:
            self._no("symbol_denied"); return None
        if self._cooldown > 0:
            self._cooldown -= 1; self._no("cooldown"); return None

        need = max(cfg.lookback + cfg.pivot_right + 3, cfg.vol_avg_period + 5, 30)
        rows = store.fetch_klines(store.symbol, cfg.signal_tf, need) or []
        if len(rows) < max(20, min(need, cfg.lookback)):
            self._no("history_short"); return None
        rows = [[float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                 float(r[5]) if len(r) > 5 else 0.0] for r in rows]

        tf_ts = int(rows[-1][0])
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts; self._no("first_bar"); return None
        if tf_ts == self._last_tf_ts:
            self._no("same_bar"); return None
        self._last_tf_ts = tf_ts

        atr = mc.atr(rows, cfg.atr_period, exclude_last=True)
        if not (atr == atr and atr > 0):
            self._no("atr_invalid"); return None
        bar = rows[-1]; price = bar[4]; last_idx = len(rows) - 1

        tol, touches, pl, pr, max_age = cfg.tol_atr, cfg.min_touches, cfg.pivot_left, cfg.pivot_right, cfg.max_age_bars
        if cfg.adaptive:
            ch = mc.classify_channel(rows, atr_value=atr)
            ap = _adaptive_params((atr / price * 100.0) if price else 0.0, ch.get("regime", "unknown"))
            tol, touches, pl, pr, max_age = ap["tol_atr"], ap["min_touches"], ap["pivot_left"], ap["pivot_right"], ap["max_age_bars"]

        res = mc.horizontal_levels(rows, side="resistance", atr_value=atr, left=pl, right=pr, tol_atr=tol, min_touches=touches)
        sup = mc.horizontal_levels(rows, side="support", atr_value=atr, left=pl, right=pr, tol_atr=tol, min_touches=touches)
        def fresh(c2): return (last_idx - c2["last_idx"]) <= max_age
        rng = max(1e-12, bar[2] - bar[3])
        lower_wick = (min(bar[1], bar[4]) - bar[3]) / rng
        upper_wick = (bar[2] - max(bar[1], bar[4])) / rng
        vols = [r[5] for r in rows]
        avg_v = sum(vols[-cfg.vol_avg_period - 1:-1]) / max(1, len(vols[-cfg.vol_avg_period - 1:-1]))
        vol_ok = (avg_v <= 0) or (vols[-1] >= cfg.vol_mult * avg_v)

        # ── Setup A: bounce/retest off a fresh strong level ─────────────────
        # LONG off support
        if cfg.allow_long:
            cands = [c2 for c2 in sup if fresh(c2) and bar[3] - c2["level"] <= cfg.entry_band_atr * atr and c2["level"] <= price]
            if cands:
                lvl = max(cands, key=lambda c2: c2["level"])["level"]
                if (not cfg.require_reject_close or bar[4] >= bar[1]) and lower_wick >= cfg.min_wick_frac and vol_ok:
                    sl = lvl - cfg.sl_atr_buffer * atr
                    risk = price - sl
                    if risk > 0:
                        sp = risk / price
                        if cfg.min_stop_pct <= sp <= cfg.max_stop_pct:
                            sig = self._build("long", price, sl, price + cfg.tp1_rr * risk, price + cfg.tp_rr * risk,
                                              f"irv4A_long lvl={lvl:.6f} rr={cfg.tp_rr}")
                            if sig:
                                self._cooldown = cfg.cooldown_bars; return sig
        # SHORT off resistance
        if cfg.allow_short:
            cands = [c2 for c2 in res if fresh(c2) and c2["level"] - bar[2] <= cfg.entry_band_atr * atr and c2["level"] >= price]
            if cands:
                lvl = min(cands, key=lambda c2: c2["level"])["level"]
                if (not cfg.require_reject_close or bar[4] <= bar[1]) and upper_wick >= cfg.min_wick_frac and vol_ok:
                    sl = lvl + cfg.sl_atr_buffer * atr
                    risk = sl - price
                    if risk > 0:
                        sp = risk / price
                        if cfg.min_stop_pct <= sp <= cfg.max_stop_pct:
                            sig = self._build("short", price, sl, price - cfg.tp1_rr * risk, price - cfg.tp_rr * risk,
                                              f"irv4A_short lvl={lvl:.6f} rr={cfg.tp_rr}")
                            if sig:
                                self._cooldown = cfg.cooldown_bars; return sig

        # ── Setup B: retest of a recently BROKEN level (flip) ───────────────
        if cfg.enable_setup_b and vol_ok:
            if cfg.allow_long:
                bsup = mc.nearest_broken_level(rows, res, price, atr, "support", max_age_bars=max_age)
                if bsup and abs(price - bsup["level"]) <= cfg.entry_band_atr * atr and bar[4] >= bar[1]:
                    lvl = bsup["level"]; sl = lvl - cfg.sl_atr_buffer * atr; risk = price - sl
                    if risk > 0 and cfg.min_stop_pct <= risk / price <= cfg.max_stop_pct:
                        sig = self._build("long", price, sl, price + cfg.tp1_rr * risk, price + cfg.tp_rr * risk,
                                          f"irv4B_long flip={lvl:.6f}")
                        if sig:
                            self._cooldown = cfg.cooldown_bars; return sig
            if cfg.allow_short:
                bres = mc.nearest_broken_level(rows, sup, price, atr, "resistance", max_age_bars=max_age)
                if bres and abs(price - bres["level"]) <= cfg.entry_band_atr * atr and bar[4] <= bar[1]:
                    lvl = bres["level"]; sl = lvl + cfg.sl_atr_buffer * atr; risk = sl - price
                    if risk > 0 and cfg.min_stop_pct <= risk / price <= cfg.max_stop_pct:
                        sig = self._build("short", price, sl, price - cfg.tp1_rr * risk, price - cfg.tp_rr * risk,
                                          f"irv4B_short flip={lvl:.6f}")
                        if sig:
                            self._cooldown = cfg.cooldown_bars; return sig

        self._no("no_setup"); return None
