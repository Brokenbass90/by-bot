#!/usr/bin/env python3
"""glubina_istorii.py — проба глубины истории до 2023 для HOLDOUT_2020_2022 (TOLPA, C8). 03.10.
ТОЛЬКО ПРОВЕРКА НАЛИЧИЯ ДАННЫХ: ни одной доходности, ни одного сигнала, ничего не сохраняет, кроме отчёта о глубине.

Вопросы (условия менеджера: без них окно не используется):
  1. Отдаёт ли Bybit до 2023: дневные свечи, суточный OI, долю лонг-аккаунтов (account-ratio 1d и 1h)?
  2. Восстановима ли PIT топ-50 по OI: сколько живых сегодня бессрочных USDT-контрактов запущено до каждой даты
     (паспорт launchTime). Снятые с торгов Bybit не отдаёт (известно с 30.09) — для 2020–2022 это главный риск.
  3. Доступен ли Binance data.binance.vision для снятых монет (LUNA, FTT) — альтернатива без выживаемости.

    .venv/bin/python3 research_lab/glubina_istorii.py
"""
import datetime as dt, json, time, urllib.parse, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parent
B = "https://api.bybit.com/v5/market/"
T0 = int(dt.datetime(2019, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
SIMV = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "LINKUSDT", "DOGEUSDT", "SOLUSDT", "AVAXUSDT", "LTCUSDT"]


def get(path, **q):
    try:
        d = json.loads(urllib.request.urlopen(B + path + "?" + urllib.parse.urlencode(q), timeout=20).read())
        return d.get("result") if d.get("retCode") == 0 else {"_oshibka": d.get("retMsg")}
    except Exception as e:
        return {"_oshibka": str(e)[:80]}


def samaya_rannyaya(path, pole_ts, interval_key, interval, sym, limit):
    """идём назад от 2023-01-01, пока биржа отдаёт; возвращаем самую раннюю дату и число точек до 2023"""
    end, vse = T1 - 1, set()
    for _ in range(60):
        r = get(path, category="linear", symbol=sym, **({interval_key: interval} if interval_key else {}),
                startTime=T0, endTime=end, limit=limit, **({"start": T0, "end": end} if path == "kline" else {}))
        rows = (r or {}).get("list") or []
        if not rows:
            break
        ts = [int(x[0]) if isinstance(x, list) else int(x[pole_ts]) for x in rows]
        vse.update(ts)
        if min(ts) >= end:
            break
        end = min(ts) - 1; time.sleep(0.15)
    return (dt.datetime.fromtimestamp(min(vse) / 1000, dt.timezone.utc).date().isoformat() if vse else None), len(vse)


def main():
    print("1) ГЛУБИНА РЯДОВ ДО 2023 (самая ранняя дата, точек до 2023-01-01)")
    for s in SIMV:
        sv = samaya_rannyaya("kline", None, "interval", "D", s, 1000)
        oi = samaya_rannyaya("open-interest", "timestamp", "intervalTime", "1d", s, 200)
        l1d = samaya_rannyaya("account-ratio", "timestamp", "period", "1d", s, 500)
        l1h = samaya_rannyaya("account-ratio", "timestamp", "period", "1h", s, 500)
        print(f"  {s:9s} свечи D {sv}   OI 1d {oi}   long/short 1d {l1d}   long/short 1h {l1h}", flush=True)
    print("\n2) PIT-ВСЕЛЕННАЯ: живых сегодня бессрочных USDT-контрактов, запущенных до даты (паспорт)")
    p = json.load(open(LAB / "data/basis/pasport_linear.json"))["spisok"]
    for d in ("2020-06-01", "2021-01-01", "2021-06-01", "2022-01-01", "2022-06-01", "2023-01-01"):
        t = int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        print(f"  {d}: {sum(1 for x in p if x.get('launchTime') and x['launchTime'] < t)}")
    print("  снятые с торгов (LUNA, FTT, SRM …) в паспорте Bybit отсутствуют — для них истории нет")
    print("\n3) BINANCE data.binance.vision для снятых монет (только наличие файла)")
    for url in ("https://data.binance.vision/data/futures/um/daily/metrics/LUNAUSDT/LUNAUSDT-metrics-2022-05-01.zip",
                "https://data.binance.vision/data/futures/um/daily/metrics/FTTUSDT/FTTUSDT-metrics-2022-11-01.zip",
                "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2021-12-01.zip",
                "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2021-06-01.zip"):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20)
            print(f"  есть ({r.headers.get('Content-Length')} байт): {url.split('/')[-1]}")
        except Exception as e:
            print(f"  нет ({str(e)[:40]}): {url.split('/')[-1]}")
    print("\nНичего не посчитано и не сохранено, кроме этого отчёта. Решение о HOLDOUT — после него, до скачивания.")


if __name__ == "__main__":
    main()
