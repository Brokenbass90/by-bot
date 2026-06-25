# Claude audit — баги, дыры, статусы (2026-06-22)

Аудит по коду (не по доке). Сверено с фактическим деревом и pytest. Точка входа
сессии: `reports/STATE_AND_MIGRATION_2026_06_22.md`. Тесты на момент аудита:
**422 passed** (было 420 + 2 новых регрессионных).

---

## 0. TL;DR
- **Исправлено + тест:** promotion-gate CLI был не fail-closed → теперь выходит
  с кодом ≠0 при провале. Регрессионный тест добавлен.
- **Коррекция доки:** closed-candle баг в **live-монолите уже закрыт** (store
  режет незакрытую свечу, есть тест). Старый `CODEX_HANDOFF_2026_06_20 §3`
  устарел — он утверждал, что не закрыт.
- **Новая находка:** контрактная нестыковка внутри v3-семейства
  (`breakdown_retest_v3` / `spike_fade_v3` доверяют переданным o/h/l/c как
  решающему бару, а `inplay_retest_v3` сам берёт последний ЗАКРЫТЫЙ). Латентный
  live-parity баг — закрыть до ненулевого риска.
- **Alpaca adaptive v1:** логика крепкая, но реального bear walk-forward нет —
  годовой зарабатывающей цифры пока нет.

---

## 1. ИСПРАВЛЕНО: fail-closed promotion gate
**Файл:** `scripts/evaluate_crypto_promotion.py` (зона Codex — прошу ревью).
**Баг:** `raise SystemExit(main())`, но `main()` возвращал `0` всегда (и в
`--json`, и в конце), независимо от `overall_pass`. Машина, читающая код выхода,
считала ПРОВАЛЕННОГО кандидата промоутабельным.
**Фикс:** оба `return 0` → `return 0 if overall_pass else 2`.
**Тест:** `tests/test_promotion_gate_fail_closed.py` (мок-загрузчики + мок-гейты,
проверяет код выхода в обе стороны). Зелёный.
**Примечание:** `backtest/promotion_gate.py` (моя зона) — чистая функция
`evaluate()->GateResult.go`, её `__main__` только печатает демо, она не была
источником бага; источник — именно CLI в scripts/.

---

## 2. КОРРЕКЦИЯ: closed-candle в live — уже закрыт
**Факт из кода/теста, а не из доки:**
- Монолит использует СВОЙ IVB1-движок (`smart_pump_reversal_bot.py:8252`), а не
  `strategies/alt_volume_spike_momentum_v1.py`.
- `_IVB1Store.fetch_klines` и `_ElderStore.fetch_klines` оборачивают
  `_fetch_closed_klines` (`smart_pump_reversal_bot.py:11860,11868`) → незакрытая
  свеча отрезается.
- Это зафиксировано тестом
  `tests/test_live_closed_candle_parity.py::test_live_range_ivb1_and_elder_use_closed_kline_adapter`
  — зелёный.

**Остаточный долг (research-parity, НЕ live-слив):** strategies/-копии всё ещё
читают `rows[-1]`/переданный бар:
- `strategies/alt_volume_spike_momentum_v1.py` — явный override последнего бара
  переданными o/h/l/c («Override current bar with passed values»). Если этот
  модуль когда-нибудь подключат в live — вернётся внутрибарное решение.
- `strategies/alt_elder_revived_v1.py:165,172` — `rows[-1]` только как fallback
  в `_swing_low/_high` (минорно).
- `strategies/elder_triple_screen_v3.py:378` — `cur_price=rows[-1][4]` в
  `_atr_quality_ok` (research-модуль).

**Вывод:** в боевом пути закрыто; привести research-модули к одному контракту
закрытого бара — гигиена перед тем, как двигать любую из них в live.

---

## 3. НОВАЯ НАХОДКА: контрактная нестыковка v3-семейства
Эталон — `strategies/inplay_retest_v3.py`: решающий бар берётся ВНУТРИ из
закрытой истории, привязка по времени:
```
entry_closed_rows = _closed_rows_before(entry_raw, signal_ts_ms, ...)
trigger_row = entry_closed_rows[-1]          # последний ЗАКРЫТЫЙ бар
```
Переданные o/h/l/c для триггера игнорируются → иммунитет к ошибкам вызывающего.

