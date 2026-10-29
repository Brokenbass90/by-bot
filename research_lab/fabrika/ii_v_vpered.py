#!/usr/bin/env python3
"""ii_v_vpered.py — ИИ пишет формулы прямо в «Фабрику вперёд» (29.10.2026, Claude). Хук сторожа; генерация — раз в неделю ночью (01–05 UTC),
≤ 5 предложений, локальная Ollama (qwen3:4b → 8b), без платных API. Генератор больше не ждёт исторических окон: каждая формула проверяется только на днях
ПОСЛЕ её предложения (модель их не видела). Словарь — 17 атомов каталога v2; формула — дерево глубины ≤ 3, атомов ≤ 3; пары из сетки v1/v2
(они уже проверяются) отклоняются — ИИ нужен для формул сложнее пары. В промпт идут уроки провалов (реестр гипотез). Реестр предложений —
data/factory_v3/vpered_ii/predlozheniya.jsonl (дописывается, с механизмом и датой). Оценка каждый проход: та же поперечная проверка, что у v1/v2,
Бонферрони по ВСЕМ предложениям ИИ за всё время, вердикт с 60 дней от даты предложения. Ордеров нет."""
import json, sys, time, hashlib, statistics as st, math
from pathlib import Path
from statistics import NormalDist
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika")); sys.path.insert(0, str(LAB))
import fabrika_vpered as FV, fabrika_vpered_v2 as V2
OUT = LAB / "data" / "factory_v3" / "vpered_ii"; PR = OUT / "predlozheniya.jsonl"; SOST = OUT / "sost.json"
OPIS = {"m3_perp": "доля агрессивных покупок на перпе", "spot": "доля агрессивных покупок на споте", "spot_minus_perp": "спот против плечевого спроса",
        "m3_vsplesk": "всплеск агрессии покупателей против нормы 28 дн", "vyhodnye": "доходность за выходные", "mom1": "доходность за день", "mom7": "за 7 дней",
        "mom28": "за 28 дней", "volat28": "волатильность 28 дн", "obem_vsplesk": "объём к норме 28 дн", "diapazon": "дневной диапазон", "spot_dolya": "доля спота в обороте",
        "fanding_den": "фандинг за день", "fanding_vsplesk": "фандинг против нормы", "oi_izm1": "изменение OI за день", "oi_izm7": "изменение OI за 7 дн",
        "oi_minus_cena7": "OI растёт без цены"}
OPS = {"plus": 2, "minus": 2, "proizv": 2, "neg": 1, "abs": 1}

def _gl(f): return 0 if isinstance(f, str) else 1 + max(_gl(x) for x in f[1:])
def _ok(f):
    if isinstance(f, str): return f in V2.ATOMY
    return isinstance(f, list) and f and f[0] in OPS and len(f) == OPS[f[0]] + 1 and all(_ok(x) for x in f[1:])
def _klyuch(f, z): return json.dumps(f, separators=(",", ":")) + f"|{z:+d}"

