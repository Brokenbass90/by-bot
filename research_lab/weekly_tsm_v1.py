"""RESEARCH-ONLY: weekly time-series momentum BTC/ETH (первые цифры, скрининг).

Идея: среднесрок с БОЛЬШОЙ амплитудой монетизируется трендом, не усреднением.
Правило: раз в неделю по закрытым дневкам считаем return за L недель;
>0 -> long, <0 -> short (или flat в long-only). Позиция $1000, без плеча.
Издержки: 6+2 bps на сторону при смене позиции, funding 3bps/день в позиции.
Каузально: решение на закрытой неделе, исполнение next open. НЕ вердикт станции.
"""
from __future__ import annotations
import json, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from level_dca_v1 import load_5m, to_1h, FEE_SIDE, FUNDING_PER_DAY


def to_daily(h1):
    out = []
    for i in range(0, len(h1) - len(h1) % 24, 24):
        ch = h1[i:i + 24]
        out.append((ch[0][0], ch[0][1], max(b[2] for b in ch),
                    min(b[3] for b in ch), ch[-1][4]))
    return out


def tsm(daily, lookback_w=8, mode="long_short", capital=1000.0):
    L = lookback_w * 7
    pos = 0            # -1/0/+1
    entry_px = None
    equity = capital
    eq_max = equity; maxdd = 0.0
    flips = 0; wins = 0; trades = 0; days_in = 0
    pnl_hist = []
    for i in range(L + 1, len(daily) - 1, 7):        # раз в неделю
        c = daily[i][4]
        ret = c / daily[i - L][4] - 1.0
        want = 1 if ret > 0 else (-1 if mode == "long_short" else 0)
        if want != pos:
            nxt_open = daily[i + 1][1]
            if pos != 0 and entry_px:
                gross = (nxt_open / entry_px - 1.0) * capital * pos
                pnl = gross - capital * FEE_SIDE - capital * FUNDING_PER_DAY * days_in
                equity += pnl; pnl_hist.append(pnl)
                trades += 1; wins += 1 if pnl > 0 else 0
            if want != 0:
                equity -= capital * FEE_SIDE
                entry_px = nxt_open
                days_in = 0
            pos = want; flips += 1
        if pos != 0:
            days_in += 7
        # equity mark для DD
        if pos != 0 and entry_px:
            mark = equity + (c / entry_px - 1.0) * capital * pos
        else:
            mark = equity
        eq_max = max(eq_max, mark); maxdd = max(maxdd, eq_max - mark)
    if pos != 0 and entry_px:
        last = daily[-1][4]
        pnl = (last / entry_px - 1.0) * capital * pos - capital * FEE_SIDE - capital * FUNDING_PER_DAY * days_in
        equity += pnl; pnl_hist.append(pnl); trades += 1; wins += 1 if pnl > 0 else 0
    bh = (daily[-1][4] / daily[0][4] - 1.0) * capital
    return {"net": round(equity - capital, 1), "maxdd": round(maxdd, 1),
            "trades": trades, "wr": round(wins / trades, 2) if trades else 0,
            "buyhold": round(bh, 1),
            "worst": round(min(pnl_hist, default=0.0), 1),
            "best": round(max(pnl_hist, default=0.0), 1)}


if __name__ == "__main__":
    path = os.path.join(_HERE, "results", "weekly_tsm_v1.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        b5 = load_5m(sym)
        if not b5:
            continue
        daily = to_daily(to_1h(b5))
        days = len(daily)
        for lb in (4, 8, 12, 26):
            for mode in ("long_short", "long_only"):
                m = tsm(daily, lookback_w=lb, mode=mode)
                rec = {"sym": sym, "lookback_w": lb, "mode": mode, "days": days, **m}
                with open(path, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                print(f"{sym} L={lb}w {mode:10}: net={m['net']:>7} dd={m['maxdd']:>6} "
                      f"trades={m['trades']} wr={m['wr']} bh={m['buyhold']}", flush=True)
