# Range/Bounce пакет — RUNBOOK «один раз и правильно» (2026-07-01, Claude)

Цель: довести ARF2/ASB2/ACB1 до честного gate БЕЗ пустых тестов. Дополняет
TARGET_STRATEGY_PORTFOLIO (Codex) + INTEGRATION_REFERENCE (Claude). Порядок строгий —
не переходить к дорогому шагу, не пройдя дешёвый.

## Инварианты (учтено всё)
- SIDE-SPLIT: ARF2_short, ASB2_long, ACB1_long, ACB1_short — ОТДЕЛЬНЫЕ рукава.
  Статистика/breaker/allocation side-specific. Bidirectional PF больше НЕ основание для live.
- Общий helper-контракт на КАЖДУЮ ногу (по INTEGRATION_REFERENCE): regime_hmm -> сигнал+уровень
  -> range_filter -> elder_filter -> level_entry -> position_sizing -> exposure_gate -> decision_bus -> trailing.
- Уровни: горизонтали + HVN + наклонные confluence + flip/broken + liquidity_sweep. ARF2 сейчас
  НЕ на общем контракте -> перевести ПЕРВЫМ делом.
- Издержки честные: maker-fill (portfolio_engine limit) + slippage_model. Отбор: wf_folds+oos_selector.

## Шаг 0 — PRE-FLIGHT (обязательно, дёшево) — НЕ гнать gate без него
Прогнать быстрый DRY signal-run каждой стороны на ШИРОКОМ юниверсе (7-8 mid-caps:
ADA/DOGE/SUI/AVAX/MATIC/LTC/XRP/LINK) за 240-360d, собрать signals=[{ts,symbol}].
`bot/preflight_check.preflight(signals, n_folds=4, min_trades_total=40, min_trades_per_fold=8, min_symbols=3)`.
- NO-GO -> НЕ запускать OOS gate. Сначала: расширить юниверс ещё / ослабить min_quality (в разумных
  рамках) / понизить ТФ. Повторить pre-flight.
- GO -> только тогда полный rolling OOS gate. Это убивает «пустые тесты» (InPlay был бы NO-GO:
  21 сделка, фолд с 1 -> не запускали бы дорогой прогон).

## Шаг 1 — Перевести ARF2 на общий контракт
ARF2 fade от сопротивления: подключить range_filter (торговать fade только в range/у сильного
уровня), retest_quality (качество), level_entry (maker у уровня), elder_filter (short только при
allow_short), decision_bus. Убрать самодельные веса. Тест: 56+ прежних зелёных не падают.

## Шаг 2 — pre-flight по каждой стороне (Шаг 0) на широком юниверсе
ARF2_short, ASB2_long, ACB1_long, ACB1_short — по отдельности. Записать per_fold/symbols.
Только GO-стороны идут дальше.

## Шаг 3 — OOS gate (только для GO-сторон)
wf_folds (purge+embargo) -> oos_selector. Пре-регистрированные критерии PASS:
≥3/4 фолда net>0, медиана>0, нет один-окно-героя, N≥40 (≥8/фолд), fee/slip-stress выживает,
cross-symbol (≥2-3 символа несут, не один). Свип: tp_rr{2,2.5,3}, min_quality, require_with_tide{0,1}.

## Шаг 4 — по результату
PASS -> champion_challenger: shadow (paper) -> edge_monitor healthy N -> tiny canary (breaker+expiry).
FAIL -> НЕ хоронить: если NO-GO по частоте даже на широком юниверсе -> сторона = редкий
диверсификатор (в мульти-ногу), не основной рукав. Гипотеза-фикс -> обратно.

## Порядок исполнения (чтобы ничего не забыть)
1) ARF2 на контракт. 2) pre-flight всех 4 сторон. 3) gate только GO. 4) champion_challenger.
Параллельно (не блокирует): H4 real-data (сервер), Alpaca $500 (владелец).

## Что это даёт
Ни одного дорогого прогона впустую: сначала дешёвый pre-flight (частота/покрытие), потом gate.
Всё side-specific, на общем контракте, с честными издержками и OOS. «Сделано нормально».
