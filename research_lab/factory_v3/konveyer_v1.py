#!/usr/bin/env python3
"""konveyer_v1.py — закрывает разрыв «модули Фабрики есть» ↔ «Фабрика сама исследует» (15.10.2026).

Очередь data/factory_v3/ochered.jsonl (append-only): {"tip":"zayavka", "spec":{id, gipoteza, okno, eksperiment, parametry, kriterii},
"karta":{...}}. Сторож раз в час вызывает prohod(): каждая НОВАЯ заявка с полной картой кандидата и разрешённым шаблоном
исполняется фермой ОДИН раз (ferma_v1.zapustit → реестр: попытка до прогона, результат после), итог дописывается в очередь
как {"tip":"itog", ...}. Повтора нет: заявка с итогом не исполняется второй раз.

Карта кандидата обязательна ДО прогона (без неё — отказ, не прогон):
  data_ready (bool), istochniki (список), hist_dev ("ferma"|"skript:<путь>"), sobytiy_v_nedelyu (число),
  ozhidanie_vpered_dney (число), ispolnimost ("ponyatna"|"neyasna"), put_k_micro_live (строка), mehanizm (строка)
Правило: если data_ready=False — отказ BLOCKED_DATA; если ispolnimost="neyasna" — прогон разрешён, но к тени не допускается.
Шаблоны — только из RAZRESHENO. Окна HOLDOUT ферма сама запрещает.
"""
import json, time, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
OCHERED = HERE.parent / "data" / "factory_v3" / "ochered.jsonl"
RAZRESHENO = {"ferma_shablony:xs_nedelya_binance", "ferma_primery:moment_na_shume", "shablony_v2:odin_aktiv_chas", "shablony_v2:sobytie", "shablony_v2:vneshniy_ryad_nedelya"}
KARTA = {"data_ready": (bool, str), "istochniki": list, "hist_dev": str, "sobytiy_v_nedelyu": (int, float), "ozhidanie_vpered_dney": (int, float),
         "ispolnimost": str, "put_k_micro_live": str, "mehanizm": str}


def chitat(put=OCHERED):
    put = Path(put)
    return [json.loads(l) for l in open(put, encoding="utf-8") if l.strip()] if put.exists() else []


def dopisat(zap, put=OCHERED):
    put = Path(put); put.parent.mkdir(parents=True, exist_ok=True)
    with open(put, "a", encoding="utf-8") as f: f.write(json.dumps(zap, ensure_ascii=False) + "\n")


def podat(spec, karta, put=OCHERED):
    """Подать заявку (Claude / ИИ-раунд). Проверка карты — сразу, чтобы мусор не попадал в очередь."""
    plohie = [k for k, t in KARTA.items() if not isinstance(karta.get(k), t)
              or (k != "data_ready" and isinstance(karta.get(k), bool) != (t is bool))]
    if isinstance(karta.get("data_ready"), str) and not karta["data_ready"].startswith("manifest:"): plohie.append("data_ready")
    if plohie: raise ValueError(f"карта кандидата неполна: {plohie}")
    if spec.get("eksperiment") not in RAZRESHENO: raise ValueError(f"шаблон не разрешён: {spec.get('eksperiment')}")
    if karta["ispolnimost"] not in ("ponyatna", "neyasna"): raise ValueError("ispolnimost ∈ {ponyatna, neyasna}")
    dopisat(dict(tip="zayavka", kogda=int(time.time() * 1000), spec=spec, karta=karta), put)


def gotovnost(dr, koren=None):
    """True / False (терминально BLOCKED_DATA) / None (ждём манифест: заявка остаётся в очереди без итога)."""
    if isinstance(dr, bool): return dr
    p = (Path(koren) if koren else HERE.parent) / dr.split(":", 1)[1]
    try:
        return True if json.loads(p.read_text()).get("gotovo") is True else None
    except Exception:
        return None


def prohod(put=OCHERED, reestr=None, processov=2, koren=None):
    import fcntl
    put = Path(put); put.parent.mkdir(parents=True, exist_ok=True); fd = open(str(put) + ".lock", "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fd.close(); return []
    try:
        return _prohod(put, reestr, processov, koren)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); fd.close()