Но `breakdown_retest_v3.py:186` и `spike_fade_v3.py:184` берут решающий бар из
ПЕРЕДАННЫХ параметров:
```
cur_open, cur_high, cur_low, cur_close = float(o), float(h), float(l), float(c)
```
История — закрытая (`_closed_rows_before`), но сам решающий бар = то, что подал
вызывающий. В backtest туда подаётся закрытый бар (тесты зелёные). В live
монолит для IVB1 подаёт формирующийся WS-тик — если breakdown/spike подключат
так же, решение будет внутрибарным → расхождение с research → слив.

**Рекомендация (до ненулевого риска):** привести `breakdown_retest_v3` и
`spike_fade_v3` к паттерну `inplay_retest_v3` — выводить trigger-бар внутри из
`_closed_rows_before(...)[-1]`, а не из переданных o/h/l/c. + добавить
parity-тест (открытый последний бар не должен менять решение). Это аддитивно,
модули мои, риск 0 — могу сделать по твоему «go».

---

## 4. Alpaca adaptive v1 — ревью
`strategies/alpaca_adaptive_v1.py` (269 строк, pure stdlib, юнит-тесты есть).
**Сильное:** рыночный гейт SPY>SMA200 → кэш в медведе (защита от красных
месяцев — главное, чего не хватало v3x/v38); Sharpe-скоринг
`(mom60/vol60)*recency*trend_quality`; vol-adjusted (risk-parity) сайзинг;
секторный кап; min-momentum фильтр; portfolio DD-guard; soft_regime (частичная
экспозиция в пограничной зоне); trailing_exit overlay; опциональный AI-veto хук
(честно помечен как ФИЛЬТР, не альфа).
**Дыра (его же докстринг):** нет реального walk-forward на медвежьих данных
(2022). Это data-wiring шаг, его делает Codex. До него — годовой зарабатывающей
цифры нет, реальные $500 не трогать (ревью после закрытия 2026-06-26).
**Идея на усиление:** A/B bakeoff baseline vs lively_config vs soft-only vs
trailing-only с критерием «частота/доходность чуть выше, DD не растёт >~3%»
(уже в плане §6.5) + прогон по бычьим годам для первой годовой цифры.

---

## 5. Ростер крипты (дефолты risk_mult в монолите)
Живой риск несут (по live-проверке): `flat_resistance_fade≈0.30x`, legacy Range
short-only `0.25x`. Остальные ядровые (ATT1/bounce/breakdown/IVB1/midterm) —
scan/shadow, risk 0. Elder/ASB1-slope/HZBO1 — выключены. Фактические значения
задаются live-env (`configs/*.env`, зона Codex), дефолты модуля — лишь floor.
Полный список модулей: ~88 в `strategies/` (много дублей-research — кандидаты на
консолидацию 87→~12 из §6.6).

---

## 6. Приоритеты (порядок не меняю относительно §6)
1. Сохранить v3 в git (ждём Codex / снятия lock).
2. **Безопасность:** fail-closed gate — СДЕЛАНО (этот аудит). Подтвердить, что
   closed-candle покрывает все живые пути — по факту покрывает (тест есть).
3. Привести `breakdown_retest_v3`/`spike_fade_v3` к closed-trigger контракту
   `inplay_retest_v3` + parity-тесты (моя зона, по «go»).
4. v3 → autoresearch sweep → monthly → отбор без красных медвежьих.
5. `hedge_pairing(range, breakdown_retest_v3)` — доказать связку (нужны данные).
6. Alpaca A/B + bull-year прогон → первая годовая цифра.

## 7. Файлы, тронутые/созданные в этой сессии (для стейджинга Codex)
- ИЗМЕНЁН: `scripts/evaluate_crypto_promotion.py` (fail-closed, 2 строки).
- НОВЫЙ: `tests/test_promotion_gate_fail_closed.py`.
- НОВЫЙ: `reports/CLAUDE_AUDIT_2026_06_22.md` (этот файл).
- МУСОР (удалить, песочница не смогла unlink): `tests/__wtest__.py`,
  `.git/__write_test__`, `__wt_test__` (в корне).

## 8. Открытые вопросы для Codex
- В live монолит реально подаёт IVB1.maybe_signal формирующийся бар или уже
  закрытый? (от этого зависит, нужен ли strategies-уровневый щит для v3.)
- Можно ли поставить v3-семейство в очередь autoresearch сразу после коммита?

---

## ADDENDUM (та же сессия, позже) — пакет-тестер, Alpaca-плечо, v3-контракт

