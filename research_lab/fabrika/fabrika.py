#!/usr/bin/env python3
"""fabrika.py — Factory V1, непрерывный цикл.

    очередь → прогон → детерминированный судья → вердикт → следующая
    очередь почти пуста → фабрика САМА порождает гипотезы из каталога
                          (механизм × рынок × сторона, mehanizmy.py)
    нечего прогонять    → пишет zadachi.json (переходники, данные, новый
                          пакет) и ждёт, перечитывая очередь каждые 30 мин

Правила:
  * первым идёт паритет; не пройден — фабрика стоит;
  * вердикт пишется один раз в verdikty.jsonl (только дописывание);
  * статус в очереди меняет только этот скрипт;
  * семейство на рынке после 3 NEGATIVE — на паузу (лимит «жвачки»);
  * следующая гипотеза — из семейства и рынка, где проверок меньше всего;
  * остановка в любой момент безопасна: RUNNING при старте возвращается
    в очередь, начатый прогон просто повторяется (чисел у него ещё нет).
  * LLM только предлагает механизмы (в mehanizmy.py, по версиям каталога).
    PASS/FAIL решает только судья ниже.

Команды:
    python3 fabrika.py --demon          крутить без конца (Ctrl+C — стоп)
    python3 fabrika.py                  один проход очереди и выход
    python3 fabrika.py --otchet         сводка за 24 часа
    python3 fabrika.py --doska          вся очередь
    python3 fabrika.py --samoproverka   таблица истинности судьи
    python3 fabrika.py --povtorit_tehnicheskie   вернуть упавшие технически
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, math, os, subprocess, sys, time
from collections import Counter
from pathlib import Path

DIR = Path(__file__).resolve().parent
LAB = DIR.parent
ROOT = LAB.parent
sys.path.insert(0, str(DIR))
OCHERED = DIR / "ochered.json"
VERDIKTY = DIR / "verdikty.jsonl"
ZADACHI = DIR / "zadachi.json"
REZ = DIR / "rezultaty"
ZAMOK = DIR / ".zamok"
POLY_METKA = DIR / ".poly_posledniy"
OTCHET_MD = DIR / "DAILY_RESEARCH_REPORT.md"
OTCHET_JSON = DIR / "DAILY_RESEARCH_REPORT.json"
SUTKI = 24 * 3600
BEGUNY = {"h1": DIR / "begun_h1.py", "meh": DIR / "begun_meh.py", "portfel": DIR / "begun_portfel.py", "bull": DIR / "begun_bull.py", "xsec": DIR / "begun_xsec.py", "sensor": DIR / "begun_sensor.py"}
PREDL = DIR / "predlozheniya"
PREREG_KATALOG_V2 = "research_lab/fabrika/PREREG_KATALOG_V2_2026_09_21.md"
SUDYA_PORTFEL = {"porog_t": 2.5, "min_neff": 20, "min_pokrytie": 0.8}
SUDYA_PODTV = {"porog_t": 2.0, "min_neff": 10}
PREREG_KATALOG = "research_lab/fabrika/PREREG_KATALOG_V1_2026_09_21.md"
SUDYA_KATALOG = {"porog_z": 3.1, "min_n": 50, "min_n_o3": 30}
LIMIT_ZHVACHKI = 3
TYAZHELYE = {"bull"}
PAUZA_SEMEYSTV = {"trendline_touch", "sloped_retest"}      # из предрегистрации каталога v1
MIN_V_OCHEREDI = 3
SON = 1800
KONEC = {"NEGATIVE", "POSITIVE_LEAD", "PLUS_NO_CONFIDENCE", "INCONCLUSIVE_LOW_N",
         "LEAD_BLOCKED_DATA", "PARITY_PASS", "CONFIRMED", "FAILED_CONFIRMATION",
         "CONFIRMATION_INCONCLUSIVE", "BLOCKED_DATA", "DIAGNOSTIC",
         "SHADOW_WAITING", "SHADOW_RUNNING", "SHADOW_FAILED", "READY_FOR_BUILD",
         "DEFERRED"}   # отложено решением: не бежит, не ждёт данных, вернётся только новой предрегистрацией

# ПОТОЛОК. Дальше этого фабрика не идёт НИКОГДА и ни при каких результатах.
# Привязка к брокеру, деньги и LIVE — только Codex и письменное решение владельца.
POTOLOK = "READY_FOR_BUILD"
TENI = DIR / "teni"          # спецификации теней, порождённые подтверждением
DOSE = DIR / "dose"          # пакеты READY_FOR_BUILD для Codex
MOLCHIT_CHASOV = 18          # тень, не писавшая столько часов, считается упавшей
PRIYOMKA = DIR / "priyomka.json"   # приёмка данных человеком: рынок → принятый отпечаток
# Рынки, где смена данных НЕ даёт права на прогон без человека: у золота и FX
# окна надо переобъявить, у акций вселенная может быть списком выживших.
RYNKI_S_PRIYOMKOY = {"gold", "fx7", "akcii_pit", "gold_glub", "fx7_glub"}
_PRIYOMKA_TEST = None        # подмена файла приёмки в самопроверке


def seychas():
    return dt.datetime.now(dt.timezone.utc)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "NET_FAYLA"


def zagruzit():
    return json.loads(OCHERED.read_text())


def sohranit(d):
    tmp = OCHERED.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1)); os.replace(tmp, OCHERED)


def verdikty_vse():
    if not VERDIKTY.exists():
        return []
    return [json.loads(s) for s in VERDIKTY.read_text().splitlines() if s.strip()]


def verdikty():
    return {v["id"]: v for v in verdikty_vse()}          # последний по каждому id


def zhiv(pid):
    try:
        os.kill(int(pid), 0); return True
    except Exception:
        return False


# ── судья ─────────────────────────────────────────────────────────────
def obshchiy_z(okna):
    w = [(o["edge"], o["se"]) for o in okna if o.get("kontrol_sobran") and o.get("se", 0) > 0]
    if len(w) < 2:
        return None
    sw = sum(1 / se ** 2 for _, se in w)
    return sum(ed / se ** 2 for ed, se in w) / sw * math.sqrt(sw)


def sudya_paritet(rez, etalon):
    for w, et in etalon.items():
        o = rez["okna"][w]
        if o.get("n") != et["n"] or not o.get("kontrol_sobran"):
            return "BLOCKED_PARITY", f"{w}: n={o.get('n')} вместо {et['n']}"
        if abs(o["edge"] - et["edge"]) > 0.0005:
            return "BLOCKED_PARITY", f"{w}: эдж {o['edge']:+.4f} вместо {et['edge']:+.4f}"
    return "PARITY_PASS", "повторил эталон точно"


def sudya(rez, s):
    ok = rez["okna"]; o1, o2 = ok["O1"], ok["O2"]; o3 = ok.get("O3")
    for w, o in (("O1", o1), ("O2", o2)):
        if o.get("n", 0) < s["min_n"] or not o.get("kontrol_sobran"):
            return "INCONCLUSIVE_LOW_N", f"{w}: n={o.get('n', 0)}"
    if not (o1["edge"] > 0 and o2["edge"] > 0):
        return "NEGATIVE", f"эдж O1 {o1['edge']:+.4f} ({o1['z']:+.2f}σ), O2 {o2['edge']:+.4f} ({o2['z']:+.2f}σ)"
    z = obshchiy_z([o1, o2])
    if o3 is None:
        if z >= s["porog_z"]:
            return "LEAD_BLOCKED_DATA", f"z={z:.2f}, окна O3 нет — нужны свежие данные"
        return "PLUS_NO_CONFIDENCE", f"z={z:.2f} (порог {s['porog_z']}), окна O3 нет"
    o3_ok = o3.get("kontrol_sobran") and o3.get("n", 0) >= s["min_n_o3"] and o3["edge"] > 0
    if z >= s["porog_z"] and o3_ok:
        return "POSITIVE_LEAD", f"z={z:.2f}, O3 эдж {o3['edge']:+.4f}"
    return "PLUS_NO_CONFIDENCE", f"z={z:.2f} (порог {s['porog_z']}), O3 {'+' if o3_ok else 'нет'}"


def sudya_portfel(rez, s):
    ok = rez["okna"]; v, h1, h2 = ok["VSE"], ok["H1"], ok["H2"]
    if rez.get("net_dannyh"):
        return "BLOCKED_DATA", f"нет данных: {rez['net_dannyh'][:120]}"
    if rez.get("chlenov_s_cenoy_mediana", 0) < s["min_pokrytie"] or v.get("n", 0) == 0:
        return "BLOCKED_DATA", f"у членов вселенной есть цена лишь в {rez.get('chlenov_s_cenoy_mediana', 0):.0%} случаев"
    if v.get("n_eff", 0) < s["min_neff"]:
        return "INCONCLUSIVE_LOW_N", f"эфф. периодов {v.get('n_eff')}"
    if not (v["edge"] > 0 and h1.get("edge", -1) > 0 and h2.get("edge", -1) > 0):
        return "NEGATIVE", (f"эдж {v['edge']:+.4f} (t {v['t']:+.2f}), половины "
                            f"{h1.get('edge', float('nan')):+.4f} / {h2.get('edge', float('nan')):+.4f}")
    if v["t"] >= s["porog_t"]:
        return "POSITIVE_LEAD", f"t={v['t']:.2f}, обе половины в плюсе"
    return "PLUS_NO_CONFIDENCE", f"t={v['t']:.2f} (порог {s['porog_t']})"


SUDYA_SENSOR = {"porog_p": 0.01, "min_neff": 20}


def sudya_sensor(rez, s):
    """информация в признаке: перестановочный тест по дням"""
    ok = rez["okna"]; v, h1, h2 = ok["VSE"], ok.get("H1", {}), ok.get("H2", {})
    if rez.get("net_dannyh"):
        return "BLOCKED_DATA", f"нет данных: {rez['net_dannyh'][:100]}"
    if v.get("n_eff", 0) < s["min_neff"] or "edge" not in v:
        return "INCONCLUSIVE_LOW_N", f"эфф. периодов {v.get('n_eff')}"
    if v["edge"] <= 0:
        return "NEGATIVE", f"эдж {v['edge']:+.5f}, p={v['p']:.3f}"
    if v["p"] <= s["porog_p"] and h1.get("edge", -1) > 0 and h2.get("edge", -1) > 0:
        return "POSITIVE_LEAD", f"эдж {v['edge']:+.5f}, p={v['p']:.4f}, обе половины в плюсе"
    return "PLUS_NO_CONFIDENCE", f"эдж {v['edge']:+.5f}, p={v['p']:.3f} (порог {s['porog_p']})"


def sudya_podtv(rez, s):
    """подтверждение на нетронутом окне (данные, которых обнаружение не видело)"""
    v = rez["okna"].get("VSE") or rez["okna"].get("O3") or {}
    t = v.get("t", v.get("z")); n = v.get("n_eff", v.get("n", 0))
    if not v or n < s["min_neff"]:
        return "CONFIRMATION_WAITING_DATA", f"мало данных в окне подтверждения: {n}"
    if v["edge"] <= 0:
        return "FAILED_CONFIRMATION", f"эдж {v['edge']:+.4f} на нетронутом окне"
    if t >= s["porog_t"]:
        return "CONFIRMED", f"эдж {v['edge']:+.4f}, t={t:.2f} на нетронутом окне"
    return "CONFIRMATION_INCONCLUSIVE", f"эдж {v['edge']:+.4f}, t={t:.2f} (порог {s['porog_t']})"


def sudit(item, rez):
    if item["tip"] == "diagnostika":
        v = (rez.get("okna") or {}).get("VSE") or {}
        if not v.get("n"):
            return "BLOCKED_DATA", "нет данных для диагностики"
        return "DIAGNOSTIC", f"эдж {v.get('edge', float('nan')):+.5f}, t={v.get('t', float('nan')):.2f}, n_eff={v.get('n_eff')} — не вердикт, мера для сравнения"
    if item["tip"] == "paritet" and item["begun"] == "bull":
        if rez.get("sovpadayut") and rez.get("planov", 0) >= 5:
            return "PARITY_PASS", f"нарезка = один проход, планов {rez['planov']}"
        return "BLOCKED_PARITY", f"совпадают: {rez.get('sovpadayut')}, планов {rez.get('planov')}"
    if item["tip"] == "paritet":
        return sudya_paritet(rez, item["etalon"])
    if item.get("param", {}).get("etap") == "confirmation":
        return sudya_podtv(rez, item.get("sudya", SUDYA_PODTV))
    if item["begun"] == "sensor":
        return sudya_sensor(rez, item.get("sudya", SUDYA_SENSOR))
    if item["begun"] in ("portfel", "xsec"):
        return sudya_portfel(rez, item.get("sudya", SUDYA_PORTFEL))
    v, poch = sudya(rez, item["sudya"])
    if item.get("param", {}).get("etap") == "discovery" and v == "LEAD_BLOCKED_DATA":
        return "POSITIVE_LEAD", poch.replace("окна O3 нет — нужны свежие данные", "окно подтверждения спрятано")
    return v, poch


def postavit_podtverzhdenie(d, item):
    """POSITIVE_LEAD → сам ставит подтверждение на нетронутых данных"""
    cid = item["id"] + "__PODTV"
    if any(it["id"] == cid for it in d["ochered"]):
        return None
    par = dict(item["param"], etap="confirmation")
    d["ochered"].append(dict(id=cid, tip="gipoteza", begun=item["begun"], prereg=item.get("prereg"),
                             sostoyanie="QUEUED", rynok=item.get("rynok"), semya=item.get("semya"),
                             param=par, sudya=SUDYA_PODTV, roditel=item["id"],
                             porozhdeno=seychas().isoformat(timespec="seconds")))
    return cid


# ── предложения (proposer → prereg → очередь) ─────────────────────────
def _svezh(imya):
    """модуль-каталог, перечитанный с диска. Демон живёт сутками, а новые
    механизмы и сигналы дописываются в mehanizmy.py / portfeli.py на ходу.
    Без этого перечитывания новый пакет гипотез требовал бы перезапуска."""
    import importlib
    return importlib.reload(importlib.import_module(imya))


OBYAZ = ("id", "begun", "param", "semya", "rynok", "gipoteza", "pochemu_nezavisima", "avtor")


def prinyat_predlozheniya(d, V):
    """LLM/агент кладёт JSON в predlozheniya/. Фабрика проверяет и замораживает.
    Предложение может ссылаться только на существующий код (сигнал/механизм);
    числа и вердикт — только судья."""
    if not PREDL.exists():
        return []
    _m = _svezh("mehanizmy"); MEHANIZMY, RYNKI = _m.MEHANIZMY, _m.RYNKI
    SIGNALY = _svezh("portfeli").SIGNALY
    (PREDL / "prinyato").mkdir(exist_ok=True); (PREDL / "otkloneno").mkdir(exist_ok=True)
    _, neg = schet_proverok(d, V); est = {it["id"] for it in d["ochered"]}; prin = []
    for f in sorted(PREDL.glob("*.json")):
        prich = None
        try:
            pr = json.loads(f.read_text())
        except Exception as e:
            pr, prich = {}, f"не JSON: {e}"
        if not prich:
            net = [k for k in OBYAZ if not pr.get(k)]
            if net: prich = f"нет полей: {net}"
            elif pr["id"] in est: prich = "такой id уже есть"
            elif pr["begun"] not in BEGUNY: prich = f"нет прогонщика {pr['begun']}"
            elif pr["begun"] == "portfel" and pr["param"].get("signal") not in SIGNALY: prich = "нет такого сигнала в portfeli.py"
            elif pr["begun"] == "meh" and (pr["param"].get("meh") not in MEHANIZMY or pr["param"].get("rynok") not in RYNKI):
                prich = "нет такого механизма/рынка в mehanizmy.py"
            elif pr["semya"] in PAUZA_SEMEYSTV or neg[(pr["rynok"], pr["semya"])] >= LIMIT_ZHVACHKI:
                prich = f"семейство {pr['semya']} на паузе (лимит жвачки)"
        if prich:
            f.replace(PREDL / "otkloneno" / f.name)
            (PREDL / "otkloneno" / (f.stem + ".prichina.txt")).write_text(prich); continue
        dst = PREDL / "prinyato" / f.name; f.replace(dst)
        par = dict(pr["param"]); par.setdefault("etap", "discovery")
        d["ochered"].append(dict(id=pr["id"], tip="gipoteza", begun=pr["begun"], param=par,
                                 prereg=str(dst.relative_to(ROOT)), sostoyanie="QUEUED", rynok=pr["rynok"],
                                 semya=pr["semya"], avtor=pr["avtor"],
                                 sudya=pr.get("sudya") or (SUDYA_PORTFEL if pr["begun"] == "portfel" else SUDYA_KATALOG),
                                 porozhdeno=seychas().isoformat(timespec="seconds")))
        est.add(pr["id"]); prin.append(pr["id"])
    return prin


# ── каталог: порождение гипотез ───────────────────────────────────────
def schet_proverok(d, V):
    """сколько вердиктов и сколько NEGATIVE в каждом (рынок, семейство)"""
    vse, neg = Counter(), Counter()
    for it in d["ochered"]:
        v = V.get(it["id"])
        if v and v["verdikt"] in KONEC and it.get("tip") not in ("paritet", "diagnostika"):
            key = (it.get("rynok"), it.get("semya"))
            vse[key] += 1; neg[key] += v["verdikt"] == "NEGATIVE"
    return vse, neg


def porodit(d, V, skolko):
    _m = _svezh("mehanizmy"); MEHANIZMY, RYNKI = _m.MEHANIZMY, _m.RYNKI
    est = {it["id"] for it in d["ochered"]}
    vse, neg = schet_proverok(d, V)
    kand = []
    for meh, M in MEHANIZMY.items():
        for ry in RYNKI:
            if RYNKI[ry].get("porozhdat") is False:        # только явный ре-тест
                continue
            for side in ("long", "short"):
                hid = f"{meh}__{ry}__{side}"
                if hid in est or neg[(ry, M["semya"])] >= LIMIT_ZHVACHKI:
                    continue
                kand.append(((vse[(ry, M["semya"])], sum(v for (r, _), v in vse.items() if r == ry), len(kand)),
                             hid, meh, ry, side, M))
    SIGNALY = _svezh("portfeli").SIGNALY
    for sg, P in SIGNALY.items():
        hid = f"P_{sg}"
        if hid in est or neg[(P["rynok"], P["semya"])] >= LIMIT_ZHVACHKI:
            continue
        kand.append(((vse[(P["rynok"], P["semya"])], sum(v for (r, _), v in vse.items() if r == P["rynok"]), len(kand)),
                     hid, sg, P["rynok"], None, P))
    kand.sort()
    novye = []
    for _, hid, meh, ry, side, M in kand[:skolko]:
        if side is None:
            it = dict(id=hid, tip="gipoteza", begun="portfel", prereg=M.get("prereg", PREREG_KATALOG_V2), sostoyanie="QUEUED",
                      rynok=ry, semya=M["semya"], slot=M.get("slot"), param=dict(signal=meh, etap="discovery"),
                      sudya=SUDYA_PORTFEL, porozhdeno=seychas().isoformat(timespec="seconds"))
        else:
            it = dict(id=hid, tip="gipoteza", begun="meh", prereg=(PREREG_KATALOG_V2 if ry == "fx7" else PREREG_KATALOG),
                      sostoyanie="QUEUED", rynok=ry, semya=M["semya"],
                      param=dict(meh=meh, rynok=ry, side=side, **({"etap": "discovery"} if ry == "fx7" else {})),
                      sudya=SUDYA_KATALOG, porozhdeno=seychas().isoformat(timespec="seconds"))
        d["ochered"].append(it); vse[(ry, M["semya"])] += 1; novye.append(hid)
    return novye


def vybrat(d, V, krome=None):
    vse, _ = schet_proverok(d, V)
    par_ok = {it["begun"] for it in d["ochered"] if it["tip"] == "paritet" and it["sostoyanie"] == "PARITY_PASS"}
    par_est = {it["begun"] for it in d["ochered"] if it["tip"] == "paritet"}
    sost = {it["id"]: it["sostoyanie"] for it in d["ochered"]}
    def gotovo_posle(it):
        """диагностика ждёт, пока родитель получит окончательный ответ (и подтверждение, если оно было)"""
        rod = it.get("posle")
        if not rod:
            return True
        if sost.get(rod) in (None, "QUEUED", "RUNNING"):
            return False
        return sost.get(rod) != "POSITIVE_LEAD" or sost.get(rod + "__PODTV") not in (None, "QUEUED", "RUNNING")
    run = [(i, it) for i, it in enumerate(d["ochered"]) if it["sostoyanie"] == "QUEUED"
           and it.get("begun") in BEGUNY and mozhno_progonyat(it) and it["id"] != krome and gotovo_posle(it)
           and (it["tip"] == "paritet" or it["begun"] not in par_est or it["begun"] in par_ok)]
    if not run:
        return None
    par = [it for _, it in run if it["tip"] == "paritet" and it["begun"] not in TYAZHELYE]
    if par:
        return par[0]
    # тяжёлые прогоны (часы) — после быстрых; паритет тяжёлого — перед его гипотезами
    run.sort(key=lambda t: (t[1]["begun"] in TYAZHELYE, t[1]["tip"] != "paritet",
                            vse[(t[1].get("rynok"), t[1].get("semya"))],
                            sum(v for (r, _), v in vse.items() if r == t[1].get("rynok")), t[0]))
    return run[0][1]


# ── служебное ─────────────────────────────────────────────────────────
def otpechatok_dannyh(rynok):
    papki = {"kripto_pit": ["data/pit_daily"], "kripto_pit50": ["data/pit_daily", "data/basis"], "xsec": ["data/pit_daily", "data/basis"], "kripto_pit50_poly": ["data/pit_daily", "data/basis", "data/poly/istoriya"], "akcii_pit": ["data/alpaca_pit_daily_v1/bars"],
             "crypto137": ["data/h1"], "gold": ["data/zoloto_h1"], "fx7": ["data/fx_h1"], "gold_glub": ["data/zoloto_h1"], "fx7_glub": ["data/fx_h1"], "crypto137_m5": ["data/m5_posle"]}.get(rynok, [])
    n = sz = 0
    for pp in papki:
        q = LAB / pp
        if q.exists():
            for f in q.iterdir():
                n += 1; sz += f.stat().st_size
    return f"{n}:{sz}"


def prinyatye():
    if _PRIYOMKA_TEST is not None:
        return _PRIYOMKA_TEST
    try:
        return json.loads(PRIYOMKA.read_text()) if PRIYOMKA.exists() else {}
    except Exception:
        return {}                       # битый файл приёмки = ничего не принято


def mozhno_progonyat(it):
    """Единственные ворота перед прогоном. Рынок с приёмкой (или пункт с пометкой
    trebuet_priyomki) прогоняется только если человек принял ИМЕННО текущий
    отпечаток данных. Проверяется и при синхронизации, и в момент выбора —
    чтобы ни одна ветка не смогла взвести пункт в обход."""
    ry = it.get("rynok")
    if ry not in RYNKI_S_PRIYOMKOY and not it.get("trebuet_priyomki"):
        return True
    return prinyatye().get(ry, {}).get("otpechatok") == otpechatok_dannyh(ry)


def kod_otpechatok():
    """Отпечаток кода фабрики. 30.09 демон, запущенный 28.09 в 09:35, крутил код
    ДО исправления 10:04 (Python не перечитывает модуль) и вынес 8 вердиктов по
    старой логике. Демон обязан замечать, что его код сменился, и останавливаться."""
    fayly = [Path(__file__).resolve(), DIR / "mehanizmy.py", *BEGUNY.values()]
    return "|".join(sha(f) for f in fayly)


def sinhronizirovat(d, V):
    for it in d["ochered"]:
        # пункт, созданный сразу в ожидании данных, вердикта ещё не имеет: сравнивать
        # не с чем. Поэтому отпечаток папки запоминается в момент постановки.
        if it["sostoyanie"] == "BLOCKED_DATA" and (not V.get(it["id"]) or it.get("trebuet_priyomki")):
            bylo = it.get("otpechatok_pri_postanovke")
            if bylo is None:
                # первая встреча: запомнить и НЕ проваливаться дальше
                it["otpechatok_pri_postanovke"] = otpechatok_dannyh(it.get("rynok"))
                continue
            elif bylo != otpechatok_dannyh(it.get("rynok")):
                # Данные ИЗМЕНИЛИСЬ — это ещё не значит, что они ГОДНЫ.
                # Пункт с пометкой trebuet_priyomki ждёт человека: у акций
                # вселенная может оказаться списком выживших, у золота окна
                # надо переобъявить до прогона. Автовзвод здесь потратил бы
                # замороженный тест на непроверенных данных.
                if it.get("trebuet_priyomki") or not mozhno_progonyat(it):
                    it.setdefault("dannye_izmenilis", seychas().isoformat(timespec="seconds"))
                else:
                    it["sostoyanie"] = "QUEUED"
                    it["dannye_prishli"] = seychas().isoformat(timespec="seconds")
                continue
        v = V.get(it["id"])
        if (v and it["sostoyanie"] in ("BLOCKED_DATA", "CONFIRMATION_WAITING_DATA") and v.get("dannye")
                and v["dannye"] != otpechatok_dannyh(it.get("rynok"))):
            if not mozhno_progonyat(it):
                it.setdefault("dannye_izmenilis", seychas().isoformat(timespec="seconds"))
                continue
            it["sostoyanie"] = "QUEUED"; it["zhdyot_verdikt_posle"] = seychas().isoformat(timespec="seconds")
            continue
        if it.get("zhdyot_verdikt_posle") and v and v["kogda"] < it["zhdyot_verdikt_posle"]:
            continue
        if it["sostoyanie"] == "RUNNING" and not zhiv(it.get("pid", 0)):
            it["sostoyanie"] = "QUEUED"; it.setdefault("prervano", []).append(seychas().isoformat(timespec="seconds"))
        if v and it["sostoyanie"] == "QUEUED" and v["verdikt"] != "FAILED_TECHNICAL":
            it["sostoyanie"] = v["verdikt"]
    for it in d["ochered"]:
        if it["tip"] == "paritet" and it["begun"] == "bull" and it["sostoyanie"] == "BLOCKED_PARITY":
            for x in d["ochered"]:
                if x["begun"] == "bull" and x["tip"] != "paritet" and x["sostoyanie"] == "QUEUED":
                    x["sostoyanie"] = "BLOCKED_ADAPTER"; x["blocker"] = "паритет нарезки не пройден"
    # находка, не пережившая подтверждение, перестаёт быть находкой: иначе она
    # вечно висит в дневном отчёте как повод вмешаться. Окно подтверждения
    # потрачено, тот же механизм повторно не прогоняется.
    sost_all = {x["id"]: x["sostoyanie"] for x in d["ochered"]}
    for it in d["ochered"]:
        if it["sostoyanie"] == "POSITIVE_LEAD" and sost_all.get(it["id"] + "__PODTV") == "FAILED_CONFIRMATION":
            it["sostoyanie"] = "NEGATIVE"
            it.setdefault("chto_vernyot", "находка не пережила подтверждение на нетронутом окне; "
                                          "окно потрачено, повтор того же механизма запрещён — "
                                          "вернёт только новая предрегистрация на новых данных")
    # последний рубеж: взведённый без приёмки пункт возвращается в ожидание,
    # откуда бы он ни пришёл (генератор, старая ветка, ручная правка)
    for it in d["ochered"]:
        if it["sostoyanie"] == "QUEUED" and not mozhno_progonyat(it):
            it["sostoyanie"] = "BLOCKED_DATA"
            it["blocker"] = f"ждёт ПРИЁМКИ данных рынка {it.get('rynok')} человеком (fabrika.py --prinyat {it.get('rynok')})"
            it.setdefault("vozvrashchen_iz_queued", seychas().isoformat(timespec="seconds"))
    vse, neg = schet_proverok(d, V)
    for it in d["ochered"]:
        if it["sostoyanie"] == "QUEUED" and it.get("tip") != "paritet" and (
                it.get("semya") in PAUZA_SEMEYSTV or neg[(it.get("rynok"), it.get("semya"))] >= LIMIT_ZHVACHKI):
            it["sostoyanie"] = "FAMILY_PAUSED"


def zapisat_zadachi(d):
    Z = []
    for it in d["ochered"]:
        s = it["sostoyanie"]
        if s == "BLOCKED_ADAPTER":
            Z.append(dict(tip="ADAPTER", id=it["id"], chto=it.get("blocker", ""), kto="Claude"))
        elif s in ("BLOCKED_DATA", "LEAD_BLOCKED_DATA"):
            Z.append(dict(tip="DATA", id=it["id"], chto=it.get("blocker", "нужны свежие/глубже данные"), kto="Claude"))
        elif s == "CONFIRMED":
            Z.append(dict(tip="SHADOW", id=it["id"], chto="подтверждено на нетронутых данных → проспективная тень", kto="Claude"))
        elif s == "CONFIRMATION_WAITING_DATA":
            Z.append(dict(tip="DATA", id=it["id"], chto="ждёт свежих данных для подтверждения", kto="Claude"))
        elif s == "WAITING_SHADOW":
            Z.append(dict(tip="SHADOW_READOUT", id=it["id"], chto=it.get("blocker", ""), kto=it.get("vladelec", "")))
    _m = _svezh("mehanizmy"); MEHANIZMY, RYNKI = _m.MEHANIZMY, _m.RYNKI
    est = {it["id"] for it in d["ochered"]}
    ostalos = sum(1 for m in MEHANIZMY for r in RYNKI for s in ("long", "short") if f"{m}__{r}__{s}" not in est)
    SIGNALY = _svezh("portfeli").SIGNALY
    ostalos += sum(1 for sg in SIGNALY if f"P_{sg}" not in est)
    if ostalos == 0 and not any(it["sostoyanie"] == "QUEUED" for it in d["ochered"]):
        Z.append(dict(tip="PROPOSER", id="novyy_paket", kto="Claude / агент",
                      chto="каталоги пройдены: положи новые предложения в predlozheniya/*.json (новые механизмы — кодом в mehanizmy.py/portfeli.py)"))
    tmp = ZADACHI.with_suffix(".tmp")
    tmp.write_text(json.dumps({"obnovleno": seychas().isoformat(timespec="seconds"), "zadachi": Z},
                              ensure_ascii=False, indent=1)); os.replace(tmp, ZADACHI)
    return Z


def heshi(item):
    h = {"begun": sha(BEGUNY[item["begun"]]), "fabrika": sha(Path(__file__))}
    if item["begun"] == "h1":
        h["random_control"] = sha(LAB / "random_control.py")
        h["strategiya"] = sha(ROOT / "strategies" / f"{item['param']['mod']}.py")
    elif item["begun"] in ("portfel", "xsec", "sensor"):
        h["portfeli"] = sha(DIR / "portfeli.py"); h["regime_v1"] = sha(DIR / "regime_v1.py")
        if item["begun"] == "xsec":
            h["xsec_v3_reference"] = sha(LAB / "xsec_v3_reference.py")
    elif item["begun"] == "bull":
        for f in ("strategies/event_expansion_retest_long_mtf_v1.py", "bot/event_long_execution_v1.py",
                  "bot/level_snapshot_v1.py"):
            h[f] = sha(ROOT / f)
    else:
        h["mehanizmy"] = sha(DIR / "mehanizmy.py")
    if item.get("prereg"):
        h["prereg"] = sha(ROOT / item["prereg"])
    return h


def posmertno(item, rez, d, V):
    ok = rez["okna"]
    plohie = [f"{w}: эдж {o['edge']:+.4f} ({o['z']:+.2f}σ), n={o['n']}"
              for w, o in ok.items() if o.get("kontrol_sobran") and o["edge"] <= 0]
    _, neg = schet_proverok(d, V)
    key = (item.get("rynok"), item.get("semya"))
    sled = vybrat(d, V, krome=item["id"])
    return {"chto_ne_srabotalo": plohie,
            "semya": f"{item.get('semya')} на {item.get('rynok')}: NEGATIVE {neg[key]} из {LIMIT_ZHVACHKI}"
                     + (" — семейство на паузу" if neg[key] >= LIMIT_ZHVACHKI else ""),
            "sleduyushchaya": sled["id"] if sled else "очередь пуста — будет порождение из каталога",
            "deshevyy_test": (f"{sled['id']} — тот же прогонщик, минуты" if sled else "—")}


def progon(item):
    REZ.mkdir(exist_ok=True)
    out = REZ / f"{item['id']}.json"
    if out.exists():
        out.unlink()
    cmd = [sys.executable, str(BEGUNY[item["begun"]]), "--param",
           json.dumps(item["param"], ensure_ascii=False), "--vyhod", str(out)]
    t0 = time.time(); r = subprocess.run(cmd, cwd=str(DIR))
    if r.returncode != 0 or not out.exists():
        return None, round(time.time() - t0)
    return json.loads(out.read_text()), round(time.time() - t0)


def odin_shag():
    """один прогон. Возвращает id или None, если прогонять нечего."""
    d = zagruzit(); V = verdikty(); sinhronizirovat(d, V)
    if any(it["tip"] == "paritet" and it["begun"] == "h1" and it["sostoyanie"] == "BLOCKED_PARITY" for it in d["ochered"]):
        sohranit(d); print("СТОП: паритет не пройден."); return "STOP"
    prin = prinyat_predlozheniya(d, V)
    if prin:
        print(f"＋ принято предложений: {', '.join(prin)}", flush=True)
    for sob in proverit_teni(d):
        print(f"◆ {sob}", flush=True)
    queued = sum(1 for it in d["ochered"] if it["sostoyanie"] == "QUEUED" and it.get("begun") in BEGUNY)
    if queued < MIN_V_OCHEREDI:
        novye = porodit(d, V, 2 * MIN_V_OCHEREDI - queued)
        if novye:
            print(f"＋ порождено из каталога: {', '.join(novye)}", flush=True)
    sled = vybrat(d, V)
    if sled is None:
        sohranit(d); zapisat_zadachi(d); return None
    if sled["tip"] != "paritet" and not any(it["tip"] == "paritet" and it["begun"] == "h1" and it["sostoyanie"] == "PARITY_PASS"
                                            for it in d["ochered"]):
        sohranit(d); print("СТОП: сначала паритет."); return "STOP"
    sled["sostoyanie"] = "RUNNING"; sled["pid"] = os.getpid(); sled["start"] = seychas().isoformat(timespec="seconds")
    sohranit(d); zapisat_zadachi(d)
    print(f"\n▶ {sled['id']}  {seychas():%H:%M} UTC", flush=True)
    rez, sek = progon(sled)
    if rez is None:
        verd, pochemu = "FAILED_TECHNICAL", "прогонщик упал, см. вывод выше"
    else:
        verd, pochemu = sudit(sled, rez)
    d = zagruzit()
    for it in d["ochered"]:
        if it["id"] == sled["id"]:
            it["sostoyanie"] = verd; it.pop("pid", None); it.pop("zhdyot_verdikt_posle", None); cur = it
    zap = {"id": sled["id"], "verdikt": verd, "pochemu": pochemu, "kogda": seychas().isoformat(timespec="seconds"),
           "sekund": sek, "heshi": heshi(sled), "okna": (rez or {}).get("okna"), "rezultat_kratko": ({k: v for k, v in rez.items() if k != "okna" and not isinstance(v, (list, dict)) or k in ("simvoly",)} if rez else None), "param": sled.get("param"),
           "rynok": sled.get("rynok"), "semya": sled.get("semya"), "dannye": otpechatok_dannyh(sled.get("rynok"))}
    V[sled["id"]] = zap
    if verd == "NEGATIVE":
        zap["posmertno"] = posmertno(cur, rez, d, V)
    with VERDIKTY.open("a") as f:
        f.write(json.dumps(zap, ensure_ascii=False) + "\n")
    obnovit_reestr(d, V)
    podtv = postavit_podtverzhdenie(d, cur) if verd == "POSITIVE_LEAD" else None
    ten = postavit_ten(d, cur, zap) if verd == "CONFIRMED" else None
    sinhronizirovat(d, V); sohranit(d); zapisat_zadachi(d)
    print(f"■ {sled['id']}: {verd} — {pochemu}  ({sek} с)", flush=True)
    if podtv:
        print(f"   ↳ поставлено подтверждение на нетронутых данных: {podtv}", flush=True)
    if ten:
        print(f"   ↳ порождена спецификация тени: {ten} (запускает владелец)", flush=True)
    if "posmertno" in zap:
        print(f"   ↳ {zap['posmertno']['semya']}; дальше: {zap['posmertno']['sleduyushchaya']}", flush=True)
    return sled["id"]


def postavit_ten(d, it, zap):
    """CONFIRMED → спецификация тени. Порождается автоматически, но ЗАПУСКАЕТ
    процесс владелец: автозапуска на этой машине нет и не будет."""
    TENI.mkdir(exist_ok=True)
    f = TENI / f"{it['id']}.json"
    if f.exists():
        return None
    zhurnal = f"research_lab/data/ten_{it['id']}.jsonl"
    spec = {
        "id": it["id"], "porozhdena": seychas().isoformat(timespec="seconds"),
        "iz_verdikta": f"research_lab/fabrika/verdikty.jsonl#{it['id']}@{zap['kogda']}",
        "prereg": it.get("prereg"), "rynok": it.get("rynok"), "semya": it.get("semya"),
        "slot": it.get("slot"), "begun": it.get("begun"),
        "strategiya_zamorozhena": it.get("param"),
        "heshi_koda": zap.get("heshi"),
        "vorota": {"resheniy": 100, "min_neff": 20, "porog_t": 2.0},
        "trebovaniya_k_svidetelstvam": [
            "журнал только дописывается, задним числом не правится",
            "момент старта фиксируется на диске один раз и не сбрасывается при перезапуске",
            "засчитываются только дни, начавшиеся ПОСЛЕ первого запуска",
            "издержки и фандинг вычитаются по факту, не моделируются постфактум",
            "контроль: случайная корзина того же размера в тот же день",
            "R и деньги до ворот не считаются и не показываются",
        ],
        "zhurnal": zhurnal,
        "bienie": f"research_lab/data/ten_{it['id']}.bienie",
        "ocenshchik": None,        # команда; должна печатать строку «ИТОГ: PASS|FAIL|MALO ...»
        "komanda_zapuska": None,
        "sostoyanie": "ZHDYOT_PROGONSHCHIKA",
        "chto_nuzhno_ot_cheloveka": ("написать прогонщик тени для этого механизма по образцу "
                                     "research_lab/ten_sila.py, вписать сюда ocenshchik и komanda_zapuska, "
                                     "затем запустить процесс вручную"),
    }
    f.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    it["sostoyanie"] = "SHADOW_WAITING"; it["ten_spec"] = str(f.relative_to(ROOT))
    return str(f.relative_to(ROOT))


def _itog_teni(vyvod):
    """последняя строка вида «ИТОГ: PASS|FAIL|MALO …» — единственное, что читается"""
    for ln in reversed((vyvod or "").splitlines()):
        if ln.strip().startswith("ИТОГ:"):
            sl = ln.split(":", 1)[1].strip().split()
            return (sl[0] if sl else ""), ln.strip()
    return "", ""


def proverit_teni(d):
    """каждый круг: жива ли тень, дошла ли до ворот, и если дошла — вердикт.
    Вердикт выносит объявленный заранее оценщик, а не фабрика."""
    if not TENI.exists():
        return []
    sobytiya = []
    sost = {it["id"]: it for it in d["ochered"]}
    for f in sorted(TENI.glob("*.json")):
        try:
            sp = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        it = sost.get(sp["id"])
        if it is None or it["sostoyanie"] not in ("SHADOW_WAITING", "SHADOW_RUNNING"):
            continue
        zh = ROOT / sp["zhurnal"]
        # Живость меряем по БИЕНИЮ, а не по журналу решений: тень может честно
        # работать неделями и не принять ни одного решения (ждёт своих дней),
        # и это не повод считать её мёртвой. Журнал — запасной вариант.
        bien = ROOT / sp["bienie"] if sp.get("bienie") else None
        istochnik = bien if (bien and bien.exists()) else (zh if zh.exists() else None)
        if istochnik is not None:
            it["sostoyanie"] = "SHADOW_RUNNING"
            molchit = (time.time() - istochnik.stat().st_mtime) / 3600
            it["ten_molchit_chasov"] = round(molchit, 1)
            if molchit > MOLCHIT_CHASOV:
                sobytiya.append(f"тень {sp['id']} молчит {molchit:.0f} ч — процесс, похоже, упал")
                continue
        else:
            it["ten_molchit_chasov"] = None
        if not sp.get("ocenshchik"):
            continue
        try:
            n = sum(1 for x in zh.read_text(encoding="utf-8").splitlines()
                    if x.strip() and json.loads(x).get("zakryto")) if zh.exists() else 0
        except Exception:
            n = 0
        it["ten_resheniy"] = n
        if n < sp["vorota"]["resheniy"]:
            continue
        r = subprocess.run(sp["ocenshchik"], capture_output=True, text=True, cwd=str(ROOT), shell=isinstance(sp["ocenshchik"], str))
        itog, stroka = _itog_teni(r.stdout)
        if itog == "PASS":
            put = sobrat_dose(it, sp, stroka)
            it["sostoyanie"] = POTOLOK; it["dose"] = put
            sobytiya.append(f"тень {sp['id']} прошла ворота → {POTOLOK}: {put}")
        elif itog == "FAIL":
            it["sostoyanie"] = "SHADOW_FAILED"; it["chto_vernyot"] = f"тень не прошла ворота: {stroka}"
            sobytiya.append(f"тень {sp['id']} не прошла ворота: {stroka}")
    return sobytiya


def sobrat_dose(it, sp, stroka):
    """READY_FOR_BUILD: всё, что нужно Codex, и ничего, что нужно брокеру."""
    DOSE.mkdir(exist_ok=True)
    f = DOSE / f"{it['id']}_READY_FOR_BUILD.md"
    t = [f"# {it['id']} — READY_FOR_BUILD", "",
         f"Собрано фабрикой автоматически {seychas():%Y-%m-%d %H:%M} UTC.",
         "Это ПОТОЛОК автоматизации. Привязка к брокеру, размер позиции, деньги и LIVE —",
         "только Codex и отдельное письменное решение владельца. Фабрика к ним не прикасается.",
         "", "## Замороженная стратегия", "",
         "    " + json.dumps(sp.get("strategiya_zamorozhena"), ensure_ascii=False),
         f"    прогонщик: {sp.get('begun')}",
         f"    предрегистрация: {sp.get('prereg')}",
         f"    хеши кода на момент вердикта: {json.dumps(sp.get('heshi_koda'), ensure_ascii=False)}",
         "", "## Контракт на данные", "",
         f"    рынок: {sp.get('rynok')}",
         f"    журнал тени: {sp.get('zhurnal')}",
         "    вход считается только по барам, закрывшимся строго ДО решения",
         "    членство во вселенной — на дату, с делистингами",
         "", "## Издержки и допущения о риске", "",
         "    издержки и фандинг вычтены по факту, не смоделированы",
         "    проскальзывание НЕ моделировалось: это работа Codex на PAPER",
         "    заёмные ограничения на шорт НЕ моделировались",
         "    размер книги не моделировался",
         "", "## Требования к паритету и свидетельствам", "",
         "    прогонщик Codex обязан повторить журнал тени бар в бар на том же окне",
         "    расхождение хотя бы в одном решении — стоп, разбор причины до продолжения",
         "    порог тени и ворота менять запрещено: они объявлены в предрегистрации",
         "", "## Итог тени", "", f"    {stroka}",
         "", "## Что дальше делает человек", "",
         "    1. Codex: паритет прогонщика против журнала тени",
         "    2. Codex: PAPER со стоп-краном",
         "    3. владелец: письменное решение о деньгах. Не раньше."]
    f.write_text("\n".join(t) + "\n", encoding="utf-8")
    return str(f.relative_to(ROOT))


def obnovit_reestr(d=None, V=None):
    """журнал → канонический реестр (под замком, атомарно) → доска-вид"""
    try:
        import reestr_sink, master
        d = d or zagruzit(); V = V or verdikty()
        n = reestr_sink.primenit(reestr_sink.iz_verdiktov(d["ochered"], V))
        master.postroit()
        return n
    except Exception as e:                     # реестр не должен ронять фабрику
        print(f"   ! реестр не обновлён: {e}", flush=True)
        return -1


def s_zamkom(fn):
    if ZAMOK.exists() and zhiv(ZAMOK.read_text().strip() or 0) and ZAMOK.read_text().strip() != str(os.getpid()):
        print(f"Фабрика уже крутится (pid {ZAMOK.read_text().strip()})."); return
    ZAMOK.write_text(str(os.getpid()))
    try:
        fn()
    except KeyboardInterrupt:
        print("\nОстановлено вручную. Очередь сохранена; начатый прогон вернётся в очередь при старте.")
    finally:
        ZAMOK.unlink(missing_ok=True)


def odin_prohod():
    while True:
        r = odin_shag()
        if r in (None, "STOP"):
            if r is None:
                print("Прогонять нечего. Задачи для людей — в zadachi.json:"); pokazat_zadachi()
            return


def poly_sutki():
    """раз в сутки: дельта Polymarket (новые рынки, история нужных, круг снимков).
    Автозапуска на машине нет: это делает та же фабрика, пока она крутится."""
    posl = float(POLY_METKA.read_text()) if POLY_METKA.exists() else 0.0
    if time.time() - posl < SUTKI:
        return None
    print(f"\n◇ суточный сбор Polymarket {seychas():%H:%M} UTC", flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(DIR / "poly_sbor.py"), "--delta"], cwd=str(DIR))
    POLY_METKA.write_text(str(time.time()))
    print(f"◇ сбор закончен за {round(time.time() - t0)} с, код {r.returncode}", flush=True)
    return r.returncode


def otchet_dnya():
    """Одна строка состояния конвейера и короткий список того, что ждёт человека.

    Формат строки задан владельцем:
        tested | killed | leads | confirmed | shadows | ready_for_build | blocked | owner_action
    """
    d = zagruzit(); V = verdikty()
    gran = seychas() - dt.timedelta(hours=24)
    vv = [v for v in verdikty_vse() if dt.datetime.fromisoformat(v["kogda"]).replace(tzinfo=dt.timezone.utc) >= gran
          and v["verdikt"] not in ("PARITY_PASS", "BLOCKED_PARITY", "FAILED_TECHNICAL")]
    c = Counter(v["verdikt"] for v in vv)
    sost = Counter(it["sostoyanie"] for it in d["ochered"])
    ist = LAB / "data/poly/istoriya"
    poly = {"rynkov_v_istorii": len(list(ist.glob("*.json"))) if ist.exists() else 0,
            "posledniy_sbor": (dt.datetime.fromtimestamp(float(POLY_METKA.read_text()), dt.timezone.utc).isoformat(timespec="seconds")
                               if POLY_METKA.exists() else None)}

    ubito = c["NEGATIVE"] + c["FAILED_CONFIRMATION"]
    lidy = [it["id"] for it in d["ochered"] if it["sostoyanie"] == "POSITIVE_LEAD"]
    podtv = [it["id"] for it in d["ochered"] if it["sostoyanie"] == "CONFIRMED"]
    teni = [it for it in d["ochered"] if it["sostoyanie"] in ("SHADOW_WAITING", "SHADOW_RUNNING")]
    gotovo = [it["id"] for it in d["ochered"] if it["sostoyanie"] == POTOLOK]
    zhdut_dannyh = [it["id"] for it in d["ochered"] if it["sostoyanie"] in ("BLOCKED_DATA", "CONFIRMATION_WAITING_DATA")]
    zhdut_perehodnika = [it["id"] for it in d["ochered"] if it["sostoyanie"] == "BLOCKED_ADAPTER"]
    slomano = [it["id"] for it in d["ochered"] if it["sostoyanie"] == "FAILED_TECHNICAL"]
    ochered_pusta = not any(it["sostoyanie"] == "QUEUED" and it.get("begun") in BEGUNY for it in d["ochered"])

    # ЧТО ЖДЁТ ЧЕЛОВЕКА. Только то, где машина физически не может продолжить сама.
    nuzhno = []
    if gotovo:
        nuzhno.append(f"Codex: принять пакет READY_FOR_BUILD — {', '.join(gotovo)}")
    for it in teni:
        sp = it.get("ten_spec")
        if it["sostoyanie"] == "SHADOW_WAITING":
            nuzhno.append(f"владелец: запустить тень {it['id']} (спецификация {sp})")
        elif it.get("ten_molchit_chasov") and it["ten_molchit_chasov"] > MOLCHIT_CHASOV:
            nuzhno.append(f"владелец: тень {it['id']} молчит {it['ten_molchit_chasov']:.0f} ч — поднять заново")
    if slomano:
        nuzhno.append(f"разобрать технический сбой: {', '.join(slomano)}")
    priyomka = [it["id"] for it in d["ochered"]
                if it.get("trebuet_priyomki") and it.get("dannye_izmenilis")]
    if priyomka:
        nuzhno.append("данные изменились, нужна ПРИЁМКА до прогона: " + ", ".join(priyomka))
    if zhdut_dannyh:
        nuzhno.append(f"нужны данные для {len(zhdut_dannyh)} пунктов — что именно, в zadachi.json")
    if ochered_pusta and not zhdut_dannyh and not zhdut_perehodnika and not teni:
        nuzhno.append("механизмы исчерпаны: очередь пуста и ничто не ждёт ни данных, ни тени")

    # ТРИ РАЗНЫХ ПУСТЫХ ОЧЕРЕДИ
    if not ochered_pusta:
        pochemu_pusto = None
    elif teni:
        pochemu_pusto = "ждём тень"
    elif zhdut_dannyh or zhdut_perehodnika:
        pochemu_pusto = "ждём данные"
    else:
        pochemu_pusto = "механизмы исчерпаны"

    stroka = (f"tested {len(vv)} | killed {ubito} | leads {len(lidy)} | confirmed {len(podtv)} | "
              f"shadows {len(teni)} | ready_for_build {len(gotovo)} | "
              f"blocked {len(zhdut_dannyh) + len(zhdut_perehodnika)} | owner_action {len(nuzhno)}")

    j = {"kogda": seychas().isoformat(timespec="seconds"), "stroka": stroka,
         "tested": len(vv), "killed": ubito, "leads": lidy, "confirmed": podtv,
         "shadows": [x["id"] for x in teni], "ready_for_build": gotovo,
         "blocked": {"dannye": zhdut_dannyh, "perehodnik": zhdut_perehodnika},
         "ochered_pusta": ochered_pusta, "pochemu_pusto": pochemu_pusto,
         "za_sutki": dict(c), "sostoyaniya": dict(sost), "poly": poly,
         "owner_action": nuzhno, "trebuetsya_vmeshatelstvo": bool(nuzhno),
         "zhdut_priyomki": priyomka,
         "potolok": POTOLOK}
    OTCHET_JSON.write_text(json.dumps(j, ensure_ascii=False, indent=1))

    t = [f"# Отчёт за сутки — {seychas():%Y-%m-%d %H:%M} UTC", "", "    " + stroka, ""]
    if pochemu_pusto:
        t += [f"Очередь пуста: {pochemu_pusto}.", ""]
    t += [f"Polymarket: рынков {poly['rynkov_v_istorii']}, последний сбор {poly['posledniy_sbor']}", "",
          f"**ТРЕБУЕТСЯ ВМЕШАТЕЛЬСТВО: {'ДА' if nuzhno else 'НЕТ'}**"]
    if nuzhno:
        t += [""] + [f"- {x}" for x in nuzhno]
    t += ["", f"Потолок автоматизации: {POTOLOK}. Брокер, деньги и LIVE — Codex и владелец."]
    OTCHET_MD.write_text("\n".join(t) + "\n")
    return j

def demon():
    print(f"Фабрика в непрерывном режиме с {seychas():%Y-%m-%d %H:%M} UTC. Ctrl+C — стоп.", flush=True)
    kod0 = kod_otpechatok()
    while True:
        if kod_otpechatok() != kod0:
            print(f"!! {seychas():%H:%M} UTC код фабрики изменился после запуска — демон ОСТАНОВЛЕН, "
                  "чтобы не судить старой логикой. Перезапустить вручную.", flush=True)
            return
        r = odin_shag()
        if r == "STOP":
            return
        if r is None:
            if poly_sutki() is not None:
                continue                                   # пришли новые данные — сразу проверить очередь
            j = otchet_dnya()
            print(f"… {seychas():%H:%M} UTC прогонять нечего; жду {SON // 60} мин. {otchet_stroka()}"
                  f" | вмешательство: {'ДА' if j['trebuetsya_vmeshatelstvo'] else 'нет'}", flush=True)
            time.sleep(SON)


# ── отчёты ────────────────────────────────────────────────────────────
def otchet_stroka(chasov=24):
    gran = seychas() - dt.timedelta(hours=chasov)
    vv = [v for v in verdikty_vse() if dt.datetime.fromisoformat(v["kogda"]).replace(
        tzinfo=dt.timezone.utc) >= gran and v["verdikt"] not in ("PARITY_PASS", "BLOCKED_PARITY", "FAILED_TECHNICAL")]
    c = Counter(v["verdikt"] for v in vv)
    d = zagruzit()
    run = next((it["id"] for it in d["ochered"] if it["sostoyanie"] == "RUNNING"), None)
    blocked = sum(1 for it in d["ochered"] if it["sostoyanie"].startswith("BLOCKED") or it["sostoyanie"] == "LEAD_BLOCKED_DATA")
    conf = sum(1 for it in d["ochered"] if it.get("param", {}).get("etap") == "confirmation")
    return (f"{chasov}h: tested {len(vv)} | negative {c['NEGATIVE']} | plus_no_conf {c['PLUS_NO_CONFIDENCE']} | "
            f"low_n {c['INCONCLUSIVE_LOW_N']} | blocked {blocked} | positive leads {c['POSITIVE_LEAD']} | "
            f"confirmation {conf} (confirmed {c['CONFIRMED']}) | next running: {run or '—'}")


def pokazat_zadachi():
    if ZADACHI.exists():
        for z in json.loads(ZADACHI.read_text())["zadachi"]:
            print(f"  {z['tip']:<15}{z['id']:<34}{z['kto']:<10}{z['chto'][:70]}")


def doska():
    d = zagruzit(); V = verdikty()
    c = Counter(it["sostoyanie"] for it in d["ochered"])
    print("\nФАБРИКА —", seychas().strftime("%Y-%m-%d %H:%M UTC"))
    print("  " + "  ".join(f"{k}: {v}" for k, v in sorted(c.items())))
    print(" ", otchet_stroka()); print()
    for it in d["ochered"]:
        v = V.get(it["id"])
        print(f"  {it['id']:<34}{it['sostoyanie']:<20}{(v['pochemu'] if v else it.get('blocker', ''))[:80]}")


# ── самопроверка ──────────────────────────────────────────────────────
def samoproverka():
    S = {"porog_z": 2.39, "min_n": 50, "min_n_o3": 30}
    def ok(n, e, se=0.02): return {"n": n, "kontrol_sobran": True, "edge": e, "se": se, "z": e / se}
    def R(a, b, c=None): return {"okna": {"O1": a, "O2": b, **({"O3": c} if c is not None else {})}}
    sl = [("мало сделок", R(ok(40, .1), ok(300, .1), ok(100, .1)), "INCONCLUSIVE_LOW_N"),
          ("контроль не собран", R({"n": 60, "kontrol_sobran": False}, ok(300, .1), ok(100, .1)), "INCONCLUSIVE_LOW_N"),
          ("минус во втором окне", R(ok(900, .1), ok(300, -.01), ok(100, .1)), "NEGATIVE"),
          ("оба плюс, сильный, O3 плюс", R(ok(900, .06), ok(300, .06), ok(100, .01)), "POSITIVE_LEAD"),
          ("оба плюс, сильный, O3 минус", R(ok(900, .06), ok(300, .06), ok(100, -.01)), "PLUS_NO_CONFIDENCE"),
          ("оба плюс, сильный, O3 мало", R(ok(900, .06), ok(300, .06), ok(10, .05)), "PLUS_NO_CONFIDENCE"),
          ("оба плюс, слабый", R(ok(900, .01), ok(300, .01), ok(100, .05)), "PLUS_NO_CONFIDENCE"),
          ("ноль ровно", R(ok(900, 0.0), ok(300, .1), ok(100, .1)), "NEGATIVE"),
          ("золото: сильный, O3 нет", R(ok(900, .06), ok(300, .06)), "LEAD_BLOCKED_DATA"),
          ("золото: слабый, O3 нет", R(ok(900, .01), ok(300, .01)), "PLUS_NO_CONFIDENCE")]
    bad = 0
    for name, rez, want in sl:
        got = sudya(rez, S)[0]; bad += got != want
        print(f"  {'PASS' if got == want else 'FAIL'}  {name:<34}{got}")
    et = {"O1": {"n": 942, "edge": 0.0486}, "O2": {"n": 376, "edge": -0.0519}}
    for name, rez, want in [("паритет точно", R(ok(942, .0486), ok(376, -.0519)), "PARITY_PASS"),
                            ("паритет n другой", R(ok(941, .0486), ok(376, -.0519)), "BLOCKED_PARITY"),
                            ("паритет эдж уехал", R(ok(942, .0496), ok(376, -.0519)), "BLOCKED_PARITY")]:
        got = sudya_paritet(rez, et)[0]; bad += got != want
        print(f"  {'PASS' if got == want else 'FAIL'}  {name:<34}{got}")
    # лимит жвачки и порождение
    d = {"ochered": [dict(id=f"X{i}", tip="gipoteza", rynok="crypto137", semya="breakout",
                          sostoyanie="NEGATIVE", begun="meh") for i in range(3)]
         + [dict(id="Q", tip="gipoteza", rynok="crypto137", semya="breakout", sostoyanie="QUEUED", begun="meh")]}
    V = {f"X{i}": {"verdikt": "NEGATIVE"} for i in range(3)}
    sinhronizirovat(d, V)
    got = d["ochered"][-1]["sostoyanie"]; bad += got != "FAMILY_PAUSED"
    print(f"  {'PASS' if got == 'FAMILY_PAUSED' else 'FAIL'}  {'3 NEGATIVE → семейство на паузу':<34}{got}")
    nov = porodit(d, V, 50)
    b = any("PROBOY_55__crypto137" in x for x in nov); bad += b
    print(f"  {'PASS' if not b else 'FAIL'}  {'пауза: пробой крипты не порождается':<34}{len(nov)} новых")
    d2 = {"ochered": [dict(id="R", tip="gipoteza", sostoyanie="RUNNING", pid=999999, begun="meh")]}
    sinhronizirovat(d2, {}); got = d2["ochered"][0]["sostoyanie"]; bad += got != "QUEUED"
    print(f"  {'PASS' if got == 'QUEUED' else 'FAIL'}  {'мёртвый RUNNING → назад в очередь':<34}{got}")
    SP = {"porog_t": 2.5, "min_neff": 20, "min_pokrytie": 0.8}
    def P(e, t, h1, h2, neff=50, pk=0.95):
        return {"chlenov_s_cenoy_mediana": pk, "okna": {"VSE": {"n": 200, "n_eff": neff, "edge": e, "t": t},
                "H1": {"edge": h1}, "H2": {"edge": h2}}}
    for name, rez, want in [("портфель: нет цен у вселенной", P(.01, 3, .01, .01, pk=.35), "BLOCKED_DATA"),
                            ("портфель: мало периодов", P(.01, 3, .01, .01, neff=10), "INCONCLUSIVE_LOW_N"),
                            ("портфель: половина в минусе", P(.01, 3, .01, -.001), "NEGATIVE"),
                            ("портфель: сильный", P(.01, 3, .01, .01), "POSITIVE_LEAD"),
                            ("портфель: слабый", P(.01, 1.2, .01, .01), "PLUS_NO_CONFIDENCE")]:
        got = sudya_portfel(rez, SP)[0]; bad += got != want
        print(f"  {'PASS' if got == want else 'FAIL'}  {name:<34}{got}")
    SC = {"porog_t": 2.0, "min_neff": 10}
    def Q(e, t, n): return {"okna": {"VSE": {"n": 100, "n_eff": n, "edge": e, "t": t}}}
    for name, rez, want in [("подтв.: мало данных", Q(.01, 3, 5), "CONFIRMATION_WAITING_DATA"),
                            ("подтв.: минус", Q(-.01, -1, 30), "FAILED_CONFIRMATION"),
                            ("подтв.: плюс сильный", Q(.01, 2.5, 30), "CONFIRMED"),
                            ("подтв.: плюс слабый", Q(.01, 1.0, 30), "CONFIRMATION_INCONCLUSIVE")]:
        got = sudya_podtv(rez, SC)[0]; bad += got != want
        print(f"  {'PASS' if got == want else 'FAIL'}  {name:<34}{got}")
    d3 = {"ochered": [dict(id="L", tip="gipoteza", begun="portfel", rynok="akcii_pit", semya="x",
                           param={"signal": "AKC_MOM_6_1", "etap": "discovery"}, sostoyanie="POSITIVE_LEAD")]}
    cid = postavit_podtverzhdenie(d3, d3["ochered"][0])
    okc = cid == "L__PODTV" and d3["ochered"][-1]["param"]["etap"] == "confirmation" and postavit_podtverzhdenie(d3, d3["ochered"][0]) is None
    bad += not okc
    print(f"  {'PASS' if okc else 'FAIL'}  {'находка → подтверждение, один раз':<34}{cid}")
    rez_bez_okon = {"tip": "proverka_narezki", "sovpadayut": True, "planov": 7, "simvoly": {"SOLUSDT": {}}}
    it_b = {"id": "PB", "tip": "paritet", "begun": "bull"}
    try:
        v_, _ = sudit(it_b, rez_bez_okon)
        json.dumps({"okna": (rez_bez_okon or {}).get("okna"), "verdikt": v_})
        okb = v_ == "PARITY_PASS"
    except Exception:
        okb = False
    bad += not okb
    print(f"  {'PASS' if okb else 'FAIL'}  {'результат без okna → запись вердикта':<34}{'ok' if okb else 'ошибка'}")
    # ── потолок автоматизации и запрет двигать планку ─────────────────
    okp = POTOLOK == "READY_FOR_BUILD" and not any(
        x in KONEC for x in ("LIVE", "TINY_LIVE", "PRODUCTION", "BROKER_BOUND"))
    bad += not okp
    print(f"  {'PASS' if okp else 'FAIL'}  {'потолок фабрики — READY_FOR_BUILD':<34}{POTOLOK}")

    d4 = {"ochered": [dict(id="L2", tip="gipoteza", begun="portfel", rynok="akcii_pit", semya="x",
                           param={"signal": "AKC_MOM_6_1", "etap": "discovery"}, sostoyanie="POSITIVE_LEAD"),
                      dict(id="L2__PODTV", tip="gipoteza", begun="portfel", rynok="akcii_pit", semya="x",
                           param={"signal": "AKC_MOM_6_1", "etap": "confirmation"},
                           sostoyanie="FAILED_CONFIRMATION", roditel="L2")]}
    okr = postavit_podtverzhdenie(d4, d4["ochered"][0]) is None
    bad += not okr
    print(f"  {'PASS' if okr else 'FAIL'}  {'окно подтверждения не тратится дважды':<34}{'ok' if okr else 'ПОВТОР'}")

    okt = True
    try:
        dt_ = {"ochered": [dict(id="TQ", tip="gipoteza", begun="meh", rynok="crypto137", semya="proverka",
                               sostoyanie="BLOCKED_DATA", otpechatok_pri_postanovke="0:0")]}
        sinhronizirovat(dt_, {})
        okt = dt_["ochered"][0]["sostoyanie"] == "QUEUED"
    except Exception:
        okt = False
    okpr = True
    try:
        dp_ = {"ochered": [dict(id="TP", tip="gipoteza", begun="portfel", rynok="akcii_pit", semya="proverka",
                               sostoyanie="BLOCKED_DATA", otpechatok_pri_postanovke="0:0",
                               trebuet_priyomki=True)]}
        sinhronizirovat(dp_, {})
        okpr = dp_["ochered"][0]["sostoyanie"] == "BLOCKED_DATA" and dp_["ochered"][0].get("dannye_izmenilis")
    except Exception:
        okpr = False
    bad += not okpr
    print(f"  {'PASS' if okpr else 'FAIL'}  {'данные годны? ждёт приёмки, не прогона':<34}{'ok' if okpr else 'ВЗВЁЛСЯ САМ'}")
    bad += not okt
    print(f"  {'PASS' if okt else 'FAIL'}  {'данные пришли → пункт сам в очередь':<34}{'ok' if okt else 'не взвёлся'}")

    # ── дефект 30.09: три случая + ворота + старый код ────────────────
    global _PRIYOMKA_TEST
    _PRIYOMKA_TEST = {}
    try:
        def G(**kw):
            base = dict(tip="gipoteza", begun="meh", rynok="gold", semya="proverka", sostoyanie="BLOCKED_DATA")
            base.update(kw); return base
        # 1: отпечатка нет → запомнить, не взвестись, не провалиться дальше
        d5 = {"ochered": [G(id="T1", trebuet_priyomki=True)]}
        sinhronizirovat(d5, {})
        ok1 = d5["ochered"][0]["sostoyanie"] == "BLOCKED_DATA" and d5["ochered"][0].get("otpechatok_pri_postanovke")
        # 2: есть прежний вердикт со старым отпечатком → не взвестись
        d6 = {"ochered": [G(id="T2", trebuet_priyomki=True, otpechatok_pri_postanovke="0:0")]}
        sinhronizirovat(d6, {"T2": {"verdikt": "INCONCLUSIVE_LOW_N", "dannye": "0:0", "kogda": "2026-01-01"}})
        ok2 = d6["ochered"][0]["sostoyanie"] == "BLOCKED_DATA" and d6["ochered"][0].get("dannye_izmenilis")
        d6b = {"ochered": [G(id="T2b", rynok="fx7")]}          # без пометки, но рынок с приёмкой
        sinhronizirovat(d6b, {"T2b": {"verdikt": "INCONCLUSIVE_LOW_N", "dannye": "0:0", "kogda": "2026-01-01"}})
        ok2 = ok2 and d6b["ochered"][0]["sostoyanie"] == "BLOCKED_DATA"
        # 3: пункт с пометкой, оказавшийся в QUEUED, не выбирается и возвращается назад
        d7 = {"ochered": [G(id="T3", trebuet_priyomki=True, sostoyanie="QUEUED")]}
        ok3 = vybrat(d7, {}) is None
        sinhronizirovat(d7, {})
        ok3 = ok3 and d7["ochered"][0]["sostoyanie"] == "BLOCKED_DATA"
        # 4: после приёмки ИМЕННО текущего отпечатка ворота открываются
        _PRIYOMKA_TEST = {"gold": {"otpechatok": otpechatok_dannyh("gold")}}
        ok4 = mozhno_progonyat(G(id="T4", trebuet_priyomki=True))
        _PRIYOMKA_TEST = {"gold": {"otpechatok": "1:1"}}
        ok4 = ok4 and not mozhno_progonyat(G(id="T4", trebuet_priyomki=True))
    except Exception as e:
        print("  исключение:", e); ok1 = ok2 = ok3 = ok4 = False
    finally:
        _PRIYOMKA_TEST = None
    for ok_, name in [(ok1, "нет отпечатка → ждёт, не взводится"), (ok2, "есть прежний вердикт → не взводится"),
                      (ok3, "пометка в QUEUED → не бежит, назад"), (ok4, "приёмка: только текущий отпечаток")]:
        bad += not ok_
        print(f"  {'PASS' if ok_ else 'FAIL'}  {name:<34}{'ok' if ok_ else 'ДЫРА'}")
    nov_ = porodit({"ochered": []}, {}, 10**6)
    okg = not any("_glub__" in x for x in nov_)
    bad += not okg
    print(f"  {'PASS' if okg else 'FAIL'}  {'глубина: генератор не порождает':<34}{'ok' if okg else 'ВОСКРЕШАЕТ'}")
    k1 = kod_otpechatok(); okk = k1 == kod_otpechatok() and "NET_FAYLA" not in k1
    bad += not okk
    print(f"  {'PASS' if okk else 'FAIL'}  {'отпечаток кода для демона':<34}{'ok' if okk else 'нет'}")

    import py_compile
    for f in sorted(DIR.glob("*.py")):
        try:
            py_compile.compile(str(f), doraise=True); okc = True
        except py_compile.PyCompileError:
            okc = False
        bad += not okc
        if not okc:
            print(f"  FAIL  не компилируется: {f.name}")
    print(f"  {'PASS' if bad == 0 else '    '}  все прогонщики компилируются")
    print("ИТОГ:", "ВСЁ ПРОШЛО" if not bad else f"ПРОВАЛОВ {bad}")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for k in ("demon", "otchet", "doska", "samoproverka", "povtorit_tehnicheskie", "reestr", "otchet_dnya"):
        ap.add_argument(f"--{k}", action="store_true")
    ap.add_argument("--prinyat", metavar="RYNOK", help="человеческая приёмка текущих данных рынка")
    a = ap.parse_args()
    if a.prinyat:
        pr = prinyatye(); ot = otpechatok_dannyh(a.prinyat)
        pr[a.prinyat] = {"otpechatok": ot, "kogda": seychas().isoformat(timespec="seconds"),
                         "kto": "владелец, ручной запуск --prinyat"}
        PRIYOMKA.write_text(json.dumps(pr, ensure_ascii=False, indent=1))
        print(f"принят рынок {a.prinyat}, отпечаток {ot}. Пункты сами в очередь НЕ встают — "
              "ре-тест ставится отдельным предрегистрированным решением."); sys.exit(0)
    if a.samoproverka:
        sys.exit(1 if samoproverka() else 0)
    if a.otchet_dnya:
        print(json.dumps(otchet_dnya(), ensure_ascii=False, indent=1)); sys.exit(0)
    if a.reestr:
        print("изменено записей реестра:", obnovit_reestr()); sys.exit(0)
    if a.otchet:
        print(otchet_stroka()); pokazat_zadachi(); sys.exit(0)
    if a.doska:
        doska(); sys.exit(0)
    if a.povtorit_tehnicheskie:
        d = zagruzit()
        for it in d["ochered"]:
            if it["sostoyanie"] == "FAILED_TECHNICAL":
                it["sostoyanie"] = "QUEUED"; print("снова в очереди:", it["id"])
        sohranit(d)
    s_zamkom(demon if a.demon else odin_prohod)
