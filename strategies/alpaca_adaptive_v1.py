"""alpaca_adaptive_v1 — best-of-breed Alpaca equities selector (2026-06-15).

Goal
----
Turn the Alpaca sleeve from a long-only "piggy bank" (which loses 15-30% in a
bear market — see runtime/alpaca_v39_*/v40_* OOS bear-2022 probes) into a
regime-aware sleeve that goes to CASH in downtrends. It consolidates the proven
technologies that were scattered across v3/v4/v38/swing into one module:

  1. MARKET REGIME GATE (the key missing piece): if the index (SPY) is below its
     long SMA (default 200), NO new long entries — sit in cash. This is what
     prevents the red bear-market months.
  2. SHARPE-LIKE SCORING (from v4): score = (mom60/vol60) * recency * trend_quality.
  3. VOLATILITY-ADJUSTED SIZING (risk-parity, from v4): weight_i ~ target_vol/vol_i,
     capped at max_position_frac.
  4. SECTOR DIVERSIFICATION CAP (from v4): at most max_per_sector names per sector.
  5. MIN MOMENTUM FILTER: skip names with mom60 below min_entry_mom.
  6. PORTFOLIO DRAWDOWN GUARD (from v4): pause new buys while portfolio DD > limit.
  7. OPTIONAL AI-APPROVAL HOOK: a callable that can veto a candidate (news /
     earnings / AI research). Default None = disabled. It is a FILTER, not alpha:
     it can avoid obvious traps but does not by itself create edge — validate
     before trusting, and it adds latency/cost/dependency.

Pure stdlib, unit-tested offline. Real historical walk-forward (incl. a true
bear like 2022) requires the equities data feed and is the wiring step before
live — this module is the strategy logic, deliberately data-source agnostic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple


# Approver: (symbol, metrics_dict) -> (approved: bool, reason: str)
AiApprover = Callable[[str, Dict[str, float]], Tuple[bool, str]]


@dataclass
class AdaptiveConfig:
    mom_fast: int = 20
    mom_slow: int = 60
    vol_period: int = 60
    trend_sma: int = 50            # per-name trend filter: price > SMA(trend_sma)
    regime_index_sma: int = 200    # MARKET gate: index price > SMA(regime_index_sma)
    min_entry_mom: float = 0.0     # require mom_slow >= this (0 = simply positive)
    target_vol: float = 0.02       # risk-parity target (per-bar realized vol)
    max_position_frac: float = 0.40
    max_per_sector: int = 2
    max_portfolio_dd_pct: float = 15.0
    top_n: int = 5
    max_positions: int = 4

    # --- "bodrее" extensions (OFF by default => baseline behavior unchanged) ---
    # Graduated market gate: instead of binary cash-vs-invested, allow a reduced
    # exposure in a borderline band just below the regime SMA, and only go FULL
    # cash when the index is clearly below it. This adds activity in mild dips
    # while keeping the deep-bear protection that gives the small drawdown.
    soft_regime: bool = False
    soft_band_pct: float = 3.0     # band width below SMA where we run reduced size
    soft_exposure: float = 0.40    # total exposure fraction inside that band
    # Trailing-stop overlay (exit between monthly rebalances). Pure helpers below;
    # the executor calls them per bar. Locks gains / cuts losers earlier.
    use_trailing: bool = False
    trail_atr_mult: float = 3.0    # exit if price retraces this many ATR from peak
    trail_activate_pct: float = 4.0  # arm only after +this% in favor
    trail_pct: float = 0.0         # optional % trail floor (0 = ATR-only)


# ----------------------------- pure helpers --------------------------------
def _sma(xs: Sequence[float], n: int) -> float:
    if n <= 0 or len(xs) < n:
        return float("nan")
    return sum(xs[-n:]) / n


def _ret(xs: Sequence[float], n: int) -> float:
    if n <= 0 or len(xs) < n + 1 or xs[-n - 1] <= 0:
        return float("nan")
    return xs[-1] / xs[-n - 1] - 1.0


def _realized_vol(xs: Sequence[float], n: int) -> float:
    if n <= 1 or len(xs) < n + 1:
        return float("nan")
    rets = [xs[i] / xs[i - 1] - 1.0 for i in range(len(xs) - n, len(xs)) if xs[i - 1] > 0]
    if len(rets) < 2:
        return float("nan")
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(max(0.0, var))


def market_regime_ok(index_closes: Sequence[float], sma_n: int) -> bool:
    """True if the index is in an uptrend (price >= its long SMA). The gate."""
    sma = _sma(index_closes, sma_n)
    if math.isnan(sma) or not index_closes:
        return False  # not enough data -> stay defensive (cash)
    return index_closes[-1] >= sma


def regime_exposure(index_closes: Sequence[float], cfg: "AdaptiveConfig") -> float:
    """Graduated market gate -> target total exposure in [0, 1].

    - index >= SMA            -> 1.0 (uptrend; same as the binary gate)
    - SMA*(1-band) <= index   -> cfg.soft_exposure (borderline; reduced size) IF soft_regime
    - index < SMA*(1-band)    -> 0.0 (clear downtrend; full cash, bear protection)

    With soft_regime=False this is exactly the binary gate (1.0 or 0.0), so the
    proven baseline is preserved unless the operator opts in.
    """
    sma = _sma(index_closes, cfg.regime_index_sma)
    if math.isnan(sma) or not index_closes:
        return 0.0
    px = index_closes[-1]
    if px >= sma:
        return 1.0
    if not cfg.soft_regime:
        return 0.0
    floor = sma * (1.0 - max(0.0, cfg.soft_band_pct) / 100.0)
    if px >= floor:
        return max(0.0, min(1.0, cfg.soft_exposure))
    return 0.0


def _score(closes: Sequence[float], cfg: AdaptiveConfig) -> Optional[Dict[str, float]]:
    mom_s = _ret(closes, cfg.mom_slow)
    mom_f = _ret(closes, cfg.mom_fast)
    vol = _realized_vol(closes, cfg.vol_period)
    sma_t = _sma(closes, cfg.trend_sma)
    if any(math.isnan(x) for x in (mom_s, mom_f, vol, sma_t)):
        return None
    # filters
    if closes[-1] < sma_t:                      # per-name trend filter
        return None
    if mom_s < cfg.min_entry_mom:               # min momentum
        return None
    sharpe_proxy = mom_s / max(0.01, vol)
    recency = 1.0 + 0.3 * (1.0 if mom_f > 0 else 0.0)
    score = sharpe_proxy * recency
    vol_weight = cfg.target_vol / max(vol, 0.005)
    return {"score": score, "mom_slow": mom_s, "mom_fast": mom_f,
            "vol": vol, "vol_weight": vol_weight}


def select(
    universe: Dict[str, Sequence[float]],
    index_closes: Sequence[float],
    *,
    sectors: Optional[Dict[str, str]] = None,
    current_dd_pct: float = 0.0,
    cfg: Optional[AdaptiveConfig] = None,
    ai_approver: Optional[AiApprover] = None,
    force_regime_ok: bool = False,
) -> Dict[str, object]:
    """Return target picks with risk-parity weights, or cash with a reason.

    Output: {"regime_ok": bool, "reason": str, "picks": [ {symbol, weight, ...} ]}
    """
    cfg = cfg or AdaptiveConfig()
    sectors = sectors or {}

    # 1) MARKET GATE — the bear-month protection. force_regime_ok=True is for
    #    A/B backtesting (measuring the gate's contribution), never for live.
    if force_regime_ok:
        exposure = 1.0
    else:
        exposure = regime_exposure(index_closes, cfg)
        if exposure <= 0.0:
            return {"regime_ok": False, "reason": "market_below_regime_sma_cash",
                    "exposure": 0.0, "picks": []}

    # 2) PORTFOLIO DD GUARD — stop adding risk while deep in drawdown.
    if current_dd_pct > cfg.max_portfolio_dd_pct:
        return {"regime_ok": True, "reason": "portfolio_dd_guard_no_new_buys", "picks": []}

    # 3) score + rank
    ranked: List[Tuple[str, Dict[str, float]]] = []
    for sym, closes in universe.items():
        m = _score(closes, cfg)
        if m is not None:
            ranked.append((sym, m))
    ranked.sort(key=lambda kv: kv[1]["score"], reverse=True)

    picks: List[Dict[str, object]] = []
    sector_count: Dict[str, int] = {}
    for sym, m in ranked:
        if len(picks) >= cfg.max_positions:
            break
        sec = sectors.get(sym, "unknown")
        if sector_count.get(sec, 0) >= cfg.max_per_sector:
            continue
        # 4) optional AI approval (news/earnings/AI research veto)
        if ai_approver is not None:
            ok, reason = ai_approver(sym, m)
            if not ok:
                continue
        picks.append({"symbol": sym, "sector": sec, **m})
        sector_count[sec] = sector_count.get(sec, 0) + 1

    # 5) risk-parity weights, normalized to sum=1, then HARD-capped at
    #    max_position_frac. Capping is a risk limit, so we do NOT renormalize
    #    upward afterwards (that would re-breach the cap) — the leftover simply
    #    stays in cash. Weights therefore sum to <= 1.0 by design.
    total_w = sum(float(p["vol_weight"]) for p in picks) or 1.0
    for p in picks:
        norm = float(p["vol_weight"]) / total_w
        capped = min(norm, cfg.max_position_frac)
        # graduated regime scales TOTAL exposure (reduced size in borderline band)
        p["weight"] = capped * exposure

    cash_frac = max(0.0, 1.0 - sum(float(p["weight"]) for p in picks))
    reason = "ok" if picks else "no_qualifying_names"
    if picks and exposure < 1.0:
        reason = f"soft_regime_partial_exposure_{exposure:.2f}"
    return {"regime_ok": True, "reason": reason, "exposure": exposure,
            "cash_frac": cash_frac, "picks": picks}


# ----------------------------- trailing exit overlay -----------------------
def update_peak(prev_peak: float, price: float, side: str = "long") -> float:
    """Track the best price since entry (high-water for long, low-water for short)."""
    if side == "long":
        return max(float(prev_peak), float(price))
    return min(float(prev_peak), float(price))


def trailing_exit(entry: float, peak: float, price: float, atr: float,
                  cfg: "AdaptiveConfig", side: str = "long") -> Tuple[bool, float]:
    """Pure trailing-stop check. Returns (should_exit, stop_price).

    Arms only after price has moved `trail_activate_pct` in favor; then exits if
    price retraces `trail_atr_mult`*ATR (or `trail_pct`%, whichever is wider) from
    the peak. The executor calls this each bar with the running peak from
    `update_peak`. Disabled (no exit) when cfg.use_trailing is False.
    """
    if not cfg.use_trailing or entry <= 0:
        return (False, float("nan"))
    atr = float(atr or 0.0)
    if side == "long":
        gain_pct = (peak / entry - 1.0) * 100.0
        if gain_pct < cfg.trail_activate_pct:
            return (False, float("nan"))
        dist = cfg.trail_atr_mult * atr
        if cfg.trail_pct > 0:
            dist = max(dist, peak * cfg.trail_pct / 100.0)
        stop = peak - dist
        return (price <= stop, stop)
    else:
        gain_pct = (entry / peak - 1.0) * 100.0
        if gain_pct < cfg.trail_activate_pct:
            return (False, float("nan"))
        dist = cfg.trail_atr_mult * atr
        if cfg.trail_pct > 0:
            dist = max(dist, peak * cfg.trail_pct / 100.0)
        stop = peak + dist
        return (price >= stop, stop)


def lively_config() -> AdaptiveConfig:
    """Recommended "bodrее" preset: a bit more active + trailing, while KEEPING
    the deep-bear cash protection. For Codex to A/B vs the baseline AdaptiveConfig().
    """
    return AdaptiveConfig(
        soft_regime=True, soft_band_pct=3.0, soft_exposure=0.45,
        use_trailing=True, trail_atr_mult=3.0, trail_activate_pct=4.0,
        max_positions=5, top_n=6,
    )