### Alpaca — реальная цифра дохода (не только медведь)
Оффлайн-бэктест `backtest/alpaca_adaptive_backtest.py` на кэше ~2023-05..2026-04
(с комиссиями): **GATED CAGR +21.1%, maxDD 4.9%, 58% плюсовых месяцев**
(~1.71%/мес). Прежний −6.5% — это ХУДШИЙ медведь (2022), а не норма.

### Alpaca — плечо (ответ на «2%/мес при той же просадке»)
`backtest/alpaca_leverage_probe.py` (regime-gated плечо, маржа 6.5%/год):
| lev | CAGR | avg/mo | maxDD |
|-----|------|--------|-------|
| 1.00 | 21.1% | 1.71% | 4.9% |
| 1.25 | 25.3% | 2.05% | 6.3% |
| 1.50 | 29.5% | 2.39% | 7.7% |
| 2.00 | 37.7% | 3.07% | 10.4% |
Вывод: 2%/мес достижимо при ~1.25x ценой роста DD 4.9%→6.3%. «Та же DD при 24%+»
бесплатно невозможна (закон риска). В медведе плечо умножает и убыток.

### Пакет-тестер
`backtest/package_efficiency_run.py` — signal-replay всего пакета (9 крипто +
Elder) с ресэмплингом 5m→любой TF, ранжирование по эджу, хук комиссий PKG_COST_R.
Диагностика «молчунов»: только ARS1 был реально сломан (требовал 15m, нет в кэше)
— починено ресэмплингом. ASB1/ARF1/SFV3/PF2 молчат ПРАВИЛЬНО (ждут режим/сетап).
Охотник за ликвидностью НЕ входит (нужны события ликвидаций; его движок —
backtest/liquidation_sweep_research.py). Полный прогон 12 монет × 365д + реальные
комиссии = серверная работа Codex.

### v3 closed-bar контракт
Уточнение: breakdown/spike используют ТОТ ЖЕ контракт, что боевой IVB1
(переданный бар = решающий, история закрытая) — это не баг, а указание Codex'у
подавать в live закрытый бар. Зафиксировано тестом
`tests/test_v3_closed_bar_contract.py` (форм-бар в ленте не меняет решение). Зелёный.

### Файлы этой сессии для стейджинга Codex (итог)
ИЗМЕНЁН: `scripts/evaluate_crypto_promotion.py` (fail-closed).
НОВЫЕ: `tests/test_promotion_gate_fail_closed.py`, `tests/test_v3_closed_bar_contract.py`,
`backtest/package_efficiency_run.py`, `backtest/alpaca_leverage_probe.py`,
`reports/CLAUDE_AUDIT_2026_06_22.md`.
МУСОР (удалить): `tests/__wtest__.py`, `.git/__write_test__`, `__wt_test__`.
Тесты: **423 passed**.

### hedge_pairing — реальный прогон (range vs breakdown)
`backtest/hedge_pairing_run.py` (BTCUSDT, локальный кэш 2025-02..2026-02, без комиссий):
- primary (range/ARS1): FAIL, красные медвежьи: 2025-02,03,11, 2026-01,02.
- combined (range+breakdown): breakdown **закрыл 2025-03 и 2025-11**, PnL +6.2R→+14.3R,
  hedge drag = none. Полного флипа FAIL→PASS нет (остались 2025-02,2026-01,02).
- Вывод: концепция хеджа работает частично уже на прокси; **окончательный
  improved=True проверять на сервере с РЕАЛЬНЫМ range-стримом + комиссиями.**

---

## 9. ЧЕК-ЛИСТ ДЛЯ CODEX — проверить / задеплоить / поднять тесты

### A. ПРОВЕРИТЬ (перед коммитом)
1. Codex реально не работает: `ps aux | grep -iE "codex|git "` пусто; снять
   stale-локи `.git/index.lock .git/objects/maintenance.lock` (см. §раньше — они
   пустые, 6ч, незавершённых операций нет).
2. Прогнать `pytest -q` → ожидаемо **423 passed** (0 skip/fail).
3. Глазами просмотреть diff `scripts/evaluate_crypto_promotion.py` (зона Codex,
   фикс 2 строки fail-closed) — убедиться, что только exit-код изменён.
4. `git diff --cached --name-only` после стейджинга = ровно список из §B (ничего
   лишнего, без `.env`/`configs/*secret`).

