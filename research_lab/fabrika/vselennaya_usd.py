"""vselennaya_usd.py — PIT-вселенная крипты: топ-50 по открытому интересу В ДОЛЛАРАХ.

Старая вселенная (basis/vselennaya_pit.json) ранжирует OI в штуках монеты — в неё
попадают монеты с низкой ценой за штуку (SHIB, BTT, BABYDOGE…), а BTC/ETH нет.
Эта ранжирует OI_штук × цену закрытия, обе величины известны СТРОГО ДО даты
(последняя точка OI с ts < даты, не старше 7 суток; последнее закрытие с ts < даты).
Ряды: basis/oi_sutochnyy/*.json, цены: pit_daily/*.json (dannye_pit_kripto.py --vse).
    python3 vselennaya_usd.py      → data/basis/vselennaya_pit_usd50.json
"""
from __future__ import annotations
import datetime as dt, json
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
TOP_N, DEN = 50, 86400000
OUT = LAB / "data/basis/vselennaya_pit_usd50.json"


def main():
    oi, ceny, bez_ceny = {}, {}, []
    for f in (LAB / "data/basis/oi_sutochnyy").glob("*.json"):
        d = json.load(open(f))
        if d["ryad"]:
            oi[d["symbol"]] = sorted((int(t), float(v)) for t, v in d["ryad"])
    for s in oi:
        p = LAB / f"data/pit_daily/{s}.json"
        if p.exists():
            ceny[s] = sorted((int(r[0]), float(r[4])) for r in json.load(open(p))["daily"])
        else:
            bez_ceny.append(s)
    dolya = len(bez_ceny) / max(1, len(oi))
    if dolya > 0.05:
        print(f"СТОП: у {len(bez_ceny)} из {len(oi)} инструментов с OI нет цен ({dolya:.0%}). "
              "Вселенная из одних скачанных монет была бы смещённой — файл НЕ записан.\n"
              "Сначала: python3 dannye_pit_kripto.py --vse")
        if OUT.exists():
            OUT.replace(OUT.with_suffix(".NEPOLNAYA.json"))
            print(f"прежний файл отложен как {OUT.with_suffix('.NEPOLNAYA.json').name}")
        return 1
    nach = int(dt.datetime(2023, 1, 2, tzinfo=dt.timezone.utc).timestamp() * 1000)
    kon = max(t for r in oi.values() for t, _ in r) + DEN
    sostav = {}
    idx_o = {s: 0 for s in oi}; idx_c = {s: 0 for s in ceny}
    t = nach
    while t <= kon:
        ocenki = []
        for s, r in oi.items():
            if s not in ceny:
                continue
            i = idx_o[s]
            while i < len(r) and r[i][0] < t: i += 1
            idx_o[s] = i
            if i == 0 or t - r[i - 1][0] > 7 * DEN:
                continue
            c = ceny[s]; j = idx_c[s]
            while j < len(c) and c[j][0] < t: j += 1
            idx_c[s] = j
            if j == 0 or t - c[j - 1][0] > 7 * DEN:
                continue
            ocenki.append((r[i - 1][1] * c[j - 1][1], s))
        if ocenki:
            ocenki.sort(reverse=True)
            sostav[dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m-%d")] = [s for _, s in ocenki[:TOP_N]]
        t += DEN
    vse = sorted({s for v in sostav.values() for s in v})
    OUT.write_text(json.dumps({"schema_id": "pit_universe_usd_oi_v1",
                               "pravilo": f"top-{TOP_N} по OI в долларах (штуки × закрытие), обе величины строго до даты, не старше 7 суток",
                               "bez_ceny": sorted(bez_ceny), "s_cenoy": len(ceny), "dat": len(sostav), "unikalnyh_simvolov": len(vse),
                               "simvoly": vse, "sostav": sostav}, ensure_ascii=False, indent=1))
    print(f"дат {len(sostav)}, символов {len(vse)}, инструментов с OI без цены: {len(bez_ceny)}")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
