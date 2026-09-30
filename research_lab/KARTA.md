# KARTA — одна живая карта проекта

Единственный файл состояния. Обновляется на месте; история — в git.
Не отчёт и не план: только SLEEVE → STATUS → EVIDENCE → GATE → NEXT → OWNER.
Прогресс = смена статуса на PASS / FAIL / KILLED / READY / LIVE, а не новые файлы.
Обновлено: 2026-09-30, Claude. Строки Codex — по его хендоффу, Claude их не проверял.

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
| Золото/FX глубина | 6 ре-тестов ждут приёмки | окна `gold_glub`/`fx7_glub` заморожены по частоте | `--prinyat gold_glub`, `--prinyat fx7_glub` | прогон 6 пунктов → вердикты | владелец → Claude |
| Золото/FX прочее | закрыто | 18 NEGATIVE, 6 PNC, 14 структурно LOW_N | — | не трогать | — |
| ETS2M | ждём вердикт | 1004 входа, когорта 900 заморожена | 2026-10-10 19:00 UTC | запустить evaluator, не менять | Claude |
| Тень SILA | идёт медленно | 3/100 решений | 100 решений | не выключать Mac | Claude |
| Фабрика | демон погашен, защита исправлена | самопроверка ВСЁ ПРОШЛО | окна объявлены + приёмка | поднять демон после приёмки | владелец |

## Живые острова вне фабрики (найдены 30.09, статус по их же файлам)

| SLEEVE | STATUS | EVIDENCE | NEXT | OWNER |
|---|---|---|---|---|
| Тень арбитража (`live_mirror/arb_roi_estimate.json`) | **отрицательная** | 500 циклов, win 27%, mean −0.07%/цикл, p25 проекция −5.6%/мес | кандидат в KILL, решает владелец | владелец |
| Тень PUMP4 (`data/ten_pump4.log`) | **мертва** | каждый проход: `Operation not permitted` (у запускающего python нет доступа к Documents) | чинить или закрыть | владелец |
| Тень ATT1 (`data/ten_ATT1.log`) | идёт | 1082 закрытых из порога 400 | свести с вердиктом Codex по ATT1 | Codex |
| Тень ETS2S | идёт | 223 прохода | статус по prereg не сведён | Claude |
| Тени фандинга dynamic / post_n42 | идут, питают SHORT_HVOST | в леджерах дубли записи исхода | не менять скрипты до вердикта | — |
| research_station (launchd) | работает | `logs/research_station_launchd.log` | противоречит правилу «без автозапуска на Mac» — решение владельца | владелец |
| xsec_v3, alpaca_adaptive shadow | идут | не сведены | свести при следующем проходе | Claude |

## DISCOVERY lane — закрыта до вердиктов по золоту/FX
Первые домены: фандинг/базис хвоста, Polymarket, малоликвидный хвост pit_daily.

## Запрещено
LIVE без владельца; размер ставки как замена edge; воскрешать NEGATIVE; менять пороги
судей; трогать контур Codex; автозапуск на Mac; массовые переносы файлов.