### B. ЗАДЕПЛОИТЬ (git, зона Codex)
Стейджить ЯВНЫМИ путями (никогда `git add .`):
```
# убрать мусор от песочницы (она не смогла unlink)
rm -f tests/__wtest__.py .git/__write_test__ __wt_test__
# v3-семейство (untracked, из §3 STATE-дока) + работа этой сессии
git add strategies/breakdown_retest_v3.py strategies/spike_fade_v3.py \
  backtest/hedge_pairing.py tests/test_breakdown_retest_v3.py \
  tests/test_spike_fade_v3.py tests/test_hedge_pairing.py \
  tests/test_proof_of_life_digest.py scripts/proof_of_life.py \
  scripts/evaluate_crypto_promotion.py \
  tests/test_promotion_gate_fail_closed.py tests/test_v3_closed_bar_contract.py \
  backtest/package_efficiency_run.py backtest/alpaca_leverage_probe.py \
  backtest/hedge_pairing_run.py \
  reports/STATE_AND_MIGRATION_2026_06_22.md reports/CLAUDE_AUDIT_2026_06_22.md
git diff --cached --name-only   # СВЕРИТЬ
git commit -m "additive: v3 family + fail-closed gate + package/hedge/leverage runners + tests"
git push origin codex/dynamic-symbol-filters
```
ВНИМАНИЕ по fail-closed: теперь `evaluate_crypto_promotion.py` выходит с кодом 2
при провале. Проверить, что ВЫЗЫВАЮЩИЕ скрипты/CI трактуют non-zero как «не
промоутить» (halt), а не как «crash» — это и есть цель.

### C. ПОДНЯТЬ ТЕСТЫ / СЕРВЕРНЫЕ ПРОГОНЫ (доказательства эджа)
Локальные (быстрые, уже зелёные): `tests/test_promotion_gate_fail_closed.py`,
`tests/test_v3_closed_bar_contract.py`, плюс существующие v3/hedge тесты.

Серверные прогоны на ПОЛНОЙ истории + РЕАЛЬНЫХ комиссиях (это и есть отбор ног):
1. `PYTHONPATH=. python3 backtest/package_efficiency_run.py` (12 монет × 365д,
   задать `PKG_COST_R` ≈ реальные fee+slip) → ранжирование по эджу, отобрать
   expectancy>0 / PF>1.2 кандидатов (IVB1 — первый на проверку).
2. `PYTHONPATH=. python3 backtest/hedge_pairing_run.py` но с РЕАЛЬНЫМ range-стримом
   (sr_range_strategy), не ARS1-прокси → цель `improved=True` (FAIL→PASS).
3. `PYTHONPATH=. python3 backtest/alpaca_leverage_probe.py` → решить по плечу
   (1.25x ≈ 2%/мес, DD 6.3%). Реальные $500 — только после ревью 2026-06-26.
4. Отобранных кандидатов → autoresearch sweep → `evaluate_crypto_promotion.py`
   (теперь fail-closed) → shadow → canary $100.

### D. НОВЫЕ ТЕСТЫ ДОБАВИТЬ (на сервере, когда появятся данные)
- monthly-stability тест для IVB1 (≤3 красных, streak≤2) на 360d next-open.
- parity-тест live==research для ЛЮБОЙ v3, которую двигают в live (closed-bar).
- регресс на hedge improved=True, когда докажется на реальных стримах.

---

## 10. СРЕДНЕСРОЧКА — прогон через тестер (новый раннер)
`backtest/midterm_efficiency_run.py` (BTC+ETH, локальный кэш ~1г, скан 4h,
удержание до 27д, БЕЗ комиссий):
| стратегия | trades | win% | expR | PF |
|-----------|--------|------|------|----|
| midterm_v3 | 10 | 40% | +0.40 | 1.67 |
| sloped_reclaim | 4 | 50% | +0.83 | 2.67 |
| midterm_pullback | 31 | 39% | +0.24 | 1.39 |
| midterm_short_v2 | 2 | 100% | +1.50 | inf |
| cycle_continuation / regime_retest | 0 | — | нужна многолетняя история | — |
| cycle_pullback | 8 | 13% | -0.52 | 0.40 |

**Вывод:** `midterm_v3` и `midterm_pullback` — позитивные кандидаты с приличной
частотой; sloped_reclaim даёт высокий эдж, но мало сделок. cycle-* молчат на 1
году (циклы нужно тестить на 3+ годах). Это НЕ доказательство (1 год, без
комиссий, 2 монеты) — но класс перспективный.

