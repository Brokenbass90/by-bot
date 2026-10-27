#!/usr/bin/env python3
"""poly_ishod_reshen.py — prereg/PREREG_POLY_ISHOD_RESHEN_2026_10_27.md. Mac (сеть + Ollama), лучше ночью, ~2–3 ч:
    .venv/bin/python3 research_lab/poly_ishod_reshen.py > research_lab/data/poly_reshen.log 2>&1
    итог в любой момент:  .venv/bin/python3 research_lab/poly_ishod_reshen.py --itog
Только чтение (Gamma, CLOB prices-history, Google News RSS, локальная Ollama). Ордеров и ключей нет. Повторный запуск продолжает с места."""
import datetime as dt, hashlib, json, math, re, sys, time, urllib.parse
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import poly_novosti_ollama as P, poly_ollama_istoriya as I
SHA = "73292f3dd4c0e8b35462278c1c0ee2aeaa728d07af074ec80fd6b2f6f85af44b"; N_MAX = 300; TOCHKI = (7, 3, 1)
OUT = HERE / "data" / "poly_ishod_reshen.jsonl"
SIS = ("You read news for a prediction market. Given the question, its exact resolution rules, the current time and dated headlines, decide "
       "whether the outcome is ALREADY DECIDED as of now: the event has already happened (YES) or has become impossible under the rules (NO). "
       "Answer YES or NO only if a headline directly shows it; if anything is still uncertain, answer OPEN. "
       'Answer JSON only: {"reshen": "YES" | "NO" | "OPEN", "prichina": "<one short sentence>"}')

def kom(rate, cena): return rate * (1 - cena)

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_POLY_ISHOD_RESHEN_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    model = P.model_dostupna()
    if not model: sys.exit("Ollama недоступна (ollama serve / модель qwen3:8b)")
    kl = P.klient(model); uzhe = {json.loads(l)["id"] for l in OUT.open()} if OUT.exists() else set()
    ryn = I.zakrytye(); print("закрытых рынков подходит:", len(ryn), flush=True); n = len(uzhe)
    for m in ryn:
        if n >= N_MAX: break
        if m["id"] in uzhe: continue
        try:
            T = c = None
            for d in TOCHKI:
                t = m["konec"] - dt.timedelta(days=d); y = I.cena_do(m["token"], t)
                if y is not None and 0.80 <= max(y, 1 - y) <= 0.97: T, c = t, y; break
            if T is None: continue
            q = re.sub(r"^(will|is|does|did|has|have|are)\s+", "", m["vopros"].strip(), flags=re.I).rstrip("?")[:110]
            nov = I._rss("https://news.google.com/rss/search?" + urllib.parse.urlencode(dict(q=q + f" after:{(T - dt.timedelta(days=7)).date()} before:{(T + dt.timedelta(days=1)).date()}", hl="en-US", gl="US", ceid="US:en")), T)
            baza = (f"Question: {m['vopros']}\nDeadline: {m['konec'].isoformat()}\nNow: {T.isoformat(timespec='minutes')}\nResolution rules: {m['pravila']}\n"
                    "Recent headlines (newest first):\n" + ("\n".join(f"- [{a[:16]}] {s}" for a, s in nov) or "- (none found)"))
            o = kl(SIS, baza); r = str(o.get("reshen", "OPEN")).upper().strip()
            r = r if r in ("YES", "NO") else "OPEN"
        except Exception as e:
            print("  !", m["vopros"][:60], type(e).__name__, str(e)[:80], flush=True); continue
        z = dict(id=m["id"], vopros=m["vopros"], konec=m["konec"].isoformat(), T=T.isoformat(), obem=m["obem"], fee=m["fee"], cena_yes=c,
                 reshen=r, prichina=str(o.get("prichina", ""))[:200], ishod=m["ishod"], novostey=len(nov))
        with OUT.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        n += 1; print(n, m["vopros"][:60], "YES", round(c, 3), "ИИ", r, "исход", m["ishod"], flush=True)
    itog()

def _st(r):
    if len(r) < 3: return dict(n=len(r), sred=round(sum(r) / len(r), 4) if r else None)
    m = sum(r) / len(r); sd = (sum((v - m) ** 2 for v in r) / (len(r) - 1)) ** 0.5
    return dict(n=len(r), sred=round(m, 4), t=round(m / (sd / math.sqrt(len(r))), 2) if sd else None)

def dohod(storona_yes, x):
    cena = min(0.99, (x["cena_yes"] if storona_yes else 1 - x["cena_yes"]) + 0.01)
    vyigral = x["ishod"] == (1 if storona_yes else 0)
    return (1.0 if vyigral else 0.0) / cena - 1 - kom(x["fee"], cena)

def itog():
    L = [json.loads(l) for l in OUT.open()]
    ii = [dohod(x["reshen"] == "YES", x) for x in L if x["reshen"] != "OPEN"]
    oshib = sum(1 for x in L if x["reshen"] != "OPEN" and x["ishod"] != (1 if x["reshen"] == "YES" else 0))
    kontrol_vse = [dohod(x["cena_yes"] >= 0.5, x) for x in L]
    kontrol_te_zhe = [dohod(x["cena_yes"] >= 0.5, x) for x in L if x["reshen"] != "OPEN"]
    sovp = sum(1 for x in L if x["reshen"] != "OPEN" and (x["reshen"] == "YES") == (x["cena_yes"] >= 0.5))
    a, k = _st(ii), _st(kontrol_vse)
    ok = a["n"] >= 30 and (a.get("sred") or 0) > 0 and (a.get("t") or 0) >= 2.0 and (a["sred"] - (k.get("sred") or 0)) >= 0.02
    out = dict(rynkov=len(L), resheno_ii=a["n"], oshibok_ii=oshib, ii_za_favorita=sovp, stavki_ii=a, kontrol_favorit_vse=k,
               kontrol_na_tekh_zhe=_st(kontrol_te_zhe), vyvod="PASS_V_TEN" if ok else "FAIL")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("poly_ishod_reshen_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    itog() if "--itog" in sys.argv else main()
