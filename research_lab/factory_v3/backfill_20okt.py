#!/usr/bin/env python3
"""backfill_20okt.py — внесение исследований 20.10.2026 в реестр Factory задним числом (PM 20.10, срок 22.10).
Историю не переписывает: только новые семьи/гипотезы + nasledie (статус с документом) + kvitanciya (sha256 документа).
Каждая запись помечена «зарегистрировано задним числом 21.10.2026». Повторный запуск: уже внесённое пропускается.
    python3 research_lab/factory_v3/backfill_20okt.py [--suhoy <путь к копии реестра>]"""
import hashlib, json, subprocess, sys
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "factory_v3"))
import reestr_v1 as R
POM = "зарегистрировано задним числом 21.10.2026 (исследование 20.10)"

def sha(p): return hashlib.sha256((LAB / p).read_bytes()).hexdigest()
def git(p):
    r = subprocess.run(["git", "log", "-1", "--format=%h", "--", str(LAB / p)], cwd=LAB, capture_output=True, text=True)
    return r.stdout.strip() or None

SEMI = {"PUMP_FADE": "фейд пампа после разгона монеты (PUMP4)", "INPLAY": "ретест пробоя в игре (InPlay)",
        "NAKLONNYE_UROVNI": "наклонные линии поддержки/сопротивления: касание и пробой",
        "KORPUS_SKAN": "сквозной скан корпуса стратегий бота на истории"}
