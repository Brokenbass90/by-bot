#!/usr/bin/env python3
"""kity_bybit_ten.py — бумажная тень Bybit-НАТИВНОЙ KITY (PREREG_KITY_BYBIT_TEN_2026_10_11.md). Только публичные данные Bybit,
без ключей и заявок. Правило = судья KITY_BYBIT_ARHIV (CROSS_VENUE_PASS 07.10): вселенная — топ-50 Bybit по OI$ к концу дня d−1,
признак — доля агрессивных покупок дня d−1 из публичного архива сделок Bybit, лонг верхнего дециля / шорт нижнего (k=n//10),
вход закрытием дня d, 7 дней, фандинг Bybit, 12 bps круг. Корзина по построению — только монеты Bybit.
Расписание (UTC): ср 23:50–23:59 — снимок OI/цен; чт с 00:10 — архив d−1 по монетам снимка (повтор раз в час, пока не будет ≥ всех
или до 23:00); пт 00:05 — вход по закрытию d; через 7 дней — выход и квитанция. --proverka: проверка доступа и форматов."""
import csv, datetime as dt, fcntl, gzip, hashlib, io, json, math, os, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
API = "https://api.bybit.com"; ARH = "https://public.bybit.com/trading/{s}/{s}{d}.csv.gz"
D = Path(__file__).resolve().parent / "data" / "kity_bybit_ten"
NACH_SETKI = dt.date(2021, 7, 1); PERVYY = dt.date(2026, 10, 15)
TOP, MIN_MONET, MIN_BAROV, HOLD, KOM, NOTIONAL, DEN = 50, 30, 60, 7, 0.0012, 100.0, 86_400_000
def utc(): return dt.datetime.now(dt.timezone.utc)
def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def sha(b): return hashlib.sha256(b).hexdigest()
def log(*a): print(utc().isoformat(timespec="seconds"), *a, flush=True)

def get(put, **p):
    url = API + put + "?" + urllib.parse.urlencode(p)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                b = r.read(); time.sleep(0.12); j = json.loads(b)
                if j.get("retCode") == 0: return j["result"], b
                if j.get("retCode") in (10006, 10018): time.sleep(20 * (k + 1)); continue
                return None, b
        except Exception: time.sleep(3 * (k + 1))
    raise RuntimeError(f"Bybit не ответил: {put} {p}")

