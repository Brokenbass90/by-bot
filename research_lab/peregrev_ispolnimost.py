#!/usr/bin/env python3
"""peregrev_ispolnimost.py — ворота исполнимости семейства PEREGREV_HVOSTA (без торговых действий).

Сигнал, пороги, окна SHORT_HVOST_FANDING и C8 не трогаются. Меряется только одно: можно ли
исполнить шорт малоликвидного перпа по публичным стаканам без съедения edge.

Шаг 1 (Mac, публичный REST, без ключей):  --meta     статус, мин./макс. ордер, первый лимит риска
Шаг 2 (Mac, существующий сборщик, ограничен по времени):
    scripts/collect_bybit_orderbook_density.py --depth 200 --impact-notionals 100,500,2000 ...
Шаг 3 (где угодно):                       без флагов → вердикт EXECUTABLE / TOO_EXPENSIVE / INSUFFICIENT_DATA

Критерии объявлены ДО сбора данных (2026-09-30):
  издержка круга = impact продажи в биды + impact покупки из асков (от mid) + 11 bps тейкер-комиссий;
  символ учитывается при ≥ 60 снимках (30 мин при шаге 30 с); отсутствие глубины = бесконечная издержка;
  для суммы N: EXECUTABLE, если медиана по символам p90-издержки ≤ 60 bps и ≥ 80% символов шортопригодны;
  покрыто < 20 символов или нет --meta → INSUFFICIENT_DATA; иначе TOO_EXPENSIVE.
  Итог = вердикт на $100; ёмкость = наибольшая N с EXECUTABLE.
  60 bps ≈ 20% исторического сырого edge семейства (C8 +315 bps, SHORT_HVOST ≈ +400 bps после штрафа).
"""
import json, sys, time, urllib.request
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "research_lab/data/peregrev_meta.json"
STAKAN = ROOT / "runtime/orderbook/peregrev_ispolnimost.jsonl"
# заморожено: символы поиска SHORT_HVOST (14) + 16 самых частых символов C8 в 2026 году
SIMVOLY = ["BLESSUSDT", "BICOUSDT", "ACEUSDT", "USELESSUSDT", "AKEUSDT", "CYSUSDT", "HFTUSDT", "VELVETUSDT",
           "MAGMAUSDT", "APRUSDT", "HUSDT", "BEATUSDT", "BTRUSDT", "BTWUSDT",
           "LYNUSDT", "ARIAUSDT", "FOLKSUSDT", "TRUTHUSDT", "PTBUSDT", "ASPUSDT", "PLAYSOUTUSDT", "STBLUSDT",
           "SPORTFUNUSDT", "XNYUSDT", "AIOUSDT", "QUSDT", "THEUSDT", "1000TAGUSDT", "INXUSDT", "BMNRUSDT"]
SUMMY = [100, 500, 2000]
KOMISSIYA_BPS, POROG_BPS, MIN_SNIMKOV, MIN_SIMVOLOV, MIN_DOLYA_SHORT = 11.0, 60.0, 60, 20, 0.8


def get(path, **q):
    url = "https://api.bybit.com/v5/market/" + path + "?" + "&".join(f"{k}={v}" for k, v in q.items())
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read())


def meta():
    out = {}
    for s in SIMVOLY:
        try:
            ii = (get("instruments-info", category="linear", symbol=s).get("result") or {}).get("list") or []
            rl = (get("risk-limit", category="linear", symbol=s).get("result") or {}).get("list") or []
            t = (get("tickers", category="linear", symbol=s).get("result") or {}).get("list") or []
            i0 = ii[0] if ii else {}
            lf = i0.get("lotSizeFilter") or {}
            out[s] = dict(status=i0.get("status"), min_notional=float(lf.get("minNotionalValue") or 0),
                          max_mkt_qty=float(lf.get("maxMktOrderQty") or 0),
                          price=float(t[0]["lastPrice"]) if t else None,
                          risk_limit_1=float(rl[0]["riskLimitValue"]) if rl else None)
        except Exception as e:
            out[s] = dict(oshibka=str(e))
        time.sleep(0.15)
    META.write_text(json.dumps({"kogda": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "simvoly": out},
                               ensure_ascii=False, indent=1))
    print("записано", META)


def shortoprigoden(m, n):
    if not m or m.get("status") != "Trading" or not m.get("price"):
        return False
    return m["min_notional"] <= n and m["max_mkt_qty"] * m["price"] >= n and (m.get("risk_limit_1") or 0) >= n


def verdikt():
    if not STAKAN.exists():
        return print("INSUFFICIENT_DATA: нет файла стаканов", STAKAN)
    mt = json.loads(META.read_text())["simvoly"] if META.exists() else None
    rt = {s: {n: [] for n in SUMMY} for s in SIMVOLY}; spred = {s: [] for s in SIMVOLY}
    for line in STAKAN.open():
        r = json.loads(line); s = r.get("symbol"); ib = r.get("impact_bps")
        if s not in rt or not ib:
            continue
        spred[s].append(r["spread_bps"])
        for n in SUMMY:
            a, b = ib["sell"].get(str(n)), ib["buy"].get(str(n))
            rt[s][n].append(1e6 if a is None or b is None else a + b + KOMISSIYA_BPS)   # 1e6 = глубины не хватило
    pokryty = [s for s in SIMVOLY if len(rt[s][SUMMY[0]]) >= MIN_SNIMKOV]
    print(f"символов с ≥{MIN_SNIMKOV} снимками: {len(pokryty)} из {len(SIMVOLY)}")
    print(f"{'символ':<14}{'спред':>7}" + "".join(f"{'$'+str(n)+' мед/p90':>18}" for n in SUMMY) + "  шорт($100)")
    for s in pokryty:
        cells = "".join(f"{np.median(rt[s][n]):>9.0f}/{np.percentile(rt[s][n], 90):<8.0f}" for n in SUMMY)
        print(f"{s:<14}{np.median(spred[s]):>7.1f}{cells}  {shortoprigoden((mt or {}).get(s), 100) if mt else '—'}")
    itog = {}
    for n in SUMMY:
        if len(pokryty) < MIN_SIMVOLOV or mt is None:
            itog[n] = "INSUFFICIENT_DATA"; continue
        p90 = float(np.median([np.percentile(rt[s][n], 90) for s in pokryty]))
        dolya = np.mean([shortoprigoden(mt.get(s), n) for s in pokryty])
        itog[n] = "EXECUTABLE" if p90 <= POROG_BPS and dolya >= MIN_DOLYA_SHORT else "TOO_EXPENSIVE"
        print(f"${n}: медиана p90-издержки {p90:.0f} bps (порог {POROG_BPS:.0f}), шортопригодны {dolya:.0%} → {itog[n]}")
    emk = max([n for n in SUMMY if itog[n] == "EXECUTABLE"], default=None)
    print(f"ИТОГ: {itog[SUMMY[0]]}; ёмкость на одну позицию: {'$' + str(emk) if emk else 'нет'}")


if __name__ == "__main__":
    meta() if "--meta" in sys.argv else verdikt()
