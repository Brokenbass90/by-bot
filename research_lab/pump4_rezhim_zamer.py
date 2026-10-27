#!/usr/bin/env python3
"""pump4_rezhim_zamer.py — PUMP4 V1 × REZHIM_V1 по prereg/PREREG_PUMP4_REZHIM_V1_2026_10_27.md (27.10.2026, Claude).
    python3 research_lab/pump4_rezhim_zamer.py e0            # 84 сделки 01.09–19.10.2026 (описание)
    python3 research_lab/pump4_rezhim_zamer.py e1 [--proc 3] # история 2023-03..2025-09 (обнаружение)
    python3 research_lab/pump4_rezhim_zamer.py e2 [--proc 3] # запечатанное 2025-10-01..2026-08-11 (только при PASS Э1)
Стратегия и сделка — тот же путь, что pump4_polnyy_povtor (P.Store, P.simulate, стоп ×4, 168 ч, тейкер 6 bps, sim_geo ×10).
Метка режима — os2/rezhim_v1.metki на часе сигнала (известна к концу часа), вход — открытие следующего часа."""
import collections, glob, hashlib, importlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "os2"))
import pump4_pereschet as P          # делает chdir в корень репо
import rezhim_v1 as RZ
H = 3600000
PREREG = HERE / "prereg" / "PREREG_PUMP4_REZHIM_V1_2026_10_27.md"
PREREG_SHA = "6699dd41491eaafd2882f6795beafc2c356df38bef756b1d4e0d2be414efd1b4"
import calendar
T = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%d")) * 1000
OKNA = {"e1": (T("2023-03-01"), T("2025-10-01")), "e2": (T("2025-10-01"), T("2026-08-11"))}
POD = {"e1": {"W1 2023-03..2024-02": (T("2023-03-01"), T("2024-03-01")), "W2 2024-03..2025-09": (T("2024-03-01"), T("2025-10-01"))}}
PROGREV = 1200

def proverka_prereg():
    s = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if s != PREREG_SHA: sys.exit("prereg изменён после заморозки: " + s)
    if not RZ.proverit(): sys.exit("замок REZHIM_V1 FAIL")

def metki_btc(ts, o):
    return {int(t): (m or "UNKNOWN") for t, m in zip(ts, RZ.metki(ts, o))}

# ---------- статистика ----------
def prosadka(R):
    c = np.cumsum(R); return float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max()) if len(R) else 0.0

def svod(g):
    if not g: return dict(n=0)
    g = sorted(g, key=lambda x: x["ts"]); R = np.array([x["R"] for x in g])
    out = dict(n=len(g), sred_R=round(float(R.mean()), 4), itog_R=round(float(R.sum()), 2), ubytochnyh=int((R < 0).sum()),
               hudshiy=round(float(R.min()), 3), prosadka_R=round(prosadka(R), 2))
    c = [x["ctrl"] for x in g if x.get("ctrl") is not None]
    if c: out.update(kontrol_sred=round(float(np.mean(c)), 4), prevyshenie=round(float(np.mean([x["R"] - x["ctrl"] for x in g if x.get("ctrl") is not None])), 4))
    return out

def epizody(metki_ts, sdelki):
    """число непрерывных отрезков режима (по часовым меткам BTC), в которые попали сделки, по состояниям"""
    ks = sorted(metki_ts); ep, cur, k = {}, None, -1
    for t in ks:
        m = metki_ts[t]
        if m != cur: k += 1; cur = m
        ep[t] = k
    d = collections.defaultdict(set)
    for x in sdelki: d[x["rezhim"]].add(ep.get(x["ts"]))
    return {m: len(v) for m, v in d.items()}

