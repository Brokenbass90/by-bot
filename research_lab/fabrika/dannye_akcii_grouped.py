#!/usr/bin/env python3
"""dannye_akcii_grouped.py — вселенная акций США без смещения выживших (для второго семейства, 01.10).

Блокер акций (EQUITIES_SPCX_XTKG_VERDIKT_2026_09_29.md): пул отбирался по СЕГОДНЯШНЕЙ ликвидности, значит
в нём нет бумаг, переставших существовать. Обход: «сгруппированные дневки» Massive (бывш. Polygon) —
один запрос отдаёт ВСЕ бумаги, торговавшиеся в этот день. Состав на каждую дату — ровно то, что торговалось
тогда, включая будущие делистинги. Плюс справочник типов (обычные акции, активные и снятые).

Только публичные рыночные данные, ключ из configs/massive_stocks_local.env (никогда не печатается),
никаких ордеров. Тариф Basic: 5 запросов в минуту → пауза 13 с; ~2 года ≈ 520 торговых дней ≈ 2 часа.
Можно прерывать: уже скачанные дни пропускаются.

    python3 dannye_akcii_grouped.py --spravochnik     справочник CS активные + снятые (минуты)
    python3 dannye_akcii_grouped.py                   ETB-снимок Alpaca на сегодня + докачка дневок
Кладёт research_lab/data/akcii_grouped/<YYYY-MM-DD>.json и spravochnik_{active,inactive}.json.
"""
import datetime as dt, json, sys, time, urllib.error, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
OUT = LAB / "data/akcii_grouped"; OUT.mkdir(parents=True, exist_ok=True)
API = "https://api.massive.com"; PAUZA = 13.0


def kluch():
    for line in (ROOT / "configs/massive_stocks_local.env").read_text().splitlines():
        if line.strip().startswith("MASSIVE_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    sys.exit("MASSIVE_API_KEY не найден в configs/massive_stocks_local.env")


def zapros(put, k):
    req = urllib.request.Request(API + put, headers={"Authorization": f"Bearer {k}", "Accept": "application/json",
                                                     "User-Agent": "research-readonly-grouped/1.0"})
    for p in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(60); continue
            if e.code in (401, 403):
                sys.exit(f"доступ запрещён ({e.code}) — проверь тариф/ключ; путь {put.split('?')[0]}")
            time.sleep(5 * (p + 1))
        except Exception:
            time.sleep(5 * (p + 1))
    return None


def spravochnik(k):
    for active in ("true", "false"):
        vse, put = [], f"/v3/reference/tickers?market=stocks&type=CS&active={active}&limit=1000"
        while put:
            d = zapros(put, k) or {}
            vse += d.get("results") or []
            nxt = d.get("next_url")
            put = nxt.replace(API, "") if nxt else None
            print(f"  active={active}: {len(vse)}", flush=True); time.sleep(PAUZA)
        (OUT / f"spravochnik_{'active' if active == 'true' else 'inactive'}.json").write_text(json.dumps(vse))


def dnevki(k):
    den = dt.date.today() - dt.timedelta(days=730)
    while den < dt.date.today():
        p = OUT / f"{den.isoformat()}.json"
        if den.weekday() < 5 and not p.exists():
            d = zapros(f"/v2/aggs/grouped/locale/us/market/stocks/{den.isoformat()}?adjusted=true", k)
            if d is not None:
                rows = [[r.get("T"), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v"), r.get("vw"), r.get("n")]
                        for r in d.get("results") or []]
                p.write_text(json.dumps({"date": den.isoformat(), "rows": rows}))
                print(f"{den} бумаг {len(rows)}", flush=True)
            time.sleep(PAUZA)
        den += dt.timedelta(days=1)
    print("готово")


def etb_snimok():
    """01.10: снимок shortable/easy_to_borrow Alpaca на сегодня — для ATTENTION_SHORT_ETB «ETB на дату события».
    Только чтение списка активов (GET /v2/assets, paper-ключ из configs/alpaca_paper_local.env, не печатается).
    Кладёт data/etb_snimki/<YYYY-MM-DD>.json: {символ: [shortable, easy_to_borrow]}. Ордеров нет."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import materialize_alpaca_pit_daily as M
    e = M._load_env(ROOT / "configs/alpaca_paper_local.env")
    k, s = e.get("ALPACA_API_KEY_ID", ""), e.get("ALPACA_API_SECRET_KEY", "")
    if not k or not s:
        print("ETB-снимок пропущен: нет ключа Alpaca paper"); return
    p = LAB / "data/etb_snimki" / f"{dt.date.today().isoformat()}.json"; p.parent.mkdir(parents=True, exist_ok=True)
    try:
        a = M._alpaca_asset_array(k, s)
    except Exception as ex:
        print(f"ETB-снимок не получен: {type(ex).__name__}"); return
    d = {r["symbol"]: [bool(r.get("shortable")), bool(r.get("easy_to_borrow"))] for r in a if r.get("symbol")}
    p.write_text(json.dumps(d))
    print(f"ETB-снимок {p.name}: бумаг {len(d)}, ETB {sum(v[1] for v in d.values())}")


if __name__ == "__main__":
    k = kluch()
    if "--spravochnik" in sys.argv:
        spravochnik(k)
    else:
        if "--bez-etb" not in sys.argv:
            etb_snimok()
        dnevki(k)
