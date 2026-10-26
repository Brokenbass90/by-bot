#!/usr/bin/env python3
"""Тень вперёд POLY_MAKER_NO (prereg PREREG_POLY_MAKER_NO_2026_10_26, дополнение 1). Только чтение снимков и 5m.
Хук ocenshchiki_ezhednevno: извлекает страйки из data/poly/snimki с t ≥ GRAN, считает тем же poly_maker_no.main и добавляет разрез по
направлению BTC за 24 ч до расчёта. → data/poly_maker_no_vpered/itog.json"""
import bisect, collections, json, math, sys, tempfile
from pathlib import Path
LAB = Path(__file__).resolve().parent; sys.path.insert(0, str(LAB / "polymarket"))
import poly_px1_zapazdyvanie as X, poly_maker_no as M
GRAN = 1793059200000                       # 2026-10-27 00:00 UTC
OUT = LAB / "data" / "poly_maker_no_vpered"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp()); vse = tmp / "vse.jsonl"; X.izvlech(str(LAB / "data/poly/snimki"), str(vse))
    vp = tmp / "vpered.jsonl"
    with open(vp, "w") as fo:
        for l in open(vse):
            if json.loads(l)[0] >= GRAN: fo.write(l)
    if vp.stat().st_size == 0:
        (OUT / "itog.json").write_text(json.dumps({"status": "NET_DANNYH_VPERED"})); print("нет данных вперёд"); return
    M.main(str(vp), str(LAB / "data/breakout_ten/m5"), str(OUT / "itog.json"))
    razrez(OUT / "itog.json"); hedzh(vp, OUT / "itog.json")


def hedzh(fin, f, m5=None):
    """MAKER_HEDGE (дополнение 2): та же мейкер-рука + статический хедж дельты на Bybit до расчёта, 12 bps круг. Описательно."""
    m5 = Path(m5 or LAB / "data/breakout_ten/m5"); px = {}
    for a in ("BTCUSDT", "ETHUSDT"):
        rows = sorted(json.loads(l) for l in open(m5 / f"{a}.jsonl")); px[a] = ([r[0] + 300000 for r in rows], [r[4] for r in rows])
    def cena(a, t):
        e, c = px[a]; i = bisect.bisect_right(e, t) - 1
        return (c[i], i) if i >= 0 and t - e[i] < 600000 else (None, None)
    def sig(a, i):
        c = px[a][1]
        if i < 289: return None
        r = [math.log(c[j] / c[j - 1]) for j in range(i - 287, i + 1)]; m = sum(r) / len(r)
        return math.sqrt(sum((x - m) ** 2 for x in r) / len(r)) * math.sqrt(288 * 365)
    po = collections.defaultdict(list)
    for l in open(fin):
        x = json.loads(l); po[x[1]].append(x)
    d = collections.defaultdict(float); n = 0
    for cid, xs in po.items():
        xs.sort(); akt, K, rasch = xs[0][2], xs[0][3], xs[0][4]; e, c = px[akt]; k = bisect.bisect_left(e, rasch)
        if k >= len(e) or e[k] != rasch or abs(c[k] / K - 1) < 0.001: continue
        ST = c[k]; y = 1.0 if ST > K else 0.0; i = 0
        while i < len(xs):
            t, _, _, _, _, bid, bsz, ask, asz = xs[i]; mid = (bid + ask) / 2
            if not (0.1 <= mid <= 0.9) or rasch - t < 2 * 3600000: i += 1; continue
            S, ii = cena(akt, t); s = sig(akt, ii) if S else None; tau = (rasch - t) / 1000 / 86400 / 365
            if not S or not s or tau <= 0: i += 1; continue
            d2 = (math.log(S / K) - 0.5 * s * s * tau) / (s * math.sqrt(tau)); fv = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            if ask < fv + 0.02: i += 1; continue
            j = i + 1; isp = None
            while j < len(xs) and xs[j][0] <= t + 3600000:
                if xs[j][5] >= ask: isp = j; break
                j += 1
            if isp is None: i = j; continue
            Sf, _ = cena(akt, xs[isp][0]); sh = 10 / (1 - ask)
            dl = math.exp(-d2 * d2 / 2) / math.sqrt(2 * math.pi) / (S * s * math.sqrt(tau))
            d[(rasch, akt)] += sh * (ask - y) + dl * sh * (ST - Sf) - dl * sh * Sf * 12 / 1e4; n += 1; i = isp + 1
    o = json.loads(Path(f).read_text()); v = list(d.values())
    if len(v) > 2:
        m = sum(v) / len(v); sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
        o["MAKER_HEDGE"] = dict(ispolneno=n, sred_usd_na_10=round(sum(v) / n, 3), t_po_datam=round(m / (sd / math.sqrt(len(v))), 2) if sd else None)
    Path(f).write_text(json.dumps(o, ensure_ascii=False, indent=1))


def razrez(f, m5=None):
    """Разрез по направлению BTC за 24 ч до расчёта (дополнение 1)."""
    o = json.loads(Path(f).read_text()); rows = sorted(json.loads(l) for l in open(Path(m5 or LAB / "data/breakout_ten/m5") / "BTCUSDT.jsonl"))
    e = [r[0] + 300000 for r in rows]; c = [r[4] for r in rows]
    def px(t):
        i = bisect.bisect_right(e, t) - 1; return c[i] if i >= 0 else None
    pd = o.get("MAKER", {}).get("po_datam", {}); rost, pad = [], []
    for r, v in pd.items():
        a, b = px(int(float(r)) - 86400000), px(int(float(r)))
        if a and b: (rost if b > a else pad).append(v)
    o["razrez_btc_24ch"] = {"rost": dict(dat=len(rost), itogo_usd=round(sum(rost), 2)), "padenie": dict(dat=len(pad), itogo_usd=round(sum(pad), 2))}
    m = o.get("MAKER", {})
    if o.get("verdikt") == "PASS" and not (sum(rost) > 0 and sum(pad) > 0): o["verdikt"] = "INCONCLUSIVE_NAPRAVLENIE"
    if len(rost) >= 6 and sum(rost) < 0: o["verdikt"] = "FAIL"
    Path(f).write_text(json.dumps(o, ensure_ascii=False, indent=1)); print("разрез:", o["razrez_btc_24ch"], o.get("verdikt"))


if __name__ == "__main__":
    main()
