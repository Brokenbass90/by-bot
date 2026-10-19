#!/usr/bin/env python3
"""ai_formula_v1.py — ИИ-цикл Factory без ручного исследовательского кода (19.10.2026, PM «AUTONOMOUS ALPHA DISCOVERY» P0).

Недостающее звено между `ai_kontrakt_v1` (ИИ пишет механизм словами → NEW в реестре) и фермой (`ferma_v1` исполняет
только код шаблонов): ИИ задаёт признак не кодом, а ФОРМУЛОЙ из закрытого словаря уже проверенных причинных атомов
(`ferma_shablony._priznak`, всё — данные дня d−1, известные до входа) и пяти операций без чисел. Чисел (порогов,
окон, коэффициентов) в формуле нет вообще — значит, «подкрутить параметр» под историю нельзя; механика сделки,
издержки, судья, окно, бюджет и поправка на число попыток — замороженные из реестра и фермы.

Цикл (каждый шаг пишет след):
  1. proverit(pr)        — контракт ai_kontrakt_v1 + формула: атомы из словаря, операции из словаря, глубина ≤ 3,
                           ≤ 3 атома, атомы покрывают окно, нет дубля формулы в реестре, суточный бюджет ИИ-попыток.
  2. prereg(pr)          — текст предрегистрации из полей предложения + замороженные критерии; коммитится в git ДО прогона.
  3. zapustit(pr)        — семья AI_FORMULA_XS (создаётся один раз), гипотеза NEW → SCREEN, попытка на DEV-окне через
                           ferma_v1.zapustit (шаблон xs_nedelya_binance, издержки и t Ньюи–Уэста — судьи KITY), вердикт
                           реестра с порогом t, растущим с числом попыток окна. Результат — в реестр и журнал.
Дальше SCREEN PASS → TEST только на CONFIRM-окне (вперёд), это делают существующие правила реестра, не этот модуль.

    python3 research_lab/factory_v3/ai_formula_v1.py --proverit predl.json         # только проверка
    python3 research_lab/factory_v3/ai_formula_v1.py --prereg predl.json            # написать prereg (коммит — git)
    python3 research_lab/factory_v3/ai_formula_v1.py --zapustit predl.json          # только если prereg уже в git HEAD
    python3 research_lab/factory_v3/ai_formula_v1.py --prompt                       # промпт для Ollama / любого LLM
"""
from __future__ import annotations
import argparse, datetime as dt, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent; LAB = HERE.parent; ROOT = LAB.parent
for p in (str(HERE), str(LAB)):
    if p not in sys.path: sys.path.insert(0, p)
import ai_kontrakt_v1 as A

