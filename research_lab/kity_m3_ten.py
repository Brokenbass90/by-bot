#!/usr/bin/env python3
"""kity_m3_ten.py — бумажная тень KITY_M3_POTOK (вперёд, невиданные данные). БЕЗ ключей, БЕЗ ордеров, только публичный Binance.

Правило заморожено в PREREG_KITY_M3_POTOK_2026_10_04.md и здесь НЕ меняется:
  четверг d (сетка от 2021-07-01, шаг 7): вселенная — PIT топ-50 USDT-перпов по OI $ на 23:55 UTC дня d−1;
  ≥ 60 закрытых дневных баров до d; признак — taker_buy_quote / quote_volume дневной свечи d−1; ≥ 30 монет;
  лонг верхних 10% (5), шорт нижних 10% (5), равные веса; вход — закрытие дня d, выход — закрытие d+7;
  12 bps на круг, фандинг Binance (лонг платит положительный).
Порядок PAPER_TEN_KITY_M3.md. Состояние: data/kity_m3_ten/<d>/ (сырые ответы API + sha256, сигнал, вход, выход, квитанция).

    python3 research_lab/kity_m3_ten.py --proverka        связь с API и разбор (ничего не пишет)
    python3 research_lab/kity_m3_ten.py --shag            сделать всё, что уже наступило (идемпотентно)
    python3 research_lab/kity_m3_ten.py --cikl            --shag раз в час (запускать в screen, без автозапуска)
    python3 research_lab/kity_m3_ten.py --sverka 2026-10-08   сверка признака с архивом data.binance.vision
"""
from __future__ import annotations
import csv, datetime as dt, hashlib, io, json, sys, time, urllib.parse, urllib.request, zipfile
from pathlib import Path

API = "https://fapi.binance.com"
ARH = "https://data.binance.vision/data/futures/um/daily"
D = Path(__file__).resolve().parent / "data" / "kity_m3_ten"
NACH_SETKI = dt.date(2021, 7, 1)
TOP, MIN_MONET, MIN_BAROV, HOLD, KOM, NOTIONAL = 50, 30, 60, 7, 0.0012, 100.0
PAUZA = 0.25
DEN = 86_400_000


def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
def utc(): return dt.datetime.now(dt.timezone.utc)
def sha(b: bytes): return hashlib.sha256(b).hexdigest()


def get(put, **p):
    url = API + put + ("?" + urllib.parse.urlencode(p) if p else "")
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                b = r.read(); time.sleep(PAUZA); return json.loads(b), b
        except urllib.error.HTTPError as e:
            if e.code in (418, 429):
                time.sleep(60 * (k + 1)); continue
            if e.code == 400:
                return None, b""
            time.sleep(3 * (k + 1))
        except Exception:
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"API не ответил: {put} {p}")


