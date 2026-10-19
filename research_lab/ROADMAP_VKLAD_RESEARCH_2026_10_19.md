# Вклад Research Lane в канонический ROADMAP_SELF_IMPROVING.md (19.10.2026)

Это не новый roadmap. Это готовые строки Research Lane для вставки в единственный канонический файл
`bybit-bot-recovery-20260824/ROADMAP_SELF_IMPROVING.md` (последняя версия 4ea7d61, 24.08).
Вставляет файл Codex — по той же схеме, что и доску (4129fed): одна ручка на файл, research-строки
переносятся дословно со ссылкой на SHA этого коммита. Execution-строки Claude не пишет.

Копия `bybit-bot-clean-v28/ROADMAP_SELF_IMPROVING.md` (апрельская, 9812b07) — **OBSOLETE**, не редактируется.

## Кто что обновляет
| что | кто держит ручку | как |
|---|---|---|
| файл ROADMAP_SELF_IMPROVING.md (структура, фазы, changelog) | Codex | коммит в recovery-ветку |
| строки Research Lane (статусы, evidence, блокеры, acceptance) | Claude | этот документ в research/fabrika-v1 → Codex переносит дословно |
| строки Money Lane / execution / runtime | Codex | сам |
| RESEARCH_TO_LIVE_BOARD.md | Codex (единый источник с 18.10) | research-статусы — только из опубликованных research-коммитов |
| приоритеты, разрешения, GO | PM / владелец | Claude и Codex их не меняют |
Правило: если статус в roadmap расходится с доской или паспортом стратегии — побеждает опубликованный receipt,
расхождение пишется в changelog, а не правится молча.

## Строки Research Lane
Статусы: IMPLEMENTED = код + тест + актуальный runtime evidence; иначе PARTIAL.