def butstrap_raznica(sd, n=2000, seed=27):
    """недельный бутстрап разницы превышения: «не BULL» − BULL. Возвращает среднюю разницу, 5 % квантиль, долю ≤ 0."""
    ned = collections.defaultdict(list)
    for x in sd:
        if x.get("ctrl") is None: continue
        ned[x["ts"] // (7 * 86400000)].append((x["rezhim"] != "BULL_TREND", x["R"] - x["ctrl"]))
    keys = list(ned); rng = np.random.default_rng(seed); res = []
    def razn(ws):
        a = [v for w in ws for f, v in ned[w] if f]; b = [v for w in ws for f, v in ned[w] if not f]
        return (np.mean(a) - np.mean(b)) if a and b else None
    base = razn(keys)
    for _ in range(n):
        r = razn([keys[i] for i in rng.integers(0, len(keys), len(keys))])
        if r is not None: res.append(r)
    res = np.array(res)
    return dict(raznica=round(float(base), 4) if base is not None else None, q05=round(float(np.quantile(res, 0.05)), 4),
                dolya_le0=round(float((res <= 0).mean()), 4), nedel=len(keys))

def otchet(sd, metki_ts):
    po = {m: svod([x for x in sd if x["rezhim"] == m]) for m in ("BULL_TREND", "BEAR_TREND", "NEUTRAL", "UNKNOWN")}
    nb = [x for x in sd if x["rezhim"] != "BULL_TREND"]; bu = [x for x in sd if x["rezhim"] == "BULL_TREND"]
    return dict(vse=svod(sd), po_rezhimam=po, filtr_ne_bull=svod(nb), otrezano=svod(bu),
                dolya_otrezano=round(len(bu) / len(sd), 3) if sd else None, epizody=epizody(metki_ts, sd),
                butstrap=butstrap_raznica(sd) if bu and nb else None)

# ---------- Э0 ----------
def e0():
    d = json.load(open(HERE / "results" / "pump4_fanding_ekonomika_20261026T1414Z.json"))["sdelki"]
    ctrl = {(x["sym"], x["ts"]): x.get("ctrl") for x in json.load(open(HERE / "results" / "pump4_polnyy_povtor_20261026T0857Z.json"))["sdelki"]}
    # публичные часовки Bybit BTCUSDT 01.05–20.10.2026, скачанные 20.10 (сеть из VM к Bybit закрыта)
    b = sorted(json.load(open(HERE / "data" / "oos_bybit_h1_20261020" / "BTCUSDT.json")))
    # после 20.10 09:00 — часы из 5-минуток Bybit (breakout_ten/m5), только полные 12/12; сверка на пересечении пишется в отчёт
    m5 = collections.defaultdict(list)
    for l in open(HERE / "data" / "breakout_ten" / "m5" / "BTCUSDT.jsonl"):
        r = json.loads(l); m5[int(r[0]) // H * H].append([float(v) for v in r[:6]])
    h_m5 = {}
    for t, g in m5.items():
        g = sorted(g)
        if [int(x[0]) for x in g] == [t + k * 300000 for k in range(12)]:
            h_m5[t] = [t, g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)]
    peres = [abs(h_m5[x[0]][4] / x[4] - 1) for x in b if x[0] in h_m5]
    sverka_m5 = dict(chasov_peresecheniya=len(peres), maks_rashozhdenie_close=max(peres) if peres else None)
    t = b[-1][0] + H
    while t in h_m5: b.append(h_m5[t]); t += H
    dyry = sum(1 for i in range(1, len(b)) if b[i][0] - b[i - 1][0] != H)
    ts = np.array([x[0] for x in b], dtype=np.int64); o = np.array([x[1:] for x in b], dtype=float)
    mt = metki_btc(ts, o)
    sd = [dict(sym=x["sym"], ts=x["ts"], mesyac=x["mesyac"], R=round(x["R_posle_komissii"] + x["fanding_R"], 4),
               ctrl=ctrl.get((x["sym"], x["ts"])), rezhim=mt.get(x["ts"], "NET_METKI")) for x in d]
    okno = {t: m for t, m in mt.items() if min(x["ts"] for x in d) <= t <= max(x["ts"] for x in d)}
    out = dict(etap="E0", btc_chasov=len(b), btc_dyr=dyry, sverka_m5=sverka_m5, btc_do=b[-1][0], otchet=otchet(sd, okno),
               po_mesyacam={m: {r: svod([x for x in sd if x["mesyac"] == m and x["rezhim"] == r]) for r in ("BULL_TREND", "BEAR_TREND", "NEUTRAL", "UNKNOWN")}
                            for m in sorted({x["mesyac"] for x in sd})},
               rezhim_btc_po_dnyam=_po_dnyam(okno), sdelki=sd)
    return out

def _po_dnyam(mt):
    d = collections.defaultdict(collections.Counter)
    for t, m in mt.items(): d[time.strftime("%m-%d", time.gmtime(t / 1000))][m] += 1
    return {k: v.most_common(1)[0][0][:4] for k, v in sorted(d.items())}

# ---------- Э1 / Э2 ----------
def odna_moneta(args):
    sym, start, cut, seed = args
    os.environ.update({f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    f = HERE / "data" / "h1" / f"{sym}.npz"
    if not f.exists(): return sym, None, "net_fayla"
    z = np.load(f); ts = z["ts"].astype(np.int64); o = z["ohlcv"].astype(float)
    m = (ts >= start - PROGREV * H) & (ts < cut); ts, o = ts[m], o[m]
    if len(ts) < 400: return sym, [], "malo_barov"
    b = [[int(ts[k]), *map(float, o[k])] for k in range(len(ts))]
    dyr = sum(1 for k in range(1, len(b)) if b[k][0] - b[k - 1][0] != H)
    strat = K(); st = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else st
    rng = np.random.default_rng(seed); pool = list(range(200, max(200, len(b) - P.HOLD - 2))); out = []
    for i in range(len(b) - 1):
        st.rows = b[: i + 1]; r_ = b[i]
        try: s = strat.maybe_signal(perv, *r_)
        except Exception: s = None
        if s is None or getattr(s, "side", None) not in ("long", "short") or r_[0] < start or i < 200: continue
        r = P.simulate(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
        x = dict(sym=sym, ts=r_[0], side=s.side)
        if r is None or r.get("lev", 0) > P.MAX_LEV: x["status"] = "NE_ISPOLNIMO"
        elif not P.zaversheno(b, i, r): x["status"] = "NE_ZAVERSHENA_DO_GRANICY"
        else:
            e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * P.STOP_MULT)); rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
            k1, k2 = (rr + [999.0, 999.0])[:2]
            c = [P.sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [P.F1])[0], P.HOLD) for _ in range(P.DRAWS)] if pool else []
            c = [v for v in c if v is not None]
            x.update(status="ZAKRYTA", R=round(r["R"], 4), ctrl=round(float(np.mean(c)), 4) if c else None, barov=r["bars"], lev=round(r["lev"], 2))
        out.append(x)
    return sym, out, f"dyr {dyr}" if dyr else "ok"

