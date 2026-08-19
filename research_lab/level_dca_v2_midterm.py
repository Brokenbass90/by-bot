"""RESEARCH-ONLY: level_dca_v2_midterm — «умная сетка» владельца (2026-07-20).

Отличия от провалившегося v1 (5m, 10 колен, без спасения):
- СРЕДНЕСРОК: сим на 1h барах, уровни на 4h, движения-цели 5-10%;
- МАЛО колен: 4-5 усреднений по сильным уровням (не сетка);
- RESCUE: если колена кончились — задача выйти в ~ноль (avg + издержки),
  а не сидеть до катастрофы; плюс time-stop 90д;
- ФЛЕТ-ГЕЙТ: опциональный вход только при низком Kaufman ER (боковик);
- отбор монет: считаем ER-флетовость символа и смотрим корреляцию с net
  (честно: по ВСЕМ монетам, без выбора победителей задним числом).

Издержки: 6+2 bps/сторона на каждое колено, funding 3bps/день. Каузально:
закрытые бары, исполнение next-open. НЕ прод. НЕ вердикт станции.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from level_dca_v1 import load_5m, to_1h, _pivots, _atr, FEE_SIDE, FUNDING_PER_DAY

IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]


def _agg_n(bars, n):
    out = []
    for i in range(0, len(bars) - len(bars) % n, n):
        ch = bars[i:i + n]
        out.append((ch[0][0], ch[0][1], max(b[2] for b in ch),
                    min(b[3] for b in ch), ch[-1][4]))
    return out


def to_4h(h1):
    out = []
    for i in range(0, len(h1) - len(h1) % 4, 4):
        ch = h1[i:i + 4]
        out.append((ch[0][0], ch[0][1], max(b[2] for b in ch),
                    min(b[3] for b in ch), ch[-1][4]))
    return out


def build_levels_4h(h1_closed, min_touches=2, lookback_4h=750, agg=4):
    h4 = (to_4h(h1_closed) if agg == 4 else _agg_n(h1_closed, agg))[-lookback_4h:]
    atr = _atr(h4)
    if atr <= 0 or len(h4) < 60:
        return [], [], 0.0
    tol = 0.5 * atr
    res = {}
    for mode in ("low", "high"):
        piv = sorted(_pivots(h4, left=3, right=3, mode=mode))
        levels, cluster = [], []
        for px in piv:
            if not cluster or px - cluster[0] <= tol:
                cluster.append(px)
            else:
                levels.append((sum(cluster) / len(cluster), len(cluster)))
                cluster = [px]
        if cluster:
            levels.append((sum(cluster) / len(cluster), len(cluster)))
        res[mode] = sorted(px for px, t in levels if t >= min_touches)
    return res["low"], res["high"], atr


def kaufman_er(closes, n=72):
    if len(closes) < n + 1:
        return 1.0
    seg = closes[-n - 1:]
    direction = abs(seg[-1] - seg[0])
    vol = sum(abs(seg[i] - seg[i - 1]) for i in range(1, len(seg)))
    return direction / vol if vol > 0 else 1.0


def simulate_mid(h1, side="long", capital=1000.0, tranches=5, leverage=1.0,
                 min_touches=2, touch_tol_atr=0.25, level_gap_atr=0.75,
                 tp_buf_atr=0.25, min_tp_pct=0.05, max_tp_pct=0.10,
                 rescue=True, rescue_pad=0.002,
                 er_gate=None,  # None=off, иначе порог ER (напр. 0.25)
                 er_n=72, trend_gate=None,  # trend_gate="with": long только в аптренде (EMA200+наклон)
                 level_agg=4, max_hold_days=90, refit_bars=24):
    tranche_margin = capital / tranches
    sup = resl = []
    atr = 0.0
    pos, pend = None, None
    cycles, equity = [], capital
    eq_min = eq_max = capital
    closes = [b[4] for b in h1]
    ema = []
    if trend_gate is not None:
        k = 2.0 / 201.0
        e = closes[0]
        for c_ in closes:
            e = c_ * k + e * (1 - k)
            ema.append(e)

    def avg_px():
        tot_n = sum(n for _, n in pos["legs"])
        return sum(px * n for px, n in pos["legs"]) / tot_n, tot_n

    def close_cycle(exit_px, ts, reason):
        nonlocal pos, equity, eq_min, eq_max
        a, tot_n = avg_px()
        gross = (exit_px / a - 1.0) * tot_n if side == "long" else (1.0 - exit_px / a) * tot_n
        days = max(0.0, (ts - pos["entry_ts"]) / 86400000.0)
        pnl = gross - tot_n * FEE_SIDE * 2 - tot_n * FUNDING_PER_DAY * days
        equity += pnl
        eq_min = min(eq_min, equity); eq_max = max(eq_max, equity)
        cycles.append({"pnl": round(pnl, 2), "legs": len(pos["legs"]),
                       "days": round(days, 1), "reason": reason})
        pos = None

    n = len(h1)
    for i in range(200, n - 1):
        ts, o, h, l, c = h1[i]
        if pend is not None:
            act, pend = pend, None
            if act[0] == "enter" and pos is None:
                pos = {"legs": [(o, tranche_margin * leverage)], "last_lvl": act[1], "entry_ts": ts}
            elif act[0] == "add" and pos is not None and len(pos["legs"]) < tranches:
                pos["legs"].append((o, tranche_margin * leverage)); pos["last_lvl"] = act[1]

        if i % refit_bars == 0:
            sup, resl, atr = build_levels_4h(h1[:i], min_touches=min_touches, agg=level_agg)
        if atr <= 0:
            continue
        lv_entry = sup if side == "long" else resl
        lv_target = resl if side == "long" else sup

        if pos is None:
            if not lv_entry:
                continue
            if er_gate is not None and kaufman_er(closes[max(0, i - er_n - 1):i + 1], n=er_n) > er_gate:
                continue
            if trend_gate == "with":
                if side == "long" and not (c > ema[i] and ema[i] > ema[max(0, i - 24)]):
                    continue
                if side == "short" and not (c < ema[i] and ema[i] < ema[max(0, i - 24)]):
                    continue
            for L_ in (reversed(lv_entry) if side == "long" else lv_entry):
                if side == "long":
                    if L_ > c:
                        continue
                    if l <= L_ + touch_tol_atr * atr and c >= L_ and c <= L_ + 1.5 * atr:
                        pend = ("enter", L_); break
                else:
                    if L_ < c:
                        continue
                    if h >= L_ - touch_tol_atr * atr and c <= L_ and c >= L_ - 1.5 * atr:
                        pend = ("enter", L_); break
            continue

        a, tot_n = avg_px()
        full = len(pos["legs"]) >= tranches

        # rescue: колена кончились -> выйти в ~ноль при первом касании
        if rescue and full:
            r_px = a * (1 + 2 * FEE_SIDE + rescue_pad) if side == "long" else a * (1 - 2 * FEE_SIDE - rescue_pad)
            if (side == "long" and h >= r_px) or (side == "short" and l <= r_px):
                close_cycle(r_px, ts, "rescue"); continue

        if (ts - pos["entry_ts"]) / 86400000.0 >= max_hold_days:
            close_cycle(c, ts, "time"); continue

        # тейк 5-10%: перед следующим уровнем, но не дальше max_tp_pct
        if side == "long":
            lo_t, hi_t = a * (1 + min_tp_pct), a * (1 + max_tp_pct)
            nxt = [x for x in lv_target if lo_t < x <= hi_t * 1.02]
            tp = (min(nxt) - tp_buf_atr * atr) if nxt else hi_t
            tp = max(min(tp, hi_t), lo_t)
            if h >= tp:
                close_cycle(tp, ts, "tp"); continue
        else:
            lo_t, hi_t = a * (1 - min_tp_pct), a * (1 - max_tp_pct)
            nxt = [x for x in lv_target if hi_t * 0.98 <= x < lo_t]
            tp = (max(nxt) + tp_buf_atr * atr) if nxt else hi_t
            tp = min(max(tp, hi_t), lo_t)
            if l <= tp:
                close_cycle(tp, ts, "tp"); continue

        if not full:
            if side == "long":
                deeper = [x for x in lv_entry if x < pos["last_lvl"] - level_gap_atr * atr]
                if deeper:
                    nl = max(deeper)
                    if l <= nl + touch_tol_atr * atr and c >= nl:
                        pend = ("add", nl)
            else:
                deeper = [x for x in lv_entry if x > pos["last_lvl"] + level_gap_atr * atr]
                if deeper:
                    nl = min(deeper)
                    if h >= nl - touch_tol_atr * atr and c <= nl:
                        pend = ("add", nl)

    if pos is not None:
        close_cycle(h1[-1][4], h1[-1][0], "eod")

    wins = [x for x in cycles if x["pnl"] > 0]
    return {
        "cycles": len(cycles), "net": round(equity - capital, 2),
        "wr": round(len(wins) / len(cycles), 3) if cycles else 0.0,
        "worst": round(min((x["pnl"] for x in cycles), default=0.0), 2),
        "rescues": sum(1 for x in cycles if x["reason"] == "rescue"),
        "timeouts": sum(1 for x in cycles if x["reason"] == "time"),
        "full_depth": sum(1 for x in cycles if x["legs"] >= tranches),
        "maxdd": round(eq_max - eq_min, 2), "eq_min": round(eq_min, 2),
        "avg_days": round(sum(x["days"] for x in cycles) / len(cycles), 1) if cycles else 0.0,
    }


GRID = [
    {"side": s, "er_gate": eg, "min_tp_pct": tp, "max_tp_pct": tp * 2}
    for s in ("long", "short") for eg in (None, 0.25) for tp in (0.05,)
] + [
    {"side": s, "er_gate": None, "min_tp_pct": 0.03, "max_tp_pct": 0.06}
    for s in ("long", "short")
] + [
    {"side": s, "er_gate": 0.25, "min_tp_pct": 0.03, "max_tp_pct": 0.06}
    for s in ("long", "short")
]


def run(run_id="level_dca_v2_midterm"):
    import time
    path = os.path.join(_HERE, "results", f"{run_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line); done.add((r["sym"], json.dumps(r["params"], sort_keys=True)))
            except Exception:
                pass
    t0 = time.time()
    for sym in IS_SYMBOLS + OOS_SYMBOLS:
        h1 = None
        for p in GRID:
            key = (sym, json.dumps(p, sort_keys=True))
            if key in done:
                continue
            if h1 is None:
                b5 = load_5m(sym)
                if not b5:
                    break
                h1 = to_1h(b5)
            er_sym = kaufman_er([b[4] for b in h1], n=len(h1) - 1)
            m = simulate_mid(h1, **p)
            rec = {"sym": sym, "params": p, **m, "sym_er": round(er_sym, 4),
                   "oos": sym in OOS_SYMBOLS}
            with open(path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            eg = p["er_gate"]
            print(f"{sym} {p['side']} er={eg} tp={p['min_tp_pct']}: net={m['net']} "
                  f"cyc={m['cycles']} wr={m['wr']} worst={m['worst']} resc={m['rescues']} "
                  f"full={m['full_depth']}", flush=True)
            if time.time() - t0 > 38:
                print("CHUNK_TIMEOUT"); return False
    print("ALL_DONE"); return True


if __name__ == "__main__":
    run()
