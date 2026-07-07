# CODEX HANDOFF 2026-07-07

## Live Money Truth
- Bybit live money remains `ATT1 short r001 risk_mult=0.10`.
- Open Bybit position at last direct REST check: `ADAUSDT Sell`, size `138`, entry `0.18913665`, exchange `stopLoss=0.1893`, exchange TP empty, uPnL about `+1.37 USDT`.
- Important: exchange SL is near breakeven, not a profit-lock stop. Runtime/local runner may display a lower internal SL (`~0.1789`), but exchange truth wins. Protective-stop fix is on disk and will apply after flat/restart.
- VPS `restart_when_flat_20260706` waits for 5 flat confirmations before restarting `bybot.service`. Do not restart live core manually while ADA runner is open unless owner explicitly approves.
- Alpaca live v38 is active on real endpoint with about `$496` equity, `$149` cash/BP, positions `SNOW`, `GE`, `ABBV`, `BAC`; all have broker-side simple stop orders. Fractional positions currently skip native trailing.

## Web / Observability
- Web was updated and VPS fast-forwarded to `4f996e0`.
- Sidebar now has `Systems -> Live Position`, direct page `/position.html`.
- Web restart touched only `uvicorn`; live trading process was not restarted.
- If owner says "web does not show trades", first check that they clicked `Live Position`, not `Sweeps`. Dashboard also shows live positions; Sweeps page only shows autoreserach sweep jobs.

## Research Status
- Inplay maker-fill strict gate: FAIL but close. Best `offset=0.4`, `validity=24`, stress `84 trades`, `+6.46R`, `PF=1.173`, unfilled `25.66%`, concentration `0.255`; failed prereg `PF>=1.2` and `3/4` positive folds (`2/4`).
- Inplay dynamic selector is still running locally (`screen=inplay_maker_dynsel_overnight_20260706`); early rows are mostly `0-1` trades and FAIL. Do not promote before final verdict.
- FX/CFD data backfill completed. Six symbols passed M5 preflight: `EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD`.
- FX/CFD multi-strategy gate completed with no capital-ready candidate. Best diagnostic row: `EURJPY liquidity_sweep_bounce_session_v1`, `21` trades, stress `+8.48` pips, but estimated return/recent quality are not good enough. Native H1 harness skipped all pairs under strict gap coverage.

## External Advisor / DeepSeek Decisions
- Accepted: split the pipeline into `Exploration` and `Validation/Promotion`.
- Accepted: add exploration queue for `Mean Reversion Basket`, `FX H1 trend/session breakout`, `XAU range-bounce`, and `OI/funding carry`.
- Accepted: Weekly Allocator spec that proposes risk_mult changes from edge_monitor, with owner approval before live changes.
- Rejected: deleting 71 strategies immediately. Only archive after inventory and references are mapped.
- Rejected: relaxing canary/live gates just because the project needs trades. `Exploration` can be soft; live money remains strict.
- Rejected: "Inplay shadow now" unless dynamic selector reaches a softer but preregistered shadow bar, e.g. `3/4 folds` and `PF>1.15`, or a new level_memory A/B validates it.

## Next Work Order
1. Finish/inspect `inplay_maker_dynsel_overnight_20260706`. If no policy hits `3/4 folds` and `PF>1.15`, freeze Inplay until `level_memory` integration.
2. Register and run Exploration pack, not live:
   - `MRB1 crypto mean-reversion basket`: rolling liquid mid-caps, z-score, 1.5 ATR SL, 2 ATR TP.
   - `FXH1 trend/session breakout-retest`: EURUSD, GBPUSD, USDJPY.
   - `XAU range-bounce`: H1 range detector with spread/session gate.
   - `OIFC1 OI-weighted funding carry`: funding + OI/liquidation filters.
3. Add exploration-mode config/API to `oos_selector` or a wrapper: soft pass labels only, never canary promotion.
4. Add a stop-truth reconciliation watchdog: if local runner desired SL differs from exchange SL for >N minutes, alert and do not mislabel it as exchange stop.
5. Update owner-facing daily digest with "next expected catalyst": active run ETA, next market open, or next owner decision.

## Do Not Do
- Do not raise Bybit risk or use `3x/full balance` until there are at least 2 live sleeves and 2 weeks positive P&L.
- Do not manually close/move ADA unless owner explicitly approves a concrete action.
- Do not run heavy research on VPS; local Mac only.
- Do not use `reset --hard` on VPS dirty worktree.
