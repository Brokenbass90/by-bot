"""Research-only pivot-line break -> first retest -> structure confirmation.

V2 deliberately does not inherit the regression-channel geometry from SBR1.
It uses point-in-time confirmed pivots on completed 4h bars and a separate 15m
state machine.  Environment values are resolved once at construction.
"""
from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass
from typing import Any, Optional

from .signals import TradeSignal


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _csv_set(raw: str) -> set[str]:
    return {
        item.strip().upper()
        for item in str(raw or "").replace(";", ",").split(",")
        if item.strip()
    }


def _atr(rows: list[list], period: int) -> float:
    if len(rows) < period + 1:
        return float("nan")
    values: list[float] = []
    for idx in range(len(rows) - period, len(rows)):
        high = float(rows[idx][2])
        low = float(rows[idx][3])
        prev_close = float(rows[idx - 1][4])
        values.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(values) / len(values) if values else float("nan")


def _body_fraction(row: list) -> float:
    high, low = float(row[2]), float(row[3])
    return abs(float(row[4]) - float(row[1])) / max(1e-12, high - low)


def confirmed_pivots(
    values: list[float], *, mode: str, left: int, right: int
) -> list[tuple[int, float]]:
    """Return pivots whose right-hand confirmation bars are already present."""
    out: list[tuple[int, float]] = []
    for idx in range(max(1, left), len(values) - max(1, right)):
        value = values[idx]
        neighbours = values[idx - left:idx] + values[idx + 1:idx + right + 1]
        if mode == "high" and all(value > other for other in neighbours):
            out.append((idx, value))
        elif mode == "low" and all(value < other for other in neighbours):
            out.append((idx, value))
    return out


def _fit(points: list[tuple[int, float]]) -> tuple[float, float, float]:
    if len(points) < 2:
        return float("nan"), float("nan"), float("nan")
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    den = sum((x - x_mean) ** 2 for x in xs)
    if den <= 1e-12:
        return float("nan"), float("nan"), float("nan")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / den
    intercept = y_mean - slope * x_mean
    max_error = max(abs(y - (slope * x + intercept)) for x, y in zip(xs, ys))
    return slope, intercept, max_error


@dataclass(frozen=True)
class SlopedBreakRetestV2Config:
    line_tf: str = "240"
    trigger_tf: str = "15"
    line_lookback: int = 120
    trigger_lookback: int = 40
    atr_period: int = 14
    volume_period: int = 20
    pivot_left: int = 2
    pivot_right: int = 2
    min_pivots: int = 3
    max_pivots: int = 4
    max_pivot_age: int = 40
    min_slope_pct_day: float = 0.10
    max_slope_pct_day: float = 8.0
    max_fit_error_atr: float = 0.35
    post_fit_break_tolerance_atr: float = 0.15
    breakout_extension_atr: float = 0.25
    breakout_body_fraction: float = 0.55
    breakout_volume_multiple: float = 1.20
    retest_window_bars: int = 16
    retest_touch_atr: float = 0.20
    retest_hold_atr: float = 0.08
    invalidation_atr: float = 0.35
    structure_lookback: int = 2
    stop_buffer_atr: float = 0.20
    tp1_rr: float = 1.50
    tp2_rr: float = 3.00
    tp1_frac: float = 0.55
    tp2_frac: float = 0.25
    be_trigger_rr: float = 1.00
    trail_activate_rr: float = 1.50
    trail_atr_mult: float = 1.70
    time_stop_bars_5m: int = 288
    allow_longs: bool = True
    allow_shorts: bool = True
    symbol_allowlist: str = ""
    symbol_denylist: str = ""