**Почему среднесрочка стратегически важнее скальпинга (ответ владельцу):**
на 4h/дневках исчезают хрупкие проблемы (closed-candle, латентность,
live-parity), и появляется ВРЕМЯ на ИИ-анализ каждого сигнала. Сюда логично
вешать `deepseek_signal_gate` как второе мнение (новости/режим/уровни) — на
скальпинге это невозможно, на свинге добавляет ценность без штрафа за задержку.

### Следующие тесты для среднесрочки (сервер Codex)
1. `midterm_efficiency_run.py` на полной многолетней истории + комиссии (PKG-style)
   — особенно для cycle-* (им нужен 3+ летний контекст).
2. monthly-stability + WF для midterm_v3 / midterm_pullback (топ-кандидаты).
3. A/B: midterm с `deepseek_signal_gate` vs без — измерить, ДОБАВЛЯЕТ ли ИИ-вет
   эдж (фильтр, не альфа: доказать, что помогает, а не только тормозит).

### Файлы добавлены (этот блок)
НОВЫЕ: `backtest/midterm_efficiency_run.py`, `backtest/hedge_pairing_run.py`.

---

## 11. ВЕБ: живой перематываемый график (прототип)
`web/static/live_chart_prototype.html` — самодостаточный (canvas, без внешних
либ): свечи + слайдер перемотки + ▶ реплей с регулируемой скоростью + метки
входов/выходов (long/short, win/loss) + кроссхейр с OHLC + накопленный R.
Данные: реальные 4h BTC + сделки midterm_pullback (зашиты для демо).
**Для Codex:** заменить зашитый `DATA` на фид из API (`/api/klines`,
`/api/trades`), повесить на operator console вместо текущих статичных графиков.
Это закрывает запрос владельца на «живой график как в трейдерском журнале».

## 12. АРБИТРАЖ / MARKET-NEUTRAL — как максимизировать (честно)
Реальность: чистый CEX-CEX ценовой арбитраж для нас мёртв (HFT/латентность).
Что реально работает как МЕДЛЕННЫЙ, market-neutral, ИИ-ветируемый 3-й источник:
1. **Funding carry** — собирать funding на перпе, захеджировав спотом. Простой
   Bybit-басет был NO-GO (1.8%/год). Максимизация: динамический отбор ТОЛЬКО
   высокофандинговых символов (`bot/funding_carry_picker` уже есть) + ротация +
   гейт `backtest/funding_carry_gate`. Реалистичная цель 5-12%/год нейтрально.
2. **Базис / cash-and-carry** — перп-премия к споту (`strategies/basis_arb_v1`).
3. **Cross-exchange funding differential** — разница фандинга между биржами.
4. **Stat-arb пары** (`pair_stat_arb_v1`, shadow) — коинтеграция, медленный mean-revert.
Честно: арбитраж — это НЕ двигатель 25-30%, это СГЛАЖИВАТЕЛЬ просадки и
некоррелированный поток. Двигатель — направленная крипта; арбитраж снижает DD
всего портфеля. Следующий шаг (сервер Codex): прогнать funding_carry_picker на
высокофандинговых + basis на реальных данных через gate → если net>порог, это
3-я нога.

## 13. МОДЕРНИЗАЦИЯ рабочих схем + ИИ-оркестратор (направление)
«Адаптация под рынок через ИИ-оркестратор»: не отдавать ИИ деньги/код, а дать
ему РЕЖИМ-ОСОЗНАНИЕ. `bot/regime_orchestrator` уже жонглирует bull/bear×trend/chop
и риск-мультами. Усиление: (а) ИИ-вет на медленных сигналах (deepseek_signal_gate,
доказать A/B что добавляет эдж); (б) champion/challenger — новая версия схемы
доказывает превосходство на shadow перед заменой; (в) оркестратор крутит
risk_mult доказанных ног по режиму, НЕ включает недоказанные. Управление живой
позицией + ИИ-влияние по командам владельца — монолит/веб (зона Codex): нужен
эндпоинт «команда оператора → действие над позицией» через
`deepseek_action_executor` (одобрение человека уже встроено).

### Файлы (этот блок)
НОВЫЕ: `backtest/midterm_efficiency_run.py`, `web/static/live_chart_prototype.html`.

---

## 14. FUNDING CARRY — максимайзер (3-я нога, market-neutral)
`backtest/funding_carry_maximizer.py` на реальном `live_scan` (548 монет):
- наивная ликвидная корзина: **+20%/год**; отбор top-8 по фандингу: **+112%/год**
  (лифт +92 п.п.) — метод отбора работает.
