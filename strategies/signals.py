#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TradeSignal:
    strategy: str
    symbol: str
    side: str  # "long" | "short"
    entry: float
    sl: float
    # Fixed target (legacy): a single TP level.
    # For managed/runner exits, use `tps` (+ optional `tp_fracs`).
    tp: float

    # Optional multi-target exit plan.
    # - `tps`: ordered list of target prices.
    # - `tp_fracs`: fractions of the original position to close at each tp.
    #   If omitted, equal fractions are assumed (and the remainder is left to SL/time).
    tps: Optional[List[float]] = None
    tp_fracs: Optional[List[float]] = None

    # Optional trailing stop (ATR-based) used by the backtest engine.
    # If trailing_atr_mult <= 0, trailing is disabled.
    trailing_atr_mult: float = 0.0
    trailing_atr_period: int = 14

    # Optional time-based stop in 5m bars (0 disables).
    time_stop_bars: int = 0

    # Free-form text tag for debugging/reporting.
    reason: str = ""

    def validate(self) -> bool:
        if self.side not in ("long", "short"):
            return False
        if not (self.entry > 0 and self.sl > 0 and self.tp > 0):
            return False

        # Validate multi-TP plan if provided.
        if self.tps:
            tps = [float(x) for x in self.tps if x is not None]
            if not tps:
                return False
            if any(x <= 0 for x in tps):
                return False
            if self.side == "long":
                if not (self.sl < self.entry):
                    return False
                if any(tp <= self.entry for tp in tps):
                    return False
                if any(tps[i] > tps[i + 1] for i in range(len(tps) - 1)):
                    return False
            else:
                if not (self.sl > self.entry):
                    return False
                if any(tp >= self.entry for tp in tps):
                    return False
                # For shorts, targets should be monotonically decreasing (towards 0).
                if any(tps[i] < tps[i + 1] for i in range(len(tps) - 1)):
                    return False

            if self.tp_fracs:
                fr = [float(x) for x in self.tp_fracs if x is not None]
                if len(fr) != len(tps):
                    return False
                if any(x <= 0 for x in fr):
                    return False
                if sum(fr) > 1.000001:
                    return False

        # Must have meaningful stop and single target (legacy)
        if self.side == "long":
            return self.sl < self.entry < self.tp
        return self.tp < self.entry < self.sl