def chetverg_dlya(den): return NACH_SETKI + dt.timedelta(days=7 * ((den - NACH_SETKI).days // 7))

def instrumenty():
    out, kur = {}, ""
    while True:
        r, _ = get("/v5/market/instruments-info", category="linear", limit=1000, **({"cursor": kur} if kur else {}))
        for s in r["list"]:
            if s.get("contractType") == "LinearPerpetual" and s.get("quoteCoin") == "USDT" and s.get("status") == "Trading":
                f = s.get("lotSizeFilter", {})
                out[s["symbol"]] = dict(step=float(f.get("qtyStep", 0) or 0), min_qty=float(f.get("minOrderQty", 0) or 0),
                                        min_notional=float(f.get("minNotionalValue", 0) or 0))
        kur = r.get("nextPageCursor") or ""
        if not kur: return out

def atomno(f, tekst):
    """POPRAVKA_A1 (14.10): запись через временный файл + fsync + os.replace — частичный файл невозможен."""
    f.parent.mkdir(parents=True, exist_ok=True); tmp = f.with_name(f".{f.name}.tmp")
    with open(tmp, "w") as h: h.write(tekst); h.flush(); os.fsync(h.fileno())
    os.replace(tmp, f)

PRODUCER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def opublikovat(f, dannye):
    """A1.2: публикация без перезаписи. Эксклюзивный уникальный temp (O_EXCL), запись ВСЕХ байт в цикле, fsync файла,
    os.link в итоговое имя (ошибка, если есть), fsync каталога. При любом сбое до link — temp удаляется, final не появляется.
    Возвращает True, если опубликовано этим вызовом."""
    b = dannye if isinstance(dannye, bytes) else dannye.encode()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".{f.name}.{os.getpid()}.{time.time_ns()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        mv = memoryview(b); n = 0
        while n < len(b): n += os.write(fd, mv[n:])
        os.fsync(fd)
    except BaseException:
        os.close(fd); os.unlink(tmp); raise
    os.close(fd)
    try: os.link(tmp, f); ok = True
    except FileExistsError: ok = False
    finally: os.unlink(tmp)
    dfd = os.open(f.parent, os.O_RDONLY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return ok

def konec_okna(d_1): return dt.datetime(d_1.year, d_1.month, d_1.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1)   # 00:00 UTC дня d

def oi_valid(v):
    """A1.2: bool отвергается до float; затем float, конечность, ≥ 0."""
    if isinstance(v, bool) or v is None: return None
    try: x = float(v)
    except (TypeError, ValueError): return None
    return x if math.isfinite(x) and x >= 0 else None

def kvitanciya_snimka(papka):
    """Снимок потребляем ТОЛЬКО при валидной квитанции CAPTURE_PASS с совпадающим sha снимка."""
    f, q = papka / "snimok_2355.json", papka / "snimok_CAPTURE_RECEIPT.json"
    if not (f.exists() and q.exists()): return None
    k = json.loads(q.read_text())
    return k if k.get("status") == "CAPTURE_PASS" and k.get("snapshot_sha256") == sha(f.read_bytes()) else None

POSL_NEIZV = {}                                       # d_1 → монеты без валидного OI в последней попытке окна

def snimok(d_1):
    d = d_1 + dt.timedelta(days=1); papka = D / d.isoformat(); f = papka / "snimok_2355.json"
    if (papka / "snimok_CAPTURE_RECEIPT.json").exists() or (papka / "snimok_PROPUSHCHEN.json").exists(): return
    t_cap = utc(); cap_ms = int(t_cap.timestamp() * 1000)                       # A1.2: одна зафиксированная отметка захвата
    r, b = get("/v5/market/tickers", category="linear"); instr = instrumenty()
    nd = papka / "neudachi"
    if not r or not r.get("list"):
        opublikovat(nd / f"tickers_{cap_ms}.raw", b or b""); log("снимок: тикеры не получены, сырой ответ сохранён, повтор", d_1); return
    oi, neizv = {}, []
    for t in r["list"]:
        if t["symbol"] not in instr: continue
        v = oi_valid(t.get("openInterestValue"))
        if v is None: neizv.append(t["symbol"])
        else: oi[t["symbol"]] = v
    if neizv:                                          # невалидный OI → весь захват SOURCE_UNKNOWN, монеты не удаляются
        POSL_NEIZV[d_1] = sorted(neizv); opublikovat(nd / f"tickers_{cap_ms}.raw", b)
        log("снимок: OI невалиден у", len(neizv), "— SOURCE_UNKNOWN, сырой ответ сохранён, повтор", d_1); return
    if utc() >= konec_okna(d_1): log("снимок: захват после окна — не публикуется", d_1); return
    opublikovat(papka / "tickers_raw.json", b)
    telo = json.dumps(dict(vremya=t_cap.isoformat(timespec="seconds"), capture_ms=cap_ms, sha256_tickers=sha(b), oi_usd=oi,
                           instrumenty=instr), sort_keys=True).encode()
    if not opublikovat(f, telo): log("снимок уже существует без квитанции — не потребляется", d_1); return
    zav_ms = int(utc().timestamp() * 1000)                                       # фактическое завершение ПОСЛЕ fsync файла и каталога
    if zav_ms >= int(konec_okna(d_1).timestamp() * 1000):
        log("снимок: завершение после окна — квитанции успеха нет (BLOCKED при закрытии окна)", d_1); return
    opublikovat(papka / "snimok_CAPTURE_RECEIPT.json", json.dumps(dict(
        status="CAPTURE_PASS", day=d.isoformat(), producer_sha256=PRODUCER_SHA256, source_sha256=sha(b),
        snapshot_sha256=sha(telo), capture_ms=cap_ms, completed_ms=zav_ms), sort_keys=True))
    log("снимок", d_1, "монет", len(oi), "CAPTURE_PASS")

def propusk_okna(d_1):
    """Окно закрылось без валидной квитанции успеха → квитанция BLOCKED_DATA (без перезаписи)."""
    papka = D / (d_1 + dt.timedelta(days=1)).isoformat(); q = papka / "snimok_PROPUSHCHEN.json"
    if kvitanciya_snimka(papka) or q.exists() or utc() < konec_okna(d_1): return
    neizv = POSL_NEIZV.get(d_1)
    opublikovat(q, json.dumps(dict(status="BLOCKED_DATA", prichina="SOURCE_UNKNOWN: невалидный OI" if neizv else
                                   "окно 23:50–23:59 UTC закрыто без валидной квитанции успеха (процесс/сеть/позднее завершение)",
                                   oi_neizvesten=neizv or [], d_1=d_1.isoformat(), producer_sha256=PRODUCER_SHA256,
                                   zapisano=utc().isoformat(timespec="seconds")), ensure_ascii=False))
    log("ОКНО СНИМКА ЗАКРЫТО БЕЗ УСПЕХА", d_1, "→ BLOCKED_DATA")

def svechi(sym, do_ms, limit=75):
    r, _ = get("/v5/market/kline", category="linear", symbol=sym, interval="D", end=do_ms - 1, limit=limit)
    kl = sorted((r or {}).get("list", []), key=lambda x: int(x[0]))
    return [x for x in kl if int(x[0]) + DEN <= do_ms]

def potok(sym, den):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(ARH.format(s=urllib.parse.quote(sym, safe=""), d=den.isoformat()),
                                                            headers={"User-Agent": "research-paper"}), timeout=180).read()
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else "err"
    except Exception: return "err"
    buy = sell = 0.0
    for row in csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding="utf-8")):
        try: v = float(row.get("foreignNotional") or 0) or float(row["size"]) * float(row["price"])
        except (TypeError, ValueError): continue
        if row["side"] == "Buy": buy += v
        else: sell += v
    return dict(buy=buy, sell=sell, sha256=sha(raw)) if buy + sell > 0 else None

