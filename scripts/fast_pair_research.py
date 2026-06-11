#!/usr/bin/env python3
"""Fast vectorized pair stat-arb research with honest walk-forward (2026-06-10).

Why this exists: scripts/validate_pair_arb.py measured P&L as the change of a
spread RE-FITTED at exit (fresh beta+intercept) — not realizable; it produced
PF 4.78 fantasies. Here:
  * P&L = realizable log-returns of the two legs as the executor would book them
    (equal-notional or beta-weighted), per unit TOTAL notional, fees on 4 fills;
  * rolling OLS (beta/intercept/z) vectorized via cumulative sums (numpy);
  * rolling |corr| gate of 1h returns, like PairStatArbV1;
  * honest walk-forward: pick config on IN-SAMPLE only, evaluate on OOS.

Usage:
  python3 scripts/fast_pair_research.py --a ETHUSDT --b BTCUSDT
  python3 scripts/fast_pair_research.py --a SOLUSDT --b ETHUSDT --is-days 90 --oos-days 30
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HOUR_MS = 3_600_000


def load_1h_closes(sym: str, cache_dir: str = "data_cache") -> Dict[int, float]:
    bars: Dict[int, Tuple[int, float]] = {}
    for f in sorted(glob.glob(f"{cache_dir}/{sym}_5_*.json")):
        try:
            rows = json.load(open(f))
        except Exception:
            continue
        for r in rows:
            try:
                ts = int(r["ts"]); c = float(r["c"])
            except Exception:
                continue
            hour = ts - (ts % _HOUR_MS)
            prev = bars.get(hour)
            if prev is None or ts > prev[0]:
                bars[hour] = (ts, c)
    return {h: c for h, (_, c) in bars.items()}


def _rolling_sums(x: np.ndarray, L: int) -> np.ndarray:
    c = np.concatenate(([0.0], np.cumsum(x)))
    out = np.full(len(x), np.nan)
    out[L - 1:] = c[L:] - c[:-L]
    return out


def rolling_ols_z(la: np.ndarray, lb: np.ndarray, L: int):
    """Rolling OLS la = slope*lb + c over trailing L bars. Returns slope, z of
    the LAST residual in each window (z = resid / std(resid))."""
    Sx = _rolling_sums(lb, L); Sy = _rolling_sums(la, L)
    Sxx = _rolling_sums(lb * lb, L); Syy = _rolling_sums(la * la, L)
    Sxy = _rolling_sums(la * lb, L)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = L * Sxx - Sx * Sx
        slope = (L * Sxy - Sx * Sy) / den
        intercept = (Sy - slope * Sx) / L
        resid_last = la - slope * lb - intercept
        ssr = (Syy - Sy * Sy / L) - slope * slope * (Sxx - Sx * Sx / L)
        ssr = np.maximum(ssr, 0.0)
        std = np.sqrt(ssr / max(L - 1, 1))
        z = np.where(std > 0, resid_last / std, 0.0)
    return slope, z


def rolling_corr_returns(la: np.ndarray, lb: np.ndarray, L: int) -> np.ndarray:
    ra = np.diff(la, prepend=la[0])
    rb = np.diff(lb, prepend=lb[0])
    Sa = _rolling_sums(ra, L); Sb = _rolling_sums(rb, L)
    Saa = _rolling_sums(ra * ra, L); Sbb = _rolling_sums(rb * rb, L)
    Sab = _rolling_sums(ra * rb, L)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = Sab - Sa * Sb / L
        va = Saa - Sa * Sa / L
        vb = Sbb - Sb * Sb / L
        corr = cov / np.sqrt(va * vb)
    return corr


def simulate(la: np.ndarray, lb: np.ndarray, slope: np.ndarray, z: np.ndarray,
             corr: np.ndarray, s: int, e: int, entry_z: float, exit_z: float,
             stop_z: float, max_hold: int, fee_bps: float, beta_weighted: bool,
             min_abs_corr: float = 0.6) -> List[dict]:
    """Event loop on precomputed arrays, trading only inside [s, e)."""
    fee = fee_bps / 10000.0
    trades: List[dict] = []
    in_pos = False
    sign = 0; ia = 0; beta_e = 1.0
    for i in range(s, e):
        zi = z[i]
        if not np.isfinite(zi):
            continue
        if not in_pos:
            if abs(corr[i]) < min_abs_corr or not np.isfinite(slope[i]) or slope[i] <= 0:
                continue
            if entry_z <= abs(zi) < stop_z:
                in_pos = True
                sign = 1 if zi > 0 else -1
                ia = i
                beta_e = float(np.clip(slope[i], 0.3, 3.0)) if beta_weighted else 1.0
        else:
            exit_now = abs(zi) <= exit_z or abs(zi) >= stop_z or (i - ia) >= max_hold
            if i == e - 1:
                exit_now = True
            if exit_now:
                ret_a = la[i] - la[ia]
                ret_b = lb[i] - lb[ia]
                # sign=+1: short A (1x), long B (beta x). per TOTAL notional:
                gross = sign * (beta_e * ret_b - ret_a) / (1.0 + beta_e)
                net = gross - 2.0 * fee  # 4 fills, each on half the total notional
                trades.append({"pnl": net, "hold": i - ia})
                in_pos = False
    return trades


def metrics(trades: List[dict]) -> Dict[str, float]:
    if not trades:
        return {"profit_factor": 1.0, "return_pct": 0.0, "trades": 0,
                "win_rate": 0.0, "max_drawdown": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    pf = (sum(wins) / sum(losses)) if losses else (99.0 if wins else 1.0)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1.0 + t["pnl"])
        peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    return {"profit_factor": round(min(pf, 99.0), 3),
            "return_pct": round((eq - 1.0) * 100.0, 3),
            "trades": len(trades),
            "win_rate": round(len(wins) / len(trades), 3),
            "max_drawdown": round(mdd * 100.0, 3)}


GRID = {
    "lookback": (120, 168, 240, 336),
    "entry_z": (1.5, 2.0, 2.5),
    "exit_z": (0.0, 0.5),
    "max_hold": (72, 168),
    "beta_weighted": (True, False),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="ETHUSDT")
    ap.add_argument("--b", default="BTCUSDT")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--is-days", type=int, default=90)
    ap.add_argument("--oos-days", type=int, default=30)
    ap.add_argument("--stop-z", type=float, default=3.5)
    args = ap.parse_args()

    ra, rb = load_1h_closes(args.a), load_1h_closes(args.b)
    common = sorted(set(ra) & set(rb))
    la = np.log(np.array([ra[t] for t in common]))
    lb = np.log(np.array([rb[t] for t in common]))
    n = len(common)
    print(f"# {args.a}/{args.b}: aligned 1h bars = {n} "
          f"({(common[-1]-common[0])/86400000:.0f} days)", file=sys.stderr)

    # precompute per lookback
    pre = {}
    for L in GRID["lookback"]:
        slope, z = rolling_ols_z(la, lb, L)
        corr = rolling_corr_returns(la, lb, L)
        pre[L] = (slope, z, corr)

    is_bars = args.is_days * 24
    oos_bars = args.oos_days * 24
    folds = []
    cur = max(GRID["lookback"])  # leave warmup for largest lookback
    while cur + is_bars + oos_bars <= n:
        folds.append((cur, cur + is_bars, cur + is_bars + oos_bars))
        cur += oos_bars

    combos = list(itertools.product(*GRID.values()))
    keys = list(GRID.keys())
    fold_rows = []
    oos_all: List[dict] = []
    for (fs, fm, fe) in folds:
        best = None
        for combo in combos:
            cfg = dict(zip(keys, combo))
            slope, z, corr = pre[cfg["lookback"]]
            tr = simulate(la, lb, slope, z, corr, fs, fm, cfg["entry_z"],
                          cfg["exit_z"], args.stop_z, cfg["max_hold"],
                          args.fee_bps, cfg["beta_weighted"])
            m = metrics(tr)
            if m["trades"] < 5:
                continue
            score = m["return_pct"]
            if best is None or score > best[0]:
                best = (score, cfg, m)
        if best is None:
            fold_rows.append({"fold_start_bar": fs, "note": "no_config_with_5_trades_IS"})
            continue
        _, cfg, m_is = best
        slope, z, corr = pre[cfg["lookback"]]
        tr_oos = simulate(la, lb, slope, z, corr, fm, fe, cfg["entry_z"],
                          cfg["exit_z"], args.stop_z, cfg["max_hold"],
                          args.fee_bps, cfg["beta_weighted"])
        m_oos = metrics(tr_oos)
        oos_all.extend(tr_oos)
        from datetime import datetime, timezone
        fold_rows.append({
            "oos_start": datetime.fromtimestamp(common[fm] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "picked": cfg, "is_return_pct": m_is["return_pct"],
            "oos": m_oos,
        })

    pfs = [r["oos"]["profit_factor"] for r in fold_rows if "oos" in r]
    rets = [r["oos"]["return_pct"] for r in fold_rows if "oos" in r]
    out = {
        "pair": f"{args.a}/{args.b}",
        "bars_1h": n,
        "folds": len(fold_rows),
        "oos_pf_median": round(float(np.median(pfs)), 3) if pfs else None,
        "oos_pf_min": round(min(pfs), 3) if pfs else None,
        "oos_ret_median_pct": round(float(np.median(rets)), 3) if rets else None,
        "oos_ret_total_pct": round(float((np.prod([1 + t["pnl"] for t in oos_all]) - 1) * 100), 3) if oos_all else None,
        "oos_trades": len(oos_all),
        "oos_win_rate": round(sum(1 for t in oos_all if t["pnl"] > 0) / len(oos_all), 3) if oos_all else None,
        "verdict": ("robust" if pfs and float(np.median(pfs)) > 1.0 and min(pfs) > 0.5 else "fragile"),
        "folds_detail": fold_rows,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
