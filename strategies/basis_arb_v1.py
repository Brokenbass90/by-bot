#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
basis_arb_v1.py — Same-exchange spot↔perp basis arbitrage on Bybit Unified.

Idea
----
When perp price diverges from spot (basis), there's a mean-reversion edge:
  - Perp > Spot by > THRESHOLD%  →  SHORT perp + LONG spot (delta-neutral)
  - Perp < Spot by > THRESHOLD%  →  LONG perp + SHORT spot (needs spot borrow)
Wait for basis to converge OR for a funding payment cycle, then close both legs.

Profit drivers
--------------
  - Convergence P&L: basis closes from THRESHOLD → 0 → instant ~THRESHOLD% per leg
  - Funding payment: if held across 8h boundary, perp short collects positive funding
  - Combined edge per cycle: 0.10-0.40% (after fees), several cycles per week

Risk model
----------
  - Delta-neutral: spot+perp net exposure ~0, so spot price moves don't hurt PnL
    materially (only basis dynamics matter)
  - Execution risk: if perp fills first and spot price moves before spot fills,
    basis may close BEFORE entry → entered at worse price. Mitigated by:
      (a) sending both orders within tight window (≤500ms)
      (b) sizing so single-leg slippage ≤ 0.05%
  - Funding flip: if held across boundary and funding moves against side → loss
    of one 8h cycle. Bounded.

Sizing
------
  - Capital is split 50/50 across spot/perp legs (both legs same USD notional)
  - One position per symbol; one position cap globally (BASIS_ARB_MAX_OPEN)
  - Funding budget per leg: BASIS_ARB_PER_LEG_USD (default $100, min $50 to clear fees)

Required env vars
-----------------
  ENABLE_BASIS_ARB_TRADING        0/1            global on/off
  BASIS_ARB_RISK_MULT             float          base risk multiplier (default 0.10)
  BASIS_ARB_PER_LEG_USD           float          $ per leg (default 100, min 50)
  BASIS_ARB_MAX_OPEN              int            max concurrent positions (default 2)
  BASIS_ARB_SYMBOL_ALLOWLIST      csv            tickers, e.g. BTCUSDT,ETHUSDT,SOLUSDT
  BASIS_ARB_ENTRY_THRESHOLD_PCT   float          min basis to enter (default 0.10 = 0.1%)
  BASIS_ARB_EXIT_CONVERGE_PCT     float          basis converged to this → exit (0.02 = 0.02%)
  BASIS_ARB_HOLD_FOR_FUNDING      0/1            hold until next 8h funding payment (default 1)
  BASIS_ARB_MAX_HOLD_BARS_5M      int            max bars holding (default 144 = 12h)
  BASIS_ARB_SL_PCT                float          emergency stop on either leg (default 0.50)
  BASIS_ARB_ALLOW_SPOT_BORROW     0/1            allow short spot via spot margin (default 0)

Status: SKELETON. Backtest harness to be added in scripts/basis_arb_backtest.py.
        Acceptance gate: 90d backtest net ≥ +1%, max DD ≤ 0.8%, sharpe ≥ 2.0,
        then 30d shadow before live deploy.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except (ValueError, TypeError):
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return int(default)
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return int(default)


def _env_bool(name: str, default: bool) -> bool:
    return str(os.getenv(name, "1" if default else "0")).strip().lower() in (
        "1", "true", "yes", "y", "on",
    )


