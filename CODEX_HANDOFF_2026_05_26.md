# Codex Handoff — 2026-05-26

## Session Summary (Claude)

This session completed 3 tasks + produced 2 new full-package sweep configs. Codex verified them against a fixed dataset and moved the heavy runs off the live VPS.

## Codex Addendum — 2026-05-26 Afternoon

- Deployed read-only strict parity check in commit `e339ee2`. The old coverage-only `PASS` masked live drift: effective allocator enables extra sleeves `sloped,asm1` and expands symbols in `att1/flat/breakdown`. Follow-up process-level check corrected the first slot inference: the running account is configured for `MAX_POSITIONS=3`, `leverage=3`, effective risk `0.44%`, while the proven package research uses `5`. Fixed-cache sensitivity quantified this: `1` slot `+30.76% / PF 1.330 / DD 5.68%`; current-style `3` slots `+62.79% / PF 1.478 / DD 5.36%`; `4` slots `+74.41% / PF 1.600 / DD 5.03%` but 3 red months; `5` baseline `+73.96% / PF 1.591 / DD 5.16%` with 2 red months.
- This drift is not yet the direct cause of zero entries: fresh counters still reject before order generation (`breakdown RSI/support`, `flat same_bar/range`, `ATT1 trendline`). It will contaminate performance once signals begin, so any promotion must test strict four-sleeve and slot parity first.
- `package_breakdown_rsi_v1` completed: best accepted `+74.43%`, PF `1.596`, DD `5.16%`, one negative month. `package_arf1_flat_touch_v1` finished `48/48`; winner `r002` (`ARF1_MIN_RSI=48`, `ARF1_REJECT_BELOW_RES_ATR=0.08`, `ARF1_RES_TOUCH_BUFFER_ATR=0.35`) replayed successfully: five slots `+77.57%`, PF `1.646`, DD `5.16%`, 419 trades, 2 negative months; four slots `+76.55%`, PF `1.636`, DD `5.00%`, 423 trades, but 3 negative months. Do not alter live until strict four-sleeve/fixed-symbol policy and capped total risk are reviewed.
- Alpaca trailing fix is on `v38 hybrid top4 monthly paper`, not v39. At `2026-05-26 14:00 UTC`, GOOGL HWM trailing triggered a paper close submission and re-entry block; the `14:30 UTC` gate showed GOOGL absent and no duplicate cleanup while preserving intraday-owned NFLX. Still reconcile ledger/credentials/end-of-cycle before considering `$500`.
- Alpaca intraday v3 is rejected as a capital candidate: 360d backtest `-5.78%`, PF `0.886`, DD `20.64%`, 98 trades.

---

## ✅ Completed This Session

### Task 14 — Setup Screener chart modal upgrade (`web/static/index.html`)
**File:** `web/static/index.html` — `SetupCardChart` function (line ~1717)

The old sparkline (72px, no real value) was replaced with a full-screen `LightweightCharts` candlestick modal.

**What the new modal shows:**
- "График" button opens a `modal-overlay` / `modal-box` (reusing existing CSS)
- Header: `SYMBOL · setup_type  SIDE-BADGE`
- Meta bar: Price | Level (Nx) | Dist ATR | Invalidation | Score | Strategy
- Full candlestick chart from `/api/setup-scanner/chart?symbol=X&interval=Y&limit=120`
- Colored horizontal line at `level_price` (red=short, green=long, lineStyle=1 solid)
- Yellow dashed line at `invalidation` (lineStyle=2)
- Interval switcher: 5m / 15m / 1h / 4h (reloads candles on click)
- Reasons row at bottom: blue "Сигналы:" + reasons.join(' · ')
- Escape key closes; click outside modal closes; ResizeObserver handles window resize
- Chart destroyed on close (no memory leak); data reset so next open reloads fresh

**Why this matters:** Traders can now click any screener card and instantly see the full Bybit chart with the exact resistance/support level and invalidation drawn. This closes the "setup screener has no chart" gap.

---

### Task 15 — Full-package sweep configs for breakdown RSI and flat touch

**Files created:**
- `configs/autoresearch/package_breakdown_rsi_v1.json` — 45 combos (5×3×3)
- `configs/autoresearch/package_arf1_flat_touch_v1.json` — 48 combos (4×4×3)

**Key design:** Both run ALL 4 strategies together (`alt_trendline_touch_v1,alt_resistance_fade_v1,alt_inplay_breakdown_v1,btc_eth_midterm_pullback`) with all non-varying params locked at `crypto_income_static_v1` baseline. This enforces the additivity test — only combos that improve the full package PF advance.

**Old local-cache baseline:** `crypto_income_static_v1`: +70.17%, PF 1.545, DD 6.23%
**Fixed server-dataset baseline (2026-05-26):** +73.96%, PF 1.591, DD 5.16%, 436 trades, 2 red months, streak 1. The original difference was traced to different `.cache/klines` inputs: an isolated local shadow using the exported server cache now reproduces the server result exactly.
**Promotion gate:** replay uses the exact server protocol (`365d`, `end=2026-04-25`, `risk_pct=0.01`, `max_positions=5`, `fees=6bps`, `slippage=2bps`) and must beat `+73.96% / PF 1.591` while keeping `DD <= 5.17%`, negative months `<= 2`, and negative-month streak `<= 1`.

**Breakdown RSI grid:**
- `BREAKDOWN_RSI_MAX`: [50, 53, 55, 58, 60]
- `BREAKDOWN_LOOKBACK_H`: [36, 48, 60]
- `BREAKDOWN_REGIME_MIN_ER`: [0.10, 0.15, 0.20]

