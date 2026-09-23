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
  python3 poly_sbor.py --proverka_rynkov  событие → рынок → токен ДА → точки, на ~10 рынках (до --istoriya)
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


def _sek(s):
    import datetime as _dt
    if not s:
        return None
    try:
        return int(_dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def sejchas():
    return int(time.time() * 1000)


def zagruzit_map():
    return json.loads(MAP.read_text())


def tekst_rynka(m):
    chasti = [str(m.get(k) or "") for k in ("question", "slug", "groupItemTitle")]
    for e in (js(m.get("events")) or []):
        if isinstance(e, dict):
            chasti += [str(e.get(k) or "") for k in ("title", "slug", "seriesSlug", "ticker")]
            for t in (e.get("tags") or []):
                chasti.append(str(t.get("label") or t.get("slug") or "") if isinstance(t, dict) else str(t))
    return " ".join(chasti).lower()


def kategoriya(m, pravila):
    tekst = tekst_rynka(m)
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


def _okno(a_dt, b_dt, closed):
    """все рынки с датой окончания в [a, b). Gamma не листает дальше ~2000 по offset —
    если окно заполнено до потолка, делим его пополам (рекурсивно, до часа)."""
    import datetime as _dt
    out, off = [], 0
    while True:
        r = get(GAMMA, "/markets", limit=100, offset=off, closed=closed, order="id", ascending="true",
                end_date_min=a_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), end_date_max=b_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if r is None and off >= 1900:            # упёрлись в потолок offset
            if b_dt - a_dt <= _dt.timedelta(hours=1):
                print(f"  ! окно {a_dt} слишком плотное, взято {len(out)}"); return out
            m = a_dt + (b_dt - a_dt) / 2
            return _okno(a_dt, m, closed) + _okno(m, b_dt, closed)
        if not r:
            return out
        out += r; off += len(r)
        if off >= 2000:
            m = a_dt + (b_dt - a_dt) / 2
            if b_dt - a_dt <= _dt.timedelta(hours=1):
                return out
            return _okno(a_dt, m, closed) + _okno(m, b_dt, closed)
        time.sleep(PAUZA)


POLYA = ("id", "question", "slug", "conditionId", "clobTokenIds", "outcomes", "startDate", "endDate", "createdAt",
         "closed", "active", "volume", "volumeNum", "groupItemTitle", "negRisk")


def uzko(m):
    """только нужные поля (каталог — сотни тысяч рынков, описания не храним)"""
    x = {k: m.get(k) for k in POLYA}
    x["events"] = [{k: e.get(k) for k in ("id", "title", "slug", "seriesSlug", "ticker")} |
                   {"tags": [t.get("label") or t.get("slug") for t in (e.get("tags") or []) if isinstance(t, dict)]}
                   for e in (js(m.get("events")) or []) if isinstance(e, dict)]
    return x


def katalog():
    """Окна по 30 дней даты окончания, каждое — отдельный файл katalog/<начало>.jsonl.
    Готовые окна в прошлом не перекачиваются (можно прерывать и продолжать);
    окна, которые заканчиваются позже чем 7 дней назад, обновляются всегда."""
    import datetime as _dt
    d = OUT / "katalog"; d.mkdir(parents=True, exist_ok=True)
    now = _dt.datetime.now(_dt.timezone.utc)
    a = _dt.datetime(2023, 1, 1, tzinfo=_dt.timezone.utc)
    konec = now + _dt.timedelta(days=400)
    vsego = 0
    while a < konec:
        b = min(a + _dt.timedelta(days=30), konec)
        f = d / f"{a:%Y%m%d}.jsonl"
        if f.exists() and b < now - _dt.timedelta(days=7):
            vsego += sum(1 for _ in f.open()); a = b; continue
        t0 = sejchas(); vse = {}
        for closed in ("false", "true"):
            for m in _okno(a, b, closed):
                vse[m.get("id")] = uzko(m)
        tmp = f.with_suffix(".tmp")
        with tmp.open("w") as fh:
            for m in vse.values():
                fh.write(json.dumps({"polucheno_ms": t0, **m}, ensure_ascii=False) + "\n")
        tmp.replace(f); vsego += len(vse)
        print(f"  окно {a:%Y-%m-%d}…{b:%Y-%m-%d}: {len(vse)} рынков (всего {vsego})", flush=True)
        a = b
    print(f"каталог готов: {vsego} рынков в {d}")


def otobrat_potokom():
    """каталог читается построчно (3 млн рынков в память не грузим), остаются только рынки из маппинга;
    итог — data/poly/otobrano.json"""
    mp = zagruzit_map(); pr = mp["kategorii"]; mn = mp.get("min_obem_usd", 100000)
    d = OUT / "katalog"; vse = {}; prosmotreno = 0
    for f in sorted(d.glob("*.jsonl")):
        with f.open() as fh:
            for s in fh:
                prosmotreno += 1
                m = json.loads(s)
                for x in otobrannye([m], pr, mn):
                    x["sobytie"] = ((m.get("events") or [{}])[0] or {}).get("title")
                    vse[x["conditionId"]] = x
    out = sorted(vse.values(), key=lambda x: -x["obem"])
    (OUT / "otobrano.json").write_text(json.dumps({"prosmotreno": prosmotreno, "rynki": out}, ensure_ascii=False))
    return out, prosmotreno


def otobrannye_gotovye():
    p = OUT / "otobrano.json"
    if not p.exists():
        otobrat_potokom()
    return json.loads(p.read_text())["rynki"]


def posledniy_katalog():
    d = OUT / "katalog"
    fs = sorted(d.glob("*.jsonl")) if d.exists() else []
    if not fs:
        raise SystemExit("нет каталога: сначала --katalog")
    out = []
    for f in fs:
        out += [json.loads(s) for s in f.read_text().splitlines() if s.strip()]
    return out


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


def proverka_rynkov(n=12):
    """событие → рынок → токен ДА → число точек истории, по 2 крупнейших рынка в каждой категории"""
    sel = otobrannye_gotovye()
    from collections import Counter
    print("рынков по маппингу:", len(sel), dict(Counter(s["kat"] for s in sel)))
    uzhe = Counter()
    for s in sel:
        if uzhe[s["kat"]] >= 2:
            continue
        uzhe[s["kat"]] += 1
        h = get(CLOB, "/prices-history", market=s["token"], interval="max", fidelity=60)
        n_t = len((h or {}).get("history", []))
        print(f"  [{s['kat']}] событие «{str(s.get('sobytie'))[:40]}» → рынок «{str(s['vopros'])[:55]}» "
              f"→ токен ДА …{str(s['token'])[-8:]} → точек {n_t}  (объём ${s['obem']:,.0f}, закрыт={s['closed']})")
        time.sleep(PAUZA)


def istoriya():
    sel = otobrannye_gotovye()
    d = OUT / "istoriya"; d.mkdir(parents=True, exist_ok=True)
    print(f"рынков по маппингу: {len(sel)}")
    for i, s in enumerate(sel, 1):
        p = d / f"{s['conditionId']}.json"
        if p.exists() and s["closed"]:
            continue                                   # закрытый рынок не меняется
        h = get(CLOB, "/prices-history", market=s["token"], interval="max", fidelity=60)
        ryad = {int(x["t"]): float(x["p"]) for x in (h or {}).get("history", [])}
        st, kn = _sek(s["start"]), _sek(s["konec"]) or int(time.time())
        if st and (len(ryad) < 48 or min(ryad, default=kn) > st + 86400):
            a = st
            while a < min(kn, int(time.time())):
                b = min(a + 14 * 86400, kn)
                h2 = get(CLOB, "/prices-history", market=s["token"], startTs=a, endTs=b, fidelity=60)
                ryad.update({int(x["t"]): float(x["p"]) for x in (h2 or {}).get("history", [])})
                a = b; time.sleep(PAUZA)
        ryad = sorted(ryad.items())
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
            kat = []
            for off in range(0, 2000, 100):                  # 2000 самых объёмных активных рынков
                r = get(GAMMA, "/markets", limit=100, offset=off, closed="false", order="volume", ascending="false") or []
                kat += r
                if not r:
                    break
                time.sleep(PAUZA)
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


def delta(snimok=True):
    """ежедневная дельта: новые и активные рынки, история только по нужным, один круг снимков"""
    import datetime as _dt
    mp = zagruzit_map(); pr = mp["kategorii"]; mn = mp.get("min_obem_usd", 100000)
    now = _dt.datetime.now(_dt.timezone.utc)
    svezhie = {}
    for off in range(0, 2000, 100):                      # активные по объёму
        r = get(GAMMA, "/markets", limit=100, offset=off, closed="false", order="volume", ascending="false") or []
        for m in r:
            svezhie[m.get("id")] = uzko(m)
        if not r:
            break
        time.sleep(PAUZA)
    for m in _okno(now - _dt.timedelta(days=45), now + _dt.timedelta(days=1), "true"):   # недавно закрытые
        svezhie[m.get("id")] = uzko(m)
    d = OUT / "katalog"; d.mkdir(parents=True, exist_ok=True)
    f = d / f"delta_{now:%Y%m%d}.jsonl"
    with f.open("w") as fh:
        for m in svezhie.values():
            fh.write(json.dumps({"polucheno_ms": sejchas(), **m}, ensure_ascii=False) + "\n")
    bylo = {x["conditionId"] for x in otobrannye_gotovye()}
    novye = [x for x in otobrannye(list(svezhie.values()), pr, mn) if x["conditionId"] not in bylo]
    otobrat_potokom()                                     # пересобрать общий список (с дельтой)
    print(f"дельта: рынков просмотрено {len(svezhie)}, новых по маппингу {len(novye)}")
    istoriya()
    if snimok:
        try:
            snimki_odin_krug(mp)
        except Exception as e:
            print("  ! снимок не снят:", e)
    return len(svezhie), len(novye)


def snimki_odin_krug(mp):
    d = OUT / "snimki"; d.mkdir(parents=True, exist_ok=True)
    kat = []
    for off in range(0, 1000, 100):
        r = get(GAMMA, "/markets", limit=100, offset=off, closed="false", order="volume", ascending="false") or []
        kat += r
        if not r:
            break
        time.sleep(PAUZA)
    sel = [s for s in otobrannye(kat, mp["kategorii"], mp.get("min_obem_usd", 100000)) if not s["closed"]]
    t = sejchas(); n = 0
    with (d / time.strftime("%Y-%m-%d.jsonl", time.gmtime())).open("a") as f:
        for s in sel:
            b = get(CLOB, "/book", token_id=s["token"]) or {}
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)[:10]
            asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))[:10]
            oi = get(DATA, "/oi", market=s["conditionId"])
            f.write(json.dumps({"t": t, "conditionId": s["conditionId"], "kat": s["kat"], "bids": bids, "asks": asks,
                                "oi": oi if not isinstance(oi, list) else (oi[0] if oi else None)}) + "\n")
            n += 1; time.sleep(PAUZA)
    print(f"  снимков стакана: {n}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--delta" in a: delta()
    elif "--otobrat" in a:
        r, n = otobrat_potokom(); print(f"просмотрено {n}, по маппингу {len(r)}")
    elif "--proverka_rynkov" in a: proverka_rynkov()
    elif "--proverka" in a: proverka()
    elif "--katalog" in a: katalog()
    elif "--istoriya" in a: istoriya()
    elif "--snimki" in a:
        i = a.index("--snimki"); snimki(int(a[i + 1]) if len(a) > i + 1 and a[i + 1].isdigit() else 15)
    else: print(__doc__)
