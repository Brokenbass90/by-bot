#!/usr/bin/env python3
"""ispolnimost.py — ворота Фабрики V2 G1/G3 (FABRIKA_V2_PEREZAPUSK_TREBOVANIYA_2026_10_12.md). Чистые функции, без сети.
G1: lev = 1/stop_pct > 100 → infeasible_stop_lev (A7, research_machine.MAX_LEV).
G3: издержки круга в R = lev·(2·fee_bps + спред_med_bps)/1e4 > 0.25 → cost_dominated. Для крипты спред — из
    data/kripto_atlas/ATLAS.json; символ без атласа (снимков < 500 или глубина < $1 000) → atlas_net (не допускается).
Возвращаемый spred_R — доля спреда в R, которую бегун вычитает из R сделки И из R каждого контроля (комиссия уже в симуляторе)."""
import json
from pathlib import Path
MAX_LEV, POTOLOK_R, MIN_SNIMKOV, MIN_GLUBINA = 100.0, 0.25, 500, 1000.0
ATLAS = Path(__file__).resolve().parents[1] / "data" / "kripto_atlas" / "ATLAS.json"
_kesh = {}


def atlas(put=ATLAS):
    if put not in _kesh:
        _kesh[put] = json.loads(Path(put).read_text())["atlas"] if Path(put).exists() else None
    return _kesh[put]


def dopusk(sym, stop_pct, fee_bps, kripto, put=ATLAS):
    """→ (ok, prichina, spred_R)."""
    if not (stop_pct > 0): return False, "infeasible_stop_lev", 0.0
    lev = 1.0 / stop_pct
    if lev > MAX_LEV: return False, "infeasible_stop_lev", 0.0
    spred = 0.0
    if kripto:
        at = atlas(put)
        z = (at or {}).get(sym)
        if not z or z["n"] < MIN_SNIMKOV or z["glubina_med_usd"] < MIN_GLUBINA: return False, "atlas_net", 0.0
        spred = float(z["spred_med_bps"])
    if lev * (2 * fee_bps + spred) / 1e4 > POTOLOK_R: return False, "cost_dominated", 0.0
    return True, "", lev * spred / 1e4