def _env_csv(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default).strip()
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class BasisArbV1Config:
    per_leg_usd: float = field(
        default_factory=lambda: max(50.0, _env_float("BASIS_ARB_PER_LEG_USD", 100.0))
    )
    max_open: int = field(default_factory=lambda: max(1, _env_int("BASIS_ARB_MAX_OPEN", 2)))
    symbol_allowlist: List[str] = field(
        default_factory=lambda: _env_csv("BASIS_ARB_SYMBOL_ALLOWLIST", "BTCUSDT,ETHUSDT,SOLUSDT")
    )
    entry_threshold_pct: float = field(
        default_factory=lambda: _env_float("BASIS_ARB_ENTRY_THRESHOLD_PCT", 0.10)
    )
    exit_converge_pct: float = field(
        default_factory=lambda: _env_float("BASIS_ARB_EXIT_CONVERGE_PCT", 0.02)
    )
    hold_for_funding: bool = field(
        default_factory=lambda: _env_bool("BASIS_ARB_HOLD_FOR_FUNDING", True)
    )
    max_hold_bars_5m: int = field(
        default_factory=lambda: _env_int("BASIS_ARB_MAX_HOLD_BARS_5M", 144)
    )
    sl_pct: float = field(default_factory=lambda: _env_float("BASIS_ARB_SL_PCT", 0.50))
    allow_spot_borrow: bool = field(
        default_factory=lambda: _env_bool("BASIS_ARB_ALLOW_SPOT_BORROW", False)
    )
    fee_bps: float = field(default_factory=lambda: _env_float("BASIS_ARB_FEE_BPS", 6.0))
    slippage_bps: float = field(default_factory=lambda: _env_float("BASIS_ARB_SLIPPAGE_BPS", 2.0))


@dataclass
class BasisArbSignal:
    """A delta-neutral basis arb signal — must execute both legs in one go."""
    symbol: str
    side: str               # "perp_short_spot_long" | "perp_long_spot_short"
    spot_price: float
    perp_price: float
    basis_pct: float        # signed: positive = perp > spot
    per_leg_usd: float
    spot_qty: float
    perp_qty: float
    expected_pnl_pct: float
    reason: str
    funding_rate: Optional[float] = None
    hold_until_funding: bool = False


