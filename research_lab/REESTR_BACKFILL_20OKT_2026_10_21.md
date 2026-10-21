# Реестр Factory: исследования 20.10 внесены задним числом (21.10.2026, Claude research)

Что не изменилось: история реестра не переписана (журнал только дописан); PUMP4 V1, Monthly, KITY_M3-тень, Brain — без изменений;
окно KRIPTO_FWD_2026Q4 не тронуто. Скрипт `factory_v3/backfill_20okt.py` (идемпотентен, проверен на копии реестра).
Каждая запись: nasledie (статус + prereg@git → документ) и kvitanciya RETRO_20OKT (sha256 документа, prereg sha256/git, окно,
результат, статус, следующий шаг, пометка «зарегистрировано задним числом 21.10.2026»).

Новые семьи: PUMP_FADE, INPLAY, NAKLONNYE_UROVNI, KORPUS_SKAN (все ACTIVE — закрыты версии, не идеи).

| гипотеза | семья | статус в реестре | итог | следующий шаг |
|---|---|---|---|---|
| PUMP4_V1 | PUMP_FADE | SHADOW | PASS: 66 закрытых, эдж +0.159R, t 2.74, монет в плюсе 33/50 | Codex: исполнитель → TINY по GO |
| PUMP4_V2_TOPLIVO | PUMP_FADE | KILL | FAIL: фильтры топлива не улучшают | — |
| PUMP4_V2_KONTEKST2 | PUMP_FADE | KILL | FAIL: |z| < 0.5 | — |
| PUMP4_OI_DINAMIKA | PUMP_FADE | KILL | FAIL: −1.36 п.п., z −0.41 | — |
| PUMP4_V2_VYHOD | PUMP_FADE | SHADOW | UNKNOWN: пары копятся | ≤ 200 пар / 31.03.2027 |
| INPLAY_MEHANIZM_15M | INPLAY | KILL | FAIL: M1 −13.8 п.п. | InPlay-H4 — кандидат в активную гипотезу |
| INPLAY_RODNAYA_V3 / V4 | INPLAY | KILL | FAIL: эдж −0.018R / −0.058R | то же |
| PROBOY_30D_V1 | BREAKOUT | KILL | FAIL: z −0.79 | — |
| KASANIE_H4_V1 | BOUNCE | KILL | FAIL: −2.35 п.п., z −15.9 | LIQ_OTSKOK_4H_V2 — кандидат |
| NAKLONKI_KASANIE_V1 | NAKLONNYE_UROVNI | KILL | FAIL: касание −1.13 п.п. | пробой — ниже |
| SLOPE_BREAKDOWN_SHORT_V1 | NAKLONNYE_UROVNI | SHADOW | INCONCLUSIVE: OOS +0.045R, σ 1.63 | forward + хедж BTC с 21.10, 150 пар |
| OOS_H1_KANDIDATY | KORPUS_SKAN | KILL | FAIL: 3/3 | список на архив владельцу |
| SKAN_M15_V1 | KORPUS_SKAN | SCREEN | FAIL на DEV (этап 1 — 4 стратегии) | breakdown_retest_v3 на 20 длинных монетах |
| KITY_SPOKOYNYY_ABS_VOL | KITY | KILL (версия) | BLOCKED_DATA: 7 спокойных недель | KITY_M3 тень идёт; относительная норма vol — отдельно |
| ALPACA_H6_TREYL | ALPACA | SHADOW | UNKNOWN: forward копится | вердикт на 120 когортах |
| KITY_M3_BYBIT_TEN (квитанция DANNYE) | KITY | SHADOW | PASS: Binance D1 паритет 10/10 | держать хук |

XS-моментум (MOM30_XS, IMP7_XS) уже шёл через реестр 20.10 — не дублировался.
Итог реестра после внесения: гипотез KILL 40, SHADOW 10, SCREEN 6, NEW 6.
