"""KITY_BITGET_VPERED — проспективный сборщик публичных данных Bitget USDT-M для кросс-биржевой
проверки KITY M3 (поток тейкеров). Только публичный API, без ключей, без заявок. Исходы не судит.

Расписание (UTC), цикл раз в минуту:
  23:50–23:59 дня D  → снимок tickers (OI, цены) = PIT-вселенная для сигнала D+1;
  с 00:15 дня D+1    → по топ-ВЕРХ монетам снимка D: taker-buy-sell 1D, дневные свечи, фандинг.
Каждый ответ сохраняется сырым байтом + sha256 (судья позже парсит сам). Пропуск окна = честная дыра,
задним числом снимок не подменяется (файл помечается propusk).
Запуск:  python3 research_lab/fabrika/bitget_vpered.py --proverka
         python3 research_lab/fabrika/bitget_vpered.py --cikl   (в screen, лог в data/bitget_vpered.log)
"""
import datetime as dt, hashlib, json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

API = "https://api.bitget.com"
PT = "usdt-futures"
VERH = 80                       # с запасом над топ-50, чтобы удалённые/новые не выпали
D = Path(__file__).resolve().parents[1] / "data" / "bitget_vpered"
PAUZA = 0.15

def utc(): return dt.datetime.now(dt.timezone.utc)
def sha(b): return hashlib.sha256(b).hexdigest()

def get(put, **p):
    url = API + put + ("?" + urllib.parse.urlencode(p) if p else "")
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                b = r.read(); time.sleep(PAUZA)
                return json.loads(b), b, url
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(30 * (k + 1)); continue
            if e.code == 400: return None, e.read() if hasattr(e, "read") else b"", url
            time.sleep(3 * (k + 1))
        except Exception:
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"Bitget не ответил: {put} {p}")

def zapis(path, url, b):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"url": url, "poluceno": int(time.time() * 1000), "sha256": sha(b),
                            "telo": b.decode("utf-8", "replace")}, ensure_ascii=False) + "\n")

def oi_usd(t):
    try: return float(t.get("holdingAmount") or 0) * float(t.get("lastPr") or t.get("markPrice") or 0)
    except (TypeError, ValueError): return 0.0

def snimok(den):
    p = D / den.isoformat() / "tickers_2355.jsonl"
    if p.exists(): return
    j, b, url = get("/api/v2/mix/market/tickers", productType=PT)
    zapis(p, url, b)
    print(f"{utc().isoformat(timespec='seconds')} снимок {den}: тикеров {len((j or {}).get('data') or [])}", flush=True)

def verh_iz_snimka(den):
    p = D / den.isoformat() / "tickers_2355.jsonl"
    if not p.exists(): return None
    j = json.loads(json.loads(p.read_text().splitlines()[0])["telo"])
    t = sorted(j.get("data") or [], key=oi_usd, reverse=True)
    return [x["symbol"] for x in t[:VERH]]

