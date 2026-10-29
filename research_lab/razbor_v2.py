#!/usr/bin/env python3
"""razbor_v2.py — Brain-аналитик сделок на ПОЛНОЙ выборке (28.10.2026, Claude; задание PM). Read-only, после razbor_sbor.py.
1. Признаки, известные ДО входа (час входа не используется): rost24, rost72 (%), oi_izm24 (% изменения OI за 24 ч), oi_minus_cena (oi_izm24 − rost24),
   fanding_pered (последняя ставка до входа, bps), spot_dolya (доля спота в обороте 24 ч), bazis (перп/спот − 1, bps), obem3 (объём 3 ч / средний 24 ч),
   btc24 (рост BTC за 24 ч). Нет данных — None, не подменяется.
2. Тип каждой убыточной сделки по конкурирующим причинам (закрытый список, первая подходящая): NE_PAMP (PUMP4: рост 24 ч < 6 %);
   USTOYCHIVYY_SPROS (OI рос ≥ 10 % и цена после входа ушла против нас ≥ 1 ед. риска без отката ≥ 0.5); OSHIBKA_VYHODA (был плюс ≥ 1 ед., закрыли хуже);
   OSHIBKA_VHODA (против нас ≥ 1 ед. в первые 6 ч); MALO_LIKVIDNOSTI (оборот перпа 24 ч < $2 млн); PROCHEE.
3. Контроль той же монеты и периода: те же признаки в 10 случайных часах окна (дальше 12 ч от входа) — чем вход отличался от обычного часа.
4. Терти каждого признака: средний исход в нижней/верхней трети (отдельно PUMP4 и SHORT_HVOST; SHORT_HVOST — до и после заморозки 30.09).
5. Графики: все убыточные сделки (свечи + OI), помесячно: net по ногам до/после заморозки, кривая и просадка, вклад монет.
Выход: razbor/v2/*.png, razbor/RAZBOR_V2.md, results/razbor_v2_*.json.   python3 research_lab/razbor_v2.py"""
import collections, glob, json, random, statistics as st, sys, time
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = Path(__file__).resolve().parent; H = 3600000; DD = HERE / "data" / "razbor_dannye"; OUT = HERE / "razbor" / "v2"; OUT.mkdir(parents=True, exist_ok=True)
ZAMOROZKA = 1790769600000; PR = ["rost24", "rost72", "oi_izm24", "oi_minus_cena", "fanding_pered", "spot_dolya", "bazis", "obem3", "btc24"]

def ishody():
    m = {}
    for x in json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]))["sdelki"]:
        if x.get("R") is not None: m[("PUMP4", x["sym"], x["ts"] + H)] = dict(rez=x["R"], ed_pct=x["risk_pct"], ctrl=x.get("ctrl"))
    for x in json.load(open(sorted(glob.glob(str(HERE / "results" / "short_hvost_uderzhanie_*.json")))[-1]))["sdelki"]:
        m[("SHORT_HVOST", x["sym"], x["ts"])] = dict(rez=x["16"]["net_hedzh"] / 100, ed_pct=10.0, ctrl=None)       # SH: % ; ед. риска 10 %
    return m

