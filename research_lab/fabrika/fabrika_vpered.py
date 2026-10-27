#!/usr/bin/env python3
"""fabrika_vpered.py — «Фабрика вперёд» v1 (27.10.2026, Claude; путь развития интеллекта). Хук сторожа, раз в сутки.
Зачем: исторические окна Фабрики исчерпаны (ИИ стоит с 21.10). Будущие дни бюджета не имеют — модель их не видела.
Фабрика каждый день сама проверяет ВЕСЬ закрытый каталог гипотез на новых днях Binance (с 2026-10-01, `data/binance_d1_vpered`).
Каталог (заморожен этим файлом, sha в сводке): 12 атомов → одиночные (контроль) + все пары (plus/minus) × знак ±1; плюс все формулы,
которые ИИ когда-либо предлагал (data/factory_v3/ai_predlozheniya/obrabotano, со своим знаком).
Тест: поперечный, каждый день: z-оценка атомов по монетам (ликвидные: топ-100 по обороту 28 дн), сигнал на закрытии d−1, лонг верхних 20 %,
шорт нижних 20 %, доход дня d (закрытие к закрытию, перп), издержки 10 bps на сторону × оборот. Только чтение данных; ордеров нет.
Вердикт: до 60 дней — NAKOPLENIE; дальше KANDIDAT, если t ≥ порога Бонферрони по всему каталогу (одностороннее 5 %) и обе половины > 0.
KANDIDAT — не деньги: идёт в обычный prereg-путь Фабрики (на новых будущих днях, одна попытка).
Выход: data/factory_v3/vpered/dni.jsonl (по дню на запись, дописывается), svodka.json."""
import glob, hashlib, json, math, statistics as st, time
from pathlib import Path
from statistics import NormalDist
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
ARH, VP = D / "binance_kity", D / "binance_d1_vpered"
OUT = D / "factory_v3" / "vpered"; DNI, SV = OUT / "dni.jsonl", OUT / "svodka.json"
DEN = 86_400_000; START = 1790812800000                  # 2026-10-01 UTC — первый день вне всех окон
TOP, DOLYA, KOM_BPS, MIN_DNEY = 100, 0.2, 10.0, 60
ATOMY = ["m3_perp", "spot", "spot_minus_perp", "m3_vsplesk", "vyhodnye",           # атомы Фабрики v1
         "mom1", "mom7", "mom28", "volat28", "obem_vsplesk", "diapazon", "spot_dolya"]  # новые ценовые/объёмные атомы

def katalog():
    k = {}
    for a in ATOMY:
        for z in (1, -1): k[f"{a}|{z:+d}"] = dict(formula=a, znak=z, avtor="setka", kontrol=True)
    for i, a in enumerate(ATOMY):
        for b in ATOMY[i + 1:]:
            for op in ("plus", "minus"):
                for z in (1, -1): k[f"{op}({a},{b})|{z:+d}"] = dict(formula=[op, a, b], znak=z, avtor="setka", kontrol=False)
    for p in sorted(glob.glob(str(D / "factory_v3" / "ai_predlozheniya" / "obrabotano" / "*.json"))):
        try: pr = json.load(open(p))
        except Exception: continue
        if pr.get("formula") and all(a in ATOMY for a in _atomy(pr["formula"])):
            k[f'{pr.get("id")}|{int(pr.get("znak", 1)):+d}'] = dict(formula=pr["formula"], znak=int(pr.get("znak", 1)), avtor="ii", kontrol=False)
    return k

def _atomy(f): return [f] if isinstance(f, str) else [a for x in f[1:] for a in _atomy(x)]

def _calc(f, v):
    if isinstance(f, str): return v.get(f)
    x = [_calc(a, v) for a in f[1:]]
    if any(y is None for y in x): return None
    return {"plus": lambda: x[0] + x[1], "minus": lambda: x[0] - x[1], "proizv": lambda: x[0] * x[1], "neg": lambda: -x[0], "abs": lambda: abs(x[0])}[f[0]]()

def zagruzka():
    dan = {}
    for p in glob.glob(str(VP / "klines" / "*.json")):
        s = Path(p).stem; r = {}
        for nm in ("klines", "taker", "spot_taker"):
            rows = {}
            for src in (ARH / nm / f"{s}.json", VP / nm / f"{s}.json"):
                if src.exists():
                    for x in json.load(open(src)): rows[int(x[0])] = x
            r[nm] = rows
        if r["klines"] and r["taker"]: dan[s] = r
    return dan

def atomy_dnya(r, t):
    """Атомы, известные на закрытии дня t (бар t закрыт)."""
    k, tk, sp = r["klines"], r["taker"], r["spot_taker"]
    if t not in k or t not in tk: return None
    def m3(d): return tk[d][2] / tk[d][1] if d in tk and tk[d][1] else None
    def cl(d): return k[d][4] if d in k else None
    v = {}
    v["m3_perp"] = m3(t)
    v["spot"] = sp[t][2] / sp[t][1] if t in sp and sp[t][1] else None
    v["spot_minus_perp"] = v["spot"] - v["m3_perp"] if v["spot"] is not None and v["m3_perp"] is not None else None
    pr = [m3(t - i * DEN) for i in range(1, 29)]; pr = [x for x in pr if x is not None]
    v["m3_vsplesk"] = v["m3_perp"] - st.mean(pr) if v["m3_perp"] is not None and len(pr) >= 20 else None
    wd = time.gmtime(t / 1000).tm_wday; sun = t - ((wd - 6) % 7) * DEN; fri = sun - 2 * DEN
    v["vyhodnye"] = cl(sun) / cl(fri) - 1 if cl(sun) and cl(fri) else None
    for n, nm in ((1, "mom1"), (7, "mom7"), (28, "mom28")):
        v[nm] = cl(t) / cl(t - n * DEN) - 1 if cl(t) and cl(t - n * DEN) else None
    rets = [cl(t - i * DEN) / cl(t - (i + 1) * DEN) - 1 for i in range(28) if cl(t - i * DEN) and cl(t - (i + 1) * DEN)]
    v["volat28"] = st.pstdev(rets) if len(rets) >= 20 else None
    ob = [tk[t - i * DEN][1] for i in range(1, 29) if t - i * DEN in tk]
    v["obem_vsplesk"] = tk[t][1] / st.mean(ob) - 1 if len(ob) >= 20 and st.mean(ob) > 0 else None
    v["diapazon"] = (k[t][2] - k[t][3]) / k[t][4] if k[t][4] else None
    v["spot_dolya"] = sp[t][1] / (sp[t][1] + tk[t][1]) if t in sp and (sp[t][1] + tk[t][1]) else None
    v["_oborot28"] = st.mean(ob) if ob else 0
    return v

