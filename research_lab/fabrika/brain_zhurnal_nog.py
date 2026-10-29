#!/usr/bin/env python3
"""brain_zhurnal_nog.py — обратная связь для Brain (27.10.2026, Claude): ОДИН журнал «сигнал → условия рынка → исход» по ногам, идущим к деньгам.
Только чтение источников; выход перезаписывается (производный): data/brain_shadow_v1/zhurnal_nog.jsonl + svodka_nog.json. Хук сторожа.
Прав на торговлю нет. Исходы помечены: model (повтор/тень) или real (когда появятся реальные сделки).
Условия рынка — только известные к моменту сигнала: REZHIM_V1 (BTC 4h, последний закрытый), ширина волны пампов (сигналы PUMP4 за 24 ч).
Источники: PUMP4 — последний непрерывный повтор (results/pump4_polnyy_povtor_*.json); SHORT_HVOST — исходы двух теней фандинга (runtime/...);
ETS2S2 — исправленная тень (data/ten_ETS2S2.jsonl); KITY — недели тени (data/kity_bybit_ten/*/vyhod.json)."""
import bisect, collections, glob, json, sys, time
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent; D = LAB / "data"; H = 3600000
OUT = D / "brain_shadow_v1" / "zhurnal_nog.jsonl"; SV = D / "brain_shadow_v1" / "svodka_nog.json"
sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB / "os2"))

def metki_btc():
    import rezhim_v1 as RZ
    b = sorted(json.load(open(D / "oos_bybit_h1_20261020" / "BTCUSDT.json")))
    m5 = collections.defaultdict(list)
    p = D / "breakout_ten" / "m5" / "BTCUSDT.jsonl"
    if p.exists():
        for l in open(p):
            r = json.loads(l); m5[int(r[0]) // H * H].append([float(v) for v in r[:6]])
    t = b[-1][0] + H
    while t in m5 and len(m5[t]) == 12:
        g = sorted(m5[t]); b.append([t, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)]); t += H
    ts = np.array([x[0] for x in b], dtype=np.int64); o = np.array([x[1:] for x in b], dtype=float)
    return {int(a): (m or "UNKNOWN") for a, m in zip(ts, RZ.metki(ts, o))}

# ---- Brain V4 (задание PM 27.10): правила с неопределённостью, контрфакт по каждой записи, карта общего риска. Только чтение. ----
PRAVILA = {  # правило → (нога, условие пропуска). Ни одно не применяется к ордерам: Brain read-only.
    "P1_PUMP4_volna3_BULL": ("PUMP4", lambda z, ctx: z["rezhim_btc"] == "BULL_TREND" and z["shirina_24ch"] >= 3),
    "P2_PUMP4_BULL": ("PUMP4", lambda z, ctx: z["rezhim_btc"] == "BULL_TREND"),
    "P4_PUMP4_V1_2_5_za_sutki": ("PUMP4", lambda z, ctx: z["shirina_24ch"] >= 5),   # V1.2 (prereg 29.10): ≥ 5 сигналов за 24 ч до этого
    "P3_zapret_dvoynoy_SHORT_HVOST": ("SHORT_HVOST", lambda z, ctx: z["sym"] in ctx["otkryty_pump4"]),
}
MIN_DNEY = 15

def _ci90_po_dnyam(vals_dni, rng=None):
    rng = rng or np.random.default_rng(7)
    dni = collections.defaultdict(list)
    for d, v in vals_dni: dni[d].append(v)
    g = list(dni.values())
    if len(g) < 2: return None, None
    bs = []
    for _ in range(2000):
        idx = rng.integers(0, len(g), len(g)); x = [v for i in idx for v in g[i]]; bs.append(float(np.mean(x)))
    return round(float(np.percentile(bs, 5)), 4), round(float(np.percentile(bs, 95)), 4)

