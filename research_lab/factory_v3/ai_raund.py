#!/usr/bin/env python3
"""ai_raund.py V2 — ОГРАНИЧЕННЫЙ раунд ИИ-исследователя (Ollama). 13.10.2026, после зависания Мака на V1.

Причины зависания V1 (дефекты кода): нет лимита вывода (qwen3 «думает» вслух), нет лимита контекста, таймаут 300 с × 3 вызова,
выбор «первой qwen*/deepseek*» без ограничения размера, нет проверки уже загруженных моделей, модель оставалась в памяти,
нет проверки свободной RAM. V2 закрывает каждый пункт:

  • разрешённые модели — только список MODELI (≤ 8B), размер по /api/tags ≤ MAX_GB;
  • /api/ps должен быть ПУСТ (никакой второй модели/агента в памяти) — иначе отказ;
  • свободная память macOS (vm_stat: free+inactive+speculative) ≥ размер модели + запас — иначе отказ;
    запас = max(1.5 ГБ, ½ размера модели) (19.10: фиксированные 4 ГБ не пускали даже 4B-модель на рабочем Маке
    с открытыми браузером и IDE; лимиты вывода/контекста/выгрузки V2 остаются — они и закрыли зависание 13.10);
  • один раунд одновременно (flock data/locks/ai_raund.lock), никаких фоновых циклов, n ≤ 3 (по умолчанию 1);
  • вызов: num_ctx 2048, num_predict 512, num_thread 4, think=false, keep_alive=0 (выгрузка сразу), таймаут 120 с;
  • общий дедлайн процесса 300 с (SIGALRM); по таймауту — принудительная выгрузка модели и выход с кодом 3;
  • сухой режим (по умолчанию) НИЧЕГО не пишет в проект: реестр — копия во временной папке, итог — только на экран;
    с --zapisat — NEW в реестр и журнал data/factory_v3/ai_raundy.jsonl.

    .venv/bin/python research_lab/factory_v3/ai_raund.py --proverka     # только проверки ресурсов, модель НЕ грузится
    .venv/bin/python research_lab/factory_v3/ai_raund.py                # 1 предложение, сухо
"""
import argparse, datetime as dt, fcntl, json, os, re, shutil, signal, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from reestr_v1 import Reestr, PUT_PO_UMOLCHANIYU
import ai_kontrakt_v1 as A

MODELI = ("qwen3:4b", "qwen3:8b", "qwen2.5:7b", "deepseek-r1:7b", "deepseek-r1:8b")
MAX_GB, ZAPAS_MIN_GB, N_MAX, TIMEOUT_S, DEDLAYN_S = 6.0, 1.5, 3, 300, 600
LOCKS = HERE.parent / "data" / "locks"


class Otkaz(Exception):
    pass


def _get(host, put, timeout=10):
    with urllib.request.urlopen(f"{host}{put}", timeout=timeout) as r: return json.loads(r.read())


def svobodno_gb():
    """macOS: (free + inactive + speculative) страниц × размер страницы. На не-macOS — None (проверка не пройдена)."""
    try: out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
    except Exception: return None
    ps = int(re.search(r"page size of (\d+)", out).group(1))
    v = lambda k: int(re.search(rf"{k}:\s+(\d+)", out).group(1)) if re.search(rf"{k}:\s+(\d+)", out) else 0
    return (v("Pages free") + v("Pages inactive") + v("Pages speculative")) * ps / 2**30