def _prohod(put, reestr, processov, koren):
    zap = chitat(put); sdelano = {z["id"] for z in zap if z["tip"] == "itog"}
    novye = [z for z in zap if z["tip"] == "zayavka" and z["spec"]["id"] not in sdelano]
    itogi = []
    gt = {z["spec"]["id"]: gotovnost(z["karta"]["data_ready"], koren) for z in novye}
    for i, usl in uderzhat(put, koren).items():                 # 16.10: удержание заявки до условия (напр. исправленное правило данных)
        if i in gt and gt[i] is True: gt[i] = None
    for z in novye:
        if gt[z["spec"]["id"]] is False:
            itogi.append(dict(tip="itog", id=z["spec"]["id"], status="BLOCKED_DATA", kogda=int(time.time() * 1000)))
    gotovye = [z for z in novye if gt[z["spec"]["id"]] is True]
    proshli = []
    for z in gotovye:                                            # общий шаг измерений без доходностей, если в карте заданы пороги
        por = z["karta"].get("izmereniya_porogi")
        if not por:
            proshli.append(z); continue
        try:
            iz = izmereniya_xs(z["spec"])
        except Exception as e:
            iz = dict(oshibka=str(e)[:200])
        ok = ("oshibka" not in iz and iz["mediana_pokrytiya"] >= por.get("pokrytie", 20) and iz["mediana_modulya_bps"] >= por.get("modul_bps", 12)
              and iz["korr_s_m3_mediana"] is not None and abs(iz["korr_s_m3_mediana"]) < por.get("korr_m3", 0.5))
        dopisat(dict(tip="izmereniya", id=z["spec"]["id"], rez=iz, porogi=por, status="PASS" if ok else "FAIL", kogda=int(time.time() * 1000)), put)
        if ok: proshli.append(z)
        else: itogi.append(dict(tip="itog", id=z["spec"]["id"], status="BLOCKED_BY_MEASUREMENT", izmereniya=iz, kogda=int(time.time() * 1000)))
    gotovye = proshli
    if gotovye:
        import ferma_v1
        for x in ferma_v1.zapustit([z["spec"] for z in gotovye], reestr=reestr, processov=processov):
            k = next(z["karta"] for z in gotovye if z["spec"]["id"] == x["id"])
            x.update(tip="itog", kogda=int(time.time() * 1000),
                     k_teni=bool(x.get("status") == "PASS" and k["ispolnimost"] == "ponyatna"))
            itogi.append(x)
    for x in itogi:
        dopisat(x, put)
        if x.get("status") == "FAIL":
            try: avto_postmortem(x, reestr)
            except Exception: pass
    try:
        obnovit_kartu()
    except Exception:
        pass
    try:                                              # запас кандидатов виден без рестарта сторожа (модуль перечитывается)
        (Path(put).parent / "ZAPAS.json").write_text(json.dumps(dict(zapas(put), kogda=int(time.time() * 1000)), ensure_ascii=False))
    except Exception:
        pass
    return itogi


MIN_ZAPAS = 3


def zapas(put=OCHERED):
    """Правило 15.10: впереди всегда ≥ MIN_ZAPAS независимых кандидатов (заявки без итога + карты в KANDIDATY_V_OCHEREDI.json)."""
    zap = chitat(put); sdelano = {z["id"] for z in zap if z["tip"] == "itog"}
    v_ocheredi = [z["spec"]["id"] for z in zap if z["tip"] == "zayavka" and z["spec"]["id"] not in sdelano]
    p = Path(put).parent / "KANDIDATY_V_OCHEREDI.json"
    karty = [k["imya"] for k in json.loads(p.read_text()) if k.get("status") == "OZHIDAET"] if p.exists() else []
    n = len(v_ocheredi) + len(karty)
    rez = dict(n=n, zayavki=v_ocheredi, karty=karty, status="OK" if n >= MIN_ZAPAS else "TREVOGA_MALO_KANDIDATOV")
    if n < MIN_ZAPAS:                                         # авто-пополнение: предложения из карты пространства (не запускаются сами)
        kp = Path(put).parent / "KARTA_PROSTRANSTVA.json"
        if kp.exists():
            sl = json.loads(kp.read_text()).get("shortlist", [])
            rez["predlozheniya"] = sorted(sl, key=lambda z: (z["status_istochnika"] != "LOCAL", z["kill"] - z["zhivyh"]))[:5]
    return rez


def obnovit_kartu(maks_vozrast_ch=24):
    """Каталог источников и карта пространства пересобираются не чаще раза в сутки (из часового прохода сторожа)."""
    kp = OCHERED.parent / "KARTA_PROSTRANSTVA.json"
    if kp.exists() and time.time() - kp.stat().st_mtime < maks_vozrast_ch * 3600: return False
    import katalog_istochnikov, karta_prostranstva
    katalog_istochnikov.main(); karta_prostranstva.main(); return True


def kladbishche(slova, koren=None):
    """Поиск по ОБОИМ кладбищам: реестр V3 (семьи/гипотезы) и старый реестр Фабрики V2 (data/reestr.json, 148 записей).
    15.10: кандидат «ночной дрейф золота» прошёл проверку только по V3, а в V2 он уже NEGATIVE (UTC-ретест 01.10) — дыра закрыта.
    Возвращает совпадения (id, состояние); пустой список = похожего не найдено."""
    koren = Path(koren) if koren else HERE.parent
    slova = [w.lower() for w in slova]; out = []
    p2 = koren / "data" / "reestr.json"
    if p2.exists():
        for z in json.loads(p2.read_text()):
            t = json.dumps(z, ensure_ascii=False).lower()
            if all(w in t for w in slova): out.append((z.get("id"), z.get("sostoyanie")))
    p3 = koren / "data" / "factory_v3" / "reestr_v1.jsonl"
    if p3.exists():
        for l in open(p3, encoding="utf-8"):
            t = l.lower()
            if l.strip() and all(w in t for w in slova):
                z = json.loads(l); out.append((z.get("id") or z.get("gipoteza") or z.get("popytka"), z.get("status") or z.get("verdikt") or z.get("tip")))
    return out


