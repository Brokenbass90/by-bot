#!/usr/bin/env python3
"""poly_sbor.py — сборщик Polymarket. ТОЛЬКО ЧТЕНИЕ: без ключей, без кошелька, без ордеров.

Публичные адреса:
  gamma-api.polymarket.com  — каталог событий и рынков (метаданные)
  clob.polymarket.com       — история цен (/prices-history), стакан (/book)
  data-api.polymarket.com   — открытый интерес (/oi)

Точка во времени (без заглядывания вперёд):
  * каждый снимок каталога пишется с временем получения (polucheno_ms);
  * история цен — ряд (t, p), t = время сделки/котировки; в признаках берётся только t < дня решения;
  * рынок участвует в признаке только после своей даты старта и до закрытия;
  * стакан истории не имеет — он копится ВПЕРЁД режимом --snimki.

Команды (запускать на Mac, в VM нет сети):
  python3 poly_sbor.py --proverka          пара запросов, показать поля (сначала это)
  python3 poly_sbor.py --katalog           снимок каталога рынков (активные и закрытые)
  python3 poly_sbor.py --istoriya          история цен по рынкам из маппинга (poly_map.json)
  python3 poly_sbor.py --snimki [минут]    бесконечно: стакан+цена+OI по отслеживаемым рынкам, раз в N минут (15)
Данные: research_lab/data/poly/
"""
from __future__ import annotations
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
OUT = LAB / "data/poly"
MAP = Path(__file__).resolve().parent / "poly_map.json"
GAMMA, CLOB, DATA = "https://gamma-api.polymarket.com", "https://clob.polymarket.com", "https://data-api.polymarket.com"
PAUZA = 0.25


def get(base, path, **q):
    url = f"{base}{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    for popytka in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-readonly/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except Exception as e:
            if popytka == 3:
                print(f"  ! {path}: {e}"); return None
            time.sleep(2 * (popytka + 1))


def js(x):
    """в Gamma outcomes/outcomePrices/clobTokenIds — JSON внутри строки"""
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return None
    return x


def sejchas():
    return int(time.time() * 1000)


def zagruzit_map():
    return json.loads(MAP.read_text())


def kategoriya(m, pravila):
    tekst = " ".join(str(m.get(k) or "") for k in ("question", "slug", "description", "groupItemTitle")).lower()
    for kat, pr in pravila.items():
        if any(re.search(p, tekst) for p in pr["iskat"]) and not any(re.search(p, tekst) for p in pr.get("isklyuchit", [])):
            return kat
    return None


def proverka():
    m = get(GAMMA, "/markets", limit=2, closed="false")
    print("gamma /markets поля:", sorted((m or [{}])[0].keys())[:60] if m else m)
    if m:
        tok = (js(m[0].get("clobTokenIds")) or [None])[0]
        print("clobTokenIds[0]:", tok)
        h = get(CLOB, "/prices-history", market=tok, interval="max", fidelity=60)
        print("prices-history ключи:", list((h or {}).keys()), "точек:", len((h or {}).get("history", [])))
        b = get(CLOB, "/book", token_id=tok)
        print("book ключи:", list((b or {}).keys()))
        oi = get(DATA, "/oi", market=m[0].get("conditionId"))
        print("oi:", str(oi)[:200])
    e = get(GAMMA, "/events", limit=1, closed="true")
    print("gamma /events поля:", sorted((e or [{}])[0].keys())[:60] if e else e)


def katalog():
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = sejchas(); vse = []
    for closed in ("false", "true"):
        off = 0
        while True:
            r = get(GAMMA, "/markets", limit=500, offset=off, closed=closed, order="id", ascending="true")
            if not r:
                break
            vse += r; off += len(r)
            print(f"  closed={closed}: {off}", flush=True)
            if len(r) < 500:
                break
            time.sleep(PAUZA)
    put = OUT / f"katalog_{time.strftime('%Y%m%d_%H%M', time.gmtime())}.jsonl"
    with put.open("w") as f:
        for m in vse:
            f.write(json.dumps({"polucheno_ms": t0, **m}, ensure_ascii=False) + "\n")
    print(f"каталог: {len(vse)} рынков → {put.name}")
    return put


