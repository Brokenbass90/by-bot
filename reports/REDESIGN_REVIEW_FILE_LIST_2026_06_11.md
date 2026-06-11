# Redesign Review File List — 2026-06-11

Цель: дать внешним ревьюерам короткий список файлов и вопросов. Большой файл со
содержимым стратегий уже собран здесь:

- `reports/STRATEGIES_FOR_REVIEW_2026_06_11.md`

Этот документ — навигация: что пересматриваем, что уже не идёт в портфель, и где
ожидаем улучшение P&L.

## 1. BD1 / Inplay Breakdown — redesign, not portfolio

Текущий вердикт: **не включать в портфель**. Последний repair-прогон дал лучший
кандидат только `PF=1.079`, `net=2.67`, `negative_months=5`, `max_negative_streak=3`.
Это слабый edge; параметры не спасают механизм.

Файлы:

- `strategies/alt_inplay_breakdown_v1.py`
- `strategies/alt_inplay_breakdown_v2.py`
- `strategies/breakdown_live.py`
- `strategies/inplay_breakout.py`
- `strategies/inplay_wrapper.py`
- `inplay_live.py`
- `configs/autoresearch/breakdown_v1_bear_failed_reclaim_sweep_v1.json`
- `configs/autoresearch/package_breakdown_recovery_v1.json`
- `configs/autoresearch/package_breakdown_rsi_v1.json`
- `configs/autoresearch/package_breakdown_regime_bounded_v1.json`
- `backtest_runs/autoresearch_20260611_150546_breakdown_v1_bear_failed_reclaim_sweep_v1/ranked_results.csv`
- `logs/bd1_repair_20260611.log`

Что спросить у ревьюеров:

- BD1 сейчас ловит настоящий breakdown или поздно входит после шума?
- Нужно ли разделить механизм на `bear_trend continuation` и `bear_chop failed-reclaim fade` вместо одной стратегии?
- Какие фильтры должны быть обязательными: ATR expansion, volume impulse, ADX/efficiency ratio, close below level N bars, retest failure?
- Как исключить месяцы разворота, где breakdown начинает шортить дно?
- Нужен ли выход не фиксированным RR, а trailing после импульса + time stop, если follow-through не пришёл?

Моё предложение:

- Переписать BD1 как **breakdown continuation after failed reclaim**: вход только если был пробой уровня, слабый ретест снизу, продавец удержал уровень, и рынок в bear_trend/strong risk-off.
- В bear_chop не торговать BD1 как continuation; там нужен отдельный fade/reversion sleeve.
- Добавить replay-разрез сделок: `breakdown_before_trend`, `late_breakdown`, `reclaim_failure`, `range_fakeout`. Без этого мы снова будем чинить среднюю температуру.

## 2. Elder / Triple Screen — redesign, not portfolio

Текущий вердикт: **не включать в портфель**. Последний relax-прогон дал лучший
кандидат `PF=1.115`, `net=1.53`, `negative_months=5`. Это не портфельный edge.

Файлы:

- `strategies/elder_triple_screen_v2.py`
- `strategies/elder_triple_screen_v3.py`
- `strategies/elder_crypto_v1.py`
- `strategies/alt_elder_revived_v1.py`
- `configs/autoresearch/elder_v3_macro_off_full_relax_v1.json`
- `configs/autoresearch/elder_ts_v2_sweep_v1.json`
- `configs/autoresearch/elder_ts_v2_signal_rescue_v2.json`
- `configs/autoresearch/elder_ts_v3_macro_relax_v1.json`
- `configs/autoresearch/triple_screen_elder_v20_quality_filter_repair.json`
- `configs/autoresearch/triple_screen_elder_v21_trend_retest_repair.json`
- `configs/autoresearch/package_elder_ema_v1.json`
- `configs/autoresearch/package_elder_revived_v1.json`
- `backtest_runs/autoresearch_20260611_153833_elder_v3_macro_off_full_relax_v1/ranked_results.csv`
- `logs/elder_v3_repair_20260611.log`

Что спросить у ревьюеров:

- Classic Elder подходит крипто-перпам или надо делать crypto-native 3-screen?
- Screen 3 должен быть stop-order breakout, close-confirmation, или pullback-to-value entry?
- Force Index/MACD в текущем виде слишком лаговый для crypto 1h/4h?
- Можно ли заменить oscillator-screen на volatility contraction + funding/liquidation context?
- В каких режимах Elder должен вообще молчать?

Моё предложение:

- Не чинить “Elder” как религию. Сделать **macro trend + pullback-to-value + trigger**:
  HTF trend, LTF pullback к EMA/VWAP/AVWAP, затем reclaim/impulse trigger.
- Отдельно тестировать long и short. Crypto shorts в bear phases должны быть самостоятельным sleeve, а не зеркалом long-логики.

## 3. LSR1 Liquidity Hunter — best crypto candidate, needs WF/additivity

Текущий вердикт: **лучший новый кандидат**, но не live. Нужен годовой WF на полной
вселенной и проверка additivity с ATT1/flat.

Файлы:

- `bot/liquidity_map.py`
- `tests/test_liquidity_map.py`
- `scripts/backtest_candidates.py`
- `configs/autoresearch/liquidity_sweep_reversal_v2_param_sweep_v1.json`
- `configs/autoresearch/liquidity_sweep_reversal_v2_full_grid_v1.json`

Что спросить:

- HTF pools + LTF sweep — устойчивый механизм или переобучение на basket?
- Какой trend-filter спасает SOL/BTC/ETH от fading continuation?
- Лучше фиксированный `2R` или pool-to-pool targets + runner?
- Какие признаки добавить: liquidation cascade, funding skew, OI change?

Моё предложение:

- Первый mandatory split: `sweep_with_trend`, `sweep_against_trend`, `sweep_in_chop`.
- Корзину выбирать только на IS-окне, подтверждать на следующем OOS-окне.
- Не включать в live до portfolio-additivity test: стратегия может быть плюсовой отдельно и всё равно ухудшать портфель через корреляцию/slot collision.

## 4. Pair Stat-Arb — keep, but fix accounting first

Текущий вердикт: **research only**. Старый высокий PF был артефактом валидатора.
До следующего теста обязательно учесть funding и согласовать beta-weighted signal
с исполнением.

Файлы:

- `strategies/pair_stat_arb_v1.py`
- `strategies/pair_arb_executor_v1.py`
- `scripts/pair_arb_scanner.py`
- `scripts/validate_pair_arb.py`
- `scripts/walkforward_pair_arb.py`
- `scripts/fast_pair_research.py`
- `tests/test_pair_stat_arb.py`
- `tests/test_pair_arb_executor.py`
- `tests/test_validate_pair_arb.py`
- `tests/test_pair_arb_scanner.py`

Что спросить:

- Как правильно считать realized PnL для beta-weighted perp pair?
- Funding должен быть отдельным veto, cost term или source of edge?
- Исполнение: equal notional, beta-weighted notional, vol-targeted legs?
- Какие stationarity/beta-stability gates обязательны?
- Как строить WF на 20+ парах без p-hacking?

Моё предложение:

- Fix #0: funding accounting.
- Fix #1: frozen beta at entry, not refit at exit.
- Fix #2: executor legs must match validator legs.
- Fix #3: meta-gate by spread volatility and crypto regime.

## 5. Alpaca v38 and Active Swing — diversify, do not mix gates

Текущий вердикт: v38 — первый real-кандидат после своего paper/preflight gate.
Active swing с trailing — кандидат рядом с v38, но пока paper/research.

Файлы:

- `configs/alpaca_v38_hybrid_top4_candidate.env`
- `scripts/equities_alpaca_paper_bridge.py`
- `strategies/equities_swing_active_v1.py`
- `scripts/validate_swing_alpaca.py`
- `configs/alpaca_v38_active_paper_candidate.env`
- `configs/alpaca_v38_more_active_research.env`
- `tests/test_equities_swing_active.py`
- `tests/test_validate_swing_alpaca.py`
- `tests/test_alpaca_live_order_guard.py`

Что спросить:

- Почему active trailing лучше только при hold ~15 дней, а не на коротком hold?
- Как не допустить конфликта тикеров между v38 monthly и active swing?
- Какой минимальный paper gate: 20+ closes / 4 weeks / protection incidents = 0?
- Как учитывать 2022 bear-market в WF?

Моё предложение:

- $500 real не дробить до завершения v38 gate: сначала v38, active рядом в paper.
- Active может получить долю только после собственного live-vs-sim gate.
- В портфеле Alpaca считать отдельным диверсификатором, не основным P&L engine.

## 6. Portfolio healing — how to attack red months

Главная проблема не в одном “плохом месяце”, а в том, что текущие crypto sleeves
слишком похожи по рыночному риску. Лечение:

1. Один scoreboard для всех цифр:
   `period`, `universe`, `fees`, `funding`, `slippage`, `IS/OOS`, `strategy set`,
   `monthly returns`, `red months`, `max red streak`.
2. Убрать из live то, что не прошло gate: BD1/Elder в redesign, не в portfolio.
3. Добавить независимые источники доходности:
   - LSR1: liquidity sweep reversion;
   - pair-stat-arb: market-neutral stabilizer after funding fix;
   - funding carry/reversion: low-turnover sleeve after realized funding validation;
   - flat/range mean reversion: отдельный bear_chop/sideways sleeve;
   - Alpaca: equity diversification, not crypto replacement.
4. Portfolio selection должен оптимизировать не “самый высокий PF”, а:
   `return / drawdown / red_months / correlation / slot collision`.
5. Smart leverage включать только после confidence score:
   live-vs-backtest match, DD state, regime confidence, liquidation buffer, sleeve edge.

## Existing review package locations

- Big all-in-one code packet: `reports/STRATEGIES_FOR_REVIEW_2026_06_11.md`
- Short independent packet: `reports/INDEPENDENT_REVIEW_PACKET_2026_06_11.md`
- Tracker of applied review fixes: `reports/STRATEGY_REVIEW_TRACKER_2026_06_11.md`
- Strategy package narrative: `STRATEGY_PACKAGE_2026_06_10.md`
- Review response: `REVIEW_RESPONSE_2026_06_11.md`
