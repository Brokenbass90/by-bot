#!/usr/bin/env python3
"""brain_sovety.py — decision_feedback_v1 (27.10.2026, Claude; путь развития интеллекта, ступень 2). Хук сторожа, после brain_zhurnal_nog.
Brain read-only: советы пишутся, к ордерам не идут.
1. Совет по каждой записи журнала ног — в момент ПЕРВОГО появления записи (append-only, цепочка хэшей): какие правила совпали,
   совет (PROPUSK / VHOD), уверенность = статус правила (ULUCHSHAET / UHUDSHAET / INCONCLUSIVE). Флаг do_ishoda — у записи ещё не было исхода.
2. Оценка: когда исход есть — «что дал бы совет» против baseline без Brain. Отдельно — только советы, записанные ДО исхода (честная оценка вперёд).
3. Флаг деградации ноги: среднее 20 последних исходов ниже среднего всей истории ноги больше чем на 1 стандартную ошибку.
4. Причинный тест «свойство ноги или режима»: условие правила на ДРУГИХ шорт-ногах (если там тоже хуже — правило общее для шортов).
Выход: data/brain_shadow_v1/sovety.jsonl (журнал), sovety_svodka.json (перезаписывается)."""
import hashlib, json, math, statistics as st, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data" / "brain_shadow_v1"
ZH, SOV, SV, SVN = D / "zhurnal_nog.jsonl", D / "sovety.jsonl", D / "sovety_svodka.json", D / "svodka_nog.json"
USLOVIYA = {"volna3_BULL": lambda z: z["rezhim_btc"] == "BULL_TREND" and z["shirina_24ch"] >= 3, "BULL": lambda z: z["rezhim_btc"] == "BULL_TREND"}

def kl(z): return f'{z["noga"]}|{z["sym"]}|{z["t_signala"]}'

def _m(x):
    if not x: return dict(n=0)
    o = dict(n=len(x), sred=round(st.mean(x), 4))
    if len(x) > 2: o["se"] = round(st.stdev(x) / math.sqrt(len(x)), 4)
    return o

def prohod():
    if not ZH.exists(): return dict(status="NET_ZHURNALA")
    zap = [json.loads(l) for l in ZH.open()]
    sv_nog = json.loads(SVN.read_text()) if SVN.exists() else {}
    stat = {k: v.get("status") for k, v in (sv_nog.get("pravila_brain") or {}).items()}
    bylo, prev = {}, "0" * 64
    if SOV.exists():
        for l in SOV.open():
            r = json.loads(l); bylo[r["kl"]] = r; prev = r["hash"]
    novyh, seychas = 0, int(time.time() * 1000)
    with SOV.open("a") as f:
        for z in zap:
            if kl(z) in bylo: continue
            pr = z.get("pravila_sovpali") or []
            r = dict(kl=kl(z), noga=z["noga"], t_signala=z["t_signala"], t_soveta=seychas, sovet="PROPUSK" if pr else "VHOD", pravila=pr,
                     uverennost={p: stat.get(p, "INCONCLUSIVE") for p in pr}, do_ishoda=z.get("ishod") is None,
                     prev=prev)
            r["hash"] = prev = hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            f.write(json.dumps(r, ensure_ascii=False) + "\n"); bylo[r["kl"]] = r; novyh += 1
    # 2. оценка советов
    po_kl = {kl(z): z for z in zap}
    def ocenka(filtr):
        out = {}
        for noga in sorted({r["noga"] for r in bylo.values()}):
            g = [(r, po_kl[r["kl"]]) for r in bylo.values() if r["noga"] == noga and filtr(r) and r["kl"] in po_kl and po_kl[r["kl"]].get("ishod") is not None]
            prop = [-z["ishod"] for r, z in g if r["sovet"] == "PROPUSK"]
            out[noga] = dict(sovetov=len(g), propuskov=len(prop), effekt_brain_summa=round(sum(prop), 2), effekt_na_propusk=_m(prop),
                             edinica=g[0][1]["edinica"] if g else None)
        return out
    vse = ocenka(lambda r: True); vpered = ocenka(lambda r: r["do_ishoda"])
    # 3. деградация
    degr = {}
    for noga in sorted({z["noga"] for z in zap}):
        x = [z["ishod"] for z in sorted(zap, key=lambda z: z["t_signala"]) if z["noga"] == noga and z.get("ishod") is not None]
        if len(x) < 40: degr[noga] = dict(n=len(x), status="MALO_DANNYH"); continue
        p, vs = x[-20:], x
        se = st.stdev(vs) / math.sqrt(20)
        degr[noga] = dict(n=len(x), posl20=round(st.mean(p), 4), vsya=round(st.mean(vs), 4), se20=round(se, 4),
                          status="DEGRADACIYA" if st.mean(p) < st.mean(vs) - se else "NORMA")
    # 4. причинный тест: условие на каждой шорт-ноге (ед. у ног разные → сравниваем знак разницы «в условии − вне»)
    shorty = sorted({z["noga"] for z in zap if z.get("storona") in ("short", -1)})
    prich = {}
    for u, f in USLOVIYA.items():
        prich[u] = {}
        for noga in shorty:
            g = [z for z in zap if z["noga"] == noga and z.get("ishod") is not None]
            a, b = [z["ishod"] for z in g if f(z)], [z["ishod"] for z in g if not f(z)]
            prich[u][noga] = dict(v_uslovii=_m(a), vne=_m(b), raznica=round(st.mean(a) - st.mean(b), 4) if a and b else None)
        rz = [v["raznica"] for v in prich[u].values() if v["raznica"] is not None]
        prich[u]["vyvod"] = ("OBSHEE_DLYA_SHORTOV" if len(rz) >= 2 and all(r < 0 for r in rz) else
                             "SPECIFICHNO_DLYA_NOGI" if len(rz) >= 2 and any(r < 0 for r in rz) else "MALO_NOG") + " (описательно, n малы — только гипотеза для проверки вперёд)"
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), sovetov_vsego=len(bylo), novyh=novyh,
               sovetov_do_ishoda=sum(1 for r in bylo.values() if r["do_ishoda"]),
               ocenka_vse=vse, ocenka_vpered_tolko_do_ishoda=vpered, degradaciya=degr, prichinnyy_test=prich,
               primechanie="Brain read-only; эффект — что дал бы совет против торговли без Brain. Честная оценка — только советы, записанные до исхода.")
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    trev = [f"Brain: деградация {k}" for k, v in degr.items() if v.get("status") == "DEGRADACIYA"]
    return dict(novyh=novyh, trevogi=trev)

if __name__ == "__main__":
    print(prohod()); print(SV.read_text()[:3000])