def signal(d):
    papka = D / d.isoformat(); f = papka / "signal.json"
    if f.exists(): return json.loads(f.read_text())
    sn = papka / "snimok_2355.json"
    if not kvitanciya_snimka(papka) or utc() < dt.datetime(d.year, d.month, d.day, 0, 10, tzinfo=dt.timezone.utc): return None
    s = json.loads(sn.read_text()); top = [k for k, _ in sorted(s["oi_usd"].items(), key=lambda z: -z[1])[:TOP]]
    pf = papka / "potok.json"; pt = json.loads(pf.read_text()) if pf.exists() else {}
    pozdno = utc() >= dt.datetime(d.year, d.month, d.day, 23, 0, tzinfo=dt.timezone.utc)
    if pf.exists() and time.time() - pf.stat().st_mtime < 3300 and not pozdno: return None   # повтор архива не чаще раза в час
    d_1 = d - dt.timedelta(days=1)
    for sym in top:
        if sym not in pt or pt[sym] == "err":
            v = potok(sym, d_1)
            if v is not None: pt[sym] = v
    atomno(pf, json.dumps(pt, sort_keys=True))
    gotovo = sum(1 for sym in top if isinstance(pt.get(sym), dict))
    if gotovo < len(top) and not pozdno:
        log(d, f"архив d−1 готов у {gotovo}/{len(top)} — повтор через час"); return None
    rows = []
    for sym in top:
        a = pt.get(sym)
        if not isinstance(a, dict): continue
        kl = svechi(sym, ms(d))
        if len(kl) < MIN_BAROV or int(kl[-1][0]) != ms(d_1): continue
        rows.append((a["buy"] / (a["buy"] + a["sell"]), sym))
    rows.sort(); k = len(rows) // 10; ok = len(rows) >= MIN_MONET
    rez = dict(d=d.isoformat(), vychisleno=utc().isoformat(timespec="seconds"), monet_v_top=len(top), monet_s_priznakom=len(rows),
               dostatochno=ok, long=[dict(s=x, taker=round(v, 6)) for v, x in rows[-k:]] if ok else [],
               short=[dict(s=x, taker=round(v, 6)) for v, x in rows[:k]] if ok else [], vse_priznaki={x: round(v, 6) for v, x in rows},
               sha256=dict(snimok=sha(sn.read_bytes()), potok=sha(pf.read_bytes())), instrumenty={x: s["instrumenty"][x] for _, x in rows})
    atomno(f, json.dumps(rez, ensure_ascii=False, indent=1)); log("СИГНАЛ", d, "монет", len(rows), "k", k); return rez

def zakrytie(sym, den):
    kl = [x for x in svechi(sym, ms(den + dt.timedelta(days=1)), 3) if int(x[0]) == ms(den)]
    return float(kl[0][4]) if kl else None

def vhod(d, sig):
    f = D / d.isoformat() / "vhod.json"
    if f.exists(): return json.loads(f.read_text())
    if not sig or not sig["dostatochno"] or utc() < dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1, minutes=5): return None
    poz = []
    for side, nogi in ((+1, sig["long"]), (-1, sig["short"])):
        for n in nogi:
            c = zakrytie(n["s"], d); ins = sig["instrumenty"].get(n["s"], {}); q = NOTIONAL / c if c else None
            if q and ins.get("step"): q = int(q / ins["step"]) * ins["step"]
            poz.append(dict(s=n["s"], side=side, cena_vhoda=c, kolichestvo=q,
                            lot_ok=bool(q and q >= ins.get("min_qty", 0) and q * c >= ins.get("min_notional", 0))))
    rez = dict(d=d.isoformat(), zapisano=utc().isoformat(timespec="seconds"), pozicii=poz); atomno(f, json.dumps(rez, ensure_ascii=False, indent=1)); return rez

