#!/usr/bin/env python3
"""etf_vpered.py — причинная тень ETF_PREMIYA_BTC (CONFIRM вперёд) + ежедневная фиксация Farside. 17.10.2026.

Решение владельца 17.10 («все да»): сборщик закрытий IBIT и собственная фиксация потоков Farside.
Вызывается сторожем раз в час (`prohod()`), идемпотентно, только публичные данные, без ордеров.

Правило событий ЗАМОРОЖЕНО (PREREG_ETF_PREMIYA_2026_10_17, fabrika/etf_premiya_sobytiya.py) и здесь не меняется:
premiya_t = (P_IBIT/P_BTC)_t / median(20 прошлых сессий) − 1, P_BTC = close часового бара Binance [15:00,16:00) ET;
z = premiya / sd(60 прошлых, ≥40); событие |z| ≥ 1.5, знак = sign(z); удержание 24 часовых бара; издержки 11 bps.

Три класса записей (не смешивать):
  OOS_POSLE_DEV  — сессии 2026-08-11 … 2026-10-16: правило заморожено до того, как кто-либо видел эти исходы
                   (DEV кончался на 2026-08-10, т.к. часовые BTC обрывались). Вход как в DEV: закрытие + 1 ч.
  VPERED         — сессии ≥ 2026-10-19: запись решения ДО исхода. Вход DEV (закрытие+1 ч) И исполнимый вход
                   (первый полный час после момента записи) — оба исхода пишутся; CONFIRM судится по исполнимому.
Исходы пишутся отдельным журналом и только когда все 24 бара закрыты.
"""
import datetime as dt, gzip, hashlib, json, math, sys, time, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "fabrika"))
NY = ZoneInfo("America/New_York"); H = 3_600_000
D = LAB / "data" / "etf_premiya"; G = LAB / "data" / "akcii_grouped"; F = LAB / "data" / "etf_potoki" / "vpered"
BTC_LIVE = D / "btc_h1_live.json"; TEN = D / "ten_ETF_PREMIYA.jsonl"; ISH = D / "ishody_ETF_PREMIYA.jsonl"
SOST = D / "vpered_sostoyanie.json"
DEV_KONEC, VPERED_S = "2026-08-10", "2026-10-19"
POROG_Z, OKNO, MIN_IST, HOLD, IZD = 1.5, 60, 40, 24, 11.0
MAKS_DNEVOK_ZA_PROHOD = 2


def _log(msg):
    D.mkdir(parents=True, exist_ok=True)
    with open(D / "vpered.log", "a") as f:
        f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}\n")


def _get(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "trading-os-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
    return b if raw else json.loads(b.decode())


def _jsonl(p):
    if not p.exists(): return []
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]


