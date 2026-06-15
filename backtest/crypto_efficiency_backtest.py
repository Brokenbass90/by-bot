"""Crypto strategy EFFICIENCY backtester (signal-replay over OHLC).

Measures what actually matters for a 'workhorse' (per the owner's insight:
maximum efficiency / catching wide moves, NOT frequency):
  * trades, win%, avg_win_R, avg_loss_R, expectancy (R/trade), profit factor,
  * frequency (trades per 30 days).

It replays cached OHLC bar-by-bar into a strategy's maybe_signal(store, ...),
opens a trade on a signal, and simulates the exit (SL / TP / time-stop) on the
signal timeframe — measuring realised R = reward_or_loss / initial_risk.

Additive / standalone (imports strategy classes directly, NOT the monolith).
Designed to accept richer server data later; on the fragmentary local cache it
is a smoke/inspection tool. Run:
    PYTHONPATH=. python backtest/crypto_efficiency_backtest.py
"""
from __future__ import annotations

import bisect
import glob
import json
import math
import os
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data_cache"


def _load_interval(symbol: str, interval: str) -> List[list]:
    """Merge all cached files for symbol+interval into sorted list-rows [ts,o,h,l,c,v]."""
    rows: Dict[int, list] = {}
    for f in glob.glob(str(CACHE / f"{symbol}_{interval}_*.json")):
        try:
            data = json.loads(Path(f).read_text())
        except Exception:
            continue
        seq = data if isinstance(data, list) else data.get("data") or data.get("klines") or []
        for r in seq:
            if isinstance(r, dict):
                ts = int(r.get("ts") or r.get("start") or 0)
                row = [ts, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]),
                       float(r.get("v", 0.0))]
            else:
                ts = int(float(r[0]))
                row = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                       float(r[5] if len(r) > 5 else 0.0)]
            rows[ts] = row
    return [rows[t] for t in sorted(rows)]


class BacktestStore:
    """Serves fetch_klines(symbol, interval, limit) up to a moving cursor ts."""

    def __init__(self, symbol: str, intervals: List[str]):
        self.symbol = symbol
        self._data = {iv: _load_interval(symbol, iv) for iv in intervals}
        self._ts = {iv: [r[0] for r in rows] for iv, rows in self._data.items()}
        self._cursor_ts = 0

    def set_cursor(self, ts_ms: int):
        self._cursor_ts = ts_ms

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        rows = self._data.get(str(interval), [])
        ts = self._ts.get(str(interval), [])
        hi = bisect.bisect_right(ts, self._cursor_ts)  # rows with ts <= cursor
        lo = max(0, hi - limit) if limit else 0
        return rows[lo:hi]

    def has(self, interval: str) -> bool:
        return len(self._data.get(str(interval), [])) > 0


def _target_from_signal(sig) -> Optional[float]:
    """Pick a take-profit: explicit tp, else the FINAL ladder tp (widest move)."""
    tp = getattr(sig, "tp", None)
    if tp:
        return float(tp)
    tps = getattr(sig, "tps", None)
    if tps:
        return float(tps[-1])     # the runner's far target = the wide amplitude
    return None


def backtest(strategy, symbol: str, signal_tf: str, regime_tf: str,
             max_hold_bars: int = 200) -> dict:
    store = BacktestStore(symbol, [signal_tf, regime_tf])
    if not store.has(signal_tf):
        return {"error": f"no {signal_tf} data for {symbol}"}
    sig_rows = store._data[signal_tf]
    Rs: List[float] = []
    in_trade_until = -1
    first_ts = sig_rows[0][0] if sig_rows else 0
    last_ts = sig_rows[-1][0] if sig_rows else 0
    for i in range(len(sig_rows)):
        ts, o, h, l, c, v = sig_rows[i]
        if i <= in_trade_until:
            continue
        store.set_cursor(ts)
        try:
            sig = strategy.maybe_signal(store, ts, o, h, l, c, v)
        except Exception:
            sig = None
        if sig is None:
            continue
        side = str(getattr(sig, "side", "")).lower()
        entry = float(getattr(sig, "entry", c) or c)
        sl = getattr(sig, "sl", None)
        tp = _target_from_signal(sig)
        if not sl or entry <= 0:
            continue
        sl = float(sl)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        # simulate forward on signal tf
        exit_R = None
        for j in range(i + 1, min(i + 1 + max_hold_bars, len(sig_rows))):
            hj, lj, cj = sig_rows[j][2], sig_rows[j][3], sig_rows[j][4]
            if side in ("buy", "long"):
                if lj <= sl:
                    exit_R = -1.0; break
                if tp and hj >= tp:
                    exit_R = (tp - entry) / risk; break
            else:  # short
                if hj >= sl:
                    exit_R = -1.0; break
                if tp and lj <= tp:
                    exit_R = (entry - tp) / risk; break
            in_trade_until = j
        if exit_R is None:  # time-stop at last close
            cj = sig_rows[min(i + max_hold_bars, len(sig_rows) - 1)][4]
            exit_R = ((cj - entry) if side in ("buy", "long") else (entry - cj)) / risk
        Rs.append(exit_R)

    return _metrics(Rs, first_ts, last_ts)


def _metrics(Rs: List[float], first_ts: int, last_ts: int) -> dict:
    n = len(Rs)
    if n == 0:
        return {"trades": 0, "note": "no signals on available data"}
    wins = [r for r in Rs if r > 0]
    losses = [r for r in Rs if r <= 0]
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    gp = sum(wins); gl = -sum(losses)
    pf = (gp / gl) if gl > 0 else float("inf")
    days = max(1.0, (last_ts - first_ts) / 86400000.0)
    return {
        "trades": n,
        "win_pct": round(100.0 * len(wins) / n, 1),
        "avg_win_R": round(avg_w, 2),
        "avg_loss_R": round(avg_l, 2),
        "expectancy_R": round(sum(Rs) / n, 3),
        "profit_factor": round(pf, 2) if pf != float("inf") else "inf",
        "trades_per_30d": round(n / days * 30.0, 1),
    }


if __name__ == "__main__":
    from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy
    from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy
    # use intervals present in the local cache (override default 240/60 -> 60/5)
    os.environ.setdefault("ASB1_REGIME_TF", "60")
    os.environ.setdefault("ASB1_SIGNAL_TF", "5")
    print("=== crypto efficiency (local cache smoke; tool ready for server data) ===")
    for sym in ("SOLUSDT", "LINKUSDT", "ADAUSDT"):
        m = backtest(AltSupportBounceV1Strategy(), sym, signal_tf="5", regime_tf="60")
        print(f"ASB1 {sym:<9} {m}")
