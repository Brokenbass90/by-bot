# pump_fade v4 Revival — Research Report
**Date:** 2026-03-27 | **Branch:** codex/dynamic-symbol-filters (research-only)

---

## Baseline

`baselines/pump_fade_v4c_240d/summary.csv`:
- **Net PnL:** +7.81% on $100 equity
- **Profit Factor:** 1.883
- **Trades:** 19 over 240 days (25 symbols)
- **Win Rate:** 42.1%
- **Avg Win / Avg Loss:** $2.08 / $0.80 = 2.6× ratio
- **Max Drawdown:** 3.77%

The edge is real but low-frequency (~1 trade/13 days per 25-symbol universe).

---

## Analysis of v3 / v4 / v5 / v6

### v3 — Peak momentum loss + re-entry
**Logic:** pump → RSI overbought at peak (≥74) → RSI fades to <60 → bearish reversal bars + volume fade.
**Assessment:** Moderate complexity. The RSI-peak detection via historical slice is fragile (can give NaN if history too short). More filters than v4, but the entry trigger (RSI drop + bearish bars) is less precise than a wick signature. Not the baseline winner.

### v4 — Climax exhaustion wick ✅ **CHOSEN**
**Logic:** pump → peak candle must have large upper wick (≥32% of range) + small body (≤55% of range) + volume climax → price breaks below exhaustion candle's low.
**Assessment:** The most mechanically clean pattern. The wick shape is a concrete, visual exhaustion signal (institutional sellers absorbing retail buy pressure). The fail-break confirmation (price closes below the exhaustion low) adds a second gate. v4_rsi_max=58 ensures cooling has begun. This is why the baseline used v4.

### v5 — Dump → lower-high bounce → support break
**Logic:** pump → initial dump → bounce retraces 25-80% → lower high forms → support break.
**Assessment:** More complete distribution structure, but requires 3 phases to play out on 5m bars. For alt-coin pumps (which can fully collapse in 1-2 hours), by the time v5 confirms, the move is often over. Too slow for pumpy alts. Better suited for BTC/ETH on larger timeframes.

### v6 — v5 on 15m aggregated bars + 5m trigger
**Logic:** v5 structure on 3×5m=15m bars, then 5m break-of-support trigger candle.
**Assessment:** Clever multi-timeframe approach. But the 15m aggregation from 5m raw bars introduces edge artifacts (bar boundaries don't align with natural 15m opens). For pumpy alts, volume patterns in the aggregated bars can be misleading. Too experimental for a first autoresearch pass.

---

## Structural Bugs Found

### Bug 1 (FIXED): Cooldown non-functional for v4/v5/v6 modes
In `archive/strategies_retired/pump_fade.py`, the cooldown decrement at line 1045 is placed **after** the v3/v4/v5/v6 dispatch. Since v4 returns early at line 1038, the cooldown counter was set by `_emit_short_signal` but **never decremented**, making post-trade cooldown completely skip for v4.

**Impact:** In the baseline test (19 trades over 240 days), this probably didn't matter much because pump conditions naturally prevent re-entry. But in softer parameter combos it could cause double-entries.

**Fix in `pump_fade_v4r.py`:** Moved cooldown check to before the v3/v4/v5/v6 dispatch.

### Bug 2 (FIXED): Dead code — unreachable `return None`
Line 1177 in archive: `return None` after `return sig`. Unreachable. Removed.

### Non-issue: bearish confirmation direction check (line 1158)
Initially suspicious: `if i > 1 and self._closes[-i] < self._closes[-(i-1)]: bearish_ok = False`. This correctly checks that closes are descending over time (older bar below newer → price going up → fail). Not a bug.

---

## Files Changed

| File | Action | Note |
|------|--------|------|
| `strategies/pump_fade_v4r.py` | **CREATED** | Revival copy with v4_enable=True default, cooldown fix, dead code removed |
| `backtest/run_portfolio.py` | **MODIFIED** | Registered `pump_fade_v4r` (import, allowed, dict, signal loop) |
| `configs/autoresearch/pump_fade_v4r_alts.json` | **CREATED** | 243-combo spec, pumpy alts, cache_only=true |
| `archive/strategies_retired/pump_fade.py` | **NOT TOUCHED** | Historical record preserved |
| Live bot files | **NOT TOUCHED** | Research-only branch |

---

## Autoresearch Spec Summary

**File:** `configs/autoresearch/pump_fade_v4r_alts.json`
**Strategy:** `pump_fade_v4r` (v4 only, cooldown fixed)
**Symbols:** DOGEUSDT, 1000PEPEUSDT, SOLUSDT, SUIUSDT, ADAUSDT, LINKUSDT, ARBUSDT, XRPUSDT, ENAUSDT, TAOUSDT
**Period:** 270 days ending 2026-02-24 (~Sep 2025 – Feb 2026)
**Combos:** 243 (3^5 grid)

Grid parameters:
- `PF_V4_PUMP_THRESHOLD_PCT`: 0.07, 0.10, 0.13 — pump strength gate
- `PF_V4_EXHAUSTION_WICK_MIN_FRAC`: 0.25, 0.32, 0.42 — wick quality
- `PF_V4_PEAK_RECENT_BARS`: 6, 10, 16 — peak freshness
- `PF_V4_RSI_MAX`: 50, 58, 66 — entry RSI ceiling
- `PF_V4_RR`: 1.8, 2.1, 2.5 — reward/risk ratio

Fixed: `PF_V4_ENABLE=1`, `PF_COOLDOWN_BARS=20`, `cache_only=true`
Constraints: min_trades=8, min_PF=1.40, max_DD=8.0%, min_net=+3.0%

**To run (from your local terminal):**
```bash
cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_v4r_alts.json \
  > /tmp/pf_v4r_autoresearch.log 2>&1 &
echo "PID: $!"
```

---

## Should You Continue This Branch?

**Yes — conditionally.** The edge is real (PF=1.88 in baseline). Key questions autoresearch will answer:

1. **Does the cooldown fix change things?** If yes, the baseline trade count and PF may shift. We'll know from comparing autoresearch results to the v4c baseline.
2. **Is the edge from the wick gate or the pump strength?** The `PF_V4_EXHAUSTION_WICK_MIN_FRAC` sweep will show if loosening the wick requirement increases trades without killing PF.
3. **Is DOGE/PEPE the real source?** With 10 symbols, if 80% of wins come from 2-3 coins, you may want a tighter allowlist.

**Stop condition:** If autoresearch finds <3 parameter sets meeting constraints, the edge is too narrow to deploy. Archive the revival and move on.

**Deploy condition:** ≥5 combos passing constraints + at least 1 with trades ≥15 and PF ≥1.6 → write deploy spec + enable `ENABLE_PUMP_FADE_TRADING=1`.