def vyhod(d, vh):
    f = D / d.isoformat() / "vyhod.json"
    if f.exists(): return json.loads(f.read_text())
    d7 = d + dt.timedelta(days=HOLD)
    if not vh or utc() < dt.datetime(d7.year, d7.month, d7.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1, minutes=5): return None
    t0, t1 = ms(d) + DEN, ms(d7) + DEN; nogi = []
    for p in vh["pozicii"]:
        c1 = zakrytie(p["s"], d7); r, _ = get("/v5/market/funding/history", category="linear", symbol=p["s"], startTime=t0 + 1, endTime=t1, limit=200)
        fs = sum(float(x["fundingRate"]) for x in (r or {}).get("list", []) if t0 < int(x["fundingRateTimestamp"]) <= t1)
        dh = None if not (c1 and p["cena_vhoda"]) else p["side"] * (c1 / p["cena_vhoda"] - 1) - p["side"] * fs - KOM
        nogi.append(dict(p, cena_vyhoda=c1, fanding=fs, dohod=dh))
    ok = [n["dohod"] for n in nogi if n["dohod"] is not None]
    rez = dict(d=d.isoformat(), zapisano=utc().isoformat(timespec="seconds"), nogi=nogi, nedelya_bps=round(sum(ok) / len(ok) * 1e4, 1) if ok else None,
               status="PAPER_WEEK_OPERATIONAL_PASS" if len(ok) == len(nogi) and all(p["lot_ok"] for p in vh["pozicii"]) else "PAPER_WEEK_OPERATIONAL_FAIL")
    atomno(f, json.dumps(rez, ensure_ascii=False, indent=1)); log("ВЫХОД", d, rez["status"], rez["nedelya_bps"]); return rez

def shag():
    n = utc(); seg = n.date()
    if n.hour == 23 and n.minute >= 50 and (seg + dt.timedelta(days=1)) == chetverg_dlya(seg + dt.timedelta(days=1)) and seg + dt.timedelta(days=1) >= PERVYY:
        snimok(seg)
    vchera = seg - dt.timedelta(days=1)
    if seg == chetverg_dlya(seg) and seg >= PERVYY: propusk_okna(vchera)
    for d in sorted({chetverg_dlya(seg) - dt.timedelta(days=7 * k) for k in range(3)}):
        if d < PERVYY: continue
        sig = signal(d); vh = vhod(d, sig); vyhod(d, vh)

def proverka():
    instr = instrumenty(); print("перпов USDT Trading:", len(instr), "BTC:", instr.get("BTCUSDT"))
    r, _ = get("/v5/market/tickers", category="linear"); t = sorted(r["list"], key=lambda x: -float(x.get("openInterestValue") or 0))[:5]
    print("топ-5 OI$:", [(x["symbol"], round(float(x["openInterestValue"]) / 1e6)) for x in t])
    kl = svechi("BTCUSDT", ms(utc().date())); print("дневных свечей BTC:", len(kl), "последняя", dt.datetime.utcfromtimestamp(int(kl[-1][0]) / 1000).date())
    a = potok("BTCUSDT", utc().date() - dt.timedelta(days=2)); print("архив BTC d−2:", {k: v for k, v in (a or {}).items() if k != "sha256"} if isinstance(a, dict) else a)
    r, _ = get("/v5/market/funding/history", category="linear", symbol="BTCUSDT", limit=2); print("фандинг:", [x["fundingRate"] for x in r["list"]])
    print("ПРОВЕРКА: OK" if instr and kl and isinstance(a, dict) else "ПРОВЕРКА: FAIL")

if __name__ == "__main__":
    if "--proverka" in sys.argv: proverka()
    elif "--cikl" in sys.argv:
        (D.parent / "locks").mkdir(parents=True, exist_ok=True)          # POPRAVKA_A1: единственный писатель (сверх лаунчера)
        _zamok = open(D.parent / "locks" / "kity_bybit_ten.lock", "a+")
        try: fcntl.flock(_zamok, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: sys.exit("kity_bybit_ten: второй писатель — отказ (замок занят)")
        poslp = 0
        while True:
            try:
                shag()
                if time.time() - poslp > 3600: log("пульс: жив, первый четверг", PERVYY); poslp = time.time()
            except Exception as e: log("ошибка шага:", type(e).__name__, str(e)[:200])
            time.sleep(60)
    else: proverka()
