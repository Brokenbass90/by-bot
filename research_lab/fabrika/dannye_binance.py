#!/usr/bin/env python3
"""dannye_binance.py — загрузка публичного архива Binance USD-M (data.binance.vision, без ключей) для
PREREG_TOLPA_BINANCE_REPLICATION_2021_2022.md. Написано и закоммичено ДО скачивания данных.

Что берём (только компактные значения, сырые zip не храним):
  metrics (дневные файлы, 5 мин) 2021-06-25…2022-12-31 → на каждый день:
      r00  = count_long_short_ratio в 00:00 UTC (допуск: первая точка в [00:00, 00:15]) — для L1 (день d−1);
      r22  = count_long_short_ratio в 22:00 UTC (последняя точка в [21:45, 22:00]) — для TOLPA_1D;
      oi   = sum_open_interest_value в 23:55 UTC (последняя точка в [23:40, 23:55]) — для PIT-вселенной дня d+1.
  klines 1d (месячные) 2021-04…2023-01; fundingRate (месячные) 2021-06…2023-01.
Символы — листинг архива metrics (снятые с торгов включены, они там остаются). Только бессрочные …USDT
(как Bybit linear USDT), без датированных (с «_»).

Старт с самопроверки на BTCUSDT (один файл каждого вида): не разобрали → СТОП, ничего не качаем.
Возобновляемо: готовый символ (data/binance/gotovo/SYM) пропускается. В конце — data/binance/gotovo.json.

    python3 research_lab/fabrika/dannye_binance.py            скачать
    python3 research_lab/fabrika/dannye_binance.py --proverka только самопроверка
"""
import csv, datetime as dt, io, json, re, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data" / "binance"
ARH = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix="
M_OT, M_DO = dt.date(2021, 6, 25), dt.date(2022, 12, 31)
K_MES = [f"{y}-{m:02d}" for y in (2021, 2022, 2023) for m in range(1, 13)
         if "2021-04" <= f"{y}-{m:02d}" <= "2023-01"]
F_MES = [m for m in K_MES if m >= "2021-06"]
POTOKI = 12


def get(url, popytki=4):
    url = urllib.parse.quote(url, safe=":/?&=%")   # символы с не-ASCII именами (03.10: 哈基米USDT уронил загрузку)
    for k in range(popytki):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research"}), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 451):
                sys.exit(f"СТОП: {e.code} на {url} — доступ закрыт, не долбим")
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"не скачалось после {popytki} попыток: {url}")


def listing(prefix):
    """S3-листинг: (подпапки, ключи), с пагинацией."""
    papki, klyuchi, marker = [], [], ""
    while True:
        x = get(S3 + prefix + (f"&marker={marker}" if marker else "")).decode()
        papki += re.findall(r"<CommonPrefixes><Prefix>(.*?)</Prefix>", x)
        klyuchi += re.findall(r"<Key>(.*?)</Key>", x)
        if "<IsTruncated>true</IsTruncated>" not in x:
            return papki, klyuchi
        m = re.search(r"<NextMarker>(.*?)</NextMarker>", x)
        marker = m.group(1) if m else (klyuchi or papki)[-1]


def csv_iz_zip(b):
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        return list(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), "utf-8")))


def fl(s):
    try:
        v = float(s); return v if v == v else None
    except (TypeError, ValueError):
        return None


