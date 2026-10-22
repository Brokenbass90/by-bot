"""BTC_ETH_SREDNESROK_OTKAT — проверка btc_eth_midterm_pullback (код без изменений, конфиг по умолчанию).
Prereg: research_lab/prereg/PREREG_BTC_ETH_SREDNESROK_OTKAT_2026_10_22.md
Версия A (критерий): трейлинг 1.1×ATR14 часовика, пересчёт на закрытии часа. B: трейлинг по ATR14 5m с первого бара
(как в движке). C: без трейлинга. Контроль: 20 случайных входов той же монеты/стороны/месяца в часы с той же стороной тренда.
"""
import bisect, json, math, random, statistics as st, sys, datetime as dt, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategies.btc_eth_midterm_pullback import BTCETHMidtermPullbackStrategy, _atr_from_rows  # noqa

COST = 8e-4          # 6 bps комиссия + 2 bps проскальзывание, на сторону
H, H4, M5 = 3600_000, 4 * 3600_000, 300_000
TSTOP = 84
SEED = 20261022


def agg(c5, step):
    out, cur = [], None
    for ts, o, h, l, c, v in c5:
        k = ts // step * step
        if cur is None or cur[0] != k:
            if cur: out.append(cur)
            cur = [k, o, h, l, c, v]
        else:
            cur[2] = max(cur[2], h); cur[3] = min(cur[3], l); cur[4] = c; cur[5] += v
    if cur: out.append(cur)
    return out


class Store:
    def __init__(self, sym, c5):
        self.symbol = sym
        self.c5 = c5
        self.tf = {"60": agg(c5, H), "240": agg(c5, H4)}
        self.st = {k: [r[0] for r in v] for k, v in self.tf.items()}
        self.step = {"60": H, "240": H4}
        self.now_end = 0

    def closed(self, tf):
        # число закрытых баров: старт + шаг <= конец текущей 5m-свечи
        return bisect.bisect_right(self.st[tf], self.now_end - self.step[tf])

    def fetch_klines(self, symbol, interval, limit):
        n = self.closed(str(interval))
        return self.tf[str(interval)][max(0, n - int(limit)):n]


