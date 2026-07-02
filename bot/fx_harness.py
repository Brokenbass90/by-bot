"""FX backtest harness — run fx_setups over FX/CFD data honestly, feed the gate.

Unblocks the FX track: fx_setups are built, but had no runner. This walks bars,
calls a setup, opens a maker-ish trade with a fixed R (SL=sl_atr*ATR, TP=tp_rr*R),
resolves it on SUBSEQUENT bars (SL-first on same bar = conservative), charges fees
in R, and returns trades ready for wf_folds -> oos_selector. Causal: exits use only
bars AFTER entry; one position at a time (cooldown). Pure stdlib + market_context.atr.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

from bot.market_context import atr, HIGH, LOW, CLOSE, TS


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


def backtest_fx_setup(
    rows: Sequence[Sequence[float]],
    setup_fn: Callable[..., Any],
    *,
    setup_kwargs: Dict[str, Any] | None = None,
    tp_rr: float = 2.0,
    sl_atr: float = 1.0,
    fee_bps: float = 1.0,          # FX majors: tight; per side
    slippage_bps: float = 0.5,
    max_hold: int = 240,
    warmup: int = 80,
    atr_period: int = 14,
) -> List[Dict[str, Any]]:
    """Run one fx_setup over rows; return net-of-fee trades [{entry_ts,exit_ts,r,side}]."""
    setup_kwargs = setup_kwargs or {}
    n = len(rows)
    trades: List[Dict[str, Any]] = []
    i = max(warmup, atr_period + 2)
    while i < n - 1:
        sig = setup_fn(rows[: i + 1], **setup_kwargs)
        side = getattr(sig, "side", "none")
        if side not in ("long", "short"):
            i += 1
            continue
        a = atr(rows[: i + 1], atr_period)
        if not (a == a and a > 0):
            i += 1
            continue
        entry = _f(rows[i], CLOSE)
        if side == "long":
            stop = entry - sl_atr * a
            risk = entry - stop
            tp = entry + tp_rr * risk
        else:
            stop = entry + sl_atr * a
            risk = stop - entry
            tp = entry - tp_rr * risk
        if risk <= 0:
            i += 1
            continue

        # resolve on subsequent bars (causal), SL-first on same bar
        exit_j = min(n - 1, i + max_hold)
        r_gross = None
        for j in range(i + 1, min(n, i + 1 + max_hold)):
            hi, lo = _f(rows[j], HIGH), _f(rows[j], LOW)
            if side == "long":
                if lo <= stop:
                    r_gross = -1.0; exit_j = j; break
                if hi >= tp:
                    r_gross = tp_rr; exit_j = j; break
            else:
                if hi >= stop:
                    r_gross = -1.0; exit_j = j; break
                if lo <= tp:
                    r_gross = tp_rr; exit_j = j; break
        if r_gross is None:
            # timed out: mark-to-close in R
            c = _f(rows[exit_j], CLOSE)
            r_gross = ((c - entry) if side == "long" else (entry - c)) / risk

        # fees in R: round-trip cost / (risk as fraction of price)
        risk_frac = risk / entry
        fee_r = (2.0 * (fee_bps + slippage_bps) / 1e4) / max(1e-9, risk_frac)
        r_net = r_gross - fee_r
        trades.append({"entry_ts": _f(rows[i], TS), "exit_ts": _f(rows[exit_j], TS),
                       "r": round(r_net, 4), "side": side})
        i = exit_j + 1     # cooldown: no overlapping positions
    return trades


def summarize_trades(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Quick net-of-fee summary for a first read before the full gate."""
    rs = [float(t["r"]) for t in trades if t.get("r") == t.get("r")]
    n = len(rs)
    if not n:
        return {"trades": 0, "net_r": 0.0, "pf": 0.0, "win_rate": 0.0}
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    gp = sum(wins); gl = -sum(losses)
    return {"trades": n, "net_r": round(sum(rs), 3),
            "pf": round(gp / gl, 3) if gl > 0 else float("inf"),
            "win_rate": round(len(wins) / n, 3)}
