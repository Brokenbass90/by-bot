# Codex Handoff - 2026-05-25

**Session summary**: Claude prepared strategy drafts, a diagnostic tool and sweep configs. Codex validated parameter names and deployment gates; strategy rewrites remain research-only until reviewed and tested.

---

## Verified after Claude follow-up review

- Server diagnostic at 2026-05-25 16:20 UTC: `bybot` healthy, `open_trades=0`, `bear_chop`, allocator `safe_mode=False`; static-v1/live input parity is now `100%`.
- Current live blocker is internal signal conversion, not routing: `breakdown` is dominated by RSI/support, `flat` by touch, `ATT1` by trendline rejection with one signal reaching rounding.
- The main bot already calls `AltBearRegimeContinuationV1Strategy.signal(...)` in its BRC1 live path. Claude's added `maybe_signal(...)` bridge is not a missing-interface live repair.
- Claude's BRC1 indicator changes, ARF1 rewrite/filter flag, Elder rewrite and `btc_eth_midterm_pullback` runner-default change are local challenger code only. In particular, MTPB v1 is part of `crypto_income_static_v1`, so its exit-default change requires a new full-package baseline/challenger replay before any commit or deploy.
- Leave the running server BRC1 sweep as a baseline run against the deployed implementation; do not interpret its results as validation of the local challenger rewrite.
- Prepared diagnostics-only patch: bounded `runtime/signal_decisions.jsonl` for `midterm/att1/flat/breakdown`, summarized by `scripts/build_crypto_setup_blocker_report.py` and passed to onboard DeepSeek context. Deploy only this trace before loosening any filter; sample 2-24h.

---

## P0 — Deploy gate (bot must trade before anything else matters)

### P0-1: Run ATT1 replay with sweep-winner params

**Context**: ATT1 density sweep v3 (864 combos) is still running. Do not select a winner before completion: by checkpoint `415/864`, interim candidates `r394` (`+38.17%`, PF `1.374`, DD `4.00%`) and `r412` (`+38.25%`, PF `1.341`, DD `4.65%`) had already exceeded the earlier `r196`.

**What to do when sweep finishes**:
1. Pull the top-5 combos by score from the sweep output.
2. Run a `crypto_income_static_v1` replay for each (the full package: ATT1 + ARF1 + breakdown + midterm, same dates as sweep — 360 days ending 2026-04-30).
3. Compare against the existing package baseline (`+70.17%`, PF `1.545`, DD `6.23%`); a lower PF is not an improvement merely because it passes an absolute gate.
4. If it improves package quality: update the reviewed approved-params config through Codex deployment, not `.env` ad hoc; restart only after `open_trades=0`, then monitor signals for 48h.

**New sweep config also ready** (run in parallel with v3 or after):
```
configs/autoresearch/att1_density_v4_slope.json
```
This adds `ATT1_SHORT_MAX_POS_SLOPE` as a sweep dimension. 288 combos, ~40 min.

---

### P0-2: Run `att1_short_slope_v1` sweep (focused, fast)

**Context**: Diagnostic confirmed `short_slope_direction` is the #1 real blocker for ATT1 shorts (16.4% of all bars after warm-up). Current live `ATT1_SHORT_MAX_POS_SLOPE=0.5` rejects ascending resistance lines — but bear bounces create valid ascending resistance (lower-high pattern).

**Config**: `configs/autoresearch/att1_short_slope_v1.json`
- 6×3 = 18 implemented combinations after removing ignored env names
- Tests `SHORT_MAX_POS_SLOPE` ∈ [0.5, 0.6, 0.7, 0.8, 1.0, 1.5]
- Locked on optimal density params from v3 best result
- If winner has slope > 0.5: include it in the P0-1 full-package replay. Promote only through reviewed approved-params config if the package baseline improves.

**Queued**: local detached session `att1_slope_after_v3_20260525` waits for `att1_density_20260525` to end, then writes its output to `logs/att1_short_slope_after_v3_20260525.nohup.log`.

---

## P1 — Backtest new strategy code (already written, not deployed)

### P1-1: Elder Revived diagnostic, then WF-22 only if viable

**File**: `strategies/alt_elder_revived_v1.py` (complete rewrite)

**What changed** (critical fixes):
- Added `maybe_signal(store, ts_ms, o, h, l, c, v)` — bot runner can now call it
- O(N) MACD (was O(N²) — caused timeout on live server)
- Outputs `TradeSignal` (was custom dataclass, incompatible with allocator)
- Config via `ELDERREV_*` env vars with `ElderRevivedConfig.from_env()`

**First diagnostic task**:
```bash
python3 backtest/run_portfolio.py \
  --strategies alt_elder_revived_v1 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT \
  --days 360 --end 2026-04-30 \
  --tag elder_revived_diagnostic_360d_20260525 \
  --starting_equity 100 --risk_pct 0.0075 --leverage 1 \
  --max_positions 3 --fee_bps 6 --slippage_bps 2
```
**Gate**: if trades ≥30 and PF >1.15, queue WF-22. If trades <15, inspect/relax Screen 2 RSI in research only. Only add to live if later WF-22 passes.

