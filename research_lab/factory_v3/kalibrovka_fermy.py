#!/usr/bin/env python3
"""kalibrovka_fermy.py — калибровка фабрики подложенным edge (мощность и ложные срабатывания). 13.10.2026.
Синтетика (ferma_shablony.xs_sintetika), отдельный реестр kalibrovka_reestr.jsonl — основной реестр и данные не трогаются.
Для каждой силы эффекта N прогонов с разными семенами через ферму с поправкой реестра на перебор:
  edge 0 bps → доля PASS = ложные срабатывания (должна быть ≈ 0);
  edge > 0   → доля PASS = мощность (какой силы эффект фабрика гарантированно видит).
    python3 research_lab/factory_v3/kalibrovka_fermy.py [N=20]
"""
import json, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from reestr_v1 import Reestr
import ferma_v1 as F

SILY = (0, 50, 103, 150, 200)                                   # 103 = размер KITY M3


def main(n=20, put=None, pisat=True):
    r = Reestr(put or Path(tempfile.mkdtemp()) / "kalibrovka.jsonl")
    r.semya("KALIBROVKA", "подложенный edge на синтетике")
    specs = []
    for e in SILY:                                              # схема по умолчанию: окно DEV, бюджет n (=20), α 0.20
        r.okno(f"SINT_E{e}", "sintetika", "2023-01-01", "2026-09-23", "DEV", byudzhet=n)
        g = f"KAL_E{e}"; r.gipoteza(g, "KALIBROVKA", f"подложенный спред {e} bps/нед", ["sintetika"]); r.perehod(g, "SCREEN", "калибровка")
        specs += [dict(id=f"{g}_{s}", gipoteza=g, okno=f"SINT_E{e}", eksperiment="ferma_shablony:xs_sintetika",
                       parametry=dict(edge_bps=e, seed=1000 * e + s), kriterii=dict(min_n=52, znak="+")) for s in range(n)]
    it = F.zapustit(specs, r, processov=2)
    rez = {}
    for e in SILY:
        x = [i for i in it if i["id"].startswith(f"KAL_E{e}_")]
        rez[f"{e}_bps"] = dict(n=len(x), pass_=sum(i["status"] == "PASS" for i in x), dolya=round(sum(i["status"] == "PASS" for i in x) / len(x), 2))
    t_req = it[-1].get("trebuemyy_t")
    out = dict(popytok_na_okne=n, alpha_okna=0.20, trebuemyy_t=t_req, lozhnye_srabatyvaniya=rez["0_bps"]["dolya"],
               moshchnost={k: v["dolya"] for k, v in rez.items() if k != "0_bps"}, detali=rez)
    if pisat:
        p = HERE.parent / "data" / "factory_v3" / "KALIBROVKA_FERMY.json"; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
