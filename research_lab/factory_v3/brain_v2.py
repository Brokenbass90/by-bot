#!/usr/bin/env python3
"""brain_v2.py — BRAIN_V2_DET: детерминированный портфельный слой (17.10.2026, PREREG_BRAIN_V2_DET_2026_10_17). Shadow-only.

Четвёртая политика того же Brain Shadow (те же возможности, тот же risk_engine, та же хеш-цепочка). Без ML и без обучения
на исходах: только правила риска портфеля. Решение: TRADE / HEDGE / ABSTAIN + размер. Денег и ордеров не касается.
"""
import hashlib, json

PARAM = dict(net_max=3.0, makro_do_ch=2.0, vol_pct=0.95, vol_mnozh=0.5)
U = "UNKNOWN"


def _napr(side):
    return 1 if str(side).lower() in ("long", "buy") else -1 if str(side).lower() in ("short", "sell") else 0


def brain_v2_det(v, otkr, baza):
    """baza — BRAIN_V1 (тот же расчёт ожидания); поверх — портфельные правила. Возвращает (единиц, причины)."""
    ctx2 = (v.get("context") or {}).get("kontekst_v2") or {}
    hedge = v["sleeve"] == "ELDER"
    # 1. конфликт: противоположная позиция по тому же символу в другом рукаве
    protiv = [o for o, a in otkr if a > 0 and o["symbol"] == v["symbol"] and _napr(o["side"]) == -_napr(v["side"]) and o["sleeve"] != v["sleeve"]]
    if protiv and not hedge:
        return 0.0, ["ABSTAIN", "konflikt_simvola"]
    # 2. макро-окно перед релизом — новые не-хедж входы не открываем
    ch = ctx2.get("makro_cherez_ch")
    if not hedge and isinstance(ch, (int, float)) and 0 <= ch <= PARAM["makro_do_ch"]:
        return 0.0, ["ABSTAIN", f"makro_cherez_{ch}ch"]
    if hedge:
        if (v.get("context") or {}).get("rezhim_v1") == "BULL_TREND": return 0.0, ["ABSTAIN", "hedge_off_bull"]
        u, prich = 1.0, ["HEDGE"]
    else:
        u, prich = baza(v, otkr); prich = (["TRADE"] if u > 0 else ["ABSTAIN"]) + list(prich)
    if u <= 0: return 0.0, prich
    # 3. волатильность в верхних 5 % — половина размера
    vp = ctx2.get("vol_pct_720")
    if isinstance(vp, (int, float)) and vp >= PARAM["vol_pct"]:
        u *= PARAM["vol_mnozh"]; prich.append("vol_vysokaya")
    # 4. чистая направленность портфеля (хедж уменьшает |net| — не ограничивается)
    net = sum(_napr(o["side"]) * a for o, a in otkr)
    nov = net + _napr(v["side"]) * u
    if not hedge and abs(nov) > PARAM["net_max"] and abs(nov) > abs(net):
        u = max(0.0, PARAM["net_max"] - abs(net)); prich.append("net_cap")
        if u <= 0: return 0.0, ["ABSTAIN", "net_cap"]
    return round(u, 4), prich


SHA = hashlib.sha256(json.dumps(["BRAIN_V2_DET", PARAM, "v1"], sort_keys=True).encode()).hexdigest()
