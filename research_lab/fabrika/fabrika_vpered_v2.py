#!/usr/bin/env python3
"""fabrika_vpered_v2.py — «Фабрика вперёд», каталог v2 (27.10.2026, Claude). Хук сторожа. Те же правила, что v1 (fabrika_vpered.py),
отдельный замороженный каталог и отдельный порог Бонферрони. Новые атомы позиционирования (сборщик binance_fanding_oi_vpered):
  fanding_den — сумма ставок фандинга за день d−1; fanding_vsplesk — она минус среднее 28 предыдущих дней;
  oi_izm1 / oi_izm7 — изменение открытого интереса ($) за 1 / 7 дней; oi_minus_cena7 — oi_izm7 − mom7 (позиции растут без цены).
Каталог: одиночные новые атомы × знак + все пары, где хотя бы один атом новый (plus/minus × знак). Пары только из v1 — в v1.
Выход data/factory_v3/vpered_v2/."""
import json, statistics as st, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika")); import fabrika_vpered as FV
FO = LAB / "data" / "binance_fanding_oi_vpered"; OUT = LAB / "data" / "factory_v3" / "vpered_v2"
NOVYE = ["fanding_den", "fanding_vsplesk", "oi_izm1", "oi_izm7", "oi_minus_cena7"]; ATOMY = FV.ATOMY + NOVYE
_kesh = {}

def _ryad(vid, sym):
    k = (vid, sym)
    if k not in _kesh:
        p = FO / vid / f"{sym}.json"; _kesh[k] = {int(r[0]): r for r in json.load(open(p))} if p.exists() else {}
    return _kesh[k]

def katalog():
    k = {}
    for a in NOVYE:
        for z in (1, -1): k[f"{a}|{z:+d}"] = dict(formula=a, znak=z, avtor="setka", kontrol=True)
    for i, a in enumerate(ATOMY):
        for b in ATOMY[i + 1:]:
            if a not in NOVYE and b not in NOVYE: continue
            for op in ("plus", "minus"):
                for z in (1, -1): k[f"{op}({a},{b})|{z:+d}"] = dict(formula=[op, a, b], znak=z, avtor="setka", kontrol=False)
    return k

def atomy_dnya(r, t):
    v = FV.atomy_dnya(r, t)
    if v is None: return None
    sym = r.get("_sym")
    f, o = _ryad("fanding", sym), _ryad("oi", sym)
    v["fanding_den"] = f[t][1] if t in f else None
    pr = [f[t - i * FV.DEN][1] for i in range(1, 29) if t - i * FV.DEN in f]
    v["fanding_vsplesk"] = v["fanding_den"] - st.mean(pr) if v["fanding_den"] is not None and len(pr) >= 20 else None
    def oi(d): return o[d][2] if d in o and o[d][2] else None
    v["oi_izm1"] = oi(t) / oi(t - FV.DEN) - 1 if oi(t) and oi(t - FV.DEN) else None
    v["oi_izm7"] = oi(t) / oi(t - 7 * FV.DEN) - 1 if oi(t) and oi(t - 7 * FV.DEN) else None
    v["oi_minus_cena7"] = v["oi_izm7"] - v["mom7"] if v["oi_izm7"] is not None and v.get("mom7") is not None else None
    return v

def prohod():
    if not FO.exists(): return {"status": "net_dannyh_fanding_oi"}
    _kesh.clear(); zag = FV.zagruzka
    def zagruzka():
        d = zag()
        for s, r in d.items(): r["_sym"] = s
        return d
    FV.zagruzka = zagruzka
    try: return FV.prohod(kat=katalog(), atom_fn=atomy_dnya, atomy=ATOMY, out_dir=OUT, nazvanie="Фабрика вперёд v2")
    finally: FV.zagruzka = zag

if __name__ == "__main__":
    print(prohod())
