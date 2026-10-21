# Brain: DEV-исправления подтверждённых дефектов ревью (21.10.2026, Claude research)
Что не изменилось: LIVE, PUMP4 V1, Monthly, контур Codex, накопленные forward-записи Brain — не тронуты (журналы не переписывались).
Изменения только в ветке research/fabrika-v1. Тесты: 64 PASS (55 существующих тестов модулей + 9 новых
`tests/test_dev_fixes_20261021.py`); существующие тесты не потребовали правок.

| файл | правка | до → после | кого касается (вызывающие) |
|---|---|---|---|
| bot/market_context.py `sloped_level` | (1) проверка пробоя линии только с первого пивота; (2) новый параметр `last_pivots=k` — линия через последние k точек | см. замер ниже | fx_setups_v2, pump_exhaustion_unwind_short_v1, scripts/market_survey, render_levels; поведение по умолчанию у них не меняется |
| bot/range_filter.py | `extra.is_flat_range` и `extra.is_sloped_channel` раздельно; меры chop/volp/adx в try с флагом `extra.degraded`; флаг при отсутствии forex.regime | `is_range` прежний (совместимость) | inplay_retest_v4, alt_resistance_fade_v2, fx_*, smart_grid, range_scanner, failed_breakout, pump_exhaustion, decision_bus |
| bot/regime_hmm.py | битый/нулевой ATR → ok=False «unknown» вместо уверенного «range»; `regime_gate` без данных → allow=False, risk 0 (только новые входы) | NaN → range с высокой вероятностью; нет данных → полный риск | smart_grid, fx_context, range_scanner, fx_setups_v2 (FX/сетка; крипто-ноги PUMP4/KITY не используют) |
| bot/elder_filter.py | без полной истории EMA200 → ok=False (вместо тихой EMA≈51); NaN MACD больше не «да»; волна — опция `require_wave`, поле `extra.wave_agrees`; docstring исправлен | см. тесты | inplay_retest_v4, alt_resistance_fade_v2, fx_*, decision_bus |
| bot/adaptive_context.py `adaptive_params` | высокая волатильность раньше «флэта»; NaN/0 ATR → осторожные параметры | флэт при ATR 8 % → узкие уровни | alt_support_bounce_v2, alt_channel_bounce_v1, inplay_retest_v4 (только при ADAPTIVE=1) |
| research_lab/factory_v3/opportunity_v2.py | `ispravit_ishod()` — коррекция исхода отдельным событием со ссылкой на хеш исправляемой записи и обязательной причиной; `ishod_aktualnyy()` | ошибку исхода исправить было нельзя | Brain shadow (новых коррекций пока нет) |

## Измеримый эффект: наклонные линии (главная находка)
H1-бары 16 монет, окно 120 ч, шаг 24 ч, 11 424 линии поддержки/сопротивления:
| построение | линий «целых» (не пробиты закрытием) |
|---|---|
| старое (регрессия через все пивоты окна) | **0 из 11 424 = 0 %** |
| исправленная проверка, все пивоты | 0 % |
| через последние 3 точки (`last_pivots=3`) | 48.5 % |
| через последние 2 точки | 72.9 % |
Вывод: прежний `sloped_level` на реальных данных НИ РАЗУ не дал пригодной наклонной — регрессия через все минимумы/максимумы окна
не похожа на линию трейдера. Ветки `require_unbroken=True` в pump_exhaustion_unwind_short_v1 и fx_setups_v2 из-за этого
фактически не работали. Это подтверждает замечание владельца «отрисовку наклонных надо корректировать». Новое построение —
опция; существующие стратегии не меняются, пока не будет A/B.

## Что дальше
- InPlay Structural использует: `last_pivots=3` для наклонных, `is_flat_range` (флэт строго без наклона), Elder — только с полной историей.
- A/B «наклонная через 3 точки» — в рамках Structural (Brain ON/OFF), не отдельной гипотезой.
- Список кандидатов на удаление (без удаления): bot/risk_manager.py (нет вызывающих), ветка tuner в adaptive_context,
  `is_choppy`/`--tf` в regime_orchestrator — в инвентаризацию.