def priznaki(z, t):
    P = {r[0]: r for r in z["perp"]}; S = {r[0]: r for r in z["spot"]}; B = {r[0]: r for r in z["btc"]}; O = {r[0]: r[1] for r in z["oi"]}
    c = lambda d, k: d[k][4] if k in d else None
    def izm(d, a, b): return (c(d, a) / c(d, b) - 1) * 100 if c(d, a) and c(d, b) else None
    t_ = t - H                                                    # последний закрытый час до входа
    v = dict(rost24=izm(P, t_, t_ - 24 * H), rost72=izm(P, t_, t_ - 71 * H), btc24=izm(B, t_, t_ - 24 * H))
    o1, o0 = O.get(t_), O.get(t_ - 24 * H)
    v["oi_izm24"] = (o1 / o0 - 1) * 100 if o1 and o0 else None
    v["oi_minus_cena"] = v["oi_izm24"] - v["rost24"] if v["oi_izm24"] is not None and v["rost24"] is not None else None
    fr = [f for ts, f in z["fanding"] if ts <= t_]; v["fanding_pered"] = max(fr, key=lambda _: 0) * 1e4 if False else (sorted([(ts, f) for ts, f in z["fanding"] if ts <= t_])[-1][1] * 1e4 if fr else None)
    pv = sum(P[k][5] * P[k][4] for k in range(t_ - 23 * H, t_ + H, H) if k in P); sv = sum(S[k][5] * S[k][4] for k in range(t_ - 23 * H, t_ + H, H) if k in S)
    v["spot_dolya"] = sv / (sv + pv) if S and (sv + pv) > 0 else None
    v["bazis"] = (c(P, t_) / c(S, t_) - 1) * 1e4 if c(P, t_) and c(S, t_) else None
    v3 = [P[k][5] for k in range(t_ - 2 * H, t_ + H, H) if k in P]; v24 = [P[k][5] for k in range(t_ - 23 * H, t_ + H, H) if k in P]
    v["obem3"] = (st.mean(v3) / st.mean(v24)) if v3 and v24 and st.mean(v24) > 0 else None
    v["oborot24_usd"] = pv
    return v

