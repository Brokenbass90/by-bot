#!/usr/bin/env python3
"""dubl_proverka.py — сверка новой гипотезы с закрытыми семьями реестра ДО того, как она получит попытку (17.10.2026).
Описания старых семей бедные («пачка 1»), поэтому сверка по понятиям: регулярные выражения по id + описанию + механизму.
Совпадение ≥ 2 понятий с KILL-семьёй → подозрение на дубликат; гипотеза регистрируется только с явным полем otlichie
(чем механизм отличается: новые данные / другой горизонт / другой класс активов)."""
import re

PONYATIYA = {
    "funding": r"fund|fand|фандинг",
    "oi": r"(^|_|\b)oi(_|\b)|open.?interest|открыт\w* интерес",
    "likvidacii": r"liq|likv|ликвид",
    "tolpa": r"tolpa|crowd|толп|long.?short|перекос",
    "carry": r"carry|kerri|керри",
    "basis": r"basis|bazis|базис",
    "kross": r"(_|\b)xs(_|\b)|kross|кросс|дециль|квинтил|kvintil",
    "proboy": r"proboy|break|пробо",
    "otskok": r"otskok|bounce|отскок|reversal|возврат",
    "impuls": r"impul|momentum|импульс",
    "srednee": r"mean.?rev|range|боков|средн",
    "makro": r"makro|macro|cpi|fomc|fed|макро",
    "etf": r"etf|ibit|farside",
    "vol": r"(_|\b)vol|волатил|dvol|atr",
    "kanal": r"kanal|channel|sloped|наклон|att1|asm",
    "sobytie_kalendar": r"ekspir|expir|экспир|kalendar|календар|weekend|выходн",
}


def ponyatiya(tekst):
    t = tekst.lower()
    return {k for k, rx in PONYATIYA.items() if re.search(rx, t)}


def najti(tekst, sostoyanie, min_obshchih=2):
    """→ [(semya, общие понятия)] среди KILL-семей и KILL-гипотез."""
    moi = ponyatiya(tekst); out = []
    for sid, f in sostoyanie.get("semi", {}).items():
        if f.get("status") != "KILL": continue
        tekst_f = " ".join([sid, f.get("opisanie") or ""] + [g.get("mehanizm") or "" for g in sostoyanie.get("gipotezy", {}).values()
                                                             if g.get("semya") == sid])
        ob = moi & ponyatiya(tekst_f)
        if len(ob) >= min_obshchih: out.append((sid, sorted(ob)))
    return out
