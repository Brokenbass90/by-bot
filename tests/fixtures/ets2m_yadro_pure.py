KONFIG = {
    "modul": "elder_triple_screen_v2",
    "klass": "ElderTripleScreenV2Strategy",
    "storona": "short",
    "otstup": 0.002,
    "zhdat": 6,
    "stop": 4.0,
    "fee_vhod": 1.5,
    "fee_vyhod": 5.5,
    # ПРИЧИННОСТЬ НА БАРЕ ВХОДА. Часовой OHLC не говорит, что случилось
    # раньше: касание лимита или касание стопа/цели в том же баре. Гадать
    # нельзя, поэтому правило объявляется ДО данных и попадает в хеш
    # конфигурации: на баре входа срабатывает ТОЛЬКО стоп, цели — начиная
    # со следующего бара. Неоднозначность всегда разрешается против нас.
    "prichinnost_bar_vhoda": "na_bare_vhoda_tolko_stop",
    # РАСПИСАНИЕ ВЫЗОВОВ СТРАТЕГИИ. 15 сентября доказано офлайн на одних и
    # тех же барах: `maybe_signal` ПОМНИТ состояние между вызовами. Спросив
    # её на лишнем баре, вы меняете её ответ на следующем. Наборы сигналов
    # разошлись в ОБЕ стороны — значит это не блокировка, а состояние.
    # Отсюда инвариант, который нельзя ослаблять: ядро вызывает стратегию
    # РОВНО в той же последовательности, что канонический ten.py. Ни одного
    # лишнего вызова, ни одного пропущенного. Фиксированного якоря мало.
    # ИСТОЧНИК ВХОДОВ — ВНЕШНИЙ. Ядро не вызывает maybe_signal вообще.
    # Два доказанных факта 15 сентября: ответ стратегии зависит от истории
    # вызовов, и холодная эпоха не может повторить прогретую тень (8 против
    # 0 сигналов на восьми монетах). Значит спорить с прогревом бессмысленно:
    # вход надо брать у той самой ETS2S, чей выход мы и хотим улучшить.
    "istochnik": "ten_ETS2S.jsonl",
    # Доля первой цели в журнал источника не пишется. Берётся значение по
    # умолчанию лаборатории. Если оно неверно, наш CONTROL систематически
    # разойдётся с R источника — и это будет видно в отчёте, а не спрячется.
    "dolya_pervoy_celi": 0.55,
    "env": {"ETS2_TREND_TF": "1440", "ETS2_WAVE_TF": "240",
            "ETS2_ENTRY_TF": "60", "ETS2_RISK_TF": "240"},
}

DVIGATELI = {
    "CONTROL": {"rr": None,       "hold": 336},
    "24H":     {"rr": None,       "hold": 24},
    "WIDE":    {"rr": (0.5, 1.0), "hold": 336},
}

KONTROL = "CONTROL"

def papka(epoha: str) -> Path:
    p = YADRO / epoha
    p.mkdir(parents=True, exist_ok=True)
    return p

def chitat_jsonl(p: Path) -> list:
    if not p.exists():
        return []
    out = []
    for s in p.read_text(encoding="utf-8").splitlines():
        if s.strip():
            try:
                out.append(json.loads(s))
            except Exception:
                continue
    return out

def istochnik_vhodov(nachalo: int) -> list:
    """ВНЕШНИЙ ИСТОЧНИК ВХОДОВ. Ядро НЕ вызывает maybe_signal вообще.

    Почему так, а не «повторить генератор». 15 сентября доказано дважды:
    ответ `maybe_signal` зависит от того, сколько раз её спросили раньше.
    Живая ETS2S идёт с 3 сентября и к каждому бару приходит с сотнями
    вызовов за спиной; любая свежая эпоха приходит холодной. На восьми
    монетах холодный прогон дал 8 сигналов, прогретый — ноль.

    Воспроизвести её состояние теоретически можно, отыграв всю историю
    вызовов с 3 сентября. Но это лишняя работа ради вопроса, который мы
    и не задавали. Мы спрашиваем не «умеет ли ядро быть Элдером», а
    «можно ли улучшить ВЫХОД у реально работающей ETS2S, не трогая её
    вход». Значит вход надо просто взять у неё.

    Берутся ЗАКРЫТЫЕ решения: только они несут долю стопа и цели, без
    которых запускать движки не на чем. Ждущая запись их не содержит.
    Это не цензура по длительности: каждое решение рано или поздно
    закрывается, и в когорту оно попадает по времени СИГНАЛА, а не по
    времени закрытия.
    """
    syrye = chitat_jsonl(DATA / KONFIG["istochnik"])
    vidno = {}
    for x in syrye:
        if x.get("R") is None or x.get("stop_dolya") is None:
            continue
        ts = int(x["ts"])
        if ts < nachalo:
            continue
        k = (x["sym"], ts)
        if k not in vidno:                 # первая запись побеждает
            vidno[k] = x
    return [vidno[k] for k in sorted(vidno)]

