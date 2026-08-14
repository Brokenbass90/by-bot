"""Research-only V3: V2 geometry with a delayed retest reclaim.

The only conceptual change from V2 is that touching the broken line and
proving that the line was reclaimed must happen on different completed 15m
bars.  Break detection, invalidation, BOS, stop, exits, costs, and environment
configuration remain inherited from V2.
"""
from __future__ import annotations

from typing import Optional

from .signals import TradeSignal
from .sloped_break_retest_v2 import SlopedBreakRetestV2Strategy


class SlopedBreakRetestV3Strategy(SlopedBreakRetestV2Strategy):
    STRATEGY_NAME = "sloped_break_retest_v3"

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
            if touched:
                self._pending["touched"] = True
                self._pending["touch_ts"] = trigger_ts
                self._pending["touch_extreme"] = low if side == "long" else high
                self._pending["reclaimed"] = False
                self.last_no_signal_reason = "retest_touched_waiting_reclaim"
            else:
                self.last_no_signal_reason = "waiting_first_retest"
            return None

        if not self._pending.get("reclaimed"):
            if trigger_ts <= int(self._pending["touch_ts"]):
                return None
            reclaimed = (
                close >= level + self.cfg.retest_hold_atr * atr_now
                if side == "long"
                else close <= level - self.cfg.retest_hold_atr * atr_now
            )
            if not reclaimed:
                self.last_no_signal_reason = "retest_waiting_reclaim"
                return None
            self._pending["reclaimed"] = True
            self._pending["reclaim_ts"] = trigger_ts
            self.last_no_signal_reason = "retest_reclaimed_waiting_bos"
            return None

        if trigger_ts <= int(self._pending["reclaim_ts"]):
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
