"""ACB1 — alt_channel_bounce_v1: two-sided channel bounce on the shared layer.

Owner wants bounces in flat, ascending AND descending channels, both sides:
- LONG off the lower channel line / support;
- SHORT off the upper channel line / resistance.

Thin strategy: consumes `bot.market_context.classify_channel` for the regime +
channel bounds and `horizontal_levels` to prefer real clusters, then requires a
rejection candle + volume confirmation at the touched edge. Target is the
opposite channel line (scaled), so geometry adapts to the channel width.

Regime gating (configurable):
- flat        -> both sides allowed (cleanest mean-reversion);
- ascending   -> long off lower preferred; short off upper allowed but near target;
- descending  -> short off upper preferred; long off lower allowed but near target.

Contract: maybe_signal(store, ts_ms, o, h, l, c, v) -> Optional[TradeSignal].
Research-only until WF gate. Namespace ACB1_*.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .signals import TradeSignal
from bot import market_context as mc


def _f(name, d):
    v = os.getenv(name)
    try:
        return float(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _i(name, d):
    v = os.getenv(name)
    try:
        return int(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _b(name, d):
    v = os.getenv(name)
    return d if v is None else str(v).strip().lower() in {"1", "true", "yes", "on"}


def _cset(name):
    raw = os.getenv(name, "") or ""
    return {x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()}


@dataclass
class AltChannelBounceV1Config:
    signal_tf: str = "60"
    lookback: int = 120
    atr_period: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    edge_pos: float = 0.25            # within 25% of a channel edge counts as a touch
    min_width_atr: float = 1.5        # ignore too-thin channels (noise)
    min_lower_wick_frac: float = 0.20 # long rejection: lower wick
    min_upper_wick_frac: float = 0.20 # short rejection: upper wick
    require_reject_close: bool = True # long: close>open ; short: close<open
    vol_avg_period: int = 20
    vol_mult: float = 1.2
    require_hvn: bool = False
    hvn_bins: int = 24
    hvn_top_n: int = 6
    hvn_confluence_atr: float = 0.7
    flat_slope_atr: float = 0.04
    allow_long: bool = True
    allow_short: bool = True
    allow_long_in_descending: bool = True
    allow_short_in_ascending: bool = True
    sl_atr_mult: float = 0.6
    target_frac: float = 0.85         # aim this fraction toward the opposite line
    countertrend_target_frac: float = 0.5  # nearer target against the channel slope
    tp1_frac: float = 0.6
    min_rr: float = 0.9
    min_stop_pct: float = 0.001
    max_stop_pct: float = 0.20
    trail_atr_mult: float = 1.0
    trail_activate_rr: float = 1.0
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.2
    cooldown_bars: int = 0
    config_refresh_bars: int = 50


def _load_cfg() -> AltChannelBounceV1Config:
    c = AltChannelBounceV1Config()
    c.signal_tf = os.getenv("ACB1_SIGNAL_TF", c.signal_tf)
    c.lookback = _i("ACB1_LOOKBACK", c.lookback)
    c.atr_period = _i("ACB1_ATR_PERIOD", c.atr_period)
    c.pivot_left = _i("ACB1_PIVOT_LEFT", c.pivot_left)
    c.pivot_right = _i("ACB1_PIVOT_RIGHT", c.pivot_right)
    c.edge_pos = _f("ACB1_EDGE_POS", c.edge_pos)
    c.min_width_atr = _f("ACB1_MIN_WIDTH_ATR", c.min_width_atr)
    c.min_lower_wick_frac = _f("ACB1_MIN_LOWER_WICK_FRAC", c.min_lower_wick_frac)
    c.min_upper_wick_frac = _f("ACB1_MIN_UPPER_WICK_FRAC", c.min_upper_wick_frac)
    c.require_reject_close = _b("ACB1_REQUIRE_REJECT_CLOSE", c.require_reject_close)
    c.vol_avg_period = _i("ACB1_VOL_AVG_PERIOD", c.vol_avg_period)
    c.vol_mult = _f("ACB1_VOL_MULT", c.vol_mult)
    c.require_hvn = _b("ACB1_REQUIRE_HVN", c.require_hvn)
    c.hvn_bins = _i("ACB1_HVN_BINS", c.hvn_bins)
    c.hvn_top_n = _i("ACB1_HVN_TOP_N", c.hvn_top_n)
    c.hvn_confluence_atr = _f("ACB1_HVN_CONFLUENCE_ATR", c.hvn_confluence_atr)
    c.flat_slope_atr = _f("ACB1_FLAT_SLOPE_ATR", c.flat_slope_atr)
    c.allow_long = _b("ACB1_ALLOW_LONG", c.allow_long)
    c.allow_short = _b("ACB1_ALLOW_SHORT", c.allow_short)
    c.allow_long_in_descending = _b("ACB1_ALLOW_LONG_IN_DESC", c.allow_long_in_descending)
    c.allow_short_in_ascending = _b("ACB1_ALLOW_SHORT_IN_ASC", c.allow_short_in_ascending)
    c.sl_atr_mult = _f("ACB1_SL_ATR_MULT", c.sl_atr_mult)
    c.target_frac = _f("ACB1_TARGET_FRAC", c.target_frac)
    c.countertrend_target_frac = _f("ACB1_CT_TARGET_FRAC", c.countertrend_target_frac)
    c.tp1_frac = _f("ACB1_TP1_FRAC", c.tp1_frac)
    c.min_rr = _f("ACB1_MIN_RR", c.min_rr)
    c.min_stop_pct = _f("ACB1_MIN_STOP_PCT", c.min_stop_pct)
    c.max_stop_pct = _f("ACB1_MAX_STOP_PCT", c.max_stop_pct)
    c.trail_atr_mult = _f("ACB1_TRAIL_ATR_MULT", c.trail_atr_mult)
    c.trail_activate_rr = _f("ACB1_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
    c.be_trigger_rr = _f("ACB1_BE_TRIGGER_RR", c.be_trigger_rr)
    c.be_lock_rr = _f("ACB1_BE_LOCK_RR", c.be_lock_rr)
    c.cooldown_bars = _i("ACB1_COOLDOWN_BARS", c.cooldown_bars)
    return c


class AltChannelBounceV1Strategy:
    def __init__(self, cfg: Optional[AltChannelBounceV1Config] = None):
        self.cfg = cfg or _load_cfg()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._bar_count = 0
        self.last_no_signal_reason = ""
        self._allow = _cset("ACB1_SYMBOL_ALLOWLIST")
        self._deny = _cset("ACB1_SYMBOL_DENYLIST")

    def _no(self, r: str) -> None:
        self.last_no_signal_reason = r

    def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v, ts_ms)
        self.last_no_signal_reason = ""
        self._bar_count += 1
        if self._bar_count % max(1, self.cfg.config_refresh_bars) == 0:
            self.cfg = _load_cfg()
            self._allow = _cset("ACB1_SYMBOL_ALLOWLIST")
            self._deny = _cset("ACB1_SYMBOL_DENYLIST")
        cfg = self.cfg

        sym = str(getattr(store, "symbol", "")).upper()
        if self._allow and sym not in self._allow:
            self._no("symbol_not_allowed"); return None
        if sym in self._deny:
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

        atr = mc.atr(rows, cfg.atr_period)
        if not (atr == atr and atr > 0):
            self._no("atr_invalid"); return None

        ch = mc.classify_channel(rows, atr_value=atr, lookback=cfg.lookback,
                                 pivot_left=cfg.pivot_left, pivot_right=cfg.pivot_right,
                                 flat_slope_atr=cfg.flat_slope_atr)
        upper = ch.get("upper_now"); lower = ch.get("lower_now")
        regime = ch.get("regime", "unknown")
        pos = ch.get("pos_in_channel")
        width_atr = ch.get("width_atr")
        if upper is None or lower is None or pos != pos or width_atr != width_atr:
            self._no("no_channel"); return None
        if width_atr < cfg.min_width_atr:
            self._no(f"channel_too_thin_{width_atr:.2f}"); return None

        last = rows[-1]
        price = last[4]
        rng = max(1e-12, last[2] - last[3])
        lower_wick = (min(last[1], last[4]) - last[3]) / rng
        upper_wick = (last[2] - max(last[1], last[4])) / rng
        vols = [r[5] for r in rows]
        avg_v = sum(vols[-cfg.vol_avg_period - 1:-1]) / max(1, len(vols[-cfg.vol_avg_period - 1:-1]))
        vol_ok = (avg_v <= 0) or (vols[-1] >= cfg.vol_mult * avg_v)

        side = None
        if pos <= cfg.edge_pos and cfg.allow_long:                       # near lower edge -> long
            if regime == "descending" and not cfg.allow_long_in_descending:
                self._no("long_blocked_descending"); return None
            if cfg.require_reject_close and last[4] < last[1]:
                self._no("long_no_reject_close"); return None
            if lower_wick < cfg.min_lower_wick_frac:
                self._no("long_weak_wick"); return None
            side = "long"
        elif pos >= (1.0 - cfg.edge_pos) and cfg.allow_short:            # near upper edge -> short
            if regime == "ascending" and not cfg.allow_short_in_ascending:
                self._no("short_blocked_ascending"); return None
            if cfg.require_reject_close and last[4] > last[1]:
                self._no("short_no_reject_close"); return None
            if upper_wick < cfg.min_upper_wick_frac:
                self._no("short_weak_wick"); return None
            side = "short"
        else:
            self._no(f"not_at_edge_pos_{pos:.2f}"); return None

        if not vol_ok:
            self._no("weak_volume"); return None

        # volume-density confluence on the touched edge
        edge_level = lower if side == "long" else upper
        hvns = mc.volume_hvns(rows, bins=cfg.hvn_bins, top_n=cfg.hvn_top_n)
        hvn_dist = mc.nearest_dist_atr(edge_level, hvns, atr)
        if cfg.require_hvn and hvn_dist > cfg.hvn_confluence_atr:
            self._no(f"no_hvn_confluence_{hvn_dist:.2f}"); return None

        countertrend = (side == "long" and regime == "descending") or \
                       (side == "short" and regime == "ascending")
        tfrac = cfg.countertrend_target_frac if countertrend else cfg.target_frac

        if side == "long":
            sl = lower - cfg.sl_atr_mult * atr
            risk = price - sl
            tp2 = price + tfrac * (upper - price)
        else:
            sl = upper + cfg.sl_atr_mult * atr
            risk = sl - price
            tp2 = price - tfrac * (price - lower)
        if risk <= 0:
            self._no("invalid_risk"); return None
        stop_pct = risk / max(1e-12, price)
        if stop_pct < cfg.min_stop_pct:
            self._no("stop_too_tight"); return None
        if stop_pct > cfg.max_stop_pct:
            self._no("stop_too_wide"); return None
        rr = abs(tp2 - price) / risk
        if rr < cfg.min_rr:
            self._no(f"rr_low_{rr:.2f}"); return None
        tp1 = price + (tp2 - price) * 0.5

        sig = TradeSignal(
            strategy="alt_channel_bounce_v1",
            symbol=store.symbol,
            side=side,
            entry=float(price),
            sl=float(sl),
            tp=float(tp2),
            tps=[float(tp1), float(tp2)],
            tp_fracs=[min(0.9, max(0.1, cfg.tp1_frac)),
                      max(0.05, 1.0 - min(0.9, max(0.1, cfg.tp1_frac)))],
            be_trigger_rr=max(0.0, cfg.be_trigger_rr),
            be_lock_rr=max(0.0, cfg.be_lock_rr),
            trailing_atr_mult=max(0.0, cfg.trail_atr_mult),
            trailing_atr_period=cfg.atr_period,
            trail_activate_rr=max(0.0, cfg.trail_activate_rr),
            reason=(f"acb1_{side} regime={regime} pos={pos:.2f} "
                    f"width={width_atr:.1f}atr ct={int(countertrend)} hvn={hvn_dist:.2f}"),
        )
        if not sig.validate():
            self._no("signal_invalid"); return None
        self._cooldown = max(0, cfg.cooldown_bars)
        return sig
