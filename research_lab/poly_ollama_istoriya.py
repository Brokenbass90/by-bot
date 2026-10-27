#!/usr/bin/env python3
"""poly_ollama_istoriya.py — prereg/PREREG_POLY_OLLAMA_ISTORIYA_2026_10_27.md. Mac (сеть + локальная Ollama), ~1 ч:
    .venv/bin/python3 research_lab/poly_ollama_istoriya.py         (можно в фоне: nohup ... > /tmp/poly_ist.log 2>&1 &)"""
import datetime as dt, hashlib, json, math, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import poly_novosti_ollama as P
SHA = "777b022e584bddf66e57a9dba8e452d6b7dc20f95e5c270024e00bbe0c990595"; N_MAX = 120; DNI_DO = 3
OUT = HERE / "data" / "poly_ollama_istoriya.jsonl"
SIS_B = ("You are a careful forecaster. You are given a prediction-market question, its rules, the CURRENT MARKET PRICE of YES (the crowd's "
         "probability) and dated headlines. Start from the market price. Change it ONLY if a specific dated headline gives concrete new information "
         "the market may not have priced; otherwise return the market price unchanged. "
         'Answer JSON only: {"p_yes": <number 0..1>, "prichina": "<one short sentence>"}')

def zakrytye():
    out = []
    for off in range(0, 3000, 100):
        evs = P.get_json(f"{P.GAMMA}/events?" + urllib.parse.urlencode(dict(closed="true", limit=100, offset=off, order="volume", ascending="false",
                                                                          end_date_min="2026-08-01T00:00:00Z", end_date_max="2026-10-26T00:00:00Z"))) or []
        if not evs: break
        for e in evs:
            teg = [str(t.get("slug") or t.get("label") or "") for t in (e.get("tags") or [])]
            if any(re.search(r"crypto|sport", t, re.I) for t in teg): continue
            for m in e.get("markets") or []:
                outc, toks, pr = P.js(m.get("outcomes")) or [], P.js(m.get("clobTokenIds")) or [], P.js(m.get("outcomePrices")) or []
                if [str(o).lower() for o in outc] != ["yes", "no"] or len(toks) != 2 or len(pr) != 2: continue
                q = m.get("question") or ""
                if P.ISKL.search(q): continue
                try: kon = dt.datetime.fromisoformat((m.get("endDate") or "").replace("Z", "+00:00")); obem = float(m.get("volume") or 0)
                except Exception: continue
                if obem < P.MIN_OBEM or {str(x) for x in pr} not in ({"1", "0"},): continue
                out.append(dict(id=m.get("id"), vopros=q, pravila=(m.get("description") or "")[:1500], konec=kon, obem=obem, token=toks[0],
                                fee=P.fee_rate(teg), ishod=1 if str(pr[0]) == "1" else 0))
        time.sleep(0.25)
    out.sort(key=lambda x: -x["obem"]); return out

def cena_do(token, t):
    h = P.get_json(f"{P.CLOB}/prices-history?" + urllib.parse.urlencode(dict(market=token, startTs=int(t.timestamp()) - 3 * 86400, endTs=int(t.timestamp()), fidelity=60)))
    pts = [x for x in (h or {}).get("history", []) if x.get("t", 0) <= t.timestamp()]
    return float(pts[-1]["p"]) if pts else None

def novosti_do(vopros, t):
    q = re.sub(r"^(will|is|does|did|has|have|are)\s+", "", vopros.strip(), flags=re.I).rstrip("?")[:110]
    q += f" after:{(t - dt.timedelta(days=7)).date()} before:{t.date()}"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(dict(q=q, hl="en-US", gl="US", ceid="US:en"))
    try: return P.novosti.__wrapped__(q, t) if hasattr(P.novosti, "__wrapped__") else _rss(url, t)
    except Exception: return []

