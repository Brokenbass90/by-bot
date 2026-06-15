"""Multi-arm portfolio projector (assumption-driven, NOT a backtest).

Answers the strategic question: "what do we need to reach ~2-3%/month, and is
the lever more money?" It Monte-Carlo-simulates several uncorrelated return
streams (arms), blends them, and reports blended annual return, volatility,
median worst drawdown, and the chance of hitting return targets.

KEY POINT it demonstrates: returns are in PERCENT. Adding capital scales the
DOLLARS, not the percentages — so "more money" does NOT move these numbers.
What moves them is (a) each arm's edge, and (b) LOW CORRELATION between arms
(diversification raises return-per-unit-risk). Inputs are explicit assumptions
you can edit; the output is a projection, not a promise.
"""
from __future__ import annotations

import numpy as np

# --- ASSUMPTIONS (edit these). Annualized. Conservative-ish placeholders. ---
ARMS = {
    # name:            (ann_return, ann_vol)
    "crypto_core":      (0.25, 0.30),   # proven directional core (target)
    "equities_gated":   (0.10, 0.09),   # alpaca_adaptive_v1 style (gated)
    "market_neutral":   (0.07, 0.05),   # funding-carry / arb (low vol)
}
WEIGHTS = {"crypto_core": 0.40, "equities_gated": 0.35, "market_neutral": 0.25}
# pairwise correlations (low = the whole point)
CORR = {
    ("crypto_core", "equities_gated"): 0.30,
    ("crypto_core", "market_neutral"): 0.10,
    ("equities_gated", "market_neutral"): 0.15,
}
N_PATHS = 20000
MONTHS = 12
SEED = 11


def _corr_matrix(names):
    n = len(names); M = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            r = CORR.get((names[i], names[j])) or CORR.get((names[j], names[i])) or 0.0
            M[i, j] = M[j, i] = r
    return M


def simulate(arms, weights, months=MONTHS, n=N_PATHS, seed=SEED):
    rng = np.random.default_rng(seed)
    names = list(arms.keys())
    mu_m = np.array([arms[k][0] / 12.0 for k in names])
    sig_m = np.array([arms[k][1] / np.sqrt(12.0) for k in names])
    L = np.linalg.cholesky(_corr_matrix(names))
    w = np.array([weights[k] for k in names])

    ann_returns = np.empty(n); max_dds = np.empty(n); pos_month_frac = np.empty(n)
    for p in range(n):
        z = rng.standard_normal((months, len(names))) @ L.T
        arm_m = mu_m + sig_m * z                      # monthly returns per arm
        port_m = arm_m @ w                            # blended monthly return
        curve = np.cumprod(1.0 + port_m)
        ann_returns[p] = curve[-1] - 1.0
        peak = np.maximum.accumulate(curve)
        max_dds[p] = float(np.max((peak - curve) / peak))
        pos_month_frac[p] = float(np.mean(port_m > 0))
    return ann_returns, max_dds, pos_month_frac, names, w


def arm_solo_stats(arms):
    out = {}
    for k, (r, v) in arms.items():
        out[k] = (r, v, r / v if v else float("nan"))
    return out


def pct(a, q): return float(np.percentile(a, q))


if __name__ == "__main__":
    ann, dd, posm, names, w = simulate(ARMS, WEIGHTS)
    print("=== Multi-arm portfolio projection (assumptions, NOT a backtest) ===")
    print("Per-arm assumptions (ann_ret / ann_vol / Sharpe):")
    for k, (r, v, s) in arm_solo_stats(ARMS).items():
        print(f"  {k:<16} {r*100:5.1f}% / {v*100:4.1f}% / {s:.2f}   weight={WEIGHTS[k]*100:.0f}%")
    blended_mu = sum(ARMS[k][0] * WEIGHTS[k] for k in ARMS)
    print(f"\nBlended (1yr horizon, {N_PATHS} paths):")
    print(f"  expected annual return : {blended_mu*100:5.1f}%  (~{blended_mu/12*100:.2f}%/mo avg)")
    print(f"  annual return  P10/P50/P90 : {pct(ann,10)*100:+5.1f}% / {pct(ann,50)*100:+5.1f}% / {pct(ann,90)*100:+5.1f}%")
    print(f"  worst drawdown P50/P90     : {pct(dd,50)*100:5.1f}% / {pct(dd,90)*100:5.1f}%")
    print(f"  median % of months positive: {pct(posm,50)*100:.0f}%")
    print(f"  P(annual >= 24% i.e. ~2%/mo): {float(np.mean(ann>=0.24))*100:.0f}%")
    print(f"  P(annual >= 36% i.e. ~3%/mo): {float(np.mean(ann>=0.36))*100:.0f}%")
    print(f"  P(losing year, annual < 0) : {float(np.mean(ann<0))*100:.0f}%")
    # contrast: crypto arm ALONE
    a2,d2,_,_,_ = simulate({"crypto_core":ARMS["crypto_core"]}, {"crypto_core":1.0})
    print(f"\nFor contrast — crypto_core ALONE: medianDD {pct(d2,50)*100:.0f}% (P90 {pct(d2,90)*100:.0f}%) "
          f"vs blend medianDD {pct(dd,50)*100:.0f}% — same edge, far less pain via diversification.")
    print("\nNote: 'more money' scales $ not %, so it does NOT change any number above.")