# (гипотеза, семья, механизм, статус, prereg, документ-результат, окно, результат, статус_исследования, следующий шаг)
G = [
 ("PUMP4_V1", "PUMP_FADE", "фейд после пампа: шорт по PumpFadeV4R H1, стоп x4, tp1 40%/tp2 60%, удержание 168",
  "SHADOW", "prereg/PREREG_PUMP4_PLATO_2026_08_31.md", "results/pump4_pereschet_20261020.json",
  "проспективная тень 31.08–20.10.2026 (завершённые удержания)", "66 закрытых, +0.159R к случайному входу, t 2.74 → PODTVERZHDENA",
  "PASS", "Codex: исполнитель по контракту PUMP4_V1_EXECUTION_CONTRACT_V1 → fixtures 65/65 → TINY по GO владельца"),
 ("PUMP4_V2_TOPLIVO", "PUMP_FADE", "фильтры топлива пампа (объём, фандинг, разгон) поверх V1",
  "KILL", "prereg/PREREG_PUMP4_V2_TOPLIVO_ZAMERY_2026_10_20.md", "results/pump4_v2_zamery_20261020.json",
  "события пампов 2023–2026 (2756)", "ни один фильтр не улучшает долю (F1 −4.4 п.п. z −1.9), по годам знак скачет",
  "FAIL", "V1 без фильтров; новых фильтров на этой истории не перебирать"),
 ("PUMP4_V2_KONTEKST2", "PUMP_FADE", "контекст рынка (BTC-режим, ширина) поверх V1",
  "KILL", "prereg/PREREG_PUMP4_V2_KONTEKST2_2026_10_20.md", "results/pump4_v2_kontekst2_20261020.json",
  "события пампов 2023–2026 (2756)", "G1 −0.8 п.п., G2 −0.95 п.п., |z| < 0.5", "FAIL", "закрыто"),
 ("PUMP4_OI_DINAMIKA", "PUMP_FADE", "динамика открытого интереса во время пампа как фильтр V1",
  "KILL", "prereg/PREREG_PUMP4_OI_DINAMIKA_2026_10_20.md", "results/pump4_oi_20261020.json",
  "события пампов 2023–2026, покрытие OI 100%", "рост OI vs падение −1.36 п.п., z −0.41", "FAIL", "закрыто"),
 ("PUMP4_V2_VYHOD", "PUMP_FADE", "выход V2: вторая цель 0.9R вместо исходной — парная forward-оценка против V1",
  "SHADOW", "prereg/PREREG_PUMP4_V2_VYHOD_2026_10_20.md", "results/pump4_v1_v2_analitika_20261020.json",
  "forward с 20.10.2026, до 200 пар или 31.03.2027", "ещё нет пар", "UNKNOWN", "копить пары; низкий приоритет; V1 не трогать"),
 ("INPLAY_MEHANIZM_15M", "INPLAY", "механизм InPlay на 15m: доходит ли цена до цели после ретеста против контроля",
  "KILL", "prereg/PREREG_INPLAY_MEHANIZM_ZAMERY_2026_10_20.md", "results/inplay_zamery_20261020.json",
  "15m 2023–2026, 133 монеты", "M1 −13.8 п.п. к контролю; стоп внутри шума", "FAIL",
  "одна гипотеза InPlay-H4 (старший ТФ, стоп за зоной закола) — по выбору владельца/PM"),
 ("INPLAY_RODNAYA_V3", "INPLAY", "родная геометрия inplay_retest_v3, R от сигнального риска",
  "KILL", "prereg/PREREG_INPLAY_RODNAYA_GEOMETRIYA_2026_10_20.md", "results/inplay_rodnaya_inplay_retest_v3.json",
  "история 2023–2026", "эдж к случайному −0.018R (σ −1.28) и −0.002R", "FAIL", "см. InPlay-H4"),
 ("INPLAY_RODNAYA_V4", "INPLAY", "родная геометрия inplay_retest_v4, R от сигнального риска",
  "KILL", "prereg/PREREG_INPLAY_RODNAYA_GEOMETRIYA_2026_10_20.md", "results/inplay_rodnaya_inplay_retest_v4.json",
  "история 2023–2026", "эдж −0.058R (σ −1.09) и −0.042R; монет в плюсе 20/61", "FAIL", "см. InPlay-H4"),
 ("PROBOY_30D_V1", "BREAKOUT", "пробой 30-дневного максимума: продолжение против гонки разорения",
  "KILL", "prereg/PREREG_PROBOY_30D_ZAMER_2026_10_20.md", "results/proboy_30d_zamer_20261020.json",
  "D1 2023–2026, 2375 событий", "доля 0.492, z −0.79; с объёмом и без — без перевеса", "FAIL", "закрыто"),
 ("KASANIE_H4_V1", "BOUNCE", "отскок от горизонтального уровня H4 на 1–3 касании",
  "KILL", "prereg/PREREG_KASANIE_H4_UROVNYA_ZAMER_2026_10_20.md", "results/kasanie_h4_20261020.json",
  "H4 2023–2026, 96 808 касаний", "−2.35 п.п. к эталону, z −15.9 (хуже случайного); заколы 40%",
  "FAIL", "отскок только с причиной: LIQ_OTSKOK_4H_V2 (каскад ликвидаций)"),
 ("NAKLONKI_KASANIE_V1", "NAKLONNYE_UROVNI", "отскок от наклонной линии (касание)",
  "KILL", "prereg/PREREG_NAKLONKI_ZAMER_2026_10_20.md", "results/naklonki_20261020.json",
  "H1/H4 2023–2026, 35 398 касаний", "−1.13 п.п., z −4.6; пробой поддержки в шорт +3.8 п.п. все 4 года",
  "FAIL", "касание закрыто; пробой — SLOPE_BREAKDOWN_SHORT_V1"),
 ("SLOPE_BREAKDOWN_SHORT_V1", "NAKLONNYE_UROVNI", "пробой растущей наклонной поддержки в шорт (+ хедж BTC)",
  "SHADOW", "prereg/PREREG_SLOPE_BREAKDOWN_HEDGE_VPERED_2026_10_20.md", "results/slope_breakdown_oos_20261020.json",
  "OOS 2026 (prereg SLOPE_BREAKDOWN_SHORT_OOS) + forward с 21.10.2026, 150 пар",
  "OOS: +0.045R к контролю, σ 1.63 (порог не взят)", "INCONCLUSIVE",
  "forward-тень с хеджем BTC (β 30 дн в [0.3, 2]); улучшения отрисовки — только на новых данных"),
 ("OOS_H1_KANDIDATY", "KORPUS_SKAN", "3 H1-кандидата корпуса на OOS 07–10.2026",
  "KILL", "prereg/PREREG_OOS_KANDIDATY_2026_07_10_2026_10_20.md", "results/oos_kandidaty_20261020.json",
  "OOS 07–10.2026", "3 из 3 OOS_FAIL", "FAIL", "H1-корпус закрыт; список на архив — владельцу"),
 ("SKAN_M15_V1", "KORPUS_SKAN", "скан 15m-стратегий корпуса (частота → DEV)",
  "SCREEN", "prereg/PREREG_SKAN_M15_KORPUS_2026_10_20.md", "results/skan_m15_20261021/skan_m15_itog.json",
  "15m 2023–2026", "этап 1 прошли 4 (alt_range_scalp_v1, spike_fade_v3, elder_triple_screen_v2, inplay_retest_v3); DEV PASS 0",
  "FAIL", "breakdown_retest_v3 — перепрогон на 20 монетах с самой длинной историей; затем список на архив"),
 ("KITY_SPOKOYNYY_ABS_VOL", "KITY", "фильтр KITY: торговать только в спокойные недели по абсолютному порогу vol 0.427",
  "KILL", "prereg/PREREG_KITY_SPOKOYNYY_2021_2022_2026_10_20.md", "results/kity_spokoynyy_2021_2022_20261020.json",
  "Binance D1 2021H2–2022, 57 недель", "спокойных недель 7 (−58.6 bps), все недели +74 bps t 1.18 — данных мало (BLOCKED_DATA)",
  "BLOCKED_DATA", "закрыта только версия с абсолютным порогом; KITY_M3 тень идёт; относительная норма vol — отдельная гипотеза вперёд"),
 ("ALPACA_H6_TREYL", "ALPACA", "ширина трейлинга Monthly: 6 рук (A35…BEZ_TREYLA) forward",
  "SHADOW", "prereg/PREREG_ALPACA_H6_TREYL_UTECHKA_I_FORWARD_2026_10_19.md", "ALPACA_H6_UTECHKA_ITOG_2026_10_19.md",
  "история (утечка) + forward с 19.10.2026", "утечка = ширина трейла + невзведённые; forward копится",
  "UNKNOWN", "вердикт на 120 когортах; Monthly не менять"),
]
KVIT_EXTRA = [("KITY_M3_BYBIT_TEN", "DANNYE", "PASS", "PM_20OCT_RECEIPTS_2026_10_20.md",
               {"chto": "Binance D1 продолжение после архива (fabrika/binance_d1_vpered.py)", "okno": "с 01.10.2026",
                "rezultat": "паритет 10/10 = 0.0; 6 669 дневок дописано; свежесть в nepreryvnost.py",
                "sleduyushchiy_shag": "держать хук; меню ИИ — новое forward-окно отдельным решением PM"})]