def izmereniya_xs(spec, okno_ot="2023-01-01", okno_do="2026-09-23"):
    """16.10: ОБЩИЙ шаг измерений без доходностей для недельной кросс-секции — новая семья = функция признака + карта, без своего
    кода измерений. Считает по неделям окна DEV: покрытие топ-50, медиану |признака| (bps), корр. с KITY m3 (независимость)."""
    import datetime as dt, statistics, numpy as np, ferma_shablony as F, kity_sudya as K
    D = F._dannye(); M = D["M"]; p = spec["parametry"]; pr = F._priznak(p["priznak"], D); m3 = F._priznak("m3_perp", D)
    sdv = int(p.get("sdvig_dney", 0)); pokr, modul, korr = [], [], []
    for d0 in K.SETKA:
        d = d0 + dt.timedelta(days=sdv)
        if not dt.date.fromisoformat(okno_ot) <= d <= dt.date.fromisoformat(okno_do): continue
        vch = (d - dt.timedelta(days=1)).isoformat()
        _v = d - dt.timedelta(days=1); vu = (_v - dt.timedelta(days=(_v.weekday() - 2) % 7)).isoformat()   # OI есть только по средам: вселенная —
        oi = sorted([(x["met"][vu][4], s) for s, x in M.items() if vu in x["met"] and x["met"][vu][4]], reverse=True)[:50]  # последняя среда ≤ d−1
        pary = [(pr(s, vch), m3(s, vch)) for _, s in oi]
        pary = [(a, b) for a, b in pary if a is not None and not isinstance(a, tuple)]
        pokr.append(len(pary)); modul += [abs(a) for a, _ in pary]
        bb = [(a, b) for a, b in pary if b is not None]
        if len(bb) >= 20 and np.std([a for a, _ in bb]) > 0: korr.append(float(np.corrcoef([a for a, _ in bb], [b for _, b in bb])[0, 1]))
    return dict(nedel=len(pokr), mediana_pokrytiya=statistics.median(pokr) if pokr else 0,
                mediana_modulya_bps=round(statistics.median(modul) * 1e4, 2) if modul else 0.0,
                korr_s_m3_mediana=round(statistics.median(korr), 3) if korr else None)


def avto_postmortem(itog, reestr=None):
    """16.10: на FAIL конвейер сам пишет черновик постмортема: метрики, половины, «прошёл бы обратный знак?». Решение о варианте спасения —
    за исследователем (бюджет: ≤ 2 диагностики + 1 причинный вариант); без него семья закрывается."""
    from reestr_v1 import Reestr
    r = reestr or Reestr(); p = r.sostoyanie()["popytki"].get(itog["id"], {}); m = (p.get("rezultat") or {}).get("metrika") or {}
    t = float(itog.get("t", 0)); treb = float(itog.get("trebuemyy_t", 0) or 0)
    z = dict(id=itog["id"], status=itog["status"], t=t, trebuemyy_t=treb, edge_bps=m.get("edge_bps"), polovinki_bps=m.get("polovinki_bps"),
             n=itog.get("n"), obratnyy_znak_proshel_by=abs(t) >= treb and t < 0,
             polovinki_soglasny=(m.get("polovinki_bps") or [0, 0])[0] * (m.get("polovinki_bps") or [0, 0])[1] > 0,
             vyvod="обратный знак значим — это НОВАЯ гипотеза с собственным prereg, не спасение" if abs(t) >= treb and t < 0
             else "ни прямой, ни обратный знак не значимы — спасение только причинным вариантом, иначе KILL")
    put = OCHERED.parent / "postmortem_avto" / f"{itog['id']}.json"; put.parent.mkdir(parents=True, exist_ok=True)
    put.write_text(json.dumps(z, ensure_ascii=False, indent=1)); return z


def uderzhat(put=OCHERED, koren=None):
    """data/factory_v3/UDERZHAT.json: [{id, prichina, poka: {path, key, value}}] — заявка не исполняется, пока в файле path
    поле key не равно value. Используется, когда правило данных исправлено после постановки заявки (без подглядывания в результат)."""
    p = Path(put).parent / "UDERZHAT.json"; out = {}
    if not p.exists(): return out
    for z in json.loads(p.read_text()):
        u = z.get("poka") or {}
        try:
            v = json.loads(((Path(koren) if koren else HERE.parent) / u["path"]).read_text()).get(u["key"])
        except Exception:
            v = None
        if v != u.get("value"): out[z["id"]] = z
    return out
