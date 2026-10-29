#!/usr/bin/env python3
"""reestr_gipotez.py — единый реестр гипотез с памятью провалов (27.10.2026, Claude; предложение PM: «память отрицательных результатов»).
Сводит в одно место: вердикты судьи Фабрики (PRICHINY_VERDIKTOV.json), закрытые протоколом семьи, механизмы Polymarket и ноги, каталоги
Фабрики вперёд. У каждой записи: механизм/семья, статус, ПРИЧИНА провала по закрытому словарю, следующий ход.
Из реестра собираются «уроки» (≤ 450 знаков) — они дописываются в промпт генератора идей (ai_formula_v1.prompt_menyu), чтобы ИИ не
повторял те же ошибки под другим именем. Хук сторожа. Только чтение источников; выход data/factory_v3/REESTR_GIPOTEZ.{json,md}, uroki_dlya_ii.txt."""
import collections, json, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; F = LAB / "data" / "factory_v3"
PRICHINY = {  # закрытый словарь причин (PM 27.10)
    "NET_SIGNALA": "сигнал неотличим от случайного входа", "IZDERZHKI": "информация есть, её съедают спред/комиссии",
    "REZHIM": "работает в одной эпохе, ломается в другой", "NAPRAVLENIE": "плюс от скрытой ставки на направление рынка",
    "KONCENTRACIYA": "плюс держится на нескольких сделках", "ZAPAZDYVANIE": "рынок переоценивается быстрее нас",
    "EFFEKTIVNYY_RYNOK": "цены откалиброваны, дешёвого исхода нет", "MALO_DANNYH": "мощности не хватает",
    "PROTIV": "сигнал хуже случайного", "SLABYY_II": "модель не умеет задачу (прогноз хуже рынка)", "TEHNIKA": "техническая ошибка теста"}
KLASS_V_PRICHINU = {"NET_INFORMACII": "NET_SIGNALA", "INFO_EST_DENEG_NET": "IZDERZHKI", "NESTABILNO": "REZHIM", "PROTIV_SLUCHAYA": "PROTIV",
                    "MALO_DANNYH": "MALO_DANNYH", "NET_OKON": "TEHNIKA", "SLABYY_PLYUS": "MALO_DANNYH"}
