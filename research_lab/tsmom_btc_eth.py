"""TSMOM_BTC_ETH — prereg research_lab/prereg/PREREG_TSMOM_BTC_ETH_D1_2026_10_22.md"""
import json, math, random, statistics as st, sys, datetime as dt
from pathlib import Path

D = Path(sys.argv[1])
END = dt.date(2021, 4, 30)
COST = 8e-4
FUND_SHORT_WEEK = 1e-4 * 21  # 1 bp за 8 ч, 21 начисление в неделю
TV, CAP = 0.20, 1.5


def weekly(sym):
    rows = json.load(open(D / f"{sym}.json"))
    w = {}
    for ts, o, h, l, c, v in rows:
        d = dt.datetime.utcfromtimestamp(ts / 1000).date()
        if d > END:
            continue
        w[d.isocalendar()[:2]] = (d, c)
    ks = sorted(w)[:-1]  # последняя неделя может быть неполной
    ks = ks[1:]          # первая неполная (с 17.08.2017)
    dates = [w[k][0] for k in ks]
    px = [w[k][1] for k in ks]
    r = [math.log(px[i] / px[i - 1]) for i in range(1, len(px))]
    return dates[1:], r


def leg(r, L, long_only=False, signs=None):
    """Недельная доходность ноги с i=L... Возвращает список (доходность после расходов)."""
    out, prev_w = [], 0.0
    for i in range(L, len(r)):
        past = sum(r[i - L:i])
        sg = (1 if past > 0 else -1) if signs is None else signs[i - L]
        if long_only and sg < 0:
            sg = 0
        win = r[max(0, i - 12):i]
        sig = st.pstdev(win) * math.sqrt(52) if len(win) >= 4 else 0.0
        w = sg * min(CAP, TV / sig) if sig > 0 else 0.0
        ret = w * (math.exp(r[i]) - 1)
        ret -= abs(w - prev_w) * COST
        if w < 0:
            ret -= abs(w) * FUND_SHORT_WEEK
        prev_w = w
        out.append(ret)
    return out


def stats(p):
    n = len(p)
    m, s = st.mean(p), st.pstdev(p)
    eq, pk, mdd = 1.0, 1.0, 0.0
    for x in p:
        eq *= 1 + x; pk = max(pk, eq); mdd = max(mdd, 1 - eq / pk)
    yrs = n / 52.18
    return {"n_nedel": n, "sred_%_nedelya": round(m * 100, 3), "t": round(m / (s / math.sqrt(n)), 2),
            "god_%": round((eq ** (1 / yrs) - 1) * 100, 1), "sharpe": round(m / s * math.sqrt(52), 2),
            "maks_prosadka_%": round(mdd * 100, 1), "itog_x": round(eq, 2)}


def port(a, b):
    k = min(len(a), len(b))
    return [0.5 * x + 0.5 * y for x, y in zip(a[-k:], b[-k:])]


def main():
    dB, rB = weekly("BTCUSDT")
    dE, rE = weekly("ETHUSDT")
    assert dB == dE
    out = {}
    L = 12
    a, b = leg(rB, L), leg(rE, L)
    P = port(a, b)
    out["osnovnaya_L12"] = stats(P)
    out["BTC"] = stats(a); out["ETH"] = stats(b)
    # перестановки знаков
    rng = random.Random(20261022)
    real = st.mean(P)
    better = 0
    N = 2000
    for _ in range(N):
        sa = [rng.choice((1, -1)) for _ in range(len(rB) - L)]
        sb = [rng.choice((1, -1)) for _ in range(len(rE) - L)]
        q = port(leg(rB, L, signs=sa), leg(rE, L, signs=sb))
        if st.mean(q) >= real:
            better += 1
    out["p_perestanovok"] = round(better / N, 4)
    # описание
    hold = port(leg(rB, L, signs=[1] * (len(rB) - L)), leg(rE, L, signs=[1] * (len(rE) - L)))
    out["kupit_derzhat_tot_zhe_risk"] = stats(hold)
    out["L4"] = stats(port(leg(rB, 4)[8:], leg(rE, 4)[8:]))
    out["L26"] = stats(port(leg(rB, 26), leg(rE, 26)))
    out["tolko_long_L12"] = stats(port(leg(rB, L, long_only=True), leg(rE, L, long_only=True)))
    dates = dB[L:]
    po = {}
    for d, x in zip(dates, P):
        po.setdefault(d.year, []).append(x)
    out["po_godam_%"] = {y: round((math.prod(1 + x for x in v) - 1) * 100, 1) for y, v in po.items()}
    out["period"] = [str(dates[0]), str(dates[-1])]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
