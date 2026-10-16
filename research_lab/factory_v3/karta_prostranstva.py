#!/usr/bin/env python3
"""karta_prostranstva.py — карта исследовательского пространства (16.10.2026):
механизм × рынок × источник × горизонт × проверено? × итог — по ОБОИМ кладбищам (реестр V3 + старый data/reestr.json).
Разметка — по ключевым словам id/описания (правила ниже, открыты для правки); неразмеченное перечисляется явно, не прячется.
Плюс шортлист: какие пары «источник × механизм» из каталога ещё не проверялись. Шортлист НЕ запускается сам —
каждому нужен экономический тезис и заранее заданный знак (TREBUET_TEZISA).
    python3 research_lab/factory_v3/karta_prostranstva.py   → data/factory_v3/KARTA_PROSTRANSTVA.json + .md
"""
import json, re
from collections import defaultdict
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"

MEHANIZMY = {
    "поток агрессора": r"kity|m3|taker|potok|pogloshch|order_flow|vsplesk",
    "толпа/позиции/OI": r"tolpa|crowd|oi_|_oi|pozicii|squeeze|l2_|l3_|speculation",
    "carry/funding/basis": r"carry|funding|fanding|basis|term_|xex|roll",
    "разворот": r"razvorot|reversal|otkat|vozvrat|weekly_rev|quiet_drop|pustoy_hod|peregrev",
    "импульс/тренд/пробой": r"moment|impuls|mom_|trend|proboy|breakout|52w|maksimum|att1|elder|ets2|sbr1|frog|bull|otstayush|obem_impuls|gap_volume|diffusion|sila|rotaciya|xsec_v3|bliz_max|alpaca",
    "ликвидность/микроструктура": r"glubina|order_book|microstr|maker|spread|razmah|telo_svechi|price_adj|illiquid|cs_oborot|oborot|shirina",
    "вынужденный поток": r"liq|likvid|kaskad|forced|settlement|rebal|cap_stress",
    "география площадок": r"coinbase|upbit|premiya|dislocation|arb_|tradfi|dolya_obema|token_gold",
    "время суток/календарь": r"nochnoy|chas|london|vyhodn|turn_of_month|overnight|gep|session|intraday",
    "волатильность/страх": r"strah|dvol|szhatie|vol_|low_vol|v1_prem|v2_vspl|lottery|asimmetriya_vol|razbros|low_price",
    "события/отчёты/предложение": r"otchet|e1_|e2_|e3_|listing|razlok|vozrast|edgar|novye_dengi|information|etf_potok",
    "рынки предсказаний": r"poly",
    "уровни/геометрия": r"uroven|svip|otboy|lozhnyy|bounce|urovni|geometr|^gold\b",
    "бета/корреляция": r"beta|korr",
}
RYNKI = {"акции США": r"eq_|akc|alpaca|52w|frog|e1_|e2_|e3_|overnight|lottery|low_price|illiquid|edgar|indeks",
         "FX/золото": r"fx|gold|zoloto|london|nochnoy|svip|gep_vyh|token_gold|^gold", "Polymarket": r"poly"}
GORIZONT = {"неделя": r"nedel|weekly|xs|kity|7d|_w|carry", "часы": r"_h1|chas|intraday|nochnoy|london|4h|kaskad", "день": r"1d|d1|sutoch|razvorot"}
ITOG = lambda st: "PASS/жив" if str(st).upper() in ("SHADOW", "CANARY", "MONEY", "CONFIRMED", "PASS", "SCREEN", "ACTIVE", "NEW", "POSITIVE_LEAD") else \
    ("KILL" if str(st).upper() in ("KILL", "NEGATIVE", "FAIL", "KILLED", "ОПРОВЕРГНУТА") else str(st))


def semyi():
    out = {}
    for z in json.loads((D / "reestr.json").read_text()):
        out[z["id"]] = dict(id=z["id"], tekst=f"{z['id']} {z.get('imya', '')}", status=z.get("sostoyanie"), istochnik="V2")
    for l in open(D / "factory_v3" / "reestr_v1.jsonl", encoding="utf-8"):
        if not l.strip(): continue
        z = json.loads(l)
        if z.get("tip") in ("semya", "gipoteza"):
            k = z["id"]; out.setdefault(k, dict(id=k, tekst="", status=None, istochnik="V3"))
            out[k]["tekst"] += f" {k} {z.get('opisanie', '')} {z.get('mehanizm', '')}"; out[k]["status"] = z.get("status") or out[k]["status"]
        if z.get("tip") == "perehod" and z.get("gipoteza") in out: out[z["gipoteza"]]["status"] = z.get("v")
        if z.get("tip") == "semya_kill" and z.get("semya") in out: out[z["semya"]]["status"] = "KILL"
    return list(out.values())


