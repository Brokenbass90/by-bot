"""FX backtest harness — run fx_setups over FX/CFD data honestly, feed the gate.

Unblocks the FX track: fx_setups are built, but had no runner. This walks bars,
calls a setup, opens a maker-ish trade with a fixed R (SL=sl_atr*ATR, TP=tp_rr*R),
resolves it on SUBSEQUENT bars (SL-first on same bar = conservative), charges fees
in R, and returns trades ready for wf_folds -> oos_selector. Causal: exits use only
bars AFTER entry; one position at a time (cooldown). Pure stdlib + market_context.atr.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Sequence

from bot.market_context import atr, HIGH, LOW, CLOSE, TS


def _f(row, i):
    try:
        return float(row[i])
    except (IndexError, TypeError, ValueError):
        return float("nan")


class _PrefixView(Sequence):
    """Zero-copy causal view of rows[:n] — kills the O(n^2) slice-per-bar cost.

    Setups only ever read history (len, indexing, small negative slices), so a
    lightweight prefix view is behaviourally identical to rows[:n]."""
    __slots__ = ("_rows", "_n")

    def __init__(self, rows: Sequence[Sequence[float]], n: int) -> None:
        self._rows = rows
        self._n = int(n)

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self._n)
            return [self._rows[j] for j in range(start, stop, step)]
        i = int(idx)
        if i < 0:
            i += self._n
        if i < 0 or i >= self._n:
            raise IndexError(idx)
        return self._rows[i]


def _prefix_atr_arrays(rows: Sequence[Sequence[float]]):
    """Precompute finite-TR prefix sums so ATR(rows[:i+1]) is O(1) per bar.

    Replicates bot.market_context.atr exactly: TR list keeps FINITE values only,
    ATR = mean of the last `period` entries of that finite list."""
    fin_sums = [0.0]          # prefix sums of finite TRs (in order)
    cnt_at = [0] * len(rows)  # finite-TR count among bars 1..i
    c = 0
    for i in range(1, len(rows)):
        h, l = _f(rows[i], HIGH), _f(rows[i], LOW)
        pc = _f(rows[i - 1], CLOSE)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        if tr == tr and tr not in (float("inf"), float("-inf")):
            c += 1
            fin_sums.append(fin_sums[-1] + tr)
        cnt_at[i] = c
    return fin_sums, cnt_at


def _atr_at(fin_sums, cnt_at, i: int, period: int) -> float:
    """ATR of rows[:i+1] (same value as market_context.atr(rows[:i+1], period))."""
    if i < 1:
        return float("nan")
    c = cnt_at[i]
    if c == 0:
        return float("nan")
    w = min(int(max(1, period)), c)
    return (fin_sums[c] - fin_sums[c - w]) / w


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
    fin_sums, cnt_at = _prefix_atr_arrays(rows)
    try:
        accepts_atr_value = "atr_value" in inspect.signature(setup_fn).parameters
    except (TypeError, ValueError):
        accepts_atr_value = False
    i = max(warmup, atr_period + 2)
    while i < n - 1:
        a = _atr_at(fin_sums, cnt_at, i, atr_period)
        kwargs = setup_kwargs
        if accepts_atr_value:
            kwargs = {**setup_kwargs, "atr_value": a if (a == a and a > 0) else None}
        sig = setup_fn(_PrefixView(rows, i + 1), **kwargs)
        side = getattr(sig, "side", "none")
        if side not in ("long", "short"):
            i += 1
            continue
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


def cost_feasibility(
    rows: Sequence[Sequence[float]],
    *,
    sl_atr: float = 1.0,
    fee_bps: float = 1.0,
    slippage_bps: float = 0.5,
    atr_period: int = 14,
    max_fee_r: float = 0.25,
) -> Dict[str, Any]:
    """Refuse to backtest a doomed (data x timeframe x cost) combination.

    EURUSD/M5 lesson (2026-07-03): with ATR ~2 pips a 0.8*ATR stop makes the
    round-trip cost ~1.78R per trade — every result is an artifact of costs,
    not the market (screen showed PF 0.00 over 1111 trades). Call this BEFORE
    backtest_fx_setup; if feasible=False the run is uninformative: fix the
    timeframe/data or the cost model, do not read the PF.
    """
    a = atr(rows, atr_period) if len(rows) > atr_period + 2 else float("nan")
    price = _f(rows[-1], CLOSE) if rows else float("nan")
    if not (a == a and a > 0 and price == price and price > 0):
        return {"feasible": False, "fee_r": float("nan"), "reason": "no_atr_or_price"}
    risk_frac = max(1e-9, float(sl_atr) * a / price)
    fee_r = (2.0 * (float(fee_bps) + float(slippage_bps)) / 1e4) / risk_frac
    if fee_r > float(max_fee_r):
        return {"feasible": False, "fee_r": round(fee_r, 4),
                "reason": f"fee_r_{fee_r:.2f}_exceeds_{max_fee_r}"}
    return {"feasible": True, "fee_r": round(fee_r, 4), "reason": ""}


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
