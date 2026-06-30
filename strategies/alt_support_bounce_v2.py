"""ASB2 — alt_support_bounce_v2: regime-aware support bounce on the shared layer.

Rehab of ASB1 (card #2). ASB1 failed because it read weak levels and ignored
channel regime. ASB2 is thin: it consumes the shared market-context layer
(`bot.market_context`) for real horizontal support clusters + channel regime, and
takes a LONG bounce only when:
  - price is tagging a real support (>= min_touches) or the lower channel line;
  - a rejection candle confirms (tagged the level, closed back up, lower wick);
  - volume confirms (current bar volume > vol_mult x average);
  - regime is flat / ascending (full target) or descending (near target only —
    owner: "отскоки берутся проще, но движения короче").

Contract matches the rest of the repo:
    Strategy(cfg).maybe_signal(store, ts_ms, o, h, l, c, v) -> Optional[TradeSignal]

Research-only until it passes the WF gate. Namespace ASB2_*, separate from ASB1.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .signals import TradeSignal
from bot import market_context as mc
from bot.adaptive_context import adaptive_params as _adaptive_params


def _env_float(name: str, d: float) -> float:
    v = os.getenv(name)
    try:
        return float(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _env_int(name: str, d: int) -> int:
    v = os.getenv(name)
    try:
        return int(str(v).strip()) if v is not None else d
    except (TypeError, ValueError):
        return d


def _env_bool(name: str, d: bool) -> bool:
    v = os.getenv(name)
    return d if v is None else str(v).strip().lower() in {"1", "true", "yes", "on"}


def _csv_set(name: str) -> set:
    raw = os.getenv(name, "") or ""
    return {x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()}


@dataclass
class AltSupportBounceV2Config:
    signal_tf: str = "60"
    lookback: int = 120
    atr_period: int = 14
    pivot_left: int = 2
    pivot_right: int = 2
    min_touches: int = 3
    level_tol_atr: float = 0.45        # how close to support counts as a tag
    max_entry_dist_atr: float = 0.60   # don't chase far from the level
    # rejection confirm
    require_close_up: bool = True      # close back above the level / green-ish
    min_lower_wick_frac: float = 0.20  # lower wick >= frac of bar range
    # volume confirm
    vol_avg_period: int = 20
    vol_mult: float = 1.2
    # volume-density (HVN) confluence — strong level = touches + volume node nearby
    require_hvn: bool = False
    hvn_bins: int = 24
    hvn_top_n: int = 6
    hvn_confluence_atr: float = 0.7
    # regime gate
    allow_flat: bool = True
    allow_ascending: bool = True
    allow_descending: bool = True
    flat_slope_atr: float = 0.04
    adaptive: bool = False        # ASB2_ADAPTIVE: regime-tune tol/touches/pivot + freshness
    max_age_bars: int = 0         # 0 = off; else drop supports older than N bars
    # risk geometry
    sl_atr_mult: float = 0.6
    tp1_rr: float = 1.0
    tp2_rr: float = 2.0
    tp1_frac: float = 0.6
    min_rr: float = 0.9
    min_stop_pct: float = 0.001
    max_stop_pct: float = 0.20
    # descending channel: take a nearer target (shorter move)
    descending_tp2_rr: float = 1.2
    trail_atr_mult: float = 1.0
    trail_activate_rr: float = 1.0
    be_trigger_rr: float = 1.0
    be_lock_rr: float = 0.2
    time_stop_bars: int = 0
    cooldown_bars: int = 0
    config_refresh_bars: int = 50


def _load_cfg() -> AltSupportBounceV2Config:
    c = AltSupportBounceV2Config()
    c.signal_tf = os.getenv("ASB2_SIGNAL_TF", c.signal_tf)
    c.lookback = _env_int("ASB2_LOOKBACK", c.lookback)
    c.atr_period = _env_int("ASB2_ATR_PERIOD", c.atr_period)
    c.pivot_left = _env_int("ASB2_PIVOT_LEFT", c.pivot_left)
    c.pivot_right = _env_int("ASB2_PIVOT_RIGHT", c.pivot_right)
    c.min_touches = _env_int("ASB2_MIN_TOUCHES", c.min_touches)
    c.level_tol_atr = _env_float("ASB2_LEVEL_TOL_ATR", c.level_tol_atr)
    c.max_entry_dist_atr = _env_float("ASB2_MAX_ENTRY_DIST_ATR", c.max_entry_dist_atr)
    c.require_close_up = _env_bool("ASB2_REQUIRE_CLOSE_UP", c.require_close_up)
    c.min_lower_wick_frac = _env_float("ASB2_MIN_LOWER_WICK_FRAC", c.min_lower_wick_frac)
    c.vol_avg_period = _env_int("ASB2_VOL_AVG_PERIOD", c.vol_avg_period)
    c.vol_mult = _env_float("ASB2_VOL_MULT", c.vol_mult)
    c.require_hvn = _env_bool("ASB2_REQUIRE_HVN", c.require_hvn)
    c.hvn_bins = _env_int("ASB2_HVN_BINS", c.hvn_bins)
    c.hvn_top_n = _env_int("ASB2_HVN_TOP_N", c.hvn_top_n)
    c.hvn_confluence_atr = _env_float("ASB2_HVN_CONFLUENCE_ATR", c.hvn_confluence_atr)
    c.allow_flat = _env_bool("ASB2_ALLOW_FLAT", c.allow_flat)
    c.allow_ascending = _env_bool("ASB2_ALLOW_ASCENDING", c.allow_ascending)
    c.allow_descending = _env_bool("ASB2_ALLOW_DESCENDING", c.allow_descending)
    c.flat_slope_atr = _env_float("ASB2_FLAT_SLOPE_ATR", c.flat_slope_atr)
    c.adaptive = _env_bool("ASB2_ADAPTIVE", c.adaptive)
    c.max_age_bars = _env_int("ASB2_MAX_AGE_BARS", c.max_age_bars)
    c.sl_atr_mult = _env_float("ASB2_SL_ATR_MULT", c.sl_atr_mult)
    c.tp1_rr = _env_float("ASB2_TP1_RR", c.tp1_rr)
    c.tp2_rr = _env_float("ASB2_TP2_RR", c.tp2_rr)
    c.tp1_frac = _env_float("ASB2_TP1_FRAC", c.tp1_frac)
    c.min_rr = _env_float("ASB2_MIN_RR", c.min_rr)
    c.min_stop_pct = _env_float("ASB2_MIN_STOP_PCT", c.min_stop_pct)
    c.max_stop_pct = _env_float("ASB2_MAX_STOP_PCT", c.max_stop_pct)
    c.descending_tp2_rr = _env_float("ASB2_DESCENDING_TP2_RR", c.descending_tp2_rr)
    c.trail_atr_mult = _env_float("ASB2_TRAIL_ATR_MULT", c.trail_atr_mult)
    c.trail_activate_rr = _env_float("ASB2_TRAIL_ACTIVATE_RR", c.trail_activate_rr)
    c.be_trigger_rr = _env_float("ASB2_BE_TRIGGER_RR", c.be_trigger_rr)
    c.be_lock_rr = _env_float("ASB2_BE_LOCK_RR", c.be_lock_rr)
    c.time_stop_bars = _env_int("ASB2_TIME_STOP_BARS", c.time_stop_bars)
    c.cooldown_bars = _env_int("ASB2_COOLDOWN_BARS", c.cooldown_bars)
    return c


class AltSupportBounceV2Strategy:
    def __init__(self, cfg: Optional[AltSupportBounceV2Config] = None):
        self.cfg = cfg or _load_cfg()
        self._cooldown = 0
        self._last_tf_ts: Optional[int] = None
        self._bar_count = 0
        self.last_no_signal_reason = ""
        self._allow = _csv_set("ASB2_SYMBOL_ALLOWLIST")
        self._deny = _csv_set("ASB2_SYMBOL_DENYLIST")

    def last_no_signal_reason_str(self) -> str:
        return self.last_no_signal_reason

    def _no(self, reason: str) -> None:
        self.last_no_signal_reason = reason

    def _regime_allowed(self, regime: str) -> bool:
        c = self.cfg
        return (
            (regime == "flat" and c.allow_flat)
            or (regime == "ascending" and c.allow_ascending)
            or (regime == "descending" and c.allow_descending)
        )

    def maybe_signal(self, store, ts_ms: int, o: float, h: float, l: float,
                     c: float, v: float = 0.0) -> Optional[TradeSignal]:
        _ = (o, h, l, c, v, ts_ms)
        self.last_no_signal_reason = ""
        self._bar_count += 1
        if self._bar_count % max(1, self.cfg.config_refresh_bars) == 0:
            self.cfg = _load_cfg()
            self._allow = _csv_set("ASB2_SYMBOL_ALLOWLIST")
            self._deny = _csv_set("ASB2_SYMBOL_DENYLIST")
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

        # closed-bar contract
        tf_ts = int(rows[-1][0])
        if self._last_tf_ts is None:
            self._last_tf_ts = tf_ts; self._no("first_bar"); return None
        if tf_ts == self._last_tf_ts:
            self._no("same_bar"); return None
        self._last_tf_ts = tf_ts

        atr = mc.atr(rows, cfg.atr_period)
        if not (atr == atr and atr > 0):
            self._no("atr_invalid"); return None
        price = rows[-1][4]

        ch = mc.classify_channel(rows, atr_value=atr, lookback=cfg.lookback,
                                 pivot_left=cfg.pivot_left, pivot_right=cfg.pivot_right,
                                 flat_slope_atr=cfg.flat_slope_atr)
        regime = ch.get("regime", "unknown")
        if not self._regime_allowed(regime):
            self._no(f"regime_blocked_{regime}"); return None

        # effective detector params (regime-adaptive if enabled)
        eff_tol, eff_touch, eff_pl, eff_pr = cfg.level_tol_atr, cfg.min_touches, cfg.pivot_left, cfg.pivot_right
        eff_max_age = cfg.max_age_bars
        if cfg.adaptive:
            ap = _adaptive_params((atr / price * 100.0) if price else 0.0, regime)
            eff_tol, eff_touch = ap["tol_atr"], ap["min_touches"]
            eff_pl, eff_pr, eff_max_age = ap["pivot_left"], ap["pivot_right"], ap["max_age_bars"]

        # nearest real horizontal support at/under price (freshness-filtered)
        last_idx = len(rows) - 1
        sup_levels = mc.horizontal_levels(rows, side="support", atr_value=atr,
                                          left=eff_pl, right=eff_pr,
                                          tol_atr=eff_tol, min_touches=eff_touch)
        cand = [c2 for c2 in sup_levels
                if c2["level"] <= price + eff_tol * atr
                and (eff_max_age <= 0 or (last_idx - c2["last_idx"]) <= eff_max_age)]
        # also consider the lower channel line as a dynamic support
        lower = ch.get("lower_now")
        support = None
        if cand:
            support = max(cand, key=lambda c2: c2["level"])["level"]
        if lower == lower and lower is not None and lower <= price + cfg.level_tol_atr * atr:
            support = max(support, lower) if support is not None else lower
        if support is None:
            self._no("no_support"); return None

        # price must be tagging the support (low near it) and not far above it
        bar_low = rows[-1][3]
        dist_atr = (price - support) / atr
        tag = (bar_low - support) <= cfg.level_tol_atr * atr
        if not tag:
            self._no("not_tagging_support"); return None
        if dist_atr > cfg.max_entry_dist_atr:
            self._no("entry_too_far"); return None

        # rejection candle confirm
        rng = max(1e-12, rows[-1][2] - rows[-1][3])
        lower_wick = (min(rows[-1][1], rows[-1][4]) - rows[-1][3]) / rng
        if cfg.require_close_up and rows[-1][4] < rows[-1][1]:
            self._no("no_close_up"); return None
        if lower_wick < cfg.min_lower_wick_frac:
            self._no("weak_lower_wick"); return None

        # volume confirm
        vols = [r[5] for r in rows]
        avg_v = sum(vols[-cfg.vol_avg_period - 1:-1]) / max(1, len(vols[-cfg.vol_avg_period - 1:-1]))
        if avg_v > 0 and vols[-1] < cfg.vol_mult * avg_v:
            self._no("weak_volume"); return None

        # volume-density confluence: is the support backed by an HVN node?
        hvns = mc.volume_hvns(rows, bins=cfg.hvn_bins, top_n=cfg.hvn_top_n)
        hvn_dist = mc.nearest_dist_atr(support, hvns, atr)
        if cfg.require_hvn and hvn_dist > cfg.hvn_confluence_atr:
            self._no(f"no_hvn_confluence_{hvn_dist:.2f}"); return None

        # risk geometry
        sl = support - cfg.sl_atr_mult * atr
        risk = price - sl
        if risk <= 0:
            self._no("invalid_risk"); return None
        stop_pct = risk / max(1e-12, price)
        if stop_pct < cfg.min_stop_pct:
            self._no("stop_too_tight"); return None
        if stop_pct > cfg.max_stop_pct:
            self._no("stop_too_wide"); return None

        tp2_rr = cfg.descending_tp2_rr if regime == "descending" else cfg.tp2_rr
        tp1 = price + cfg.tp1_rr * risk
        tp2 = price + tp2_rr * risk
        rr = (tp2 - price) / risk
        if rr < cfg.min_rr:
            self._no(f"rr_low_{rr:.2f}"); return None

        sig = TradeSignal(
            strategy="alt_support_bounce_v2",
            symbol=store.symbol,
            side="long",
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
            time_stop_bars=max(0, cfg.time_stop_bars),
            reason=(f"asb2_bounce regime={regime} sup={support:.6f} "
                    f"dist={dist_atr:.2f}atr wick={lower_wick:.2f} hvn={hvn_dist:.2f}"),
        )
        if not sig.validate():
            self._no("signal_invalid"); return None
        self._cooldown = max(0, cfg.cooldown_bars)
        return sig