RUCHNYE = [  # закрыто протоколом / проверено вне судьи Фабрики (источник — файлы-итоги в research_lab)
    ("SVIP_UROVNYA", "ложный пробой горизонтального уровня", "KILL", "NET_SIGNALA", "наклонные линии — не проверялись", "6091e14"),
    ("FX_GOLD_ETAP", "ночной дрейф FX, золото trend/pullback", "KILL", "REZHIM", "только с новым экономическим механизмом", "30.09"),
    ("OI_KAPITULYACIYA", "капитуляция через OI", "HISTORY_AGAINST", "NET_SIGNALA", "—", "26.10"),
    ("POLY_FAVORIT_KRIPTO", "ставка на фаворита в крипто-страйках", "KILL", "EFFEKTIVNYY_RYNOK", "—", "19.10"),
    ("POLY_FAVORIT_TEMY", "фаворит 80–95 ¢ во всех темах", "NEGATIVE", "EFFEKTIVNYY_RYNOK", "—", "POLY_FAVORIT_VSE_TEMY_ITOG"),
    ("POLY_STRUKTURA", "арбитраж negRisk / монотонность страйков", "NONE", "EFFEKTIVNYY_RYNOK", "—", "POLY_STRUKTURA_I_PX1_ITOG"),
    ("POLY_PX1", "запаздывание переоценки страйков", "FAIL", "ZAPAZDYVANIE", "секундное окно — поле HFT", "POLY_STRUKTURA_I_PX1_ITOG"),
    ("POLY_MAKER_NO", "мейкер продаёт переоценённый YES", "INCONCLUSIVE", "NAPRAVLENIE", "тень вперёд, плюс и в дни роста BTC", "POLY_MAKER_NO_ITOG"),
    ("POLY_OLLAMA_PROGNOZ", "ИИ-прогноз вероятности по новостям", "FAIL", "SLABYY_II", "ИИ как читатель, не прогнозист", "POLY_SISTEMA_I_PERERABOTKA"),
    ("POLY_ISHOD_RESHEN", "ИИ: исход уже решён по заголовкам RSS", "FAIL", "SLABYY_II", "первоисточники вместо RSS", "POLY_SISTEMA_I_PERERABOTKA"),
    ("POLY_LAG_POSLE_KONCA", "покупка 0.90–0.99 после конца рынка", "FAIL", "ZAPAZDYVANIE", "живой монитор: окно в минутах", "POLY_SISTEMA_I_PERERABOTKA"),
    ("KITY", "корзина 5L5S Binance", "TECH_PASS", "KONCENTRACIYA", "TINY по решению владельца", "KITY_PAKET_RESHENIYA_300"),
    ("ETS2S", "Элдер шорт", "FAIL_POVTOR", "NET_SIGNALA", "только в разрешённом режиме Brain", "ETS2S_POVTOR_ITOG"),
    ("DELIST_FORCED", "шорт на принудительном делистинге", "FAIL", "NET_SIGNALA", "защита шортов — гипотеза", "DELIST_FORCED_ITOG"),
    ("ATT1_PROBOY_VPERED", "шорт на пробое наклонной (тень вперёд 09–10.2026)", "NEGATIVE", "NET_SIGNALA",
     "ни в одном режиме/срезе зрения вклад сигнала не > 0; следующий механизм — ATT1_RETEST: вход на возврате к пробитой линии (ручной стиль владельца)",
     "results/att1_karta_brain_*.json"),
    ("RETEST_SLOPED_H1", "ретест пробитой наклонной, H1 (V1 + вариант значимого пробоя)", "KILL", "IZDERZHKI",
     "V1: вклад +0.02R (t 0.6), издержки 0.18R при стопе ≈ 1 ATR; V2 (значимый пробой): ХУЖЕ случайного −0.13R (t −1.9) → зеркальная гипотеза «провал значимого пробоя» — только prereg и вперёд; H1 со стопом ≈ 1 % съедается издержками",
     "results/retest_sloped*_20261027*.json"),
    ("DUMP_OTSKOK_H1", "лонг отскока после дампа ≥ 8 % за 24 ч (зеркало PUMP4)", "KILL", "NET_SIGNALA",
     "V1: вклад +0.06R (t 0.18) на падающем рынке; V2 вне BEAR: вклад −0.005R → асимметрия: пампы альтов перегреваются, дампы — нет", "results/dump_otskok*_20261028*.json"),
    ("PUMP4_FILTR_ROST24", "PUMP4 только на настоящем пампе (рост ≥ 6 % за 24 ч)", "HISTORY_AGAINST", "REZHIM", "2025: отфильтрованные +0.02R хуже остальных +0.095R — подгонка под 09–10.2026; вперёд дособирается по prereg", "ISTORIYA_2025_ITOG"),
    ("PUMP4_V1_2025", "PUMP4 V1 на 9 мес 2025", "PODTVERZHDEN", None, "+0.067R, t 2.4, 6/9 мес; кандидат V1.1 пауза в BULL_TREND (7/9 мес)", "ISTORIYA_2025_ITOG"),
    ("SHORT_HVOST_2025", "реконструкция SHORT_HVOST на 2025 (V1 + перегрев)", "NE_REGULYAREN", "KONCENTRACIYA", "режимный плюс 2026; левый хвост сквизов; только TINY после PASS", "ISTORIYA_2025_ITOG"),
    ("POLY_95", "купить сторону, дошедшую до 0.95 у нас на глазах", "VPERED", None, "судья fabrika/poly_95_sudya.py, вердикт с 150 сделок", "PREREG_POLY_95_VPERED"),
    ("FLET_SETKA_H1", "сетка с усреднением во флэте (V1 + по тренду 30 дн)", "KILL", "IZDERZHKI",
     "2026: ≈ случайному; 2025 (137 монет, 9 мес): V1 −0.19 %, 0/9 мес; V2 по тренду −0.23 %, 2/9 мес — выходы из флэта и издержки частей", "results/flet_setka*_2026*.json"),
    ("PUMP4_V1_1_BULL_PAUZA", "PUMP4 без сделок в BULL_TREND", "SHADOW", None,
     "2025: net +167 против +163, просадка 80 против 93, худший мес −65 против −72, 7/9 мес; 2026: просадка 44 против 89, худший мес −9 против −39; пропущено 73 сделки (47 прибыльных, в сумме −$3.7)", "ISTORIYA_2025_ITOG"),
    ("H4_TREND_2025", "H4 по тренду D1: пробой / ретест / Элдер, стоп 2 ATR, цель 3R", "KILL", "REZHIM",
     "пробой −0.02R, ретест −0.09R; Элдер +0.12R (вклад +0.17, издержки 0.08R) но t 1.4 и 4/8 мес; V2 с трендом BTC t 1.57, 4/8 мес: фев–май плюс, июн–сен минус → кандидат для карты режимов Brain, не нога", "results/h4_*_2025*.json"),
    ("SHORT_HVOST", "шорт перегретого хвоста с фандингом", "KANDIDAT", None, "вердикт на 30 событиях, вариант B", "SHORT_HVOST_VARIANT_B"),
    ("PUMP4", "шорт после пампа", "LIVE_PODGOTOVKA", None, "Codex; вклад сигнала +0.14R к случайному входу", "obyasneniya_pump4.json"),
    ("POLY_NO_PEREPLATA", "NO при переоценённом YES крипто-страйков", "NAKOPLENIE", None, "вердикт на 30 событиях", "POLY_PUT_K_LIVE"),
]

