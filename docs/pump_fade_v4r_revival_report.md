# pump_fade Revival — Research Report
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
**Assessment:** Moderate complexity. The RSI-peak detection via historical slice is fragile. Not the baseline winner.

### v4 — Climax exhaustion wick ✅ Initially chosen, then invalidated
**Logic:** pump → peak candle must have large upper wick (≥32% of range) + small body (≤55% of range) + volume climax → price breaks below exhaustion candle's low.
**Assessment:** Mechanically clean pattern, but **wrong mode for this baseline**. See below.

### v5 — Dump → lower-high bounce → support break
**Logic:** pump → initial dump → bounce retraces 25-80% → lower high forms → support break.
**Assessment:** Too slow for pumpy alts. Better suited for BTC/ETH on larger timeframes.

### v6 — v5 on 15m aggregated bars + 5m trigger
**Assessment:** Multi-timeframe approach with edge artifacts from 5m→15m aggregation. Too experimental.

---

## Critical Finding: Baseline Was BASE Mode, Not v4

### What We Thought
- Baseline used `pf_v4c_240d` tag → assumed v4 (climax wick mode)
- Launched 243-combo v4 autoresearch on liquid alts (DOGE, PEPE, SOL, SUI, etc.)

### What Baseline Actually Was
Inspection of `baselines/pump_fade_v4c_240d/trades.csv` trade reasons:
```
"pump 21.3%/120m then reversal"   ← BASE mode format, NOT v4
"pump 8.9%/120m then reversal"
"pump 6.4%/120m then reversal"
```
The `v4` in `pf_v4c_240d` referred to a *commit tag*, not the v4 strategy variant.

**The baseline used BASE mode with 120m pump window on micro-cap meme coins.**

### Autoresearch v4r Result
- **243/243 combos completed, 0 passing** (best: PF=0.247, 2 trades)
- Correct diagnosis: exhaustion wick is too rare on liquid alts in this period
- v4 is correct pattern for select conditions but not the source of the baseline edge

---

## Structural Bugs Found

### Bug 1 (FIXED in pump_fade_v4r.py): Cooldown non-functional for v4/v5/v6 modes
In `archive/strategies_retired/pump_fade.py`, the cooldown decrement at line 1045 is placed **after** the v3/v4/v5/v6 dispatch. Since v4 returns early at line 1038, the cooldown counter was set by `_emit_short_signal` but **never decremented**, making post-trade cooldown completely skip for v4.

**Fix in `pump_fade_v4r.py`:** Moved cooldown check to before the v3/v4/v5/v6 dispatch.

### Bug 2 (FIXED): Dead code — unreachable `return None`
Line 1177 in archive: `return None` after `return sig`. Unreachable. Removed.

### Discovery: Archive BASE Mode ≠ Baseline Code
The archive version (`archive/strategies_retired/pump_fade.py`, 1191 lines) has many additional filters added after the baseline commit:
- `PF_USE_EXHAUSTION_FILTER` — extra gate that didn't exist in baseline
- `PF_CONFIRM_BARS` — multi-bar reversal confirmation (baseline was single-bar)
- `PF_REVERSAL_BODY_MIN_FRAC` — body fraction check (not in baseline)
- `ENTRY_TOO_EARLY` gate — min drop from peak (not in baseline)
- `leg_pct` computation — shortleg momentum gate (not in baseline)
- `move_ref = max(c, window_high)` — archive uses max of close vs window high; baseline used only close

The baseline was the simple 190-line `strategies/pump_fade.py` at commit `e341055e`.

---

## Correct Approach: pump_fade_simple

Created `strategies/pump_fade_simple.py` — **exact verbatim copy of the baseline code** (commit e341055e), with class renamed from `PumpFadeStrategy` → `PumpFadeSimpleStrategy` to avoid collisions with the archive.

**Logic (190 lines):**
1. Pump detection: `(c / base_close_24bars_ago) >= pump_threshold_pct`
2. `_pumped_flag` stays True until trade or >8% drop from recent peak
3. Entry gate: RSI ≥ rsi_overbought (default 75) at the reversal bar
4. Reversal trigger: `c < EMA9 AND c < prev_close`
5. Stop: `peak_high * (1 + stop_buffer_pct)`
6. TP: `entry - rr * risk`