class BasisArbV1Strategy:
    """Same-exchange spot↔perp basis arbitrage.

    This is a SKELETON. Integrates with bot's order placement only after:
      1. backtest_basis_arb.py shows positive 90d edge net of fees
      2. 30d shadow mode logs ≥ 3 valid entries/week with realistic basis sizes
      3. operator approves live deploy with ENABLE_BASIS_ARB_TRADING=1
    """

    def __init__(self, config: Optional[BasisArbV1Config] = None) -> None:
        self.cfg = config or BasisArbV1Config()
        self._last_no_signal_reason: Dict[str, str] = {}

    # ── Public signal interface ────────────────────────────────────────────
    def signal(
        self,
        symbol: str,
        *,
        spot_price: float,
        perp_price: float,
        funding_rate_8h: Optional[float] = None,
        seconds_to_funding: Optional[int] = None,
        spot_orderbook: Optional[Dict[str, Any]] = None,
        perp_orderbook: Optional[Dict[str, Any]] = None,
    ) -> Optional[BasisArbSignal]:
        """Generate a basis-arb entry signal or None.

        spot_orderbook/perp_orderbook can be passed for slippage estimation;
        if absent, uses fee_bps + slippage_bps as static slippage estimate.
        """
        symbol_u = symbol.upper()
        if symbol_u not in {s.upper() for s in self.cfg.symbol_allowlist}:
            return self._no_signal(symbol_u, "not_in_allowlist")

        if spot_price <= 0 or perp_price <= 0:
            return self._no_signal(symbol_u, "invalid_prices")

        basis_pct = (perp_price - spot_price) / spot_price * 100.0
        abs_basis = abs(basis_pct)

        # Round-trip fee cost
        rt_fee_pct = (self.cfg.fee_bps * 2 + self.cfg.slippage_bps * 2) / 100.0
        # Expected gross PnL = basis - exit_threshold (we exit when basis converges
        # to exit_converge_pct, so capture basis - exit_converge_pct).
        gross_capture_pct = abs_basis - self.cfg.exit_converge_pct
        net_expected_pct = gross_capture_pct - rt_fee_pct
        # Add expected funding if holding to next payment
        funding_bonus_pct = 0.0
        hold_for_funding = False
        if (
            self.cfg.hold_for_funding
            and funding_rate_8h is not None
            and seconds_to_funding is not None
            and seconds_to_funding < 4 * 3600  # within 4h of next payment
        ):
            # If we're shorting perp and funding > 0, we receive funding
            if basis_pct > 0:  # perp > spot → short perp
                funding_bonus_pct = max(0.0, funding_rate_8h) * 100.0
            else:  # perp < spot → long perp
                funding_bonus_pct = max(0.0, -funding_rate_8h) * 100.0
            net_expected_pct += funding_bonus_pct
            hold_for_funding = True

        # Entry gate
        if abs_basis < self.cfg.entry_threshold_pct:
            return self._no_signal(symbol_u, f"basis_too_small:{abs_basis:.3f}%")
        if net_expected_pct <= 0:
            return self._no_signal(symbol_u, f"net_expected_pct≤0:{net_expected_pct:.3f}%")

        # Direction
        if basis_pct > 0:
            side = "perp_short_spot_long"
            if not self.cfg.allow_spot_borrow and False:  # would need to short spot — not this side
                pass
        else:
            # Need spot borrow to short spot
            if not self.cfg.allow_spot_borrow:
                return self._no_signal(symbol_u, "needs_spot_borrow_disabled")
            side = "perp_long_spot_short"

        per_leg = self.cfg.per_leg_usd
        spot_qty = per_leg / spot_price
        perp_qty = per_leg / perp_price

        return BasisArbSignal(
            symbol=symbol_u,
            side=side,
            spot_price=spot_price,
            perp_price=perp_price,
            basis_pct=basis_pct,
            per_leg_usd=per_leg,
            spot_qty=spot_qty,
            perp_qty=perp_qty,
            expected_pnl_pct=net_expected_pct,
            reason=(
                f"basis={basis_pct:+.3f}% gross={gross_capture_pct:.3f}% "
                f"fee={rt_fee_pct:.3f}% funding+={funding_bonus_pct:.3f}% "
                f"net={net_expected_pct:.3f}%"
            ),
            funding_rate=funding_rate_8h,
            hold_until_funding=hold_for_funding,
        )

    # ── Exit logic ─────────────────────────────────────────────────────────
    def should_exit(
        self,
        signal: BasisArbSignal,
        *,
        current_spot: float,
        current_perp: float,
        bars_held: int,
        passed_funding_boundary: bool,
    ) -> Tuple[bool, str]:
        """Return (exit, reason)."""
        if current_spot <= 0 or current_perp <= 0:
            return True, "invalid_prices"
        current_basis = (current_perp - current_spot) / current_spot * 100.0

        # Converged enough → exit
        if abs(current_basis) <= self.cfg.exit_converge_pct:
            return True, f"converged_to_{current_basis:.3f}%"

        # If we crossed funding payment and signal was for funding capture → exit
        if signal.hold_until_funding and passed_funding_boundary:
            return True, "funding_collected"

        # Max hold reached
        if bars_held >= self.cfg.max_hold_bars_5m:
            return True, f"max_hold_{bars_held}_bars"

        # Emergency stop: basis blew out against us (very rare for delta-neutral)
        # We measure: if our net unrealized P&L < -SL_PCT, exit
        # net pnl on long-spot leg: (cur_spot - signal.spot_price) / signal.spot_price
        # net pnl on short-perp leg: (signal.perp_price - cur_perp) / signal.perp_price
        if signal.side == "perp_short_spot_long":
            spot_pnl = (current_spot - signal.spot_price) / signal.spot_price
            perp_pnl = (signal.perp_price - current_perp) / signal.perp_price
        else:
            spot_pnl = (signal.spot_price - current_spot) / signal.spot_price
            perp_pnl = (current_perp - signal.perp_price) / signal.perp_price
        net_pnl_pct = (spot_pnl + perp_pnl) * 100.0
        if net_pnl_pct < -self.cfg.sl_pct:
            return True, f"emergency_sl_{net_pnl_pct:.3f}%"

        return False, ""

    # ── Diagnostics ────────────────────────────────────────────────────────
    def last_no_signal_reason(self, symbol: str) -> str:
        return self._last_no_signal_reason.get(symbol.upper(), "")

    def _no_signal(self, symbol: str, reason: str) -> None:
        self._last_no_signal_reason[symbol] = reason
        return None