def config_from_env() -> SlopedBreakRetestV2Config:
    defaults = SlopedBreakRetestV2Config()
    return SlopedBreakRetestV2Config(
        line_tf=os.getenv("SLBR2_LINE_TF", defaults.line_tf),
        trigger_tf=os.getenv("SLBR2_TRIGGER_TF", defaults.trigger_tf),
        line_lookback=_env_int("SLBR2_LINE_LOOKBACK", defaults.line_lookback),
        trigger_lookback=_env_int("SLBR2_TRIGGER_LOOKBACK", defaults.trigger_lookback),
        atr_period=_env_int("SLBR2_ATR_PERIOD", defaults.atr_period),
        volume_period=_env_int("SLBR2_VOLUME_PERIOD", defaults.volume_period),
        pivot_left=_env_int("SLBR2_PIVOT_LEFT", defaults.pivot_left),
        pivot_right=_env_int("SLBR2_PIVOT_RIGHT", defaults.pivot_right),
        min_pivots=_env_int("SLBR2_MIN_PIVOTS", defaults.min_pivots),
        max_pivots=_env_int("SLBR2_MAX_PIVOTS", defaults.max_pivots),
        max_pivot_age=_env_int("SLBR2_MAX_PIVOT_AGE", defaults.max_pivot_age),
        min_slope_pct_day=_env_float("SLBR2_MIN_SLOPE_PCT_DAY", defaults.min_slope_pct_day),
        max_slope_pct_day=_env_float("SLBR2_MAX_SLOPE_PCT_DAY", defaults.max_slope_pct_day),
        max_fit_error_atr=_env_float("SLBR2_MAX_FIT_ERROR_ATR", defaults.max_fit_error_atr),
        post_fit_break_tolerance_atr=_env_float(
            "SLBR2_POST_FIT_BREAK_TOLERANCE_ATR", defaults.post_fit_break_tolerance_atr
        ),
        breakout_extension_atr=_env_float(
            "SLBR2_BREAKOUT_EXTENSION_ATR", defaults.breakout_extension_atr
        ),
        breakout_body_fraction=_env_float(
            "SLBR2_BREAKOUT_BODY_FRACTION", defaults.breakout_body_fraction
        ),
        breakout_volume_multiple=_env_float(
            "SLBR2_BREAKOUT_VOLUME_MULTIPLE", defaults.breakout_volume_multiple
        ),
        retest_window_bars=_env_int("SLBR2_RETEST_WINDOW_BARS", defaults.retest_window_bars),
        retest_touch_atr=_env_float("SLBR2_RETEST_TOUCH_ATR", defaults.retest_touch_atr),
        retest_hold_atr=_env_float("SLBR2_RETEST_HOLD_ATR", defaults.retest_hold_atr),
        invalidation_atr=_env_float("SLBR2_INVALIDATION_ATR", defaults.invalidation_atr),
        structure_lookback=_env_int("SLBR2_STRUCTURE_LOOKBACK", defaults.structure_lookback),
        stop_buffer_atr=_env_float("SLBR2_STOP_BUFFER_ATR", defaults.stop_buffer_atr),
        tp1_rr=_env_float("SLBR2_TP1_RR", defaults.tp1_rr),
        tp2_rr=_env_float("SLBR2_TP2_RR", defaults.tp2_rr),
        tp1_frac=_env_float("SLBR2_TP1_FRAC", defaults.tp1_frac),
        tp2_frac=_env_float("SLBR2_TP2_FRAC", defaults.tp2_frac),
        be_trigger_rr=_env_float("SLBR2_BE_TRIGGER_RR", defaults.be_trigger_rr),
        trail_activate_rr=_env_float(
            "SLBR2_TRAIL_ACTIVATE_RR", defaults.trail_activate_rr
        ),
        trail_atr_mult=_env_float("SLBR2_TRAIL_ATR_MULT", defaults.trail_atr_mult),
        time_stop_bars_5m=_env_int("SLBR2_TIME_STOP_BARS_5M", defaults.time_stop_bars_5m),
        allow_longs=_env_bool("SLBR2_ALLOW_LONGS", defaults.allow_longs),
        allow_shorts=_env_bool("SLBR2_ALLOW_SHORTS", defaults.allow_shorts),
        symbol_allowlist=os.getenv("SLBR2_SYMBOL_ALLOWLIST", defaults.symbol_allowlist),
        symbol_denylist=os.getenv("SLBR2_SYMBOL_DENYLIST", defaults.symbol_denylist),
    )


