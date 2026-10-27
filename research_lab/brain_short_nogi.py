#!/usr/bin/env python3
"""brain_short_nogi.py — prereg/PREREG_BRAIN_SHORT_NOGI_REZHIM_2026_10_27.md (27.10.2026, Claude).
    python3 research_lab/brain_short_nogi.py  → research_lab/results/brain_short_nogi_<время>.json
Каждая нога отдельно (ATT1, ETS2; PUMP4 — справочно из Э1), затем портфель A/B с лимитами риска."""
import bisect, collections, glob, hashlib, json, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "os2"))
import rezhim_v1 as RZ
H = 3600000; M15 = 900000
PREREG = HERE / "prereg" / "PREREG_BRAIN_SHORT_NOGI_REZHIM_2026_10_27.md"
PREREG_SHA = "a8bc23c54bd1d7f706527b603d6c0975a32e44f324e512bc783f17dc372602d7"
SEALED = 1759276800000

def kv(t): g = time.gmtime(t / 1000); return f"{g.tm_year}-Q{(g.tm_mon - 1) // 3 + 1}"
def god(t): return time.gmtime(t / 1000).tm_year

def metki_ist():
    z = np.load(HERE / "data/h1/BTCUSDT.npz"); ts = z["ts"].astype(np.int64); m = ts < SEALED
    return {int(t): (x or "UNKNOWN") for t, x in zip(ts[m], RZ.metki(ts[m], z["ohlcv"].astype(float)[m]))}

def metki_vpered():
    b = sorted(json.load(open(HERE / "data/oos_bybit_h1_20261020/BTCUSDT.json")))
    m5 = collections.defaultdict(list)
    for l in open(HERE / "data/breakout_ten/m5/BTCUSDT.jsonl"):
        r = json.loads(l); m5[int(r[0]) // H * H].append([float(v) for v in r[:6]])
    t = b[-1][0] + H
    while t in m5:
        g = sorted(m5[t])
        if [int(x[0]) for x in g] != [t + k * 300000 for k in range(12)]: break
        b.append([t, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)]); t += H
    ts = np.array([x[0] for x in b], dtype=np.int64); o = np.array([x[1:] for x in b], dtype=float)
    return {int(a): (x or "UNKNOWN") for a, x in zip(ts, RZ.metki(ts, o))}

def metka(mt, ts, bar):
    """состояние, известное к закрытию сигнального бара: час, закрывшийся не позже ts+bar"""
    return mt.get((ts + bar) // H * H - H, "UNKNOWN")

def prosadka(R):
    c = np.cumsum(R); return float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max()) if len(R) else 0.0

def svod(g):
    if not g: return dict(n=0)
    g = sorted(g, key=lambda x: x["ts"]); R = np.array([x["R"] for x in g])
    o = dict(n=len(g), sred_R=round(float(R.mean()), 4), itog_R=round(float(R.sum()), 2), ubytochnyh=int((R < 0).sum()),
             prosadka_R=round(prosadka(R), 2), pribylnyh=int((R > 0).sum()), summa_pribylnyh_R=round(float(R[R > 0].sum()), 2))
    c = [x["ctrl"] for x in g if x.get("ctrl") is not None]
    if c: o["kontrol_sred"] = round(float(np.mean(c)), 4)
    z = [x["zatraty"] for x in g if x.get("zatraty") is not None]
    if z: o["izderzhki_sred_R"] = round(float(np.mean(z)), 4)
    return o