| компонент | ORIGINAL GOAL | CURRENT STATUS | ответственный | код | тест | runtime evidence | blocker | следующий acceptance criterion |
|---|---|---|---|---|---|---|---|---|
| Ворота исполнимости V2.2 | не принимать неисполнимые сигналы | **IMPLEMENTED** (по умолчанию в очереди) | Claude | `fabrika/ispolnimost_v22.py`, `ispolnimost_v21.py` | `fabrika/test_ispolnimost_v21.py`, samoproverka `fabrika.py` | `results/fabrika_v2_2_integ_20261019/integ_verdikty.jsonl` (3a349a3) | издержки FX/золота — из демо-атласа FxPro, своп не моделируется | сверка спредов демо против боевого счёта, если появится доступ |
| Денежный судья | edge против контроля ≠ деньги | **IMPLEMENTED** | Claude | `fabrika/sudya_dengi.py`, `fabrika.py` (LEAD_NO_MONEY / CONFIRMED_NO_MONEY) | samoproverka: 6 кейсов PASS | там же: NOCHNOY_DREYF FX → LEAD_NO_MONEY | — | — |
| Демон каталога механизмов | непрерывная самостоятельная проверка | **PARTIAL**: код есть; runtime — простаивает с 01.10 | Claude (код), владелец (ручной screen) | `fabrika/fabrika.py --demon` | samoproverka PASS | последний вердикт 2026-10-01 | нет автозапуска на Mac (правило); каталог на старых окнах исчерпан | неделя проходов без `PROPUSK_PROHODA` в `nepreryvnost` + ≥ 1 новая заявка обработана до вердикта без участия человека |
| ИИ-предлагатель формул + автоматический prereg | ИИ генерирует → prereg → проверка → вердикт | **PARTIAL** | Claude | `factory_v3/ai_formula_v1.py`, `fabrika/ai_formula_cikl.py`, `factory_v3/ai_raund.py --formula` | `test_ai_formula_v1` 12 PASS, `test_ai_raund` PASS, factory_v3 115 PASS | 2 вердикта (KILL), автоматический prereg 19da42e; журнал `data/factory_v3/ai_formula_zhurnal.jsonl` | (1) обе формулы составил Claude в роли генератора, не Ollama; (2) хук в сторожах ещё не наблюдался в `storozh.log`; (3) автор предлагателя и автор судьи — один (Claude) | (a) строка `хук ai_formula_cikl` в `data/storozh/storozh.log`; (b) одно предложение Ollama обработано до вердикта; (c) независимый review `ferma_shablony.xs_nedelya_binance` + `reestr_v1` (Codex или отдельный агент) |
| Бюджет экспериментов | переобучение через перебор | **PARTIAL** | Claude | `factory_v3/reestr_v1.py` (t_req = Φ⁻¹(1−α/2k), бюджеты окон), дедупликация формул по каноническому виду | `test_reestr_v1` PASS | `data/factory_v3/reestr_v1.jsonl` (append-only) | каждая формула = попытка в k (перебор комбинаций повышает порог), но контроль ведёт тот же автор; окно `KRIPTO_D1_2023_2026Q3` 20/20, `KRIPTO_D1_2021H2_2022` 12/20 | независимая сверка реестра против журнала прогонов (число k = число реально прогнанных формул) |
| Паспорта стратегий | одна правда о статусе стратегии | **IMPLEMENTED** (research-часть) | Claude | `factory_v3` + `harvest_passports.py` | `test_pasport` PASS | сверка доски 4129fed (без конфликтов статусов) | — | — |
| Brain: режимы | помогать всем стратегиям | **PARTIAL**: метки есть, денег не добавляют | Claude | `fabrika/brain_rezhimy.py`, `begun_meh_sdelki.py` | тест обрезки (причинность) | `results/brain_rezhimy_20261018/` (a2b64a2): лучше момент входа, MONEY_PASS 0 | — | — |
| Brain: портфельная ценность | распределение лучше фиксированного | **BLOCKED_ECONOMICS** | Claude | — | — | — | экономически подтверждённый рукав один (Monthly); распределять нечего | ≥ 2 подтверждённых независимых рукава → A/B против равных весов |
| BIL/SGOV для свободного капитала | работа свободных денег без рисков SPY | **MISSING** (данные есть) | Claude | будет `alpaca_bil_sgov.py` | — | данные: `data/alpaca_bil_sgov_20261019/` (Codex 92dd3f2, QA PASS) | — | prereg закоммичен до чтения доходностей; вердикт по правилу prereg; формулировка без «безрисковый» |
| Polymarket | отдельный рынок со своей экономикой | **PARTIAL** | Claude (стенд), Codex (данные) | `polymarket/polymarket_stend.py` (766b043) | тесты стенда PASS | пилот 40 рынков / 20 752 точки, NOT_SCREEN_READY | полный реестр рынков и история не выгружены; исторические издержки | полный census → проверка изоляции будущего на всём реестре → затем prereg экрана |
| Умный отбор акций (SEC Form 4, AI ranking, стабильность рейтинга) | лучше выбирать внутри Monthly | **MISSING** | Claude (гипотезы), Codex (SEC после Money Lane) | — | — | Monthly SELECTION_PASS против случайных (a212281 / 2f10c5a) | SEC: данные; AI ranking: Ollama «знает» историю известных акций → исторический тест невалиден, только forward-тень | ≤ 3 гипотезы одним prereg с общей поправкой; сравнение с Monthly, momentum, random-within-setup, SPY при одинаковых издержках |
| Золото / FX | искать и там | **FAIL** на каталоге (0 MONEY_PASS) | Claude | `fabrika/mehanizmy.py`, `begun_h1.py` | samoproverka | `ITOG_FABRIKA_VOROTA_V2_1_V2_2_2026_10_18.md` | ценовые механизмы на H1 съедаются спредом | новые данные CFTC COT (позиционирование) — независимый от цены источник |

## Активные задачи Claude (P0 + один P1)
- P0: не трогать live (NET/SHOP, разрешения, защиту, production managers). Из research — ничего в execution.
- P1 (один): BIL/SGOV overlay — prereg, затем вердикт.
Остальное — очередь, не в работе одновременно.

## Сознательно отложено
- SEC Form 4 и AI ranking — до поставки данных и Money Lane P0 Codex.
- Brain-аллокатор — BLOCKED_ECONOMICS, пока один подтверждённый рукав.
- Новые ИИ-формулы на окнах D1 — бюджет почти исчерпан; следующие только на `KRIPTO_H1M5` или новых данных.
- Polymarket-экран — до полного census.
- Перезапуск демона каталога — решение владельца/PM; без новых заявок он ничего не даст.

## Соответствие доске
Строки выше не меняют ни одного research-статуса доски 18.10: ATT1 ECONOMIC_FAIL, KITY INCONCLUSIVE,
Weekly/EventReselection ECONOMIC_FAIL, Monthly — основной кандидат, Brain A/B INCONCLUSIVE.
Новые строки (V2.2, денежный судья, ИИ-цикл, BIL/SGOV) на доске ещё отсутствуют — их добавляет Codex при переносе.