def main():
    put = sys.argv[sys.argv.index("--suhoy") + 1] if "--suhoy" in sys.argv else None
    r = R.Reestr(put=put) if put else R.Reestr(); S = r.sostoyanie(); log = []
    for s, op in SEMI.items():
        if s not in S["semi"]: r.semya(s, op, istochnik=POM); log.append(f"семья {s}")
    for gid, sm, meh, st, pre, doc, okno, rez, sti, nxt in G:
        S = r.sostoyanie()
        if gid not in S["gipotezy"]:
            r.gipoteza(gid, sm, meh, ["bybit_h1/m15/d1", "binance_d1"], otlichie=f"{POM}; prereg {pre}")
            r.nasledie(gid, st, f"{pre}@{git(pre)} → {doc}")
            log.append(f"гипотеза {gid} → {st}")
        if not any(k["sha256"] == sha(doc) for k in r.sostoyanie()["gipotezy"][gid].get("kvitancii", [])):
            r.kvitanciya(gid, "RETRO_20OKT", sti, doc, sha(doc),
                         {"prereg": pre, "prereg_sha256": sha(pre), "prereg_git": git(pre), "okno": okno,
                          "rezultat": rez, "status": sti, "sleduyushchiy_shag": nxt, "pometka": POM})
            log.append(f"квитанция {gid} {sti}")
    for gid, vid, sti, doc, det in KVIT_EXTRA:
        if not any(k["sha256"] == sha(doc) and k["vid"] == vid for k in r.sostoyanie()["gipotezy"][gid].get("kvitancii", [])):
            r.kvitanciya(gid, vid, sti, doc, sha(doc), det | {"pometka": POM}); log.append(f"квитанция {gid} {vid}")
    print("\n".join(log) or "всё уже внесено")

if __name__ == "__main__":
    main()