def nagruzka():
    """macOS: давление памяти (sysctl kern.memorystatus_vm_pressure_level: 1 норма, 2 предупреждение, 4 критично),
    swap (vm.swapusage), загрузка CPU (loadavg за 1 мин / число ядер). Не измерено → davlenie None (fail-closed)."""
    def sc(k):
        try: return subprocess.run(["sysctl", "-n", k], capture_output=True, text=True, timeout=5).stdout.strip()
        except Exception: return ""
    d = sc("kern.memorystatus_vm_pressure_level"); sw = sc("vm.swapusage")
    mb = lambda key: float(re.search(rf"{key} = ([\d.]+)M", sw).group(1)) if re.search(rf"{key} = ([\d.]+)M", sw) else None
    try: l1 = os.getloadavg()[0]
    except Exception: l1 = None
    return dict(davlenie=int(d) if d.isdigit() else None, swap_used_mb=mb("used"), swap_total_mb=mb("total"),
                load1=round(l1, 2) if l1 is not None else None, yader=os.cpu_count())


MAKS_ZAGRUZKA_CPU = 0.75     # loadavg/ядра выше — Мак занят работой владельца, ИИ пропускает раунд


def vygruzit(host, model):
    try:
        body = json.dumps(dict(model=model, prompt="", keep_alive=0)).encode()
        urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception:
        pass


def proverki(host, model, pamyat_fn=svobodno_gb, nagruzka_fn=nagruzka):
    """Возвращает dict ресурсов или бросает Otkaz. Модель не загружает."""
    if model not in MODELI: raise Otkaz(f"модель {model} не в списке разрешённых {MODELI}")
    tags = {m["name"]: m for m in _get(host, "/api/tags").get("models", [])}
    if model not in tags: raise Otkaz(f"модели {model} нет в Ollama (есть: {sorted(tags)[:8]})")
    gb = tags[model].get("size", 0) / 2**30
    if gb > MAX_GB: raise Otkaz(f"{model} весит {gb:.1f} ГБ > {MAX_GB}")
    zagr = [m.get("name") for m in _get(host, "/api/ps").get("models", [])]
    if zagr: raise Otkaz(f"в памяти уже есть модели {zagr} — второй инференс запрещён")
    sv = pamyat_fn()
    if sv is None: raise Otkaz("не удалось измерить свободную память — отказ (fail-closed)")
    zapas = max(ZAPAS_MIN_GB, 0.5 * gb)
    if sv < gb + zapas: raise Otkaz(f"свободно {sv:.1f} ГБ < модель {gb:.1f} + запас {zapas:.1f} ГБ")
    n = nagruzka_fn()
    if n.get("davlenie") is None: raise Otkaz("не удалось измерить давление памяти macOS — отказ (fail-closed)")
    if n["davlenie"] > 1: raise Otkaz(f"давление памяти macOS = {n['davlenie']} (не норма) — Мак занят, раунд пропущен")
    if n.get("load1") is not None and n.get("yader") and n["load1"] / n["yader"] > MAKS_ZAGRUZKA_CPU:
        raise Otkaz(f"CPU занят: loadavg {n['load1']} на {n['yader']} ядер > {MAKS_ZAGRUZKA_CPU:.0%} — раунд пропущен")
    return dict(model=model, model_gb=round(gb, 2), svobodno_gb=round(sv, 1), **n)


def zamok():
    LOCKS.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCKS / "ai_raund.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise Otkaz("раунд ИИ уже идёт (замок занят)")
    return fd


