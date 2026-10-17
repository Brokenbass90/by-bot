#!/usr/bin/env python3
"""avto_prodvizhenie.py — FACTORY → PROVEN CANDIDATE → EXECUTION DOSSIER автоматически (17.10.2026).

Вызывается в конце каждого прохода конвейера. Для каждого итога PASS без квитанции:
 1. пересчитывает исходы по событиям тем же экспериментом и окном (детерминированно) и проверяет концентрацию:
    доля трёх лучших в сумме положительных R < 50 %; без трёх крупнейших |R| среднее > 0 (R — после издержек);
 2. PROVEREN → репликация: если в карте заявки задано `replikaciya` = {okno, sobytiya} (записано ДО результата) —
    подаёт заявку `<id>_R` сам; иначе пишет «репликация невозможна → CONFIRM вперёд»;
 3. пишет черновик досье `dosie/AVTO_<гипотеза>.md` и строку статуса для Codex в `data/factory_v3/DLYA_CODEX.jsonl`.
Ничего не меняет в правилах и порогах; деньги/ордера не трогает. Квитанция: `data/factory_v3/prodvizhenie/<id>.json`.
"""
import json, sys, time
from pathlib import Path
from types import SimpleNamespace
HERE = Path(__file__).resolve().parent; LAB = HERE.parent; sys.path.insert(0, str(HERE))
PRAVILO_S_MS = 1792236000000   # 2026-10-17 11:20 UTC: для итогов раньше — проверка концентрации лишь диагностика (не была в prereg)
OUT = LAB / "data/factory_v3/prodvizhenie"; CODEX = LAB / "data/factory_v3/DLYA_CODEX.jsonl"; DOSIE = LAB / "dosie"


def _okno(oid):
    import okna_proverka as O
    o = O.okna()[oid]; return SimpleNamespace(t0=O._ms(o["nachalo"]), t1=O._ms(o["konec"], True) - 1)


def koncentraciya(po_sob):
    R = [x[2] for x in po_sob]
    if len(R) < 6: return dict(ok=False, prichina="мало событий")
    pol = sorted([r for r in R if r > 0], reverse=True)
    dolya3 = sum(pol[:3]) / sum(pol) if pol else 1.0
    bez = sorted(R, key=lambda r: abs(r))[:-3]
    sr_bez = sum(bez) / len(bez)
    return dict(ok=bool(dolya3 < 0.5 and sr_bez > 0), dolya_top3=round(dolya3, 3), srednee_bez_top3_bps=round(sr_bez, 2),
                n=len(R), srednee_bps=round(sum(R) / len(R), 2))


def _pereschitat(spec):
    eks = spec["eksperiment"]
    if eks != "shablony_v2:sobytie": return None
    import importlib, shablony_v2; importlib.reload(shablony_v2)
    return shablony_v2.sobytie(spec["parametry"], _okno(spec["okno"]))["metrika"].get("po_sobytiyam")


def prohod(put):
    import konveyer_v1 as K
    OUT.mkdir(parents=True, exist_ok=True); zap = K.chitat(put)
    zayavki = {z["spec"]["id"]: z for z in zap if z["tip"] == "zayavka"}
    sdelano = []
    for it in (z for z in zap if z["tip"] == "itog" and z.get("status") == "PASS"):
        kv = OUT / f"{it['id']}.json"
        if kv.exists() or it["id"] not in zayavki: continue
        z = zayavki[it["id"]]; spec, karta = z["spec"], z["karta"]
        try:
            ps = _pereschitat(spec)
        except Exception as e:
            ps = None; oshibka = str(e)[:200]
        k = koncentraciya(ps) if ps else dict(ok=None, prichina="пересчёт по событиям недоступен для этого эксперимента")
        status = "PROVEREN" if k.get("ok") else ("FAIL_KONCENTRACIYA" if k.get("ok") is False else "NUZHNA_RUCHNAYA_PROVERKA")
        if it.get("kogda", 0) < PRAVILO_S_MS:                 # честно: правило появилось после этого результата
            k["tolko_diagnostika"] = True
            status = "PROVEREN" if status != "NUZHNA_RUCHNAYA_PROVERKA" else status
        rep = karta.get("replikaciya"); replikaciya = None
        if status == "PROVEREN" and rep and not it["id"].endswith("_R"):
            rs = dict(spec, id=it["id"] + "_R", okno=rep["okno"], parametry=dict(spec["parametry"], sobytiya=rep["sobytiya"]))
            K.podat(rs, dict(karta, replikaciya=None)); replikaciya = rs["id"]
        kvit = dict(id=it["id"], gipoteza=spec["gipoteza"], t=it.get("t"), n=it.get("n"), trebuemyy_t=it.get("trebuemyy_t"),
                    koncentraciya=k, status=status, pravilo_do_rezultata=it.get("kogda", 0) >= PRAVILO_S_MS, replikaciya=replikaciya or ("подана" if replikaciya else
                    ("невозможна → CONFIRM вперёд" if status == "PROVEREN" else None)), kogda=int(time.time() * 1000))
        kv.write_text(json.dumps(kvit, ensure_ascii=False, indent=1))
        if status == "PROVEREN":
            DOSIE.mkdir(exist_ok=True)
            (DOSIE / f"AVTO_{spec['gipoteza']}.md").write_text(
                f"# Досье (авточерновик) — {spec['gipoteza']} — статус DRAFT\n\n"
                f"Сгенерировано avto_prodvizhenie {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Шаблон: SHABLON_DOSIE_ISPOLNENIYA.md.\n\n"
                f"1. Идентичность: {it['id']}, окно {spec['okno']}, t {it.get('t'):.2f} / треб. {it.get('trebuemyy_t')}, n {it.get('n')}.\n"
                f"2. Сигнал: эксперимент `{spec['eksperiment']}`, параметры `{json.dumps(spec['parametry'], ensure_ascii=False)}`.\n"
                f"3. Механизм: {karta.get('mehanizm')}.\n4. Источники: {karta.get('istochniki')}.\n"
                f"5. Концентрация: {json.dumps(k, ensure_ascii=False)}.\n6. Путь: {karta.get('put_k_micro_live')}.\n"
                f"7. Репликация: {kvit['replikaciya']}.\n\nРазделы 3–11 шаблона (время доступности, исполнение, размер, остановка, "
                f"квитанции) заполняет Claude при переходе в READY_FOR_ORDERS_OFF.\n")
            with open(CODEX, "a") as f:
                f.write(json.dumps(dict(komponent=spec["gipoteza"], gate="DEV_PASS_PROVEREN", evidence=(str(kv.relative_to(LAB)) if kv.is_relative_to(LAB) else str(kv)),
                                        blocker="CONFIRM вперёд / репликация", next="Claude: досье → READY_FOR_ORDERS_OFF",
                                        kogda=kvit["kogda"]), ensure_ascii=False) + "\n")
        sdelano.append((it["id"], status))
    return sdelano
