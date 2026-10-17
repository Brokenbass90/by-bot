#!/usr/bin/env python3
"""okna_proverka.py — автоматическая проверка независимости окон (17.10.2026, замечание PM).

1. Окна реестра с ролью DEV/CONFIRM не должны пересекаться по датам, если одно используется как РЕПЛИКАЦИЯ другого.
2. Файл событий заявки должен целиком лежать внутри окна заявки (иначе — утечка данных другого периода).
3. Манифест окон: границы, источник баров и sha — data/factory_v3/OKNA_MANIFEST.json.
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "factory_v3"))
from reestr_v1 import PUT_PO_UMOLCHANIYU

def okna():
    return {r["id"]: r for r in (json.loads(s) for s in PUT_PO_UMOLCHANIYU.read_text().splitlines() if s.strip()) if r.get("tip") == "okno"}

def _ms(d, konec=False):
    t = dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc)
    return int(((t + dt.timedelta(days=1)) if konec else t).timestamp() * 1000)

def peresekayutsya(a, b):
    O = okna(); A, B = O[a], O[b]
    return not (_ms(A["konec"], True) <= _ms(B["nachalo"]) or _ms(B["konec"], True) <= _ms(A["nachalo"]))

def sobytiya_v_okne(fayl, okno):
    O = okna()[okno]; s, e = _ms(O["nachalo"]), _ms(O["konec"], True)
    ev = json.loads((LAB / fayl).read_text()); vne = [x["t_ms"] for x in ev if not s <= x["t_ms"] < e]
    return dict(vsego=len(ev), vne_okna=len(vne), ok=not vne)

def manifest():
    istochniki = {"KRIPTO_D1_2021H2_2022": "data/h1/BTCUSDT_B21.npz", "KRIPTO_D1_2023_2026Q3": "data/h1/BTCUSDT.npz",
                  "KRIPTO_H1M5_2023_2026Q3": "data/h1/BTCUSDT.npz"}
    out = {}
    for k, o in okna().items():
        src = istochniki.get(k); p = LAB / src if src else None
        out[k] = dict(nachalo=o["nachalo"], konec=o["konec"], rol=o["rol"], bary=src,
                      bary_sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p and p.exists() else None)
    out["nezavisimost"] = {"KRIPTO_D1_2021H2_2022 vs KRIPTO_D1_2023_2026Q3":
                           "OK" if not peresekayutsya("KRIPTO_D1_2021H2_2022", "KRIPTO_D1_2023_2026Q3") else "PERESECHENIE"}
    (LAB / "data/factory_v3/OKNA_MANIFEST.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out

if __name__ == "__main__":
    print(json.dumps(manifest(), ensure_ascii=False, indent=1))