def identify_breakout(rows: list[list], cfg: SlopedBreakRetestV2Config) -> Optional[dict[str, Any]]:
    """Identify one completed 4h breakout without using future bars."""
    need = max(cfg.atr_period + 2, cfg.volume_period + 2, 30)
    if len(rows) < need:
        return None
    atr_now = _atr(rows, cfg.atr_period)
    if not math.isfinite(atr_now) or atr_now <= 0:
        return None
    highs = [float(row[2]) for row in rows]
    lows = [float(row[3]) for row in rows]
    closes = [float(row[4]) for row in rows]
    current_idx = len(rows) - 1
    previous_idx = current_idx - 1
    volumes = [float(row[5] or 0.0) for row in rows]
    vol_hist = [value for value in volumes[-cfg.volume_period - 1:-1] if value > 0]
    vol_reference = statistics.median(vol_hist) if vol_hist else 0.0
    vol_ok = vol_reference <= 0 or volumes[-1] >= cfg.breakout_volume_multiple * vol_reference
    body_ok = _body_fraction(rows[-1]) >= cfg.breakout_body_fraction
    if not (vol_ok and body_ok):
        return None

    candidates: list[dict[str, Any]] = []
    for side, mode in (("long", "high"), ("short", "low")):
        if side == "long" and not cfg.allow_longs:
            continue
        if side == "short" and not cfg.allow_shorts:
            continue
        source = highs if mode == "high" else lows
        pivots = confirmed_pivots(
            source[:-1], mode=mode, left=cfg.pivot_left, right=cfg.pivot_right
        )
        pivots = [point for point in pivots if current_idx - point[0] <= cfg.max_pivot_age]
        points = pivots[-cfg.max_pivots:]
        if len(points) < cfg.min_pivots:
            continue
        slope, intercept, max_error = _fit(points)
        if not all(math.isfinite(value) for value in (slope, intercept, max_error)):
            continue
        if side == "long" and slope >= 0:
            continue
        if side == "short" and slope <= 0:
            continue
        line_now = slope * current_idx + intercept
        line_prev = slope * previous_idx + intercept
        slope_pct_day = abs(slope) * 6.0 / max(1e-12, abs(line_now)) * 100.0
        if not (cfg.min_slope_pct_day <= slope_pct_day <= cfg.max_slope_pct_day):
            continue
        if max_error > cfg.max_fit_error_atr * atr_now:
            continue

        last_pivot_idx = points[-1][0]
        post_fit = range(last_pivot_idx + cfg.pivot_right + 1, current_idx)
        tolerance = cfg.post_fit_break_tolerance_atr * atr_now
        if side == "long" and any(closes[idx] > slope * idx + intercept + tolerance for idx in post_fit):
            continue
        if side == "short" and any(closes[idx] < slope * idx + intercept - tolerance for idx in post_fit):
            continue

        extension = cfg.breakout_extension_atr * atr_now
        if side == "long":
            crossed = closes[previous_idx] <= line_prev + tolerance and closes[current_idx] >= line_now + extension
        else:
            crossed = closes[previous_idx] >= line_prev - tolerance and closes[current_idx] <= line_now - extension
        if not crossed:
            continue
        candidates.append(
            {
                "side": side,
                "line_level": line_now,
                "slope_per_4h_bar": slope,
                "atr": atr_now,
                "break_bar_ts": int(float(rows[-1][0])),
                "pivot_count": len(points),
                "slope_pct_day": slope_pct_day,
            }
        )
    return candidates[0] if len(candidates) == 1 else None


