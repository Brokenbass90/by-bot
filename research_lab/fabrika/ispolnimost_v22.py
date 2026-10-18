#!/usr/bin/env python3
"""ispolnimost_v22.py — ворота V2.2 = V2.1 + издержки золота/FX по часам из атласа брокера (дополнение 1 к
PREREG_FABRIKA_VOROTA_V2_1_2026_10_18). Только исследование.

Почему: V2.1 брала для золота/FX одно число на рынок (fee_bps 3 / 1 на сторону). Перепрогон снова нашёл «ночной дрейф» FX,
который на реальных спредах часа 21–22 UTC убыточен (nochnoy_fx_cost_gate: NOT_EXECUTABLE, −1.72 bps на сделку).
V2.2 для золота/FX: издержки круга (bps) = p75 спреда в ЧАС ВХОДА (UTC) + медианный спред инструмента (выход, час неизвестен)
+ комиссия круга — из `data/atlas_izderzhek_FxPro-MT5_Demo.json` (демо-счёт: спреды демо могут отличаться от боевых —
раскрывается в итоге). Своп не моделируется (оптимистично для удержаний > 1 суток — раскрывается).
Сумма издержек подставляется вместо 2·fee_bps бегуна: spred_R = (издержки_круга − 2·fee_bps) / stop_bps.
Крипта — без изменений (V2.1). G1' и GL — как в V2.1.
"""
from __future__ import annotations
import datetime as dt, json
from pathlib import Path

import ispolnimost_v21 as V21

ATLAS_FX = Path(__file__).resolve().parents[1] / "data" / "atlas_izderzhek_FxPro-MT5_Demo.json"
IMYA = {"XAUUSD": "XAUUSD"}
_k = {}


def atlas_fx(put=ATLAS_FX):
    if put not in _k:
        _k[put] = json.loads(Path(put).read_text())["instrumenty"] if Path(put).exists() else None
    return _k[put]


def izderzhki_kruga_bps(sym, ts_utc_ms, put=ATLAS_FX):
    a = atlas_fx(put)
    z = (a or {}).get(IMYA.get(sym, sym))
    if not z:
        return None
    h = str(dt.datetime.fromtimestamp(ts_utc_ms / 1000, tz=dt.timezone.utc).hour)
    p75_vhod = float(z["po_chasam_utc_med_p75_bps"].get(h, [z["spred_med_bps"], z["spred_p75_bps"]])[1])
    return p75_vhod + float(z["spred_med_bps"]) + float(z.get("komissiya_krug_bps_primerno") or 0.0)


def dopusk(sym, stop_pct, fee_bps, rynok, ts_utc_ms, put=V21.V2.ATLAS, put_fx=ATLAS_FX, kapital=V21.KAPITAL):
    if V21.klass(rynok) == "crypto":
        return V21.dopusk(sym, stop_pct, fee_bps, rynok, put, kapital=kapital)
    ok, pr, _ = V21.dopusk(sym, stop_pct, 0.0, rynok, put, kapital=kapital)          # только G1'
    if not ok:
        return ok, pr, 0.0
    k = izderzhki_kruga_bps(sym, ts_utc_ms, put_fx)
    if k is None:
        return False, "atlas_fx_net", 0.0
    stop_bps = stop_pct * 1e4
    if k / stop_bps > V21.POTOLOK_R:
        return False, "cost_dominated", 0.0
    return True, "", (k - 2 * fee_bps) / stop_bps
