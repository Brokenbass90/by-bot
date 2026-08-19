"""RESEARCH-ONLY: cross-sectional momentum (лонг сильных / шорт слабых) — 2026-07-20.

Раз в неделю по закрытым дневкам ранжируем 6 монет по return за L недель:
LONG top-2, SHORT bottom-2, по $250 на ногу ($1000 гросс, ~рыночно-нейтрально).
Издержки 6+2bps/сторона при смене состава, funding 3bps/день на каждую ногу.

ЗАМОРОЖЕННЫЙ ГЕЙТ (до прогона, менять нельзя):
  скрин-эпоха 2023-07..2026-07 И holdout 2021-10..2023-07 (все 6 монет торгуются)
  ОБЕ должны дать: net > +5R и худший год > -15R. Иначе FAIL.
"""
from __future__ import annotations
import json, os, sys, datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from level_dca_v1 import FEE_SIDE, FUNDING_PER_DAY

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
LEG = 250.0
R_UNIT = 100.0
CUT_HOLD_START = 1634256000000   # 2021-10-15 (все 6 листингованы)
CUT_SPLIT = 1688515200000        # 2023-07-05


def load():
    data = {}
    for s in SYMS:
        rows = json.load(open(os.path.join(_HERE, "data", f"daily_{s}.json")))
        data[s] = {int(r[0]): r for r in rows}
    ts_common = sorted(set.intersection(*[set(d.keys()) for d in data.values()]))
    return data, ts_common


def xs(data, ts_list, L_weeks=4, k=2):
    Ld = L_weeks * 7
    pos = {}          # sym -> +1/-1
    entry = {}        # sym -> (px, ts)
    trades = []
    for i in range(Ld + 1, len(ts_list) - 1, 7):
        t = ts_list[i]
        rets = {}
        for s in SYMS:
            c_now = data[s][t][4]
            t_past = ts_list[i - Ld]
            rets[s] = c_now / data[s][t_past][4] - 1.0
        ranked = sorted(rets, key=rets.get)
        want = {s: -1 for s in ranked[:k]}
        want.update({s: +1 for s in ranked[-k:]})
        nxt_t = ts_list[i + 1]
        for s in set(list(pos) + list(want)):
            w = want.get(s, 0)
            p = pos.get(s, 0)
            if w != p:
                o = data[s][nxt_t][1]
                if p != 0:
                    e_px, e_ts = entry[s]
                    days = (nxt_t - e_ts) / 86400000.0
                    gross = (o / e_px - 1.0) * LEG * p
                    pnl = gross - LEG * FEE_SIDE * 2 - LEG * FUNDING_PER_DAY * days
                    trades.append({"sym": s, "exit_ts": nxt_t, "r": pnl / R_UNIT})
                if w != 0:
                    entry[s] = (o, nxt_t)
                if w == 0:
                    pos.pop(s, None); entry.pop(s, None)
                else:
                    pos[s] = w
    last_t = ts_list[-1]
    for s, p in list(pos.items()):
        e_px, e_ts = entry[s]
        days = (last_t - e_ts) / 86400000.0
        pnl = (data[s][last_t][4] / e_px - 1.0) * LEG * p - LEG * FEE_SIDE * 2 - LEG * FUNDING_PER_DAY * days
        trades.append({"sym": s, "exit_ts": last_t, "r": pnl / R_UNIT})
    return trades


def report(tag, trades):
    net = round(sum(t["r"] for t in trades), 2)
    by_year = {}
    for t in trades:
        y = datetime.datetime.utcfromtimestamp(t["exit_ts"] / 1000).year
        by_year[y] = round(by_year.get(y, 0) + t["r"], 2)
    worst_y = min(by_year.values()) if by_year else 0
    ok = net > 5.0 and worst_y > -15.0
    print(f"{tag}: net={net}R n={len(trades)} годы={by_year} -> {'OK' if ok else 'fail'}")
    return ok, net, by_year


if __name__ == "__main__":
    data, ts = load()
    for L in (2, 4, 8):
        scr = [t0 for t0 in ts if t0 >= CUT_SPLIT]
        hld = [t0 for t0 in ts if CUT_HOLD_START <= t0 < CUT_SPLIT]
        ok1, n1, y1 = report(f"L={L}w СКРИН 2023-2026", xs(data, scr, L_weeks=L))
        ok2, n2, y2 = report(f"L={L}w HOLDOUT 2021-2023", xs(data, hld, L_weeks=L))
        print(f"  => L={L}w ВЕРДИКТ: {'PASS' if (ok1 and ok2) else 'FAIL'}\n")