# атом → (с какой даты есть данные, источник каталога ai_kontrakt_v1.ISTOCHNIKI, смысл)
ATOMY = {
    "m3_perp":              ("2021-04-01", "binance_klines_d1", "доля тейкера-покупателя в объёме перпа Binance, день d−1"),
    "spot":                 ("2021-04-01", "binance_spot_taker", "доля тейкера-покупателя на споте Binance, день d−1"),
    "spot_minus_perp":      ("2021-04-01", "binance_spot_taker", "spot − m3_perp: спотовый (немаржинальный) спрос против плечевого"),
    "m3_vsplesk":           ("2021-05-15", "binance_klines_d1", "m3_perp дня d−1 минус её среднее за 28 предыдущих дней монеты"),
    "vyhodnye":             ("2021-04-01", "binance_klines_d1", "доходность монеты за выходные (закр. вс / закр. пт − 1)"),
    "glubina_imb1":         ("2023-01-04", "binance_metrics", "перекос стакана Binance в ±1 % (bid − ask)/(bid + ask), день d−1"),
    "glubina_imb2":         ("2023-01-04", "binance_metrics", "то же в ±2 %"),
    "glubina_imb5":         ("2023-01-04", "binance_metrics", "то же в ±5 %"),
    "cb_premiya":           ("2022-12-15", "binance_klines_d1", "премия Coinbase USD к перпу Binance d−1 минус её среднее за 28 дней"),
    "cb_premiya_shok":      ("2022-12-15", "binance_klines_d1", "суточный прирост премии Coinbase"),
    "up_premiya":           ("2022-12-15", "binance_klines_d1", "премия Upbit KRW к перпу Binance d−1 минус её среднее за 28 дней"),
    "dolya_obema_coinbase": ("2022-12-15", "binance_klines_d1", "доля Coinbase в объёме монеты d−1 минус её среднее за 28 дней"),
    "dolya_obema_upbit":    ("2022-12-15", "binance_klines_d1", "доля Upbit в объёме монеты d−1 минус её среднее за 28 дней"),
}
OPERACII = {"minus": 2, "plus": 2, "proizv": 2, "neg": 1, "abs": 1}
MAKS_GLUBINA, MAKS_ATOMOV = 3, 3
SDVIG_PONEDELNIK = 4          # сетка KITY начинается в четверг 2021-07-01; атом vyhodnye осмыслен только при входе в понедельник
SEMYA = "AI_FORMULA_XS"
SHABLON = "ferma_shablony:xs_nedelya_binance"
KRITERII = {"min_n": 30, "znak": "+"}            # t считается уже со знаком предложения: «+» = сторона, которую назвал ИИ
MAKS_POPYTOK_V_SUTKI = 3                         # бюджет ИИ-попыток (все окна) в сутки UTC
REZERV_OKNA = 5                                  # последние 5 попыток любого DEV-окна ИИ не тратит — они для человека
PREREG_PAPKA = LAB / "prereg" / "ai"
ZHURNAL = LAB / "data" / "factory_v3" / "ai_formula_zhurnal.jsonl"


# ---------------------------------------------------------------- формула
def atomy(f):
    if isinstance(f, str): return [f]
    return [a for x in f[1:] for a in atomy(x)]


def glubina(f):
    return 0 if isinstance(f, str) else 1 + max(glubina(x) for x in f[1:])


def kanon(f):
    """Канонический вид: перестановочные операции сортируют аргументы → «a−b» и «b−a» разные, «a+b» и «b+a» одно."""
    if isinstance(f, str): return f
    op, args = f[0], [kanon(x) for x in f[1:]]
    if op in ("plus", "proizv"): args = sorted(args)
    return f"{op}({','.join(args)})"


def proverit_formulu(f):
    err = []
    def rek(x):
        if isinstance(x, str):
            if x not in ATOMY: err.append(f"атом вне словаря: {x}")
            return
        if not (isinstance(x, list) and x and isinstance(x[0], str)): err.append(f"узел — [операция, аргументы…]: {x}"); return
        if x[0] not in OPERACII: err.append(f"операция вне словаря: {x[0]}"); return
        if len(x) - 1 != OPERACII[x[0]]: err.append(f"{x[0]}: нужно аргументов {OPERACII[x[0]]}")
        for y in x[1:]:
            if isinstance(y, (int, float)): err.append("числа в формуле запрещены (нет порогов и коэффициентов)")
            else: rek(y)
    rek(f)
    if not err:
        if glubina(f) > MAKS_GLUBINA: err.append(f"глубина формулы > {MAKS_GLUBINA}")
        if len(atomy(f)) > MAKS_ATOMOV: err.append(f"атомов > {MAKS_ATOMOV}")
        if isinstance(f, str): err.append("одиночный атом — это уже проверенный признак каталога, не новая гипотеза")
    return err


def funkciya(f, D, priznak):
    """Вычислитель формулы поверх замороженных атомов шаблона: (монета, день) → число или None."""
    if isinstance(f, str):
        return priznak(f, D)
    op = f[0]; args = [funkciya(x, D, priznak) for x in f[1:]]
    def g(s, vch):
        v = [a(s, vch) for a in args]
        if any(x is None for x in v): return None
        v = [float(x) for x in v]
        return {"minus": lambda: v[0] - v[1], "plus": lambda: v[0] + v[1], "proizv": lambda: v[0] * v[1],
                "neg": lambda: -v[0], "abs": lambda: abs(v[0])}[op]()
    return g