class SlopedBreakRetestV2Strategy:
    STRATEGY_NAME = "sloped_break_retest_v2"

    def __init__(self, cfg: Optional[SlopedBreakRetestV2Config] = None):
        self.cfg = cfg or config_from_env()
        self._allow = _csv_set(self.cfg.symbol_allowlist)
        self._deny = _csv_set(self.cfg.symbol_denylist)
        self._last_line_ts: Optional[int] = None
        self._last_trigger_ts: Optional[int] = None
        self._pending: Optional[dict[str, Any]] = None
        self.last_no_signal_reason = "initializing"

    def _projected_level(self, trigger_ts: int) -> float:
        assert self._pending is not None
        elapsed_ms = max(0, int(trigger_ts) - int(self._pending["visible_ts"]))
        bars_4h = elapsed_ms / float(4 * 60 * 60 * 1000)
        return float(self._pending["line_level"]) + bars_4h * float(
            self._pending["slope_per_4h_bar"]
        )

    def _make_signal(self, symbol: str, side: str, entry: float, stop: float, meta: dict[str, Any]) -> Optional[TradeSignal]:
        risk = entry - stop if side == "long" else stop - entry
        if risk <= 0:
            return None
        tp1 = entry + self.cfg.tp1_rr * risk if side == "long" else entry - self.cfg.tp1_rr * risk
        tp2 = entry + self.cfg.tp2_rr * risk if side == "long" else entry - self.cfg.tp2_rr * risk
        signal = TradeSignal(
            strategy=self.STRATEGY_NAME,
            symbol=symbol,
            side=side,
            entry=entry,
            sl=stop,
            tp=tp2,
            tps=[tp1, tp2],
            tp_fracs=[self.cfg.tp1_frac, self.cfg.tp2_frac],
            be_trigger_rr=self.cfg.be_trigger_rr,
            trail_activate_rr=self.cfg.trail_activate_rr,
            trailing_atr_mult=self.cfg.trail_atr_mult,
            trailing_atr_period=14,
            time_stop_bars=self.cfg.time_stop_bars_5m,
            reason=(
                f"slbr2_{side}_4h_break_15m_retest_bos "
                f"pivots={meta['pivot_count']} slope={meta['slope_pct_day']:.3f}%/d"
            ),
        )
        return signal if signal.validate() else None

    def _process_trigger(self, symbol: str, rows: list[list]) -> Optional[TradeSignal]:
        if self._pending is None or len(rows) < self.cfg.structure_lookback + 3:
            return None
        current = rows[-1]
        trigger_ts = int(float(current[0]))
        if trigger_ts <= int(self._pending["created_trigger_ts"]):
            return None
        self._pending["age"] += 1
        if int(self._pending["age"]) > self.cfg.retest_window_bars:
            self.last_no_signal_reason = "retest_expired"
            self._pending = None
            return None

        side = str(self._pending["side"])
        atr_now = float(self._pending["atr"])
        level = self._projected_level(trigger_ts)
        high, low, close = float(current[2]), float(current[3]), float(current[4])
        invalidation = self.cfg.invalidation_atr * atr_now
        if (side == "long" and close < level - invalidation) or (
            side == "short" and close > level + invalidation
        ):
            self.last_no_signal_reason = "retest_invalidated"
            self._pending = None
            return None

        if not self._pending.get("touched"):
            touched = (
                low <= level + self.cfg.retest_touch_atr * atr_now
                if side == "long"
                else high >= level - self.cfg.retest_touch_atr * atr_now
            )
            held = (
                close >= level + self.cfg.retest_hold_atr * atr_now
                if side == "long"
                else close <= level - self.cfg.retest_hold_atr * atr_now
            )
            if touched and held:
                self._pending["touched"] = True
                self._pending["touch_ts"] = trigger_ts
                self._pending["touch_extreme"] = low if side == "long" else high
                self.last_no_signal_reason = "retest_touched_waiting_bos"
            else:
                self.last_no_signal_reason = "waiting_first_retest"
            return None

        if trigger_ts <= int(self._pending["touch_ts"]):
            return None
        previous = rows[-self.cfg.structure_lookback - 1:-1]
        if side == "long":
            bos = close > max(float(row[2]) for row in previous) and close > level
            stop = min(float(self._pending["touch_extreme"]), level) - self.cfg.stop_buffer_atr * atr_now
        else:
            bos = close < min(float(row[3]) for row in previous) and close < level
            stop = max(float(self._pending["touch_extreme"]), level) + self.cfg.stop_buffer_atr * atr_now
        if not bos:
            self.last_no_signal_reason = "retest_waiting_bos"
            return None
        pending = self._pending
        self._pending = None
        signal = self._make_signal(symbol, side, close, stop, pending)
        self.last_no_signal_reason = "signal" if signal is not None else "invalid_signal_geometry"
        return signal

    def maybe_signal(
        self, store, ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0
    ) -> Optional[TradeSignal]:
        _ = (ts_ms, o, h, l, c, v)
        symbol = str(getattr(store, "symbol", "")).upper()
        if (self._allow and symbol not in self._allow) or symbol in self._deny:
            self.last_no_signal_reason = "symbol_blocked"
            return None
        line_rows = store.fetch_klines(symbol, self.cfg.line_tf, self.cfg.line_lookback) or []
        trigger_rows = store.fetch_klines(symbol, self.cfg.trigger_tf, self.cfg.trigger_lookback) or []
        if not line_rows or not trigger_rows:
            self.last_no_signal_reason = "insufficient_history"
            return None

        trigger_ts = int(float(trigger_rows[-1][0]))
        if self._last_trigger_ts != trigger_ts:
            self._last_trigger_ts = trigger_ts
            signal = self._process_trigger(symbol, trigger_rows)
            if signal is not None:
                return signal

        line_ts = int(float(line_rows[-1][0]))
        if self._last_line_ts == line_ts:
            return None
        self._last_line_ts = line_ts
        candidate = identify_breakout(line_rows, self.cfg)
        if candidate is None:
            self.last_no_signal_reason = "no_4h_pivot_line_break"
            return None
        candidate.update(
            {
                "visible_ts": line_ts + 4 * 60 * 60 * 1000,
                "created_trigger_ts": trigger_ts,
                "age": 0,
                "touched": False,
            }
        )
        self._pending = candidate
        self.last_no_signal_reason = "break_detected_waiting_retest"
        return None
