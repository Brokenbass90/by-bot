# Проверка ревью DeepSeek по Brain / Trading OS на актуальном коде (21.10.2026, Claude research)
Что не изменилось: LIVE, PUMP4 V1, Monthly, контур Codex не тронуты; ни один модуль не изменён этим документом.
Метод: чтение актуального кода (ветка research/fabrika-v1) + поиск вызывающих по bot/ strategies/ scripts/ research_lab/factory_v3,
fabrika, web, deploy, forex и корню. Оговорка: LIVE-контур Codex (repo bybit-bot-recovery-20260824) отсюда не виден — для него
«используется ли в LIVE» должен подтвердить Codex.

## Сводка
| # | замечание | статус | факт |
|---|---|---|---|
| 1 | KITY: время наблюдения на сутки раньше → все KITY-возможности не причинны | **FALSE_POSITIVE** | `d` в signal.json — день расчёта; t_obs = конец предыдущего дня, t_av = 02:04 того же дня → лаг 2.07 ч ≤ 6 ч. KITY-возможности (10 шт., сигнал 15.10) помечены late=True по другой причине: Brain записал их в 16:01, через 14 ч после доступности (Brain shadow запущен 15.10 позже сигнала) — флаг верный |
| 1a | (новое) риск потери KITY-возможности при простое сторожа | **CONFIRMED (операционный)** | late=True, если запись позже доступности + 2 ч. Сигнал KITY считается ~02:04 UTC по четвергам; 21.10 сторож молчал 03:50–07:08 UTC. Если 22.10 простой повторится — неделя KITY выпадет из сравнения Brain |
| 2 | AI-tuner меняет параметры без журнала | **NOT_USED** | `tuner=` передаётся только в tests/test_adaptive_context.py; стратегии импортируют лишь `adaptive_params` (правила); `get_adaptive_context` вызывает только scripts/render_levels.py без tuner |
| 3 | adaptive_params: «флэт» проверяется раньше высокой волатильности; NaN ATR → 0 | **CONFIRMED** | строки 30–36 bot/adaptive_context.py; влияет на alt_support_bounce_v2, alt_channel_bounce_v1, inplay_retest_v4 только при ADAPTIVE=1 (в июльском гейте и моих прогонах выключено) |
| 4 | orchestrator: `is_choppy` не используется; `--tf` не используется; confidence 0.85/0.95 не калиброваны | **CONFIRMED** | стр. 170 (мёртвая переменная), 380 (аргумент не читается), 185–190 |
| 5 | regime_hmm: NaN ATR → «range» | **CONFIRMED** | стр. 87: при NaN trend_norm = 0 → вероятность range; ok=False только при нехватке баров (стр. 80) |
| 6 | regime_hmm.regime_gate: нет данных → полный риск | **CONFIRMED** | стр. 121 `allow True, risk_scalar 1.0`. Вызывающие: smart_grid, fx_context, range_scanner, fx_setups_v2 (FX/сетка), не крипто-ноги PUMP4/KITY |
| 7 | range_filter: восходящий/нисходящий канал считается «флэтом» по умолчанию | **CONFIRMED** | `allow_sloped=True` по умолчанию; inplay_retest_v4._range_allows вызывает именно так → мой вариант B_range 21.10 фильтровал «флэт + наклонные каналы». Это объясняет его нейтральность |
| 8 | range_filter: вызовы chop/volp/adx без try/except | **CONFIRMED** | стр. 108–112 |
| 9 | Elder: «волна» считается, но в решении не участвует | **CONFIRMED** | стр. 149–162: bias и allow_* зависят только от tide; комментарий «confirmed by wave» не соответствует коду |
| 10 | Elder: при нехватке баров EMA200 тихо подменяется EMA≈51; NaN MACD проходит как «да» | **CONFIRMED** | стр. 118, 130, 132. Возможная часть причины, почему Elder в InPlay-ablation срезал сделки до 42 |
| 11 | market_context.sloped_level проверяет пробой линии с 0-го бара, до первого пивота | **CONFIRMED** | цикл `for i in range(len(rows))` — ложные valid=False; прямо касается «отрисовки наклонных», о которой говорил владелец |
| 12 | market_context.vwap по всему окну | **DESIGN_CHOICE** (имя вводит в заблуждение) | — |
| 13 | regime_side_allowed: подстрока «bull»/«bear», нейтраль = разрешить | **DESIGN_CHOICE** (задокументировано) | единственный вызывающий — smart_pump_reversal_bot.py (старый бот этого repo) |
| 14 | «Нет тестов» | **FALSE_POSITIVE** | есть test_regime_hmm, test_range_filter, test_market_context, test_elder_filter, test_adaptive_context, test_regime_side_gate, test_strategy_regime_gate, test_risk_manager |
| 15 | iz_elder пишет лонги под ETS2S | **FALSE_POSITIVE** | в ten_ETS2S.jsonl 21 198 записей, все short |
| 16 | HEDGE_V1: UNKNOWN режим → хедж включён | **DESIGN_CHOICE** (так в prereg) | для анализа отмечать отдельно |
| 17 | Нет механизма исправления исхода в журнале | **CONFIRMED (пробел)** | P1: событие-коррекция со ссылкой, оригинал сохраняется |
| 18 | A/B на разных периодах для HEDGE/BRAIN_V2 | **CONFIRMED (методика)** | сравнивать только на общем подмножестве (≥15.10 / ≥17.10) |
| 19 | risk_manager «unknown → полный риск» | **NOT_USED** | у bot/risk_manager.py нет вызывающих, кроме теста |

## Что это значит
- Данные Brain shadow НЕ испорчены: главный «критический» баг (KITY) — ложный. Пересчитывать накопленное не нужно.
- Реальные дефекты — в детекторах режима (Elder, range_filter, hmm, orchestrator, sloped_level). В денежных ногах PUMP4/KITY/Monthly
  они не участвуют (по этому repo); их влияние — на исследования InPlay/уровней. Мои InPlay-варианты с Brain-фильтрами 21.10
  тестировали в том числе эти дефекты → вывод «Brain не помогает InPlay» относится к текущим детекторам, не к идее режима.
- Для InPlay Structural: режим считаю своим явным правилом с тестами (тренд / флэт / волатильность раздельно, флэт строго без
  наклона), не через Elder/range_filter по умолчанию.

## Следующие шаги
- P0 (сегодня): попросить владельца держать сторож живым в ночь на 22.10 (KITY ~02:04 UTC, окно записи до ~04:04 UTC).
- P1 (не блокирует InPlay): минимальные правки с тестами — Elder (волна в решении или честный docstring; ok=False вместо подмены EMA;
  NaN MACD → нет решения), sloped_level (проверка после первого пивота), regime_hmm (NaN → ok=False), adaptive_params (порядок, NaN).
  Каждая правка меняет поведение стратегий, которые их используют → отдельной версией, только для исследований, LIVE не трогать.
- P1: событие-коррекция в журнале opportunity_v2.
- Кандидаты на удаление (список владельцу, ничего не удаляю): bot/risk_manager.py (нет вызывающих), ветка tuner в adaptive_context,
  `is_choppy` и `--tf` в orchestrator; полный реестр «код без вызывающих» — отдельной инвентаризацией.
