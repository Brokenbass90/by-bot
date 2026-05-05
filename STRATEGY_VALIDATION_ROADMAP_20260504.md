# Strategy Validation Roadmap — 8 untested стратегий
**Дата:** 2026-05-04
**Автор:** Claude
**Цель:** дать Codex'у roadmap на 2-3 недели с конкретными spec'ами и acceptance gates.

## Acceptance gate (одинаковый для всех)

PROMOTE-в-canary только при ВСЕХ:
1. **WF-22:** ≥ 13/22 окон pass с PF ≥ 1.20, DD ≤ 8%
2. **Annual standalone:** PF ≥ 1.30, DD ≤ 8%, trades ≥ 50
3. **Portfolio additivity vs canary v2.1:** net не падает, DD не растёт > +1.5pp, trades не падают > 30%
4. **Live shadow 7 дней:** pulse counters работают, нет ошибок в TG

---

## 1. ASB1 (alt_support_bounce_v1) — bull-chop primary long

| Параметр | Значение |
|---|---|
| Текущий статус | В live-канарее v2.1 (мой fix) — должен начать торговать |
| Прошлый sweep | r136 daily — есть config |
| Spec | `configs/autoresearch/asb1_bull_chop_repair_v1.json` ✅ готов |
| Combos | 432 |
| Ожидание | PF 1.4-1.6, 80-150 trades/y, **+15-25% годовых** в bull-режимах |
| Зачем | Заменяет ARF1 в bull-регимах (Pair 4 swap) |

---

## 2. IVB1 (impulse_volume_breakout_v1) r073

| Параметр | Значение |
|---|---|
| Текущий статус | r073 winner найден (PF 1.98, 95 trades, DD 2.28%) |
| Spec | TZ в `CODEX_TASK_wf22_impulse_r073_att1_r424_20260429.md` ✅ |
| Шаги | (a) extract r073 params → (b) WF-22 → (c) annual confirm → (d) additivity vs canary v2.1 |
| Ожидание | Если все 4 шага PASS — добавляем в canary, +5-10% годовых |

---

## 3. HZBO1 (alt_horizontal_break_v1)

| Параметр | Значение |
|---|---|
| Текущий статус | Sweep ни разу не запускался |
| Spec нужен | НОВЫЙ — `configs/autoresearch/hzbo1_initial_sweep_v1.json` |
| Grid template | `HZBO1_LOOKBACK=[24,36,48]`, `HZBO1_BREAK_ATR=[0.2,0.3,0.4]`, `HZBO1_RR=[1.5,2.0,2.5]`, `HZBO1_RSI_LONG_MAX=[55,60]`, `HZBO1_RSI_SHORT_MIN=[40,45]` (~96 combos) |
| Ожидание | Bidirectional, активен в bull_trend и bear_trend; PF 1.3-1.5 if works |

---

## 4. PUMP_FADE v5 (на bear-window)

| Параметр | Значение |
|---|---|
| Текущий статус | v4r дал PF=0 на 1 trade — мёртв |
| Spec | `configs/autoresearch/pump_fade_v5_bear_window_v1.json` ✅ готов (Claude) |
| Combos | 243 |
| Ожидание | Если найдём params где PF≥1.30 на 30+ trades — добавим в bear overlay для portfolio diversity |

---

## 5. ATT1 density v3

| Параметр | Значение |
|---|---|
| Текущий статус | Live ATT1 даёт мало сделок в bull_chop (тугие params) |
| Spec | `configs/autoresearch/att1_density_v3_more_pivots_v1.json` ✅ готов (Claude) |
| Combos | 864 |
| Ожидание | Найти params с PF ≥ 1.25 + 100+ trades/y — заменить в canary |

---

## 6. Elder v3 macro-relax

| Параметр | Значение |
|---|---|
| Текущий статус | На дефолтах 0 trades; 7 trades с macro_relax_v1 — слишком тонко |
| Spec | `configs/autoresearch/elder_v3_macro_off_full_relax_v1.json` ✅ готов (Claude) |
| Combos | 81 |
| Решение | Если PF≥1.5 на 25+ trades → промоут как фильтр, не как двигатель |