- НО `funding_carry_gate` даёт **GO=0%** по всем — и это ПРАВИЛЬНО: снапшот не
  доказывает ПОСТОЯНСТВО. Фандинг −230% (KITE/WIF) — транзиентные всплески на
  волатильных токенах, не харвест; собирать их = высокий риск разрыва хеджа.
- **Честный вывод:** реальный устойчивый carry — НЕ 112%, а после фильтра
  консистентности (picker.consistency + multi-window evidence гейта) реалистично
  **5-15%/год** нейтрально. Это сглаживатель DD и 3-я некоррелированная нога, не
  двигатель.
- **Следующий шаг (Codex):** прогнать максимайзер на 180d истории
  `funding_per_symbol.csv` (не снапшот) → отобрать монеты с высоким И стабильным
  фандингом → gate с windows/positive_windows → если GO, поднять carry-ногу в shadow.

### Файлы (этот блок)
НОВЫЙ: `backtest/funding_carry_maximizer.py`.

---

## 15. LIQUIDATION SWEEP — раннер + предварительный результат
`backtest/liquidation_sweep_run.py` (двухрежимный: реальный jsonl на сервере /
ценовой прокси локально). Движок боевой (`liquidation_sweep_research`).
**Прокси из цены (8 монет, ~год):** WR 43.8%, expR −0.62, PF 0.26 → FAIL.
Строже (drop>=2.5%): ХУЖЕ (WR 27%). Асимметрия цель/стоп (0.8/0.4, 0.6/0.4,
0.4/0.6): все FAIL.
**Вывод (важный и честный):** «купить отскок после резкого ПАДЕНИЯ ЦЕНЫ» —
убыток (ловля ножа, момент продолжается). Эдж снос-ликвидности, если есть,
живёт ТОЛЬКО в данных *принудительных ликвидаций* (маркер истощения) + тайминге
входа (ждать стабилизации), не в ценовых движениях. Это обоснование, зачем
коллектор собирает события.
**Следующий шаг (Codex):** `liquidation_sweep_run.py` подхватит реальный
`runtime/liquidations/bybit_liquidations.jsonl` автоматически → честный тест.
Если и там FAIL — эдж фальсифицирован, не тратить на него риск (это тоже
ценный результат — отрицательный, но честный).

## 16. ОСНОВА / ИИ / ВЕБ — оценка владельцу
**Основа (монолит 14.7k строк):** работает, плотно обвешана safety-rails
(fail-closed позиции, prune, рестарт только при flat). Не сломана. Долг —
размер + 88 модулей с дублями. Высшая структурная ценность: консолидация
88→~12 на общих движках + детерминированный бэктест с комиссиями (уберёт
«разные цифры»). НЕ переписывать с нуля.
**ИИ-слой:** богатый и правильно устроен — `deepseek_autoresearch_agent`
(предлагает) → `deepseek_action_executor` (исполняет С ОДОБРЕНИЕМ человека),
`signal_gate`/`research_gate`/`overlay`, зрение read-only. Архитектура верная.
Честный пробел: ЦЕННОСТЬ не доказана — гейты это ФИЛЬТРЫ, не альфа. A/B
«ИИ-вет на среднесрочке добавляет эдж или нет» — то, что докажет/опровергнет
ценность ИИ-слоя. До этого ИИ = хорошо спроектированный потенциал. Не расширять
ИИ-контроль, пока нет доказанного эджа для управления.
**Веб:** ~700 строк FastAPI + TOTP 2FA + operator console + activity feed.
Функционален и безопасен (2FA — хорошо). Жалоба на статичные графики закрыта
прототипом `live_chart_prototype.html`. Веб — НЕ узкое место, не золотить.
Ценные добавки: живой график (готов) + интерфейс «команда оператора → действие
над позицией» через action_executor (специфицировано, зона Codex).

### Файлы (этот блок)
НОВЫЙ: `backtest/liquidation_sweep_run.py`.

---