def kontrfakt(zap):
    otkr = [(z["t_signala"], z["t_konca"], z["sym"]) for z in zap if z["noga"] == "PUMP4" and z.get("t_konca")]
    res = {}
    for z in zap:
        ctx = dict(otkryty_pump4={s for a, b, s in otkr if a <= z["t_signala"] < b})
        z["pravila_sovpali"] = [k for k, (n, f) in PRAVILA.items() if z["noga"] == n and f(z, ctx)]
        z["brain_primenil"] = False                     # read-only: фактический эффект Brain = 0
        z["effekt_esli_primenit"] = (None if z["ishod"] is None else -z["ishod"]) if z["pravila_sovpali"] else 0.0
    for k, (n, f) in PRAVILA.items():
        h = [z for z in zap if k in z["pravila_sovpali"] and z["ishod"] is not None]
        ed = h[0]["edinica"] if h else None
        vd = [(time.strftime("%Y-%m-%d", time.gmtime(z["t_signala"] / 1000)), -z["ishod"]) for z in h]
        nd = len({d for d, _ in vd}); lo, hi = _ci90_po_dnyam(vd)
        if nd < MIN_DNEY or lo is None: st_ = "INCONCLUSIVE"
        elif lo > 0: st_ = "ULUCHSHAET"
        elif hi < 0: st_ = "UHUDSHAET"
        else: st_ = "INCONCLUSIVE"
        res[k] = dict(noga=n, propuskov=len(h), nezavisimyh_dney=nd, edinica=ed, effekt_na_propusk=round(float(np.mean([v for _, v in vd])), 4) if vd else None,
                      ci90=[lo, hi], effekt_summa=round(float(sum(v for _, v in vd)), 2), status=st_,
                      pravilo_statusa=f"INCONCLUSIVE если дней < {MIN_DNEY} или 90 % интервал (бутстрап по дням) накрывает 0")
    # карта общего риска: интервалы позиций с известным временем выхода (PUMP4, SHORT_HVOST); ETS2S2 без времени выхода, KITY — нейтральная корзина
    pos = [(z["t_signala"], z["t_konca"], z["sym"], z["noga"], z["storona"]) for z in zap if z.get("t_konca")]
    sob = sorted([(a, 1, i) for i, (a, b, *_ ) in enumerate(pos)] + [(b, -1, i) for i, (a, b, *_ ) in enumerate(pos)], key=lambda e: (e[0], e[1]))
    otk, pik, pik_t, dvoynye = set(), 0, None, collections.Counter()
    for t, d, i in sob:
        if d < 0: otk.discard(i); continue
        _, _, s, n, _ = pos[i]
        if any(pos[j][2] == s and pos[j][3] != n for j in otk): dvoynye[s] += 1
        otk.add(i); sh = sum(1 for j in otk if pos[j][4] == "short")
        if sh > pik: pik, pik_t = sh, t
    return res, dict(pozicyy_s_vremenem=len(pos), pik_odnovremennyh_shortov=pik,
                     pik_kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(pik_t / 1000)) if pik_t else None,
                     dvoynye_po_monete=sum(dvoynye.values()), monety_dvoynyh=sorted(dvoynye),
                     nominal_v_pike_pri_50usd=pik * 50,
                     primechanie="ETS2S2 без времени выхода и KITY (нейтральная корзина) в пике шортов не учитываются")