---

## 7. ASM1 (alt_sloped_momentum_v1)

| Параметр | Значение |
|---|---|
| Текущий статус | Low priority — archive candidate per STRATEGY_STATUS_20260419.md |
| Решение | НЕ тратим время. Если другие стратегии не дают edge — вернуться через месяц с фокусом на bull_trend pullbacks |

---

## 8. VWAP_MR (alt_vwap_mean_reversion_v1)

| Параметр | Значение |
|---|---|
| Текущий статус | 0 trades в backtest historically |
| Действие | Diagnose как flat_canary — возможно cache miss на VWAP-нужных данных, или signal logic broken. **Запустить smoke 30d на BTCUSDT с relaxed params** до full sweep. |

---

## V7 sleeves (5 штук — отдельный track)

### `breakdown_v2`
- Status: 0 trades в backtest (cache/signal bug)
- Action: Codex проверь что `tf_break="60"` not blocked by cache. Если нужен sweep — `BREAKDOWN2_LOOKBACK_H=[12,18,24,36]`, `BREAKDOWN2_RR=[1.5,2.0,2.5]`, `BREAKDOWN2_RSI_MAX=[48,52,55]`.

### `slope_choch`
- Status: untested
- Action: Sweep на bear regimes only с `SLOPE_CHOCH_R2_MIN=[0.5,0.6]`, `SLOPE_CHOCH_DEPTH_ATR=[0.6,0.8,1.0]`.

### `liq_cascade`
- Status: untested, требует liquidation feed
- Action: Сначала проверить inject данных (если liquidation map не работает, edge нулевой). Потом sweep.

### `funding_rev`
- Status: работает с funding fetcher (cron 5 мин), edge есть, нет formal WF
- Action: WF-22 на текущих params. Это short-window strategy (1-6h hold), в backtest легко проверить.

### `micro_scalp`
- Status: high-freq, опасен без validation
- Action: НЕ promote. Если хочется — paper canary 30 дней с risk_mult=0.1 → если PF≥1.3 → постепенный uplift.

---

## Приоритет для Codex (когда вернётся)

| # | Что | Время | Ожид. ROI |
|---|---|---|---|
| 1 | Запустить 5 готовых ночных spec'ов (asb1, att1, liquidity_v2, elder, pump_fade) | ~3-4ч CPU параллельно | средний |
| 2 | Запустить liquidity_sweep_reversal_v2_full_grid_v1 (новый Claude spec) | ~1ч | high (новая стратегия) |
| 3 | Запустить WF-22 для IVB1 r073 + ATT1 r424 | ~2ч | high (готовые winner'ы) |
| 4 | Активировать funding-carry executor в DRY_RUN | 5 мин | medium-high (готовый код) |
| 5 | После всех результатов — additivity test для passed candidates | per candidate ~30 мин | high — выбираем кандидатов в live |
| 6 | HZBO1 initial sweep + funding_rev WF-22 | ~3ч | medium |

Итого ~10-15 часов CPU + ~1-2 часа решений = roadmap на 2-3 дня плотной работы Codex.

---

## Что НЕ в roadmap (решения требуются)

- **ASM1** — close или promote? Сейчас archive candidate, low priority.
- **VWAP_MR** — диагностировать или archive окончательно? Решение — если smoke на default дал 0 trades, archive.
- **Старые BTC cycle стратегии** (`btc_cycle_*`, 4 штуки в strategies/) — все unused, не в allocator. Archive окончательно или на будущее?

---

## Когда roadmap считается завершённым

Promote ≥ 3 новых рукава в live canary (asb1, ivb1 r073, либо liquidity_v2) с подтверждённой additivity. Это дополнит canary v2.1 от 3 до 6+ active sleeves, что покроет больше регимов и даст +30-50% к ожидаемой годовой доходности.

Ожидаемое состояние через 2-3 недели Codex-работы:
- canary v2.2: ATT1 + ARF1 + ASB1 + midterm + IVB1 + 1-2 новых
- 6+ active sleeves с регим-aware overlay
- funding-carry passive layer
- expected annual: 60-90% (vs текущие 40-45% baseline)
