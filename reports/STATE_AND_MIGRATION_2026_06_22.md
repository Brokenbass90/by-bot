# Состояние проекта + миграция в новый чат (2026-06-22)

Чистая точка передачи для продолжения в новом чате. Читать первым вместе с `CODEX_HANDOFF_2026_06_20.md` и `PROJECT_MAP.md`. Старые заголовки про «+89%/+120%» — НЕ текущее доказательство.

## 1. Текущее live-состояние (по проверке Codex 06-20)
- `bybot.service` активен, `trade_on=true`, `dry_run=false`, открытых позиций 0, режим `bear_chop`.
- Живой риск: `flat_resistance_fade=0.30x`, legacy Range short-only `0.25x`. ATT1/bounce/breakdown/IVB1/midterm — scan/shadow, risk 0. Elder/ASB1-slope/HZBO1 — выключены.
- Живые данные: 40 закрытых сделок, ≈ **−3.81 USDT**, PF `0.517`. **Доказанного эджа для масштаба нет.**
- Тесты: полный прогон зелёный (**409 локально у меня / 410 у Codex**).

## 2. Что сделал Codex за 5 дней (коротко)
- ARS1 ADX → Wilder-сглаживание + перепрогон 64-матрицы в очереди на сервере (screen `ars1_wilder_recheck_20260620`).
- Promotion gate добавлен, **но не fail-closed** (CLI выходит 0 даже при `promotion_passed=false`) — чинить.
- Паритет свечей: live `fetch_klines()` отдаёт НЕЗАКРЫТУЮ свечу; `_IVB1Store`/`_ElderStore` берут `rows[-1]` напрямую → live ≠ research. Есть `live_kline_utils.fetch_closed_klines` — вшить в адаптеры перед любым ненулевым риском.
- Снапшот: `d035dbb separate effective runtime` — мой прежний флаг «снапшот≠live» частично закрыт.
- Прочее: per-symbol ликвидации, range-regime gating, блок повторных входов range после убытков, старт adaptive paper-драйвера.
- ARS1 (r004, ADX off): 108 сделок, +16.61%, PF 1.682, DD 6.68% — но **провал по месяцам (окт/ноя 2025 красные)**; в стеке PF падает 1.68→1.46.

## 3. Мои изменения — статус в git (ВАЖНО для переезда)
**Уже в дереве/закоммичено (цело, проверено):**
- `strategies/inplay_retest_v3.py` — закалка `max_entry_dist_atr` на месте.
- `strategies/alpaca_adaptive_v1.py` — `soft_regime` + `trailing_exit` + `lively_config` на месте.
- `web/activity_feed.py` — отслеживается (Codex уточнил докстринг — ок).

**НЕ добавлены в git (untracked, только на диске — легко потерять!):**
```
strategies/breakdown_retest_v3.py
strategies/spike_fade_v3.py
backtest/hedge_pairing.py
tests/test_breakdown_retest_v3.py
tests/test_spike_fade_v3.py
tests/test_hedge_pairing.py
tests/test_proof_of_life_digest.py
reports/STRATEGY_AUDIT_AND_TAXONOMY_2026_06_17.md
reports/STRATEGY_ROSTER_REVIEW_2026_06_17.md
reports/REVIEW_CODEX_AND_UNIFICATION_2026_06_17.md
reports/SYNC_ALPACA_AND_IDEAS_2026_06_17.md
reports/CODEX_HANDOFF_2026_06_17.md
reports/UNFREEZE_AND_V3_PLAN_2026_06_17.md
reports/IVB1_INPLAY_LOGIC_REVIEW_2026_06_16.md
reports/STATE_AND_MIGRATION_2026_06_22.md  (этот файл)
```
**Изменён, но не закоммичен:** `scripts/proof_of_life.py` (русификация PULSE + `--daily` дайджест) — функции на диске, тест `test_proof_of_life_digest.py` проходит.

Команда для Codex (Codex просил «stage only explicit paths, никогда `git add .`»):
```
git add strategies/breakdown_retest_v3.py strategies/spike_fade_v3.py backtest/hedge_pairing.py \
  tests/test_breakdown_retest_v3.py tests/test_spike_fade_v3.py tests/test_hedge_pairing.py \
  tests/test_proof_of_life_digest.py scripts/proof_of_life.py reports/STATE_AND_MIGRATION_2026_06_22.md
```
(остальные `reports/*.md` — по желанию). **До коммита эти файлы существуют только локально.**

