#!/usr/bin/env python3
"""ispolnimost_v21.py — ворота исполнимости Фабрики V2.1 (PREREG_FABRIKA_VOROTA_V2_1_2026_10_18.md). Только исследование.

Почему: V2 (`ispolnimost.py`, f856c77) считала плечо как 1 / стоп — будто на сделку рискуется ВЕСЬ капитал. На часовках
золота и валют стоп 1.5·ATR ≈ 0.3 % → «плечо» 333 → отказ почти всех сигналов (ITOG_FABRIKA_KANAL_OTSKOK_2026_10_18).
Глубину крипты V2 сравнивала с фиксированными 1000 USD без связи с размером заявки.

V2.1 — та же математика R, но размер позиции из явно помеченных ИССЛЕДОВАТЕЛЬСКИХ допущений (не разрешение на риск в LIVE):
  RISK_FRAC = 0.01 (риск на сделку), KAPITAL = 1000 USD (капитал рукава);
  нотионал N = RISK_FRAC · KAPITAL / stop_pct;   требуемое плечо L = N / KAPITAL = RISK_FRAC / stop_pct.
G1' L ≤ максимум инструмента: crypto 25 (консервативно ниже 50–100 у Bybit для альтов), gold 20, fx 30 (розничные лимиты ESMA).
GL  (только крипта) N ≤ медианной глубины ВЕРХНЕГО уровня стакана (min(bid, ask) по атласу): заявка целиком исполняется
    по лучшей цене, проскальзывание сверх полуспреда = 0. Глубже верхнего уровня данных нет → такую заявку не допускаем
    (честнее отказа, чем выдуманной модели проскальзывания). Снимков атласа ≥ 500.
G3  (без изменений) издержки круга в R = (2·fee_bps + спред_bps) / stop_bps ≤ 0.25; вычитаемый спред в R = спред / stop.
    Это то же, что в V2 (lev·cost при lev = 1/stop): в единицах R размер позиции не влияет на издержки.
"""
from __future__ import annotations
import json
from pathlib import Path

import ispolnimost as V2

RISK_FRAC, KAPITAL = 0.01, 1000.0
MAX_LEV_INSTR = {"crypto": 25.0, "gold": 20.0, "fx": 30.0}
POTOLOK_R, MIN_SNIMKOV = 0.25, 500


def klass(rynok: str) -> str:
    return "crypto" if rynok.startswith("crypto") else ("gold" if rynok.startswith("gold") else "fx")


def dopusk(sym, stop_pct, fee_bps, rynok, put=V2.ATLAS, kapital=KAPITAL, risk_frac=RISK_FRAC):
    """→ (ok, prichina, spred_R). prichina: infeasible_stop | lev_instr | atlas_net | depth_lt_order | cost_dominated."""
    if not (stop_pct > 0):
        return False, "infeasible_stop", 0.0
    kl = klass(rynok)
    L = risk_frac / stop_pct
    if L > MAX_LEV_INSTR[kl]:
        return False, "lev_instr", 0.0
    spred = 0.0
    if kl == "crypto":
        at = V2.atlas(put)
        z = (at or {}).get(sym)
        if not z or z["n"] < MIN_SNIMKOV:
            return False, "atlas_net", 0.0
        N = risk_frac * kapital / stop_pct
        if N > z["glubina_med_usd"]:
            return False, "depth_lt_order", 0.0
        spred = float(z["spred_med_bps"])
    if (2 * fee_bps + spred) / (stop_pct * 1e4) > POTOLOK_R:
        return False, "cost_dominated", 0.0
    return True, "", spred / (stop_pct * 1e4)