def butstrap(sd, n=2000, seed=27):
    ned = collections.defaultdict(list)
    for x in sd: ned[x["ts"] // (7 * 86400000)].append((x["rez"] != "BULL_TREND", x["R"]))
    keys = list(ned); rng = np.random.default_rng(seed)
    def razn(ws):
        a = [v for w in ws for f, v in ned[w] if f]; b = [v for w in ws for f, v in ned[w] if not f]
        return (np.mean(a) - np.mean(b)) if a and b else None
    base = razn(keys); res = np.array([r for r in (razn([keys[i] for i in rng.integers(0, len(keys), len(keys))]) for _ in range(n)) if r is not None])
    return dict(raznica=round(float(base), 4), q05=round(float(np.quantile(res, 0.05)), 4), dolya_le0=round(float((res <= 0).mean()), 4), nedel=len(keys))

def noga(sd):
    nb = [x for x in sd if x["rez"] != "BULL_TREND"]; bu = [x for x in sd if x["rez"] == "BULL_TREND"]
    r = lambda g: np.mean([x["R"] for x in g]) if g else None
    goda = {g: (round(float(r([x for x in nb if god(x["ts"]) == g]) - r([x for x in bu if god(x["ts"]) == g])), 4)
                if [x for x in nb if god(x["ts"]) == g] and [x for x in bu if god(x["ts"]) == g] else None) for g in sorted({god(x["ts"]) for x in sd})}
    loqo = {}
    for q in sorted({kv(x["ts"]) for x in sd}):
        a = [x for x in nb if kv(x["ts"]) != q]; b = [x for x in bu if kv(x["ts"]) != q]
        loqo[q] = round(float(r(a) - r(b)), 4) if a and b else None
    bs = butstrap(sd)
    out = dict(vse=svod(sd), po_rezhimam={m: svod([x for x in sd if x["rez"] == m]) for m in ("BULL_TREND", "BEAR_TREND", "NEUTRAL", "UNKNOWN")},
               vzyat_ne_bull=svod(nb), otrezano_bull=svod(bu), dolya_otrezano=round(len(bu) / len(sd), 3), butstrap=bs,
               raznica_po_godam=goda, bez_kvartala=loqo,
               po_kvartalam={q: dict(ne_bull=svod([x for x in nb if kv(x["ts"]) == q]), bull=svod([x for x in bu if kv(x["ts"]) == q])) for q in sorted({kv(x["ts"]) for x in sd})})
    if any("shirina" in x for x in sd):
        out["volna_v_bull_opisatelno"] = dict(otrezano=svod([x for x in sd if x["rez"] == "BULL_TREND" and x.get("shirina", 0) >= 3]),
                                             vzyat=svod([x for x in sd if not (x["rez"] == "BULL_TREND" and x.get("shirina", 0) >= 3)]))
    v = dict(a_n=len(nb) >= 30 and len(bu) >= 30, b_butstrap=bs["raznica"] > 0 and bs["dolya_le0"] <= 0.05,
             v_kazhdyy_god=all(x is not None and x > 0 for x in goda.values()), g_otrez_le0=bool(bu) and r(bu) <= 0,
             d_bez_kvartala=all(x is not None and x > 0 for x in loqo.values()))
    v = {k: bool(x) for k, x in v.items()}
    v["itog"] = "PASS" if all(v.values()) else "FAIL"; out["verdikt"] = v
    return out

def portfel(nogi, filtr):
    """nogi: имя -> список (ts_vhod, ts_vyhod, R, rez). Лимит 5 на ногу, 12 всего; сделки по времени входа."""
    ev = sorted((t0, t1, R, n, rez) for n, L in nogi.items() for (t0, t1, R, rez) in L if not (filtr.get(n) and rez == "BULL_TREND"))
    otkr = []; vzyato = []; propusk = collections.Counter()
    for t0, t1, R, n, rez in ev:
        otkr = [x for x in otkr if x[0] > t0]
        if len(otkr) >= 12 or sum(1 for x in otkr if x[1] == n) >= 5: propusk[n] += 1; continue
        otkr.append((t1, n)); vzyato.append((t0, R, n))
    R = np.array([x[1] for x in vzyato])
    ned = collections.defaultdict(float)
    for t0, r, n in vzyato: ned[t0 // (7 * 86400000)] += r
    return dict(sdelok=len(vzyato), po_nogam=dict(collections.Counter(x[2] for x in vzyato)), propuskov_po_limitu=dict(propusk),
                itog_R=round(float(R.sum()), 2), prosadka_R=round(prosadka(R), 2),
                itog_k_prosadke=round(float(R.sum()) / max(prosadka(R), 1e-9), 2)), ned

def main():
    if hashlib.sha256(PREREG.read_bytes()).hexdigest() != PREREG_SHA: sys.exit("prereg изменён")
    if not RZ.proverit(): sys.exit("замок FAIL")
    mt = metki_ist(); mv = metki_vpered()
    p4 = json.load(open(sorted(glob.glob(str(HERE / "results/pump4_shirina_e1_*.json")))[-1]))["sdelki"]
    sig_p4 = sorted(x["ts"] for x in p4)
    shir = lambda t: bisect.bisect_left(sig_p4, t) - bisect.bisect_left(sig_p4, t - 24 * H)
    # история
    att = [dict(sym=x["sym"], ts=x["ts"], R=x["R"], ctrl=x["ctrl"], rez=metka(mt, x["ts"], H)) for x in map(json.loads, open(HERE / "data/att1_kontekst/sdelki.jsonl"))]
    ets = [dict(sym=x["sym"], ts=x["ts"], R=x["R"], hours=x["hours"], rez=metka(mt, x["ts"], M15)) for x in json.load(open(HERE / "os2/potoki/ETS2.json"))]
    att = [x for x in att if x["ts"] < SEALED]; ets = [x for x in ets if x["ts"] < SEALED]
    for x in att + ets: x["shirina"] = shir(x["ts"])
    out = dict(prereg_sha256=PREREG_SHA, ATT1=noga(att), ETS2=noga(ets))
    # тени вперёд (описательно; R — оценщик штатной тени)
    vp = {}
    for n, f in (("ATT1", "ten_ATT1.jsonl"), ("ETS2S", "ten_ETS2S.jsonl")):
        L = [json.loads(l) for l in open(HERE / "data" / f) if '"R"' in l]
        sd = [dict(ts=x["ts"], R=x["R"], ctrl=x.get("ctrl"), zatraty=x.get("zatraty_R"), rez=metka(mv, x["ts"], H)) for x in L]
        vp[n] = dict(vse=svod(sd), **{m: svod([x for x in sd if x["rez"] == m]) for m in ("BULL_TREND", "BEAR_TREND", "NEUTRAL", "UNKNOWN")},
                     ne_bull=svod([x for x in sd if x["rez"] != "BULL_TREND"]),
                     po_nedelyam={time.strftime("%m-%d", time.gmtime(w * 7 * 86400)): dict(bull=svod([x for x in sd if x["ts"] // (7 * 86400000) == w and x["rez"] == "BULL_TREND"]).get("sred_R"),
                                  ne_bull=svod([x for x in sd if x["ts"] // (7 * 86400000) == w and x["rez"] != "BULL_TREND"]).get("sred_R"))
                                  for w in sorted({x["ts"] // (7 * 86400000) for x in sd})})
    out["vpered_teni"] = vp
    # портфель 2024-03..2025-09
    a0, a1 = 1709251200000, SEALED
    nogi = {"PUMP4": [(x["ts"] + H, x["ts"] + H + (x["barov"] + 1) * H, x["R"], x["rezhim"]) for x in p4 if a0 <= x["ts"] < a1],
            "ATT1": [(x["ts"] + H, x["ts"] + H + 336 * H, x["R"], x["rez"]) for x in att if a0 <= x["ts"] < a1],
            "ETS2": [(x["ts"] + M15, x["ts"] + M15 + x["hours"] * H, x["R"], x["rez"]) for x in ets if a0 <= x["ts"] < a1]}
    pas = {k: out[k]["verdikt"]["itog"] == "PASS" for k in ("ATT1", "ETS2")}; pas["PUMP4"] = False
    A, na = portfel(nogi, {}); B, nb_ = portfel(nogi, pas); B2, nb2 = portfel(nogi, {k: True for k in nogi})
    def bs_port(na, nb_, n=2000):
        ks = sorted(set(na) | set(nb_)); d = np.array([nb_.get(k, 0) - na.get(k, 0) for k in ks]); rng = np.random.default_rng(27)
        r = np.array([d[rng.integers(0, len(d), len(d))].sum() for _ in range(n)])
        return dict(raznica_R=round(float(d.sum()), 2), dolya_le0=round(float((r <= 0).mean()), 4), nedel=len(ks))
    out["portfel"] = dict(primechanie="ATT1: длительность в источнике нет → занята 336 ч (верхняя граница)", proshli=pas,
                          A_vse_vsegda=A, B_po_kriteriyu=B, B_minus_A=bs_port(na, nb_), B2_nobull_u_vseh=B2, B2_minus_A=bs_port(na, nb2))
    out.update(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    f = HERE / "results" / time.strftime("brain_short_nogi_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