def metrics_den(b):
    rows = csv_iz_zip(b); h = rows[0]
    ic, ir, io_ = h.index("create_time"), h.index("count_long_short_ratio"), h.index("sum_open_interest_value")
    toch = []
    for r in rows[1:]:
        try:
            t = dt.datetime.strptime(r[ic][:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        toch.append((t.hour * 60 + t.minute, fl(r[ir]), fl(r[io_])))
    toch.sort()
    def pervaya(a, b, k):
        v = [p[k] for p in toch if a <= p[0] <= b and p[k] is not None]; return v[0] if v else None
    def posled(a, b, k):
        v = [p[k] for p in toch if a <= p[0] <= b and p[k] is not None]; return v[-1] if v else None
    return [pervaya(0, 15, 1), posled(21 * 60 + 45, 22 * 60, 1), posled(23 * 60 + 40, 23 * 60 + 55, 2)]


def klines_mes(b):
    out = []
    for r in csv_iz_zip(b):
        if r and r[0].strip().isdigit():
            out.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
    return out


def funding_mes(b):
    rows = csv_iz_zip(b); out = []
    for r in rows:
        if r and r[0].strip().isdigit():
            v = fl(r[-1])
            if v is not None:
                out.append([int(r[0]), v])
    return out


def url_m(s, d): return f"{ARH}data/futures/um/daily/metrics/{s}/{s}-metrics-{d}.zip"
def url_k(s, m): return f"{ARH}data/futures/um/monthly/klines/{s}/1d/{s}-1d-{m}.zip"
def url_f(s, m): return f"{ARH}data/futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{m}.zip"


def proverka():
    m = metrics_den(get(url_m("BTCUSDT", "2021-12-01")))
    k = klines_mes(get(url_k("BTCUSDT", "2021-12")))
    f = funding_mes(get(url_f("BTCUSDT", "2021-12")))
    print("самопроверка BTCUSDT: metrics 2021-12-01 [r00, r22, oi23:55] =", m)
    print(f"  klines 2021-12: {len(k)} баров, первый {k[:1]}; funding 2021-12: {len(f)} ставок, первая {f[:1]}")
    if None in m or not (28 <= len(k) <= 31) or not (80 <= len(f) <= 100):
        sys.exit("СТОП: самопроверка не прошла — формат архива не тот, что ожидался; ничего не качаю")
    print("самопроверка OK")


def simvol(s):
    gf = D / "gotovo" / s
    if gf.exists():
        return json.loads(gf.read_text())
    dni = []
    for god in ("2021-", "2022-"):
        _, kl = listing(f"data/futures/um/daily/metrics/{s}/{s}-metrics-{god}")
        for k in kl:
            m = re.search(r"metrics-(\d{4}-\d\d-\d\d)\.zip$", k)
            if m and M_OT.isoformat() <= m.group(1) <= M_DO.isoformat():
                dni.append(m.group(1))
    res = {"s": s, "dney_metrics": len(dni)}
    if dni:
        def odin(d):
            b = get(url_m(s, d))
            return d, (metrics_den(b) if b else None)
        with ThreadPoolExecutor(POTOKI) as ex:
            met = {d: v for d, v in ex.map(odin, sorted(dni)) if v}
        with ThreadPoolExecutor(POTOKI) as ex:
            kl = [b for b in ex.map(lambda m: get(url_k(s, m)), K_MES)]
            fr = [b for b in ex.map(lambda m: get(url_f(s, m)), F_MES)]
        kl = sorted({r[0]: r for b in kl if b for r in klines_mes(b)}.values())
        fr = sorted({r[0]: r for b in fr if b for r in funding_mes(b)}.values())
        for pap, obj in (("metrics", met), ("klines", kl), ("funding", fr)):
            (D / pap).mkdir(parents=True, exist_ok=True)
            (D / pap / f"{s}.json").write_text(json.dumps(obj))
        res.update(dney_ok=len(met), barov=len(kl), stavok=len(fr))
    (D / "gotovo").mkdir(parents=True, exist_ok=True)
    gf.write_text(json.dumps(res))
    return res


def main():
    proverka()
    if "--proverka" in sys.argv:
        return
    papki, _ = listing("data/futures/um/daily/metrics/")
    vse = sorted({p.rstrip("/").split("/")[-1] for p in papki})
    sim = [s for s in vse if s.endswith("USDT") and "_" not in s]
    print(f"символов в архиве metrics: {len(vse)}; бессрочных USDT: {len(sim)}")
    itog = []
    for n, s in enumerate(sim, 1):
        r = simvol(s); itog.append(r)
        print(f"[{n}/{len(sim)}] {s}: {r}", flush=True)
    s_dannymi = [r for r in itog if r.get("dney_ok")]
    (D / "gotovo.json").write_text(json.dumps(dict(
        kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        simvolov=len(sim), s_metrics=len(s_dannymi),
        dney_metrics=sum(r["dney_metrics"] for r in s_dannymi), dney_ok=sum(r["dney_ok"] for r in s_dannymi)), indent=1))
    print("ГОТОВО:", (D / "gotovo.json").read_text())


if __name__ == "__main__":
    main()