def generaciya(now):
    import poly_novosti_ollama as P
    m = P.model_dostupna()
    if not m: return dict(status="ollama_nedostupna")
    from factory_v3.ai_kontrakt_v1 import klient_ollama
    kl = klient_ollama(m, P.OLL, opcii=dict(num_ctx=4096, num_predict=300, temperature=0.7), timeout_s=300)
    uroki = (LAB / "data" / "factory_v3" / "uroki_dlya_ii.txt").read_text() if (LAB / "data" / "factory_v3" / "uroki_dlya_ii.txt").exists() else ""
    bylo = {json.loads(l)["klyuch"] for l in PR.open()} if PR.exists() else set()
    sis = ("Ты исследователь крипторынка. Раз в день монеты (топ-100 Binance по обороту) ранжируются по формуле из атомов (z-оценки по монетам): "
           "покупаем верхние 20 %, продаём нижние 20 %, держим сутки. Атомы: " + "; ".join(f"{k} — {v}" for k, v in OPIS.items()) +
           ". Операции: plus, minus, proizv (произведение), neg, abs. Глубина ≤ 3, атомов ≤ 3, НЕ простая пара атомов (их уже проверяем) — "
           "нужна формула сложнее, с экономической причиной: кто вынужден торговать и почему цена отклонится. " + uroki +
           ' Ответ JSON: {"formula": [...], "znak": 1 или -1, "mehanizm": "2-3 предложения", "kto_vynuzhden": "1 предложение"}')
    nov = []
    for _ in range(8):
        if len(nov) >= 5: break
        try: o = kl(sis, "Предложи одну новую формулу.")
        except Exception as e: continue
        f, z = o.get("formula"), int(o.get("znak", 1)) if str(o.get("znak", "1")).lstrip("-").isdigit() else 1
        if z not in (1, -1) or not _ok(f) or _gl(f) > 3 or len(FV._atomy(f)) > 3 or len(set(FV._atomy(f))) < 2: continue
        if _gl(f) == 1 and f[0] in ("plus", "minus"): continue                     # простая пара — уже в сетке
        k = _klyuch(f, z)
        if k in bylo: continue
        z_ = dict(klyuch=k, formula=f, znak=z, mehanizm=str(o.get("mehanizm", ""))[:400], kto_vynuzhden=str(o.get("kto_vynuzhden", ""))[:200],
                  model=m, data=time.strftime("%Y-%m-%d", time.gmtime(now)), ts=int(now * 1000))
        bylo.add(k); nov.append(z_)
    OUT.mkdir(parents=True, exist_ok=True)
    with PR.open("a") as fh:
        for z_ in nov: fh.write(json.dumps(z_, ensure_ascii=False) + "\n")
    return dict(status="ok", novyh=len(nov), model=m)

def prohod(sila=False):
    now = time.time(); g = time.gmtime(now); s = json.loads(SOST.read_text()) if SOST.exists() else {}
    ned = time.strftime("%G-W%V", g); gen = None
    if sila or (s.get("nedelya") != ned and 1 <= g.tm_hour <= 5):
        gen = generaciya(now); s["nedelya"] = ned; OUT.mkdir(parents=True, exist_ok=True); SOST.write_text(json.dumps(s))
    P = [json.loads(l) for l in PR.open()] if PR.exists() else []
    if not P: return dict(generaciya=gen, predlozheniy=0)
    kat = {p["klyuch"]: dict(formula=p["formula"], znak=p["znak"], avtor="ii", kontrol=False) for p in P}
    zag = FV.zagruzka
    def zagruzka():
        d = zag()
        for sy, r in d.items(): r["_sym"] = sy
        return d
    FV.zagruzka = zagruzka; V2._kesh.clear()
    try: FV.prohod(kat=kat, atom_fn=V2.atomy_dnya, atomy=V2.ATOMY, out_dir=OUT, nazvanie="Фабрика вперёд ИИ")
    finally: FV.zagruzka = zag
    rows = [json.loads(l) for l in (OUT / "dni.jsonl").open()] if (OUT / "dni.jsonl").exists() else []
    N = len(P); porog = NormalDist().inv_cdf(1 - 0.05 / max(N, 1)); res = {}
    for p in P:
        x = [r["spread_bps"][p["klyuch"]] - FV.KOM_BPS for r in rows if r["d"] > p["data"] and p["klyuch"] in r["spread_bps"]]
        n = len(x); t = (st.mean(x) / (st.stdev(x) / math.sqrt(n))) if n > 2 and st.stdev(x) > 0 else None
        res[p["klyuch"]] = dict(dney_posle_predlozheniya=n, mehanizm=p["mehanizm"][:120],
                                status="NAKOPLENIE" if n < FV.MIN_DNEY else ("KANDIDAT" if (t or 0) >= porog and st.mean(x[: n // 2]) > 0 and st.mean(x[n // 2:]) > 0 else "NET"))
    (OUT / "svodka_ii.json").write_text(json.dumps(dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", g), predlozheniy=N, porog_t=round(porog, 2),
        primechanie="результаты скрыты до 60 дней после предложения; считаются только дни после даты предложения", gipotezy={k: {kk: vv for kk, vv in v.items() if kk != "t"} for k, v in res.items()}), ensure_ascii=False, indent=1))
    return dict(generaciya=gen, predlozheniy=N, trevogi=[f"ИИ-гипотеза KANDIDAT: {k}" for k, v in res.items() if v["status"] == "KANDIDAT"])

if __name__ == "__main__":
    print(prohod(sila="--sila" in sys.argv))