def main():
    I = ishody(); rows = []; kontrol = collections.defaultdict(list); rng = random.Random(20261028)
    for f in sorted(DD.glob("*.json")):
        z = json.loads(f.read_text()); k = (z["noga"], z["sym"], z["t0"])
        if k not in I or not z["perp"]: continue
        x = dict(noga=z["noga"], sym=z["sym"], t0=z["t0"], **I[k], **priznaki(z, z["t0"]))
        P = {r[0]: r for r in z["perp"]}; e = P.get(z["t0"], [0, None])[1]
        if e:
            ed = e * x["ed_pct"] / 100; put = [P[t] for t in range(z["t0"], z["t1"], H) if t in P]; rano = [P[t] for t in range(z["t0"], z["t0"] + 6 * H, H) if t in P]
            x["mae"] = (max(r[2] for r in put) - e) / ed if put else None; x["mfe"] = (e - min(r[3] for r in put)) / ed if put else None
            x["mae6"] = (max(r[2] for r in rano) - e) / ed if rano else None
            if x["rez"] <= 0:
                if x["noga"] == "PUMP4" and (x["rost24"] or 0) < 6: tip = "NE_PAMP"
                elif (x["oi_izm24"] or 0) >= 10 and (x["mae"] or 0) >= 1 and (x["mfe"] or 0) < 0.5: tip = "USTOYCHIVYY_SPROS"
                elif (x["mfe"] or 0) >= 1: tip = "OSHIBKA_VYHODA"
                elif (x["mae6"] or 0) >= 1: tip = "OSHIBKA_VHODA"
                elif x["oborot24_usd"] < 2e6: tip = "MALO_LIKVIDNOSTI"
                else: tip = "PROCHEE"
            else: tip = "PLUS"
            x["tip"] = tip
        ts = [t for t in P if abs(t - z["t0"]) > 12 * H and t - 72 * H in P]
        for t in rng.sample(ts, min(10, len(ts))): kontrol[z["noga"]].append(priznaki(z, t))
        x["perp"], x["oi"] = z["perp"], z["oi"]; rows.append(x)
    def m(a): a = [v for v in a if v is not None]; return dict(n=len(a), sred=round(st.mean(a), 3)) if a else dict(n=0)
    rez = dict(sdelok={n: sum(r["noga"] == n for r in rows) for n in ("PUMP4", "SHORT_HVOST")},
               tipy_ubytkov={n: dict(collections.Counter(r.get("tip") for r in rows if r["noga"] == n)) for n in ("PUMP4", "SHORT_HVOST")},
               vhod_protiv_obychnogo_chasa={}, treti={})
    for n in ("PUMP4", "SHORT_HVOST"):
        g = [r for r in rows if r["noga"] == n]
        rez["vhod_protiv_obychnogo_chasa"][n] = {p: dict(plus=m([r.get(p) for r in g if r["rez"] > 0]), minus=m([r.get(p) for r in g if r["rez"] <= 0]),
                                                         obychnyy_chas=m([c.get(p) for c in kontrol[n]])) for p in PR}
        for chast, gg in ((("vse", g),) if n == "PUMP4" else (("do_zamorozki", [r for r in g if r["t0"] < ZAMOROZKA]), ("posle_zamorozki", [r for r in g if r["t0"] >= ZAMOROZKA]))):
            for p in PR:
                h = sorted([r for r in gg if r.get(p) is not None], key=lambda r: r[p]); k = len(h) // 3
                if k < 5: continue
                rez["treti"][f"{n}|{chast}|{p}"] = dict(granicy=[round(h[k - 1][p], 3), round(h[-k][p], 3)], niz=m([r["rez"] for r in h[:k]]),
                                                         verh=m([r["rez"] for r in h[-k:]]))
    for r in [r for r in rows if r["rez"] <= 0]:
        P = sorted(r["perp"]); O = dict(map(tuple, r["oi"]))
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
        for i, b in enumerate(P):
            col = "#2a9d8f" if b[4] >= b[1] else "#e76f51"; a1.vlines(i, b[3], b[2], color=col, lw=1); a1.vlines(i, min(b[1], b[4]), max(b[1], b[4]), color=col, lw=4)
        iv = next((i for i, b in enumerate(P) if b[0] == r["t0"]), 0); a1.axvline(iv, color="k", ls="--", lw=1)
        a2.plot([i for i, b in enumerate(P) if b[0] in O], [O[b[0]] for b in P if b[0] in O], color="#264653"); a2.set_ylabel("OI")
        a1.set_title(f'{r["noga"]} {r["sym"]} {time.strftime("%Y-%m-%d", time.gmtime(r["t0"] / 1000))} | {r["rez"]:+.2f} | {r.get("tip")} | рост24 {r["rost24"] and round(r["rost24"], 1)}% | OI24 {r["oi_izm24"] and round(r["oi_izm24"], 1)}%', fontsize=9)
        fig.tight_layout(); fig.savefig(OUT / f'{r["noga"]}_{r["sym"]}_{r["t0"]}.png', dpi=70); plt.close(fig)
    reg = json.loads((HERE / "data" / "brain_shadow_v1" / "regulyarnost.json").read_text())
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    for i, n in enumerate(("PUMP4", "SHORT_HVOST")):
        ms = reg[n]["mesyacy"]; ax[i].bar(list(ms), list(ms.values()), color=["#2a9d8f" if v > 0 else "#e76f51" for v in ms.values()])
        ax[i].set_title(f"{n}: net $ по месяцам (PUMP4 риск $10, SH $100)" + (" — до 30.09 поиск, после — вперёд" if n == "SHORT_HVOST" else ""), fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / "mesyacy.png", dpi=80); plt.close(fig)
    for r in rows: r.pop("perp", None); r.pop("oi", None)
    f = HERE / "results" / time.strftime("razbor_v2_%Y%m%dT%H%MZ.json", time.gmtime()); f.write_text(json.dumps(dict(rez, sdelki=rows), ensure_ascii=False))
    print(json.dumps({k: rez[k] for k in ("sdelok", "tipy_ubytkov")}, ensure_ascii=False))
    for k, v in rez["treti"].items(): print(k, "низ", v["niz"].get("sred"), "верх", v["verh"].get("sred"), v["granicy"])
    for n, d in rez["vhod_protiv_obychnogo_chasa"].items():
        for p, v in d.items(): print(n, p, "плюс", v["plus"].get("sred"), "минус", v["minus"].get("sred"), "обычный час", v["obychnyy_chas"].get("sred"))
    print("файл", f)

if __name__ == "__main__":
    main()
