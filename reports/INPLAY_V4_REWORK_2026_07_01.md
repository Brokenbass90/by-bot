# InPlay V4 — реворк через helper-слои (2026-07-01, Claude) — для Codex

InPlay V4 сейчас не боевой (лучший локальный PF ~1.04; на LINK/SOL/ADA минус). НЕ
размораживаем — перерабатываем ВХОД через готовые helper-модули, сохраняя short/long
сплит. Точки правки — в `strategies/inplay_retest_v4.py::maybe_signal`.

## Замены (что на что)
Сейчас Setup A вручную считает: `fresh()`, `lower/upper_wick`, `vol_ok`, entry_band.
Это ровно `bot/retest_quality.score_retest(...)`. Заменить ad-hoc гейт на градуированный:

Setup A LONG (off support):
  - было: `fresh(c2) AND band AND (reject_close) AND lower_wick>=min AND vol_ok`
  - стало: `st = score_retest(rows, lvl, "support", atr_value=atr,
            last_touch_idx=c2["last_idx"], touches=c2["touches"],
            entry_band_atr=cfg.entry_band_atr, max_age_bars=max_age)`;
            входить если `st.entry_ok and st.long_ok and st.quality >= IRV4_MIN_QUALITY`.
Setup A SHORT (off resistance): симметрично, `side="resistance"`, `st.short_ok`.

Setup B (flip пробитого уровня) — это `breakout_confirm` + ретест:
  - подтвердить пробой: `bo = breakout_confirm(rows)`; setup B LONG только если
    `bo.direction=="up" and bo.confirmed` (уровень реально пробит вверх), затем ретест
    флипнутого уровня грейдить `score_retest(..., "support")`. Симметрично для short.
  - это убирает ложные flip-входы (сейчас `nearest_broken_level` не проверяет качество пробоя).

## Конфлюэнс-гейты (поверх обоих сетапов)
1. `elder_filter.elder_bias(rows, htf_rows=structure_rows)`:
   LONG только если `allow_long`, SHORT только если `allow_short`
   (не фейдим/не ловим против явного тайда). Параметр `IRV4_REQUIRE_WITH_TIDE`.
2. `range_filter.range_state(rows)` для Setup A (bounce у уровня — режимный):
   торговать bounce только когда `st.is_range` ИЛИ уровень свежий+сильный (иначе это
   не отскок, а вход против тренда). Для Setup B (пробой) — НЕ требовать range.

## Параметры (в свип, отбор по OOS-плато)
`IRV4_MIN_QUALITY ∈ {0.55,0.65,0.75}`, `tp_rr ∈ {2,2.5,3}` (sl~1R), `require_with_tide ∈ {0,1}`,
`entry_band_atr ∈ {0.25,0.30,0.40}`, `max_age_bars ∈ {24,48}`. НЕ брать PF-пик — плато.

## Валидация (та же лестница, что для SpikeFade)
Истинный WF (train/test independent) per-symbol, fee-стресс, cross-symbol (6 HIGH_VOL из
survey), monthly stability. Дом приоритета — символы с чистыми уровнями (38 LEVELS из survey)
и форекс (range_bounce/bb_mean_reversion через те же helper-слои). Только потом canary.

## Почему это правильно, а не «разморозка»
Старый вход входил поздно/широким стопом и без конфлюэнса. retest_quality даёт тайт-вход
у свежего уровня (малый стоп -> высокий R), breakout_confirm отсекает ложные flip, elder
не даёт торговать против тайда, range_filter держит bounce в правильном режиме. Это
механика + уровни (наклон+горизонт) + сплит стороны — ровно то, что просил владелец.
