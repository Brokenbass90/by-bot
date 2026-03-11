# Архив отставленных стратегий
# Архив: archive/strategies_retired/
# Оригинал: strategies/
# Дата архивации: 2026-03-11

Файлы перемещены сюда из `strategies/`. НЕ удалены — могут понадобиться для референса.

---

## Bounce-стратегии (устаревшие версии)

### bounce_bt.py
**Причина отставки:** Оригинальная bounce-стратегия. Superseded by `bounce_bt_v2.py` → superseded by
новой logic в `smart_pump_reversal_bot.py`. Бэктесты показали нестабильную производительность
в трендовом рынке (drawdown > 30% в trending phases).

### bounce_bt_v2.py
**Причина отставки:** Вторая версия bounce. В live не дала статистически значимых результатов
за 3 месяца наблюдения. Impulse filter заблокировал >75% входов.

---

## Trend-following (крипто)

### btc_eth_trend_follow.py / btc_eth_trend_follow_v2.py
**Причина отставки:** EMA-crossover тренд на BTC/ETH. Walk-forward деградирует: in-sample
CAGR +42%, out-of-sample +8%. Слишком close-fit к 2021-2023 bull run. v2 — попытка параметрической
оптимизации, итог тот же.

### btc_eth_trend_rsi_reentry.py
**Причина отставки:** RSI-based reentry в тренде. Слишком много false reentries в sideways.
Убирает прибыль от успешных трендовых trades комиссиями за неудачные reentries.

### btc_eth_vol_expansion.py
**Причина отставки:** Вход на расширении волатильности (ATR spike). Из-за crypto overnight
gaps генерирует много false signals после вечерних spikes. Sharpe < 0.5 в OOS.

### trend_pullback.py / trend_pullback_be_trail.py
**Причина отставки:** Pullback в трендовом рынке. Требует сильного устойчивого тренда, которого
нет в crypto в 2024-2026. `be_trail` — версия с breakeven + trailing stop, улучшила winrate
но не Sharpe из-за too-tight stops. Superseded by midterm strategy.

### trend_regime_breakout.py
**Причина отставки:** Breakout с EMA-режимом. Всё что хорошее отсюда переехало в
`InPlayBreakoutStrategy` с proper `regime_mode` поддержкой. Этот файл — старый proof of concept.

---

## Trendline-стратегии (4 версии)

### trendline_break_retest.py / v2 / v3 / v4
**Причина отставки:** Trendline detection оказался слишком subjectве (разные algo рисуют разные
trendlines). v1-v4 — итерации от ручного pivot detection до ATR-weighted regression.
Итого 14 месяцев работы, финальный OOS: Sharpe 0.7 — не достаточно для production.
Backtest-live parity была плохой из-за lookahead в trendline definition.
Потенциально revisit с proper pivot swing detection в 2027.

---

## Flat/Range-стратегии

### flat_bounce_v2.py / flat_bounce_v3.py
**Причина отставки:** Bounce от SR-уровней в ranging market. Идея рабочая, но:
- SR-уровни требуют ручной калибровки по символу
- False breakouts убивают winrate
- Superseded by `adaptive_range_short` (в разработке) и `RangeStrategy` (sr_range*)

### range_bounce.py / range_wrapper.py
**Причина отставки:** Generic range bounce wrapper. range_bounce — логика, range_wrapper —
integration шим. Superseded by sr_range.py + sr_range_strategy.py которые лучше
обрабатывают dynamic range expansion.

### adaptive_range_short.py
**Причина отставки:** ВРЕМЕННО в архиве. Это единственная кандидат-стратегия для flat-рынка
(ортогональная breakout). Нужен bяктест при flat-режиме. Revisit когда q1+q2 impulse buckets
покажут что рынок в глубоком flat (>70% в q1-q2).

---

## Grid-стратегии

### smart_grid.py / smart_grid_v2.py / smart_grid_v3.py
**Причина отставки:** Arithmetic grid на BTC/ETH. При капитале $100 grid слишком мелкий
для комиссий (комиссия > PnL per grid level). Риски: при directional move против позиции
быстрый drawdown до stop. v2/v3 — попытки dynamic grid sizing, не решили проблему.
Revisit при капитале >$5000.

---

## InPlay (старые версии)

### inplay_pullback.py
**Причина отставки:** Pre-breakout pullback логика. Merged/superseded by
`InPlayPullbackStrategy` в `sr_inplay_retest.py`. Этот файл — standalone версия без retest.

### inplay_wrapper.py
**Причина отставки:** Старый wrapper без cfg dataclass. Superseded by
`strategies/inplay_breakout.py::InPlayBreakoutWrapper` с полной env-based конфигурацией.

---

## Retest / SR Break

### retest_backtest.py
**Причина отставки:** Backtest harness для retest стратегии. Логика переехала в
`sr_inplay_retest.py`. Файл содержал дублирующий код.

### sr_break_retest_volume_v1.py
**Причина отставки:** SR break + retest + volume confirmation. v1 — первый прототип.
Superseded by `InPlayBreakoutStrategy` с `impulse_vol_mult` параметром.

---

## Структурные сдвиги

### structure_shift_v1.py / structure_shift_v2.py
**Причина отставки:** Market structure shift detection (Higher Highs / Lower Lows). Идея:
входить при смене micro-тренда. Проблема: crypto structure shifts слишком часто происходят
как whipsaws. OOS: Sharpe 0.6, max DD 22%. Revisit с temporal filtering (min N bars
to confirm shift).

---

## Прочее

### donchian_breakout.py
**Причина отставки:** Classic Donchian channel breakout. Прост и интерпретируем, но слабее
чем `InPlayBreakoutStrategy` с impulse filtering. OOS перформанс degraded после 2022.

### funding_hold_v1.py
**Причина отставки:** Long spot + short perps при высоком funding rate. Идея правильная,
но требует spot API и отдельного балансирования. v1 — незаконченный proof of concept.
Revisit как `funding_carry` стратегия (см. `runtime/funding_carry/`).

### momentum_continuation.py
**Причина отставки:** Momentum after strong candle. В backtest работало (2021-2022 bull market),
в sideways 2023-2024 — отрицательный Sharpe. Overfit to bull-only conditions.

### pump_fade.py
**Причина отставки:** Fade после pump (short). Crypto pumps продолжаются дольше чем ожидаешь.
Слишком рано шортировать → большие лоссы до разворота. Требует иного timing mechanism.

### triple_screen_v132.py / triple_screen_v132b.py
**Причина отставки:** Alexander Elder's Triple Screen (3 TF). Концептуально правильно,
но 3 TF lookback → много parameters → overfit. v132b был попыткой reduce parameters,
итог OOS Sharpe 0.65.

### tv_atr_trend_v1.py / tv_atr_trend_v2.py
**Причина отставки:** TradingView ATR-based trend following (Supertrend-like). Много
false signals в low-volatility periods. v2 added volatility filter, помогло частично,
но backtest-live gap остался >30%.

### vol_breakout.py
**Причина отставки:** Volume-spike breakout. Superseded by InPlayBreakoutStrategy с
`impulse_vol_mult` параметром который делает то же самое в более structured виде.

---

## Что осталось активным (в `strategies/`)

| Файл | Назначение | Статус |
|------|-----------|--------|
| `__init__.py` | package marker | active |
| `inplay_breakout.py` | InPlayBreakoutWrapper для live | **ACTIVE (production)** |
| `btc_eth_midterm_pullback.py` | Midterm BTC/ETH pullback | active (backtesting) |
| `signals.py` | Общие signal helpers | active |

---
_Дата: 2026-03-11 | Автор: Claude (Anthropic)_
