#!/usr/bin/env python3
"""generator_v0.py — Discovery Generator v0 (разрешён менеджером 01.10 после вердикта ATTENTION_SHORT).

Принцип (Карпати, autoresearch): один изменяемый объект — кандидат-механизм; фиксированный бюджет; одна метрика.
Модель (Ollama на Mac или Claude) порождает МЕХАНИЗМЫ на ограниченном языке, а не код и не параметры:
  {"semya": "...", "kto_platit": "...", "pochemu": "...",
   "tip": "xs" | "sobytie",
   "xs":      {"priznak": "<имя>", "znak": +1|-1, "hold": 5|10|20}           высокий признак → +1 лучше рынка / −1 хуже
   "sobytie": {"usloviya": [["<имя>", ">"|"<", число], ...], "storona": +1|-1, "hold": 5|10|20}}
Данные v0 — только акции США без смещения выживших, ТОЛЬКО окно поиска (< 2026-04-01; данные позже физически
обрезаются до расчёта признаков). Метрика — discovery_paket1.itog, кластер — дата.
Ограничители: ≤ 10 кандидатов за сессию; семейства с кладбища и уже проверенные — отказ без прогона;
порог выживания t ≥ 2.0 + поправка на число проверок за сессию (Бонферрони: t ≥ z(1 − 0.025/N)).
Выживший получает только черновик предрегистрации; дальше — человек/Claude и обычная фабрика. Никаких денег.

    python3 generator_v0.py --ollama [--model имя] кандидаты от локальной модели (Mac, 127.0.0.1:11434)
    python3 generator_v0.py --fayl kand.json    кандидаты из файла (например, от Claude)
"""
import json, math, sys, urllib.request
from pathlib import Path
from statistics import NormalDist
import numpy as np

GEN = Path(__file__).resolve().parent; LAB = GEN.parent
sys.path.insert(0, str(LAB))
import discovery_paket1 as P          # noqa: E402
import discovery_paket5 as A          # noqa: E402

GRAN = "2026-04-01"; MAX_KAND = 10
MAX_SESSIY = 3          # менеджер 01.10: на этих свечах акций — сессия 1 + ещё максимум 2, потом датасет исчерпан
KLADBISCHE = GEN / "kladbische.json"; ZHURNAL = GEN / "zhurnal.jsonl"
PRIZNAKI = {
    "r5": "доходность 5 дней", "r20": "доходность 20 дней", "r60": "доходность 60 дней",
    "gap": "гэп открытия к вчерашнему закрытию", "obem_x": "оборот дня / медиана 20 дней",
    "do_max250": "закрытие / максимум 250 дней − 1", "max_r20": "максимальная дневная доходность за 20 дней",
    "vol20": "стандартное отклонение дневных доходностей 20 дней", "cena": "цена закрытия",
    "oborot20": "медианный оборот 20 дней, $", "noch20": "средняя ночная доходность 20 дней",
    "den20": "средняя дневная (открытие→закрытие) доходность 20 дней"}


def dannye():
    dates, px, cs = A.zagruzit()
    k = sum(1 for d in dates if d < GRAN)
    dates = dates[:k]
    px = {t: {i: v for i, v in d.items() if i < k} for t, d in px.items()}   # окно после GRAN физически отрезано
    px = {t: d for t, d in px.items() if d}
    tick, O, C, U = A.matricy(dates, px)
    with np.errstate(all="ignore"):
        r1 = C[1:] / C[:-1] - 1; r1 = np.vstack([np.full(C.shape[1], np.nan), r1])
        noch = O[1:] / C[:-1] - 1; noch = np.vstack([np.full(C.shape[1], np.nan), noch]); den = C / O - 1
    return dates, O, C, U, r1, noch, den


def priznak(name, i, O, C, U, r1, noch, den):
    with np.errstate(all="ignore"):
        if name in ("r5", "r20", "r60"):
            n = int(name[1:]); return C[i] / C[i - n] - 1 if i >= n else None
        if name == "gap":
            return O[i] / C[i - 1] - 1
        if name == "obem_x":
            return U[i] / np.nanmedian(U[i - 20:i], axis=0)
        if name == "do_max250":
            return C[i] / np.nanmax(C[i - 249:i + 1], axis=0) - 1 if i >= 250 else None
        if name == "max_r20":
            return np.nanmax(r1[i - 19:i + 1], axis=0)
        if name == "vol20":
            return np.nanstd(r1[i - 19:i + 1], axis=0)
        if name == "cena":
            return C[i]
        if name == "oborot20":
            return np.nanmedian(U[i - 19:i + 1], axis=0)
        if name == "noch20":
            return np.nanmean(noch[i - 19:i + 1], axis=0)
        if name == "den20":
            return np.nanmean(den[i - 19:i + 1], axis=0)
    return None


