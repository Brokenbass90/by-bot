#!/usr/bin/env python3
"""brain_otchet_regulyarnosti.py — Brain: регулярность дохода по месяцам/неделям/дням (28.10.2026, Claude; задание PM и владельца
«не надеяться на редкие выбросы»). Хук сторожа, read-only. Источники: PUMP4 — непрерывный повтор V1 (R после комиссий, контроль случайным входом);
SHORT_HVOST — все шорты хвоста двух теней (H1-пересчёт `results/short_hvost_uderzhanie_*.json`, база 16 ч с хеджем, фандингом, издержками).
Размер (фиксированный, для $-шкалы, не рекомендация): депозит $1 000, PUMP4 риск $10 на сделку, SHORT_HVOST $100 на позицию.
Для каждой ноги и портфеля: по месяцам и неделям — net $, % депозита, сделок; прибыльных/убыточных месяцев и недель, худший месяц/неделя;
макс. просадка и самое долгое восстановление (дней); без 5 лучших сделок; концентрация (доля прибыли лучшей монеты и лучшего дня);
независимых дней; вклад сигнала к случайному входу (PUMP4). Подневный журнал: data/brain_shadow_v1/podnevno.jsonl (перезаписывается) —
по каждому дню: сделки ног, net $, худшая сделка дня и её монета — сырьё для разбора «что пошло не так».
Выход: data/brain_shadow_v1/regulyarnost.json и REGULYARNOST.md."""
import collections, glob, json, statistics as st, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data" / "brain_shadow_v1"; H = 3600000; DEP = 1000.0

def sdelki():
    out = []
    f = sorted(glob.glob(str(LAB / "results" / "pump4_polnyy_povtor_*.json")))
    if f:
        for x in json.load(open(f[-1]))["sdelki"]:
            if x.get("status") == "ZAKRYTA" and x.get("R") is not None:
                out.append(dict(noga="PUMP4", sym=x["sym"], t=x["ts"] + (x["barov"] + 2) * H, usd=x["R"] * 10, ctrl_usd=(x["ctrl"] or 0) * 10 if x.get("ctrl") is not None else None))
    f = sorted(glob.glob(str(LAB / "results" / "short_hvost_uderzhanie_*.json")))
    if f:
        for x in json.load(open(f[-1]))["sdelki"]:
            out.append(dict(noga="SHORT_HVOST", sym=x["sym"], t=x["16"]["kon"], usd=100 * x["16"]["net_hedzh"] / 1e4, ctrl_usd=None))
    return sorted(out, key=lambda x: x["t"])

def analiz(g):
    if not g: return dict(n=0)
    mes, ned, den = collections.defaultdict(float), collections.defaultdict(float), collections.defaultdict(float)
    for x in g:
        tm = time.gmtime(x["t"] / 1000); mes[time.strftime("%Y-%m", tm)] += x["usd"]; ned[time.strftime("%G-W%V", tm)] += x["usd"]; den[time.strftime("%Y-%m-%d", tm)] += x["usd"]
    eq = pik = 0.0; dd = 0.0; t_pik = g[0]["t"]; dolgo = 0
    for x in g:
        eq += x["usd"]
        if eq >= pik: dolgo = max(dolgo, (x["t"] - t_pik) / 864e5); pik, t_pik = eq, x["t"]
        dd = max(dd, pik - eq)
    dolgo = max(dolgo, (g[-1]["t"] - t_pik) / 864e5)
    vse = sum(x["usd"] for x in g); top5 = sum(sorted((x["usd"] for x in g), reverse=True)[:5])
    po_monetam = collections.defaultdict(float)
    for x in g: po_monetam[x["sym"]] += x["usd"]
    plus = sum(v for v in po_monetam.values() if v > 0) or 1
    c = [x["usd"] - x["ctrl_usd"] for x in g if x["ctrl_usd"] is not None]
    return dict(n=len(g), net_usd=round(vse, 1), net_pct=round(vse / DEP * 100, 2),
                mesyacy={k: round(v, 1) for k, v in sorted(mes.items())}, mesyacev_plus=sum(v > 0 for v in mes.values()), mesyacev_minus=sum(v <= 0 for v in mes.values()),
                hudshiy_mesyac=round(min(mes.values()), 1), nedel_plus=sum(v > 0 for v in ned.values()), nedel_minus=sum(v <= 0 for v in ned.values()),
                hudshaya_nedelya=round(min(ned.values()), 1), dney_s_sdelkami=len(den), dney_plus=sum(v > 0 for v in den.values()),
                max_prosadka_usd=round(dd, 1), dolgoe_vosstanovlenie_dney=round(dolgo, 1), bez_5_luchshih_usd=round(vse - top5, 1),
                dolya_luchshey_monety=round(max(po_monetam.values()) / plus, 3), luchshaya_moneta=max(po_monetam, key=po_monetam.get),
                dolya_luchshego_dnya=round(max(den.values()) / (sum(v for v in den.values() if v > 0) or 1), 3),
                vklad_k_sluchaynomu_usd=round(st.mean(c), 2) if c else None)