def vychislit(f, znacheniya):
    """Формула на готовых значениях атомов (v2: z-оценки атомов внутри недели)."""
    if isinstance(f, str): return znacheniya[f]
    v = [vychislit(x, znacheniya) for x in f[1:]]
    return {"minus": lambda: v[0] - v[1], "plus": lambda: v[0] + v[1], "proizv": lambda: v[0] * v[1],
            "neg": lambda: -v[0], "abs": lambda: abs(v[0])}[f[0]]()


# ---------------------------------------------------------------- предложение
def proverit(pr, S=None, segodnya_popytok=0, okno=None):
    err = A.proverit({k: v for k, v in pr.items() if k not in ("formula", "znak", "okno", "normirovka", "avtor")})
    if pr.get("normirovka", "xs_z") not in ("xs_z", "net"): err.append("normirovka ∈ xs_z (по умолчанию), net")
    if pr.get("semya") != SEMYA: err.append(f"semya = {SEMYA}")
    if not str(pr.get("id", "")).startswith("AI_"): err.append("id начинается с AI_")
    if pr.get("znak") not in (1, -1): err.append("znak ∈ {1, -1}: 1 — лонг верхнего дециля формулы, −1 — шорт верхнего")
    f = pr.get("formula")
    if f is None: err.append("нет формулы")
    else: err += proverit_formulu(f)
    if S is not None:
        o = S["okna"].get(okno or pr.get("okno"))
        if not o: err.append(f"нет окна {okno or pr.get('okno')}")
        else:
            if o["rol"] != "DEV": err.append("ИИ-скрининг — только DEV-окно")
            ostalos = int(o.get("byudzhet") or 0) - sum(1 for p in S["popytki"].values() if p["okno"] == o["id"])
            if ostalos <= REZERV_OKNA: err.append(f"на окне {o['id']} осталось {ostalos} попыток — резерв {REZERV_OKNA} не для ИИ")
            if f is not None and not proverit_formulu(f):
                pozdno = [a for a in atomy(f) if ATOMY[a][0] > o["nachalo"]]
                if pozdno: err.append(f"атомы без данных на начало окна {o['nachalo']}: {pozdno}")
        if pr.get("id") in S["gipotezy"]: err.append("такой id уже есть в реестре")
        if f is not None and not proverit_formulu(f):
            k = kanon(f)
            if k in proverennye_formuly() or any((g.get("otlichie") or "").endswith(k) for g in S["gipotezy"].values()):
                err.append(f"формула уже проверялась: {k}")
    if segodnya_popytok >= MAKS_POPYTOK_V_SUTKI: err.append(f"суточный бюджет ИИ-попыток исчерпан ({MAKS_POPYTOK_V_SUTKI})")
    return err


def spec(pr):
    return {"id": f"{pr['id']}__SCREEN", "gipoteza": pr["id"], "okno": pr["okno"], "eksperiment": SHABLON,
            "parametry": {"priznak": "formula", "formula": pr["formula"], "znak": int(pr["znak"]),
                          **({"normirovka": "xs_z"} if pr.get("normirovka", "xs_z") == "xs_z" else {}),
                          **({"sdvig_dney": SDVIG_PONEDELNIK} if "vyhodnye" in atomy(pr["formula"]) else {})}, "kriterii": KRITERII}


def prereg_put(pr):
    return PREREG_PAPKA / f"PREREG_{pr['id']}.md"


