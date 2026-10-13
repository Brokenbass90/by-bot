#!/usr/bin/env python3
"""validaciya_fermy.py — проверка фермы на ИЗВЕСТНЫХ кейсах (P1). 13.10.2026.
Ферма + шаблон обязаны воспроизвести уже записанные числа замороженных судей на тех же данных и окне (PRIMARY 2023-01-01…
2026-09-23). Отдельный реестр validaciya_reestr.jsonl — основной реестр и бюджеты не трогаются. Никаких новых гипотез.
  M3_PERP        → data/binance_kity/m3_rezultat.json      (известный положительный: HISTORICAL PASS, +103.2 bps, t 2.59)
  SPOT_B         → data/binance_kity/spot_rezultat.json    (известный мёртвый: −0.2 bps, t −0.01)
  SPOT_A         → data/binance_kity/spot_A_rezultat.json  (нейтральный: +40.3 bps, t 1.26)
    python3 research_lab/factory_v3/validaciya_fermy.py <SLUCHAY>   (по одному: каждый грузит все данные)
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from reestr_v1 import Reestr
import ferma_v1 as F

D = HERE.parent / "data"
SLUCHAI = {"M3_PERP": ("m3_perp", "m3_rezultat.json"), "SPOT_B": ("spot_minus_perp", "spot_rezultat.json"),
           "SPOT_A": ("spot", "spot_A_rezultat.json")}


def main(sluchay):
    priznak, etalon = SLUCHAI[sluchay]
    r = Reestr(D / "factory_v3" / "validaciya_reestr.jsonl"); S = r.sostoyanie()
    if "VALIDACIYA" not in S["semi"]: r.semya("VALIDACIYA", "воспроизведение известных вердиктов фермой")
    if "PRIMARY_KITY" not in S["okna"]: r.okno("PRIMARY_KITY", "binance_kity", "2023-01-01", "2026-09-23", "DEV", byudzhet=20)
    g = f"VAL_{sluchay}"
    if g not in S["gipotezy"]: r.gipoteza(g, "VALIDACIYA", f"воспроизведение {etalon}", ["binance_metrics", "binance_spot_taker"]); r.perehod(g, "SCREEN", "валидация")
    n_pop = sum(1 for p in r.sostoyanie()["popytki"] if p.startswith(g))
    spec = dict(id=f"{g}_{n_pop + 1}", gipoteza=g, okno="PRIMARY_KITY", eksperiment="ferma_shablony:xs_nedelya_binance",
                parametry=dict(priznak=priznak, znak=1), kriterii=dict(min_n=52, znak="+"))
    it = F.zapustit([spec], r, processov=1)[0]
    m = r.sostoyanie()["popytki"][spec["id"]]["rezultat"]["metrika"] if it["status"] in ("PASS", "FAIL") else None
    e = json.loads((D / "binance_kity" / etalon).read_text())["PRIMARY"]
    sovp = m is not None and all(m.get(k) == e.get(k) for k in ("n", "edge_bps", "t", "polovinki_bps", "syroy_bps", "verdikt"))
    rez = dict(sluchay=sluchay, status="REPRODUCED" if sovp else "MISMATCH", ferma=it,
               ferma_metrika={k: m.get(k) for k in ("n", "edge_bps", "t", "polovinki_bps", "verdikt")} if m else None,
               etalon={k: e.get(k) for k in ("n", "edge_bps", "t", "polovinki_bps", "verdikt")})
    out = D / "factory_v3" / "VALIDACIYA_FERMY.json"
    vse = json.loads(out.read_text()) if out.exists() else {}
    vse[sluchay] = rez; out.write_text(json.dumps(vse, ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1)); return 0 if sovp else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
