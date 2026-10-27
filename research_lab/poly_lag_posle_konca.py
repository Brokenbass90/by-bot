#!/usr/bin/env python3
"""poly_lag_posle_konca.py — prereg/PREREG_POLY_LAG_POSLE_KONCA_2026_10_27.md. Mac (сеть, БЕЗ Ollama), ~30–60 мин:
    .venv/bin/python3 research_lab/poly_lag_posle_konca.py > research_lab/data/poly_lag.log 2>&1
    итог:  .venv/bin/python3 research_lab/poly_lag_posle_konca.py --itog        Только чтение Gamma и CLOB prices-history."""
import datetime as dt, hashlib, json, math, re, sys, time, urllib.parse
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import poly_novosti_ollama as P
SHA = "50dfe2a936b19d423460bdd05b241bc0547a5ea7b31cd321b6bf3f9edd794bdf"; N_MAX = 1500; TOCHKI_CH = (1, 6, 24)
OUT = HERE / "data" / "poly_lag_posle_konca.jsonl"
OT, DO = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc), dt.datetime(2026, 10, 26, tzinfo=dt.timezone.utc)
KRIPTO = re.compile(r"\b(bitcoin|ethereum|solana|xrp|btc|eth)\b.*\b(above|below|price|reach|hit)\b", re.I)

def iso(x):
    try: return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00").replace(" ", "T")) if x else None
    except Exception: return None

def rynki():
    out, vid = [], set()
    for off in range(0, 6000, 100):
        evs = None
        for par in (dict(closed="true", limit=100, offset=off, end_date_min="2026-08-01", end_date_max="2026-10-26"),
                    dict(closed="true", limit=100, offset=off, order="endDate", ascending="false")):
            try: evs = P.get_json(f"{P.GAMMA}/events?" + urllib.parse.urlencode(par)) or []; break
            except Exception as e: print("  Gamma отказ:", str(e)[:60], flush=True)
        if not evs: break
        for e in evs:
            teg = [str(t.get("slug") or t.get("label") or "") for t in (e.get("tags") or [])]
            for m in e.get("markets") or []:
                if m.get("id") in vid: continue
                outc, toks, pr = P.js(m.get("outcomes")) or [], P.js(m.get("clobTokenIds")) or [], P.js(m.get("outcomePrices")) or []
                if len(outc) != 2 or len(toks) != 2 or {str(x) for x in pr} != {"1", "0"}: continue
                q = m.get("question") or ""
                if KRIPTO.search(q): continue
                kon, ras = iso(m.get("endDate")), iso(m.get("closedTime")) or iso(m.get("umaEndDate"))
                try: obem = float(m.get("volume") or 0)
                except Exception: continue
                if not kon or not (OT <= kon <= DO) or obem < P.MIN_OBEM: continue
                vid.add(m.get("id"))
                out.append(dict(id=m.get("id"), vopros=q, konec=kon, raschet=ras, obem=obem, token=toks[0], fee=P.fee_rate(teg),
                                tema=",".join(teg)[:80], ishod=1 if str(pr[0]) == "1" else 0))
        time.sleep(0.25)
    out.sort(key=lambda x: -x["obem"]); return out

def ceny(token, kon):
    h = P.get_json(f"{P.CLOB}/prices-history?" + urllib.parse.urlencode(dict(market=token, startTs=int(kon.timestamp()), endTs=int(kon.timestamp()) + 30 * 3600, fidelity=60)))
    pts = sorted((x["t"], float(x["p"])) for x in (h or {}).get("history", []))
    res = {}
    for c in TOCHKI_CH:
        t = kon.timestamp() + c * 3600; p = next((p for tt, p in pts if tt >= t), None); res[str(c)] = p
    return res

def main():
    if hashlib.sha256((HERE / "prereg/PREREG_POLY_LAG_POSLE_KONCA_2026_10_27.md").read_bytes()).hexdigest() != SHA: sys.exit("prereg изменён")
    uzhe = {json.loads(l)["id"] for l in OUT.open()} if OUT.exists() else set()
    ryn = rynki(); print("рынков подходит:", len(ryn), flush=True); n = len(uzhe)
    for m in ryn:
        if n >= N_MAX: break
        if m["id"] in uzhe: continue
        try: c = ceny(m["token"], m["konec"]); time.sleep(0.15)
        except Exception as e: print("  !", m["vopros"][:50], str(e)[:60], flush=True); continue
        z = dict(m, konec=m["konec"].isoformat(), raschet=m["raschet"].isoformat() if m["raschet"] else None, ceny_yes=c)
        with OUT.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        n += 1
        if n % 25 == 0: print(n, m["vopros"][:50], c, "исход", m["ishod"], flush=True)
    itog()

def itog():
    L = [json.loads(l) for l in OUT.open()]; out = dict(rynkov=len(L))
    for c in TOCHKI_CH:
        r, proigr, uderzh = [], 0, []
        for x in L:
            y = x["ceny_yes"].get(str(c))
            if y is None: continue
            yes = y >= 0.5; p = y if yes else 1 - y
            if not 0.90 <= p < 0.99: continue
            cena = min(0.995, p + 0.005); win = x["ishod"] == (1 if yes else 0)
            r.append((1.0 if win else 0.0) / cena - 1 - x["fee"] * (1 - cena)); proigr += 0 if win else 1
            if x.get("raschet"):
                h = (dt.datetime.fromisoformat(x["raschet"]) - dt.datetime.fromisoformat(x["konec"])).total_seconds() / 86400 - c / 24
                if h > 0: uderzh.append(h)
        if len(r) < 3: out[f"plus_{c}ch"] = dict(n=len(r)); continue
        m = sum(r) / len(r); sd = (sum((v - m) ** 2 for v in r) / (len(r) - 1)) ** 0.5
        ud = sorted(uderzh); med = ud[len(ud) // 2] if ud else None
        out[f"plus_{c}ch"] = dict(n=len(r), sred=round(m, 4), t=round(m / (sd / math.sqrt(len(r))), 2) if sd else None, proigryshey=proigr,
                                  dolya_proigr=round(proigr / len(r), 4), uderzh_med_dney=round(med, 2) if med else None,
                                  dohod_v_sutki=round(m / med, 4) if med else None)
    a = out.get("plus_1ch", {})
    out["vyvod"] = "PASS_V_TEN" if a.get("n", 0) >= 50 and (a.get("sred") or 0) > 0 and (a.get("t") or 0) >= 2 and a.get("dolya_proigr", 1) <= 0.01 else "FAIL"
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / "results" / time.strftime("poly_lag_posle_konca_%Y%m%dT%H%MZ.json", time.gmtime())).write_text(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    itog() if "--itog" in sys.argv else main()
