"""Market-neutral pair statistical arbitrage — ETH/BTC and similar (Opus 2026-06-08).

Idea: two correlated assets (e.g. ETHUSDT, BTCUSDT) move together. Their spread
(log A - beta*log B) is mean-reverting when the pair is cointegrated. When the
spread stretches far from its mean (high |z-score|) we LONG the underperformer
and SHORT the outperformer, betting the gap closes. Direction-neutral: profits
whether the market rises or falls, as long as the gap reverts.

Pure stdlib (no numpy/statsmodels) so it is portable and unit-testable offline.
This module produces PairSignals; live execution (two legs) and backtest
validation are wired separately (Codex). NOT a money guarantee — the edge is
thin and must pass walk-forward + fee modelling (see backtest/robustness.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

_LN2 = math.log(2.0)


@dataclass
class PairConfig:
    lookback: int = 336          # bars for beta + z-score window (e.g. 336 = 14d of 1h)
    entry_z: float = 2.5         # enter when |z| >= this
    exit_z: float = 0.5          # exit when |z| <= this (reverted)
    stop_z: float = 3.0          # bail when |z| >= this (gap keeps widening)
    max_half_life: float = 48.0  # bars; spread must mean-revert faster than this
    min_abs_corr: float = 0.75   # min |corr| of the two return series
    risk_pct_per_pair: float = 0.3
    beta_stability_lookback: int = 168
    max_beta_drift_frac: float = 0.35


@dataclass
class PairSignal:
    long_symbol: str
    short_symbol: str
    z: float
    beta: float
    half_life: float
    corr: float
    reason: str


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _ols(y: Sequence[float], x: Sequence[float]) -> Tuple[float, float]:
    """Return (slope, intercept) for y = slope*x + intercept (least squares)."""
    n = len(x)
    if n < 2:
        return 0.0, 0.0
    mx, my = _mean(x), _mean(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx <= 0:
        return 0.0, my
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx
    return slope, my - slope * mx


def _corr(a: Sequence[float], b: Sequence[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[-n:], b[-n:]
    sa, sb = _std(a), _std(b)
    if sa <= 0 or sb <= 0:
        return 0.0
    ma, mb = _mean(a), _mean(b)
    cov = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b)) / (n - 1)
    return cov / (sa * sb)


def compute_spread(prices_a: Sequence[float], prices_b: Sequence[float]) -> Tuple[float, float, List[float]]:
    """Hedge ratio beta and spread = log(A) - beta*log(B) - intercept."""
    la = [math.log(p) for p in prices_a]
    lb = [math.log(p) for p in prices_b]
    beta, intercept = _ols(la, lb)
    spread = [a - (beta * b + intercept) for a, b in zip(la, lb)]
    return beta, intercept, spread


def half_life(spread: Sequence[float]) -> float:
    """Ornstein-Uhlenbeck half-life of mean reversion, in bars.

    Regress dS_t on S_{t-1}: dS = lambda * S_{t-1} + c. Reverting => lambda < 0,
    half_life = ln(2)/-lambda. Returns +inf if not mean-reverting.
    """
    if len(spread) < 3:
        return math.inf
    s_prev = spread[:-1]
    ds = [spread[i] - spread[i - 1] for i in range(1, len(spread))]
    lam, _ = _ols(ds, s_prev)
    if lam >= 0:
        return math.inf
    return _LN2 / (-lam)


def returns(prices: Sequence[float]) -> List[float]:
    return [(prices[i] / prices[i - 1] - 1.0) for i in range(1, len(prices))]


class PairStatArbV1:
    """Stateless evaluator for one pair (A vs B)."""

    NAME = "pair_stat_arb_v1"

    def __init__(self, cfg: Optional[PairConfig] = None) -> None:
        self.cfg = cfg or PairConfig()
        self.last_reason: str = ""

    def diagnostics(self, prices_a: Sequence[float], prices_b: Sequence[float]) -> dict:
        cfg = self.cfg
        n = min(len(prices_a), len(prices_b))
        if n < cfg.lookback:
            return {"tradeable": False, "reason": f"history_short_{n}"}
        a = list(prices_a[-cfg.lookback:])
        b = list(prices_b[-cfg.lookback:])
        beta, _, spread = compute_spread(a, b)
        mu, sd = _mean(spread), _std(spread)
        z = (spread[-1] - mu) / sd if sd > 0 else 0.0
        hl = half_life(spread)
        corr = _corr(returns(a), returns(b))
        beta_drift_frac = 0.0
        if cfg.max_beta_drift_frac > 0 and n >= cfg.lookback + max(20, cfg.beta_stability_lookback):
            prev_a = list(prices_a[-cfg.lookback - cfg.beta_stability_lookback:-cfg.beta_stability_lookback])
            prev_b = list(prices_b[-cfg.lookback - cfg.beta_stability_lookback:-cfg.beta_stability_lookback])
            prev_beta, _, _ = compute_spread(prev_a, prev_b)
            if prev_beta > 0:
                beta_drift_frac = abs(beta - prev_beta) / max(abs(prev_beta), 1e-12)

        tradeable = (
            beta > 0
            and math.isfinite(hl) and 0 < hl <= cfg.max_half_life
            and abs(corr) >= cfg.min_abs_corr
            and (cfg.max_beta_drift_frac <= 0 or beta_drift_frac <= cfg.max_beta_drift_frac)
            and sd > 0
        )
        reason = "ok"
        if not tradeable:
            if beta <= 0:
                reason = "beta_invalid"
            elif not (math.isfinite(hl) and 0 < hl <= cfg.max_half_life):
                reason = "half_life_bad"
            elif abs(corr) < cfg.min_abs_corr:
                reason = "corr_low"
            elif cfg.max_beta_drift_frac > 0 and beta_drift_frac > cfg.max_beta_drift_frac:
                reason = "beta_unstable"
            else:
                reason = "not_cointegrated"
        return {
            "tradeable": tradeable, "beta": beta, "z": z, "half_life": hl,
            "corr": corr, "spread_std": sd, "beta_drift_frac": beta_drift_frac, "reason": reason,
        }

    def signal(
        self,
        symbol_a: str,
        symbol_b: str,
        prices_a: Sequence[float],
        prices_b: Sequence[float],
    ) -> Optional[PairSignal]:
        d = self.diagnostics(prices_a, prices_b)
        if not d.get("tradeable"):
            self.last_reason = d.get("reason", "not_tradeable")
            return None
        z = d["z"]
        if abs(z) < self.cfg.entry_z:
            self.last_reason = f"z_small_{z:.2f}"
            return None
        if abs(z) >= self.cfg.stop_z:
            self.last_reason = f"z_blowout_{z:.2f}"
            return None
        # z>0: A rich vs B -> short A, long B. z<0: A cheap -> long A, short B.
        if z > 0:
            long_sym, short_sym = symbol_b, symbol_a
        else:
            long_sym, short_sym = symbol_a, symbol_b
        self.last_reason = f"entry_z_{z:.2f}"
        return PairSignal(
            long_symbol=long_sym, short_symbol=short_sym, z=z,
            beta=d["beta"], half_life=d["half_life"], corr=d["corr"],
            reason=self.last_reason,
        )

    def should_exit(self, z: float) -> Tuple[bool, str]:
        if abs(z) <= self.cfg.exit_z:
            return True, f"reverted_z_{z:.2f}"
        if abs(z) >= self.cfg.stop_z:
            return True, f"stop_z_{z:.2f}"
        return False, ""
