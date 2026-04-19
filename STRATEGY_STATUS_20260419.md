# Strategy Status Register — 2026-04-19

## ✅ PRODUCTION — Working, live in allocator

| Strategy | Sleeve | Evidence | Regimes active |
|----------|--------|----------|----------------|
| `alt_resistance_fade_v1` | flat | WF-22 pass, ~13% annual, core portfolio | bear_chop (PRIMARY) |
| `alt_sloped_channel_v1` | sloped | WF-22 pass, tuned per-regime | bear_chop shorts, bull_trend both |
| `alt_support_bounce_v1` | bounce1 | WF-22 pass | bull_trend (PRIMARY) |
| `alt_range_scalp_v1` | range_scalp | WF-22 pass | all regimes |
| `elder_triple_screen_v2` | elder_ts | WF-22 pass | bull longs, bear shorts |
| `impulse_volume_breakout_v1` | impulse | Part of core3, AvgPF=1.361 | bear_chop, bear_trend |
| `alt_inplay_breakdown_v1` | breakdown | Core3 WF AvgPF=1.361, best params found (LOOKBACK=36, SL=1.4, RR=2.0) | **DISABLED** — needs WF-22 re-validation → Task 1.1 |

---

## 🟡 PENDING WF-22 — Params found, not yet validated

| Strategy | Sleeve | Best params | Status |
|----------|--------|-------------|--------|
| `alt_trendline_touch_v1` | att1 | PIVOT_LEFT=2, R=2, R2=0.9, TOUCH_ATR=0.25, RSI_L=52 → PF=1.295 | → Codex Task 3.1 |
| `alt_horizontal_break_v1` | hzbo1 | Live bridge sweep not run yet | → Codex Task 3.2 |
| `elder_triple_screen_v3` | elder_ts_v3 | 96-combo sweep not run yet (default=0 trades) | → Codex Task 2.1 |
| `btc_eth_midterm_v3` | midterm_v3 | SL bug fixed (3fd801f), needs param sweep | → Codex Task 2.2 |
| `inplay_breakout` | breakout | SL/TP ATR-scale bug fixed (96cf4fd), needs retune sweep | → Codex Task 1.2 |

---

## 🔴 BROKEN / DISABLED — Known issues

| Strategy | Problem | Fix |
|----------|---------|-----|
| `alt_inplay_breakdown_v2` | 0 trades in all backtests (cache or signal bug) | Codex Task 3.4 diagnosis |
| `btc_eth_midterm_pullback` | Old version, superseded by v3 | Archive |
| `btc_eth_midterm_pullback_v2` | Old version, superseded by v3 | Archive |
| `btc_eth_midterm_short_v1` | Implemented, never WF-22'd | Queue after midterm_v3 |
| `btc_eth_midterm_short_v2` | Implemented, never WF-22'd | Queue after midterm_v3 |
| `alt_sloped_momentum_v1` (asm1) | Never WF-22'd, low priority | Archive candidate |

---

## 🆕 V7 NEW SLEEVES — Registered but never tested

All added in commit e9b898f. Enabled in regime overlays but never backtested.
**RISK: these may be losing money live right now with no evidence of edge.**

| Strategy | Sleeve | Enabled in | Priority |
|----------|--------|-----------|----------|
| `alt_inplay_breakdown_v2` | breakdown_v2 | bear_trend only | HIGH — diagnose 0 trades first |
| `sloped_resistance_choch_v1` | slope_choch | bear_chop, bear_trend | MEDIUM |
| `liquidation_cascade_entry_v1` | liq_cascade | all regimes | MEDIUM — concept solid |
| `funding_rate_reversion_v1` | funding_rev | all regimes | MEDIUM — Bybit-specific edge |
| `micro_scalper_v1` | micro_scalp | all regimes | LOW — very high frequency, noisy |

**Recommendation:** Consider setting all v7 sleeves to `risk_mult=0.3` (reduced size) in
`portfolio_allocator_policy.json` until at least one passes WF-22.

---

## 📦 ARCHIVE — Not in allocator, not tested

Strategies that exist in `strategies/` but are unused:

| Strategy | Reason |
|----------|--------|
| `alt_range_reclaim_v1` | Never registered |
| `alt_support_reclaim_v1` | Never registered |
| `alt_volume_spike_momentum_v1` | Never registered |
| `alt_vwap_mean_reversion_v1` (vwap_mr) | Registered but disabled (0 trades in tests) |
| `pump_fade_v2`, `pump_fade_v4r` | Old — superseded by new fade logic |
| `pump_fade_simple` | Prototype only |
| `pump_momentum_v1` | Never tested |
| `btc_cycle_*` (4 strategies) | Macro-scale, no 5m backtest framework fit |
| `sloped_break_retest_v1` | Swept but never promoted |
| `btc_sloped_reclaim_v1` | Never tested |
| `btc_swing_zone_reclaim_v1` | Never tested |
| `btc_daily_level_reclaim_v1` | Never tested |
| `btc_regime_*` (2 strategies) | Never tested |
| `btc_weekly_zone_reclaim_v2` | Never tested |
| `funding_hold_v1` | Early prototype, superseded by funding_rev |

---

## Summary scorecard

```
Total strategies: 23 registered sleeves
├── Live & proven:        6  (fade, sloped, bounce, range_scalp, elder_ts_v2, impulse)
├── Live but unproven:    5  (v7 sleeves: breakdown_v2, choch, cascade, funding, micro)
├── Disabled pending WF:  5  (breakdown_v1, att1, hzbo1, elder_v3, inplay_breakout)
├── Broken/needs fix:     2  (midterm_v3, breakdown_v2)
└── Archive:             16+ (unregistered / old versions)

3-day Codex queue targets: promote 3-5 strategies to production
Priority order: breakdown_v1 > inplay_breakout > elder_v3 > att1 > midterm_v3
```
