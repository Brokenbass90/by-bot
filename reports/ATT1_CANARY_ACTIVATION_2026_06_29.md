# ATT1 short-only canary — ACTIVATION + 48h watch (2026-06-29)

Owner gave explicit GO: "включай ATT1 canary". This is the first live crypto risk.
Tiny by design. Claude can't touch the server — Codex executes; owner watches.

## Codex — activate (operator override, no hand-editing strategy_pause.env)
```bash
cd /root/by-bot
# server-only env that the operator-override layer loads on top of live .env:
#   ALLOW_OPERATOR_LIVE_OVERRIDES=1
#   OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env
# then restart the service
systemctl restart bybot.service   # or the project's restart script
```

## Verify heartbeat BEFORE walking away (all must be true)
- `risk_mult.att1 = 0.10`  (was 0.0)
- `att1` side = short only (ATT1_ALLOW_LONGS=0, ATT1_ALLOW_SHORTS=1)
- `flat / range / breakdown / asb1 / elder = 0.0`  (nothing else un-paused)
- `att1_breaker.enabled = true`  (auto-rollback armed)
- `ATT1_MAX_OPEN_TRADES = 3`  (stack_comparison: cap>=3 doesn't strangle)
- `open_trades = 0`, `trade_on = true`, `dry_run = false`, regime `bear_chop`

## What "healthy first 48h" looks like
- A handful of short signals on the dynamic short universe; entries with broker SL.
- Per-trade risk ~ $0.05 (0.10 mult x 0.5% of ~$100). P&L in cents — this is a
  PROOF of the live loop, not income. Don't judge edge on a few trades.
- Live slippage/fees per trade roughly match backtest assumptions (6/2 bps).

## Auto-rollback (already wired — no action needed, just know it)
`bot/strategy_breaker.py` will hard-pause ATT1 (risk->0) if ANY:
- realized net <= ATT1_BREAKER_HARD_NET_PNL (-3.0) over >=6 closes;
- ATT1_BREAKER_MAX_CONSEC_LOSSES (5) in a row;
- canary expiry ATT1_CANARY_EXPIRY_UTC (2026-07-20) reached.
Soft-cut to x0.5 at net <= -1.5. TG alert on each.

## Manual rollback (if you want out early)
Set ATT1_RISK_MULT=0.0 in the override env + restart. No code revert needed.

## Scale-up gate (later, not now)
Only raise risk_mult toward 0.25 if after ~30 days / 50+ live trades ATT1 shows
positive expectancy (Sharpe>0) on LIVE — not backtest. Otherwise hold or rollback.

## Next canary in line
ARF2 (rebuilt saw / resistance-fade) — promoted ONLY after its full sweep + WF
(>=3/4 windows +, PF>1 after fees, <=3 red months). Then add as ATT1 diversifier.