def raund_formula(a, r, klient=None):
    """Формула для ai_formula_v1 в режиме МЕНЮ (19.10: модель 4B копировала шаблон и выдумывала атомы): модель выбирает
    номер ещё не проверенной формулы из списка, знак и пишет механизм; служебные поля фиксированы. Проверка — по
    НАСТОЯЩЕМУ реестру, прогон делает хук сторожа ai_formula_cikl (prereg-коммит до прогона). Пороги модель не трогает."""
    import ai_formula_v1 as F
    S = Reestr().sostoyanie(); men = F.menyu(S)
    if not men:
        return [dict(status="MENYU_PUSTO", detal="все формулы окна проверены")]
    kl = klient or A.klient_ollama(a.model, a.host, opcii=dict(num_predict=600, num_thread=2), timeout_s=TIMEOUT_S)  # 2 потока: медленнее, Мак не душит
    out = []
    for _ in range(a.n):
        try: otv = kl(F.prompt_menyu(men), a.zapros)
        except Exception as e:
            out.append(dict(status="OSHIBKA_MODELI", detal=str(e)[:200])); continue
        obj = F.iz_otveta_menyu(otv, men)
        if obj is None:
            out.append(dict(status="OTKLONENO", oshibki=[f"номер вне списка 1..{len(men)}: {otv.get('nomer')}"])); continue
        obj["avtor"] = f"ai:{getattr(kl, 'model', 'neizvestno')} (выбор из меню {len(men)} формул)"
        err = F.proverit(obj, S, F.popytok_segodnya())
        if err:
            out.append(dict(status="OTKLONENO", id=obj.get("id"), oshibki=err)); continue
        if a.zapisat:
            put = HERE.parent / "data" / "factory_v3" / "ai_predlozheniya" / f"{obj['id']}.json"
            put.parent.mkdir(parents=True, exist_ok=True); put.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
            out.append(dict(status="V_OCHEREDI_HUKA", id=obj["id"], formula=F.kanon(obj["formula"]), znak=obj["znak"]))
        else:
            out.append(dict(status="PROSHLO_PROVERKU_SUHO", id=obj["id"], formula=F.kanon(obj["formula"]), znak=obj["znak"]))
    return out


def main(argv=None, pamyat_fn=svobodno_gb, nagruzka_fn=nagruzka):
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=1); ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--host", default="http://localhost:11434"); ap.add_argument("--zapisat", action="store_true")
    ap.add_argument("--proverka", action="store_true")
    ap.add_argument("--formula", action="store_true", help="19.10: предложение-формула для ai_formula_v1 → data/factory_v3/ai_predlozheniya/")
    ap.add_argument("--zapros", default="Предложи механизм, независимый от уже убитых, на данных из каталога.")
    a = ap.parse_args(argv)
    if not 1 <= a.n <= N_MAX: print(f"n ∈ [1, {N_MAX}]"); return 2
    try:
        fd = zamok(); res = proverki(a.host, a.model, pamyat_fn, nagruzka_fn); t0 = time.time()
    except Otkaz as e:
        print("ОТКАЗ:", e); return 2
    except Exception as e:
        print("ОТКАЗ: Ollama недоступна:", e); return 2
    print("ресурсы:", res)
    if a.proverka: return 0
    def dedlayn(*_):
        vygruzit(a.host, a.model); print(f"ABORTED: общий дедлайн {DEDLAYN_S} с, модель выгружена"); os._exit(3)
    signal.signal(signal.SIGALRM, dedlayn); signal.alarm(DEDLAYN_S)
    try: os.nice(10)
    except Exception: pass
    if a.zapisat: r = Reestr()
    else:
        tmp = Path(tempfile.mkdtemp()) / "reestr_kopiya.jsonl"
        if PUT_PO_UMOLCHANIYU.exists(): shutil.copy(PUT_PO_UMOLCHANIYU, tmp)
        r = Reestr(tmp)
    try:
        if a.formula:
            rez = raund_formula(a, r)
        else:
            rez = A.raund(r, A.klient_ollama(a.model, a.host, timeout_s=TIMEOUT_S), a.zapros, a.n)
    finally:
        signal.alarm(0); vygruzit(a.host, a.model)
    if a.zapisat:
        log = HERE.parent / "data" / "factory_v3" / "ai_raundy.jsonl"
        with open(log, "a") as f:
            posle = dict(svobodno_gb=(lambda v: round(v, 1) if v is not None else None)(pamyat_fn()), **nagruzka_fn())
            f.write(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), resursy=res,
                                    resursy_posle=posle, sekund=round(time.time() - t0, 1), itogi=rez), ensure_ascii=False) + "\n")
    print(f"модель {a.model}, {'ЗАПИСЬ в реестр' if a.zapisat else 'сухой прогон (в проект ничего не записано)'}")
    for x in rez: print(" ", json.dumps(x, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
