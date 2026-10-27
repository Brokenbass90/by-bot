#!/usr/bin/env python3
"""ets2s_polnyy_povtor.py — проверка тени ETS2S НЕПРЕРЫВНЫМ повтором (27.10.2026, Claude). Аналог pump4_polnyy_povtor.
Зачем: тень (`ten.py`) каждый час заново прогоняет стратегию на последних 1000 барах; блокировка «одна позиция на монету» действует
только внутри прохода, а уже виденные сигналы в следующих проходах пропускаются, не выставляя блок → возможны наложенные решения
по одной монете. Здесь: одна стратегия на монету, каждая закрытая H1 подряд от (начала тени − 1000 ч), стратегии на каждом баре
отдаются последние 1000 баров (как в тени), блок по монете сквозной,
вход/исход — те же sim_limit и параметры, что заморожены в тени (отступ 0.002, ждать 6, стоп ×4, держать 336, только шорт,
мейкер 1.5 / тейкер 5.5 bps). Контроль — sim_limit в случайный бар той же монеты (20 розыгрышей, seed фиксирован).
    Mac (сеть к Bybit):  .venv/bin/python3 research_lab/ets2s_polnyy_povtor.py
    без сети (138 монет, данные до 20.10):  python3 research_lab/ets2s_polnyy_povtor.py --lokalno
Результат: research_lab/results/ets2s_polnyy_povtor_<время>.json"""
import collections, glob, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
# таймфреймы — ровно как при запуске тени (podnyat_teni.sh)
os.environ.update(ETS2_TREND_TF="1440", ETS2_WAVE_TF="240", ETS2_ENTRY_TF="60", ETS2_RISK_TF="240")
import ten as T                       # chdir в корень, те же Store/sim_limit/MAX_LEV/prefiks
import pump4_pereschet as P
H = 3600000
SOST = json.load(open(HERE / "data" / "ten_ETS2S_sost.json"))
NACHALO = int(SOST["nachalo"]); Z = SOST["zamorozheno"]
OTSTUP, ZHDAT, STOP, HOLD = Z["otstup"], Z["zhdat"], Z["stop"], Z["hold"]
FEE_IN, FEE_OUT = 1.5, 5.5
MODUL, KLASS = "elder_triple_screen_v2", "ElderTripleScreenV2Strategy"
SLOTY = (3, 5, 10)                    # 3 — замороженный лимит портфеля тени (SLOTOV_SCHYOTA)

def bary_lokalno(sym):
    f = HERE / "data" / "oos_bybit_h1_20261020" / f"{sym}.json"
    return sorted(json.load(open(f))) if f.exists() else None

