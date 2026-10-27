#!/usr/bin/env python3
"""brain_obyasneniya.py — конкурирующие объяснения убытков ноги (27.10.2026, Claude; ступень «Объясняет», предложение PM).
Для PUMP4 вместо жёсткого правила «BULL — выключить» проверяются ТРИ заранее заданных объяснения (список закрыт):
  A. массовый памп альтов — убыток, когда пампов много (ширина 24 ч) и альты сильнее BTC (alt_minus_btc_7d);
  B. ликвидность/шум — убыток, когда у монеты широкий стоп (risk_pct) и рынок разрозненный (disp_ret);
  C. нет преимущества у самой стратегии — разложение R = контроль (случайный вход той же монеты/времени) + вклад сигнала.
Проверка «предсказывает ли»: порог и направление каждого признака берутся ТОЛЬКО по первой (ранней) половине сделок,
потом смотрим, разделяет ли он вторую половину. Объяснение, которое разделяет и раньше, и позже, — кандидат в правило (prereg, вперёд).
Только чтение. Выход data/brain_shadow_v1/obyasneniya_pump4.json. Хук сторожа (после brain_zrenie)."""
import glob, json, math, statistics as st, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data" / "brain_shadow_v1"; DEN = 86_400_000
PRIZNAKI = {"A_shirina_24ch": "A", "A_alt_minus_btc_7d": "A", "B_risk_pct": "B", "B_disp_ret": "B"}

def _m(x): return dict(n=len(x), sred=round(st.mean(x), 4), se=round(st.stdev(x) / math.sqrt(len(x)), 4) if len(x) > 2 else None) if x else dict(n=0)

def prohod():
    f = sorted(glob.glob(str(LAB / "results" / "pump4_polnyy_povtor_*.json")))
    if not f: return {"status": "net_povtora"}
    sd = sorted([x for x in json.load(open(f[-1]))["sdelki"] if x.get("R") is not None], key=lambda x: x["ts"])
    Z = json.loads((D / "zrenie_dni.json").read_text()) if (D / "zrenie_dni.json").exists() else {}
    rows = []
    for x in sd:
        z = Z.get(str(x["ts"] // DEN * DEN - DEN)) or {}
        rows.append(dict(R=x["R"], ctrl=x.get("ctrl"), A_shirina_24ch=x.get("shirina"), A_alt_minus_btc_7d=z.get("alt_minus_btc_7d"),
                         B_risk_pct=x.get("risk_pct"), B_disp_ret=z.get("disp_ret")))
    h = len(rows) // 2; ran, poz = rows[:h], rows[h:]
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), sdelok=len(rows), istochnik=Path(f[-1]).name, priznaki={})
    for p, gr in PRIZNAKI.items():
        a = [r for r in ran if r[p] is not None]; b = [r for r in poz if r[p] is not None]
        if len(a) < 10 or len(b) < 10: out["priznaki"][p] = dict(status="MALO"); continue
        por = st.median(r[p] for r in a)
        vys_a, niz_a = [r["R"] for r in a if r[p] > por], [r["R"] for r in a if r[p] <= por]
        napr = "vysokiy_hudshe" if st.mean(vys_a) < st.mean(niz_a) else "nizkiy_hudshe"
        vys_b, niz_b = [r["R"] for r in b if r[p] > por], [r["R"] for r in b if r[p] <= por]
        def raz(v, n): return (st.mean(v) - st.mean(n)) if v and n else None
        ra, rb = raz(vys_a, niz_a), raz(vys_b, niz_b)
        podtv = rb is not None and ((napr == "vysokiy_hudshe" and rb < 0) or (napr == "nizkiy_hudshe" and rb > 0))
        se_b = math.hypot(_m(vys_b).get("se") or 0, _m(niz_b).get("se") or 0)
        out["priznaki"][p] = dict(obyasnenie=gr, porog_po_ranney=round(por, 5), napravlenie=napr, raznica_rannyaya=round(ra, 4),
                                  raznica_pozdnyaya=round(rb, 4) if rb is not None else None, se_pozdney=round(se_b, 4),
                                  predskazyvaet=bool(podtv), silno=bool(podtv and abs(rb) > 2 * se_b))
    c = [r for r in rows if r["ctrl"] is not None]
    out["C_razlozhenie"] = dict(R=_m([r["R"] for r in c]), kontrol=_m([r["ctrl"] for r in c]), vklad_signala=_m([r["R"] - r["ctrl"] for r in c]),
        ubytochnye=dict(n=sum(1 for r in c if r["R"] < 0), kontrol_v_nih=_m([r["ctrl"] for r in c if r["R"] < 0]),
                        vklad_signala_v_nih=_m([r["R"] - r["ctrl"] for r in c if r["R"] < 0])))
    vyv = [f'{p}: {"предсказывает" if v.get("predskazyvaet") else "не предсказывает"}{" (сильно)" if v.get("silno") else ""}' for p, v in out["priznaki"].items() if "napravlenie" in v]
    out["vyvod"] = vyv + ["C: убыток от рынка (контроль тоже теряет) или от сигнала — см. C_razlozhenie"]
    (D / "obyasneniya_pump4.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return dict(sdelok=len(rows), vyvod=vyv)

if __name__ == "__main__":
    print(prohod()); print(json.dumps(json.loads((D / "obyasneniya_pump4.json").read_text())["C_razlozhenie"], ensure_ascii=False))
    for p, v in json.loads((D / "obyasneniya_pump4.json").read_text())["priznaki"].items(): print(p, v)