## 4. Стратегии, готовые к прогону (список «на тесты»)
1. **`inplay_retest_v3`** (ретест уровня, закалён entry-cap) — autoresearch sweep → `monthly_analysis` → `hedge_pairing` с range → gate → canary. Перед live: closed-candle адаптер.
2. **`breakdown_retest_v3`** (слом поддержки, 5 тестов) — sweep на медвежьих/флэт окнах; **хедж красных месяцев range**. Перед live: closed-candle адаптер.
3. **`spike_fade_v3`** (пампы/дампы у уровней, 5 тестов) — sweep; памп в сопротивление→шорт, дамп в поддержку→лонг. Только у реальных уровней. Добавочная частота, не фундамент.
4. **`alpaca_adaptive_v1` + `lively_config()`** — bakeoff A/B: baseline vs lively vs soft-only vs trailing-only; критерий — частота/доходность чуть выше, **просадка не растёт выше ~3%**. + прогон по бычьим годам (годовой зарабатывающей цифры пока нет).
5. **`backtest/hedge_pairing`** — `hedge_report(range_stream, breakdown_stream)` и `(range_stream, elder_stream)`: цель `improved=True`, красные месяцы range закрыты.

Семейство v3 теперь полное: ретест (лонг/шорт у уровня) + слом (шорт) + памп/дамп (фейд у уровня). Все на одной level-машине (`bot.chart_geometry`), anti-lookahead, единый контракт TradeSignal. Это и есть «классика, переписанная правильно» — но **доказательства эджа ещё нет**, поэтому всё через gate перед деньгами.

## 4b. Аналитика: что сделал Codex за 5 дней (45 коммитов)
**Сильное (оставляем, это хорошая основа):**
- **Maker-входы ВШИТЫ** в монолит (`post_only_price` + `timeInForce=PostOnly`, `af9fdba`) — моя идея #1 закрыта Codex. Возврат комиссий на входах у уровня.
- **Закрытые свечи** заведены в live-адаптеры (`69b58d2`, `_fetch_closed_klines` в монолите + att1/asm1) — убирает рассинхрон live vs research.
- **adaptive_v1 поехал на пейпере** (`b1867d7`, `scripts/alpaca_adaptive_paper.py`) + защита позиций от intraday-очистки (`22e6ed8`).
- **Гора live-safety**: fail-closed при недоступности позиций, prune завершённых сделок, рестарт только при flat-счёте, явный live-truth в контексте оператора.
- **range обезопашен**: short-only канарейка (`539129b`), regime-gate (`88d8d1a`), блок повторных входов после убытков (`93a7fba`).
- **Снапшот**: `d035dbb separate effective runtime` — мой флаг «снапшот≠live» частично закрыт.

**Риски/долги (требуют внимания нового чата):**
- **Promotion gate НЕ fail-closed**: CLI выходит `0` даже при `promotion_passed=false` — авто-промоушен опасен, чинить в первую очередь.
- **range всё ещё краснеет** (окт/ноя 2025), ADX перепрогон в очереди — без хеджа не масштабировать.
- **IVB1/Elder-сторы** по словам Codex ещё берут `rows[-1]` напрямую — проверить, что closed-candle покрывает и их.
- **Моё v3-семейство Codex НЕ подхватил** (untracked) → ни в одном sweep. Нужно git add + поставить в очередь autoresearch.
- Эджа в live по-прежнему нет (40 сделок, −3.81 USDT, PF 0.517).

## 5. Открытые риски/долги (для нового чата)
- Promotion gate **не fail-closed** — приоритет, иначе авто-промоушен опасен.
- Паритет свечей: вшить `fetch_closed_klines` в IVB1/Elder/ARS1 **и** в v3-стратегии (они тоже берут текущий бар).
- range краснеет в окт/ноя 2025 → без хеджа (breakdown_retest_v3 / Elder) масштабировать нельзя.
- Единый чат веб↔ТГ: веб-лента готова; зеркалирование свободного текста ТГ в `runtime/web_ai_history.json` — за Codex (монолит).
- Русификация монолита (`pulse()`/`reports_loop()`/`_tg_reply()`) — словари в `proof_of_life.py`.

## 6. Что делать дальше (порядок)
1. **Сохранить работу:** `git add` untracked v3-семейства (§3) — иначе оно вне sweep и может потеряться.
2. **Безопасность раньше денег:** сделать promotion gate fail-closed (CLI ≠ 0 при провале); подтвердить closed-candle для IVB1/Elder.
3. **v3-семейство в autoresearch:** `inplay_retest_v3`, `breakdown_retest_v3`, `spike_fade_v3` → sweep → `monthly_analysis` → отобрать чистых (без красных медвежьих).
4. **Хедж красных месяцев range:** `hedge_pairing(range, breakdown_retest_v3)` и `(range, elder)`. Если `improved=True` → можно поднимать множитель range (путь к двузначным %).
5. **adaptive A/B:** baseline vs `lively_config` на bakeoff + прогон по бычьим годам (получить наконец годовую зарабатывающую цифру).
6. **Затем:** Elder-редизайн (4h+1/день), консолидация-культя дублей (87→~12), русификация монолита, единый чат шаг-2.

**Честный итог:** инфраструктура за 5 дней стала заметно крепче (maker, closed-candle, safety, adaptive paper), но **доказанного эджа всё ещё нет** — поэтому фокус: прогнать переписанную классику (v3) через честный gate и найти связку, которая не краснеет в медведе. Деньги — только после этого.