def posledniy_katalog():
    k = sorted(OUT.glob("katalog_*.jsonl"))
    if not k:
        raise SystemExit("нет каталога: сначала --katalog")
    return [json.loads(s) for s in k[-1].read_text().splitlines() if s.strip()]


def otobrannye(katalog, pravila, min_obem):
    out = []
    for m in katalog:
        kat = kategoriya(m, pravila)
        if not kat:
            continue
        try:
            obem = float(m.get("volume") or m.get("volumeNum") or 0)
        except Exception:
            obem = 0.0
        if obem < min_obem:
            continue
        toks = js(m.get("clobTokenIds")) or []; outc = js(m.get("outcomes")) or []
        if not toks:
            continue
        yes = next((t for t, o in zip(toks, outc) if str(o).lower() == "yes"), toks[0])
        out.append({"conditionId": m.get("conditionId"), "id": m.get("id"), "kat": kat, "token": yes,
                    "vopros": m.get("question"), "start": m.get("startDate") or m.get("createdAt"),
                    "konec": m.get("endDate"), "closed": m.get("closed"), "obem": obem})
    return out


def istoriya():
    mp = zagruzit_map(); kat = posledniy_katalog()
    sel = otobrannye(kat, mp["kategorii"], mp.get("min_obem_usd", 100000))
    d = OUT / "istoriya"; d.mkdir(parents=True, exist_ok=True)
    print(f"рынков по маппингу: {len(sel)}")
    for i, s in enumerate(sel, 1):
        p = d / f"{s['conditionId']}.json"
        if p.exists() and s["closed"]:
            continue                                   # закрытый рынок не меняется
        h = get(CLOB, "/prices-history", market=s["token"], interval="max", fidelity=60)
        ryad = [(int(x["t"]), float(x["p"])) for x in (h or {}).get("history", [])]
        tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps({**s, "polucheno_ms": sejchas(), "ryad": ryad}))
        tmp.replace(p)
        if i % 25 == 0 or i == len(sel):
            print(f"  {i}/{len(sel)} {s['kat']:<14} точек {len(ryad):>5}  {str(s['vopros'])[:60]}", flush=True)
        time.sleep(PAUZA)


def snimki(minut=15):
    mp = zagruzit_map()
    d = OUT / "snimki"; d.mkdir(parents=True, exist_ok=True)
    print(f"снимки раз в {minut} мин. Ctrl+C — стоп. Автозапуска нет: это обычный процесс в терминале.", flush=True)
    kat, kat_vremya = None, 0
    while True:
        if kat is None or time.time() - kat_vremya > 6 * 3600:     # обновлять список активных раз в 6 ч
            kat = [m for m in (get(GAMMA, "/markets", limit=500, closed="false", order="volume", ascending="false") or [])]
            kat_vremya = time.time()
        sel = [s for s in otobrannye(kat, mp["kategorii"], mp.get("min_obem_usd", 100000)) if not s["closed"]]
        t = sejchas(); zapisi = []
        for s in sel:
            b = get(CLOB, "/book", token_id=s["token"]) or {}
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)[:10]
            asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))[:10]
            oi = get(DATA, "/oi", market=s["conditionId"])
            zapisi.append({"t": t, "conditionId": s["conditionId"], "kat": s["kat"], "bids": bids, "asks": asks,
                           "oi": oi if not isinstance(oi, list) else (oi[0] if oi else None)})
            time.sleep(PAUZA)
        with (d / time.strftime("%Y-%m-%d.jsonl", time.gmtime())).open("a") as f:
            for z in zapisi:
                f.write(json.dumps(z) + "\n")
        print(f"  {time.strftime('%H:%M', time.gmtime())} UTC снимков {len(zapisi)}", flush=True)
        time.sleep(max(60, minut * 60 - (sejchas() - t) / 1000))


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--proverka" in a: proverka()
    elif "--katalog" in a: katalog()
    elif "--istoriya" in a: istoriya()
    elif "--snimki" in a:
        i = a.index("--snimki"); snimki(int(a[i + 1]) if len(a) > i + 1 and a[i + 1].isdigit() else 15)
    else: print(__doc__)
