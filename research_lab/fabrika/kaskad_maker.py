#!/usr/bin/env python3
"""КАСКАД ЛИКВИДАЦИЙ × MAKER-ВХОД — единственный причинный вариант (PREREG_KASKAD_MAKER_2026_10_12.md).
Baseline (29.07, research_lab/liquidation_cascade.py): эффект +7.9 bps, t 3.54 над контролем, но под издержками тейкера → закрыт.
Причина смерти — издержки, а не отсутствие эффекта. Вариант атакует именно её: вход лимитом (maker) на открытии бара после
каскада. Определение события — дословно июльское (20× медианы, ≥ $50k, доминирование стороны 2×). Окно 2026-07-29 19:00 …
2026-09-13 19:00 UTC (доходности не смотрел никто). Один прогон; повтор блокирует ITOG.json."""
import datetime as dt, gzip, hashlib, json, math, random, statistics, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; LAB = ROOT / "research_lab"
LIQ = ROOT / "runtime/liquidations/bybit_liquidations.jsonl"
M5 = LAB / "data/breakout_m5_v2"; OUT = LAB / "data/kaskad_maker"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "SUIUSDT", "AVAXUSDT", "BNBUSDT"]
ms = lambda *a: int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp() * 1000)
T0, T1, SER = ms(2026, 7, 29, 19), ms(2026, 9, 13, 19), ms(2026, 8, 21, 19)
BAR = 300_000; MULT, FLOOR = 20.0, 50_000.0          # июльское определение, не трогать
LIM_BARS = 2; EXIT_BAR = 6                            # лимит живёт бары i+1..i+2; выход закрытием бара i+6 (как июль: 30 мин)
MAKER, TAKER, SLIP = 2.0, 5.5, 1.0                    # bps: вход maker, выход taker + проскальзывание
COST = MAKER + TAKER + SLIP


def bars(sym):
    rows = {}
    for f in sorted((M5 / sym).glob(f"{sym}_2026-0[6789].jsonl.gz")):
        for line in gzip.open(f, "rt"):
            if line.strip():
                r = json.loads(line); rows[int(r[0])] = tuple(float(x) for x in r[1:5])
    ts = sorted(rows); return ts, [rows[t] for t in ts]


def events():
    bk = {}
    for line in open(LIQ):
        try:
            d = json.loads(line); s = d["symbol"]; b = int(d["ts_ms"]) // BAR * BAR; u = float(d.get("usd") or 0.0)
        except Exception:
            continue
        r = bk.setdefault((s, b), [0.0, 0.0]); r[0 if d.get("side") == "long" else 1] += u
    per = defaultdict(list)
    for (s, b), (lo, sh) in bk.items(): per[s].append((b, lo, sh))
    ev = []
    for s, rows in per.items():
        if s not in SYMS: continue
        base = statistics.median([lo + sh for _, lo, sh in rows if lo + sh > 0]) or 1.0
        th = max(FLOOR, base * MULT)
        for b, lo, sh in rows:
            if not (T0 <= b < T1): continue
            if lo >= th and lo > sh * 2: ev.append((s, b, +1))      # ликвидировали лонги → покупаем
            elif sh >= th and sh > lo * 2: ev.append((s, b, -1))    # ликвидировали шорты → продаём
    return sorted(ev, key=lambda e: (e[1], e[0]))


def trade(ts, px, i, sgn):
    """i — индекс бара каскада. None = нет данных; 'nofill' = лимит не исполнен; иначе net bps."""
    if i + EXIT_BAR >= len(ts) or ts[i + EXIT_BAR] - ts[i] != EXIT_BAR * BAR: return None
    lim = px[i + 1][0]                                               # открытие бара i+1
    fill = any((px[k][2] < lim) if sgn > 0 else (px[k][1] > lim) for k in range(i + 1, i + 1 + LIM_BARS))  # строго сквозь
    if not fill: return "nofill"
    ex = px[i + EXIT_BAR][3]
    return sgn * (ex / lim - 1.0) * 1e4 - COST


def tstat(a):
    if len(a) < 3: return 0.0
    sd = statistics.pstdev(a); return statistics.fmean(a) / (sd / math.sqrt(len(a))) if sd > 0 else 0.0


def main():
    if (OUT / "ITOG.json").exists(): print("уже выполнен — повтор запрещён"); return 1
    OUT.mkdir(parents=True, exist_ok=True)
    ev = events(); B = {s: bars(s) for s in SYMS}; idx = {s: {t: k for k, t in enumerate(B[s][0])} for s in SYMS}
    rnd = random.Random(20261012); sch = defaultdict(int); rows = []
    for s, b, sgn in ev:
        ts, px = B[s]; i = idx[s].get(b)
        if i is None: sch["net_bara"] += 1; continue
        r = trade(ts, px, i, sgn)
        if r is None: sch["net_dannyh"] += 1; continue
        if r == "nofill": sch["nofill"] += 1; continue
        hour = (b // 3_600_000) % 24; c = None                       # контроль: случайный бар того же символа и часа в окне
        for _ in range(200):
            k = rnd.randrange(0, len(ts) - EXIT_BAR - 1)
            if T0 <= ts[k] < T1 and (ts[k] // 3_600_000) % 24 == hour:
                c = trade(ts, px, k, sgn)
                if isinstance(c, float): break                       # контроль тоже должен исполниться
        if not isinstance(c, float): c = None
        rows.append(dict(s=s, b=b, sgn=sgn, net=r, ctrl=c))
    net = [r["net"] for r in rows]; izb = [r["net"] - r["ctrl"] for r in rows if r["ctrl"] is not None]
    h1 = [r["net"] for r in rows if r["b"] < SER]; h2 = [r["net"] for r in rows if r["b"] >= SER]
    n = len(net); m = statistics.fmean(net) if net else 0.0
    gp = sum(x for x in net if x > 0); gl = -sum(x for x in net if x < 0); pf = gp / gl if gl > 0 else float("inf")
    pas = n >= 200 and m > 0 and tstat(izb) >= 2.0 and h1 and h2 and statistics.fmean(h1) > 0 and statistics.fmean(h2) > 0
    rez = dict(prereg="PREREG_KASKAD_MAKER_2026_10_12.md", verdikt="PASS_KANDIDAT" if pas else "FAIL_TERMINAL_KILL",
               sobytiy=len(ev), schetchiki=dict(sch), n=n, dolya_fill=round(n / max(1, n + sch["nofill"]), 3),
               sred_net_bps=round(m, 2), pf=round(pf, 3), t_net=round(tstat(net), 2),
               izbytok=dict(n=len(izb), sred=round(statistics.fmean(izb), 2) if izb else None, t=round(tstat(izb), 2)),
               long=dict(n=sum(r["sgn"] > 0 for r in rows), sred=round(statistics.fmean([r["net"] for r in rows if r["sgn"] > 0] or [0]), 2)),
               short=dict(n=sum(r["sgn"] < 0 for r in rows), sred=round(statistics.fmean([r["net"] for r in rows if r["sgn"] < 0] or [0]), 2)),
               polovina_1=dict(n=len(h1), sred=round(statistics.fmean(h1), 2) if h1 else None),
               polovina_2=dict(n=len(h2), sred=round(statistics.fmean(h2), 2) if h2 else None),
               izderzhki_bps=COST, liq_sha256=hashlib.sha256(LIQ.read_bytes()).hexdigest())
    (OUT / "sdelki.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (OUT / "ITOG.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
