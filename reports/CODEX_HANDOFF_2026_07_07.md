# CODEX HANDOFF 2026-07-07

## Live Money Truth
- Bybit live money remains `ATT1 short r001 risk_mult=0.10`.
- Open Bybit position at fresh VPS runtime check (`2026-07-07 12:00 UTC`): `ADAUSDT Sell`, size `138`, entry `0.189137`, current about `0.1775`, exchange `stopLoss=0.1893`, exchange TP empty, uPnL about `+1.61 USDT`.
- Important correction: current runtime row says `tp_model=none`, `runner.enabled=false`, `runner.targets=[]`, breakeven/trailing/time-stop disabled. Exchange SL is near breakeven, not a profit-lock stop. Do not tell the owner this specific live ADA remainder is trailing/runner-protected until live core is flat/restarted and verified.
- VPS `restart_when_flat_20260706` waits for 5 flat confirmations before restarting `bybot.service`. Do not restart live core manually while ADA runner is open unless owner explicitly approves.
- Alpaca live v38 is active on real endpoint with about `$496` equity, `$149` cash/BP, positions `SNOW`, `GE`, `ABBV`, `BAC`; all have broker-side simple stop orders. Fractional positions currently skip native trailing.

## Web / Observability
- Web was updated and VPS fast-forwarded to `4f996e0`.
- Sidebar now has `Systems -> Live Position`, direct page `/position.html`.
- Follow-up fix on disk: `web/main.py` now serves `/position.html` before the SPA catch-all. Before this fix, the URL changed but FastAPI returned `index.html`, so the owner still saw Dashboard.
- Latest web fix: `/position.html` now serves the SPA shell, which selects `Live Position`; the detailed standalone panel is embedded as `/static/position.html`. `X-Frame-Options=SAMEORIGIN` allows same-origin embedding. The candle chart avoids array-spread min/max over large candle sets to prevent `RangeError: Maximum call stack size exceeded`.
- New observability patch on disk: `bot/position_view.py` emits `exit_state`/`runner_state` and warning labels (`no_tp_plan_visible`, `profit_not_locked`, `runner_disabled`, `trailing_disabled`); headline `R` is hidden when computed from tiny current-SL risk instead of original risk. `/static/position.html` displays those warnings and passes Alpaca positions + recent events into AI chat context.
- Web restart touched only `uvicorn`; live trading process was not restarted.
- If owner says "web does not show trades", first check that they clicked `Live Position`, not `Sweeps`. Dashboard also shows live positions; Sweeps page only shows autoreserach sweep jobs.

## Research Status
- Inplay maker-fill strict gate: FAIL but close. Best `offset=0.4`, `validity=24`, stress `84 trades`, `+6.46R`, `PF=1.173`, unfilled `25.66%`, concentration `0.255`; failed prereg `PF>=1.2` and `3/4` positive folds (`2/4`).
- Inplay dynamic selector was stopped after hours of mostly `0-1` future trades and FAIL rows. Current inplay-maker implementation is not promotable; freeze until `level_memory`/entry-filter repair or redesigned gate.
- MRB crypto mean-reversion exploration added: `scripts/run_crypto_mrb_exploration_20260707.py`. Baseline and three quick variants all FAIL as broad baskets; baseline `1516` trades, net `-146.72R`, PF `0.843`, positive folds `0/4`. Do not promote "pila" as a generic basket. If revisited, require causal symbol-selection, not cherry-picked top symbols.
- FX H1 exploration completed with no capital-ready row. Best diagnostic seed was `XAUUSD trend_retest_session_v2` under soft exploration, but it is not promotion-grade; most EURUSD/GBPUSD/USDJPY range/sweep/trend rows were negative.
- Added `scripts/run_crypto_level_memory_sweep_reclaim_20260707.py` (research-only): H1 level sweep/reclaim gated by `level_memory`, long/short, cached data only. Smoke on BTC/ETH/ADA/SUI/DOGE 180d gave `24` trades, net `+4.93R`, PF `1.40`, 2/4 folds, not PASS due tiny sample. Full local screen is running: `crypto_lm_sweep_reclaim_20260707` over 24 symbols/360d.
- Funding-carry maximizer on a single old live scan showed attractive annualized diagnostics but `GO=0%`; needs 180d funding history gate before sleeve discussion.
- FX/CFD data backfill completed. Six symbols passed M5 preflight: `EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD`.
- FX/CFD multi-strategy gate completed with no capital-ready candidate. Best diagnostic row: `EURJPY liquidity_sweep_bounce_session_v1`, `21` trades, stress `+8.48` pips, but estimated return/recent quality are not good enough. Native H1 harness skipped all pairs under strict gap coverage.