def prohod(kat=None, atom_fn=None, atomy=None, out_dir=None, nazvanie="Фабрика вперёд"):
    atom_fn = atom_fn or atomy_dnya; atomy = atomy or ATOMY; out_dir = out_dir or OUT
    DNI, SV = out_dir / "dni.jsonl", out_dir / "svodka.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    kat = kat or katalog(); sha = hashlib.sha256(json.dumps(kat, sort_keys=True).encode()).hexdigest()[:16]
    gotovo = {json.loads(l)["d"] for l in DNI.open()} if DNI.exists() else set()
    dan = zagruzka()
    posl = max((max(r["klines"]) for r in dan.values()), default=0)
    novyh, prev_port = 0, {}
    t = START
    while t + DEN <= posl:                                       # сигнал на закрытии t, доход дня t+DEN
        d = time.strftime("%Y-%m-%d", time.gmtime((t + DEN) / 1000))
        if d in gotovo: t += DEN; continue
        A = {s: atom_fn(r, t) for s, r in dan.items()}
        A = {s: v for s, v in A.items() if v and t + DEN in dan[s]["klines"]}
        liq = sorted(A, key=lambda s: -A[s]["_oborot28"])[:TOP]
        ret = {s: dan[s]["klines"][t + DEN][4] / dan[s]["klines"][t][4] - 1 for s in liq if dan[s]["klines"][t][4]}
        Z = {}
        for a in atomy:
            xs = [A[s][a] for s in liq if A[s].get(a) is not None]
            if len(xs) < 30: continue
            m, sd = st.mean(xs), st.pstdev(xs) or 1.0
            for s in liq:
                if A[s].get(a) is not None: Z.setdefault(s, {})[a] = (A[s][a] - m) / sd
        rez = {}
        for key, h in kat.items():
            sc = [(s, _calc(h["formula"], Z.get(s, {}))) for s in liq]; sc = sorted([(s, x) for s, x in sc if x is not None and s in ret], key=lambda q: q[1])
            if len(sc) < 30: continue
            n = max(1, int(len(sc) * DOLYA)); lo, hi = [s for s, _ in sc[:n]], [s for s, _ in sc[-n:]]
            if h["znak"] < 0: lo, hi = hi, lo
            gross = st.mean(ret[s] for s in hi) - st.mean(ret[s] for s in lo)
            rez[key] = round(gross * 1e4, 2); 
        with DNI.open("a") as f: f.write(json.dumps(dict(d=d, monet=len(liq), katalog_sha=sha, spread_bps=rez), ensure_ascii=False) + "\n")
        novyh += 1; t += DEN
    # сводка (издержки: 10 bps на сторону, дневная перебалансировка ~ консервативно 2 × 10 × 0.5 оборота = 10 bps в день)
    rows = [json.loads(l) for l in DNI.open()] if DNI.exists() else []
    N = len(kat); porog = NormalDist().inv_cdf(1 - 0.05 / max(N, 1))
    out = {}
    for key, h in kat.items():
        x = [r["spread_bps"][key] - KOM_BPS for r in rows if key in r["spread_bps"]]
        if len(x) < 3: continue
        m, sd = st.mean(x), st.stdev(x); tt = m / (sd / math.sqrt(len(x))) if sd else 0
        hlf = len(x) // 2
        status = "NAKOPLENIE" if len(x) < MIN_DNEY else ("KANDIDAT" if tt >= porog and st.mean(x[:hlf]) > 0 and st.mean(x[hlf:]) > 0 else "NET")
        out[key] = dict(dney=len(x), sred_bps_den=round(m, 2), t=round(tt, 2), status=status, avtor=h["avtor"], kontrol=h["kontrol"])
    top = sorted(out.items(), key=lambda kv: -kv[1]["t"])[:15]
    SV.write_text(json.dumps(dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), katalog=N, katalog_sha=sha, dney=len(rows),
                                  porog_t_bonferroni=round(porog, 2), min_dney=MIN_DNEY, kandidatov=sum(1 for v in out.values() if v["status"] == "KANDIDAT"),
                                  top15_opisatelno=dict(top), vse=out,
                                  primechanie="до 60 дней — только накопление; top15 описательно, не вердикт"), ensure_ascii=False, indent=1))
    return dict(novyh_dney=novyh, dney=len(rows), katalog=N, trevogi=[f"{nazvanie}: KANDIDAT {k}" for k, v in out.items() if v["status"] == "KANDIDAT"])

if __name__ == "__main__":
    t0 = time.time(); r = prohod(); print(r, round(time.time() - t0, 1), "с")
    s = json.loads(SV.read_text()); print("порог t", s["porog_t_bonferroni"]); [print(k, v) for k, v in list(s["top15_opisatelno"].items())[:8]]