## 17. AI-VET A/B — добавляет ли ИИ-вет эдж? (харнес)
`backtest/ai_vet_ab_run.py` (BTC+ETH, midterm, прокси-вето = confluence: SMA200 4h
+ волатильность; реальный гейт подставляется на сервере):
| стратегия | baseline expR/PF | gated expR/PF | Δ |
|-----------|------------------|---------------|---|
| midterm_pullback | 0.24 / 1.39 | 0.26 / 1.45 | +0.02 (помог чуть) |
| midterm_v3 | 0.40 / 1.67 | 0.17 / 1.25 | −0.23 (ВРЕДИТ) |
**Вывод:** ИИ-вет — НЕ множитель эджа. Помогает маржинально и только тем
стратегиям, что НЕ кодируют ту же логику; стратегию с уже встроенным трендом
(midterm_v3) он портит. Ценность ИИ-слоя надо ИЗМЕРЯТЬ per-strategy, а не
включать глобально. Это операционализирует тезис «гейты — фильтры, не альфа».
**Сервер (Codex):** подменить proxy_veto на `bot.deepseek_signal_gate.gate_signal`
(тот же action/risk_factor) → A/B с реальным ИИ (он оценивает новости/события).

### Файлы (этот блок)
НОВЫЙ: `backtest/ai_vet_ab_run.py`.

---

## 18. КОНСОЛИДАЦИЯ 85 → 13 семейств (карта, ответ на долг «огромная система»)
Инвентаризация всех `strategies/*.py` (85 модулей) → группировка по ТОРГОВОЙ
ЛОГИКЕ. Каждое семейство = один движок + параметры; «keeper» = на чём строить.

1. **Уровневый отбой/фейд (горизонталь)** keeper: `inplay_retest_v3`/ASB1/ARF1.
   Поглощает: support_bounce, resistance_fade, flat_resistance_fade, bounce1,
   support_reclaim(_live), range_reclaim, horizontal_break, scalper_bounce,
   micro_scalper_bounce, hzbo1, spike_rejection. (~12 → 1)
2. **Пила во флэте (обе границы)** keeper: `alt_range_scalp_v1` (ARS1).
   Поглощает: range_mean_reversion, vwap_mean_reversion. (3→1)
3. **Пробой/слом + ретест** keeper: `inplay_retest_v3`+`breakdown_retest_v3`+IVB1.
   Поглощает: inplay_breakout, breakdown_live, inplay_breakdown v1/v2, asm1, gs1,
   momentum_breakout, squeeze_breakout, impulse_volume_breakout, session_open_breakout,
   scalper_breakout, micro_scalper_breakout, sloped_break_retest. (~14→1)
4. **Наклонка/канал (диагональ)** keeper: `alt_trendline_touch_v2` (ATT1).
   Поглощает: att1(_v2)_live, slope_break, sloped_channel(_live), sloped_momentum,
   sloped_resistance_choch, btc_sloped_reclaim, asb1_live. (~9→1)
5. **Памп/дамп фейд** keeper: `spike_fade_v3`.
   Поглощает: pump_fade_simple/smart/v2/v4r, pump_momentum, pfs1. (~7→1)
6. **Элдер (тройной экран)** keeper: `elder_triple_screen_v3` (редизайн).
   Поглощает: elder_v2, elder_crypto, elder_revived, pullback_continuation. (5→1)
7. **Среднесрочный BTC/ETH свинг** keeper: `btc_eth_midterm_v3` + pullback.
   Поглощает: midterm_pullback_v2, midterm_short v1/v2, trend_pullback. (6→1)
8. **BTC цикл/режим** keeper: `btc_regime_retest_v1`.
   Поглощает: cycle_continuation/level_target/pullback, regime_flip, bear_regime_cont. (6→1)
9. **Снос ликвидности** keeper: `liquidation_cascade_entry_v1`.
   Поглощает: liquidity_sweep_reversal, scalper_sweep. (3→1)
10. **Market-neutral (funding/basis/pair)** keeper: `funding_carry`+`basis_arb_v1`.
    Поглощает: funding_hold, funding_rate_reversion, pair_arb_executor, pair_stat_arb. (~6→1)
11. **Грид** keeper: `grid_smart_v1`. Поглощает: smart_grid. (2→1)
12. **Микро-скальп** keeper: `micro_scalper_v1` — КАНДИДАТ НА ДЕПРЕКАЦИЮ
    (скальпинг — самый хрупкий класс). Поглощает: micro_scalper_live, sc1, scalper_classic,
    whale_print_follow. (5→1, либо в архив)
13. **Alpaca (акции)** keeper: `alpaca_adaptive_v1`.
    Поглощает: alpaca_dynamic_v3/v4_event, equities_swing_active. (4→1)

**Итог:** 85 → 13 семейств. Это НЕ удалять код сразу, а: (а) пометить keeper'ы,
(б) остальное → `strategies/archive/` (не в scan), (в) фичи из дублей переносить
в keeper по мере доказательства. Снижает поверхность багов и когнитивную нагрузку
в разы. Делает Codex (он владеет деревом/деплоем) по этой карте.

