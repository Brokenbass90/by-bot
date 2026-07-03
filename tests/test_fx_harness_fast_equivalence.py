"""Golden equivalence: fast fx_harness (PrefixView + prefix-ATR) must produce
bit-identical trades to the original O(n^2) implementation."""
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.fx_harness import backtest_fx_setup, _atr_at, _prefix_atr_arrays, _f
from bot.market_context import atr, HIGH, LOW, CLOSE, TS


def _reference_backtest(rows, setup_fn, *, setup_kwargs=None, tp_rr=2.0, sl_atr=1.0,
                        fee_bps=1.0, slippage_bps=0.5, max_hold=240, warmup=80,
                        atr_period=14) -> List[Dict[str, Any]]:
    """Verbatim copy of the ORIGINAL slow harness loop (golden reference)."""
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
            c = _f(rows[exit_j], CLOSE)
            r_gross = ((c - entry) if side == "long" else (entry - c)) / risk
        risk_frac = risk / entry
        fee_r = (2.0 * (fee_bps + slippage_bps) / 1e4) / max(1e-9, risk_frac)
        trades.append({"entry_ts": _f(rows[i], TS), "exit_ts": _f(rows[exit_j], TS),
                       "r": round(r_gross - fee_r, 4), "side": side})
        i = exit_j + 1
    return trades


class _Sig:
    def __init__(self, side):
        self.side = side


def _noisy_setup(rows, mod=17):
    """Deterministic pseudo-setup exercising len(), [-k:] slices and indexing."""
    n = len(rows)
    if n % mod == 0:
        tail = rows[-3:]
        return _Sig("long" if tail[-1][4] > tail[0][4] else "short")
    if n % (mod * 2) == 1:
        return _Sig("short")
    return _Sig("none")


def _random_rows(n, seed=7):
    rnd = random.Random(seed)
    rows, px = [], 100.0
    for i in range(n):
        px *= 1 + rnd.uniform(-0.01, 0.01)
        hi = px * (1 + rnd.uniform(0, 0.008))
        lo = px * (1 - rnd.uniform(0, 0.008))
        rows.append([i * 3_600_000, px, hi, lo, px * (1 + rnd.uniform(-0.004, 0.004)), 10.0])
    return rows


def test_prefix_atr_matches_reference():
    rows = _random_rows(400)
    fin_sums, cnt_at = _prefix_atr_arrays(rows)
    for i in (1, 2, 13, 14, 15, 100, 399):
        ref = atr(rows[: i + 1], 14)
        fast = _atr_at(fin_sums, cnt_at, i, 14)
        assert (ref != ref and fast != fast) or abs(ref - fast) < 1e-12, i


def test_fast_harness_bit_identical_to_reference():
    rows = _random_rows(1200)
    for seed_mod in (13, 17, 29):
        setup = lambda r, m=seed_mod: _noisy_setup(r, m)
        ref = _reference_backtest(rows, setup, tp_rr=1.5, sl_atr=0.8)
        fast = backtest_fx_setup(rows, setup, tp_rr=1.5, sl_atr=0.8)
        assert ref == fast, f"mismatch mod={seed_mod}: {len(ref)} vs {len(fast)} trades"


def test_fast_harness_with_nan_bars():
    rows = _random_rows(600)
    rows[50][2] = float("nan")  # broken high -> non-finite TR path
    rows[51][3] = float("nan")
    setup = lambda r: _noisy_setup(r, 11)
    assert _reference_backtest(rows, setup) == backtest_fx_setup(rows, setup)