def chetverg_dlya(den: dt.date) -> dt.date:
    """последняя дата сетки ≤ den"""
    return NACH_SETKI + dt.timedelta(days=7 * ((den - NACH_SETKI).days // 7))


def instrumenty():
    x, b = get("/fapi/v1/exchangeInfo")
    out = {}
    for s in x["symbols"]:
        if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
            f = {q["filterType"]: q for q in s["filters"]}
            lot = f.get("MARKET_LOT_SIZE") or f.get("LOT_SIZE") or {}
            out[s["symbol"]] = dict(step=float(lot.get("stepSize", 0) or 0), min_qty=float(lot.get("minQty", 0) or 0),
                                   min_notional=float((f.get("MIN_NOTIONAL") or {}).get("notional", 0) or 0))
    return out, b


def oi_2355(sym, d_1: dt.date):
    t1 = ms(d_1) + 23 * 3_600_000 + 55 * 60_000
    x, b = get("/futures/data/openInterestHist", symbol=sym, period="5m", startTime=t1 - 15 * 60_000, endTime=t1, limit=10)
    if not x:
        return None, b
    x = [r for r in x if t1 - 15 * 60_000 <= int(r["timestamp"]) <= t1]
    return (float(x[-1]["sumOpenInterestValue"]) if x else None), b


def svechi(sym, do_ms, limit=75):
    x, b = get("/fapi/v1/klines", symbol=sym, interval="1d", endTime=do_ms - 1, limit=limit)
    return [r for r in (x or []) if int(r[6]) < do_ms], b      # только закрытые до do_ms


def signal(d: dt.date):
    papka = D / d.isoformat(); f = papka / "signal.json"
    if f.exists():
        return json.loads(f.read_text())
    if utc() < dt.datetime(d.year, d.month, d.day, 0, 5, tzinfo=dt.timezone.utc):
        return None                                   # свеча d−1 ещё не закрыта
    syr = papka / "syroe"; syr.mkdir(parents=True, exist_ok=True)
    instr, b = instrumenty(); (syr / "exchangeInfo.json").write_bytes(b)
    d_1 = d - dt.timedelta(days=1); oi = {}
    for s in sorted(instr):
        v, bb = oi_2355(s, d_1)
        if v:
            oi[s] = v
    (syr / "oi_2355.json").write_text(json.dumps(oi, sort_keys=True))
    top = [s for s, _ in sorted(oi.items(), key=lambda z: -z[1])[:TOP]]
    rows, kl_all = [], {}
    for s in top:
        kl, bb = svechi(s, ms(d)); kl_all[s] = kl
        if len(kl) < MIN_BAROV or int(kl[-1][0]) != ms(d_1):
            continue
        qv, tq = float(kl[-1][7]), float(kl[-1][10])
        if qv > 0:
            rows.append((tq / qv, s))
    (syr / "klines_d-1.json").write_text(json.dumps(kl_all, sort_keys=True))
    rows.sort(); k = len(rows) // 10
    rez = dict(d=d.isoformat(), vychisleno=utc().isoformat(timespec="seconds"), monet_v_top=len(top), monet_s_priznakom=len(rows),
               dostatochno=len(rows) >= MIN_MONET,
               long=[dict(s=s, taker=round(v, 6)) for v, s in rows[-k:]] if len(rows) >= MIN_MONET else [],
               short=[dict(s=s, taker=round(v, 6)) for v, s in rows[:k]] if len(rows) >= MIN_MONET else [],
               vse_priznaki={s: round(v, 6) for v, s in rows},
               sha256={p.name: sha(p.read_bytes()) for p in sorted(syr.iterdir())},
               instrumenty={s: instr[s] for s in instr if s in {r[1] for r in rows}})
    f.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); return rez


def zakrytie(sym, den: dt.date):
    kl, _ = svechi(sym, ms(den + dt.timedelta(days=1)), limit=3)
    kl = [r for r in kl if int(r[0]) == ms(den)]
    return float(kl[0][4]) if kl else None


def vhod(d, sig):
    f = D / d.isoformat() / "vhod.json"
    if f.exists() or not sig or not sig["dostatochno"]:
        return json.loads(f.read_text()) if f.exists() else None
    if utc() < dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1, minutes=5):
        return None
    poz = []
    for side, nogi in ((+1, sig["long"]), (-1, sig["short"])):
        for n in nogi:
            c = zakrytie(n["s"], d); ins = sig["instrumenty"].get(n["s"], {})
            qty = NOTIONAL / c if c else None
            if qty and ins.get("step"):
                qty = int(qty / ins["step"]) * ins["step"]
            poz.append(dict(s=n["s"], side=side, cena_vhoda=c, kolichestvo=qty,
                            lot_ok=bool(qty and qty >= ins.get("min_qty", 0) and qty * c >= ins.get("min_notional", 0))))
    rez = dict(d=d.isoformat(), zapisano=utc().isoformat(timespec="seconds"), dopushchenie="вход по закрытию дня d (бумага), $100 на позицию",
               pozicii=poz)
    f.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); return rez