def potok(den):
    """Поток дня den (закрыт) для монет снимка den."""
    gotovo = D / den.isoformat() / "potok.gotovo"
    if gotovo.exists(): return
    syms = verh_iz_snimka(den)
    if syms is None:
        (D / den.isoformat()).mkdir(parents=True, exist_ok=True)
        (D / den.isoformat() / "propusk").write_text("нет снимка 23:50–23:59 — вселенная дня не зафиксирована\n")
        gotovo.write_text("propusk\n"); print(f"{utc().isoformat(timespec='seconds')} {den}: ПРОПУСК снимка", flush=True); return
    ok = 0; est_den = 0
    for s in syms:
        for put, extra, imya in (("/api/v2/mix/market/taker-buy-sell", {"period": "1h"}, "taker_1h"),
                                 ("/api/v2/mix/market/taker-buy-sell", {"period": "1D"}, "taker"),
                                 ("/api/v2/mix/market/candles", {"granularity": "1Dutc", "limit": 5}, "svechi_utc"),
                                 ("/api/v2/mix/market/candles", {"granularity": "1D", "limit": 5}, "svechi"),
                                 ("/api/v2/mix/market/history-fund-rate", {"pageSize": 10}, "fanding")):
            j, b, url = get(put, symbol=s, productType=PT, **extra)
            zapis(D / den.isoformat() / f"{imya}.jsonl", url, b)
            ok += j is not None
            if imya == "taker_1h" and j:   # 1D у Bitget = пекинские сутки (16:00 UTC); UTC-день собираем из 24 часов
                nach = int(dt.datetime(den.year, den.month, den.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
                chasy = {int(x.get("ts", 0)) for x in (j.get("data") or [])}
                est_den += all(nach + 3600000 * h in chasy for h in range(24))
    gotovo.write_text(json.dumps({"monet": len(syms), "otvetov_ok": ok, "taker_s_dnem": est_den, "vremya": utc().isoformat()}) + "\n")
    print(f"{utc().isoformat(timespec='seconds')} поток {den}: монет {len(syms)}, ответов ок {ok}/{5 * len(syms)}, полный UTC-день потока у {est_den}", flush=True)

def chasovoy(seychas):
    """Каждые 6 ч: часовой поток (API отдаёт последние 30 ч) по монетам последнего снимка.
    Окна перекрываются, поэтому сон Mac до ~24 ч не рвёт UTC-сутки. Судья склеивает часы по ts."""
    metka = seychas.strftime("%Y-%m-%dT%H")
    gotovo = D / "chasovoy" / f"{metka}.gotovo"
    if gotovo.exists(): return
    for k in range(3):
        syms = verh_iz_snimka(seychas.date() - dt.timedelta(days=k))
        if syms: break
    if not syms: return
    for s in syms:
        j, b, url = get("/api/v2/mix/market/taker-buy-sell", symbol=s, productType=PT, period="1h")
        zapis(D / "chasovoy" / f"{seychas.date().isoformat()}.jsonl", url, b)
    gotovo.write_text(utc().isoformat() + "\n")
    print(f"{utc().isoformat(timespec='seconds')} часовой поток {metka}: монет {len(syms)}", flush=True)

def shag(seychas):
    if seychas.hour % 6 == 0 and seychas.minute >= 20 or seychas.hour % 6 in (1, 2):
        chasovoy(seychas.replace(hour=seychas.hour - seychas.hour % 6))
    if seychas.hour == 23 and seychas.minute >= 50:
        snimok(seychas.date())
    if seychas.hour >= 0 and (seychas.hour, seychas.minute) >= (0, 15):
        vchera = seychas.date() - dt.timedelta(days=1)
        if vchera >= START: potok(vchera)

START = dt.date(2026, 10, 6)     # первый снимок — вечер 06.10; всё раньше не наше

def proverka():
    j, b, _ = get("/api/v2/mix/market/tickers", productType=PT)
    t = (j or {}).get("data") or []
    top = sorted(t, key=oi_usd, reverse=True)[:5]
    print("тикеров USDT-M:", len(t), "| топ-5 по OI$:", [(x["symbol"], round(oi_usd(x) / 1e6)) for x in top])
    print("поля тикера:", sorted(t[0].keys()) if t else None)
    for put, extra in (("/api/v2/mix/market/taker-buy-sell", {"period": "1h"}),
                       ("/api/v2/mix/market/taker-buy-sell", {"period": "1D"}),
                       ("/api/v2/mix/market/candles", {"granularity": "1Dutc", "limit": 2}),
                       ("/api/v2/mix/market/candles", {"granularity": "1D", "limit": 2}),
                       ("/api/v2/mix/market/history-fund-rate", {"pageSize": 2})):
        j, b, _ = get(put, symbol="BTCUSDT", productType=PT, **extra)
        print(put, "→", b[:300].decode("utf-8", "replace"))
        if "taker" in put and j and j.get("data"):
            ts = sorted(int(x["ts"]) for x in j["data"])
            f = lambda m: dt.datetime.fromtimestamp(m / 1000, dt.timezone.utc).date()
            g = lambda m: dt.datetime.fromtimestamp(m / 1000, dt.timezone.utc).isoformat(timespec="minutes")
            print("   поток", extra["period"], ": баров", len(ts), "с", g(ts[0]), "по", g(ts[-1]))
        if not j or str(j.get("code")) not in ("00000", "0"): sys.exit("ПРОВЕРКА: FAIL " + put)
    if len(t) < 100 or oi_usd(top[0]) <= 0: sys.exit("ПРОВЕРКА: FAIL tickers")
    print("ПРОВЕРКА: OK")

if __name__ == "__main__":
    if "--proverka" in sys.argv: proverka()
    elif "--cikl" in sys.argv:
        posl_puls = 0
        while True:
            try:
                s = utc(); shag(s)
                if time.time() - posl_puls >= 3600:
                    print(f"{s.isoformat(timespec='seconds')} пульс: жив", flush=True); posl_puls = time.time()
            except Exception as e:
                print(utc().isoformat(timespec="seconds"), "ошибка шага:", type(e).__name__, str(e)[:200], flush=True)
            time.sleep(60)
    else: proverka()
