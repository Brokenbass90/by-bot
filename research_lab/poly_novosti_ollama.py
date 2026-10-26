#!/usr/bin/env python3
"""Тень POLY_NOVOSTI_OLLAMA (prereg PREREG_POLY_NOVOSTI_OLLAMA_2026_10_26, e14562a). Только чтение: Gamma, CLOB /book,
Google News RSS, локальная Ollama. Без аргументов: prognoz, затем sudya (так вызывает ocenshchiki_ezhednevno).
  python3 research_lab/poly_novosti_ollama.py [prognoz|sudya|proba]"""
import datetime as dt, email.utils, hashlib, json, math, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
D = LAB / "data" / "poly_ollama"; ZH = D / "prognozy.jsonl"; SUD = D / "sudya.json"
GAMMA, CLOB, OLL = "https://gamma-api.polymarket.com", "https://clob.polymarket.com", "http://localhost:11434"
MAKS_V_DEN, MIN_OBEM, DNI = 15, 50_000, (3, 30)
ISKL = re.compile(r"\b(bitcoin|ethereum|solana|xrp|btc|eth|crypto|nfl|nba|mlb|nhl|soccer|football|tennis|ufc|match|vs\.?|o/u|spread)\b", re.I)
SISTEMA = ("You are a careful forecaster. Given a prediction-market question, its exact resolution rules, the deadline and recent "
           "dated news headlines, estimate the probability that the market resolves YES. Use only the information given and base rates. "
           'Answer JSON only: {"p_yes": <number 0..1>, "prichina": "<one short sentence>"}')


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def js(x):
    if isinstance(x, str):
        try: return json.loads(x)
        except Exception: return None
    return x


def fee_rate(teg):
    s = " ".join(teg).lower()
    if "geopolitic" in s: return 0.0
    if "politic" in s or "election" in s: return 0.04
    return 0.05


def otbor(seychas, gamma=get_json):
    out = []
    for off in range(0, 500, 100):
        evs = gamma(f"{GAMMA}/events?" + urllib.parse.urlencode(dict(active="true", closed="false", limit=100, offset=off,
                                                                         order="volume", ascending="false"))) or []
        for e in evs:
            teg = [str(t.get("slug") or t.get("label") or "") for t in (e.get("tags") or [])]
            if any(re.search(r"crypto|sport", t, re.I) for t in teg): continue
            for m in e.get("markets") or []:
                if m.get("closed") or not m.get("active", True): continue
                outc, toks, pr = js(m.get("outcomes")) or [], js(m.get("clobTokenIds")) or [], js(m.get("outcomePrices")) or []
                if [str(o).lower() for o in outc] != ["yes", "no"] or len(toks) != 2: continue
                q = m.get("question") or ""
                if ISKL.search(q): continue
                try:
                    kon = dt.datetime.fromisoformat((m.get("endDate") or "").replace("Z", "+00:00"))
                    obem = float(m.get("volume") or 0); mid = float(pr[0])
                except Exception: continue
                dn = (kon - seychas).total_seconds() / 86400
                if not (DNI[0] <= dn <= DNI[1]) or obem < MIN_OBEM or not 0.05 <= mid <= 0.95: continue
                out.append(dict(cid=m.get("conditionId"), mid_id=m.get("id"), vopros=q, pravila=(m.get("description") or "")[:1500],
                                konec=kon.isoformat(), obem=obem, token_yes=toks[0], tegi=teg, fee=fee_rate(teg)))
        if not evs: break
        time.sleep(0.25)
    out.sort(key=lambda x: -x["obem"])
    return out


def novosti(vopros, seychas, fetch=None):
    q = re.sub(r"^(will|is|does|did|has|have|are)\s+", "", vopros.strip(), flags=re.I).rstrip("?")[:120]
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(dict(q=q + " when:7d", hl="en-US", gl="US", ceid="US:en"))
    raw = fetch(url) if fetch else urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
    out = []
    for it in ET.fromstring(raw).iter("item"):
        try: t = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except Exception: continue
        if t <= seychas: out.append((t, it.findtext("title") or ""))
    out.sort(reverse=True)
    return [(t.isoformat(), s[:200]) for t, s in out[:10]]