---

## Files Changed

| File | Action | Note |
|------|--------|------|
| `strategies/pump_fade_v4r.py` | **CREATED** | Revival copy with v4_enable=True default, cooldown fix, dead code removed |
| `strategies/pump_fade_simple.py` | **CREATED** | Exact baseline logic (commit e341055e), renamed class |
| `backtest/run_portfolio.py` | **MODIFIED** | Registered `pump_fade_v4r` and `pump_fade_simple` (import, allowed, dict, signal loop) |
| `configs/autoresearch/pump_fade_v4r_alts.json` | **CREATED** | 243-combo spec, pumpy alts, completed — 0 passing combos |
| `configs/autoresearch/pump_fade_base_meme.json` | **CREATED** | 486-combo spec for archive BASE mode — invalidated (archive ≠ baseline code) |
| `configs/autoresearch/pump_fade_simple_meme.json` | **CREATED** | ✅ Correct spec: 486 combos using pump_fade_simple on meme coins |
| `archive/strategies_retired/pump_fade.py` | **NOT TOUCHED** | Historical record preserved |
| Live bot files | **NOT TOUCHED** | Research-only branch |

---

## Autoresearch Spec to Run

**File:** `configs/autoresearch/pump_fade_simple_meme.json`
**Strategy:** `pump_fade_simple` (exact baseline code)
**Symbols basket 1:** MYXUSDT, RIVERUSDT, AZTECUSDT, ENSOUSDT, PIPPINUSDT, VVVUSDT, DOGEUSDT, 1000PEPEUSDT
**Symbols basket 2:** MYXUSDT, RIVERUSDT, AZTECUSDT, ENSOUSDT, PIPPINUSDT, VVVUSDT, ARBUSDT, ENAUSDT
**Period:** 240 days ending 2026-02-24
**Combos:** 486 (2 baskets × 3^4 grid)

Grid parameters:
- `PF_PUMP_WINDOW_MIN`: 90, 120, 150 — pump lookback (baseline: 120m)
- `PF_PUMP_THRESHOLD_PCT`: 0.06, 0.08, 0.10 — pump strength (baseline: 0.08)
- `PF_RSI_OVERBOUGHT`: 70, 75, 80 — RSI gate at entry (baseline: 75)
- `PF_RR`: 1.4, 1.7, 2.1 — reward/risk ratio (baseline: 1.6)

Fixed: cooldown=24 bars, stop_buffer=0.25%, cache_only=true
Constraints: min_trades=10, min_PF=1.50, max_DD=7.0%, min_net=+3.0%

**To run (from your local terminal):**
```bash
cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_simple_meme.json \
  > /tmp/pf_simple_autoresearch.log 2>&1 &
echo "PID: $!"
```

> **Note:** Must run from your local machine — the VM's `.cache/klines/` is incomplete
> (files contain only the most recent ~11 days per symbol, not full 240-day history).
> Autoresearch will use your local cache with full historical data.

---

## Decisions

### v4r
- **Result: FAILED.** 0/243 combos pass. Archive v4 is correct logic but wrong universe for this period (requires more liquid coins, different time window).
- **Verdict: Archive.** Keep `pump_fade_v4r.py` for future research on different universes/periods.

### pump_fade_simple (baseline resurrection)
- **Status: Ready to run.** Strategy created, registered, autoresearch spec ready.
- **Deploy condition:** ≥5 combos passing + at least 1 with trades ≥15 and PF ≥1.6
- **Stop condition:** <3 combos passing → edge too narrow, archive this revival

### Key open question
The baseline got 5 trades from AZTECUSDT. In all our VM runs, AZTECUSDT shows 0 trades because the `.cache/klines/` file only has the last 11 days of data (Feb 12-23, 2026) with no pre-pump history. The full autoresearch on your local machine should resolve this — AZTECUSDT had multiple strong pump-revert events in Q3-Q4 2025 (pre-listing period where data was cached).
