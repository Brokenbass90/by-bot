#!/usr/bin/env python3
"""poly_monitor_minuty.py — живой монитор Polymarket (27.10.2026, Claude; Polymarket ступень 2–3). Только чтение, ордеров и ключей нет.
Зачем: на часовой истории окна «исход решён, цена нет» нет (poly_lag_posle_konca: FAIL). Если окно есть — оно в минутах.
Пишем поминутно стакан и новости по рынкам у конца, потом считаем: момент первой решающей новости → когда и по какой цене
можно было купить победившую сторону (ask, глубина).
Рынки (обновление раз в 30 мин): активные бинарные, не крипто-страйки, оборот ≥ $50 000, конец в окне [сейчас − 48 ч, сейчас + 72 ч], ≤ 60.
Каждую минуту: /book YES — лучший bid/ask и глубина в 2 ¢; пишется при изменении и раз в 15 мин. Раз в 10 мин — Google News RSS по вопросу
(новые заголовки с pubDate и временем, когда мы их увидели). Закрытие рынка и исход — из Gamma.
Запуск ТОЛЬКО вручную в screen (без автозапуска):
    screen -S polymon .venv/bin/python3 research_lab/poly_monitor_minuty.py      (выйти: Ctrl-A D; остановить: Ctrl-C)
Выход: data/poly_monitor/{knigi,novosti,rynki}.jsonl."""
import datetime as dt, json, re, sys, time, urllib.parse
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import poly_novosti_ollama as P, poly_ollama_istoriya as I
OUT = HERE / "data" / "poly_monitor"; OUT.mkdir(parents=True, exist_ok=True)
KN, NV, RY = OUT / "knigi.jsonl", OUT / "novosti.jsonl", OUT / "rynki.jsonl"
KRIPTO = re.compile(r"\b(bitcoin|ethereum|solana|xrp|btc|eth)\b.*\b(above|below|price|reach|hit)\b", re.I)
MAKS_RYNKOV, MIN_OBEM = 60, 50_000

def pis(p, z):
    with p.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")

def iso(x):
    try: return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")) if x else None
    except Exception: return None

def spisok(seychas):
    out = []
    for off in range(0, 1000, 100):
        try: evs = P.get_json(f"{P.GAMMA}/events?" + urllib.parse.urlencode(dict(active="true", closed="false", limit=100, offset=off, order="volume", ascending="false"))) or []
        except Exception: break
        if not evs: break
        for e in evs:
            for m in e.get("markets") or []:
                outc, toks = P.js(m.get("outcomes")) or [], P.js(m.get("clobTokenIds")) or []
                if len(outc) != 2 or len(toks) != 2 or m.get("closed"): continue
                q = m.get("question") or ""; kon = iso(m.get("endDate"))
                try: obem = float(m.get("volume") or 0)
                except Exception: continue
                if KRIPTO.search(q) or not kon or obem < MIN_OBEM: continue
                if not (seychas - dt.timedelta(hours=48) <= kon <= seychas + dt.timedelta(hours=72)): continue
                out.append(dict(id=m.get("id"), cid=m.get("conditionId"), vopros=q, konec=kon.isoformat(), obem=obem, token=toks[0]))
    out.sort(key=lambda x: -x["obem"]); return out[:MAKS_RYNKOV]

def kniga(token):
    b = P.get_json(f"{P.CLOB}/book?token_id={token}", timeout=10)
    bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids") or []), reverse=True)
    asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks") or [])
    bb, ba = (bids[0][0] if bids else None), (asks[0][0] if asks else None)
    gb = round(sum(p * s for p, s in bids if bb and p >= bb - 0.02), 2); ga = round(sum(p * s for p, s in asks if ba and p <= ba + 0.02), 2)
    return bb, ba, gb, ga

def main():
    ryn, t_spiska, t_nov, vid_nov, prosh, t_hb = [], 0, 0, set(), {}, {}
    if NV.exists():
        for l in NV.open(): vid_nov.add(json.loads(l)["kl"])
    while True:
        seychas = dt.datetime.now(dt.timezone.utc); ts = seychas.timestamp()
        if ts - t_spiska > 1800:
            novye = spisok(seychas); stare = {m["id"] for m in ryn}
            for m in novye:
                if m["id"] not in stare: pis(RY, dict(sob="dobavlen", t=seychas.isoformat(timespec="seconds"), **m))
            for m in ryn:
                if m["id"] not in {x["id"] for x in novye}:
                    try:
                        g = P.get_json(f"{P.GAMMA}/markets/{m['id']}")
                        pis(RY, dict(sob="vybyl", t=seychas.isoformat(timespec="seconds"), id=m["id"], closed=g.get("closed"),
                                     outcomePrices=g.get("outcomePrices"), umaResolutionStatus=g.get("umaResolutionStatus"), closedTime=g.get("closedTime")))
                    except Exception: pass
            ryn, t_spiska = novye, ts
            print(seychas.isoformat(timespec="minutes"), "рынков:", len(ryn), flush=True)
        for m in ryn:
            try: bb, ba, gb, ga = kniga(m["token"])
            except Exception: continue
            k = (bb, ba)
            if prosh.get(m["id"]) != k or ts - t_hb.get(m["id"], 0) > 900:
                pis(KN, dict(id=m["id"], t=int(ts), bid=bb, ask=ba, gl_bid=gb, gl_ask=ga)); prosh[m["id"]] = k; t_hb[m["id"]] = ts
            time.sleep(0.3)
        if ts - t_nov > 600:
            for m in ryn:
                q = re.sub(r"^(will|is|does|did|has|have|are)\s+", "", m["vopros"].strip(), flags=re.I).rstrip("?")[:110]
                try: nov = I._rss("https://news.google.com/rss/search?" + urllib.parse.urlencode(dict(q=q + " when:2d", hl="en-US", gl="US", ceid="US:en")), seychas)
                except Exception: continue
                for d, s in nov:
                    kl = f'{m["id"]}|{s}'
                    if kl in vid_nov: continue
                    vid_nov.add(kl); pis(NV, dict(kl=kl, id=m["id"], pub=d, uvideli=seychas.isoformat(timespec="seconds"), zagolovok=s))
                time.sleep(0.5)
            t_nov = ts
        time.sleep(max(1, 60 - (time.time() - ts)))

if __name__ == "__main__":
    main()
