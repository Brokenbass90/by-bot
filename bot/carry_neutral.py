"""Delta-neutral funding-carry brain (decisions + guards), dependency-free.

The existing live carry executor is one-legged (perp only = directional risk).
This module supplies the MARKET-NEUTRAL decision logic DeepSeek asked for: hold /
rebalance / exit for a two-legged position (spot + perp) with three guards —
basis/hedge, liquidation, and delta-rebalance. It is pure (no API, no orders) so
the risky logic is unit-tested here; Codex wraps it with real spot+perp order
placement on the server.

Convention — POSITIVE-carry position (the safe default):
    spot LONG + perp SHORT  (perp funding positive => shorts get paid).
Price moves of the two legs cancel (delta ~ 0). The residual risks are:
  * BASIS: spot-long + perp-short profits if basis (perp-spot) NARROWS and loses
    if it WIDENS. Exit if adverse basis move exceeds the funding cushion.
  * FUNDING FLIP: if funding turns negative, the short perp now PAYS -> carry
    reversed -> exit.
  * LIQUIDATION: the short perp is liquidated on a big up-move; keep margin
    distance above a buffer, else de-risk/exit.
  * DELTA DRIFT: fills/fees make notional legs uneven -> rebalance to neutral.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def basis_pct(spot_price: float, perp_price: float) -> float:
    """(perp - spot) / spot, in fraction. Positive => perp richer than spot."""
    if spot_price <= 0:
        return float("nan")
    return (perp_price - spot_price) / spot_price


def net_delta_usd(spot_qty: float, spot_price: float, perp_qty: float, perp_price: float,
                  perp_side: str = "short") -> float:
    """Signed USD delta. spot long is +, perp short is -, perp long is +."""
    spot_usd = spot_qty * spot_price
    perp_usd = perp_qty * perp_price
    perp_signed = -perp_usd if perp_side == "short" else perp_usd
    return spot_usd + perp_signed


@dataclass
class CarryConfig:
    # basis guard: exit if adverse basis move (since entry) exceeds this fraction
    # AND is larger than the funding cushion collected so far.
    max_adverse_basis_pct: float = 0.006      # 0.6%
    basis_cushion_mult: float = 1.0           # adverse basis must exceed cushion*funding
    # funding guard
    exit_on_funding_flip: bool = True
    min_funding_8h_pct: float = 0.0           # below this (for short perp) => exit
    # liquidation guard: keep margin ratio above buffer (margin_ratio = maint/equity-ish,
    # we use distance-to-liquidation fraction). Exit if liq distance below this.
    min_liq_distance_pct: float = 0.08        # 8% price room to liquidation
    # delta rebalance
    rebalance_delta_pct: float = 0.01         # |delta|/notional above this => rebalance


@dataclass
class CarryPosition:
    perp_side: str = "short"          # "short" for positive carry
    spot_qty: float = 0.0
    perp_qty: float = 0.0
    entry_basis_pct: float = 0.0      # basis at entry (perp-spot)/spot
    funding_accrued_pct: float = 0.0  # funding collected since entry, as % of notional


@dataclass
class CarryMarket:
    spot_price: float = 0.0
    perp_price: float = 0.0
    funding_8h_pct: float = 0.0       # current funding (positive => shorts receive)
    liq_distance_pct: Optional[float] = None  # fractional price distance to perp liquidation


def evaluate_carry(pos: CarryPosition, mkt: CarryMarket, cfg: Optional[CarryConfig] = None) -> dict[str, Any]:
    """Return {action: hold|rebalance|exit, reason, ...} for a neutral carry leg."""
    cfg = cfg or CarryConfig()
    out: dict[str, Any] = {
        "action": "hold", "reason": "", "basis_pct": float("nan"),
        "adverse_basis_pct": float("nan"), "net_delta_usd": float("nan"),
        "notional_usd": float("nan"),
    }
    if mkt.spot_price <= 0 or mkt.perp_price <= 0:
        out["action"] = "hold"; out["reason"] = "price_unavailable"; return out

    cur_basis = basis_pct(mkt.spot_price, mkt.perp_price)
    out["basis_pct"] = round(cur_basis, 6)
    notional = pos.spot_qty * mkt.spot_price
    out["notional_usd"] = round(notional, 2)
    delta = net_delta_usd(pos.spot_qty, mkt.spot_price, pos.perp_qty, mkt.perp_price, pos.perp_side)
    out["net_delta_usd"] = round(delta, 4)

    # ---- LIQUIDATION guard (highest priority) ----
    if mkt.liq_distance_pct is not None and mkt.liq_distance_pct < cfg.min_liq_distance_pct:
        out["action"] = "exit"
        out["reason"] = f"liq_distance {mkt.liq_distance_pct:.3f} < {cfg.min_liq_distance_pct:.3f}"
        return out

    # ---- FUNDING flip guard ----
    if cfg.exit_on_funding_flip:
        # for a short perp we need funding >= min (positive). For long perp, mirror.
        eff = mkt.funding_8h_pct if pos.perp_side == "short" else -mkt.funding_8h_pct
        if eff < cfg.min_funding_8h_pct:
            out["action"] = "exit"
            out["reason"] = f"funding_flip eff={eff:.4f}% < {cfg.min_funding_8h_pct:.4f}%"
            return out

    # ---- BASIS / hedge guard ----
    # adverse for spot-long+perp-short = basis WIDENING (perp richens vs entry).
    if pos.perp_side == "short":
        adverse = cur_basis - pos.entry_basis_pct      # >0 means widened against us
    else:
        adverse = pos.entry_basis_pct - cur_basis
    out["adverse_basis_pct"] = round(adverse, 6)
    cushion = cfg.basis_cushion_mult * (pos.funding_accrued_pct / 100.0)
    if adverse > cfg.max_adverse_basis_pct and adverse > cushion:
        out["action"] = "exit"
        out["reason"] = (f"basis widened {adverse*100:.3f}% > "
                         f"{cfg.max_adverse_basis_pct*100:.3f}% and > cushion {cushion*100:.3f}%")
        return out

    # ---- DELTA rebalance ----
    if notional > 0 and abs(delta) / notional > cfg.rebalance_delta_pct:
        out["action"] = "rebalance"
        out["reason"] = f"delta {abs(delta)/notional*100:.2f}% > {cfg.rebalance_delta_pct*100:.2f}%"
        return out

    out["action"] = "hold"
    out["reason"] = "neutral_and_collecting"
    return out
