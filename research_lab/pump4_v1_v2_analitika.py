"""PM 20.10 «PUMP4 V1/V2, BRAIN, INPLAY: уточнение»: расходы V1, диагностика V2 (без подбора цели), портфельный риск.
Данные: решения pump4_pereschet_20261020, свечи кэша OOS. Параметры V1/V2 не меняются."""
import json, os, sys, math, statistics as st, importlib, datetime as dt, collections
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
from research_machine import Store, simulate, pervyy_argument, FEE_BPS_SIDE
o = json.load(open("research_lab/results/pump4_pereschet_20261020.json"))
z = [x for x in o["resheniya"] if x["status"] == "ZAKRYTA"]
syms = sorted({x["sym"] for x in z})
os.environ.update({"PUMP4_SYMBOL_ALLOWLIST": ",".join(syms), "PUMP4_ALLOW_LONGS": "1", "PUMP4_ALLOW_SHORTS": "1"})
K = importlib.import_module("strategies.pump_fade_v4r").PumpFadeV4RStrategy
H = 3600000; S = []
for sym in syms:
    p = f"research_lab/data/oos_bybit_h1_20261020/{sym}.json"
    b = json.load(open(p)) if os.path.exists(p) else []
    need = {x["ts"]: x for x in z if x["sym"] == sym}; got = set()
    s = K(); sto = Store(sym); pv = sym if pervyy_argument(K) == "symbol" else sto
    for i in range(200, len(b) - 1):
        sto.rows = b[:i + 1]; r = b[i]
        try: g = s.maybe_signal(pv, *r)
        except Exception: continue
        if g is None or r[0] not in need or r[0] in got: continue
        got.add(r[0]); S.append(dict(sym=sym, i=i, b=b, g=g, x=need[r[0]]))
    for t in set(need) - got: print("NE_VOSPR", sym, dt.datetime.utcfromtimestamp(t / 1000), "kandles", len(b), "first", dt.datetime.utcfromtimestamp(b[0][0] / 1000) if b else None)

def put(b, i, g, tp2_r=None, be=False, delay=0, extra_bps=0.0):
    """Полный путь: вход open i+1+delay, стоп ×4, tp1 доля 0.55, tp2 — стратегии или tp2_r (в R), БУ после tp1 если be."""
    e_i = i + 1 + delay
    if e_i >= len(b): return None
    en = b[e_i][1]; sh = g.side == "short"; sl = en + (g.sl - b[i + 1][1]) * 4.0 if False else None
    e0 = b[i + 1][1]; risk = abs((e0 + (g.sl - e0) * 4.0) - e0)            # риск V1 (от входа без задержки)
    stop = en + risk if sh else en - risk
    tps = [abs(t - e0) / risk for t in (g.tps or [])]; r1 = tps[0]; r2 = tp2_r if tp2_r else tps[1]
    f1 = (g.tp_fracs or [0.55])[0]; lev = en / risk
    cost = lev * 2 * (FEE_BPS_SIDE + extra_bps) / 1e4
    rem, gross, done1 = 1.0, 0.0, False
    for j in range(e_i, min(e_i + 168, len(b))):
        h, l = b[j][2], b[j][3]
        if (h >= stop) if sh else (l <= stop):
            gross += rem * ((en - stop) if sh else (stop - en)) / risk; return dict(R=gross - cost, lev=lev, vyhod="stop" if not done1 else "BU/stop")
        t1 = en - r1 * risk if sh else en + r1 * risk; t2 = en - r2 * risk if sh else en + r2 * risk
        if not done1 and ((l <= t1) if sh else (h >= t1)):
            gross += f1 * r1; rem -= f1; done1 = True
            if be: stop = en
        if done1 and ((l <= t2) if sh else (h >= t2)):
            gross += rem * r2; return dict(R=gross - cost, lev=lev, vyhod="tp2")
    j = min(e_i + 168, len(b)) - 1
    if e_i + 168 > len(b): return None
    gross += rem * ((en - b[j][4]) if sh else (b[j][4] - en)) / risk; return dict(R=gross - cost, lev=lev, vyhod="vremya")