def vyhod(d, vh):
    f = D / d.isoformat() / "vyhod.json"
    if f.exists() or not vh:
        return json.loads(f.read_text()) if f.exists() else None
    d7 = d + dt.timedelta(days=HOLD)
    if utc() < dt.datetime(d7.year, d7.month, d7.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1, minutes=5):
        return None
    t0, t1 = ms(d) + DEN, ms(d7) + DEN; nogi = []
    for p in vh["pozicii"]:
        c1 = zakrytie(p["s"], d7)
        fr, _ = get("/fapi/v1/fundingRate", symbol=p["s"], startTime=t0 + 1, endTime=t1, limit=1000)
        fsum = sum(float(r["fundingRate"]) for r in (fr or []) if t0 < int(r["fundingTime"]) <= t1)
        r = None if not (c1 and p["cena_vhoda"]) else p["side"] * (c1 / p["cena_vhoda"] - 1) - p["side"] * fsum - KOM
        nogi.append(dict(p, cena_vyhoda=c1, fanding=fsum, dohod=r))
    ok = [n["dohod"] for n in nogi if n["dohod"] is not None]
    rez = dict(d=d.isoformat(), zapisano=utc().isoformat(timespec="seconds"), nogi=nogi,
               nedelya_bps=round(sum(ok) / len(ok) * 1e4, 1) if ok else None)
    f.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); return rez


def kvitanciya(d, sig, vh, vy):
    f = D / d.isoformat() / "KVITANCIYA_NEDELI.json"
    if f.exists() or not vy:
        return
    sv = D / d.isoformat() / "sverka.json"
    sverka = json.loads(sv.read_text()) if sv.exists() else None
    prich = []
    if not sig["dostatochno"]: prich.append("< 30 монет")
    if not (dt.datetime.fromisoformat(sig["vychisleno"]) < dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc) + dt.timedelta(days=1)):
        prich.append("сигнал посчитан после закрытия дня d (не успели к входу)")
    if not all(p["lot_ok"] for p in vh["pozicii"]): prich.append("не все позиции проходят мин. лот/номинал при $100")
    if any(n["dohod"] is None for n in vy["nogi"]): prich.append("нет цены входа/выхода у части ног")
    if not sverka or not sverka.get("ok"): prich.append("сверка с архивом не пройдена или не сделана")
    st = "PAPER_WEEK_OPERATIONAL_PASS" if not prich else "PAPER_WEEK_OPERATIONAL_FAIL"
    f.write_text(json.dumps(dict(d=d.isoformat(), status=st, prichiny=prich,
        nedelya_bps_spravochno=vy["nedelya_bps"], primechanie="одна неделя доходности — шум; вердикт только операционный",
        sha256=dict(signal=sha((D / d.isoformat() / "signal.json").read_bytes()), vhod=sha((D / d.isoformat() / "vhod.json").read_bytes()),
                    vyhod=sha((D / d.isoformat() / "vyhod.json").read_bytes()))), ensure_ascii=False, indent=1))
    print("КВИТАНЦИЯ НЕДЕЛИ:", st, prich)


