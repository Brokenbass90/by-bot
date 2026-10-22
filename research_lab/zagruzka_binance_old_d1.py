"""Загрузка старой дневной истории BTC/ETH (спот Binance, бесплатный публичный архив data.binance.vision).
Окно 2017-08 … 2021-04 — фабрикой не просмотрено (в репозитории крипто-история начинается с 2021-04).
Запуск вручную из корня репозитория:  .venv/bin/python3 research_lab/zagruzka_binance_old_d1.py [СИМВОЛЫ…]
Пишет research_lab/data/binance_old_d1/{BTCUSDT,ETHUSDT}.json и manifest.json (sha256). Ничего не удаляет.
"""
import hashlib, io, json, sys, urllib.request, zipfile, datetime as dt
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "binance_old_d1"
URL = "https://data.binance.vision/data/spot/monthly/klines/{s}/1d/{s}-1d-{y}-{m:02d}.zip"
SYMS = tuple(sys.argv[1:]) or ("BTCUSDT", "ETHUSDT")


def months():
    y, m = 2017, 8
    while (y, m) <= (2021, 4):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"istochnik": "data.binance.vision spot monthly 1d", "zagruzheno": dt.datetime.utcnow().isoformat() + "Z", "faily": {}}
    for s in SYMS:
        rows, miss = [], []
        for y, m in months():
            u = URL.format(s=s, y=y, m=m)
            try:
                data = urllib.request.urlopen(u, timeout=30).read()
            except Exception as e:
                miss.append(f"{y}-{m:02d}: {e}")
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for line in z.read(z.namelist()[0]).decode().splitlines():
                    p = line.split(",")
                    if not p[0].isdigit():
                        continue
                    ts = int(p[0])
                    if ts > 10**14:  # микросекунды в новых архивах
                        ts //= 1000
                    rows.append([ts, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
        rows.sort()
        f = OUT / f"{s}.json"
        f.write_text(json.dumps(rows))
        d = lambda t: dt.datetime.utcfromtimestamp(t / 1000).date().isoformat()
        man["faily"][f.name] = {"strok": len(rows), "s": d(rows[0][0]) if rows else None, "po": d(rows[-1][0]) if rows else None,
                                "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "propuski": miss}
        print(s, len(rows), man["faily"][f.name]["s"], "…", man["faily"][f.name]["po"], "пропусков месяцев:", len(miss))
    old = json.loads((OUT / "manifest.json").read_text()) if (OUT / "manifest.json").exists() else {"faily": {}}
    old["faily"].update(man["faily"]); man["faily"] = old["faily"]
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print("готово:", OUT)


if __name__ == "__main__":
    sys.exit(main())