def paritet_istochnika(epoha: str) -> int:
    """Единственный паритет, который здесь имеет смысл: наш журнал входов
    против источника. Не «похожий генератор», а буквально один источник.

        у источника есть решение, у нас его нет  -> ПРОВАЛ
        у нас есть вход, которого нет в источнике -> ПРОВАЛ
        расходится сторона, доля стопа или цели   -> ПРОВАЛ
        дубль по (монета, время)                  -> ПРОВАЛ
        вход раньше начала эпохи                  -> ПРОВАЛ
        источник пуст после начала эпохи          -> NOT_MEASURED
    """
    p = papka(epoha)
    man = json.loads((p / "epoha.json").read_text(encoding="utf-8"))
    nachalo = man["nachalo_ms"]
    ist = {(x["sym"], int(x["ts"])): x for x in istochnik_vhodov(nachalo)}
    moi_spisok = chitat_jsonl(p / "vhody.jsonl")
    moi = {(x["sym"], int(x["ts"])): x for x in moi_spisok}
    import datetime as dt
    kogda = dt.datetime.fromtimestamp(nachalo / 1000, dt.timezone.utc)
    print("=" * 88)
    print(f"  ПАРИТЕТ ИСТОЧНИКА: эпоха {epoha} против {KONFIG['istochnik']}")
    print(f"  начало эпохи {kogda:%Y-%m-%d %H:%M} UTC")
    print("=" * 88)
    if not ist and not moi:
        print("  в источнике после начала эпохи пока нет закрытых решений.")
        print("  NOT_MEASURED — это отсрочка, а не результат.")
        print("=" * 88)
        return 2
    net = sorted(set(ist) - set(moi))
    lish = sorted(set(moi) - set(ist))
    dubli = len(moi_spisok) - len(moi)
    rano = [k for k in moi if k[1] < nachalo]
    raz = []
    for k in sorted(set(ist) & set(moi)):
        a_, b_ = moi[k], ist[k]
        if a_["side"] != b_["side"]:
            raz.append((k, "сторона"))
        elif abs(float(a_["stop_dolya"]) - float(b_["stop_dolya"])) > 1e-9:
            raz.append((k, "доля стопа"))
        elif abs(float(a_["k1"]) - float(b_.get("rr1") or 999.0)) > 1e-9:
            raz.append((k, "первая цель"))
    print(f"  в источнике {len(ist)}, у нас {len(moi)}, общих {len(set(ist) & set(moi))}")
    print(f"  не перенесено {len(net)}, лишних {len(lish)}, дублей {dubli}, "
          f"раньше начала {len(rano)}, расхождений полей {len(raz)}")
    for k in (net[:3] + lish[:3]):
        print(f"    {k[0]} {k[1]}")
    for k, pole in raz[:3]:
        print(f"    {k[0]} {k[1]}: {pole}")
    ok = not net and not lish and not dubli and not rano and not raz
    print()
    print("  ПАРИТЕТ ИСТОЧНИКА ЕСТЬ." if ok else
          "  ПАРИТЕТА НЕТ. Считать ветки нельзя.")
    print("=" * 88)
    return 0 if ok else 1