def prohod():
    mt = metki_btc(); rez = lambda t: mt.get(int(t) // H * H - H, "NET_DANNYH")
    zap = []
    f = sorted(glob.glob(str(LAB / "results" / "pump4_polnyy_povtor_*.json")))
    p4 = json.load(open(f[-1]))["sdelki"] if f else []
    tp = sorted(x["ts"] for x in p4); shir = lambda t: bisect.bisect_left(tp, t) - bisect.bisect_left(tp, t - 24 * H)
    for x in p4:
        zap.append(dict(noga="PUMP4", sym=x["sym"], t_signala=x["ts"], storona=x["side"], rezhim_btc=rez(x["ts"] + H), shirina_24ch=shir(x["ts"]),
                        status=x["status"], ishod=x.get("R"), edinica="R", tip_ishoda="model", kontrol=x.get("ctrl"), istochnik=Path(f[-1]).name,
                        t_konca=x["ts"] + (x.get("barov", 0) + 2) * H))
    sys.path.insert(0, str(LAB)); import fanding_hvost as FH
    u = {}
    for fn in FH.LEDGERY:
        pth = ROOT / fn
        if not pth.exists(): continue
        for l in open(pth):
            r = json.loads(l)
            if r.get("record_type") == "outcome" and r.get("status") == "closed" and r.get("side") == -1 and r.get("symbol") not in FH.NE_HVOST:
                u[(r["symbol"], r["event_ts"])] = r
    for (s, t), r in sorted(u.items(), key=lambda kv: kv[0][1]):
        v = r.get("net_btc_hedged_bps", r.get("net_raw_bps"))
        zap.append(dict(noga="SHORT_HVOST", sym=s, t_signala=t, storona="short", rezhim_btc=rez(t), shirina_24ch=shir(t),
                        status="ZAKRYTA", ishod=None if v is None else round(v - FH.SHTRAF_BPS, 1), edinica="bps", tip_ishoda="model",
                        posle_zamorozki=t >= FH.ZAMOROZKA_MS, istochnik="runtime/funding_positioning_*_ledger.jsonl", t_konca=t + 16 * H))
    e2 = D / "ten_ETS2S2.jsonl"
    if e2.exists():
        for l in open(e2):
            r = json.loads(l)
            if "R" not in r: continue
            zap.append(dict(noga="ETS2S2", sym=r["sym"], t_signala=r["ts"], storona=r.get("side"), rezhim_btc=rez(r["ts"] + H), shirina_24ch=shir(r["ts"]),
                            status="ZAKRYTA", ishod=r["R"], edinica="R", tip_ishoda="model", istochnik="data/ten_ETS2S2.jsonl"))
    for p in sorted(glob.glob(str(D / "kity_bybit_ten" / "20*" / "vyhod.json"))):
        v = json.load(open(p)); d = v.get("d")
        t = int(time.mktime(time.strptime(d, "%Y-%m-%d")) * 1000) if d else 0
        zap.append(dict(noga="KITY", sym="KORZINA_5L5S", t_signala=t, storona="neytral", rezhim_btc=rez(t), shirina_24ch=shir(t), status="ZAKRYTA",
                        ishod=v.get("nedelya_bps"), edinica="bps/нед", tip_ishoda="model", istochnik=p.split("research_lab/")[-1]))
    zap.sort(key=lambda z: z["t_signala"])
    pravila, karta = kontrfakt(zap)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zap))
    sv = {}
    for n in sorted({z["noga"] for z in zap}):
        g = [z for z in zap if z["noga"] == n and z["ishod"] is not None]
        def m(h): return dict(n=len(h), sred=round(float(np.mean([z["ishod"] for z in h])), 4) if h else None)
        sv[n] = dict(vse=m(g), edinica=g[0]["edinica"] if g else None,
                     po_rezhimu={r: m([z for z in g if z["rezhim_btc"] == r]) for r in sorted({z["rezhim_btc"] for z in g})},
                     volna_ge3_v_bull=m([z for z in g if z["rezhim_btc"] == "BULL_TREND" and z["shirina_24ch"] >= 3]),
                     ostalnoe=m([z for z in g if not (z["rezhim_btc"] == "BULL_TREND" and z["shirina_24ch"] >= 3)]))
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), zapisey=len(zap), nogi=sv, pravila_brain=pravila, karta_riska=karta,
               primechanie="все исходы — model (повтор/тень); real появятся с первыми реальными сделками")
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return dict(zapisey=len(zap), nogi={k: v["vse"] for k, v in sv.items()})

if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False, indent=1)); print(SV.read_text())
