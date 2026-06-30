# Range-filter wiring — спец для Codex (2026-06-30, Claude)

Готов единый модуль `bot/range_filter.py` (+ `tests/test_range_filter.py`, 7 зелёных;
фундамент стал 78 зелёных). Консолидирует ТРИ прежде разрозненных детектора в один
вызов и даёт явное разделение стороны long/short. Задача Codex — подключить и закоммитить.

## API (одна функция)
```python
from bot.range_filter import range_state, from_candles
st = range_state(rows, require_all=False, lower_zone=0.30, upper_zone=0.70)
# rows = [[ts,o,h,l,c,v], ...] (крипто-формат). Форекс: rows = from_candles(candles)
```
RangeState поля: `ok, is_range, regime(flat/asc/desc), pos_in_channel(0=низ..1=верх),
side_hint("long"/"short"/"none"), long_ok, short_ok, upper_now/lower_now (наклонные),
nearest_support/nearest_resistance (горизонтальные), ci/vp/adx, votes`.

## Логика (как устроено)
- Range-голос = forex.regime.is_ranging (3 меры: Choppiness>58, VolPct<40, ADX<25;
  2-из-3, либо все-3 при require_all) — ловит РВАНУЮ пилу (важно: гладкая волна в
  коридоре по этим мерам читается как мини-тренд, это by design).
- Режим/позиция = classify_channel (наклонные линии). Учитываются И flat, И наклонные
  каналы (allow_sloped=True) — владелец хотел отскоки в flat/up/down.
- Уровни: и горизонтальные (horizontal_levels), и наклонные (upper_now/lower_now) в state.

## Разделение стороны (КЛЮЧЕВОЕ требование владельца)
- `long_ok` = is_range И цена у НИЖНЕЙ границы (pos<=0.30) -> LONG-ONLY bounce.
- `short_ok` = is_range И цена у ВЕРХНЕЙ границы (pos>=0.70) -> SHORT-ONLY fade.
- Взаимоисключающи (тест это гарантирует) -> рукав остаётся однонаправленным.

## Что подключить (bounce/fade ноги)
Крипто: `alt_resistance_fade_v1` (живой flat, сейчас 0/45), `alt_resistance_fade_v2`,
`alt_support_bounce_v2`, `alt_channel_bounce_v1`, `range_mean_reversion_v1`,
`alt_range_scalp_v1`, `alt_range_reclaim_v1`.
Форекс (детектор НЕ используют — только bb_mean_reversion_v3 использует): `range_bounce_session_v1`,
`grid_reversion_session_v1`, `asia_range_reversion_session_v1`, `adaptive_grid_range_v1`,
`bb_mean_reversion_v1/v2/v2p`.

Паттерн подключения в каждой ноге: получить `st = range_state(rows)`; SHORT-only нога
торгует ТОЛЬКО при `st.short_ok`, LONG-only — только при `st.long_ok`; иначе no_signal
с reason из `st.reason`/`st.votes`. Свои самодельные range-гейты убрать (единый источник).

## После подключения — честный WF (приоритет OOS)
Свип с асимметр. R:R (tp∈{2,2.5,3}R, sl~1R) + require_all ∈ {False,True} как параметр;
отбор по OOS-плато (≥3/4 окна), НЕ по PF-пику. Ожидание: на форексе ranges чище ->
там выше шанс эджа, чем на крипто-мажорах (см. RANGE_DETECTOR_AUDIT_2026_06_30).