def prereg_tekst(pr, S):
    o = S["okna"][pr["okno"]]
    from reestr_v1 import trebuemyy_t, ALPHA
    k = sum(1 for p in S["popytki"].values() if p["okno"] == o["id"]) + 1
    t_req = trebuemyy_t(k, float(o.get("alpha") or ALPHA))
    return f"""# PREREG {pr['id']} — ИИ-гипотеза, скрининг формулы (автоматически из предложения, {dt.date.today()})

Автор предложения: {pr.get('avtor', 'неизвестно')}. Пишется и коммитится ДО прогона; спецификация замораживается sha в реестре.

## Механизм (слова ИИ, не проверены)
{pr['mehanizm']}

Почему не выбрано арбитражем: {pr['pochemu_ne_arbitrazhirovano']}
Время известности: {pr['vremya_izvestnosti']} · горизонт {pr['gorizont']} · вселенная {pr['vselennaya']}
Контроль: {pr['kontrol']} · Фальсификация: {pr['falsifikaciya']}

## Исполняемое определение (без чисел)
Формула: `{kanon(pr['formula'])}` · знак {pr['znak']:+d} (1 — лонг верхнего дециля, шорт нижнего; −1 — наоборот).
Неделя: {'вход закрытием понедельника (атом vyhodnye: d−1 = воскресенье)' if 'vyhodnye' in atomy(pr['formula']) else 'вход закрытием четверга (сетка KITY)'}.
Нормировка: {'атомы z-нормируются по монетам внутри каждой недели, затем формула (v2)' if pr.get('normirovka', 'xs_z') == 'xs_z' else 'сырые значения атомов (v1)'}.
Атомы: {', '.join(f'{a} — {ATOMY[a][2]}' for a in sorted(set(atomy(pr['formula']))))}.
Шаблон `{SHABLON}`: недельная кросс-секция PIT топ-50 по OI Binance, вход закрытием d, удержание 7 дней, децили,
издержки и фандинг — замороженный `kity_sudya.sdelka`, t Ньюи–Уэста лаг 1 (`discovery_paket1.itog`).

## Окно и критерии (заданы реестром, не ИИ)
Окно {o['id']} ({o['nachalo']} … {o['konec']}, DEV, α {o.get('alpha')}), это попытка № {k} на окне →
требуемый |t| ≥ {t_req:.2f} (Φ⁻¹(1 − α / 2k)), n ≥ {KRITERII['min_n']} недель, знак «+» относительно указанной стороны.
PASS → гипотеза может перейти в TEST только на CONFIRM-окне вперёд (одна попытка). FAIL → формула не повторяется.
Деньги, риск, LIVE — вне этого цикла.
"""


def prereg_v_gite(put):
    """Ветка исследований — research/fabrika-v1 (рабочее дерево может стоять на другой ветке Codex)."""
    rel = Path(put).resolve().relative_to(ROOT)
    return any(subprocess.run(["git", "cat-file", "-e", f"{ref}:{rel}"], cwd=ROOT, capture_output=True).returncode == 0
               for ref in ("research/fabrika-v1", "HEAD"))


def proverennye_formuly():
    if not ZHURNAL.exists(): return set()
    return {json.loads(s)["formula"] for s in ZHURNAL.read_text().splitlines() if s.strip() and json.loads(s).get("shag") == "zapusk"}


def popytok_segodnya():
    if not ZHURNAL.exists(): return 0
    d = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return sum(1 for s in ZHURNAL.read_text().splitlines() if s.strip() and json.loads(s).get("kogda", "")[:10] == d
               and json.loads(s).get("shag") == "zapusk")


def _zhurnal(z):
    ZHURNAL.parent.mkdir(parents=True, exist_ok=True)
    with ZHURNAL.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")


def zapustit(pr, reestr=None, processov=1):
    from reestr_v1 import Reestr
    import ferma_v1
    r = reestr or Reestr(); S = r.sostoyanie()
    err = proverit(pr, S, popytok_segodnya())
    if err: raise ValueError("; ".join(err))
    put = prereg_put(pr)
    if not put.exists() or not prereg_v_gite(put): raise ValueError(f"prereg {put.name} не закоммичен в git — прогон запрещён")
    if SEMYA not in S["semi"]:
        r.semya(SEMYA, "ИИ-формулы из закрытого словаря причинных атомов, недельная кросс-секция (ai_formula_v1)", istochnik="ai_formula_v1")
    r.gipoteza(pr["id"], SEMYA, pr["mehanizm"], pr["istochniki_dannyh"], avtor=pr.get("avtor", "ai"),
               otlichie=f"формула {kanon(pr['formula'])}")
    r.perehod(pr["id"], "SCREEN", f"ИИ-цикл ai_formula_v1, prereg {put.relative_to(ROOT)}")
    itog = ferma_v1.zapustit([spec(pr)], reestr=r, processov=processov)
    if itog and itog[0].get("status") in ("FAIL", "OSHIBKA_EKSPERIMENTA"):
        r.perehod(pr["id"], "KILL", f"SCREEN {itog[0]['status']} (t {itog[0].get('t')}, требуемый {itog[0].get('trebuemyy_t')}); формула не повторяется")
    z = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), shag="zapusk", id=pr["id"],
             formula=kanon(pr["formula"]), znak=pr["znak"], avtor=pr.get("avtor"), okno=pr["okno"], itog=itog)
    _zhurnal(z)
    return itog


