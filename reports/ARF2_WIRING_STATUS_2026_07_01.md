# ARF2 wiring status — 2026-07-01

Цель: начать перевод `alt_resistance_fade_v2` на общий helper-chain без изменения старого baseline.

## Что сделано

`strategies/alt_resistance_fade_v2.py` получил флаговые research-переключатели:

- `ARF2_USE_UNIFIED_LEVELS`
- `ARF2_USE_RANGE_FILTER`
- `ARF2_USE_RETEST_QUALITY`
- `ARF2_USE_ELDER_FILTER`
- `ARF2_USE_LEVEL_ENTRY`

Все флаги по умолчанию `false`, поэтому старое поведение ARF2 не меняется. Это важно для честного OLD vs NEW A/B.

## Что подключено за флагами

- `unified_levels`: общий source уровней, включая horizontal/sloped/flip/HVN и опциональные liquidity-extreme.
- `range_filter`: проверка, что short fade действительно находится в range/channel зоне для short.
- `retest_quality`: дополнительная оценка качества ретеста сопротивления.
- `elder_filter`: блокировка шорта против явного up-tide.
- `level_entry`: maker-limit у уровня вместо позднего входа по close; сигнал получает `entry_order_type="limit"` и `limit_validity_bars`.

## Что проверено

Focused tests:

```text
tests/test_alt_resistance_fade_v2.py
tests/test_preflight_check.py
tests/test_unified_levels.py
tests/test_range_filter.py
tests/test_retest_quality.py
tests/test_elder_filter.py
tests/test_level_entry.py

53 passed
```

Добавлен тест, что `ARF2_USE_LEVEL_ENTRY` реально строит limit-сигнал, а дефолтный путь остаётся рабочим.

## Что ещё не сделано

- Не запускался OLD vs NEW A/B.
- Не запускался sequential filter analysis.
- Не запускался preflight по `ARF2_short`.
- Это не live-ready изменение и не разморозка ARF2.

## Следующий шаг

Сделать быстрый dry-run/A-B:

1. OLD ARF2 baseline.
2. NEW ARF2 с флагами:
   - сначала только `ARF2_USE_LEVEL_ENTRY=1`;
   - затем `+ARF2_USE_UNIFIED_LEVELS=1`;
   - затем `+ARF2_USE_RANGE_FILTER=1`;
   - затем `+ARF2_USE_RETEST_QUALITY=1`;
   - затем `+ARF2_USE_ELDER_FILTER=1`.
3. На каждом шаге считать signal count, cheap PF/R, per-symbol coverage.
4. Если фильтр режет >50% сигналов без улучшения PF/R — не делать его обязательным для ARF2.