def stakan(token, book=None):
    b = book(token) if book else get_json(f"{CLOB}/book?token_id={token}")
    bids = sorted((float(x["price"]) for x in b.get("bids") or []), reverse=True)
    asks = sorted(float(x["price"]) for x in b.get("asks") or [])
    return (bids[0] if bids else None), (asks[0] if asks else None)


def model_dostupna():
    try:
        im = {m["name"] for m in get_json(f"{OLL}/api/tags", 5).get("models", [])}
    except Exception:
        return None
    for m in ("qwen3:8b", "qwen3:4b"):
        if m in im: return m
    return None


def klient(model):
    from factory_v3.ai_kontrakt_v1 import klient_ollama
    return klient_ollama(model, OLL, opcii=dict(num_ctx=4096, num_predict=200, temperature=0.3), timeout_s=180)


def prognoz(seychas=None, gamma=get_json, fetch=None, book=None, kl=None):
    seychas = seychas or dt.datetime.now(dt.timezone.utc)
    D.mkdir(parents=True, exist_ok=True)
    uzhe = {json.loads(l)["cid"] for l in ZH.open()} if ZH.exists() else set()
    model = getattr(kl, "model", None) if kl else model_dostupna()
    if model is None: return {"status": "OLLAMA_NEDOSTUPNA"}
    kl = kl or klient(model)
    sdelano = 0
    for m in otbor(seychas, gamma):
        if sdelano >= MAKS_V_DEN: break
        if m["cid"] in uzhe: continue
        try:
            nov = novosti(m["vopros"], seychas, fetch)
            zapros = (f"Question: {m['vopros']}\nDeadline: {m['konec']}\nNow: {seychas.isoformat(timespec='minutes')}\n"
                      f"Resolution rules: {m['pravila']}\nRecent headlines (newest first):\n" +
                      ("\n".join(f"- [{t[:16]}] {s}" for t, s in nov) or "- (none found)"))
            otv = kl(SISTEMA, zapros); p = float(otv.get("p_yes"))
            if not 0 <= p <= 1: raise ValueError("p_yes вне 0..1")
            bid, ask = stakan(m["token_yes"], book)
        except Exception as e:
            print("  !", m["vopros"][:60], type(e).__name__, str(e)[:100]); continue
        z = dict(kogda=seychas.isoformat(timespec="seconds"), model=model, cid=m["cid"], market_id=m["mid_id"], vopros=m["vopros"],
                 konec=m["konec"], obem=m["obem"], fee=m["fee"], tegi=m["tegi"], novostey=len(nov), novosti=nov,
                 p_model=round(p, 4), prichina=str(otv.get("prichina", ""))[:300], bid=bid, ask=ask,
                 mid=round((bid + ask) / 2, 4) if bid is not None and ask is not None else None)
        z["sha256"] = hashlib.sha256(json.dumps(z, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with ZH.open("a") as fh: fh.write(json.dumps(z, ensure_ascii=False) + "\n")
        uzhe.add(m["cid"]); sdelano += 1
    return {"status": "OK", "model": model, "novyh_prognozov": sdelano, "vsego": len(uzhe)}


def ishod(market_id, gamma=get_json):
    m = gamma(f"{GAMMA}/markets/{market_id}") or {}
    if not m.get("closed"): return None
    pr = js(m.get("outcomePrices")) or []
    try: y = float(pr[0])
    except Exception: return None
    return 1.0 if y > 0.99 else (0.0 if y < 0.01 else None)


def sudya(gamma=get_json, seychas=None):
    seychas = seychas or dt.datetime.now(dt.timezone.utc)
    if not ZH.exists(): return {"status": "NET_PROGNOZOV"}
    Z = [json.loads(l) for l in ZH.open()]
    sost = json.loads(SUD.read_text()) if SUD.exists() else {"ishody": {}}
    for z in Z:
        if z["cid"] in sost["ishody"] or z.get("mid") is None: continue
        if dt.datetime.fromisoformat(z["konec"]) > seychas: continue
        try: y = ishod(z["market_id"], gamma)
        except Exception: y = None
        if y is not None: sost["ishody"][z["cid"]] = y
    R = [z for z in Z if z["cid"] in sost["ishody"] and z.get("mid") is not None]
    n = len(R); sost["razresheno"] = n; sost["prognozov"] = len(Z)
    if n:
        bm = [(z["mid"] - sost["ishody"][z["cid"]]) ** 2 for z in R]
        bs = [((0.5 * z["p_model"] + 0.5 * z["mid"]) - sost["ishody"][z["cid"]]) ** 2 for z in R]
        bo = [(z["p_model"] - sost["ishody"][z["cid"]]) ** 2 for z in R]
        sost["brier"] = {"rynok": round(sum(bm) / n, 4), "smes": round(sum(bs) / n, 4), "model": round(sum(bo) / n, 4)}
        po = {}
        for z, a, b in zip(R, bm, bs): po.setdefault(z["konec"][:10], []).append(a - b)
        dm = [sum(v) / len(v) for v in po.values()]
        if len(dm) > 2:
            m_ = sum(dm) / len(dm); sd = math.sqrt(sum((x - m_) ** 2 for x in dm) / (len(dm) - 1))
            sost["t_raznicy_po_datam"] = round(m_ / (sd / math.sqrt(len(dm))), 2) if sd > 0 else None
        pnl = []
        for z in R:
            y = sost["ishody"][z["cid"]]; s = 0.5 * z["p_model"] + 0.5 * z["mid"]; f = z["fee"]
            if z["ask"] and s - z["ask"] > f * z["ask"] * (1 - z["ask"]):
                c = z["ask"]; sh = 10 / c; pnl.append(sh * (y - c - f * c * (1 - c)))
            elif z["bid"] and (1 - s) - (1 - z["bid"]) > f * z["bid"] * (1 - z["bid"]):
                c = 1 - z["bid"]; sh = 10 / c; pnl.append(sh * ((1 - y) - c - f * c * (1 - c)))
        sost["ekonomika"] = {"sdelok": len(pnl), "itogo_usd": round(sum(pnl), 2), "sred_usd": round(sum(pnl) / len(pnl), 3) if pnl else None}
        t = sost.get("t_raznicy_po_datam")
        if n < 50: sost["verdikt"] = "INCONCLUSIVE_MALO"
        elif t is not None and t >= 2 and sum(pnl) > 0: sost["verdikt"] = "PASS"
        elif (t is not None and t <= -2) or (n >= 150 and (t is None or t < 2)): sost["verdikt"] = "FAIL"
        else: sost["verdikt"] = "INCONCLUSIVE"
    D.mkdir(parents=True, exist_ok=True); SUD.write_text(json.dumps(sost, ensure_ascii=False, indent=1))
    return {k: v for k, v in sost.items() if k != "ishody"}


if __name__ == "__main__":
    rezh = sys.argv[1] if len(sys.argv) > 1 else "oba"
    if rezh == "proba":
        s = dt.datetime.now(dt.timezone.utc); M = otbor(s)
        print(len(M), "рынков прошли отбор; первые:"); [print(" ", round(m["obem"]), m["konec"][:10], m["fee"], m["vopros"][:90]) for m in M[:15]]
        if M: print("новости:", novosti(M[0]["vopros"], s)[:3]); print("модель:", model_dostupna())
    else:
        if rezh in ("oba", "prognoz"): print(json.dumps(prognoz(), ensure_ascii=False))
        if rezh in ("oba", "sudya"): print(json.dumps(sudya(), ensure_ascii=False))