---

### P1-2: Alpaca v4 draft - wire a research runner before any comparison

**File**: `strategies/alpaca_dynamic_v4_event.py` (new file, v3 untouched)

**What changed**:
- Sharpe-like scoring: `score = (ann_mom / ann_vol) × recency_boost × trend_quality`
- Risk parity sizing: `slot ∝ target_vol / actual_vol`
- `PortfolioGuard`: pauses new entries if drawdown > `ALPACA_MAX_DD_PCT` (default 15%)
- Sector cap: max 2 positions per sector (50+ symbols mapped in `SECTOR_MAP`)
- Hysteresis band: prevents churn when score difference is marginal

**Status**: the draft compiles, but there is currently no `backtest/run_alpaca.py` runner wired for it. Do not call an imaginary command and do not deploy it. First integrate it into an existing Alpaca research runner or add a test-only runner, then compare return, PF, DD, monthly loss count and turnover against v38/v39. Promotion is paper-only after a passed gate.

---

## P2 — Sweep extensions (queue for next server cycle)

### P2-1: ARF1 filter sweep

**Context**: ARF1 live params are `resistance_touch_buffer_atr=0.35, reject_below_res_atr=0.12, min_rsi=58.0`. Blocker report shows `no_res_touch` and `no_reject_back` as dominant.

**Ready config**: `configs/autoresearch/arf1_filter_v1.json`
```json
"grid": {
  "ARF1_RES_TOUCH_BUFFER_ATR": [0.25, 0.35, 0.45, 0.55],
  "ARF1_REJECT_BELOW_RES_ATR": [0.06, 0.09, 0.12],
  "ARF1_MIN_RSI": [55, 58, 62]
}
```
Use `--strategies alt_resistance_fade_v1 --symbols LINKUSDT,LTCUSDT,SUIUSDT,DOTUSDT,ADAUSDT,BCHUSDT`.

---

### P2-2: ATT2 backtest vs ATT1

**File**: `strategies/alt_trendline_touch_v2.py`

ATT2 adds: WLS pivot fitting, adaptive R2 threshold, signal quality score, volume confirm, regime-aware RSI. It is unreviewed research code. Run the same dates and symbols only after code review and unit smoke; if promising, replay within the full package before considering shadow deployment.

---

## P3 — Cron additions (passive income, no strategy risk)

### P3-1: Funding carry executor — blocked for live

**File**: `scripts/funding_carry_executor.py` (exists, not in cron)

Current file is one-legged perp exposure, not hedged carry. It may be evaluated only in `--dry-run`; do not schedule real execution until a spot hedge leg and broker-side protection are implemented and validated.

---

## Diagnostic tool (updated — use this for pre-deploy checks)

```bash
# Full diagnosis on all symbols with ARF1 now working (dotenv fixed)
python3 scripts/diagnose_strategy_filters.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT,SUIUSDT \
  --strategy att1,att2,arf1 \
  --bars 400

# Skip dotenv (CI/server where env is already set)
python3 scripts/diagnose_strategy_filters.py --no-dotenv --strategy att1
```

Run this before and after any param change to confirm the blocker profile shifts as expected.

---

## Files changed this session (all in repo, Codex should pull)

| File | Status | Notes |
|------|--------|-------|
| `strategies/alt_trendline_touch_v2.py` | NEW / UNREVIEWED | ATT1 v2 draft, research-only |
| `strategies/alt_elder_revived_v1.py` | REWRITTEN / UNREVIEWED | Diagnostic backtest only until reviewed |
| `strategies/alpaca_dynamic_v4_event.py` | NEW / UNWIRED | Needs a research runner before backtest |
| `scripts/diagnose_strategy_filters.py` | UPDATED | Dotenv fix, short_slope_direction recommendation |
| `configs/autoresearch/att1_short_slope_v1.json` | NEW | 18-combo focused sweep using implemented env names |
| `configs/autoresearch/att1_density_v4_slope.json` | NEW | 288-combo density+slope sweep |
| `configs/autoresearch/arf1_filter_v1.json` | NEW | 36-combo ARF1 blocker sweep |

---

## Priority order for Codex execution

1. **Wait for v3 sweep** -> run P0-1 package replay -> deploy only if baseline improves.
2. **Queue `att1_short_slope_v1`** as research when compute capacity permits.
3. **Run Elder diagnostic** -> WF-22 only if the initial gate passes.
4. **Queue ARF1 sweep** -> package replay required before any promotion.
5. **Wire Alpaca v4 research runner** -> paper candidate only after backtest gates.
6. **Keep funding carry blocked for live** until hedge and broker-side protection exist.

---

*Prepared from Claude session 2026-05-25 and safety-corrected by Codex. Next session should start from the ATT1 v3 completion status and the Alpaca paper cleanup observation.*