def prohod():
    S = sdelki()
    if not S: return {"status": "net_dannyh"}
    out = {n: analiz([x for x in S if x["noga"] == n]) for n in ("PUMP4", "SHORT_HVOST")}
    ot = min(x["t"] for x in S if x["noga"] == "PUMP4") if any(x["noga"] == "PUMP4" for x in S) else 0
    out["PORTFEL_s_01_09"] = analiz([x for x in S if x["t"] >= ot])
    dni = collections.defaultdict(list)
    for x in S: dni[time.strftime("%Y-%m-%d", time.gmtime(x["t"] / 1000))].append(x)
    with (D / "podnevno.jsonl").open("w") as f:
        for d, g in sorted(dni.items()):
            h = min(g, key=lambda x: x["usd"])
            f.write(json.dumps(dict(den=d, net_usd=round(sum(x["usd"] for x in g), 2), po_nogam={n: round(sum(x["usd"] for x in g if x["noga"] == n), 2) for n in {x["noga"] for x in g}},
                                    sdelok=len(g), hudshaya=dict(noga=h["noga"], sym=h["sym"], usd=round(h["usd"], 2))), ensure_ascii=False) + "\n")
    (D / "regulyarnost.json").write_text(json.dumps(dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), razmer="депозит $1000; PUMP4 риск $10; SHORT_HVOST $100/позиция", **out), ensure_ascii=False, indent=1))
    md = ["# Регулярность дохода (Brain, автоматически) — депозит $1 000; PUMP4 риск $10; SHORT_HVOST $100 на позицию", "",
          "| | сделок | net $ | мес. + / − | худший мес. | недель + / − | худшая неделя | просадка $ | восстановление, дн | без 5 лучших $ | лучшая монета | доля лучшего дня |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in out.items():
        if v.get("n"): md.append(f'| {k} | {v["n"]} | {v["net_usd"]} | {v["mesyacev_plus"]} / {v["mesyacev_minus"]} | {v["hudshiy_mesyac"]} | {v["nedel_plus"]} / {v["nedel_minus"]} | {v["hudshaya_nedelya"]} | {v["max_prosadka_usd"]} | {v["dolgoe_vosstanovlenie_dney"]} | {v["bez_5_luchshih_usd"]} | {v["luchshaya_moneta"]} ({v["dolya_luchshey_monety"]}) | {v["dolya_luchshego_dnya"]} |')
    md += ["", "По месяцам ($):"] + [f'- {k}: {v["mesyacy"]}' for k, v in out.items() if v.get("n")]
    md += ["", "Подневный журнал для разбора: `data/brain_shadow_v1/podnevno.jsonl`. Ни одна нога не получает статус «стабильно прибыльная» по одному месяцу или 30 сделкам."]
    (D / "REGULYARNOST.md").write_text("\n".join(md) + "\n")
    return {k: dict(n=v.get("n"), net=v.get("net_usd"), mes=v.get("mesyacy")) for k, v in out.items()}

if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False, indent=1)); print((D / "REGULYARNOST.md").read_text())