def proverit(k, D):
    dates, O, C, U, r1, noch, den = D
    sob = []
    if k["tip"] == "xs":
        x = k["xs"]; h = int(x["hold"])
        for i0 in range(60, len(dates) - h, 5):          # ребаланс раз в 5 дней, перекрытие учтено НВ
            un = A.vselennaya(C, U, i0); f = priznak(x["priznak"], i0, O, C, U, r1, noch, den)
            if f is None:
                continue
            js = np.flatnonzero(un & np.isfinite(f))
            if len(js) < 200:
                continue
            o = np.argsort(f[js]); q = len(js) // 10
            hi, lo = js[o[-q:]], js[o[:q]]
            lng, sht = (hi, lo) if x["znak"] > 0 else (lo, hi)
            a = [A.vyhod(C, j, i0, h, 1) for j in lng]; b = [A.vyhod(C, j, i0, h, -1) for j in sht]
            a = [z for z in a if z is not None]; b = [z for z in b if z is not None]
            if a and b:
                sob.append((i0 * P.DEN, (np.mean(a) + np.mean(b)) / 2 - A.KOM, None))
    else:
        s = k["sobytie"]; h = int(s["hold"]); st = int(s["storona"])
        for i0 in range(60, len(dates) - h):
            un = A.vselennaya(C, U, i0 - 1); mask = un.copy()
            for name, op, val in s["usloviya"]:
                f = priznak(name, i0, O, C, U, r1, noch, den)
                if f is None:
                    mask[:] = False; break
                with np.errstate(all="ignore"):
                    mask &= (f > val) if op == ">" else (f < val)
            js = np.flatnonzero(mask)
            if not len(js):
                continue
            m = A.rynok(C, un, i0, h)
            r = [A.vyhod(C, j, i0, h, st) for j in js]
            r = [z - st * m - A.KOM for z in r if z is not None and m is not None]
            if r:
                sob.append((i0 * P.DEN, float(np.mean(r)), None))
    lag = (int(k["xs"]["hold"]) // 5) if k["tip"] == "xs" else int(k["sobytie"]["hold"])
    return P.itog(sob, s_kontrolem=False, lag=lag)      # t Ньюи–Уэста: удержания перекрываются


def podpis(k):
    """сигнатура механизма без параметров и без знака: другой порог/срок или разворот проверенного механизма —
    тот же тест (разворот = производная, только через prereg на новых данных, правило менеджера)"""
    try:
        if k["tip"] == "xs":
            return ("xs", k["xs"]["priznak"])
        s = k["sobytie"]
        return ("sob", tuple(sorted((n, op) for n, op, _ in s["usloviya"])))
    except Exception:
        return None


def zhurnal():
    return [json.loads(l) for l in ZHURNAL.open() if l.strip()] if ZHURNAL.exists() else []


def kladbische():
    return json.load(open(KLADBISCHE)) if KLADBISCHE.exists() else []


def prompt():
    kl = "\n".join(f"- {x['semya']}: {x['prichina']}" for x in kladbische())
    pr = "\n".join(f"- {k}: {v}" for k, v in PRIZNAKI.items())
    pod = sorted({str(podpis(z["kandidat"])) for z in zhurnal()} - {"None"})
    kl += "\nУже проверенные сочетания (любой порог, срок и знак = отказ без прогона):\n" + "\n".join(pod)
    return (f"Ты исследователь рынка акций США. Предложи до {MAX_KAND} РАЗНЫХ экономических механизмов, "
            "где кто-то систематически оставляет деньги на столе. Не параметры — механизмы.\n"
            f"Доступные признаки (на дату, только прошлое):\n{pr}\n"
            f"Уже убитые семейства — НЕ предлагать ни их, ни их варианты:\n{kl}\n"
            'Ответ — ТОЛЬКО JSON вида {"kandidaty": [ ... ]}, внутри объекты вида '
            
            '{"semya":"...","kto_platit":"...","pochemu":"...","tip":"xs","xs":{"priznak":"r20","znak":-1,"hold":10}} '
            'или {"semya":"...","kto_platit":"...","pochemu":"...","tip":"sobytie","sobytie":{"usloviya":[["obem_x",">",3]],"storona":-1,"hold":10}}. '
            "hold только 5, 10 или 20.")


def ot_ollama():
    tags = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10).read())
    imena = [m["name"] for m in tags.get("models", [])]
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
    elif imena:
        # текстовые модели раньше визуальных (llava/qwen2.5vl плохо держат JSON), внутри — самая крупная
        model = max(tags["models"], key=lambda m: ("vision" not in (m.get("capabilities") or []),
                                                    m.get("size", 0)))["name"]
    else:
        sys.exit("в Ollama нет моделей: ollama pull qwen2.5:14b")
    print(f"Ollama: модели {imena}, берём {model}")
    body = json.dumps({"model": model, "prompt": prompt(), "stream": False, "format": "json", "think": False,
                       "options": {"temperature": 0.7, "num_ctx": 8192}}).encode()
    print("жду ответ модели (обычно 1–5 мин)…", flush=True)
    r = json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate", body,
                                                                {"Content-Type": "application/json"}), timeout=600).read())
    out = json.loads(r["response"])
    return out if isinstance(out, list) else out.get("kandidaty") or out.get("candidates") or [out], model


