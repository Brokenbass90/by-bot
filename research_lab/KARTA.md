# KARTA — одна живая карта проекта

Единственный файл состояния. Обновляется на месте; история — в git.
Не отчёт и не план: только SLEEVE → STATUS → EVIDENCE → GATE → NEXT → OWNER.
Прогресс = смена статуса на PASS / FAIL / KILLED / READY / LIVE, а не новые файлы.
Обновлено: 2026-09-30 (после прохода 08:34 UTC), Claude. Строки Codex — по его хендоффу, Claude их не проверял.

## MONEY lane (Codex)

| SLEEVE | STATUS | EVIDENCE | GATE | NEXT | OWNER |
|---|---|---|---|---|---|
| OLD ATT1 LIVE | LIVE, убыточен | 12 закрытий ≈ −1.20 USDT, паритет PASS | автомат просадки (мягкий порог) | вопрос LTC id257 (SL 0.2 при входе 0.4) | Codex |
| Alpaca | LIVE OFF, процедура готова | recovery: `reports/ALPACA_OWNER_ACTIVATION_2026_09_30.md` | frozen rules дают вход + все guards PASS | Sep30 selection → broker truth → OLD→NEW | Codex → владелец |
| NEW ATT1 | binding готов, canary_ready=false | 0 проспективных терминалов | 2–3 чистых заполненных терминала | ждать рынок, без нового кода | Codex |

## EVIDENCE lane (Claude)

| SLEEVE | STATUS | EVIDENCE | GATE | NEXT | OWNER |
|---|---|---|---|---|---|
| SHORT_HVOST_FANDING | PREREG, ждём | поиск: 60 событий, t=2.64 после штрафа 30 bps; будущие: 0/30 | `fanding_hvost.py`: n≥30, t≥2, медиана>0, монета≤50% | тени фандинга должны работать; ~конец октября | Claude |
| C8 PEREGREV_HVOSTA (дневной) | PREREG, ждём | история: 618 соб., сырой +315 bps, t 2.37; будущие: 0/30 | `discovery_paket1.py C8V` после `dannye_pit_kripto.py --vse --obnovit` | обновлять данные раз в месяц; ~конец декабря | владелец → Claude |
| Золото/FX | **ЗАКРЫТ** 2026-09-30 | 53 пункта = 47 исходных + 6 ре-тестов: 24 NEGATIVE (18 + 6 ре-тестов), 6 PNC, 20 LOW_N (14 структурно + 6 исходных, чьи ре-тесты NEGATIVE), 3 DEFERRED (xauusd_unchanged_replication_v1, trend_pullback, session_breakout) | — | 12 геометрических механизмов каталога на H1 золота и FX не воскрешать. Рынок вернётся только с новым экономическим механизмом и данными издержек (спреды/свопы) | — |
| ETS2M | ждём вердикт | 1004 входа, когорта 900 заморожена | 2026-10-10 19:00 UTC | запустить evaluator, не менять | Claude |
| Тень SILA | идёт медленно | 3/100 решений | 100 решений | не выключать Mac | Claude |
| Фабрика | демон погашен, защищён | самопроверка ВСЁ ПРОШЛО; очередь пуста | нужна новая предрегистрация | не поднимать до Discovery | владелец |

## Фоновые процессы на Mac (решение владельца 30.09)

Нужны замороженным экспериментам — НЕ гасить:

| процесс | как живёт | питает |
|---|---|---|
| тень фандинга dynamic | screen `research_funding_dynamic` → `scripts/run_funding_positioning_dynamic_shadow_loop.sh` | SHORT_HVOST_FANDING |
| тень фандинга post_n42 | screen `research_funding_frozen` → `scripts/run_funding_positioning_post_n42_frozen_loop.sh` | SHORT_HVOST_FANDING |
| ETS2M / ETS2S, тень ATT1, SILA | nohup-процессы `research_lab/ten.py` и `ten_sila.py` | вердикт ETS2M 10.10, SILA |

После перезагрузки Mac screen-тени фандинга поднимать вручную (станция больше не поднимает):
`screen -dmS research_funding_dynamic /bin/bash -lc scripts/run_funding_positioning_dynamic_shadow_loop.sh`
`screen -dmS research_funding_frozen /bin/bash -lc scripts/run_funding_positioning_post_n42_frozen_loop.sh`
(из корня репозитория; второй экземпляр сам откажется по замку).

| SLEEVE | STATUS | EVIDENCE | NEXT | OWNER |
|---|---|---|---|---|
| Тень арбитража (arb_ten) | **KILLED** 2026-09-30 | 500 циклов, win 27%, mean −0.07%/цикл, проекция −5.6%/мес | реализацию не исследовать и не тюнить; семейство вернётся только с новым механизмом | — |
| research_station (launchd) + project_audit (launchd, screen) | **гасится** | audit/model/sync-live — не нужны экспериментам | команды владельцу 30.09 | владелец |
| inplay_eth_prospective | гасится | evidence не обновлялось 16 дней | — | владелец |
| Тень PUMP4 | **DEFERRED** | петля падает `Operation not permitted`; сильного обоснования нет | не чинить | — |
| xsec_v3, alpaca_adaptive shadow | идут, контур Codex | XSEC_V3: 57 дн, t≈0.35 | решение Codex | Codex |
| Тень ATT1 (`data/ten_ATT1.log`) | идёт | 1082 закрытых из порога 400 | свести с вердиктом Codex по ATT1 | Codex |

## DISCOVERY lane — ОТКРЫТА 2026-09-30
Пачка 1 (DISCOVERY_PAKET1_2026_09_30.md): 12 экранов → 11 KILLED, 1 SURVIVED (C8), 3 BLOCKED_DATA.
Следующая: пачка 2 — B3 SETTLEMENT_FLOW, C5+стоп как член семейства, новые механизмы.
Правило пачек: 12–20 разных механизмов с family ID. Домены: фандинг/базис/carry, Polymarket,
ёмкостно ограниченное, кросс-рыночное. Итог — таблица candidate → rationale → data →
cheap test → KILLED/SURVIVED → reason. Подтверждающие окна не трогаются.
Ограничение: `pit_daily` и акции — только идеи и частота, статистический PASS запрещён
до приёмки датасета (выжившие / историческое членство во вселенной не закрыто).

## Запрещено
LIVE без владельца; размер ставки как замена edge; воскрешать NEGATIVE; менять пороги
судей; трогать контур Codex; автозапуск на Mac; массовые переносы файлов.
