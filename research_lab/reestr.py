#!/usr/bin/env python3
"""reestr.py — РЕЕСТР ГИПОТЕЗ. Память положительного, которой у нас не было.

ЗАЧЕМ
=====
Мы девять месяцев убивали гипотезы и ни разу не вели список выживших.
Из-за этого одно и то же убивалось по второму разу, а найденный плюс
терялся, стоило смениться чату. Этот файл — единственное место, где
живут все нити сразу, и он никогда ничего не удаляет.

ПЯТЬ СОСТОЯНИЙ, и переход только в одну сторону
===============================================
    NEGATIVE       умерло по объявленному правилу. Хранится вечно,
                   чтобы не убивать второй раз.
    POSITIVE_LEAD  наблюдался плюс, но доказательства не хватает.
    CANDIDATE      заморожен контракт и объявлен критерий PASS/FAIL.
    SHADOW         идёт вперёд и сам набирает наблюдения.
    CANARY         минимальные деньги. Только по отдельному решению
                   владельца, машина сюда не переводит никогда.

Обратного хода нет: гипотеза, упавшая из SHADOW, становится NEGATIVE со
своей причиной, а не возвращается в POSITIVE_LEAD. Иначе это карусель.

КАК ВЫБИРАЕТСЯ СЛЕДУЮЩИЙ ТЕСТ
=============================
    ballow = shans_polzy * pribavka_znaniya / (compute + vremya)

Ни одно из трёх чисел не выдумывается на ходу: они записаны в реестре
рядом с гипотезой и меняются только вместе с новым фактом. Машина не
решает, что интересно. Она считает, что дешевле всего узнать.

ЧЕГО ЭТОТ ФАЙЛ НЕ ДЕЛАЕТ
========================
Не торгует, не отправляет заявок, не переводит в CANARY и не обещает
прибыль. Он обещает ровно одно: каждый день либо один положительный
след становится ближе к проверке, либо одна плохая гипотеза умирает
дёшево — и ни то ни другое не забывается.

    python3 research_lab/reestr.py --spisok
    python3 research_lab/reestr.py --sleduyushchiy
    python3 research_lab/reestr.py --nochnoy
    python3 research_lab/reestr.py --tsikl      # раз в сутки, пока не закроешь
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
BAZA = KOREN / "research_lab/data/reestr.json"
ISTORIYA = KOREN / "research_lab/data/reestr_istoriya.jsonl"
ZAMOK = KOREN / "research_lab/data/reestr.lock"

# ЛЕСТНИЦА СОСТОЯНИЙ. Только вверх, и не через ступень.
#
# Раньше между «нашли» и «торгует» не было ничего, и хорошая нога могла
# навсегда остаться в research_lab. Три последние ступени — это и есть
# недостающая передача из исследования в производство.
SOSTOYANIYA = [
    "NEGATIVE",          # умерло по объявленному правилу, хранится вечно
    "HYPOTHESIS",        # идея в очереди. НИЧЕГО не измерено. Позитива здесь нет
    "POSITIVE_LEAD",     # плюс УЖЕ наблюдался в объявленном заранее тесте
    "CANDIDATE",         # контракт заморожен, критерий PASS/FAIL объявлен
    "SHADOW",            # идёт вперёд и сам набирает наблюдения
    "READY_FOR_BUILD",   # исследование закончено, собран PROMOTION_PACKET
    "READY_FOR_CANARY",  # производство приняло пакет и закрыло свои ворота
    "TINY_LIVE",         # минимальные деньги
    "SCALE_CANDIDATE",   # первые живые сделки прошли, обсуждается размер
]

# ГРАНИЦА ПОЛНОМОЧИЙ. Ниже неё я предлагаю переход и собираю
# свидетельство. Выше — только владелец, отдельным письменным «да».
# Машина не переводит в живые деньги никогда и ни при каких числах.
TOLKO_VLADELETS = {"TINY_LIVE", "SCALE_CANDIDATE"}
MOYA_GRANICA = "READY_FOR_BUILD"   # дальше этого я сам не двигаю

# Первичное население реестра. Каждое число — из прогона, у каждого есть
# путь к свидетельству. Чего нет в файлах, того здесь нет.
NACHALO = [
    {
        "id": "ETS2S", "imya": "Элдер, три экрана, шорт по лимиту",
        "sostoyanie": "SHADOW",
        "edzh": "+0.126R к контролю того же режима, sigma 0.34",
        "N": "617 закрытых из 1300", "ustoychivost": "не измерена",
        "izderzhki": "учтены, лимит honest fill",
        "nezavisimost": "крипта, средний срок",
        "svidetelstvo": "research_lab/data/ten_ETS2S.jsonl",
        "sleduyushchiy_test": "просто идти до 1300 закрытых решений",
        "pass_fail": "PASS при эдже по режиму выше порога Бонферрони на 1300",
        "shans": 0.35, "znanie": 0.9, "cena": 0.1,
    },
    {
        "id": "ARB_EGLD", "imya": "Арбитраж EGLD между биржами",
        "sostoyanie": "POSITIVE_LEAD",
        "edzh": "+47 $ чистыми на 7 465 $ после комиссий по биржам, метка HEDGEABLE",
        "N": "1 455 срезов за ~8 ч", "ustoychivost": "не измерена, замер прерывался",
        "izderzhki": "комиссии по биржам, ставки ПУБЛИЧНЫЕ, не аккаунта",
        "nezavisimost": "наивысшая: рыночного риска нет",
        "svidetelstvo": "research_lab/data/arb_ten.jsonl",
        "sleduyushchiy_test": "найти ВОСПОЛНИМЫЙ цикл: другой маршрут пополнения, "
                              "другая пара или биржа с тем же перекосом",
        "pass_fail": "PASS только если перекос можно снимать ПОВТОРНО. "
                     "Однократный съём запасом стратегией не считается",
        "shans": 0.4, "znanie": 0.8, "cena": 0.15,
        "povtoryaemost": "НЕТ — конечная возможность, не нога",
        "pochemu": "ввод EGLD на Bitget закрыт, поэтому перекос и живёт. "
                   "Снять его можно ровно на заранее заведённый запас и один "
                   "раз; дальше монета застревает на бирже покупки. "
                   "Риск второй ноги при этом ничтожен: эдж 39.6-58.4 бп "
                   "против сдвига 0.0 бп медиана и 4.4-6.2 бп в 90% случаев, "
                   "доля моментов хуже эджа — ноль на 1576 парах.",
    },
    {
        "id": "ALPACA_INTENDED", "imya": "Намеренный контракт Alpaca, v38 successor",
        "sostoyanie": "CANDIDATE",
        "edzh": "14.48% годовых, DD 7.57%, PF 1.81 — история",
        "N": "64 сделки", "ustoychivost": "СЛАБАЯ: половины 27.70 против 0.59",
        "izderzhki": "10 бп на сторону",
        "nezavisimost": "другой рынок, акции США",
        "svidetelstvo": "research_lab/data/alpaca_namerennyy_ten.jsonl",
        "sleduyushchiy_test": "закрыть операционные ворота на VPS: семь свидетельств",
        "pass_fail": "PASS при семи свидетельствах прогона на VPS; "
                     "три месячных решения — это уже STRONG, не минимальные ворота",
        "shans": 0.3, "znanie": 0.6, "cena": 0.2,
        "povtoryaemost": "ДА — месячный ритм, 12 решений в год",
        "strategy_id": "ALPACA-BASELINE-26f7ff663dc98e87",
        "kontrakt": "select_v38_successor + ворота SPY200 + 4 места + валовая 0.70 "
                    "+ потолок веса 0.60 + стоп 2xATR20 от ФАКТИЧЕСКОГО исполнения "
                    "+ храповик 3.5/3.5/0.5 + блок повтора 21 день + 10 бп на сторону",
        "vorota": "research_lab/ALPACA_VOROTA_2026_09_14.md",
        "dokazano": "офлайн-репетиция 9 из 9: заявки, якорь на исполнении, "
                    "выход по стопу, комиссии, детерминизм, чужая бумага не тронута",
        "blokery": "круг через брокера, защитный ордер у каждой позиции, "
                   "владелец сироты AMZN, восстановление после перезапуска, стоп-кран",
        "trebovaniya_birzhi": "Alpaca: дробные стопы только DAY, GTC только на "
                              "целых акциях; стопы не исполняются в расширенные часы",
        "min_kapital": "ограничения нет; целые акции и GTC потребовали бы "
                       "2193 $ на текущем выборе и до 17702 $ в худшем случае",
    },
    {
        "id": "ATT1_KASANIE", "imya": "Номер касания линии у ATT1",
        "sostoyanie": "POSITIVE_LEAD",
        "edzh": "лестница к плацебо: -2.6 / -0.3 / +2.3 / +1.3 %",
        "N": "23 656 событий на истории", "ustoychivost": "вперёд не проверялась",
        "izderzhki": "не применимо, это признак",
        "nezavisimost": "внутри ATT1, продакшн ведёт Кодекс",
        "svidetelstvo": "ITOG.md часть 63",
        "sleduyushchiy_test": "писать номер касания в журнал тени рядом с исходом",
        "pass_fail": "PASS если вперёд та же лестница на 200+ решениях",
        "shans": 0.25, "znanie": 0.5, "cena": 0.1,
    },
    {
        "id": "GOLD", "imya": "Золото, H1 через мост MT5",
        "sostoyanie": "POSITIVE_LEAD",
        "edzh": "не измерен", "N": "0", "ustoychivost": "—",
        "izderzhki": "не измерены", "nezavisimost": "другой рынок",
        "svidetelstvo": "ветка claude/alpaca-2026-09-07, коммиты 8 сентября",
        "sleduyushchiy_test": "закрыть сбор канонического набора H1",
        "pass_fail": "не объявлен — нить не доведена",
        "shans": 0.2, "znanie": 0.7, "cena": 0.5,
    },
    {
        "id": "ATT1_AGG", "imya": "ATT1 целиком, агрегат тени",
        "sostoyanie": "SHADOW",
        "edzh": "+0.055R к контролю режима при sigma 0.27; по деньгам -10.2R",
        "N": "554 закрытых из 1300", "ustoychivost": "винрейт вперёд 39% против 74% на печати",
        "izderzhki": "учтены", "nezavisimost": "крипта",
        "svidetelstvo": "research_lab/data/ten_ATT1.jsonl",
        "sleduyushchiy_test": "идти до 1300, продакшн ведёт Кодекс",
        "pass_fail": "PASS при эдже по режиму выше порога на 1300",
        "shans": 0.2, "znanie": 0.9, "cena": 0.1,
    },
    {
        "id": "UROVNI_OTBOY", "imya": "Отбой от уровня как самостоятельный вход",
        "sostoyanie": "NEGATIVE",
        "edzh": "-2.6% к плацебо на геометрии ATT1, отрицательно во всех трёх эпохах",
        "N": "23 656 событий", "ustoychivost": "устойчиво отрицателен",
        "izderzhki": "—", "nezavisimost": "—",
        "svidetelstvo": "ITOG.md часть 62",
        "sleduyushchiy_test": "не переоткрывать без нового детектора",
        "pass_fail": "закрыто",
        "shans": 0.0, "znanie": 0.0, "cena": 1.0,
    },
    {
        "id": "ATT1_FILTER", "imya": "Фильтр ATT1 по одному признаку",
        "sostoyanie": "NEGATIVE",
        "edzh": "все признаки провалили проверку по трём эпохам",
        "N": "1 376 сделок, 80 монет", "ustoychivost": "формы разные в 2023/2024/2025",
        "izderzhki": "—", "nezavisimost": "—",
        "svidetelstvo": "ITOG.md часть 63",
        "sleduyushchiy_test": "не переоткрывать; эдж размазан, фильтровать нечего",
        "pass_fail": "закрыто",
        "shans": 0.0, "znanie": 0.0, "cena": 1.0,
    },
    {
        "id": "ALPACA_A_G2", "imya": "Челленджер A+G2 у Alpaca",
        "sostoyanie": "NEGATIVE",
        "edzh": "30.26% годовых на замере, но провалил все четыре кризисных среза",
        "N": "—", "ustoychivost": "не воспроизвёлся",
        "izderzhki": "10 бп", "nezavisimost": "—",
        "svidetelstvo": "ветка claude/alpaca-2026-09-07, коммит 703174c",
        "sleduyushchiy_test": "не переоткрывать",
        "pass_fail": "закрыто",
        "shans": 0.0, "znanie": 0.0, "cena": 1.0,
    },
]


PAKETY = KOREN / "research_lab/pakety"


def paket(ident: str) -> int:
    """PROMOTION_PACKET — всё, что нужно производству, и ничего лишнего.

    Смысл ровно один: Кодекс должен взять эту бумагу и начать строить,
    НЕ переоткрывая исследование. Если в пакете чего-то не хватает и ему
    приходится лезть в research_lab и разбираться заново — пакет плохой.

    Пакет НЕ даёт права на деньги. Он даёт право начать сборку.
    """
    z = zagruzit()
    x = next((y for y in z if y["id"] == ident), None)
    if x is None:
        print(f"  в реестре нет «{ident}»")
        return 1
    if x["sostoyanie"] in ("NEGATIVE",):
        print(f"  {ident} закрыт, пакет не собирается")
        return 1
    nedostayet = [k for k in ("strategy_id", "kontrakt", "dokazano", "blokery",
                              "trebovaniya_birzhi", "povtoryaemost")
                  if not x.get(k)]

    t = [f"# PROMOTION_PACKET — {x['id']}", "",
         f"**{x['imya']}**", "",
         "Собрано реестром. Производство берёт эту бумагу и начинает сборку,",
         "не переоткрывая исследование. Права на деньги пакет не даёт.", "",
         "## 1. Личность", "",
         f"    strategy_id   {x.get('strategy_id', 'НЕ ЗАДАН')}",
         f"    состояние     {x['sostoyanie']}",
         f"    повторяемость {x.get('povtoryaemost', 'НЕ ОПРЕДЕЛЕНА')}", "",
         "## 2. Контракт целиком", "",
         f"    {x.get('kontrakt', 'НЕ ЗАДАН')}", "",
         "## 3. Что доказано и на чём", "",
         f"{x.get('dokazano', 'НЕ ЗАДАНО')}", "",
         f"Свидетельство: `{x['svidetelstvo']}`", "",
         f"Экономика: {x['edzh']}  ",
         f"Наблюдений: {x['N']}  ",
         f"Устойчивость: {x['ustoychivost']}  ",
         f"Издержки: {x['izderzhki']}", "",
         "## 4. Требования биржи или брокера", "",
         f"{x.get('trebovaniya_birzhi', 'НЕ ЗАДАНЫ')}", "",
         "## 5. Известные блокеры", "",
         f"{x.get('blokery', 'не перечислены')}", "",
         "## 6. Ворота", "",
         f"Разведены в `{x.get('vorota', 'отдельного файла нет')}`.",
         "Минимальные ворота канарейки и полный перевод — РАЗНЫЕ вещи.",
         "Требовать от маленькой живой проверки доказательства эджа нельзя:",
         "это запрещает её навсегда.", "",
         "## 7. Капитал и риск", "",
         f"{x.get('min_kapital', 'не определён')}", "",
         "Размер первой канарейки задаёт владелец. Единственное условие:",
         "сумма, которую можно потерять целиком без последствий.", "",
         "## 8. Приёмочные проверки для производства", "",
         "Каждая закрывается ПРЕДЪЯВЛЯЕМЫМ свидетельством, а не словами.",
         "Список — в файле ворот, раздел «что должен доказать прогон».", "",
         "## 9. Что требует отдельного согласия владельца", "",
         "    перевод в TINY_LIVE и любой размер живых денег",
         "    любое отклонение от замороженного контракта",
         "    включение аварийного слоя, меняющего выходы", "",
         "## 10. Чего в пакете НЕТ", "", ]
    t += ([f"    {k}" for k in nedostayet] if nedostayet
          else ["    ничего: все обязательные поля заполнены"])
    t += ["", "Пустое поле — это не мелочь. Производство, наткнувшись на него,",
          "пойдёт додумывать, и через месяц мы не поймём, что оно построило.", ""]

    PAKETY.mkdir(parents=True, exist_ok=True)
    f = PAKETY / f"PROMOTION_PACKET_{ident}.md"
    f.write_text("\n".join(t), encoding="utf-8")
    print("\n".join(t))
    print(f"\n  записано: {f}")
    if nedostayet:
        print(f"  ПАКЕТ НЕПОЛНЫЙ: не заполнено {len(nedostayet)} обязательных полей")
        return 1
    return 0


def perevesti(ident: str, kuda: str) -> int:
    """Предложение перехода. Выше своей границы я не двигаю ничего."""
    if kuda not in SOSTOYANIYA:
        print(f"  нет такого состояния: {kuda}")
        return 1
    z = zagruzit()
    x = next((y for y in z if y["id"] == ident), None)
    if x is None:
        print(f"  в реестре нет «{ident}»")
        return 1
    if kuda in TOLKO_VLADELETS:
        print(f"  {ident}: перевод в {kuda} — это ЖИВЫЕ ДЕНЬГИ.")
        print("  Машина сюда не переводит. Нужно отдельное письменное")
        print("  согласие владельца, и вносится оно руками.")
        return 1
    if SOSTOYANIYA.index(kuda) > SOSTOYANIYA.index(MOYA_GRANICA):
        print(f"  {ident}: {kuda} выше моей границы {MOYA_GRANICA}.")
        print("  Дальше решает производство, приняв PROMOTION_PACKET.")
        return 1
    staroe = x["sostoyanie"]
    # В NEGATIVE упасть можно с любой ступени — это и есть смерть гипотезы,
    # и запрещать её было бы абсурдом. Запрещено другое: тихо откатиться
    # с SHADOW обратно в POSITIVE_LEAD, чтобы попробовать ещё разок.
    if (kuda != "NEGATIVE" and staroe != "NEGATIVE"
            and SOSTOYANIYA.index(kuda) < SOSTOYANIYA.index(staroe)):
        print(f"  {ident}: {staroe} -> {kuda} это движение ВНИЗ.")
        print("  Обратного хода нет: упавшее становится NEGATIVE со своей")
        print("  причиной, а не возвращается в след. Иначе это карусель.")
        return 1
    x["sostoyanie"] = kuda
    sys.path.insert(0, str(KOREN / "research_lab/fabrika"))
    from reestr_sink import zamok, atomarno      # тот же замок, что у фабрики
    with zamok():
        z2 = json.loads(BAZA.read_text(encoding="utf-8"))
        for y in z2:
            if y["id"] == ident:
                y["sostoyanie"] = kuda
        atomarno(BAZA, json.dumps(z2, ensure_ascii=False, indent=1) + "\n")
    with ISTORIYA.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kogda_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "perehod": {"id": ident, "iz": staroe, "v": kuda}},
                            ensure_ascii=False) + "\n")
    print(f"  {ident}: {staroe} -> {kuda}")
    return 0


def zagruzit() -> list[dict]:
    if BAZA.exists():
        return json.loads(BAZA.read_text(encoding="utf-8"))
    BAZA.parent.mkdir(parents=True, exist_ok=True)
    BAZA.write_text(json.dumps(NACHALO, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return NACHALO


def ball(z: dict) -> float:
    c = max(float(z.get("cena", 1.0)), 0.01)
    return float(z.get("shans", 0)) * float(z.get("znanie", 0)) / c


def spisok(pokazat_mertvye: bool = True) -> int:
    z = zagruzit()
    zhivye = [x for x in z if x["sostoyanie"] != "NEGATIVE"]
    zhivye.sort(key=ball, reverse=True)
    print("=" * 100)
    print("  РЕЕСТР ГИПОТЕЗ. Живое сверху, по баллу «сколько узнаем на рубль усилий»")
    print("=" * 100)
    print(f"  {'id':<18}{'состояние':<15}{'балл':>7}  эдж")
    for x in zhivye:
        print(f"  {x['id']:<18}{x['sostoyanie']:<15}{ball(x):>7.2f}  {x['edzh'][:58]}")
        print(f"  {'':<18}{'':<15}{'':>7}  N={x['N']}; устойчивость: {x['ustoychivost'][:46]}")
        print(f"  {'':<18}{'':<15}{'':>7}  след. тест: {x['sleduyushchiy_test'][:60]}")
    if pokazat_mertvye:
        print()
        print("  ЗАКРЫТО. Лежит здесь, чтобы не убивать во второй раз:")
        for x in z:
            if x["sostoyanie"] == "NEGATIVE":
                print(f"    {x['id']:<18}{x['edzh'][:72]}")
    print("=" * 100)
    return 0


def sleduyushchiy() -> int:
    """Следующий ВЫПОЛНИМЫЙ тест, а не просто самый дешёвый.

    ДЕФЕКТ, найденный первым же запуском 14 сентября. Отбор назвал ETS2S,
    потому что у него лучший балл: шанс высокий, знание высокое, цена
    почти ноль. Но его «следующий тест» — просто идти до 1300 решений.
    Выполнять там нечего, и фабрика, послушав такой ответ, встала бы
    навсегда, каждый раз называя самую дешёвую пассивную нить.

    Поэтому нити делятся на три вида:
        mogu_seychas   могу взять и сделать
        sam_zreet      идёт вперёд сам, трогать нельзя и не нужно
        u_proizvodstva ушла в сборку, дальше не моя
    Выбирается лучшая из первых. Остальные печатаются рядом, чтобы было
    видно, что они живы, а не забыты.
    """
    zhivye = [x for x in zagruzit()
              if x["sostoyanie"] in ("HYPOTHESIS", "POSITIVE_LEAD", "CANDIDATE",
                                     "SHADOW", "READY_FOR_BUILD")]
    if not zhivye:
        print("  живых гипотез нет"); return 0
    zreyut = [x for x in zhivye if x.get("deystvie") == "sam_zreet"]
    u_proizv = [x for x in zhivye if x.get("deystvie") == "u_proizvodstva"]
    zaparkovany = [x for x in zhivye if x.get("zaparkovan")]
    mogu = [x for x in zhivye
            if x.get("deystvie", "mogu_seychas") == "mogu_seychas"
            and not x.get("zaparkovan")]

    if zreyut or u_proizv or zaparkovany:
        print("  идёт само и трогать не надо:")
        for x in zreyut:
            print(f"    {x['id']:<18}{x['N']}")
        for x in u_proizv:
            print(f"    {x['id']:<18}у производства: {x['sleduyushchiy_test'][:52]}")
        for x in zaparkovany:
            print(f"    {x['id']:<18}запаркован решением владельца")
        print()

    if not mogu:
        print("  ВЫПОЛНИМЫХ тестов не осталось. Это не простой: всё живое либо")
        print("  зреет само, либо ушло в сборку, либо запарковано. Фабрика ждёт")
        print("  нового кандидата, а не указаний.")
        return 0
    mogu.sort(key=ball, reverse=True)
    x = mogu[0]
    print("=" * 100)
    print(f"  СЛЕДУЮЩИЙ ТЕСТ: {x['id']} — {x['imya']}")
    print("=" * 100)
    print(f"  состояние:    {x['sostoyanie']}")
    print(f"  что делаем:   {x['sleduyushchiy_test']}")
    print(f"  PASS/FAIL:    {x['pass_fail']}")
    print(f"  свидетельство {x['svidetelstvo']}")
    print(f"  балл {ball(x):.2f} = шанс {x['shans']} x знание {x['znanie']} / цена {x['cena']}")
    print()
    print("  Балл не означает «эта сработает». Он означает «про эту мы узнаем")
    print("  больше всего за наименьшие усилия». Это разные вещи.")
    print("=" * 100)
    return 0


def _tikho(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, cwd=KOREN, capture_output=True, text=True,
                              timeout=600).stdout
    except Exception as e:
        return f"(не выполнилось: {type(e).__name__})"


def nochnoy() -> int:
    """Один ночной цикл: собрать состояние теней, дописать в историю, назвать
    следующий тест. Ничего не решает и ничего не меняет в реестре сам:
    переводы между состояниями делает человек, машина только измеряет."""
    kogda = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"НОЧНОЙ ЦИКЛ {kogda}")
    print("=" * 100)
    snimok = {"kogda_utc": kogda, "teni": {}}
    for imya, cmd in (
        ("ETS2S", [sys.executable, "research_lab/ten.py", "elder_triple_screen_v2",
                   "ElderTripleScreenV2Strategy", "ETS2S", "--otchet"]),
        ("ATT1", [sys.executable, "research_lab/ten.py", "alt_trendline_touch_v1",
                  "AltTrendlineTouchV1Strategy", "ATT1", "--otchet"]),
        ("ARB", [sys.executable, "research_lab/arb_ten.py", "--otchet"]),
        ("ALPACA", [sys.executable, "research_lab/alpaca_namerennyy_ten.py", "--otchet"]),
    ):
        out = _tikho(cmd)
        klyuchevye = [s.strip() for s in out.splitlines()
                      if any(k in s for k in ("ЗАКРЫТО", "решений", "эдж", "живых",
                                              "итог", "срезов", "ВЕРДИКТ"))][:4]
        snimok["teni"][imya] = klyuchevye
        print(f"\n  {imya}")
        for s in klyuchevye or ["(нет данных)"]:
            print(f"    {s}")
    ISTORIYA.parent.mkdir(parents=True, exist_ok=True)
    with ISTORIYA.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snimok, ensure_ascii=False) + "\n")
    print()
    sleduyushchiy()
    print(f"\n  снимок дописан в {ISTORIYA}")
    return 0


def tsikl(chasov: float) -> int:
    """Тот же ночной цикл, но крутится сам и ДЕРЖИТ ЗАМОК всё время.

    Раньше цикл заводился строкой `while true; do ...; sleep 86400; done`
    в bash. Замок внутри питона такую конструкцию не спасает: он живёт
    только на время одного прогона, а между прогонами спит вместе с
    циклом. 14 сентября это и случилось — два цикла запустились друг
    поверх друга и оба писали в одну историю.

    Здесь замок держится всё время работы, поэтому вторая копия просто
    откажется стартовать. Механизмов автозапуска по-прежнему НЕТ: это
    обычный процесс, который ты поднимаешь сам и который умирает вместе
    с сессией.
    """
    if ZAMOK.exists():
        try:
            pid = int(ZAMOK.read_text().strip())
            os.kill(pid, 0)
            print(f"ЦИКЛ УЖЕ РАБОТАЕТ, процесс {pid}. Второй копии не будет.")
            print(f"  остановить:  kill {pid}")
            return 1
        except Exception:
            pass
    ZAMOK.parent.mkdir(parents=True, exist_ok=True)
    ZAMOK.write_text(str(os.getpid()))
    print(f"ЦИКЛ РЕЕСТРА. Прогон раз в {chasov:g} ч, процесс {os.getpid()}")
    try:
        while True:
            nochnoy()
            sys.stdout.flush()
            time.sleep(chasov * 3600)
    finally:
        try:
            ZAMOK.unlink()
        except Exception:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spisok", action="store_true")
    ap.add_argument("--sleduyushchiy", action="store_true")
    ap.add_argument("--nochnoy", action="store_true")
    ap.add_argument("--tsikl", action="store_true")
    ap.add_argument("--paket", metavar="ID",
                    help="собрать PROMOTION_PACKET для кандидата")
    ap.add_argument("--perevesti", nargs=2, metavar=("ID", "СОСТОЯНИЕ"),
                    help="предложить переход по лестнице состояний")
    ap.add_argument("--chasov", type=float, default=24.0)
    a = ap.parse_args()
    if a.paket:
        return paket(a.paket)
    if a.perevesti:
        return perevesti(a.perevesti[0], a.perevesti[1])
    if a.tsikl:
        return tsikl(a.chasov)
    if a.nochnoy:
        return nochnoy()
    if a.sleduyushchiy:
        return sleduyushchiy()
    return spisok()


if __name__ == "__main__":
    raise SystemExit(main())
