# Mechanics wiring status — 2026-07-01

## Итог

Новая механика начала попадать в реальные backtest/live-контракты, а не только жить отдельными helper-модулями.

Сделано в этом проходе:

- `backtest/portfolio_engine.py`: портфельный движок теперь умеет pending limit-сигналы:
  - сигнал с `entry_order_type="limit"` не исполняется по next-open;
  - long fills только если следующий бар проторговал `low <= entry`;
  - short fills только если `high >= entry`;
  - ордер истекает через `limit_validity_bars`;
  - non-limit сигналы остаются прежними next-open.
- `strategies/inplay_retest_v4.py`: добавлен флаг `IRV4_USE_LEVEL_ENTRY`.
  - Setup A/B строят maker-limit plan через `bot.level_entry.plan_level_entry`;
  - сигнал получает `entry_order_type`, `limit_validity_bars`, `entry_level`, `entry_plan_reason`;
  - late-chase reject больше не затирается финальным `no_setup`.
- Regression tests:
  - pending limit fill/expiry в `tests/test_backtest_next_open.py`;
  - InPlay V4 limit-at-level + chase reject в `tests/test_inplay_retest_v4.py`.

Focused verification: `56 passed`.

## Smoke A/B — InPlay V4

Период: 120d, end `2026-06-30`, symbols `ADAUSDT,DOGEUSDT,SUIUSDT`, short-only, fees/slippage `6/2 bps`, next-open costs.

| Variant | Trades | Net | PF | WR | Max DD |
|---|---:|---:|---:|---:|---:|
| base close/next-open | 61 | -3.64R | 0.691 | 49.2% | 6.75R |
| `IRV4_USE_LEVEL_ENTRY=1` | 11 | +0.31R | 1.250 | 63.6% | 0.33R |

Первый вывод: maker-limit у уровня резко режет плохие поздние входы. Это не live-grade, но подтверждает правильное направление.

## Smoke с полной новой цепочкой входа

Флаги: `IRV4_USE_RETEST_QUALITY=1`, `IRV4_RETEST_MIN_QUALITY=0.45`, `IRV4_USE_LEVEL_ENTRY=1`.

Период: 240d, end `2026-06-30`, fees/slippage `6/2 bps`.

| Universe | Trades | Net | PF | WR | Max DD | Verdict |
|---|---:|---:|---:|---:|---:|---|
| `ADAUSDT,DOGEUSDT,SUIUSDT` | 22 | +2.61R | 2.520 | 72.7% | 0.60R | positive smoke |
| `LINKUSDT,SOLUSDT,ADAUSDT` | 14 | -0.19R | 0.908 | 50.0% | 0.69R | not enough |

Monthly/symbol breakdown for the positive smoke:

- Months: `2025-11 +1.20R`, `2025-12 +0.01R`, `2026-01 +1.04R`, `2026-02 +0.01R`, `2026-03 +0.02R`, `2026-06 +0.34R`.
- Symbols: `ADA +0.36R`, `DOGE +0.85R`, `SUI +1.40R`.

Это не canary-разрешение. Это candidate для настоящего rolling WF/OOS с `wf_folds + oos_selector`.

## SpikeFadeV3 status

`reports/research/sfv3_robust_gate_20260701_v2_20260701_073903/summary.md`:

- FAIL.
- OOS total: 29 trades, `+0.93R`, PF `1.144`.
- Fail reasons: `oos_net_too_low`, `oos_pf_too_low`, one bad OOS fold `-1.10R`, fee-stress failed.

Вывод: SpikeFadeV3 LINK short не размораживать. Старый красивый slice защищён robust gate и остаётся research-only.

## Следующий обязательный шаг

1. Прогнать rolling WF по InPlay V4 с новой цепочкой:
   - `retest_quality -> level_entry -> portfolio pending limit fill/expiry -> costs -> wf_folds -> oos_selector`.
2. Сравнить минимум:
   - short-only `ADA/DOGE/SUI`;
   - `LINK/SOL/ADA`;
   - long-only отдельно;
   - bidirectional отдельно.
3. Только если OOS plateau проходит:
   - shadow;
   - tiny canary with breaker+expiry.

До этого live crypto остаётся: ATT1 short-only canary; горизонтальные/InPlay рукава без денег.
