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

def prohod():
    mt = metki_btc(); rez = lambda t: mt.get(int(t) // H * H - H, "NET_DANNYH")
    zap = []
    f = sorted(glob.glob(str(LAB / "results" / "pump4_polnyy_povtor_*.json")))
    p4 = json.load(open(f[-1]))["sdelki"] if f else []
    tp = sorted(x["ts"] for x in p4); shir = lambda t: bisect.bisect_left(tp, t) - bisect.bisect_left(tp, t - 24 * H)
    for x in p4:
        zap.append(dict(noga="PUMP4", sym=x["sym"], t_signala=x["ts"], storona=x["side"], rezhim_btc=rez(x["ts"] + H), shirina_24ch=shir(x["ts"]),
                        status=x["status"], ishod=x.get("R"), edinica="R", tip_ishoda="model", kontrol=x.get("ctrl"), istochnik=Path(f[-1]).name))
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
                        posle_zamorozki=t >= FH.ZAMOROZKA_MS, istochnik="runtime/funding_positioning_*_ledger.jsonl"))
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
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), zapisey=len(zap), nogi=sv,
               primechanie="все исходы — model (повтор/тень); real появятся с первыми реальными сделками")
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return dict(zapisey=len(zap), nogi={k: v["vse"] for k, v in sv.items()})

if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False, indent=1)); print(SV.read_text())