def _rss(url, t):
    import email.utils, xml.etree.ElementTree as ET
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read(); out = []
    for it in ET.fromstring(raw).iter("item"):
        try: d = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception: continue
        if d <= t: out.append((d, it.findtext("title") or ""))
    out.sort(reverse=True); return [(d.isoformat(), s[:200]) for d, s in out[:10]]

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_POLY_OLLAMA_ISTORIYA_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    model = P.model_dostupna()
    if not model: sys.exit("Ollama недоступна (ollama serve / модель qwen3:8b)")
    kl = P.klient(model); uzhe = {json.loads(l)["id"] for l in OUT.open()} if OUT.exists() else set()
    ryn = zakrytye(); print("закрытых рынков подходит:", len(ryn), flush=True); n = len(uzhe)
    for m in ryn:
        if n >= N_MAX: break
        if m["id"] in uzhe: continue
        T = m["konec"] - dt.timedelta(days=DNI_DO)
        try:
            c = cena_do(m["token"], T)
            if c is None or not 0.03 <= c <= 0.97: continue
            nov = _rss("https://news.google.com/rss/search?" + urllib.parse.urlencode(dict(q=re.sub(r"^(will|is|does|did|has|have|are)\s+", "", m["vopros"].strip(), flags=re.I).rstrip("?")[:110] + f" after:{(T - dt.timedelta(days=7)).date()} before:{T.date()}", hl="en-US", gl="US", ceid="US:en")), T)
            baza = (f"Question: {m['vopros']}\nDeadline: {m['konec'].isoformat()}\nNow: {T.isoformat(timespec='minutes')}\nResolution rules: {m['pravila']}\n"
                    "Recent headlines (newest first):\n" + ("\n".join(f"- [{a[:16]}] {s}" for a, s in nov) or "- (none found)"))
            pa = float(kl(P.SISTEMA, baza).get("p_yes"))
            pb = float(kl(SIS_B, baza + f"\nCurrent market price of YES: {c:.3f}").get("p_yes"))
        except Exception as e:
            print("  !", m["vopros"][:60], type(e).__name__, str(e)[:80], flush=True); continue
        z = dict(id=m["id"], vopros=m["vopros"], konec=m["konec"].isoformat(), obem=m["obem"], fee=m["fee"], cena=c, p_A=pa, p_B=pb, ishod=m["ishod"], novostey=len(nov))
        with OUT.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        n += 1; print(n, m["vopros"][:60], "рынок", round(c, 3), "A", pa, "B", pb, "исход", m["ishod"], flush=True)
    itog()

def itog():
    L = [json.loads(l) for l in OUT.open()]
    br = lambda k: sum((x[k] - x["ishod"]) ** 2 for x in L) / len(L)
    def stavki(k):
        r = []
        for x in L:
            p, c = x[k], x["cena"]
            if abs(p - c) <= x["fee"] + 0.05: continue
            if p > c: cena = min(0.99, c + 0.01); r.append((x["ishod"] - cena) / cena - x["fee"])
            else: cena = min(0.99, 1 - c + 0.01); r.append(((1 - x["ishod"]) - cena) / cena - x["fee"])
        if len(r) < 3: return dict(n=len(r))
        m = sum(r) / len(r); sd = (sum((v - m) ** 2 for v in r) / (len(r) - 1)) ** 0.5
        return dict(n=len(r), sred_na_1=round(m, 3), t=round(m / (sd / math.sqrt(len(r))), 2) if sd else None)
    out = dict(rynkov=len(L), brier_rynok=round(br("cena"), 4), brier_A=round(br("p_A"), 4), brier_B=round(br("p_B"), 4),
               stavki_A=stavki("p_A"), stavki_B=stavki("p_B"), dolya_A_045=round(sum(1 for x in L if x["p_A"] == 0.45) / len(L), 2))
    sB = out["stavki_B"]; out["vyvod"] = "POLEZNA" if (out["brier_B"] < out["brier_rynok"] and sB.get("n", 0) >= 30 and (sB.get("sred_na_1") or 0) > 0 and (sB.get("t") or 0) >= 2) else "NE_DOKAZANO"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("poly_ollama_istoriya_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    itog() if "--itog" in sys.argv else main()