def otsenit(epoha: str, kogorta: int) -> int:
    """Оценка только по ЗАМОРОЖЕННОЙ КОГОРТЕ входов и только тогда, когда
    у ВСЕХ движков этой когорты есть терминальный исход. Иначе скорость
    закрытия сама становится отбором: быстрые сделки попадают в выборку,
    медленные ждут за дверью, и ветка с более длинным выходом
    систематически недосчитывается своих же победителей."""
    sys.path.insert(0, str(KOREN / "research_lab"))
    from vnutri import klaster_z_bystro
    p = papka(epoha)
    vhody = sorted(chitat_jsonl(p / "vhody.jsonl"), key=lambda x: (x["ts"], x["sym"]))
    isp = {x["id"]: x for x in chitat_jsonl(p / "ispolnenie.jsonl")}
    ish = {(x["id"], x["dvigatel"]): x for x in chitat_jsonl(p / "ishody.jsonl")}

    print("=" * 88)
    print(f"  ОЦЕНКА ЭПОХИ {epoha}. Когорта {kogorta} входов, замороженная по времени.")
    print("=" * 88)
    if len(vhody) < kogorta:
        print(f"  входов всего {len(vhody)} из {kogorta}. Ворота не достигнуты.")
        print("  Это NOT_MEASURED. Числа не считаются и не печатаются.")
        print("=" * 88)
        return 2
    kg = vhody[:kogorta]
    nereshennye = [z for z in kg if z["id"] not in isp]
    if nereshennye:
        print(f"  у {len(nereshennye)} входов когорты ещё не решено исполнение.")
        print("  Ждать. NOT_MEASURED.")
        print("=" * 88)
        return 2
    zapoln = [z for z in kg if isp[z["id"]]["ispolnen"]]
    nedodelki = [(z["id"], imya) for z in zapoln for imya in DVIGATELI
                 if (z["id"], imya) not in ish]
    if nedodelki:
        po_dvig = defaultdict(int)
        for _, imya in nedodelki:
            po_dvig[imya] += 1
        print(f"  когорта набрана, исполнилось {len(zapoln)}, но не все движки")
        print(f"  дошли до терминала: {dict(po_dvig)}")
        print("  Считать сейчас — значит выбросить медленных победителей той")
        print("  ветки, у которой выход длиннее. NOT_MEASURED, ждать.")
        print("=" * 88)
        return 2

    poteryannye = [(z["id"], imya) for z in zapoln for imya in DVIGATELI
                   if ish[(z["id"], imya)]["R"] is None]
    if poteryannye:
        print(f"  у {len(poteryannye)} пар (вход, движок) исход помечен как")
        print("  «ДАННЫЕ УТЕРЯНЫ»: бар входа выпал из окна котировок раньше,")
        print("  чем движок дошёл до терминала. Когорта испорчена — выбросить")
        print("  эти сделки нельзя, они выпали НЕ случайно, а по длительности.")
        print("  Эпоху начинать заново. NOT_MEASURED.")
        print("=" * 88)
        return 2

    mon_imena = sorted({z["sym"] for z in zapoln})
    kod = {s: i for i, s in enumerate(mon_imena)}
    mon = np.array([kod[z["sym"]] for z in zapoln], dtype=np.int64)
    tsy = np.array([z["ts"] for z in zapoln])
    seredina = float(np.median(tsy))
    R = {imya: np.array([ish[(z["id"], imya)]["R"] for z in zapoln])
         for imya in DVIGATELI}

    print(f"  входов в когорте {kogorta}, исполнилось {len(zapoln)}, "
          f"монет {len(mon_imena)}")
    print(f"  издержки: мейкер {KONFIG['fee_vhod']} бп вход, "
          f"тейкер {KONFIG['fee_vyhod']} бп выход, одинаково во всех ветках")
    print()
    print(f"  {'ветка':<9}{'сумма R':>11}{'ср. R':>10}{'прирост':>10}"
          f"{'сигма':>8}{'эпохи':>8}")
    baza = R[KONTROL]
    for imya in DVIGATELI:
        d = R[imya] - baza
        if imya == KONTROL:
            print(f"  {imya:<9}{baza.sum():>+10.1f}R{baza.mean():>+10.4f}"
                  f"{'—':>10}{'—':>8}{'—':>8}")
            continue
        z = klaster_z_bystro(d, mon) if np.any(d != 0) else float("nan")
        p1, p2 = d[tsy < seredina], d[tsy >= seredina]
        ep = len(p1) > 0 and len(p2) > 0 and (p1.mean() > 0) == (p2.mean() > 0)
        print(f"  {imya:<9}{R[imya].sum():>+10.1f}R{R[imya].mean():>+10.4f}"
              f"{d.mean():>+10.4f}{z:>8.2f}{('да' if ep else 'нет'):>8}")
    print()
    print("  Правило приёмки — PREREG_TRI_TENI_2026_09_15.md: прирост > 0,")
    print("  сигма > 2.50, знак одинаков на половинах, среднее R ветки > 0.")
    print("  Прохождение одного окна даёт только допуск ко второму.")
    print("=" * 88)
    return 0
