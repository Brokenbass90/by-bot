# Alpaca $500 LIVE canary — Go/No-Go (2026-06-29)

Sleeve: **monthly v38 hybrid top4** (`scripts/equities_alpaca_paper_bridge.py`)
Author: Claude (central). Deploy/recheck: Codex + owner. I cannot reach the VPS or place orders — owner executes every money step.

---

## Verdict: CONDITIONAL GO

Code-side safety is verified and solid. Real money may go live **today** once 5 owner-side server checks pass (below). If any fails → NO-GO, stay on paper.

Honest framing: this first $500 is a **pipeline-proof milestone** (real fills + broker-side protection working), not an income event. The v38 evidence is strong but small-sample (35 trades / 24 months). Treat it as proving the rails, with bounded downside.

---

## What I verified locally (done)

1. **Fail-closed live guard** (`_live_order_guard_errors`). Live orders are blocked (exit code 6) unless ALL hold: `ALPACA_LIVE_ACCOUNT_ROLE=monthly_v38`, `ALPACA_LIVE_CONFIRM=MONTHLY_V38_LIVE`, `ALPACA_CAPITAL_OVERRIDE_USD` set and ≤ `ALPACA_LIVE_MAX_CAPITAL_USD` (default 500). Paper base_url bypasses the guard (expected). Verified by `tests/test_alpaca_live_order_guard.py`.
2. **Broker-side protection** in `configs/alpaca_v38_hybrid_top4_candidate.env`: `ALPACA_BROKER_PROTECTION_REQUIRED=1` → if the broker stop can't be placed after a buy, the bridge closes the position rather than holding it naked. `MONTHLY_SL_PCT=0.05`, native trailing 3.5%, re-entry block 21d.
3. **Capital cap** in config: `ALPACA_CAPITAL_OVERRIDE_USD=500`, `ALPACA_MAX_POSITIONS=4`, `ALPACA_TARGET_ALLOC_PCT=0.70`.
4. **Pre-flight market-clock check**: new BUYs are skipped if market is closed (avoids accepted-but-unfilled orders).
5. **Tests green**: 12 passed across guard / monthly-trailing / zero-risk-sizing / intraday-slots.

---

## GO conditions — owner/Codex must confirm on the server (gating)

Run on `root@64.226.73.119:/root/by-bot`. ALL must be true for GO.

1. **Live account funded ~$500 and is the intended REAL account**
   - Confirm in Alpaca dashboard: real (not paper) account, buying power ≈ $500, no leftover positions from past tests.
2. **Live API keys are the REAL-money keys** (separate from paper) and stored only in the live env profile, never committed.
3. **Fresh picks exist for today**
   - `cat reports/equities_combo_active_latest.csv` shows current-cycle tickers with a recent timestamp (not stale from weeks ago).
4. **Current paper positions already carry broker stops** (sanity that protection logic works live-like)
   - From latest paper bridge log: every open position has an associated stop order; no naked positions.
5. **No duplicate / stuck open orders** on the live account
   - `open orders` list is clean before first live run.

If 3 (fresh picks) is not ready, run the monthly refresh first, then re-check.

---

## Staged runbook (owner executes; do NOT skip the dry-run)

**Step 0 — backup current env/state**
```bash
cd /root/by-bot
cp configs/alpaca_paper_local.env configs/alpaca_paper_local.env.bak_$(date +%Y%m%d_%H%M)
git status -s
```

**Step 1 — create a LIVE env profile** (do not edit the paper one). Example `configs/alpaca_live_v38.env`:
```
# REAL MONEY — monthly v38 only, capped at $500
ALPACA_BASE_URL=https://api.alpaca.markets
ALPACA_API_KEY_ID=<LIVE_KEY>
ALPACA_API_SECRET_KEY=<LIVE_SECRET>

ALPACA_LIVE_ACCOUNT_ROLE=monthly_v38
ALPACA_LIVE_CONFIRM=MONTHLY_V38_LIVE
ALPACA_LIVE_MAX_CAPITAL_USD=500
ALPACA_CAPITAL_OVERRIDE_USD=500

# pull in the verified v38 sizing + broker protection
# (source configs/alpaca_v38_hybrid_top4_candidate.env in the launcher too)
ALPACA_SEND_ORDERS=0   # DRY-RUN FIRST
```

**Step 2 — DRY-RUN against the LIVE account** (reads real account, places NOTHING because SEND_ORDERS=0):
```bash
set -a; source configs/alpaca_v38_hybrid_top4_candidate.env; source configs/alpaca_live_v38.env; set +a
source .venv/bin/activate
python3 scripts/equities_alpaca_paper_bridge.py 2>&1 | tee logs/alpaca_live_dryrun_$(date +%Y%m%d_%H%M).log
```
Confirm in output: mode shows account is LIVE, intended BUYs are sane tickers, each planned BUY has a stop spec, total intended notional ≤ $500, no errors.

**Step 3 — guard self-test** (prove fail-closed). Temporarily unset confirm and run with SEND_ORDERS=1 → must abort with `alpaca_live_order_guard` (exit 6). Re-set confirm afterward.

**Step 4 — GO LIVE**: set `ALPACA_SEND_ORDERS=1` in `alpaca_live_v38.env`, re-run the command from Step 2 **only after 09:30 ET** (market open).

**Step 5 — verify broker stops within minutes of fills**
```bash
# confirm every new live position has an open stop order; none naked
```

**Step 6 — wire the live profile into the daily cron** only after Step 5 is clean.

---

## Residual risks (honest)

- **Overnight gap**: broker stops use DAY tif and re-arm when the bridge runs; a gap beyond ~5% between runs is unhedged. Bounded by $500 / 4 positions (≈$25 worst-case per position). Acceptable for a canary; flag for later (consider GTC stops).
- **Fractional shares**: Alpaca rejects fractional bracket/trailing orders → bridge uses market entry + immediate simple stop, software-trails fractional. REQUIRED=1 means it closes if the stop can't be set.
- **Small sample edge**: v38 OOS is strong (PF 7.85, max monthly DD −2.28%) but only 15 OOS trades. Don't scale until live cycles confirm.

## Rollback
Set `ALPACA_SEND_ORDERS=0` (or point launcher back to the paper profile) and restart the cron. Manually flatten via Alpaca dashboard if needed. No code revert required — the live profile is additive.