# ─── Multi-symbol selector + partial profit-taking ────────────────────────
# Production enhancements added 2026-05-29:
#   1. Rank symbols by expected edge (basis + funding) — open positions on
#      strongest opportunities first when capital is limited
#   2. Partial profit-taking — exit half at 50% convergence, rest at 80%
#   3. Margin guard — block entry if remaining margin < safety threshold


@dataclass
class BasisArbSelectorConfig:
    """Pool selector — when many symbols offer basis edge, pick best K."""
    max_concurrent: int = 2
    # Min expected_pnl_pct to consider opening a slot
    min_expected_pnl_pct: float = 0.08
    # Reserve % of equity that should remain free for SL margin calls
    min_margin_reserve_frac: float = 0.30


class BasisArbV1Selector:
    """Picks top-K basis opportunities from a pool of candidate symbols.

    Usage:
        selector = BasisArbV1Selector(cfg)
        ranked = selector.rank(candidates)
        # ranked[0] is best opportunity
        # take up to cfg.max_concurrent that fit in margin
    """

    def __init__(self, cfg: Optional[BasisArbSelectorConfig] = None) -> None:
        self.cfg = cfg or BasisArbSelectorConfig()

    def rank(self, signals: List[BasisArbSignal]) -> List[BasisArbSignal]:
        """Return signals sorted by expected_pnl_pct desc, filtered by min."""
        eligible = [s for s in signals if s.expected_pnl_pct >= self.cfg.min_expected_pnl_pct]
        eligible.sort(key=lambda s: s.expected_pnl_pct, reverse=True)
        return eligible

    def select_for_capacity(
        self,
        signals: List[BasisArbSignal],
        available_margin_usd: float,
        equity_usd: float,
    ) -> List[BasisArbSignal]:
        """Pick top signals that fit in available margin while respecting reserve."""
        ranked = self.rank(signals)
        if not ranked:
            return []

        # Reserve margin for emergency exits
        usable_margin = available_margin_usd - (equity_usd * self.cfg.min_margin_reserve_frac)
        if usable_margin <= 0:
            return []

        chosen: List[BasisArbSignal] = []
        consumed_margin = 0.0
        for s in ranked:
            if len(chosen) >= self.cfg.max_concurrent:
                break
            # Each position uses 2 legs × per_leg_usd notional
            cost = s.per_leg_usd * 2
            if consumed_margin + cost > usable_margin:
                continue
            chosen.append(s)
            consumed_margin += cost
        return chosen


def partial_profit_targets(signal: BasisArbSignal) -> List[Tuple[float, float]]:
    """Return list of (target_convergence_pct, exit_fraction) for partial profit-taking.

    Example for basis=0.30%, entry_threshold=0.10%, exit_converge=0.02%:
      - Take 33% off at 50% convergence (basis drops to 0.16%)
      - Take 33% off at 70% convergence (basis drops to 0.10%)
      - Take 34% off at final convergence (basis drops to 0.02%)

    This locks in PnL gradually instead of waiting full convergence.
    """
    entry_abs = abs(signal.basis_pct)
    targets = []
    for frac, exit_frac in [(0.50, 0.33), (0.70, 0.33), (1.00, 0.34)]:
        target_basis = entry_abs * (1 - frac)
        targets.append((target_basis, exit_frac))
    return targets


__all__ = [
    "BasisArbV1Config", "BasisArbV1Strategy", "BasisArbSignal",
    "BasisArbSelectorConfig", "BasisArbV1Selector", "partial_profit_targets",
]
