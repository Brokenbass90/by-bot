#!/usr/bin/env python3
"""fanding_hvost.py — судья предрегистрации SHORT_HVOST_FANDING (PREREG_SHORT_HVOST_FANDING_2026_09_30.md).

Ничего не торгует и не пишет. Читает два работающих леджера теней фандинга,
берёт ТОЛЬКО исходы после заморозки и выносит вердикт по заранее записанным
правилам. Правила ниже менять нельзя: это и есть предрегистрация.

    python3 research_lab/fanding_hvost.py            # вердикт на будущих данных
    python3 research_lab/fanding_hvost.py --poisk    # выборка поиска (до заморозки), только справка
"""
import json, math, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGERY = ["runtime/funding_positioning_dynamic_shadow_ledger.jsonl",
           "runtime/funding_positioning_post_n42_frozen_ledger.jsonl"]
ZAMOROZKA_MS = 1790769600000            # 2026-09-30 12:00 UTC: всё раньше — выборка поиска
NACHALO_POISKA_MS = 1786467566137       # evidence_epoch леджеров
NE_HVOST = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT",
            "AVAXUSDT", "SUIUSDT", "DOTUSDT", "HYPEUSDT", "NEARUSDT", "AAVEUSDT", "UNIUSDT", "1000PEPEUSDT",
            "ENAUSDT", "ARBUSDT", "TRUMPUSDT", "ZECUSDT", "HBARUSDT", "XAUTUSDT"}
SHTRAF_BPS = 30.0                       # тейкер-выход и проскальзывание на тонком хвосте
MIN_N, MAX_N, PorogT, MAX_DOLYA = 30, 60, 2.0, 0.5

def iskhody(ot, do):
    u = {}
    for fn in LEDGERY:
        p = ROOT / fn
        if not p.exists():
            continue
        for line in p.open():
            if not line.strip():
                continue
            r = json.loads(line)
            if (r.get("record_type") == "outcome" and r.get("status") == "closed" and r.get("side") == -1
                    and r.get("symbol") not in NE_HVOST and ot <= r["event_ts"] < do):
                u[(r["symbol"], r["event_ts"])] = r        # дубли записи и общие события — один раз
    # хронологически: при MAX_N берутся первые 60 событий после заморозки
    return [(k[0], v["net_btc_hedged_bps"] - SHTRAF_BPS, k[1]) for k, v in sorted(u.items(), key=lambda kv: kv[0][1])]

MIN_DNEY = 15                           # поправка 2026-10-01 (до первого будущего события): t считаем
                                        # по кластерам UTC-дней — удержания 16 ч перекрываются, события
                                        # одного дня зависимы. На выборке поиска t 2.64 -> 1.19 по дням.

def t_po_dnyam(x):
    d = {}
    for _, b, ts in x:
        d.setdefault(ts // 86_400_000, []).append(b)
    dm = [st.fmean(z) for z in d.values()]
    if len(dm) < 3 or st.stdev(dm) == 0:
        return 0.0, len(dm)
    return st.fmean(dm) / st.stdev(dm) * math.sqrt(len(dm)), len(dm)

def verdikt(x):
    n = len(x)
    if n < MIN_N:
        return "ЖДЁМ", f"n={n} из {MIN_N}"
    v = [b for _, b, _ in x[:MAX_N]]; n = len(v)
    m = st.fmean(v); t, dney = t_po_dnyam(x[:MAX_N])
    plus = {}
    for s, b, _ in x[:MAX_N]:
        plus[s] = plus.get(s, 0.0) + b
    pos = sum(b for b in plus.values() if b > 0) or 1e-9
    dolya = max(plus.values()) / pos
    stroka = f"n={n} dney={dney} mean={m:.0f} med={st.median(v):.0f} t_dni={t:.2f} max_dolya={dolya:.2f}"
    if m <= 0:
        return "FAIL", stroka
    if t >= PorogT and dney >= MIN_DNEY and st.median(v) > 0 and dolya <= MAX_DOLYA:
        return "PASS", stroka
    return ("FAIL" if n >= MAX_N else "ЖДЁМ_ДО_60"), stroka

verdikt.__name__ = "verdikt"

if __name__ == "__main__":
    if "--poisk" in sys.argv:
        x = iskhody(NACHALO_POISKA_MS, ZAMOROZKA_MS)
        v = [b for _, b, _ in x]; t, dney = t_po_dnyam(x)
        print(f"ПОИСК (справка, не вердикт): n={len(v)} dney={dney} mean={st.fmean(v):.0f} med={st.median(v):.0f} "
              f"t_naivnyy={st.fmean(v)/st.stdev(v)*math.sqrt(len(v)):.2f} t_dni={t:.2f}")
    else:
        x = iskhody(ZAMOROZKA_MS, 10**14)
        print("SHORT_HVOST_FANDING:", *verdikt(x))