**ARF1 flat touch grid:**
- `ARF1_MIN_RSI`: [48, 50, 52, 55]
- `ARF1_REJECT_BELOW_RES_ATR`: [0.08, 0.10, 0.12, 0.16]
- `ARF1_RES_TOUCH_BUFFER_ATR`: [0.25, 0.35, 0.45]

**Runtime note:** these are annual full-package runs. A server attempt reduced available RAM to ~63 MB on the 1 GB live VPS and was stopped. Run this queue locally from `/private/tmp/bybot_server_shadow_20260526` in `screen`/`caffeinate`; do not run it on the live bot server.

---

### Task 16 — Server health monitor (`scripts/monitor.py`)

**File:** `scripts/monitor.py`

Python 3 operator dashboard complementing `scripts/server_status.sh` with sections `server_status.sh` doesn't cover:

| Section | What it shows |
|---|---|
| BOT PROCESS | systemd active + heartbeat age/uptime/open_trades/ws/regime |
| REGIME | regime + confidence + pending + file age |
| SLEEVES | Per-strategy health gate: OK / WATCH / PAUSE / KILL, explicitly marked historical when the snapshot is stale |
| CONTROL PLANE | File freshness for 6 key state files + allocator degraded/safe_mode/risk_mult |
| LOG ERRORS | Grep timestamped last-1h lines of `runtime/live.out` for ERROR/CRITICAL/Traceback; ignores undated tail noise and deduplicates by fingerprint |

**Usage:**
```bash
# On server:
python3 scripts/monitor.py

# From local machine via SSH:
SERVER_IP=64.226.73.119 python3 scripts/monitor.py --ssh

# Machine-readable (for cron alerting):
python3 scripts/monitor.py --json
# Returns: {"severity": 0|1|2, "healthy": true|false, "ts": 1234567890}
# Exit code: 0=healthy, 1=degraded, 2=critical
```

**Suggested cron (on server):**
```cron
*/5 * * * * python3 /root/by-bot/scripts/monitor.py --json >> /root/by-bot/runtime/monitor_status.json.tmp && mv /root/by-bot/runtime/monitor_status.json.tmp /root/by-bot/runtime/monitor_status.json
```

---

## 🔜 Pending / Codex Tasks

### P0 — Crypto unfreeze (needs Codex)

1. **Full-package ARF1 challenger is validated in research, not deployed:**
   - `package_breakdown_rsi_v1` best accepted: `+74.43%`, PF `1.596`, DD `5.16%`, 1 red month
   - `package_arf1_flat_touch_v1` winner `r002` repeated at five slots: `+77.57%`, PF `1.646`, DD `5.16%`, 2 red months
   - Four-slot replay: `+76.55%`, PF `1.636`, DD `5.00%`, but 3 red months; prefer five-slot challenger for the next shadow check
   - Next step is a strict fixed-symbol/four-sleeve five-slot policy shadow with capped aggregate risk; do not change crypto live from research output alone

2. **ATT1 short slope sweeps** — run after v3:
   - `att1_short_slope_v1.json` (18 combos, exploratory)
   - `att1_density_v4_slope.json` (288 combos, full grid)

3. **ATT1 r259 confirmed REJECTED** — solo +38.48%, PF 1.386, DD 3.97% BUT hurt full package (PF 1.386 vs 1.545). Do not deploy.

### P1 — Alpaca fix (needs Codex)

- **Alpaca v39 failed bear-2022**: -23.47%, PF 0.415, DD 27.66%
- Root cause: no regime gate — strategy runs in all conditions
- Fix options:
  1. Add bear regime gate (same as crypto: disable equity shorts in bear_trend/bear_chop)
  2. Add defensive mode: widen SL in bear regimes, shrink position size
  3. Sector cap: max 2 positions per sector (prevents concentration)
- **Action for Codex**: Run Alpaca v4 vs v3 backtest comparison across 2022/2023/2024/2025 to establish baseline, then add regime gate and test

### P2 — Research queue (can run in background)

- `arf1_filter_v1.json` — 128 combos for ARF1 param tuning (symbols: LINK/LTC/SUI/DOT/ADA/BCH)
- `att1_density_v4_slope.json` — 288 combos (after v3 completes)
- BRC1 360d sweep — run and check additivity vs baseline

### P3 — Live bot re-enablement decision

- Current: `regime=bear_chop`, `open_trades=0`, bot is running but not trading
- Research result is now available: ARF1 `r002` improves the full proven package at five slots
- Live env stays at current baseline until strict policy/symbol parity and aggregate risk sizing are explicitly reviewed
- Keep Claude strategy-semantic changes such as `MTPB_USE_RUNNER_EXITS=1` in challenger/replay until measured as part of a full package

---

## Files Modified This Session

| File | Change |
|---|---|
| `web/static/index.html` | Replaced `SetupCardChart` sparkline with full LightweightCharts modal |
| `configs/autoresearch/package_breakdown_rsi_v1.json` | NEW — 45-combo full-package breakdown sweep |
| `configs/autoresearch/package_arf1_flat_touch_v1.json` | NEW — 48-combo full-package ARF1 flat touch sweep |
| `scripts/monitor.py` | NEW — Python operator dashboard (sleeves health + log errors + exit codes) |

---

## Sweep Run Order for Codex

```
Phase 1 (now, can parallel):
  att1_short_slope_v1            18 combos  ~5 min
  att1_density_v3_more_pivots_v1 864 combos ~45 min (may already be running)
  arf1_filter_v1                 128 combos ~30 min

Phase 2 (after v3 completes):
  att1_density_v4_slope          288 combos ~35 min
  package_breakdown_rsi_v1       45 combos  bounded overnight job
  package_arf1_flat_touch_v1     48 combos  bounded overnight job

Phase 3 (after package sweeps):
  Full-package replay of any winners from Phase 2
  If PF > 1.545 AND DD ≤ 6.5%: promote to live env
```