def sverka(d: dt.date):
    """признак d−1 из архива data.binance.vision (дневные свечи) против живого; децили должны совпасть."""
    sig = json.loads((D / d.isoformat() / "signal.json").read_text()); d_1 = d - dt.timedelta(days=1); arh = {}
    for s in sig["vse_priznaki"]:
        url = f"{ARH}/klines/{s}/1d/{s}-1d-{d_1.isoformat()}.zip"
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30).read()
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                rows = [r for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))) if r and r[0].isdigit()]
            arh[s] = float(rows[0][10]) / float(rows[0][7])
        except Exception:
            pass
        time.sleep(PAUZA)
    obshchie = [s for s in sig["vse_priznaki"] if s in arh]
    if len(obshchie) < len(sig["vse_priznaki"]):
        raise RuntimeError(f"архив за {d_1} ещё не полный ({len(obshchie)}/{len(sig['vse_priznaki'])}) — повтор через час")
    raskhozh = max((abs(arh[s] - sig["vse_priznaki"][s]) for s in obshchie), default=None)
    rows = sorted((arh[s], s) for s in obshchie); k = len(sig["long"])
    lo, sh = {s for _, s in rows[-k:]}, {s for _, s in rows[:k]}
    sovp = len(lo & {x["s"] for x in sig["long"]}) + len(sh & {x["s"] for x in sig["short"]})
    rez = dict(d=d.isoformat(), monet_v_arhive=len(obshchie), iz=len(sig["vse_priznaki"]), maks_raskhozhdenie=raskhozh,
               sovpalo_v_korzine=f"{sovp}/{2 * k}", ok=bool(obshchie) and len(obshchie) == len(sig["vse_priznaki"]) and sovp == 2 * k and (raskhozh or 0) < 1e-4)
    (D / d.isoformat() / "sverka.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print("СВЕРКА:", rez)


def shag():
    D.mkdir(parents=True, exist_ok=True)
    seg = utc().date(); dd = [chetverg_dlya(seg) - dt.timedelta(days=7 * k) for k in range(3)]
    print(f"{utc().isoformat(timespec='seconds')} пульс: жив, первый сигнал 2026-10-08 00:05 UTC", flush=True)
    for d in sorted(dd):
        if d < dt.date(2026, 10, 8):                  # тень начинается с первого невиданного четверга
            continue
        sig = signal(d)
        if sig and not (D / d.isoformat() / "sverka.json").exists() and utc().date() >= d + dt.timedelta(days=1):
            try:
                sverka(d)
            except Exception as e:
                print("сверка позже:", e)
        vh = vhod(d, sig); vy = vyhod(d, vh)
        if sig and vh and vy:
            kvitanciya(d, sig, vh, vy)
        print(f"{utc().isoformat(timespec='seconds')} {d}: сигнал={'да' if sig else 'нет'} вход={'да' if vh else 'нет'} выход={'да' if vy else 'нет'}", flush=True)


def proverka():
    instr, _ = instrumenty(); print("USDT-перпов TRADING:", len(instr), "| BTCUSDT:", instr.get("BTCUSDT"))
    d_1 = utc().date() - dt.timedelta(days=1)
    v, _ = oi_2355("BTCUSDT", d_1); print(f"OI $ BTCUSDT {d_1} 23:55:", v)
    kl, _ = svechi("BTCUSDT", ms(utc().date())); print("закрытых дневных свечей BTCUSDT:", len(kl), "| последняя:",
          dt.datetime.fromtimestamp(int(kl[-1][0]) / 1000, dt.timezone.utc).date(), "доля тейкеров:", round(float(kl[-1][10]) / float(kl[-1][7]), 4))
    fr, _ = get("/fapi/v1/fundingRate", symbol="BTCUSDT", limit=3); print("фандинг BTCUSDT последние:", [r["fundingRate"] for r in fr])
    print("следующий четверг сетки:", chetverg_dlya(utc().date()) + dt.timedelta(days=7) if chetverg_dlya(utc().date()) < utc().date() else chetverg_dlya(utc().date()))
    if not (v and len(kl) >= MIN_BAROV and fr):
        sys.exit("ПРОВЕРКА: FAIL")
    print("ПРОВЕРКА: OK")


if __name__ == "__main__":
    if "--proverka" in sys.argv:
        proverka()
    elif "--sverka" in sys.argv:
        sverka(dt.date.fromisoformat(sys.argv[sys.argv.index("--sverka") + 1]))
    elif "--cikl" in sys.argv:
        while True:
            try:
                shag()
            except Exception as e:
                print(utc().isoformat(timespec="seconds"), "ошибка шага:", type(e).__name__, str(e)[:200], flush=True)
            time.sleep(3600)
    else:
        shag()