## External Advisor / DeepSeek Decisions
- Accepted: split the pipeline into `Exploration` and `Validation/Promotion`.
- Accepted: add exploration queue for `Mean Reversion Basket`, `FX H1 trend/session breakout`, `XAU range-bounce`, and `OI/funding carry`.
- Accepted: Weekly Allocator spec that proposes risk_mult changes from edge_monitor, with owner approval before live changes.
- Rejected: deleting 71 strategies immediately. Only archive after inventory and references are mapped.
- Rejected: relaxing canary/live gates just because the project needs trades. `Exploration` can be soft; live money remains strict.
- Rejected: "Inplay shadow now" unless dynamic selector reaches a softer but preregistered shadow bar, e.g. `3/4 folds` and `PF>1.15`, or a new level_memory A/B validates it.

## Priority Bets After Owner Review
1. `ATT1 exit/re-entry A/B`: current live ADA proves the entry family can catch a move, but the exit model is too passive after TP1. Test profit-lock-after-TP1, tighter ATR trail, larger TP1 fraction, and retest-exit/re-entry before changing live behavior.
2. `Level-memory range/sweep/reclaim`: keep the "pila"/range idea, but broad MRB failed. Next version must combine range scan + level respect score + causal symbol selection + regime direction guard. Build both long and short variants; separate horizontal and sloped levels.
3. `FX/XAU H1 range/sweep/session`: data is research-ready; first exploration did not pass for capital. Treat it as parallel discovery/redesign, not capital deployment. Capital only after clean OOS/demo gate.

Inplay maker is not the next live sleeve right now: fill rate was acceptable, but stability/time folds and dynamic selector quality were weak. Freeze until entry-quality repair or level_memory A/B.

## Next Work Order
1. Inspect full `crypto_lm_sweep_reclaim_20260707` output. If it improves the smoke result with enough trades/folds, design a strict validation pass; otherwise keep level_memory as a filter and redesign entry/exit.
2. Start ATT1 exit A/B research: current live ADA exposed the weak point. Variants: profit-lock-after-TP1, tighter ATR trail, larger TP1 fraction, retest-exit/re-entry.
3. Continue Exploration pack, not live:
   - `FXH1/XAU`: redesign from the completed exploration result, focusing on XAU trend-retest and session/sweep filters.
   - `OIFC1 OI-weighted funding carry`: funding + OI/liquidation filters.
4. Add exploration-mode config/API to `oos_selector` or a wrapper: soft pass labels only, never canary promotion.
5. Add a stop-truth reconciliation watchdog: if local runner desired SL differs from exchange SL for >N minutes, alert and do not mislabel it as exchange stop.
6. Update owner-facing daily digest with "next expected catalyst": active run ETA, next market open, or next owner decision.

## Do Not Do
- Do not raise Bybit risk or use `3x/full balance` until there are at least 2 live sleeves and 2 weeks positive P&L.
- Do not manually close/move ADA unless owner explicitly approves a concrete action.
- Do not run heavy research on VPS; local Mac only.
- Do not use `reset --hard` on VPS dirty worktree.
