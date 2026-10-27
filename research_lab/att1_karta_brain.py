#!/usr/bin/env python3
"""att1_karta_brain.py — ATT1 через карту Brain (27.10.2026, Claude; установка владельца «включать ногу там, где ей выгодно»).
Описательный разрез ТЕНИ вперёд ATT1 (data/ten_ATT1.jsonl, 09–10.2026, шорт), без наложений (одна позиция на монету), отдельно «вовремя».
Срезы: режим BTC (REZHIM_V1), рыночное зрение Brain (терти), вклад сигнала = R − случайный вход той же монеты/времени (ctrl).
Ячейка «работает» описательно: средний R > 0 и вклад сигнала > 0 с запасом 2 se по кластерам дней. Правила из этого — только prereg и проверка
вперёд на НОВЫХ сделках (эти уже просмотрены). Только чтение.  python3 research_lab/att1_karta_brain.py"""
import collections, json, math, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE / "fabrika")); sys.path.insert(0, str(HERE))
import audit_nalozheniy as AN, brain_zhurnal_nog as BZ
H, DEN = 3600000, 86400000

def klaster(x):  # среднее и se по кластерам дней
    po = collections.defaultdict(list)
    for d, v in x: po[d].append(v)
    m = [st.mean(v) for v in po.values()]
    if len(m) < 3: return dict(n=len(x), dney=len(m))
    return dict(n=len(x), dney=len(m), sred=round(st.mean(v for _, v in x), 4), se_dni=round(st.stdev(m) / math.sqrt(len(m)), 4))

def main():
    V = [json.loads(l) for l in open(HERE / "data" / "ten_ATT1.jsonl")]
    sig = {(x["sym"], x["ts"]): x for x in V if "R" not in x}            # запись сигнала: её vovremya = успели ли к входу
    L = [dict(x, vovremya=bool(sig.get((x["sym"], x["ts"]), {}).get("vovremya"))) for x in V if x.get("R") is not None and x.get("barov") is not None]
    B = AN.bez_nalozheniy(L)
    mt = BZ.metki_btc(); rez = lambda t: mt.get(int(t) // H * H - H, "NET_DANNYH")
    Z = json.loads((HERE / "data" / "brain_shadow_v1" / "zrenie_dni.json").read_text())
    rows = []
    for x in B:
        z = Z.get(str(int(x["ts"]) // DEN * DEN - DEN)) or {}
        rows.append(dict(d=time.strftime("%Y-%m-%d", time.gmtime(x["ts"] / 1000)), R=x["R"], vk=x["R"] - x["ctrl"] if x.get("ctrl") is not None else None,
                         vovremya=bool(x.get("vovremya")), rezhim=rez(x["ts"]), **{k: z.get(k) for k in ("shirota_rosta", "alt_minus_btc_7d", "sinhron_tejker", "shirota_obema", "disp_ret")}))
    def yach(f):
        g = [r for r in rows if f(r)]
        a, b = klaster([(r["d"], r["R"]) for r in g]), klaster([(r["d"], r["vk"]) for r in g if r["vk"] is not None])
        ok = a.get("sred", 0) > 2 * (a.get("se_dni") or 9) and b.get("sred", 0) > 2 * (b.get("se_dni") or 9)
        return dict(R=a, vklad_signala=b, rabotaet=ok)
    out = dict(vsego_v_teni=len(L), bez_nalozheniy=len(B), vse=yach(lambda r: True), vovremya=yach(lambda r: r["vovremya"]),
               pozdno=yach(lambda r: not r["vovremya"]), po_rezhimu={}, po_zreniyu={})
    for m in sorted({r["rezhim"] for r in rows}): out["po_rezhimu"][m] = yach(lambda r, m=m: r["rezhim"] == m)
    for p in ("shirota_rosta", "alt_minus_btc_7d", "sinhron_tejker", "shirota_obema", "disp_ret"):
        v = sorted(r[p] for r in rows if r[p] is not None)
        if len(v) < 30: continue
        a, b = v[len(v) // 3], v[2 * len(v) // 3]
        out["po_zreniyu"][p] = dict(granicy=[a, b], niz=yach(lambda r, p=p, a=a: r[p] is not None and r[p] <= a),
                                    verh=yach(lambda r, p=p, b=b: r[p] is not None and r[p] > b))
    f = HERE / "results" / time.strftime("att1_karta_brain_%Y%m%dT%H%MZ.json", time.gmtime()); f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("всего", len(L), "без наложений", len(B)); print("все", out["vse"]); print("вовремя", out["vovremya"]); print("поздно", out["pozdno"])
    for m, v in out["po_rezhimu"].items(): print("режим", m, v["R"], "вклад", v["vklad_signala"].get("sred"), "РАБОТАЕТ" if v["rabotaet"] else "")
    for p, v in out["po_zreniyu"].items():
        for k in ("niz", "verh"): print(p, k, v[k]["R"], "вклад", v[k]["vklad_signala"].get("sred"), "РАБОТАЕТ" if v[k]["rabotaet"] else "")
    print("файл", f)

if __name__ == "__main__":
    main()