out = {"vosproizvedeno": len(S)}
v1 = [put(q["b"], q["i"], q["g"]) for q in S]; ok = [k for k, v in enumerate(v1) if v]
R1 = [v1[k]["R"] for k in ok]; lev = [v1[k]["lev"] for k in ok]
out["v1_sverka_s_vedeniem"] = sum(abs(v1[k]["R"] - S[k]["x"]["R"]) < 1e-3 for k in ok)
out["v1_sred_R"] = st.mean(R1); out["v1_lev_med"] = st.median(lev)
out["vklyucheno_v_R"] = f"комиссия+проскальзывание {FEE_BPS_SIDE} bps на сторону (×плечо в R); фандинг НЕ включён; вход без задержки open следующего часа"
out["bezubytok_dop_bps_na_storonu"] = st.mean(R1) * 1e4 / (2 * st.mean(lev))
sc = {}
for nm, kw in (("dop_5bps", dict(extra_bps=5)), ("dop_10bps", dict(extra_bps=10)), ("dop_20bps", dict(extra_bps=20)),
               ("zaderzhka_1ch", dict(delay=1)), ("zaderzhka_2ch", dict(delay=2))):
    rr = [put(q["b"], q["i"], q["g"], **kw) for q in S]; rr = [r["R"] for r in rr if r]
    sc[nm] = dict(n=len(rr), sred_R=round(st.mean(rr), 4))
out["chuvstvitelnost_v1"] = sc
# V2 диагностика
v2 = [put(S[k]["b"], S[k]["i"], S[k]["g"], tp2_r=0.9, be=True) for k in ok]
d = [b_["R"] - a["R"] for a, b_ in zip([v1[k] for k in ok], v2) if b_]
def dost(q, lvl_from, lvl_to):
    b, i, g = q["b"], q["i"], q["g"]; e0 = b[i + 1][1]; risk = abs((e0 + (g.sl - e0) * 4.0) - e0); sh = g.side == "short"
    a1 = None
    for j in range(i + 1, min(i + 169, len(b))):
        mv = ((e0 - b[j][3]) if sh else (b[j][2] - e0)) / risk; adv = ((b[j][2] - e0) if sh else (e0 - b[j][3])) / risk
        if a1 is None and adv >= 1.0: return None if a1 is None else False
        if a1 is None and mv >= lvl_from: a1 = j
        if a1 is not None:
            if j > a1 and (((b[j][2] >= e0) if sh else (b[j][3] <= e0))): return "BU_ranshe"
            if mv >= lvl_to: return True
    return False if a1 is not None else None
for lv in (0.7, 0.9):
    r = [dost(q, 0.45, lv) for q in S]; base = [x for x in r if x is not None]
    out[f"P_{lv}R_pri_0.45R"] = dict(dostigli=sum(x is True for x in base), BU_ranshe=sum(x == "BU_ranshe" for x in base), ne_doshli=sum(x is False for x in base), iz=len(base))
out["v2_vs_v1_put"] = dict(n=len(d), sred_raznica_R=st.mean(d), sd=st.stdev(d), t=st.mean(d) / (st.stdev(d) / math.sqrt(len(d))),
                           n_dlya_t2=math.ceil((2 * st.stdev(d) / st.mean(d)) ** 2) if st.mean(d) > 0 else None,
                           v1_sred=st.mean(R1), v2_sred=st.mean([x["R"] for x in v2 if x]), vyhody_v2=dict(collections.Counter(x["vyhod"] for x in v2 if x)))
# Brain: портфельный риск
pos = sorted([(S[k]["x"]["ts"] + H, S[k]["x"]["ts"] + H * (2 + S[k]["x"]["barov"]), S[k]["x"]["R"]) for k in ok])
gr = {"<5": [], ">=5": []}
for a, e, R in pos:
    otk = sum(1 for a2, e2, _ in pos if a2 < a < e2); gr[">=5" if otk >= 5 else "<5"].append(R)
out["brain_gruppy"] = {k: dict(n=len(v), sred_R=round(st.mean(v), 4) if v else None, summa_R=round(sum(v), 2)) for k, v in gr.items()}
for cap in (5, 8):
    otkr, prin, prop = [], [], []
    for a, e, R in pos:
        otkr = [x for x in otkr if x > a]
        if len(otkr) >= cap: prop.append(R); continue
        otkr.append(e); prin.append((a, R))
    wk = collections.defaultdict(float)
    for a, R in prin: wk[dt.datetime.utcfromtimestamp(a / 1000).strftime("%G-W%V")] += R
    out[f"cap{cap}"] = dict(propushcheno=len(prop), propushcheno_plyusovyh=sum(r > 0 for r in prop), summa_propushchennyh_R=round(sum(prop), 2),
                           hudshaya_nedelya_R=round(min(wk.values()), 2), max_otkrytyy_risk_R=cap)
json.dump(out, open("research_lab/results/pump4_v1_v2_analitika_20261020.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