def e12(etap, proc):
    start, cut = OKNA[etap]
    if etap == "e2":
        f1 = sorted(glob.glob(str(HERE / "results" / "pump4_rezhim_e1_*.json")))
        if not f1 or json.load(open(f1[-1]))["verdikt"]["itog"] != "PASS": sys.exit("Э2 запрещён: нет PASS Э1")
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    os.environ[f"{P.PFX}_SYMBOL_ALLOWLIST"] = ",".join(syms)
    zb = np.load(HERE / "data" / "h1" / "BTCUSDT.npz"); bts = zb["ts"].astype(np.int64); bo = zb["ohlcv"].astype(float)
    mb = bts < cut; mt = metki_btc(bts[mb], bo[mb])
    args = [(s, start, cut, 20261027 + k) for k, s in enumerate(syms)]
    vse, sost = [], {}
    if proc > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(proc) as pool:
            for n, (sym, sd, st) in enumerate(pool.imap_unordered(odna_moneta, args), 1):
                sost[sym] = st; vse += sd or []; print(f"{n}/{len(syms)} {sym} {st} сигналов {len(sd or [])}", flush=True)
    else:
        for n, a in enumerate(args, 1):
            sym, sd, st = odna_moneta(a); sost[sym] = st; vse += sd or []; print(f"{n}/{len(syms)} {sym} {st}", flush=True)
    for x in vse: x["rezhim"] = mt.get(x["ts"], "UNKNOWN")
    z = [x for x in vse if x["status"] == "ZAKRYTA"]
    okno = {t: m for t, m in mt.items() if start <= t < cut}
    out = dict(etap=etap.upper(), okno=[start, cut], statusy=dict(collections.Counter(x["status"] for x in vse)),
               storony=dict(collections.Counter(x["side"] for x in z)), monety=sost, otchet=otchet(z, okno),
               chasy_rezhima=dict(collections.Counter(okno.values())))
    if etap in POD:
        out["po_oknam"] = {k: otchet([x for x in z if a <= x["ts"] < b_], {t: m for t, m in okno.items() if a <= t < b_}) for k, (a, b_) in POD[etap].items()}
    out["po_godam"] = {g: {r: svod([x for x in z if time.gmtime(x["ts"] / 1000).tm_year == g and (x["rezhim"] == "BULL_TREND") == (r == "BULL")]) for r in ("BULL", "ne_BULL")}
                       for g in sorted({time.gmtime(x["ts"] / 1000).tm_year for x in z})}
    out["verdikt"] = verdikt(etap, out); out["sdelki"] = z
    return out

def verdikt(etap, o):
    ot = o["otchet"]; nb, bu = ot["filtr_ne_bull"], ot["otrezano"]
    if etap == "e1":
        bs = ot["butstrap"] or {}
        a = bu.get("n", 0) >= 30 and nb.get("n", 0) >= 30
        b = (bs.get("raznica") or 0) > 0 and bs.get("dolya_le0", 1) <= 0.05
        zn = []
        for k, v in o["po_oknam"].items():
            q = v.get("butstrap") or {}; zn.append((q.get("raznica") or 0) > 0)
        c = all(zn) and len(zn) == 2
        d = bu.get("n", 0) > 0 and bu["sred_R"] <= 0
        return dict(a_n=a, b_raznica_butstrap=b, v_oba_okna=c, g_otrezannye_le0=d, itog="PASS" if (a and b and c and d) else "FAIL")
    a = bu.get("n", 0) >= 20 and nb.get("n", 0) >= 20
    b = a and nb["sred_R"] > bu["sred_R"]; c = a and bu["sred_R"] <= 0
    return dict(a_n=a, b_ne_bull_luchshe=b, v_otrezannye_le0=c, itog="PASS" if (a and b and c) else "FAIL")

if __name__ == "__main__":
    proverka_prereg()
    etap = sys.argv[1]; proc = int(sys.argv[sys.argv.index("--proc") + 1]) if "--proc" in sys.argv else 1
    t0 = time.time(); out = e0() if etap == "e0" else e12(etap, proc)
    out.update(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), sekund=round(time.time() - t0), prereg_sha256=PREREG_SHA,
               kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    f = HERE / "results" / time.strftime(f"pump4_rezhim_{etap}_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    pr = {k: v for k, v in out.items() if k not in ("sdelki", "monety")}
    print(json.dumps(pr, ensure_ascii=False, indent=1)[:6000]); print("файл:", f)
