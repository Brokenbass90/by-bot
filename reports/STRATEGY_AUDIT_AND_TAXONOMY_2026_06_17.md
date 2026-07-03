# Полный аудит стратегий + таксономия по логикам (2026-06-17)

87 модулей в `strategies/` — это в основном **дубли и эксперименты**. Реальный смысл — свести к ~12 канонам, переписать уровневые под v3-логику, лишнее убрать, события (памп/дамп, ликвидации) держать как research. Ниже: (1) карта семейств с вердиктом keep/rewrite/kill, (2) таксономия лонг/шорт × режим, (3) план.

Вердикты: **KEEP** — канон, оставляем; **REWRITE** — логика верная, но переписать под реальные уровни v3 / починить; **KILL** — дубль или доказанно плохой, в архив; **RESEARCH** — держим как движок сбора данных/гипотезу.

## 1. Семейства (87 → 12 канонов)

### Флэт, mean-reversion (пила)
- KEEP: `alt_range_scalp_v1` (ARS1) — **единственный зелёный эдж** (PF 1.6–2.0), но красные медвежьи месяцы.
- KILL (дубли): `range_mean_reversion_v1`, `alt_range_reclaim_v1`, `scalper_classic_v1`.

### Лонг от поддержки (флэт/откат)
- REWRITE→v3: `alt_support_bounce_v1` (ASB1), `support_reclaim_live`, `alt_support_reclaim_v1` → покрываются `inplay_retest_v3` (long-support retest-hold).
- KILL (дубли): `asb1_live`, `bounce1_live`, `scalper_bounce_v2`, `micro_scalper_bounce_v1`.

### Шорт от сопротивления (флэт)
- KEEP (live): `flat_resistance_fade_live` (ARF1) — малый живой рукав.
- REWRITE→v3: `alt_resistance_fade_v1` → `inplay_retest_v3` (short-resistance).

### Пробой уровня + ретест (лонг)
- REWRITE→v3: `inplay_breakout` (FAIL подтверждён), `impulse_volume_breakout_v1` (IVB1 — заморожен, логика кривая) → **заменены `inplay_retest_v3`**.
- KILL (дубли): `alt_momentum_breakout_v1`, `scalper_breakout_v2`, `micro_scalper_breakout_v1`, `alt_squeeze_breakout_v1`, `session_open_breakout_v1`, `gs1_live`, `hzbo1_live`, `alt_horizontal_break_v1` (горизонтальный пробой — поглощается v3).

### Слом поддержки + ретест (шорт)
- REWRITE→v3: `alt_inplay_breakdown_v1/v2`, `breakdown_live`, `alt_bear_regime_continuation_v1` → **новый `breakdown_retest_v3`** (план: слом→ретест снизу→шорт, тайтовый стоп над уровнем).

### Наклонки (трендовые линии)
- KEEP канон: `att1_live` (ATT1, отбой от наклонной) + один slope-break.
- REWRITE→v3: `sloped_break_retest_v1`, `alt_sloped_channel_v1` → наклонный канал уже есть в `inplay_retest_v3` (regression channel).
- KILL (дубли): `att1_v2_live`, `alt_trendline_touch_v1/v2`, `alt_slope_break_v1`, `alt_sloped_momentum_v1`, `sloped_channel_live`, `sloped_resistance_choch_v1`, `btc_sloped_reclaim_v1`.

### Памп/дамп (событие)
- REWRITE→v3: консолидировать в один `pump_fade` + **новый `spike_fade_v3`** (памп в сильное сопротивление + выдох → шорт; дамп в сильную поддержку + реклейм → лонг).
- KEEP(один): `pump_fade_smart_v1` (PFS1) как базовый, пока v3 не готов.
- KILL (дубли): `pump_fade_simple`, `pump_fade_v2`, `pump_fade_v4r`, `pump_momentum_v1`, `alt_spike_rejection_v1`, `alt_volume_spike_momentum_v1`.

### Ликвидации/свипы (событие)
- RESEARCH: `liquidation_cascade_entry_v1`, `alt_liquidity_sweep_reversal_v2` — движок копит данные, гипотеза проверяется позже.
- KILL (дубли): `scalper_sweep_v2`, `alt_whale_print_follow_v1`.

### Элдер (тренд, тройной экран)
- REWRITE: консолидировать в один `elder_triple_screen_v3`, редизайн (4h-экран + 1 сделка/символ/день — убрать гиперактивность).
- KILL (дубли): `elder_crypto_v1`, `elder_triple_screen_v2`, `alt_elder_revived_v1`.