def prohod():
    zap = []
    pv = F / "PRICHINY_VERDIKTOV.json"
    if pv.exists():
        for v in json.loads(pv.read_text())["verdikty"]:
            zap.append(dict(id=v["id"], istochnik="sudya_fabriki", status=v["verdikt"], prichina=KLASS_V_PRICHINU.get(v["klass"], v["klass"]),
                            sled=v.get("sled"), okna=v.get("okna")))
    rid = {z["id"] for z in zap}
    for i, meh, stt, pr, sled, src in RUCHNYE:
        z = dict(id=i, istochnik="protokol", mehanizm=meh, status=stt, prichina=pr, sled=sled, dokument=src)
        if i in rid: zap = [x for x in zap if x["id"] != i]
        zap.append(z)
    for nm in ("vpered", "vpered_v2"):
        s = F / nm / "svodka.json"
        if s.exists():
            x = json.loads(s.read_text())
            zap.append(dict(id=f"FABRIKA_{nm.upper()}", istochnik="fabrika_vpered", mehanizm=f"каталог {x['katalog']} гипотез на новых днях",
                            status="NAKOPLENIE" if x["dney"] < x["min_dney"] else f"KANDIDATOV {x['kandidatov']}", prichina=None,
                            sled=f"вердикт с {x['min_dney']} дней, сейчас {x['dney']}"))
    cnt = collections.Counter(z["prichina"] for z in zap if z.get("prichina"))
    uroki = ("Уроки прошлых провалов (не повторяй): " + "; ".join(f"{PRICHINY.get(k, k)} — {n}" for k, n in cnt.most_common(5)) +
             ". Нужна причина, кто ВЫНУЖДЕН торговать, и чем сигнал лучше случайного входа после издержек; не прячь ставку на направление рынка.")[:450]
    (F / "uroki_dlya_ii.txt").write_text(uroki)
    (F / "REESTR_GIPOTEZ.json").write_text(json.dumps(dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), vsego=len(zap),
        prichiny_slovar=PRICHINY, prichiny_schet=dict(cnt), zapisi=zap), ensure_ascii=False, indent=1))
    md = ["# Реестр гипотез с памятью провалов (автоматически, `fabrika/reestr_gipotez.py`)", "", f"Всего {len(zap)}. Причины провалов: " +
          ", ".join(f"{k} {n}" for k, n in cnt.most_common()), "", "Уроки для генератора идей: " + uroki, "",
          "| id | статус | причина | следующий ход |", "|---|---|---|---|"]
    for z in sorted(zap, key=lambda z: (z["istochnik"] != "protokol", z["id"])):
        md.append(f'| {z["id"]} | {z["status"]} | {PRICHINY.get(z.get("prichina"), z.get("prichina") or "—")} | {(z.get("sled") or "—")[:90]} |')
    (F / "REESTR_GIPOTEZ.md").write_text("\n".join(md) + "\n")
    return dict(vsego=len(zap), prichiny=dict(cnt.most_common(5)))

if __name__ == "__main__":
    print(prohod()); print((F / "uroki_dlya_ii.txt").read_text())