def razmetit(z):
    t = z["tekst"].lower()
    meh = [m for m, rx in MEHANIZMY.items() if re.search(rx, t)] or ["НЕ РАЗМЕЧЕНО"]
    ryn = next((r for r, rx in RYNKI.items() if re.search(rx, t)), "крипта")
    gor = next((g for g, rx in GORIZONT.items() if re.search(rx, t)), "?")
    return dict(z, mehanizmy=meh, rynok=ryn, gorizont=gor, itog=ITOG(z["status"]))


def main():
    S = [razmetit(z) for z in semyi()]
    mat = defaultdict(lambda: defaultdict(lambda: dict(n=0, kill=0, zhiv=0, id=[])))
    for z in S:
        for m in z["mehanizmy"]:
            c = mat[m][z["rynok"]]; c["n"] += 1; c["id"].append(z["id"])
            c["kill"] += z["itog"] == "KILL"; c["zhiv"] += z["itog"] == "PASS/жив"
    kat = json.loads((D / "factory_v3" / "KATALOG_ISTOCHNIKOV.json").read_text())["istochniki"] if (D / "factory_v3" / "KATALOG_ISTOCHNIKOV.json").exists() else []
    # шортлист: механизмы, которые источник может дать (по полю semyi каталога и карте), без проверок по этому механизму на крипте
    ist_meh = {"etf_btc_eth_flows": ["события/отчёты/предложение", "поток агрессора"], "stablecoin_supply": ["события/отчёты/предложение"],
               "hyperliquid_funding_oi": ["толпа/позиции/OI", "география площадок"], "liq_v2": ["вынужденный поток"],
               "obem_coinbase_d1": ["география площадок"], "obem_upbit_d1": ["география площадок"], "deribit_dvol": ["волатильность/страх"]}
    shortlist = []
    for z in kat:
        for m in ist_meh.get(z["id"], []):
            c = mat[m]["крипта"]
            shortlist.append(dict(istochnik=z["id"], status_istochnika=z["status"], mehanizm=m, proverok_na_kripte=c["n"], kill=c["kill"],
                                  zhivyh=c["zhiv"], primery=c["id"][:6], deystvie="TREBUET_TEZISA (знак и отличие от убитых — до прогона)"))
    rez = dict(semey=len(S), nerazmecheno=[z["id"] for z in S if z["mehanizmy"] == ["НЕ РАЗМЕЧЕНО"]],
               matrica={m: {r: dict(v, id=v["id"][:12]) for r, v in d.items()} for m, d in mat.items()}, shortlist=shortlist)
    (D / "factory_v3" / "KARTA_PROSTRANSTVA.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    rynki = ["крипта", "акции США", "FX/золото", "Polymarket"]
    md = ["# Карта исследовательского пространства (авто, " + str(len(S)) + " семей/гипотез из двух реестров)", "",
          "Ячейка: проверено / KILL / живых. Правила разметки — factory_v3/karta_prostranstva.py.", "",
          "| механизм | " + " | ".join(rynki) + " |", "|---|" + "---|" * len(rynki)]
    for m in list(MEHANIZMY) + ["НЕ РАЗМЕЧЕНО"]:
        if m in mat:
            md.append(f"| {m} | " + " | ".join(f"{mat[m][r]['n']} / {mat[m][r]['kill']} / {mat[m][r]['zhiv']}" if mat[m][r]["n"] else "—" for r in rynki) + " |")
    md += ["", "## Шортлист «источник × механизм» (не запускается сам)", "", "| источник | статус | механизм | проверок на крипте | KILL | живых |", "|---|---|---|---|---|---|"]
    md += [f"| {s['istochnik']} | {s['status_istochnika']} | {s['mehanizm']} | {s['proverok_na_kripte']} | {s['kill']} | {s['zhivyh']} |" for s in shortlist]
    md += ["", f"Неразмеченные ({len(rez['nerazmecheno'])}): " + ", ".join(rez["nerazmecheno"][:60])]
    (D / "factory_v3" / "KARTA_PROSTRANSTVA.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