def valid(k):
    try:
        if k["tip"] == "xs":
            x = k["xs"]; return x["priznak"] in PRIZNAKI and x["znak"] in (1, -1) and int(x["hold"]) in (5, 10, 20)
        s = k["sobytie"]
        return (int(s["hold"]) in (5, 10, 20) and s["storona"] in (1, -1) and 1 <= len(s["usloviya"]) <= 3
                and all(n in PRIZNAKI and op in (">", "<") and isinstance(v, (int, float)) for n, op, v in s["usloviya"]))
    except Exception:
        return False


def main():
    if "--ollama" in sys.argv:
        kand, istochnik = ot_ollama()
    else:
        kand = json.load(open(sys.argv[sys.argv.index("--fayl") + 1])); istochnik = "fayl"
    kand = kand[:MAX_KAND]
    zh = zhurnal()
    sessii = {z.get("sessiya", 1) for z in zh}
    sessiya = max(sessii, default=0) + 1
    if sessiya > MAX_SESSIY:
        sys.exit(f"лимит сессий на этом датасете ({MAX_SESSIY}) исчерпан — нужны новые данные, не новые идеи")
    mertvye = {x["semya"].lower() for x in kladbische()} | {z["kandidat"].get("semya", "").lower() for z in zh}
    podpisi = {podpis(z["kandidat"]) for z in zh} - {None}
    D = dannye(); N = len(kand); porog = max(2.0, NormalDist().inv_cdf(1 - 0.025 / max(N, 1)))
    print(f"сессия {sessiya}/{MAX_SESSIY}, кандидатов {N}, источник {istochnik}, порог t ≥ {porog:.2f}, данные до {D[0][-1]}")
    for k in kand:
        if not valid(k) or not k.get("kto_platit"):
            itog = {"verdikt": "ОТКАЗ", "prichina": "не по шаблону или без «кто платит»"}
        elif k["semya"].lower() in mertvye:
            itog = {"verdikt": "ОТКАЗ", "prichina": "семейство на кладбище"}
        elif podpis(k) in podpisi:
            itog = {"verdikt": "ОТКАЗ", "prichina": "вариант/разворот уже проверенного механизма"}
        else:
            podpisi.add(podpis(k))
            itog = proverit(k, D)
            if itog.get("verdikt") == "SURVIVED" and itog.get("t", 0) < porog:
                itog["verdikt"] = "KILLED"; itog["prichina"] = f"t {itog['t']} < {porog:.2f} (поправка на {N} проверок)"
        zap = {"kandidat": k, "istochnik": istochnik, "sessiya": sessiya, "itog": itog}
        with ZHURNAL.open("a") as f:
            f.write(json.dumps(zap, ensure_ascii=False) + "\n")
        print(f"{k.get('semya','?'):28s} {itog['verdikt']:9s} {itog.get('edge_bps','')} t={itog.get('t','')} {itog.get('prichina','')}")


if __name__ == "__main__":
    main()