def atr5(c5, j, p=14):
    trs = []
    for k in range(j - p + 1, j + 1):
        h, l, pc = c5[k][2], c5[k][3], c5[k - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / p


def simulate(store, i_sig, side, sl, tp1, tp2, mode):
    """Вход по открытию бара i_sig+1. Возвращает R после расходов или None."""
    c5 = store.c5
    j0 = i_sig + 1
    if j0 + TSTOP >= len(c5):
        return None
    e = c5[j0][1]
    d = 1 if side == "long" else -1
    risk = (e - sl) * d
    if risk <= 0:
        return None
    rem, R, cost = 1.0, 0.0, COST * e / risk  # вход
    tp1_done = False
    best = e
    cur_sl = sl
    hold = 0
    for j in range(j0, j0 + TSTOP):
        ts, o, h, l, c, v = c5[j]
        hold = j - j0 + 1
        # стоп первым
        hit = (l <= cur_sl) if d == 1 else (h >= cur_sl)
        if hit:
            px = cur_sl if ((o > cur_sl) if d == 1 else (o < cur_sl)) else o
            R += rem * (px - e) * d / risk; cost += rem * COST * px / risk; rem = 0
            break
        if not tp1_done and ((h >= tp1) if d == 1 else (l <= tp1)):
            R += 0.5 * (tp1 - e) * d / risk; cost += 0.5 * COST * tp1 / risk; rem -= 0.5; tp1_done = True
        if (h >= tp2) if d == 1 else (l <= tp2):
            R += rem * (tp2 - e) * d / risk; cost += rem * COST * tp2 / risk; rem = 0
            break
        best = max(best, h) if d == 1 else min(best, l)
        new = None
        if mode == "A" and (ts + M5) % H == 0:
            store.now_end = ts + M5
            rows = store.fetch_klines(store.symbol, "60", 40)
            if len(rows) >= 16:
                a = _atr_from_rows(rows, 14)
                if a == a and a > 0:
                    new = best - d * 1.1 * a
        elif mode == "B" and j >= 15:
            new = best - d * 1.1 * atr5(c5, j)
        if new is not None and ((new > cur_sl) if d == 1 else (new < cur_sl)):
            cur_sl = new
    if rem > 0:
        px = c5[j0 + TSTOP - 1][4]
        R += rem * (px - e) * d / risk; cost += rem * COST * px / risk
    return R - cost, hold


def load(sym):
    p = Path(sys.argv[1]) / f"{sym}USDT_5_1688515200000_1783123200000.json"
    raw = json.load(open(p))
    c5 = [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in raw]
    c5.sort(key=lambda r: r[0])
    return c5


def week(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000).strftime("%G-W%V")


def month(ts):
    return dt.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m")


def cl_t(xs, keys):
    n = len(xs)
    if n < 3: return float("nan")
    m = sum(xs) / n
    g = collections.defaultdict(float)
    for x, k in zip(xs, keys): g[k] += x - m
    se = math.sqrt(sum(v * v for v in g.values())) / n
    return m / se if se > 0 else float("nan")


def main():
    rng = random.Random(SEED)
    trades, ctrl_pool = [], {}
    for sym in ("BTC", "ETH"):
        c5 = load(sym)
        store = Store(sym + "USDT", c5)
        strat = BTCETHMidtermPullbackStrategy()
        busy_until = -1
        # часы с биасом тренда (для контроля)
        bias_hours = collections.defaultdict(list)  # (month, side) -> [(i5 входа-1, sl_dist)]
        for i, (ts, o, h, l, c, v) in enumerate(c5):
            store.now_end = ts + M5
            if (ts + M5) % H == 0 and i > 0:
                b = strat._trend_bias(store)
                if b in (0, 2):
                    rows = store.fetch_klines(store.symbol, "60", 40)
                    if len(rows) >= 16:
                        a = _atr_from_rows(rows, 14)
                        if a == a and a > 0:
                            bias_hours[(month(ts), "long" if b == 2 else "short")].append((i, a))
            if i <= busy_until:
                continue
            sig = strat.maybe_signal(store, ts, o, h, l, c, v)
            if sig is None:
                continue
            res = {}
            for mode in "ABC":
                r = simulate(store, i, sig.side, sig.sl, sig.tps[0], sig.tps[1], mode)
                res[mode] = r
            store.now_end = ts + M5
            if res["A"] is None:
                continue
            trades.append({"sym": sym, "side": sig.side, "ts": c5[i + 1][0], "i": i,
                           "A": res["A"][0], "holdA": res["A"][1], "B": res["B"][0], "holdB": res["B"][1],
                           "C": res["C"][0]})
            busy_until = i + res["A"][1]  # одна позиция на монету (по версии A)
        # контроль
        for t in trades:
            if t["sym"] != sym: continue
            pool = bias_hours.get((month(t["ts"]), t["side"]), [])
            vals = []
            for _ in range(20):
                if not pool: break
                i, a = rng.choice(pool)
                if i + 1 + TSTOP >= len(c5): continue
                e = c5[i + 1][1]
                d = 1 if t["side"] == "long" else -1
                sl = e - d * 1.2 * a
                risk = 1.2 * a
                r = simulate(store, i, t["side"], sl, e + d * 1.2 * risk, e + d * 2.6 * risk, "A")
                if r: vals.append(r[0])
            t["ctrl"] = st.mean(vals) if vals else None
        print(sym, "сделок", sum(1 for t in trades if t["sym"] == sym), flush=True)

    T = [t for t in trades if t["ctrl"] is not None]
    wk = [week(t["ts"]) for t in T]
    out = {"n": len(T)}
    for m in "ABC":
        xs = [t[m] for t in T]
        out[m] = {"R": round(st.mean(xs), 4), "t": round(cl_t(xs, wk), 2), "win": round(sum(x > 0 for x in xs) / len(xs), 3)}
    out["medhold_h"] = {"A": st.median(t["holdA"] for t in T) / 12, "B": st.median(t["holdB"] for t in T) / 12}
    ctrl = [t["ctrl"] for t in T]
    exc = [t["A"] - t["ctrl"] for t in T]
    out["ctrl_R"] = round(st.mean(ctrl), 4)
    out["prevyshenie"] = round(st.mean(exc), 4)
    out["t_prev"] = round(cl_t(exc, wk), 2)
    for key, f in (("long", lambda t: t["side"] == "long"), ("short", lambda t: t["side"] == "short"),
                   ("BTC", lambda t: t["sym"] == "BTC"), ("ETH", lambda t: t["sym"] == "ETH")):
        s = [t for t in T if f(t)]
        out[key] = {"n": len(s), "R_A": round(st.mean(t["A"] for t in s), 4) if s else None,
                    "ctrl": round(st.mean(t["ctrl"] for t in s), 4) if s else None}
    by_y = collections.defaultdict(list)
    for t in T: by_y[t["ts"] // 1000 // 86400 // 365]
    yrs = collections.defaultdict(list)
    for t in T: yrs[dt.datetime.utcfromtimestamp(t["ts"] / 1000).year].append(t["A"])
    out["po_godam"] = {y: {"n": len(v), "R": round(st.mean(v), 4)} for y, v in sorted(yrs.items())}
    span_y = (T[-1]["ts"] - min(t["ts"] for t in T)) / 1000 / 86400 / 365.25
    out["sdelok_v_god"] = round(len(T) / span_y, 1)
    out["proc_v_god_pri_0_5"] = round(out["A"]["R"] * out["sdelok_v_god"] * 0.5, 2)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    json.dump({"svodka": out, "sdelki": trades}, open(sys.argv[2], "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