### Файлы (этот блок)
Только доковая карта (этот раздел). Кода не трогал.

---

## 19. ПОРТФЕЛЬНЫЙ КОМБАЙНЕР — «минусы перебиваются плюсами» в цифрах
`backtest/portfolio_combiner.py` (BTC+ETH, кэш ~год, R-единицы, без комиссий):
| нога | итог,R | просадка,R | зелёных мес |
|------|--------|------------|-------------|
| midterm_v3 | +4.0 | −2.0 | 57% |
| midterm_pullback | +7.4 | −7.0 | 56% |
| range/ARS1 | +4.4 | −17.0 | 13% |
| breakdown (хедж) | +3.9 | −2.0 | 33% |
| **КНИГА ЦЕЛИКОМ** | **+19.7** | **−15.0** | **65%** |

Сумма просадок по отдельности −28R; просадка книги целиком −15R → диверсификация
экономит 13R просадки. Зелёных месяцев у книги (65%) больше, чем у любой ноги.
range в одиночку убыточен по риску (−17 просадка), в книге — сглажен. Это
численное доказательство принципа «минусы перебиваются плюсами». Иллюстрация на
кэше без комиссий; боевая кривая — на сервере на доказанных ногах + комиссии.

## 20. СЛОВАРЬ (простыми словами, для владельца)
- **эдж (edge)** — преимущество: в среднем зарабатываем больше, чем теряем.
- **экспектанси / expectancy_R** — сколько в среднем приносит ОДНА сделка (в R).
- **R** — единица риска. +1R = заработали один риск, −1R = потеряли один риск.
- **просадка / drawdown / maxDD** — самое глубокое падение счёта от пика до дна.
- **PF / profit factor** — на каждый потерянный рубль сколько заработано (>1 = плюс).
- **WR / win%** — доля прибыльных сделок.
- **гейт / promotion gate** — авто-проверка «годна ли стратегия в живую торговлю».
- **shadow** — стратегия считает сигналы, но НЕ торгует деньгами (наблюдение).
- **canary** — крошечный реальный запуск ($100) для финальной проверки.
- **closed candle** — закрытая (завершённая) свеча; решать по ней, а не по текущей.
- **market-neutral / carry / базис** — заработок без ставки на рост/падение (хедж).
- **walk-forward (WF)** — проверка на多 непересекающихся отрезках истории (честность).

### Файлы (этот блок)
НОВЫЙ: `backtest/portfolio_combiner.py`.

---

## 21. ДОКТОР КРАСНЫХ МЕСЯЦЕВ + почему аллокатор «не помогает»
**Почему основа не помогает (честно):** `bot/regime_orchestrator` читает 4h BTC и
крутит ОБЩИЙ риск-множитель по режиму (бык/медведь/флэт). Снизить риск в медведе
≠ заработать в медведе. А заработать некому: ноги, что могли бы (breakdown/Elder
шорты, carry) — на нуле риска / не доказаны. **Аллокатор исправен, но ему не на
что переключаться — нет доказанной ноги, зарабатывающей в красный месяц.**

`backtest/red_month_doctor.py` (BTC+ETH, R, без комиссий) — для каждого красного
месяца книги (midterm+range) находит, кто из ростера в ЭТОТ месяц выигрывал:
| красный месяц | книга | лекарство |
|---------------|-------|-----------|
| 2025-03 | −5.0R | IVB1 +12.0R, ATT1 +2.0R |
| 2025-08 | −0.8R | breakdown +4.1R |
| 2025-12 | −0.5R | ATT1 +5.5R, ARF1 +4.5R |
| 2026-02 | −4.8R | IVB1 +7.0R |
| 2026-03 | −2.8R | ATT1 +5.5R |
| 2025-02 | −1.0R | никто (нужен новый эдж) |
**Рецепт:** ATT1 покрывает 5/9 красных месяцев книги, IVB1 — 2/9 (мощно).
Добавить ATT1+IVB1 как доказанные ноги → аллокатор включает их в режимах, где
книга краснеет → красные месяцы закрываются. Это даёт основе ЦЕЛЬ.
**Сервер Codex:** доказать ATT1/IVB1 через gate → завести правило в оркестратор
«в bear/chop поднять риск ATT1/IVB1» → переаудит красных месяцев на комиссиях.

### Файлы (этот блок)
НОВЫЕ: `backtest/portfolio_combiner.py`, `backtest/red_month_doctor.py`.