def _dopisat(p, row):
    with open(p, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── 1. данные ──────────────────────────────────────────────────────────────────────────────
def dogruzit_dnevki(segodnya=None):
    """Недостающие будни с 2026-10-01 по вчера (по Кипру — сессия NY уже закрыта). Не больше 2 запросов за проход."""
    import dannye_akcii_grouped as A
    segodnya = segodnya or dt.date.today(); k = None; n = 0
    den = dt.date(2026, 10, 1)
    while den < segodnya and n < MAKS_DNEVOK_ZA_PROHOD:
        p = G / f"{den.isoformat()}.json"
        if den.weekday() < 5 and not p.exists():
            k = k or A.kluch()
            d = A.zapros(f"/v2/aggs/grouped/locale/us/market/stocks/{den.isoformat()}?adjusted=true", k)
            n += 1
            if d is not None and d.get("resultsCount", len(d.get("results") or [])) > 0:
                rows = [[r.get("T"), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v"), r.get("vw"), r.get("n")]
                        for r in d.get("results") or []]
                p.write_text(json.dumps({"date": den.isoformat(), "rows": rows, "polucheno_ms": int(time.time() * 1000)}))
                _log(f"дневка {den} бумаг {len(rows)}")
            elif d is not None and (segodnya - den).days > 5:
                p.write_text(json.dumps({"date": den.isoformat(), "rows": [], "pusto": True}))   # праздник: не спрашивать снова
                _log(f"дневка {den}: пусто > 5 дней — праздник, записан пустой файл")
            elif d is not None:
                _log(f"дневка {den}: пусто (не готово) — повторю позже")
            if n < MAKS_DNEVOK_ZA_PROHOD: time.sleep(A.PAUZA)
        den += dt.timedelta(days=1)


def dogruzit_btc():
    """Часовые BTCUSDT Binance (публичный API) с 2026-08-01; ts = открытие бара, мс."""
    bary = {int(r[0]): r for r in (json.loads(BTC_LIVE.read_text()) if BTC_LIVE.exists() else [])}
    start = max(bary) + H if bary else int(dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    seychas = int(time.time() * 1000)
    for _ in range(6):
        if start > seychas - H: break
        k = _get(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime={start}&limit=1000")
        if not k: break
        for x in k:
            if int(x[6]) < seychas:                                   # только ЗАКРЫТЫЕ бары
                bary[int(x[0])] = [int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])]
        start = int(k[-1][0]) + H
    D.mkdir(parents=True, exist_ok=True)
    BTC_LIVE.write_text(json.dumps([bary[t] for t in sorted(bary)]))
    return bary


# ── 2. премия и решения (замороженное правило) ─────────────────────────────────────────────
def btc_ryad(bary_live):
    z = np.load(LAB / "data/h1/BTCUSDT.npz"); out = {}
    for t, row in zip(z["ts"].astype(np.int64), z["ohlcv"].astype(float)):
        out[int(t)] = [int(t), row[0], row[1], row[2], row[3]]
    out.update({int(t): r for t, r in bary_live.items()})
    return out


def zakrytie_ms(den):
    return int(dt.datetime.combine(dt.date.fromisoformat(den), dt.time(16, 0), NY).astimezone(dt.timezone.utc).timestamp() * 1000)


def premii(btc):
    rat = {}
    for p in sorted(G.glob("20*.json")):
        d = json.loads(p.read_text()); r = {x[0]: x for x in d["rows"] if x[0] == "IBIT"}
        if "IBIT" not in r: continue
        b = btc.get(zakrytie_ms(d["date"]) - H)
        if b: rat[d["date"]] = float(r["IBIT"][4]) / b[4]
    rd = sorted(rat); prem = {}
    for i, d in enumerate(rd):
        if i >= 20: prem[d] = rat[d] / float(np.median([rat[x] for x in rd[i - 20:i]])) - 1
    out = {}; pd_ = sorted(prem)
    for i, d in enumerate(pd_):
        ist = [prem[x] for x in pd_[max(0, i - OKNO):i]]
        if len(ist) < MIN_IST: continue
        sd = float(np.std(ist, ddof=1)); out[d] = (prem[d], prem[d] / sd if sd > 0 else 0.0)
    return out


def resheniya(btc, seychas_ms=None):
    seychas_ms = seychas_ms or int(time.time() * 1000)
    uzhe = {r["den"] for r in _jsonl(TEN)}; novye = 0
    for den, (p, z) in sorted(premii(btc).items()):
        if den <= DEV_KONEC or den in uzhe: continue
        tip = "VPERED" if den >= VPERED_S else "OOS_POSLE_DEV"
        t_dev = zakrytie_ms(den) + H
        vhod_isp = max(t_dev, (seychas_ms // H + 1) * H)
        row = dict(den=den, tip=tip, premiya_bps=round(1e4 * p, 2), z=round(z, 3), sobytie=bool(abs(z) >= POROG_Z),
                   znak=(1 if z > 0 else -1) if abs(z) >= POROG_Z else 0, vhod_dev_ms=t_dev,
                   vhod_isp_ms=vhod_isp if tip == "VPERED" else None, zapisano_ms=seychas_ms,
                   pravilo="PREREG_ETF_PREMIYA_2026_10_17", kod_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16])
        _dopisat(TEN, row); novye += 1
    return novye


def ishody(btc):
    est = {(r["den"], r["vhod"]) for r in _jsonl(ISH)}; ts = sorted(btc); idx = {t: i for i, t in enumerate(ts)}; n = 0
    for r in _jsonl(TEN):
        if not r["sobytie"]: continue
        for vid, t in (("dev", r["vhod_dev_ms"]), ("isp", r.get("vhod_isp_ms"))):
            if t is None or (r["den"], vid) in est: continue
            i = idx.get(t)
            if i is None or i + HOLD - 1 >= len(ts) or ts[i + HOLD - 1] != t + (HOLD - 1) * H: continue   # ждём все 24 бара подряд
            o, c = btc[ts[i]][1], btc[ts[i + HOLD - 1]][4]
            R = r["znak"] * (c / o - 1) * 1e4 - IZD
            _dopisat(ISH, dict(den=r["den"], tip=r["tip"], vhod=vid, vhod_ms=t, R_bps=round(R, 2), zapisano_ms=int(time.time() * 1000)))
            n += 1
    return n


# ── 3. Farside: собственный first_observed ─────────────────────────────────────────────────
def farside():
    import dannye_etf_potoki as P
    s = json.loads(SOST.read_text()) if SOST.exists() else {}
    segodnya = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if s.get("farside_den") == segodnya: return "уже сегодня"
    F.mkdir(parents=True, exist_ok=True); itog = {}
    for aktiv, url in (("btc", "https://farside.co.uk/bitcoin-etf-flow-all-data/"), ("eth", "https://farside.co.uk/ethereum-etf-flow-all-data/")):
        t = int(time.time() * 1000)
        try:
            html = _get(url, headers={"User-Agent": "Mozilla/5.0 (research; trading-os)"}, raw=True)
        except Exception as e:
            itog[aktiv] = f"ошибка {type(e).__name__}"; continue
        (F / f"{aktiv}_{t}.html.gz").write_bytes(gzip.compress(html))
        znach, plohih = P.razobrat(html); put = F / f"potoki_vpered_{aktiv}.jsonl"
        vid = {(r["date"]) for r in _jsonl(put)}; nov = 0
        for d, v in sorted(znach.items()):
            if d not in vid:
                _dopisat(put, dict(date=d, first_total_musd=v, first_observed_ms=t, sobstvennyy=True)); nov += 1
        itog[aktiv] = f"дней {len(znach)}, новых {nov}, расхождений {plohih}"
    s["farside_den"] = segodnya; SOST.write_text(json.dumps(s))
    return itog


def prohod():
    rez = {}
    for imya, f in (("dnevki", dogruzit_dnevki), ("farside", farside)):
        try: rez[imya] = f()
        except BaseException as e: rez[imya] = f"ошибка {type(e).__name__}: {str(e)[:120]}"
    try:
        btc = btc_ryad(dogruzit_btc())
        rez["resheniy"] = resheniya(btc); rez["ishodov"] = ishody(btc)
    except BaseException as e:
        rez["ten"] = f"ошибка {type(e).__name__}: {str(e)[:120]}"
    _log(json.dumps(rez, ensure_ascii=False, default=str))
    return rez


if __name__ == "__main__":
    print(prohod())