def povtor_monety(sym, b, K, rng):
    strat = K(); st = T.Store(sym); perv = T.pervyy_dlya(K, st, sym); out = []; block = -1
    pool = np.arange(200, max(201, len(b) - 2))
    for i in range(200, len(b) - 1):
        if i <= block: continue
        st.rows = b[max(0, i - 999): i + 1]; r_ = b[i]          # окно 1000 баров, как у тени (ten.svechi limit=1000)
        try: s = strat.maybe_signal(perv, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
        except Exception: continue
        if s is None or getattr(s, "side", None) != "short" or r_[0] < NACHALO: continue
        e_ref = float(b[i + 1][1]); sl_w = e_ref + (float(s.sl) - e_ref) * STOP; risk_w = abs(e_ref - sl_w)
        if risk_w <= 0 or e_ref <= 0: continue
        sp = risk_w / e_ref
        if 1.0 / sp > T.MAX_LEV: continue
        tl = list(s.tps or []); k1 = abs(tl[0] - e_ref) / risk_w if tl else 999.0; k2 = abs(tl[1] - e_ref) / risk_w if len(tl) > 1 else 999.0
        f1 = float((s.tp_fracs or [0.55])[0])
        dostupno = len(b) - 1 - (i + ZHDAT)
        res = T.sim_limit(b, i, True, sp, k1, k2, f1, HOLD, OTSTUP, ZHDAT, FEE_IN, FEE_OUT) if dostupno > 1 else None
        z = dict(sym=sym, ts=int(r_[0]))
        if res is None:
            # не исполнился лимит ИЛИ не хватило данных
            z["status"] = "NET_DANNYH" if dostupno <= 1 else "LIMIT_NE_ISPOLNEN_ILI_OTKRYTA"
            if dostupno > HOLD: z["status"] = "LIMIT_NE_ISPOLNEN"
            out.append(z); continue
        if res[1] >= min(dostupno, HOLD) and dostupno < HOLD:
            z["status"] = "OTKRYTA"; out.append(z); block = len(b); continue
        c = [T.sim_limit(b, int(rng.choice(pool)), True, sp, k1, k2, f1, HOLD, OTSTUP, ZHDAT, FEE_IN, FEE_OUT) for _ in range(20)]
        c = [x[0] for x in c if x is not None]
        z.update(status="ZAKRYTA", R=round(res[0], 4), barov=int(res[1]), plecho=round(1 / sp, 2),
                 zatraty_R=round((1 / sp) * (FEE_IN + FEE_OUT) / 1e4, 4), ctrl=round(float(np.mean(c)), 4) if c else None)
        block = i + ZHDAT + res[1] + 1; out.append(z)
    return out

def fanding_istoriya(sym, t0, t1):
    """публичная история фандинга Bybit (ставки на 8/4/1 ч), [ (ts, rate) ]"""
    import urllib.request
    out, end = [], t1
    while end > t0:
        u = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={sym}&startTime={t0}&endTime={end}&limit=200"
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "ets2s/1.0"}), timeout=25) as f:
            lst = (json.loads(f.read().decode()).get("result") or {}).get("list") or []
        if not lst: break
        part = [(int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in lst]
        out += part; nov = min(t for t, _ in part) - 1
        if nov >= end: break
        end = nov; time.sleep(0.12)
    return sorted(set(out))

def dobavit_fanding(sdelki_monety, sym):
    """шорт ПОЛУЧАЕТ положительный фандинг: R += Σ rate × плечо за выплаты внутри [вход; выход]"""
    z = [x for x in sdelki_monety if x["status"] == "ZAKRYTA"]
    if not z: return
    try: fr = fanding_istoriya(sym, min(x["ts"] for x in z), max(x["ts"] + (x["barov"] + ZHDAT + 2) * H for x in z))
    except Exception: return
    for x in z:
        a, b = x["ts"] + H, x["ts"] + (x["barov"] + ZHDAT + 2) * H
        f = sum(r for t, r in fr if a <= t < b) * x["plecho"]
        x["fanding_R"] = round(f, 4); x["R_bez_fandinga"] = x["R"]; x["R"] = round(x["R"] + f, 4)

def svod(g):
    if len(g) < 3: return dict(n=len(g))
    g = sorted(g, key=lambda x: x["ts"]); R = np.array([x["R"] for x in g]); c = np.cumsum(R)
    dni = collections.defaultdict(list)
    for x in g: dni[x["ts"] // 86400000].append(x["R"])
    a = np.array([np.mean(v) for v in dni.values()])
    cc = [x for x in g if x.get("ctrl") is not None]
    return dict(n=len(g), sred_R=round(float(R.mean()), 4), itog_R=round(float(R.sum()), 1), ubytochnyh=int((R < 0).sum()),
                prosadka_R=round(float((np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c).max()), 1),
                t_po_dnyam=round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2) if len(a) > 2 else None, dney=len(a),
                prevyshenie_nad_kontrolem=round(float(np.mean([x["R"] - x["ctrl"] for x in cc])), 4) if cc else None)

def sloty(g, k):
    """портфель: не больше k одновременно открытых, по времени входа; вход ~ ts+1ч, выход ~ +barov ч"""
    otkr, vz = [], []
    for x in sorted(g, key=lambda x: x["ts"]):
        t0 = x["ts"] + H; otkr = [t for t in otkr if t > t0]
        if len(otkr) >= k: continue
        otkr.append(t0 + (x["barov"] + 1) * H); vz.append(x)
    return svod(vz)

def main():
    lok = "--lokalno" in sys.argv
    pfx = T.prefiks_strategii(MODUL) or "ETS2"
    ten_r = {(x["sym"], x["ts"]): x for x in map(json.loads, open(HERE / "data" / "ten_ETS2S.jsonl")) if "R" in x}
    if lok:
        syms = sorted(Path(f).stem for f in glob.glob(str(HERE / "data" / "oos_bybit_h1_20261020" / "*.json")))
    else:
        syms = sorted(set(T.vselennaya(0)) | {k[0] for k in ten_r})
    os.environ.update({f"{pfx}_SYMBOL_ALLOWLIST": ",".join(syms), f"{pfx}_ALLOW_LONGS": "1", f"{pfx}_ALLOW_SHORTS": "1"})
    K = T._klass(type("A", (), dict(modul=MODUL, klass=KLASS))())
    now = int(time.time() * 1000); konec = now // H * H; rng = np.random.default_rng(20261027)
    vse, net = [], []; gran = None
    for n, sym in enumerate(syms, 1):
        try:
            b = bary_lokalno(sym) if lok else [x for x in P.svechi_okno(sym, NACHALO - 1000 * H, konec) if x[0] + H <= now]
        except Exception: b = None
        if not b or len(b) < 300: net.append(sym); continue
        if lok: b = [x for x in b if x[0] >= NACHALO - 1000 * H]
        gran = max(gran or 0, b[-1][0])
        sd = povtor_monety(sym, b, K, rng)
        if not lok: dobavit_fanding(sd, sym)
        vse += sd
        if n % 50 == 0: print(f"{n}/{len(syms)}", flush=True)
    z = [x for x in vse if x["status"] == "ZAKRYTA"]
    moi = {(x["sym"], x["ts"]): x for x in z}
    # сверка с тенью на общих монетах и в пределах данных повтора
    my_syms = {x["sym"] for x in vse} | set(syms) - set(net)
    ten_vnutri = {k: v for k, v in ten_r.items() if k[0] in my_syms and k[1] + (v.get("barov", 0) + ZHDAT + 2) * H <= (gran or 0)}
    obshchie = [k for k in ten_vnutri if k in moi]
    tolko_ten = [ten_vnutri[k] for k in ten_vnutri if k not in moi]
    tolko_moi = [moi[k] for k in moi if k not in ten_r]
    rasx = [abs(moi[k]["R"] - ten_vnutri[k]["R"]) for k in obshchie]
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), rezhim="lokalno_138_do_20.10" if lok else "bybit_seychas",
               monet=len(syms), bez_dannyh=len(net), statusy=dict(collections.Counter(x["status"] for x in vse)),
               povtor=svod(z), fanding_sred_R=round(float(np.mean([x.get("fanding_R", 0) for x in z])), 4) if z else None,
               s_fandingom=sum(1 for x in z if "fanding_R" in x), po_nedelyam={time.strftime("%m-%d", time.gmtime((w * 7) * 86400)): svod([x for x in z if x["ts"] // (7 * 86400000) == w]).get("sred_R")
                                             for w in sorted({x["ts"] // (7 * 86400000) for x in z})},
               portfel_sloty={str(k): sloty(z, k) for k in SLOTY},
               sverka_s_tenyu=dict(ten_v_predelah_povtora=len(ten_vnutri), obshchih=len(obshchie),
                                   max_rashozhdenie_R=round(max(rasx), 4) if rasx else None, sovpalo_R_tochno=sum(1 for r in rasx if r < 1e-4),
                                   ten_vse=svod(list(ten_vnutri.values())), tolko_v_teni=svod(tolko_ten), tolko_v_povtore=svod(tolko_moi)),
               parametry=dict(nachalo=NACHALO, otstup=OTSTUP, zhdat=ZHDAT, stop=STOP, hold=HOLD, fee=[FEE_IN, FEE_OUT]),
               kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    f = HERE / "results" / time.strftime("ets2s_polnyy_povtor_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=out, sdelki=z), ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)

if __name__ == "__main__": main()
