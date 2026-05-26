# Codex Handoff — 2026-05-26

## Session Summary (Claude)

This session completed 3 tasks + produced 2 new full-package sweep configs. Codex verified them against a fixed dataset and moved the heavy runs off the live VPS.

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

1. **Full-package filters currently running locally** in detached `screen` session `crypto_package_sweeps_20260526`:
   - `package_breakdown_rsi_v1.json` then `package_arf1_flat_touch_v1.json`
   - First breakdown row already failed: `+69.34%`, PF `1.528`, DD `5.38%`, red months `>2`
   - Only deploy if a full-package result beats `+73.96% / PF 1.591` with `DD <= 5.17%` and no extra red months

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
- Waiting on: v3 sweep winner + full package replay confirming improvement
- Live env stays at current baseline until additivity test passes
- `MTPB_USE_RUNNER_EXITS=1` should be added to live `.env` (Codex confirmed safe)

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