### BTC/ETH среднесрок (свинг)
- KEEP канон: один лонг (`btc_eth_midterm_v3`) + один шорт (`btc_eth_midterm_short_v2`).
- KILL (дубли): `btc_eth_midterm_pullback(_v2)`, `btc_eth_midterm_short_v1`, `btc_cycle_continuation_v1`, `btc_cycle_level_target_v2`, `btc_cycle_pullback_v1`, `btc_regime_flip_continuation_v1`, `btc_regime_retest_v1`.

### Откат в тренде (continuation)
- REWRITE→v3: `alt_pullback_continuation_v1`, `trend_pullback_v1` → вход на ретесте уровня в направлении тренда (v3 с `IRV3_USE_REGIME=1`).

### Микро/VWAP/грид
- KILL/RESEARCH: `micro_scalper_*` (3 шт.), `asm1_live`, `sc1_live`, `alt_vwap_mean_reversion_v1`, `grid_smart_v1`, `smart_grid_v1` — нет доказанного эджа, высокая комиссия. VWAP можно как RESEARCH-кандидат во флэт.

### Market-neutral (фондинг/арбитраж)
- RESEARCH: `funding_hold_v1`, `funding_rate_reversion_v1`, `basis_arb_v1`, `pair_arb_executor_v1`, `pair_stat_arb_v1` — carry NO-GO (1.8%/год), держим как фон.

### Alpaca (акции)
- KEEP/IMPROVE: `alpaca_adaptive_v1` (защита капитала; добавлены soft-режим + трейлинг + `lively_config`).
- KILL/архив: `alpaca_dynamic_v3_event`, `alpaca_dynamic_v4_event`, `equities_swing_active_v1` (поглощены adaptive).

### Инфраструктура (не стратегии)
- KEEP: `signals.py`, `live_kline_utils.py`, `inplay_wrapper.py`, live-движки (`pfs1/gs1/sc1/asm1_live`).

## 2. Таксономия: лонг/шорт × режим (целевая карта)

| Режим рынка | ЛОНГ | ШОРТ |
|---|---|---|
| **Бычий тренд** | v3-ретест в направлении тренда (`IRV3_USE_REGIME=1`); Элдер; midterm лонг | — |
| **Медвежий тренд** | — | `breakdown_retest_v3`; midterm шорт; Элдер-шорт |
| **Флэт (горизонт)** | `inplay_retest_v3` от поддержки; ARS1 (нижняя граница) | `flat_resistance_fade` (ARF1); ARS1 (верхняя граница) |
| **Восходящий флэт** (наклонка вверх) | v3 от наклонной поддержки; отбой ATT1 | шорт у верхней наклонной (слабее) |
| **Нисходящий флэт** (наклонка вниз) | лонг у нижней наклонной (слабее) | v3 от наклонной сопротивления; ATT1-шорт |
| **Событие: памп** | — | `spike_fade_v3` (памп в сопротивление + выдох) |
| **Событие: дамп** | `spike_fade_v3` (дамп в поддержку + реклейм) | — |
| **Событие: ликвидации** | свип-реверс (RESEARCH) | свип-реверс (RESEARCH) |

**Пробелы (чего по сути нет качественного):** чистый медвежий-тренд шорт (breakdown_retest_v3 — в плане), нисходящий-флэт шорт, рабочий памп/дамп под уровни (spike_fade_v3 — в плане). Восходящий флэт лонгом закрывается v3 + наклонкой.

## 3. План (порядок, по эффект/риск)
1. **Консолидация-культя:** пометить KILL-дубли (архив `strategies/_attic/`), оставить ~12 канонов — резко чище и понятнее (это код-операция, аккуратно, с тестами на импорты).
2. **REWRITE под v3-уровни:** `breakdown_retest_v3` (медвежий шорт = хедж красных месяцев range) → `spike_fade_v3` (памп/дамп) → continuation через `IRV3_USE_REGIME=1`.
3. **Элдер-редизайн** (4h + 1/день) — закрыть бычий тренд.
4. **midterm** свести к лонг+шорт канону.
5. Каждый REWRITE → autoresearch → `monthly_analysis` → `hedge_pairing` с range → gate → canary.

**Что несёт деньги в этой карте:** связка `range (флэт) + breakdown_retest_v3 (медведь) + v3-ретест (флэт/тренд)` в противофазу — это путь убрать красные месяцы и масштабировать. Памп/дамп и ликвидации — добавочная частота сверху, не фундамент.
