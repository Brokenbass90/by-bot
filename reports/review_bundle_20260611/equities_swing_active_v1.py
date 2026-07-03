"""PDT-safe active swing selector for a small Alpaca account (Opus 2026-06-08).

Problem: a US equities account under $25k is capped at 3 day-trades / 5 days
(PDT rule). So "more active intraday" is regulatorily blocked at $500-1000.

Smart workaround: trade ACTIVE SWING instead of intraday — hold 2-10 days,
rotate a wider universe more often than the monthly sleeve, and never round-trip
the same name same-day. That is "more active" without tripping PDT.

Selection = blend of:
  - momentum (20d + 60d return, trend must be up: price > SMA50)
  - a pullback bonus (buy strength on a dip, not after it is overbought)
Pure stdlib, unit-tested offline. Wiring into the Alpaca bridge + real backtest
(walk-forward via backtest/robustness.py) is Codex's step before live.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple


@dataclass
class SwingConfig:
    mom_fast: int = 20
    mom_slow: int = 60
    sma_trend: int = 50
    rsi_period: int = 14
    rsi_max: float = 78.0        # skip already-overbought (chasing tops)
    rsi_pullback_lo: float = 40.0  # sweet spot: pullback within uptrend
    rsi_pullback_hi: float = 60.0
    top_n: int = 5
    max_positions: int = 4       # sized for $500-1000 (a few names, not 1)
    min_hold_days: int = 2       # PDT-safe: never same-day round trip
    market_sma: int = 50         # market-regime gate: skip longs if market < its SMA
    max_per_sector: int = 2      # diversification: cap picks per sector
    require_relative_strength: bool = False  # only names outperforming the market
    rs_lookback: int = 60        # window for relative-strength comparison
    w_mom: float = 0.6
    w_pullback: float = 0.4


def _sma(xs: Sequence[float], n: int) -> float:
    if len(xs) < n or n <= 0:
        return float("nan")
    return sum(xs[-n:]) / n


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains = losses = 0.0
    for i in range(-period, 0):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _ret(closes: Sequence[float], n: int) -> float:
    if len(closes) <= n or closes[-n - 1] <= 0:
        return float("nan")
    return closes[-1] / closes[-n - 1] - 1.0


def score_symbol(closes: Sequence[float], cfg: Optional[SwingConfig] = None) -> Dict[str, float]:
    cfg = cfg or SwingConfig()
    need = max(cfg.mom_slow, cfg.sma_trend, cfg.rsi_period) + 2
    if len(closes) < need:
        return {"eligible": False, "reason": "history_short", "score": 0.0}
    price = closes[-1]
    sma = _sma(closes, cfg.sma_trend)
    rsi = _rsi(closes, cfg.rsi_period)
    mom_f = _ret(closes, cfg.mom_fast)
    mom_s = _ret(closes, cfg.mom_slow)
    if not all(math.isfinite(x) for x in (sma, rsi, mom_f, mom_s)):
        return {"eligible": False, "reason": "nan", "score": 0.0}
    trend_ok = price > sma
    if not trend_ok:
        return {"eligible": False, "reason": "below_sma", "score": 0.0, "rsi": rsi}
    if rsi >= cfg.rsi_max:
        return {"eligible": False, "reason": "overbought", "score": 0.0, "rsi": rsi}
    momentum = 0.5 * mom_f + 0.5 * mom_s          # blended momentum
    # pullback bonus: peaks when RSI sits in the [lo,hi] band (dip within uptrend)
    mid = (cfg.rsi_pullback_lo + cfg.rsi_pullback_hi) / 2.0
    half = max(1e-9, (cfg.rsi_pullback_hi - cfg.rsi_pullback_lo) / 2.0)
    pullback = max(0.0, 1.0 - abs(rsi - mid) / half)
    score = cfg.w_mom * momentum + cfg.w_pullback * (pullback * 0.05)  # scale pullback to return-units
    return {
        "eligible": True, "reason": "ok", "score": round(score, 6),
        "momentum": round(momentum, 6), "pullback": round(pullback, 4),
        "rsi": round(rsi, 2), "trend_ok": True,
    }


def market_regime_ok(market_closes: Sequence[float], sma_period: int = 50) -> bool:
    """Safety gate: only go long when the market proxy is above its SMA (uptrend).
    Pass an index series (e.g. SPY, or an equal-weight basket of the universe)."""
    if not market_closes or len(market_closes) < sma_period:
        return True  # no data -> do not block
    return market_closes[-1] > _sma(market_closes, sma_period)


def select(
    universe_closes: Dict[str, Sequence[float]],
    cfg: Optional[SwingConfig] = None,
    market_closes: Optional[Sequence[float]] = None,
    sector_map: Optional[Dict[str, str]] = None,
    quality_scorer: Optional[Callable[[str, Dict[str, float], Sequence[float]], Optional[float]]] = None,
) -> List[Tuple[str, Dict[str, float]]]:
    """Return ranked [(symbol, score_dict)], best first, top_n.

    Safety: if market_closes is given and the market is below its SMA, return []
    (do not buy strength into a falling market). If sector_map is given, cap picks
    per sector (cfg.max_per_sector) for diversification.
    """
    cfg = cfg or SwingConfig()
    if market_closes is not None and not market_regime_ok(market_closes, cfg.market_sma):
        return []
    mkt_ret = _ret(market_closes, cfg.rs_lookback) if market_closes is not None else None
    scored = []
    for sym, closes in universe_closes.items():
        sc = score_symbol(closes, cfg)
        if not sc.get("eligible"):
            continue
        # relative strength: keep only names outperforming the market
        if cfg.require_relative_strength and mkt_ret is not None and math.isfinite(mkt_ret):
            sym_ret = _ret(closes, cfg.rs_lookback)
            if not (math.isfinite(sym_ret) and sym_ret > mkt_ret):
                continue
        # optional pluggable quality scorer (e.g. an AI/news filter) — multiplies
        # the base score; returning None or <=0 drops the candidate.
        if quality_scorer is not None:
            q = quality_scorer(sym, sc, closes)
            if q is None or q <= 0:
                continue
            sc = dict(sc); sc["score"] = sc["score"] * float(q); sc["quality_mult"] = float(q)
        scored.append((sym, sc))
    scored.sort(key=lambda kv: kv[1]["score"], reverse=True)
    if sector_map is None:
        return scored[: cfg.top_n]
    picked: List[Tuple[str, Dict[str, float]]] = []
    per_sector: Dict[str, int] = {}
    for sym, sc in scored:
        sect = sector_map.get(sym, "other")
        if per_sector.get(sect, 0) >= cfg.max_per_sector:
            continue
        picked.append((sym, sc))
        per_sector[sect] = per_sector.get(sect, 0) + 1
        if len(picked) >= cfg.top_n:
            break
    return picked


def is_day_trade_safe(entry_ts: int, now_ts: int, min_hold_days: int = 2) -> bool:
    """True if closing now would NOT be a same-day round trip (PDT-safe)."""
    return (now_ts - entry_ts) >= min_hold_days * 86400