PROMPT_FORMULA = A.PROMPT_SISTEMA + """
Дополнительно верни поля "formula" и "znak" и "okno". formula — JSON-дерево БЕЗ ЧИСЕЛ: атом — строка из словаря
""" + json.dumps({k: v[2] for k, v in ATOMY.items()}, ensure_ascii=False) + """; узел — ["minus"|"plus"|"proizv", a, b] или ["neg"|"abs", a];
глубина ≤ 3, атомов ≤ 3; одиночный атом не принимается. znak: 1 — покупать монеты с наибольшим значением формулы и продавать
с наименьшим, −1 — наоборот. semya = "AI_FORMULA_XS", id начинается с "AI_". okno — DEV-окно реестра, на начало которого у всех атомов есть данные.
СЕЙЧАС бюджет есть только у окна "KRIPTO_D1_2021H2_2022" (начало 2021-07-01): для него допустимы ТОЛЬКО атомы
m3_perp, spot, spot_minus_perp, m3_vsplesk, vyhodnye. Других атомов, операций, источников и окон не существует.
Верни РОВНО такую форму (значения — свои, поля и типы — как здесь; числа только в ozhidaemaya_chastota_v_mesyac и izderzhki_ocenka_bps):
{"id": "AI_КОРОТКОЕ_ИМЯ", "semya": "AI_FORMULA_XS", "mehanizm": "2–4 предложения (не короче 60 знаков): кто вынужден торговать и почему цена отклоняется",
 "pochemu_ne_arbitrazhirovano": "почему этим не пользуются крупные игроки", "istochniki_dannyh": ["binance_klines_d1"],
 "priznak": "словами, что измеряет формула", "vremya_izvestnosti": "закрытие дня d-1, вход закрытием дня d",
 "napravlenie": "+", "gorizont": "1w", "vselennaya": "PIT топ-50 по OI Binance",
 "kontrol": "одиночные атомы формулы и случайная перестановка", "falsifikaciya": "спред со знаком гипотезы ≤ 0 или |t| ниже порога окна",
 "ozhidaemaya_chastota_v_mesyac": 4, "izderzhki_ocenka_bps": 30,
 "formula": ["minus", "АТОМ_1", "АТОМ_2"], "znak": 1, "normirovka": "xs_z", "okno": "KRIPTO_D1_2021H2_2022"}
istochniki_dannyh — из: "binance_klines_d1", "binance_spot_taker" (по атомам формулы)."""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--proverit"); ap.add_argument("--prereg"); ap.add_argument("--zapustit")
    ap.add_argument("--prompt", action="store_true"); a = ap.parse_args()
    from reestr_v1 import Reestr
    if a.prompt: print(PROMPT_FORMULA); sys.exit(0)
    put = a.proverit or a.prereg or a.zapustit; pr = json.loads(Path(put).read_text()); S = Reestr().sostoyanie()
    if a.proverit:
        e = proverit(pr, S, popytok_segodnya()); print(json.dumps({"oshibki": e, "kanon": kanon(pr.get("formula", "")) if pr.get("formula") else None}, ensure_ascii=False)); sys.exit(1 if e else 0)
    if a.prereg:
        e = proverit(pr, S, popytok_segodnya())
        if e: print(json.dumps({"oshibki": e}, ensure_ascii=False)); sys.exit(1)
        PREREG_PAPKA.mkdir(parents=True, exist_ok=True); p = prereg_put(pr); p.write_text(prereg_tekst(pr, S))
        _zhurnal(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), shag="prereg", id=pr["id"], put=str(p.relative_to(ROOT))))
        print(p.relative_to(ROOT)); sys.exit(0)
    print(json.dumps(zapustit(pr), ensure_ascii=False, indent=1))
