# Project Journal

> One entry per session. Most recent at top.
> Format: date | who | what was done | key findings | next

---

## 2026-04-10 | Codex (session 35 - flat universe repair + Alpaca contour separation)

**Done:**

- Re-validated live server truth:
  - allocator is `ok`
  - router is `ok`
  - backtest gate is on
  - symbol memory is loaded
  - current regime is fresh, not a 7-day stale orchestrator corpse
- Found the real failure mode inside the first annual `flat` repair:
  - the poison branch was the expanded `BNBUSDT` path
  - not the fade thesis itself
  - not the allocator
- Added [flat_live_universe_repair_v2.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_live_universe_repair_v2.json) without the bad branch and launched it.
- Verified immediate passing rows on the repaired `flat` universe using the narrow alt basket and looser `ARF1` thresholds.
- Synced a looser `ARF1` live canary to the server:
  - `MIN_RSI=52`
  - `REJECT_BELOW_RES_ATR=0.08`
  - `SIGNAL_LOOKBACK=60`
- Patched Alpaca bridge coordination:
  - intraday cleanup now skips monthly-managed symbols
  - monthly stale-close no longer crashes on `held_for_orders`
- Ran server monthly Alpaca autopilot after the fixes and confirmed:
  - fresh current cycle exists
  - picks are `AMD / AMZN / BAC`
  - `BAC` is blocked by earnings
  - `AMD` and `AMZN` advance to `pending_new` market buys

**Key findings:**

- Current crypto paralysis is not primarily a foundation failure anymore.
- `flat` is no longer dying on `symbol` mismatch; after the latest server fix it is mostly a timing problem (`same_bar` / decision cadence).
- `range_scalp` is now the best additive candidate to the strong `bear_chop` package:
  - recent portfolio probe rows are around `+24.8% .. +25.4%`
  - PF around `1.90`
  - DD around `3.5% .. 4.1%`
- `Elder` keeps confirming the negative thesis:
  - after wave/lookback repair it still alternates between no trades and catastrophic overtrading
  - this is rewrite territory, not promotion territory
- Alpaca state is materially better:
  - intraday paper is real
  - monthly now reaches `send_orders` on a fresh cycle
  - remaining uncertainty is fill stability and multi-cycle behaviour, not stale-pick paralysis

**Next:**

- Continue `flat_live_universe_repair_v2`.
- Continue `bear_chop_plus_range_probe_v1`.
- Let `elder_wave_lookback_v1` finish the current bounded run, then likely retire it from active priority.
- Re-check server live counters after the `ARF1` canary has had time to breathe.
- Add a sync path from local `backtest_runs` into server `runtime/research_import` so server-side `auto_apply` can consume laptop research safely.

## 2026-04-09 | Codex (session 34 - allocator health gate repair + Alpaca paper arming)

**Done:**

- Repaired allocator truth in [build_portfolio_allocator.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py):
  - allocator now respects the base env toggle for each sleeve instead of only regime overrides
  - `overall_health=WATCH` now degrades the allocator only when the watch belongs to a sleeve that is actually active in the current regime
  - allocator state now records `health_summary` with active watch sleeves and active status counts
- Repaired the same base-env / health-gating truth in replay validators:
  - [run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py)
  - [run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py)
  - [run_dynamic_crypto_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py)
- Synced the allocator repair to the live server and rebuilt control-plane state without restarting the bot.
- Added repeated-issue throttling to [check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh):
  - first occurrence still alerts immediately
  - identical control-plane issues now repeat at most once every `12h`
  - recovery sends a single resolved message instead of endless duplicates
- Re-verified the live server after the allocator repair:
  - allocator is currently `ok`, not degraded
  - `router_status=ok`, `scan_ok=1`, `fallbacks=0`
  - repeated Telegram `overall_health_watch` alerts are now treated as alerting noise to suppress, not as current allocator truth
- Seeded live router symbol memory and rebuilt server control-plane:
  - live router now shows `symbol_memory_loaded=1`
  - backtest gate remains on
  - the new degraded mode after the rebuild is overlap-only (`portfolio_overlap:0.25`), not a stale health-file failure
- Tightened control-plane alert semantics one step further:
  - overlap-only allocator degradation is now logged as `INFO`
  - it no longer qualifies as a Telegram-worthy control-plane failure
- Armed Alpaca monthly paper lane:
  - switched [alpaca_paper_v36_candidate.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/alpaca_paper_v36_candidate.env) to `ALPACA_SEND_ORDERS=1`
  - fixed [run_equities_alpaca_v36_candidate.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_alpaca_v36_candidate.sh) so manual `--once` usage does not break the monthly bridge
  - installed monthly cron on the server via [setup_cron_alpaca.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_cron_alpaca.sh)
- Confirmed the next real Alpaca bottleneck:
  - refresh is live and produces fresh runtime files
  - monthly paper still lands in `send_orders_no_current_cycle`
  - current blocker is stale historical `picks.csv` semantics, not a dead cron or disabled send-orders flag
- Restarted top-level crypto validators on the new allocator truth:
  - `dynamic_core3_flat_impulse_nosloped_wf360_memoryfix_v1`
  - `dynamic_core3_flat_impulse_nosloped_annual_memoryfix_v1`

**Key findings:**

- The repeated live `Portfolio allocator: DEGRADED ... overall_health_watch` alert was real, but the gating rule was too blunt:
  - live `overall_health_file` stayed `WATCH`
  - but the watch came from `breakdown`, which is not active in current `bull_chop`
  - after the repair, live allocator rebuilt to:
    - `status=ok`
    - `degraded_reasons=[]`
    - `global_risk=0.90`
- This means the control-plane was not “broken”; it was over-throttling capital because it trusted a non-active watch sleeve too much.
- `sloped` leak root cause was also real:
  - validators were not respecting base env sleeve disables
  - the repaired allocator smoke now shows `ENABLE_SLOPED_TRADING=0` truly stays off in replay truth
- Alpaca monthly is now armed but not yet trading because the refreshed monthly candidate still resolves to:
  - `status=send_orders_no_current_cycle`
  - `latest_entry_day=2025-11-03`
  - `pick_age_days=157`
  - so the lane is correctly staying flat instead of buying stale picks
- The completed annual repair fronts now separate signal from noise:
  - `flat_frequency_repair_v1` is alive (`63/432` PASS; best row about `+10.78`, PF `2.106`, DD `2.40`, `3` negative months)
  - `range_scalp_v1_annual_repair_v1` did not pass (`0/432` PASS; best rows still failed on negative months / DD)

**Next:**

- Let the repaired `360d` walk-forward and annual validators finish on the new allocator truth.
- Use those outputs to judge whether `core3 flat + impulse` actually improved after the allocator repair.
- Keep monthly Alpaca armed, but shift immediate equities attention to intraday if monthly remains stuck in `no_current_cycle`.
- Next live-quality step after validators:
  - decide whether server-side symbol memory should be deployed into live router state
  - and whether `ARF1` frequency tweaks deserve a promoted live candidate overlay.

## 2026-04-09 | Codex (session 33 - router symbol memory + quality audit)

**Done:**

- Added a new offline router-memory builder:
  - [build_router_symbol_memory.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_router_symbol_memory.py)
  - it builds per-symbol penalties from real historical [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs) files
  - grouping is by:
    - sleeve env key
    - BTC 4H regime bucket
    - symbol
- Added a router-quality audit helper:
  - [router_quality_audit.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/router_quality_audit.py)
  - it compares the current router selection against the new symbol-memory truth
- Extended [dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py):
  - candidate ranking can now accept soft symbol penalties
  - ranking rows now expose:
    - market score
    - strategy score
    - memory penalty
    - final score
- Extended [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py):
  - loads optional router symbol memory
  - applies soft symbol penalties during scan-based ranking
  - exposes selected-symbol memory metadata in router state
  - writes memory path truth into the overlay/state
- Updated [deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh) so future foundation deploys also carry the new router-memory scripts.

**Key findings:**

- The new memory was built from `120` real trade files and `13,073` trade rows.
- It immediately confirms the user’s router suspicion in a machine-readable way:
  - `BREAKDOWN_SYMBOL_ALLOWLIST` in `bear_chop` shows very high penalties on:
    - `BTCUSDT`
    - `ETHUSDT`
    - `LINKUSDT`
  - `ARF1_SYMBOL_ALLOWLIST` shows `ADAUSDT` as historically toxic
  - `ASC1_SYMBOL_ALLOWLIST` currently over-trusts `DOGEUSDT`
- Current local audit output in [router_quality_audit.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/router_quality_audit.json) already flags:
  - `BREAKDOWN` carrying toxic `BTC/ETH`
  - `ARF1` carrying toxic `ADA`
  - `ASC1` carrying toxic `DOGE`
- This layer is intentionally soft and offline-first:
  - current research runs did **not** need to be restarted just because the memory layer was added
  - but any future full-stack annual / walk-forward promotion check should be rerun on the new router truth once we decide to turn it on in the active stack

**Next:**

- Let the active strategy research keep running.
- Use the new memory + audit truth to decide:
  - whether `breakdown` needs a smaller `bear_chop` basket
  - whether `ARF1` should stop carrying `ADA`
  - whether `ASC1` should stay out of core until symbol quality improves
- Rewired [run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py), [run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py), and [run_dynamic_crypto_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py) so the next validation wave can run on the memory-aware router stack instead of the older simpler replay router.
- Then rerun the dynamic annual / walk-forward validator on the memory-aware router stack.

## 2026-04-08 | Codex (session 32 - support_bounce regime fix + crypto foundation frontier)

**Done:**

- Found and fixed a real logic bug in [alt_support_bounce_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_support_bounce_v1.py):
  - the strategy exposed `ASB1_REGIME_MAX_GAP_PCT`
  - but `_regime_ok()` still hard-coded `gap_pct <= 1.0`
  - the regime gate now correctly respects the configured threshold
- Added a reusable crypto research launcher:
  - [run_crypto_foundation_frontier.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_crypto_foundation_frontier.sh)
- Added four focused foundation-era research fronts:
  - [core3_range_additivity_recent180_v2.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/core3_range_additivity_recent180_v2.json)
  - [core3_range_additivity_annual_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/core3_range_additivity_annual_v1.json)
  - [support_bounce_v1_regime_gap_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_regime_gap_repair_v1.json)
  - [impulse_volume_breakout_v1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_annual_repair_v1.json)
- Launched the new long-running frontier locally via project tooling.
  Live processes at launch time:
  - `core3_range_additivity_recent180_v2`
  - `core3_range_additivity_annual_v1`
  - `support_bounce_v1_regime_gap_repair_v1`
  - `impulse_volume_breakout_v1_annual_repair_v1`

**Key findings:**

- `range_scalp` still looks more alive than its reputation:
  - earlier package probe [core3_range_additivity_recent180_bestprobe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_134600_core3_range_additivity_recent180_bestprobe/summary.csv)
    already showed `+21.78%`, PF `1.696`, `128` trades
  - so the right next question is annual truth and repeatability, not “is the idea dead?”
- `support_bounce` deserved another look because the regime filter itself was partially lying.
- The foundation is now strong enough that new strategy work can happen on top of:
  - live control plane
  - geometry-aware router
  - exposure-aware allocator
  - explicit promotion gate
  instead of on shifting ground.

**Next:**

- Let the new frontier keep running.
- First readout priority:
  1. `core3_range_additivity_recent180_v2`
  2. `core3_range_additivity_annual_v1`
  3. `impulse_volume_breakout_v1_annual_repair_v1`
  4. `support_bounce_v1_regime_gap_repair_v1`
- After the first stable readout, decide whether the next package front is:
  - `range_scalp` as the first true frequency sleeve
  - `impulse` as the best long continuation sleeve
  - or both, but only through annual + walk-forward + portfolio compare

## 2026-04-08 | Codex (session 31 - weak-bull flat softener + explicit promotion policy)

**Done:**

- Traced the live `flat` suppression to the actual source:
  - it was not allocator overlap logic
  - it was the regime decision table in [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py)
  - `bull_trend` hard-disabled `ENABLE_FLAT_TRADING`
- Added a deterministic softener in [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py):
  - weak `bull_trend` now re-enables `flat` in reduced mode when `ER <= 0.55`
  - state now records `softeners`
  - server env patch now also writes `ORCH_BULL_TREND_FLAT_ER_MAX=0.55`
- Synced the updated regime builder to the live server and rebuilt:
  - regime
  - router
  - allocator
- Verified live result:
  - server regime stayed `bull_trend`
  - `softeners = ['weak_bull_trend_flat_on']`
  - `ENABLE_FLAT_TRADING = 1`
  - allocator now shows:
    - `flat_enabled = True`
    - `flat_risk = 0.55`
    - `flat_health = OK`
- Added explicit promotion policy artifacts:
  - [crypto_promotion_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/crypto_promotion_policy.json)
  - [evaluate_crypto_promotion.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/evaluate_crypto_promotion.py)
  - [PROMOTION_RULES.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/PROMOTION_RULES.md)
- Linked the new promotion source-of-truth from:
  - [GOLDEN_PORTFOLIO_BASELINES.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/GOLDEN_PORTFOLIO_BASELINES.md)

**Key findings:**

- The filter was partly right and partly too blunt.
- External market context today is genuinely risk-on:
  - [Investopedia market open note](https://www.investopedia.com/5-things-to-know-before-the-stock-market-opens-april-8-2026-11945258) says S&P 500 futures were up more than `2.5%` and Bitcoin was nearing `71,500`
- That supports:
  - `breakdown` staying suppressed
  - momentum sleeves being allowed
- But it does **not** justify hard-killing `flat` when the regime confidence is only around `0.50`.
- New promotion evaluator already gives a clean example:
  - current `core3` candidate fails on:
    - annual DD
    - walk-forward pass ratio
    - portfolio compare vs live golden baseline

**Next:**

- Keep this softer weak-bull flat rule unless live evidence says it over-trades.
- Use [evaluate_crypto_promotion.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/evaluate_crypto_promotion.py) as the required gate before any crypto package promotion discussion.
- Then return to sleeve work on top of the now-stronger foundation.

## 2026-04-08 | Codex (session 30 - geometry-aware router + exposure layer + live foundation deploy)

**Done:**

- Added geometry-aware routing layer:
  - [bot/router_geometry.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/router_geometry.py)
  - [scripts/build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) now:
    - scores selected symbols with deterministic geometry context
    - records per-symbol geometry reasons / keep flags
    - filters weak symbols when geometry disagrees with the sleeve
    - keeps best fallback symbols instead of emptying a sleeve blindly
- Added first real portfolio overlap / exposure layer:
  - [scripts/build_portfolio_allocator.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py)
  - [configs/portfolio_allocator_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy.json)
  - allocator now:
    - measures symbol overlap across enabled sleeves
    - applies per-sleeve overlap haircuts
    - applies global portfolio overlap haircut
    - writes overlap metrics into env/state
- Hardened one-line server operations:
  - [scripts/deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh)
  - [scripts/server_status.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/server_status.sh)
  - both now auto-pick `~/.ssh/by-bot` when available
- Deployed the updated foundation to live server `64.226.73.119`.
- Manually rebuilt live control-plane state after deploy:
  - regime
  - router
  - allocator
  - geometry
  - operator snapshot
- Removed duplicate live `cp_health` cron and left one clean entry:
  - `# bybot_cp_health`

**Key findings:**

- Local annual control-plane replay with the new stack:
  - [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_122726_annual_cp_geom_exposure_20260408/summary.json)
  - `25` checkpoints
  - allocator states:
    - `ok = 21`
    - `degraded = 4`
  - `avg_global_risk_mult = 0.861`
  - sleeve enable counts:
    - `sloped = 22`
    - `flat = 20`
    - `breakout = 17`
    - `breakdown = 2`
- This replay still validates control-plane decisions, not direct trading PnL.
- Live server truth after deploy + rebuild:
  - heartbeat fresh
  - regime/router/allocator files fresh
  - `bybot.service` active under systemd
  - watchdog cron installed
  - control-plane health cron installed once, without duplicates
  - recent WS pulse right after restart showed:
    - `ws_connect = 2`
    - `ws_disconnect = 0`
    - `ws_handshake_timeout = 0`

**Next:**

- Keep promotion strict:
  - `annual`
  - `walk-forward`
  - portfolio compare
- The remaining foundation work is now much narrower:
  - make promotion rules explicit in the portfolio path
  - then return to sleeve repair / promotion with a much cleaner base

## 2026-04-08 | Codex (session 29 - historical health timeline + operator health context)

**Done:**

- Added reusable historical health-timeline layer:
  - [bot/strategy_health_timeline.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/strategy_health_timeline.py)
  - [scripts/build_strategy_health_timeline.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_strategy_health_timeline.py)
- Built a real local health timeline artifact:
  - [strategy_health_timeline.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/strategy_health_timeline.json)
  - it currently contains `25` checkpoint snapshots from `2025-04-07` to `2026-03-25`
- Upgraded [run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py):
  - can now load historical health timeline
  - picks health by checkpoint date instead of replaying one current `strategy_health.json`
  - writes `overall_health` and `health_source` into replay timeline output
- Extended [operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py):
  - current `strategy_health` summary is now included
  - operator snapshot now also reports timeline existence, age, count, and covered date range
- Extended foundation deployment scripts:
  - [setup_server_crons.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_server_crons.sh)
  - [deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh)
  - the server can now build health timeline weekly after autopilot

**Key findings:**

- This closed one of the most misleading parts of the old replay story.
- Earlier constrained annual replay was degraded on all `25/25` checkpoints mainly because it kept using the current live `strategy_health.json` for the whole year.
- After switching replay to historical health:
  - [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_105734_annual_cp_hist_timeline_20260408/summary.json)
  - allocator states became:
    - `ok = 21`
    - `degraded = 4`
  - average global risk increased to `0.861`
  - health sources were `timeline = 25`
- This is a truth improvement, not a beauty pass:
  - the control-plane is no longer being unfairly judged by one stale present-day health file
  - but the annual replay still shows plenty of `WATCH / PAUSE / KILL` checkpoints, so the system is not “fixed by one layer”

**Next:**

- Deployed the new health-timeline + operator-health layer to server:
  - uploaded the new modules/scripts
  - refreshed server crons
  - verified live [operator_snapshot.txt](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/operator/operator_snapshot.txt)-style output on server now shows:
    - heartbeat
    - transport guard
    - control-plane
    - current health summary
    - historical health timeline metadata
- Then move to the next real foundation gap:
  - geometry-aware router / advisory
  - then correlation / exposure layer
- Only after that, return to aggressive sleeve promotion work.

## 2026-04-08 | Codex (session 26 - server parity audit, WS guard, annual truth)

**Done:**

- Audited local repo vs live server and pushed the missing control-plane pieces into real server operation:
  - regime overlay build
  - symbol router build
  - portfolio allocator build
  - live cron wiring for those layers
- Added transport self-healing guard in [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py):
  - tracks sustained websocket degradation
  - writes runtime state to `runtime/control_plane/ws_transport_guard_state.json`
  - blocks new entries during sustained critical transport conditions
  - supports controlled restart as an opt-in layer, not as default unsafe behaviour
- Extended bot observability:
  - runtime status now shows `ws_guard`
  - control-plane startup print now includes WS guard settings
- Continued chart-analysis work:
  - `/chart_ai` is now in bot code
  - chart analysis persistence is wired
  - server activation is still blocked until an image-capable API key is supplied
- Re-audited the old `core3 impulse` annual vs `180d` discrepancy from actual trade files.
- Added the first historical control-plane replay harness:
  - [run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py)
  - it replays:
    - historical BTC 4H regime
    - hysteresis
    - frozen-router profile selection
    - allocator decisions
- Hardened historical BTC cache fallback in [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py) so replay can assemble longer history from multiple cache slices instead of dying on a single late cache file.
- Ran two first control-plane annual replays:
  - constrained by current health:
    - [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_084604_annual_cp_replay_20260408/summary.json)
  - neutral-health structural view:
    - [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_084802_annual_cp_replay_neutral_20260408/summary.json)

**Key findings:**

- The old `core3` discrepancy was real, not a reporting glitch:
  - `180d`: strong
  - `360d`: weak
- Root cause of the weak annual was mostly:
  - bad `2025-04..2025-09` months
  - `alt_inplay_breakdown_v1` carrying the losses
  - much less real diversification than expected, because `ARF1` did not trade in those old probes
- Websocket degradation is real enough to justify a live guard:
  - recent `12h` and `1h` windows showed too many disconnects / handshakes
  - simply increasing timeout is not the main fix
  - the missing piece was a stateful safe-mode between "we noticed a problem" and "the bot still opens trades anyway"
- Alpaca remains operationally alive, but not validated as a money sleeve yet:
  - dynamic lane runs
  - long-only protection can block entries
  - annual validated package is still missing
- First control-plane replay truth:
  - on the constrained annual replay, the allocator stayed `degraded` on all checkpoints because the current live `strategy_health.json` is already in `WATCH`
  - applied regime over the annual timeline was mostly:
    - `bull_chop`
    - `bear_chop`
  - average allocator global risk was about `0.645`
  - regime changes were sparse (`3` on `25` checkpoints)
- This is useful, not disappointing:
  - we now have a repeatable harness for the portfolio brain
  - but the first replay also proves the next missing layers are:
    - historical health timeline
    - historical symbol selection instead of frozen overlay replay
    - later, portfolio PnL comparison using those control-plane decisions

**Next:**

- Deploy the new WS guard to server and verify that live runtime now exposes `ws_transport_guard_state.json`.
- Harden transport itself:
  - revisit shard/batch/stagger settings
  - measure next live breakdown latencies with the newer timestamps
- Move from partial control-plane to historical annual replay:
  - regime router
  - allocator
  - full-year portfolio truth
- Extend the new replay harness instead of starting another parallel framework:
  - neutral health vs constrained health
  - historical router selection
  - control-plane-aware portfolio regression
- After the transport layer is calmer, continue the foundation work:
  - geometry engine
  - regime-router backtest
  - only then more sleeves / promotions

## 2026-04-08 | Codex (session 27 - live heartbeat, watchdog, geometry state)

**Done:**

- Adapted the new self-healing foundation scripts to the real live service name `bybot` instead of the older `bybit-bot` naming:
  - [scripts/setup_systemd_bot.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_systemd_bot.sh)
  - [scripts/bot_health_watchdog.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/bot_health_watchdog.sh)
  - [scripts/check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh)
  - [scripts/setup_watchdog_cron.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_watchdog_cron.sh)
  - [scripts/deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh)
- Verified locally:
  - shell syntax for all touched foundation scripts
  - Python syntax for heartbeat / control-plane / geometry scripts
- Deployed the safe subset to the server without replacing the existing working unit:
  - new [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py)
  - external heartbeat watchdog
  - control-plane freshness check cron
- Confirmed live heartbeat now exists and updates on server:
  - `/root/by-bot/runtime/bot_heartbeat.json`
  - includes `ts`, `uptime_s`, `open_trades`, `ws_guard_active`, `bybit_msgs`, `regime`
- Confirmed watchdog stack on the server:
  - `bot_health_watchdog.sh` runs and reports `OK`
  - `check_control_plane_health.sh` runs and reports all files fresh
  - `control_plane_watchdog.py` state remains `ok`
- Promoted the first real no-API “vision under the hood” layer from local toy to live foundation:
  - added [bot/geometry_cache.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/geometry_cache.py)
  - refactored [scripts/run_geometry_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_geometry_snapshot.py) to reuse shared cache loading
  - added [scripts/build_geometry_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_geometry_state.py)
  - updated [scripts/setup_server_crons.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_server_crons.sh) so server now builds deterministic geometry state hourly
- Verified live geometry state on server:
  - `/root/by-bot/runtime/geometry/geometry_state.json`
  - active symbol snapshots built successfully from current router output

**Key findings:**

- The operator / advisory model can still be stale even when the repo is better wired:
  - it only sees the prompt + snapshot we pass into it
  - it does not “see the whole IDE + server” the way we do
  - this is why it remains helpful as an analyst but not as source-of-truth
- Heartbeat + external watchdog closes a real observability gap:
  - before, a hung bot could look “quiet” from Telegram
  - now the server has a file-based liveness signal plus external alarm path
- Deterministic geometry is already useful without any image API:
  - levels
  - channels
  - compression
  - near-support / near-resistance context
- This geometry layer is the right base for future chart-based strategies because it is:
  - cheap
  - reproducible
  - backtestable
  - safe to run on server continuously

**Next:**

- Add historical strategy-health timeline support so replay no longer depends on one current `strategy_health.json`.
- Start consuming geometry-state in advisory / regime-routing logic instead of leaving it as passive state only.
- Keep promotion strict:
  - annual
  - walk-forward
  - portfolio compare

## 2026-04-08 | Codex (session 28 - operator truth pack)

**Done:**

- Added a shared compact operator context layer:
  - [bot/operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py)
  - it summarizes:
    - heartbeat
    - WS transport guard state
    - control-plane freshness / watchdog state
    - regime/router/allocator compact truth
    - geometry highlights for active symbols
- Added a saved runtime artifact builder:
  - [scripts/build_operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_operator_snapshot.py)
  - writes:
    - `runtime/operator/operator_snapshot.json`
    - `runtime/operator/operator_snapshot.txt`
- Wired the same operator context into both AI entry points:
  - [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) `/ai` snapshot now includes `operator_context`
  - [scripts/deepseek_weekly_cron.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deepseek_weekly_cron.py) tune-phase snapshot now includes the same `operator_context`
- Deployed the operator snapshot pieces to the server and updated managed crons:
  - `build_operator_snapshot.py` now runs hourly after geometry build
  - verified `/root/by-bot/runtime/operator/operator_snapshot.txt`

**Key findings:**

- The operator problem was not only “memory too short”.
- The bigger problem was missing structured runtime truth:
  - before, the AI mostly saw prompt text plus partial runtime snapshot
  - now it gets a compact pack with the actual server/runtime/control-plane state
- This will not make the external operator omniscient.
- It does remove the most expensive blind spot:
  - stale guesses about service health
  - stale guesses about router/allocator freshness
  - stale guesses about chart structure context

**Next:**

- Historical strategy-health timeline
- geometry-aware routing/advisory
- only then return to aggressive strategy promotion

## 2026-04-03 | Codex (session 24 - breakout chop ER guard check on trusted current90)

**Done:**

- Re-ran the trusted `v5` current90 window from the project `.venv` with:
  - `BREAKOUT_CHOP_ER_MIN` unset
  - `BREAKOUT_CHOP_ER_MIN=0.20`
- Measured both:
  - full trusted stack
  - isolated `inplay_breakout`

**Key findings:**

- On the trusted full stack, both runs were identical:
  - `100 -> 101.76`
  - `+1.76%`
  - `39` trades
  - `PF 1.117`
  - `DD 4.10%`
- On isolated `inplay_breakout`, both runs were also identical:
  - `100 -> 99.40`
  - `-0.60%`
  - `1` trade
- Meaning: the live `ER` guard is currently a harmless protection layer, but it is not the thing that repairs breakout on this exact recent trusted window.

**Next:**

- Continue with the control-plane roadmap:
  - finish orchestrator clean push-set
  - build dynamic symbol router
  - return to breakout repair on top of that foundation
- Treat `ER` as a retained guard, not as the main breakout fix.

## 2026-04-03 | Codex (session 25 - tracked secret cleanup)

**Done:**

- Verified that tracked `configs/server_clean.env` still contained live-like secrets.
- Redacted the tracked file so the repo no longer stores:
  - Telegram token and chat ids
  - Bybit account JSON
  - DeepSeek API key
- Left the real server `.env` unchanged.

**Key findings:**

- The immediate security problem was in the tracked repo snapshot, not in the current server verification flow.
- This had to be cleaned before any orchestrator push-set or future publishing work.

**Next:**

- Keep real credentials only in gitignored local files and on the server.
- Continue with orchestrator isolation and then dynamic symbol routing.

## 2026-04-02 | Codex (session 23 - server env verification + orchestrator hardening)

**Done:**

- Pulled the real server `.env` strategy variables and compared them to the trusted `v5` overlay.
- Confirmed the server is still close to trusted `v5` on the key live knobs:
  - `ASC1_SYMBOL_ALLOWLIST=ADAUSDT,LINKUSDT,ATOMUSDT`
  - `ARF1_SYMBOL_ALLOWLIST=ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,LTCUSDT`
  - `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT`
  - `BREAKOUT_QUALITY_MIN_SCORE=0.53`
  - `BREAKOUT_ALLOW_SHORTS=0`
  - `BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT=0.07`
  - `MIDTERM_SYMBOLS=BTCUSDT,ETHUSDT`
- Verified the main live delta vs trusted `v5` is the added chop guard:
  - `BREAKOUT_CHOP_ER_MIN=0.20`
- Hardened the local orchestrator integration:
  - `build_regime_state.py` now accepts `TG_CHAT` as a Telegram fallback
  - overlay env now includes generation metadata and hysteresis fields
  - `smart_pump_reversal_bot.py` now checks overlay freshness and warns on stale/missing regime state
  - overlay application now also reads `ENABLE_SLOPED_TRADING`
- Syntax check passed for both orchestrator files.

**Key findings:**

- The server does not appear to be running on a wildly different strategy snapshot.
- This reduces the likelihood that the recent confusion came from a hidden server config fork.
- The bigger missing piece is still the control plane itself, not a secret server env mismatch.

**Next:**

- Isolate the orchestrator diff into a clean branch/commit set.
- Only then decide on server rollout after the fresh backtest inputs return.

## 2026-04-02 | Codex (session 22 - roadmap reset and working-order lock)

**Done:**

- Replaced the oversized roadmap with a short active roadmap in [ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md).
- Locked the new priority order:
  - validation discipline and live damage control
  - regime orchestrator
  - dynamic symbol router and strategy profiles
  - repair current live crypto sleeves
  - only then promote new strategy families and expand to other markets
- Added a session rule: every new task should start from `docs/ROADMAP.md`, and every material step should update `WORKLOG` and `JOURNAL`.

**Key findings:**

- The project had accumulated too many parallel fronts and too many stale roadmap items.
- The real next milestone is not "more strategies" but a control-plane rebuild.
- We now have one active queue that can be used as the handoff source for future sessions.

**Next:**

- Finish the regime orchestrator as a clean isolated push-set.
- Build the dynamic symbol router on top of the current allowlist pieces.
- Return to crypto sleeve repair only after the control-plane path is clearly defined.

## 2026-04-02 | Codex (session 21 — production trade state mismatch fix)

**Done:**

- Разобран реальный production-инцидент по `NOMUSDT`:
  - пользовательский журнал показал live-сделку, которой не было в локальном `TRADES`/`trade_events` текущего server bot
  - это подтвердило слепую зону: бот восстанавливал позиции только на старте, но не умел во время работы поднимать тревогу о позиции на бирже вне локального state
- В [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) добавлен runtime-scan незаведённых биржевых позиций:
  - `UNTRACKED_EXCHANGE_SCAN_SEC`
  - `UNTRACKED_EXCHANGE_ALERT_COOLDOWN_SEC`
  - `_scan_untracked_exchange_positions()`
  - теперь `sync_trades_with_exchange()` отдельно проверяет open positions на Bybit и шлёт `🚨 UNTRACKED EXCHANGE POSITION`, если позиция есть на бирже, но бот её не ведёт
- Добавлен второй безопасный слой:
  - если runtime-скан находит биржевую позицию и в `trades.db` есть незакрытый bot-entry для того же `symbol/side`,
    бот автоматически восстанавливает её в `TRADES` (`🔁 RUNTIME RESTORED ...`)
  - если matching bot-entry нет, остаётся только аварийный alert без авто-импорта
- Выбран безопасный режим реакции:
  - бот подхватывает только те позиции, для которых есть свой же незакрытый entry в БД
  - truly manual/внешние позиции не маскируются под бот-трейды
- Для следующего реального improvement-фронта собран новый bounded compare:
  - [breakout_live_bridge_v5_fixed_vs_runner.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakout_live_bridge_v5_fixed_vs_runner.json)
  - база зафиксирована на лучшем историческом breakout-pocket `v3_density r26`
  - внутри compare тестируется только exit-plan: `fixed` vs `runner`

**Key findings:**

- Скрины пользователя опровергли прежнюю гипотезу “позиции не было”; проблема реальная и продовая
- Live `breakout` сейчас работает в `fixed` exit mode, trailing не включён
- TP/SL на Bybit ставятся как `position trading-stop`, а не как обычные open orders

**Next:**

1. Прогнать compile-check локально
2. Задеплоить фикс на сервер и перезапустить `bybot`
3. Отследить следующий подобный случай: приходит ли alert о незаведённой биржевой позиции
4. После стабилизации вернуться к crypto bear-market sleeves (`breakdown`) и live diagnostics

## 2026-04-01 | Codex (session 20 — Alpaca v36 server paper rollout + InPlay minute continuation)

**Done:**

### Alpaca v36 — перестали топтаться, перешли к server-side paper rollout

- Подтверждён сильный локальный frontier:
  - `equities_monthly_v36_current_cycle_activation`
  - лучший кластер: `40 trades`, `net=164.99`, `PF=5.84`, `DD=4.60`, `1` красный месяц
- Добавлен локальный safe/offline dry-run для monthly paper bridge:
  - `scripts/equities_alpaca_paper_bridge.py`
  - `configs/alpaca_paper_v36_close_stale_dry_run.env`
  - `scripts/run_equities_alpaca_v36_close_stale_dry_run.sh`
- Локальный dry-run подтвердил текущую monthly-логику:
  - stale `GOOGL` / `TSLA` надо забыть
  - новых monthly picks сейчас нет
  - correct action = `close stale and stay flat`

### Server deploy for Alpaca

- На сервер `/root/by-bot` задеплоены:
  - `scripts/equities_alpaca_paper_bridge.py`
  - `scripts/equities_alpaca_intraday_bridge.py`
  - `scripts/equities_midmonth_monitor.py`
  - `scripts/run_equities_alpaca_v36_candidate.sh`
  - `scripts/run_equities_monthly_v36_refresh.sh`
  - `scripts/equities_monthly_research_sim.py`
  - `configs/alpaca_paper_v36_candidate.env`
  - `configs/intraday_config.json`
- Сделан backup server-side файлов в `runtime/server_backups/alpaca_v36_20260401`
- По пути найден и устранён technical blocker:
  - на сервере была старая `equities_monthly_research_sim.py`, которая не знала `--intramonth-portfolio-stop-pct`

### InPlay / scalper

- Бесполезные grids остановлены:
  - `micro_scalper_bounce_v1_grid`
  - `micro_scalper_breakout_v1_grid`
  - они только грели ноут без признаков живого кармана
- Оставлен `inplay_scalper_minute_probe_v2`
- Собран новый более живой run:
  - `configs/autoresearch/inplay_scalper_minute_probe_v3_relaxed.json`
  - идея: softer activation, longer window, more symbols, честный minute scalp sleeve

**Key findings:**

- `Alpaca` monthly core и dynamic/intraday layer — это разные вещи; monthly всё ещё может сидеть в cash
- server-side `v36` rollout — правильный следующий шаг, а не ещё один слепой research-only цикл
- текущий weakest link уже не “стратегия плохая”, а то, как быстро и гибко реагировать между monthly циклами

**Next:**

1. Добить server-side `Alpaca v36` paper run и снять реальный verdict с paper API
2. Если monthly снова flat → продвигать `equities_alpaca_intraday_bridge.py` как dynamic watchlist layer
3. Дать `InPlay v3 relaxed` первые строки и решить, есть ли там реальный скальперный pocket

---

## 2026-03-29 | Claude (session 19d — Alpaca diagnosis + intramonth stop + dynamic strategy notes)

**Done:**

### Alpaca Paper — полная диагностика и два конкретных фикса

**Диагноз:**
- Лучший прогон v23 (r011): PnL=+58.7%, PF=2.31, 17 месяцев, 10/17 зелёных
- НО: `neg_months=7` → autoresearch отклоняет все 108 прогонов (ограничение `max_negative_months=4`)
- Красные месяцы: Jun'24 (-5.4%), Oct'25 (-4.5%), Aug'23/Sep'25 (-3.7%) → NVDA/CRWD/TSLA стопы
- `profit_factor=NaN` во всех результатах → баг: поле не вычислялось в summary.csv

**Фикс 1 — `equities_monthly_research_sim.py`:**
- Добавлен `--intramonth-portfolio-stop-pct` параметр
- Новая функция `_simulate_trades_portfolio_stop()`: ежедневно считает портфельную доходность; если падает ниже порога → выходит из ВСЕХ позиций в тот же день ('portfolio_stop')
- Добавлено `profit_factor` в summary.csv (больше нет NaN)
- Добавлено `negative_months` в summary.csv (явно, не только через monthly.csv)

**Фикс 2 — `configs/autoresearch/equities_monthly_v27_intramonth_stop.json`:**
- Новый спек: 288 комбо, ~15 мин
- Grid: INTRAMONTH_STOP=[0.0, 0.035, 0.04, 0.05]
- Расслабленные ограничения: `max_negative_months=6` (реалистично), `min_profit_factor=1.5`
- Убран BENCHMARK_MIN_ABOVE_SMA=0 (теперь минимум = 1, т.е. SPY или QQQ должны быть выше SMA)

**Ожидаемый эффект:**
- С INTRAMONTH_STOP=0.04: Jun'24 (-5.4%) → -4.0%, Oct'25 (-4.5%) → -4.0%
- Это конвертирует 2 худших месяца → менее болезненные
- Compounded return должен подрасти на 2-3%

**Запустить:**
```bash
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/equities_monthly_v27_intramonth_stop.json \
  > /tmp/equities_v27.log 2>&1 &
```

### Ответы на вопросы о динамических стратегиях

**Стратегии динамические по символам?** — Да:
- `ALT_*` стратегии читают символы из `ASC1_SYMBOL_ALLOWLIST`, `ARF1_SYMBOL_ALLOWLIST` — обновляются динамически через `dynamic_allowlist.py` каждое воскресенье
- Для разных монет МОГУТ быть разные параметры через `family profiles` — это НЕ СДЕЛАНО (см. roadmap)

**Разные настройки под разные монеты?** — Да, принципиально эффективно:
- BTC/ETH — более медленные тренды, шире SL/TP
- SOL/AVAX — высокая волатильность, тighter стопы
- Mid-cap алты — нужен отдельный профиль (wider ATR multiple, longer cooldown)
- Сейчас всё на одних параметрах → family profiles это следующий шаг автономности

**Шорты vs лонги разделить?** — Да, эффективно:
- Уже реализовано в FR Reversion (LC_ALLOW_LONGS/SHORTS)
- Elder v132b уже есть ALLOW_SHORTS=0/1 в автопоиске
- В ALT_* стратегиях логика шортов и лонгов уже раздельная по условиям

---

## 2026-03-29 | Claude (session 19c — Live gates wired + Liquidation Cascade strategy + Telegram fix)

**Done:**

### 1. health_gate.py → ВШИТ В БОТ (КРИТИЧНО)
- `smart_pump_reversal_bot.py`: добавлен `from bot.health_gate import gate as _health_gate`
- 6 стратегий теперь имеют live entry gate перед `asyncio.create_task`:
  - `alt_sloped_channel_v1` (sloped trading)
  - `alt_resistance_fade_v1` (flat trading)
  - `alt_inplay_breakdown_v1` (breakdown shorts)
  - `micro_scalper_v1` (micro scalper)
  - `alt_support_reclaim_v1` (support reclaim)
  - `triple_screen_v132` (Elder / TS132)
- Gate читает `configs/strategy_health.json` с TTL 1h:
  - PAUSE/KILL → entries заблокированы + Telegram alert (1 раз/день)
  - WATCH → entries разрешены + предупреждение
  - OK → entries разрешены без лишних логов

### 2. allowlist_watcher.py → ЗАПУСКАЕТСЯ ПРИ СТАРТЕ БОТА
- `from bot.allowlist_watcher import AllowlistWatcher as _AllowlistWatcher`
- В `main()`: `_allowlist_watcher = _AllowlistWatcher(); _allowlist_watcher.start()`
- Демон-тред опрашивает файл каждые 300s
- ASC1/ARF1 обновляются в os.environ без перезапуска бота
- BREAKOUT пишет флаг `configs/allowlist_restart_needed.flag`

### 3. Telegram chunking → ПОФИКШЕНО во всех 4 файлах
- `smart_pump_reversal_bot.py`: `tg_send()` + `tg_send_kb()` → chunking по 3900 симв. с нумерацией [1/3]
- `tg_trade()` → теперь просто вызывает `tg_send()` (переиспользует логику)
- `scripts/deepseek_weekly_cron.py`: убрана тупая обрезка `[:4096]` → нормальный chunking
- `scripts/equity_curve_autopilot.py`: аналогично

### 4. Liquidation Cascade Entry v1 — новая стратегия
- `strategies/liquidation_cascade_entry_v1.py` (~250 строк)
- Edge: механические liquidation engines создают overshoots → ловим возврат
- Сигнал LONG: drop ≥ 3% за 6 баров + RSI ≤ 28 + vol spike ≥ 2.5× + price ≥ 2% ниже EMA
- SL=1.2×ATR, TP=2.0×ATR, time stop=48 баров (4h)
- Зарегистрирована в `run_portfolio.py` (4 точки)
- Создан `configs/autoresearch/liquidation_cascade_v1_grid.json` (~3888 комбо, ~45 мин)
- Longs only в первом прогоне; shorts тест отдельно после результатов

### 5. SR Break Retest Revival — статус
- Autoresearch запущен на машине пользователя, остановлен на 449/12288 (3.65%)
- Ранние результаты плохие (PF < 0.8) — нормально, начало перебора
- Нужно возобновить: `python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/sr_break_retest_volume_v1_revival_v1.json`
- Ожидаемое время: ~8-10 часов на полный прогон

### 6. Синтаксическая проверка
- Все 8 модифицированных/новых файлов: ✅ ast.parse OK

**Статус автономности (обновлено):**
| Компонент | Статус |
|-----------|--------|
| health_gate → live entry | ✅ ВШИТ |
| allowlist_watcher | ✅ ВШИТ |
| Telegram chunking | ✅ ПОФИКШЕН |
| FR Reversion strategy | ✅ готова к autoresearch |
| Liquidation Cascade v1 | ✅ готова к autoresearch |
| Elder v13 zoom autoresearch | 🔄 запущен на сервере |
| SR Break Retest revival | 🔄 449/12288 — нужно продолжить |
| Family dynamic profiles | ❌ не начато |
| Regime allocator correlation | ❌ не начато |

**Команды для запуска на сервере:**
```bash
# 1. Продолжить SR break retest (оставить до конца)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/sr_break_retest_volume_v1_revival_v1.json \
  > /tmp/sr_revival.log 2>&1 &

# 2. Запустить Funding Rate Reversion autoresearch
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/funding_rate_reversion_v1_grid.json \
  > /tmp/fr_reversion_v1.log 2>&1 &

# 3. Запустить Liquidation Cascade autoresearch
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/liquidation_cascade_v1_grid.json \
  > /tmp/lc_v1.log 2>&1 &

# 4. После Elder v13 zoom → portfolio test
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/portfolio_elder_6strat_test.json \
  > /tmp/elder_portfolio.log 2>&1 &

# 5. Запустить live funding rate fetcher рядом с ботом
nohup python3 scripts/funding_rate_fetcher.py --live > /tmp/fr_fetcher.log 2>&1 &
```

---

## 2026-03-29 | Claude (session 19b — Funding Rate Reversion: full integration)

**Done:**

### Funding Rate Reversion v1 — полная интеграция
- Зарегистрирована в `backtest/run_portfolio.py` (4 точки: import, default list, dict init, signal selector)
- Создан `configs/autoresearch/funding_rate_reversion_v1_grid.json` — 2916 комбо, ~30 мин
  - Grid: FR_THRESHOLD × EMA_PERIOD × EXT_PCT × RSI_OB × RSI_OS × SL_ATR × TP_ATR × TIME_STOP
  - FR_LATEST_* env vars инжектируют фиксированный rate 0.0008 для backtesta (тестирует RSI/EMA логику)
  - Ограничения: PF≥1.6, trades≥15, DD≤5%, net_pnl≥4
- Создан `scripts/funding_rate_fetcher.py` — 3 режима:
  - `--live` → бесконечный цикл, обновляет FR_LATEST_* env + configs/funding_rates_latest.json (60s интервал)
  - `--history --symbol BTCUSDT --days 365` → CSV с историческими rates (каждые 8h) via Bybit API
  - `--history-all` → скачать все символы сразу
  - `--status` → текущие rates + пометки EXTREME (>0.1%) / HIGH (>0.06%)
  - Pagination через Bybit cursor для полного охвата периода

**Следующие шаги FR Reversion:**
1. `python3 scripts/funding_rate_fetcher.py --status` — проверить доступность Bybit API
2. `python3 scripts/funding_rate_fetcher.py --history-all --days 365` — скачать исторические данные
3. Запустить autoresearch: `nohup python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/funding_rate_reversion_v1_grid.json > /tmp/fr_reversion_v1.log 2>&1 &`
4. После results → создать v1_zoom spec с лучшим кластером
5. Запустить `--live` рядом с ботом для live rate injection

**Ключевое ограничение backtesta:**
Стратегия видит funding rate только через store.funding_rate или env FR_LATEST_SYMBOL.
В backtest используется константный rate — результаты показывают качество RSI/EMA фильтров,
НЕ реальную частоту сигналов. Для реалистичного backtesta нужна CSV с историческими rates.

---

## 2026-03-29 | Claude (session 19 — Elder revival + dual-AI architecture)

**Done:**

### Elder Triple Screen Revival
- Подтверждено: `triple_screen_v132.py` в архиве, но уже зарегистрирована в run_portfolio.py
- `_import_strategy_class` ищет в обоих пакетах: `strategies` и `archive.strategies_retired`
- Из 1076 autoresearch v12: 204 PASS комбо, лучший PF=4.27 / PnL=+10.7% / DD=1.2% (BTC/ETH/AVAX)
- Создан `configs/autoresearch/triple_screen_elder_v13_zoom.json` — 2592 комбо, ~50 мин
- Создан `configs/autoresearch/portfolio_elder_6strat_test.json` — 256 комбо, ~5 мин (6-стратегийный тест)
- Запускать последовательно: сначала v13 zoom → потом 6-strat test

### Claude API модуль (Dual-AI Architecture)
- Создан `scripts/claude_monthly_analyst.py` — полный скелет с тремя режимами:
  - `--report` — monthly portfolio deep analysis
  - `--strategy-idea "..."` — дизайн новой стратегии с entry/exit логикой
  - `--diagnose STRAT` — deep diagnosis конкретной стратегии
- При отсутствии API key → выводит инструкцию активации + cost estimate (~$5-15/мес)
- Активировать когда P&L > $200/мес

### ROADMAP обновлён
- Добавлен Elder revival как P1 с конкретными командами запуска
- Добавлена Dual-AI архитектура (P2) с таблицей ролей DeepSeek vs Claude
- Добавлена новая стратегия P2: Funding Rate Reversion (специфика Bybit перпов)

**Команды для запуска локально:**
```bash
# 1. Elder v13 zoom (сначала):
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/triple_screen_elder_v13_zoom.json \
  > /tmp/elder_v13.log 2>&1 &

# 2. Потом 6-стратегийный тест (после v13):
python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/portfolio_elder_6strat_test.json
```

---

## 2026-03-29 | Claude (session 19 — protection layers + equity autopilot)

**Done:**

### 1. Alpaca Intraday Bridge v2 — 3-Layer Protection
`scripts/equities_alpaca_intraday_bridge.py` полностью переписан с тремя защитными слоями:
- **Layer 1 — SPY Regime Gate**: Fetches SPY daily bars → SMA50. Если SPY < SMA50 → блокирует все новые long entries. Тест показал: SPY $670 < SMA50 $687 → режим медвежий, entries заблокированы корректно.
- **Layer 2 — Daily Loss Limit**: Отслеживает P&L за сегодня. Если потери > `INTRADAY_MAX_DAILY_LOSS_PCT`% equity → стоп на день. Default 2%.
- **Layer 3 — Equity Curve Filter**: Логирует daily P&L в `configs/intraday_equity_log.json`. 20-day rolling sum < 0 AND 10d MA < 0 → observation mode. Нет новых входов пока кривая не восстановится.

Config vars: `INTRADAY_SPY_GATE=1`, `INTRADAY_MAX_DAILY_LOSS_PCT=2.0`, `INTRADAY_EQUITY_CURVE_GATE=1`, `INTRADAY_EQUITY_CURVE_DAYS=20`

### 2. Equity Curve Autopilot для Bybit стратегий
`scripts/equity_curve_autopilot.py` — антидеградационный монитор:
- Загружает trades.csv из последнего backtest run
- Строит equity curve per strategy → проверяет против MA20
- 4 статуса: OK / WATCH (curve < MA20) / PAUSE (30d PnL < -2%) / KILL (60d PnL < -4%)
- Пишет `configs/strategy_health.json` — main bot может проверять перед входом
- Telegram digest + markdown отчёт в `docs/weekly_reports/`
- Функция `strategy_is_healthy(name)` для интеграции в main бот
- Тест на золотом портфеле: 4 ✅ OK, 1 ⚠️ WATCH (alt_inplay_breakdown_v1)

### 3. Server Cron Setup Script
`scripts/setup_server_crons.sh` — ONE-SHOT скрипт активации на сервере:
```bash
bash scripts/setup_server_crons.sh
```
Устанавливает 4 крона:
- Sun 22:00 UTC → dynamic_allowlist.py
- Sun 22:30 UTC → deepseek_weekly_cron.py
- Sun 23:00 UTC → equity_curve_autopilot.py
- */5 14-21 Mon-Fri → equities_alpaca_intraday_bridge.py --live --once
Включает dry-run тесты при установке. `--remove` удаляет всё.

**Tested:** все три скрипта работают на исторических данных.

**To activate on server:**
```bash
# Один раз на сервере:
bash scripts/setup_server_crons.sh
```

**Next:**
- Проверить sr_break_retest autoresearch результаты
- Запустить equities v23 локально
- Через 2-3 недели paper → смотреть intraday bridge сигналы

---

## 2026-03-29 | Claude (session 19 — WF intraday bridge)

**Done:**
- Built `scripts/equities_alpaca_intraday_bridge.py` — complete Alpaca intraday paper execution bridge
  - Runs TSLA (breakout_continuation + quality_guard), GOOGL (grid_reversion + safe_winrate), JPM (grid_reversion default)
  - Uses WF-validated presets from `run_forex_multi_strategy_gate.py` PRESETS dict
  - Loads historical M5 seed from `data_cache/equities_1h/{SYM}_M5.csv` (1500 bars warm-up)
  - Fetches live bars from Alpaca data API (`/v2/stocks/{sym}/bars?timeframe=5Min`)
  - Submits **bracket orders** (OCO: market entry + auto SL + auto TP in one request)
  - State persistence: `configs/intraday_state.json` (tracks open positions across cron runs)
  - Detects closed positions (SL/TP hit by Alpaca) on each tick → cleans state
  - Telegram alerts on entry + position close
  - `--dry-run` / `--live` flags, `--once` (cron) and `--daemon` modes
  - Tested: imports OK, CSV loading OK (5078 bars per symbol), dry-run runs cleanly

**To run:**
```bash
# Dry-run (no orders) — test signal detection
python3 scripts/equities_alpaca_intraday_bridge.py --dry-run --once

# Live paper (real Alpaca API calls, fake money)
python3 scripts/equities_alpaca_intraday_bridge.py --live --once

# Daemon loop every 5 min (background)
nohup python3 scripts/equities_alpaca_intraday_bridge.py --live --daemon \
  >> logs/intraday_bridge.log 2>&1 &

# Cron (add to crontab, Mon-Fri market hours):
# */5 14-21 * * 1-5 cd /root/by-bot && python3 scripts/equities_alpaca_intraday_bridge.py \
#   --live --once >> logs/intraday_bridge.log 2>&1
```

**Config (all via env / alpaca_paper_local.env):**
- `INTRADAY_NOTIONAL_USD=200` — $ per position (default 200)
- `INTRADAY_MAX_POSITIONS=3` — max simultaneous positions (default 3)

**Key findings:**
- Bracket orders (OCO) are the right tool: single API call sets entry + SL + TP, Alpaca manages the exit automatically
- Strategy warmup needs ≥250 bars minimum; we seed with 1500 from CSV so EMA220 is always ready
- Session filter set to 14:00–21:00 UTC (covers 10:00 AM – 5:00 PM ET, EDT-aligned)
- State file approach handles cron mode correctly: position closed by Alpaca's SL/TP detected on next tick

**Next:**
- Run dry-run on local machine during market hours to see live signals
- After watching a few signals → switch to `--live` for paper trading
- Remember: equities v23 autoresearch still needs to run locally (equities_monthly_v23_spy_regime_gate.json)

---

## 2026-03-28 | Claude (session 18 — night, DeepSeek autonomy)

**Done:**
- Built `scripts/deepseek_weekly_cron.py` — autonomous weekly DeepSeek research agent
  - Phase 1 `audit`: scans recent backtest_runs, computes per-strategy health (PF/DD/net)
  - Phase 2 `tune`: calls `tune_strategy()` for all 5 active strategies → approval queue
  - Phase 3 `research`: flags finished autoresearch runs with PASS combos
  - Phase 4 `universe`: DeepSeek suggests new symbols per strategy family
  - Phase 5 `report`: sends full Telegram digest + saves Markdown report
  - Dry-run tested: working, already showing live audit data
- Updated ROADMAP.md: added full "DeepSeek Autonomy Architecture" section with capability matrix
- Equities v23 SPY regime gate spec (session 17): ready to run

**Key findings from dry-run audit:**
- Active 5 strategies (golden portfolio): ✅ all PF ≈ 2.13, DD 2.9% — healthy
- `btc_eth_midterm_pullback_v2`: ⚠️ PF=0.37 in autoresearch — still searching, not converged
- `pump_fade_simple`: ⚠️ PF=0.79 in raw runs — 2 PASS combos but thin (10-12 trades)
- `sr_break_retest_volume_v1`: ⚠️ PF=0.56 in raw combos — most combos failing, results pending

**To activate DeepSeek autonomous cycle (on server):**
```bash
crontab -e
# Add:
0 22 * * 0 cd /root/by-bot && python3 scripts/deepseek_weekly_cron.py \
  --quiet >> logs/deepseek_weekly.log 2>&1
```

**Manual run with full API:**
```bash
python3 scripts/deepseek_weekly_cron.py
# Or just audit + research (no API tokens spent):
python3 scripts/deepseek_weekly_cron.py --phases audit,research,report
```

---

## 2026-03-28 | Claude (session 17 — night)

**Done:**
- Deep dive into DeepSeek integration — it is MUCH deeper than expected:
  - `bot/deepseek_overlay.py` — core API client with daily request cap, approval queue, shadow log
  - `bot/deepseek_autoresearch_agent.py` — reads backtest results, proposes param changes via `/ai_tune` Telegram commands
  - `bot/deepseek_action_executor.py` — executes approved actions with safety guardrails
  - Telegram commands: `/ai_results`, `/ai_tune`, `/ai_tune breakout|flat|asc1|midterm|breakdown|alpaca`
  - This is already a full weekly-analysis loop — just triggered manually via Telegram, not on cron yet
- Created `configs/autoresearch/equities_monthly_v23_spy_regime_gate.json` — 108 combos
  - Tests `--benchmark-min-above-sma-count` = 0/1/2 (off / SPY-or-QQQ above SMA / both)
  - Existing code already supports this flag — just no spec ever used it
  - Score weights heavily penalize negative months (×8) and negative streaks (×5)

**Key findings:**
- SPY/QQQ regime gate already implemented in `equities_monthly_research_sim.py` — was just never turned ON in any spec
- Setting `--benchmark-min-above-sma-count 1` would have blocked the March 2026 XOM entry entirely
- DeepSeek already has `/ai_tune alpaca` command — can analyze equities sleeve too
- DeepSeek weekly autoresearch cron is the next logical step (trigger `/ai_tune` automatically)

**To run locally:**
```bash
# Equities v23 with SPY regime gate (108 combos, fast — equities backtest is quick)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/equities_monthly_v23_spy_regime_gate.json \
  > /tmp/equities_v23.log 2>&1 &
```

---

## 2026-03-28 | Claude (session 16 — late evening)

**Done:**
- Explored all strategies/ — found `btc_eth_midterm_pullback_v2` built but never tested (not registered)
- Diagnosed ASR1/ARR1/micro_scalper: 0 trades in 360 days — regime filters too strict
- Registered `btc_eth_midterm_pullback_v2` in `backtest/run_portfolio.py` (all 4 points: import, allowed set, dict init, signal loop)
- Created 3 new autoresearch specs:
  - `midterm_pullback_v2_btceth_v1.json` — 243 combos, channel R2/pos/SL/TP1/slope grid, BTC+ETH
  - `pump_fade_simple_expanded_v1.json` — 324 combos, wider universe (SOL/SUI/AVAX/ADA + memes), same grid as meme spec
  - `asr1_rescue_v1.json` — 972 combos, loosened RSI cap (50→60), broader symbols, fewer confirm bars

**Key findings:**
- `btc_eth_midterm_pullback_v2` adds sloped channel position filter + dynamic TP vs v1 — never tested despite being complete
- ASR1: 0 trades because RSI max=50 + confirm_bars=6 + strict regime — needs loosening
- micro_scalper: 2 trades/360 days on BTC/ETH — signal too rare; would need very different universe
- pump_fade_simple: issue is universe too narrow, not the params — need more liquid alt/meme combos

**To run locally (in this order — midterm_v2 first, highest value):**
```bash
# 1. midterm_v2 — direct upgrade to live strategy (fastest, 243 combos)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/midterm_pullback_v2_btceth_v1.json \
  > /tmp/midterm_v2.log 2>&1 &

# 2. pump_fade expanded — wider universe (324 combos)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_simple_expanded_v1.json \
  > /tmp/pf_expanded.log 2>&1 &

# 3. ASR1 rescue — diagnostic run (972 combos, run last)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/asr1_rescue_v1.json \
  > /tmp/asr1_rescue.log 2>&1 &
```

---

## 2026-03-28 | GPT (session 15 — evening)

**Done:**
- Ran `dynamic_allowlist.py --dry-run` with golden trades.csv backtest gate
- Fixed strategy tags in profiles (added `alt_sloped_channel_v1`, `alt_resistance_fade_v1`, `alt_inplay_breakdown_v1`)
- Built compare snapshot: `full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env`
- Launched annual v5 probe backtest (completed):
  - ASC1: ADAUSDT,LINKUSDT,ATOMUSDT | ARF1: ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,LTCUSDT | BREAKDOWN: BTCUSDT,ETHUSDT,SOLUSDT
- Launched sr_break_retest_volume_v1_revival autoresearch (~12,288 combos, still running as of session end)

**Key findings:**
- v5 dynamic allowlist probe: +94.76%, PF=2.141, 420 trades, DD=2.89%
- Golden baseline: +100.93%, PF=2.078, 446 trades, DD=3.65%
- **Verdict: v5 ≈ golden** — slightly lower return (-6%) but better PF (+3%) and lower DD (-0.76%)
  Main difference: dynamic allowlist dropped BCHUSDT, which contributed ~6% in that specific period
- pump_fade_simple autoresearch: 2 PASS combos (r048 PF=2.34, r129 PF=2.14), only 10-12 trades — too thin for live

**Next:**
- Wait for sr_break_retest_volume_v1 autoresearch to finish
- If passes ≥5 combos → add to portfolio probe as 6th strategy
- For pump_fade_simple → expand symbol universe or run longer period to get trade count up

---

## 2026-03-28 | Claude (sessions 13–14)

**Done:**
- Built `scripts/dynamic_allowlist.py` — live Bybit market scanner with per-strategy profiles
  (ASC1, ARF1, BREAKDOWN), optional backtest gate, dry-run mode, cron-ready
- Full Alpaca diagnosis: monthly momentum strategy has 1 trade (XOM, -3.79% stopped out March 2).
  Root cause: no regime filter. Market was risk-off (SPY selloff), strategy entered anyway.
- Identified WF-validated intraday strategies already sitting in backtest_runs:
  TSLA breakout_continuation (67% WF), GOOGL grid_reversion (67% WF), JPM grid_reversion (67% WF)
- Updated ROADMAP.md with full priority queue and 12-month architecture blueprint
- Created JOURNAL.md (this file)

**Key findings:**
- First Alpaca fix to test: add SPY 50-SMA regime gate to equities_monthly_research_sim.py
- The intraday WF strategies are already validated — they just need an execution bridge
- dynamic_allowlist.py ready to use, needs first dry-run from local machine

**Pending (user to run locally):**
- `python3 scripts/dynamic_allowlist.py --dry-run`
- `python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/pump_fade_simple_meme.json`

---

## 2026-03-28 | Claude (sessions 11–12)

**Done:**
- Full pump_fade revival research cycle completed
- Discovered: archive code ≠ baseline — archive has 6+ extra filters not in baseline commit e341055e
- Built `strategies/pump_fade_simple.py` — exact 190-line replica of baseline commit
- Registered pump_fade_simple in backtest/run_portfolio.py (all 5 registration points)
- Created autoresearch spec: `configs/autoresearch/pump_fade_simple_meme.json` (486 combos)
- Built `strategies/pump_fade_v4r.py` — fixed v4 archive with cooldown bug resolved
- Ran v4r autoresearch: 0/243 combos passed (correct — climax wick too rare on liquid alts)
- Diagnosed portfolio "drop" 100%→53%: NOT code break, just time window shift
- Confirmed golden portfolio intact: `portfolio_20260325_172613_new_5strat_final` (+100.93%)

**Key findings:**
- pump_fade baseline = simple 190-line code, not archive version
- VM cache only has ~11 days history → autoresearch MUST run on local machine
- Portfolio drop is not a code break; it is partly a time-window shift and partly config/pocket drift

---

## 2026-03-27 | GPT (session 10)

## 2026-04-01 | Codex | Alpaca dynamic builder enabled server-side

**Done:**
- Added algorithmic intraday watchlist builder: `scripts/build_equities_intraday_watchlist.py`
- Patched `scripts/equities_alpaca_intraday_bridge.py` to refresh watchlist automatically before each dry-run/live cycle
- Verified server compile for:
  - `scripts/build_equities_intraday_watchlist.py`
  - `scripts/equities_alpaca_intraday_bridge.py`
- Ran server dry-run with dynamic builder enabled
- Confirmed dynamic watchlist output on server:
  - `MDB, TSLA, XOM, SNOW, NFLX, META, AMD, NVDA, ABBV, AAPL, COST, WMT`
- Updated server cron so `Alpaca intraday` now runs every 5 minutes with:
  - `INTRADAY_DYNAMIC_BUILD=1`
  - `INTRADAY_DYNAMIC_MAX_SYMBOLS=12`
  - `INTRADAY_DYNAMIC_BREAKOUT_TARGET=6`
  - `INTRADAY_DYNAMIC_REVERSION_TARGET=6`
  - `INTRADAY_DYNAMIC_MIN_AVG_DOLLAR_VOL=25000000`
- Confirmed current server behavior:
  - monthly Alpaca: `dry_run_no_current_cycle`
  - intraday Alpaca: alive, but entries currently blocked by bearish `SPY < SMA50` gate
- Kept `InPlay minute v3` running as the only active scalper research candidate

---

## 2026-04-01 | Codex | Sloped resistance confluence short v1 created

**Done:**
- Built a new short-only confluence strategy:
  - [sloped_resistance_choch_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/sloped_resistance_choch_v1.py)
- Strategy logic combines:
  - sloped 1H regression channel
  - repeated horizontal resistance near the upper band
  - rejection candle from that confluence
  - 5m bearish structure-shift approximation before entry
- Wired it into the backtest engine:
  - [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- Added first bounded research spec:
  - [sloped_resistance_choch_v1_probe.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/sloped_resistance_choch_v1_probe.json)
- Compile + JSON validation passed
- Smoke backtest completed:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260401_204308_src1_smoke/summary.csv)
  - result: `1` trade, small loss `-0.11`
- Launched first autoresearch probe for the new sleeve

---

**Done:**
- Applied live breakout fix patch: `configs/live_breakout_v3_overlay_20260328.env`
- Server health check confirmed strategies running

---

## Before 2026-03-27 | Earlier sessions

- Initial bot setup with 5 strategies
- Golden portfolio research: +100.93%, PF=2.078, 5 strategies, 10 symbols
- DeepSeek signal audit integration
- Autoresearch pipeline established
- Equities WF gate research completed (TSLA, GOOGL, JPM, JPM validated)

---

## Quick Reference

**Server:** 64.226.73.119
**Bot dir (server):** /root/by-bot/
**Bot dir (local):** ~/Documents/Work/bot-new/bybit-bot-clean-v28/

**Golden portfolio:** `portfolio_20260325_172613_new_5strat_final`
- Return: +100.93% | PF: 2.078 | Strategies: 5 | Symbols: 10

**Current live overlay:** `live_breakout_v3_overlay_20260328.env` (applied on top of existing live5 config, 2026-03-28)

**Current allowlists:**
- ASC1: ATOMUSDT, LINKUSDT, DOTUSDT
- ARF1: LINKUSDT, LTCUSDT, SUIUSDT, DOTUSDT, ADAUSDT, BCHUSDT
- BREAKDOWN: BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, ATOMUSDT, LTCUSDT

**Alpaca paper config:** `configs/alpaca_paper_local.env`
- Max positions: 2 | Alloc: 45% per position | Capital override: $500

**AI roles:**
- Claude: architect, research specs, diagnosis, code
- GPT: deployment, server ops, quick fixes
- DeepSeek: signal audit (live), weekly analysis (planned)

---

## 2026-04-02 | Breakout compare prioritized, minute InPlay cut

**Decision:**
- Stopped `inplay_scalper_minute_probe_v3_relaxed` after it kept printing only negative rows on 1m/3m entry.
- Prioritized live `inplay_breakout` improvement instead of further minute compression.

**Why:**
- Historical `breakout_live_bridge_v3_density` already proved the live sleeve has edge:
  - `+20.67%`, `PF 1.403`, `DD 2.94`, `344 trades`
- `breakout_weak_chop_probe_v1` improved that profile further:
  - `+23.85%`, `PF 1.407`, `DD 3.13`, `412 trades`
- This points to regime/chop/quality tuning as the main path, not smaller entry TF.

**New run:**
- Added `configs/autoresearch/breakout_live_bridge_v4_regime_exit_compare.json`
- Goal: bounded compare around:
  - `quality=0.53`
  - `regime=ema`
  - `chop_er_min`
  - `min_pullback`
  - `RR`
  - fixed-mode `time_stop_bars=96`

**Kept alive:**
- `sloped_resistance_choch_v1_probe` stays on as the new confluence-short idea.

**Live debug instrumentation:**
- Added `planned_rr` and `post_fill_rr` tracking for `inplay_breakout` entries in `smart_pump_reversal_bot.py`.
- Goal: verify whether live RR degradation comes from market fill drift / rounding after entry, or from already-weak setup geometry before the order is sent.

**Breakout compare correction:**
- Stopped the first `breakout_live_bridge_v4_regime_exit_compare` attempt after early rows went deeply negative.
- Reason: that compare changed too many dimensions at once (`ema` regime + `chop_er` + `time_stop` + `RR`) and stopped being a clean improvement test.
- Replaced with `breakout_live_bridge_v4b_exit_compare`:
  - only the two historically strongest entry pockets
  - compare `RR` and `time_stop_bars`
  - keep regime `off` to avoid testing a different strategy by accident

## 2026-04-02 | Bear-market focus tightened: weak fronts cut, breakdown recent-window launched

**Decision:**
- Stopped `breakout_live_bridge_v4b_exit_compare` after the first 20 rows stayed deeply negative on the current window.
- Stopped `sloped_resistance_choch_v1_probe` after it kept producing only `1-2` trade rows and no viable density.
- Redirected the next crypto research slot to `breakdown_recent_bear_window_v1`.

**Why:**
- The live bot is currently too dependent on `inplay_breakout` longs.
- `alt_inplay_breakdown_v1` already exists in live, but realized activity is too sparse to matter.
- The right next move is not another `RR` tweak to longs, but a bounded recent-window test of the dedicated short sleeve on the current bearish/choppy market.

**New run:**
- Added `configs/autoresearch/breakdown_recent_bear_window_v1.json`
- Scope:
  - last `120` days ending `2026-04-01`
  - top liquid crypto universe
  - compare `regime on/off`, `lookback`, `RR`, `pullback depth`, and `ER anti-chop`
- Goal:
  - find whether breakdown can become a real second crypto income sleeve in the current market instead of staying decorative.

## 2026-04-02 | InPlay regime-quality repair launched; pump momentum moved to bug-fix status

**What changed:**
- Added `configs/autoresearch/breakout_live_bridge_v6_regime_quality_compare.json`
- Purpose:
  - compare the current permissive live-style `inplay_breakout` profile versus a stricter recent-window repair:
    - `BREAKOUT_REGIME_MODE=ema`
    - `BREAKOUT_IMPULSE_VOL_MULT=1.2`
    - tighter `BREAKOUT_MAX_RETEST_BARS`
    - optional `BREAKOUT_MIN_HOLD_BARS=2`
- Window:
  - `90` days ending `2026-04-01`

**Why:**
- `fixed vs runner` did not improve `InPlay`.
- Current weakness looks structural, not exit-only:
  - regime filter effectively off
  - no HTF volume confirmation by default
  - retest window too stale / permissive

**Pump/dump note:**
- `pump_fade_v4r_bear_window` is technically alive but early rows show `0 trades`.
- `pump_momentum_v1_initial` is not ready for interpretation yet:
  - full grid is crashing with `CalledProcessError`
  - moved into bug-fix / traceback-capture status before any edge judgement.

## 2026-04-03 | Control-plane became locally executable end-to-end

**What changed:**
- Hardened [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py):
  - keeps the fresh fetch path
  - falls back to exact cached fetch
  - if that still fails, aggregates the latest lower-TF local BTC cache into 4H bars
- Hardened [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py):
  - atomic env/json writes
  - router state metadata
  - regime override
  - degraded fallback to the previous overlay
  - profile-level `exclude_symbols`
  - lighter scan defaults for control-plane use
- Added runtime visibility in [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py):
  - router regime/profile lines in `/status_full`
  - optional router health checks behind `ROUTER_HEALTH_ENABLE`
- Reduced scan stickiness in [dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py):
  - configurable REST timeout
  - configurable ATR fetch retry/backoff budget

**Verified locally:**
- Orchestrator now succeeds even when fresh Bybit BTC 4H fetch is rate-limited.
- Local run wrote:
  - [orchestrator_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/regime/orchestrator_state.json)
  - [regime_orchestrator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/regime_orchestrator_latest.env)
- Current locally detected regime: `bear_chop`
  - risk multiplier `0.70`
  - breakout `OFF`
  - breakdown `ON`
  - flat `ON`
  - midterm `ON`
- Router now writes:
  - [dynamic_allowlist_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/dynamic_allowlist_latest.env)
  - [symbol_router_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/router/symbol_router_state.json)
- Under `bear_chop`, the local dynamic baskets currently resolve to:
  - breakout: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - breakdown: `BTC,ETH,SOL,XRP,DOGE,TAO,HYPE,FARTCOIN`
  - sloped: `XRP,DOGE,HYPE,ADA,LINK`
  - flat: `XRP,DOGE,HYPE,ADA,LINK,SUI,DOT`
  - midterm: `BTC,ETH`

**Why this matters:**
- We no longer have only a design for the control plane; we now have a local working loop:
  - regime state
  - per-sleeve symbol routing
  - bot-side hot-reload visibility
- This is the right foundation before touching live crypto sleeve repairs again.

**Next:**
- isolate a clean push-set for orchestrator + router changes
- then do server dry-run rollout
- only after that return to `breakout/breakdown` repair on top of the new control plane

## 2026-04-03 | Router profiles became regime-specific and versioned

**What changed:**
- Checked the real strategy logic before tightening the router:
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py) is bidirectional channel mean-reversion, not a pure bear-only short sleeve
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) is a short resistance fade and deserves a reduced basket in strong-trend regimes
- Updated [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json):
  - added `profile_version=2026-04-03-control-plane-v2`
  - split `ASC1` into:
    - `asc1_trend_reduced`
    - `asc1_chop_core`
  - split `ARF1` into:
    - `arf1_bull_reduced`
    - `arf1_bear_reduced`
    - `arf1_chop_core`
- Updated [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) so `symbol_router_state.json` and the env overlay now include `ROUTER_PROFILE_VERSION`

**Verified:**
- New dry-run under the current local regime `bear_chop` produced:
  - breakout profile: `breakout_bear_guarded`
  - breakdown profile: `breakdown_bear_core`
  - sloped profile: `asc1_chop_core`
  - flat profile: `arf1_chop_core`
  - midterm profile: `midterm_btceth_core`
- Current `bear_chop` baskets after the profile split:
  - breakout: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - breakdown: `BTC,ETH,SOL,XRP,DOGE,TAO,HYPE,FARTCOIN`
  - sloped: `XRP,DOGE,HYPE`
  - flat: `XRP,DOGE,HYPE,ADA,LINK`
  - midterm: `BTC,ETH`

**Why this matters:**
- The dynamic symbol layer is no longer one-size-fits-all.
- We can now backtest profile logic separately from core strategy logic and know exactly which profile version produced a result.

## 2026-04-03 | Funding carry is runnable again and produced a first conservative baseline

**What changed:**
- Added the capital-efficient sleeve ideas into [ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md):
  - funding harvest first
  - Hyperliquid second venue next
  - treasury deployment (`CEX Earn`, `Aave`) later
  - DeFi/arb after core stability
- Found a real funding-branch breakage:
  - [backtest_funding_capture.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/backtest_funding_capture.py) imported `strategies.funding_hold_v1`
  - that selector file had been archived out of `strategies/`
- Restored the lightweight selector as [funding_hold_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/funding_hold_v1.py)

**Verified:**
- Funding scripts compile again:
  - [backtest_funding_capture.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/backtest_funding_capture.py)
  - [strategy_symbol_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/strategy_symbol_gate.py)
- Ran a conservative 365d baseline on a fixed liquid universe:
  - symbols tested: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - selected basket: `BTC,DOGE,ETH,XRP`
  - outputs:
    - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/summary.csv)
    - [funding_per_symbol.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/funding_per_symbol.csv)
    - [monthly_pnl.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/monthly_pnl.csv)

**Human reading of the result:**
- The script modeled `4` symbols with `100 USD` notional each
- total modeled basket notional: `400 USD`
- net result after modeled fees: `+15.14 USD`
- simple reading: about `+3.78%` over `365` days on that modeled notional basket
- months:
  - mostly small green carry months
  - one red month: `2026-02`
- per-symbol leaders:
  - `BTC +4.00 USD`
  - `DOGE +3.87 USD`
  - `ETH +3.84 USD`
  - `XRP +3.43 USD`

**Caveat:**
- This is a useful baseline, not final truth.
- The current script still simplifies:
  - symbol selection
  - fee model
  - capital lock-up / margin model
  - spot hedge execution assumptions
- So funding carry is now back on the board as a serious candidate, but still needs a second validation pass before live.

## 2026-04-03 - Control-Plane Guardrails Added

**What changed:**
- Extended [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py) so every real orchestrator cycle appends a machine-readable line to [orchestrator_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/orchestrator_history.jsonl).
- Extended [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) so every real router rebuild appends a machine-readable line to [symbol_router_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/symbol_router_history.jsonl).
- Both overlays now export their history-path metadata:
  - [regime_orchestrator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/regime_orchestrator_latest.env)
  - [dynamic_allowlist_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/dynamic_allowlist_latest.env)
- Added [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py) as a dedicated gate for the trusted `v5` stack.

**What the new regression helper does:**
- Anchors to the exact trusted overlay:
  - [full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env)
- Anchors to the trusted annual summary:
  - [portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv)
- Builds the exact `run_portfolio.py` command from that trusted artifact.
- Compares fresh output against trusted `net`, `PF`, `DD`, and `trade count` with explicit tolerances.
- Writes machine-readable reports to:
  - [baseline_regression_latest.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_latest.json)
  - [baseline_regression_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_history.jsonl)

**Verification done:**
- `py_compile` passed for:
  - [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py)
  - [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py)
  - [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py)
- `run_validated_baseline_regression.py --dry-run` resolved the trusted annual command correctly.
- Ran one real orchestrator cycle:
  - fallback path still works
  - current local regime stayed `bear_chop`
  - history file was created and populated
- Ran one real router cycle:
  - scan completed
  - current router history file was created and populated

**Current next step:**
- The first real validated-baseline regression run has been launched and is in progress.

## 2026-04-03 - First Baseline Regression Verdict

**Result:**
- The first real trusted-`v5` regression run finished and **failed**.
- Report:
  - [baseline_regression_latest.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_latest.json)
  - [baseline_regression_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_history.jsonl)
- Fresh run artifacts:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/summary.csv)
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/trades.csv)

**Expected vs actual:**
- Expected trusted annual:
  - `100 -> 189.65`
  - `+89.65%`
  - PF `2.121`
  - DD `2.88%`
  - `427` trades
- Actual fresh rerun:
  - `100 -> 111.24`
  - `+11.24%`
  - PF `1.148`
  - DD `8.77%`
  - `211` trades

**Meaning:**
- This is not a tiny drift.
- The exact trusted annual result is **not currently reproducible** on the present local stack/data path.
- So the new regression gate already paid for itself:
  - it blocked us from pretending the old golden annual is still confirmed truth
  - it gave us a concrete discrepancy to investigate next

## 2026-04-03 - Quick Project Noise Audit

**Large buckets:**
- [data_cache](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/data_cache): about `644M`
- [backtest_runs_old_20260303.tgz](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs_old_20260303.tgz): about `6.7M`
- [backtest_archive](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive): about `1.2M`

**Obvious junk candidates (not deleted yet):**
- [.env.bak_20260326_local_sync](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.env.bak_20260326_local_sync)
- [runtime/live_breakout_allowv2.pid](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_breakout_allowv2.pid)
- [runtime/mplconfig](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/mplconfig)
- repo-level `__pycache__` / `.pyc` trees outside `.venv`

**Not junk by default:**
- [backtest_archive](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive)
- [runtime/control_plane](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane)
- [runtime/regime](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/regime)
- [runtime/router](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/router)
- [data_cache](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/data_cache) until we decide a clean cache policy

## 2026-04-03 - Safe Cleanup and New Strategy Queue

**Cleanup done:**
- Updated [.gitignore](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.gitignore) so future audits are quieter:
  - ignore `runtime/`
  - ignore `backtest_archive/`
  - ignore generated latest overlays/state
  - ignore `trades.db`
  - ignore underscore-form `.env.bak_*`
- Deleted only obvious disposable local artifacts:
  - [.env.bak_20260326_local_sync](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.env.bak_20260326_local_sync)
  - [runtime/live_breakout_allowv2.pid](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_breakout_allowv2.pid)
  - [runtime/mplconfig](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/mplconfig)
  - repo-level `__pycache__` trees outside `.venv`

**New strategies from Codex checked:**
- Present and compiling:
  - [alt_inplay_breakdown_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v2.py)
  - [pump_fade_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/pump_fade_v2.py)
  - [alt_support_bounce_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_support_bounce_v1.py)
  - [alt_range_scalp_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_range_scalp_v1.py)
  - [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py)
- Also verified that [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) already:
  - imports them
  - allows them in CLI validation
  - instantiates them
  - routes them into signal generation

**Important correction before research:**
- The five new autoresearch specs existed but all had `cache_only=true`.
- After the current reproducibility incident, that is the wrong evidence path.
- Switched them to fresh-data mode and JSON-validated:
  - [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
  - [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
  - [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
  - [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)
  - [elder_ts_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_sweep_v1.json)

**Research queue order recorded:**
1. `alt_range_scalp_v1`
2. `alt_inplay_breakdown_v2`
3. `alt_support_bounce_v1`
4. `pump_fade_v2`
5. `elder_triple_screen_v2`

**Constraint kept:**
- We still should not trust fresh research more than the failed annual reproducibility question.
- The next high-trust task remains forensic analysis of why the trusted `v5` annual no longer reproduces.

## 2026-04-03 - First Forensic Diff of Old vs Fresh Annual

**Compared:**
- Trusted annual:
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/trades.csv)
- Fresh failed rerun:
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/trades.csv)

**Big picture:**
- Trusted annual:
  - `427` trades
  - `0` red months
- Fresh rerun:
  - `211` trades
  - `4` red months

**Monthly shape:**
- Trusted:
  - `2025-04 +8.76%`
  - `2025-05 +7.77%`
  - `2025-06 +8.13%`
  - `2025-07 +3.43%`
  - `2025-08 +7.10%`
  - `2025-09 +2.86%`
  - `2025-10 +5.17%`
  - `2025-11 +10.91%`
  - `2025-12 +0.74%`
  - `2026-01 +4.48%`
  - `2026-02 +3.78%`
  - `2026-03 +1.60%`
- Fresh:
  - `2025-04 -0.88%`
  - `2025-05 -2.08%`
  - `2025-06 +5.15%`
  - `2025-07 -0.40%`
  - `2025-08 +1.86%`
  - `2025-09 +1.12%`
  - `2025-10 +2.71%`
  - `2025-11 +1.04%`
  - `2025-12 -2.06%`
  - `2026-01 +2.43%`
  - `2026-02 +2.18%`
  - `2026-03 +0.55%`

**Per-strategy delta:**
- Trusted:
  - `alt_inplay_breakdown_v1`: `168` trades, `+34.24%`
  - `alt_resistance_fade_v1`: `48`, `+21.11%`
  - `alt_sloped_channel_v1`: `30`, `+8.63%`
  - `btc_eth_midterm_pullback`: `51`, `+8.27%`
  - `inplay_breakout`: `130`, `+17.41%`
- Fresh:
  - `alt_inplay_breakdown_v1`: `67`, `-12.44%`
  - `alt_resistance_fade_v1`: `63`, `+13.49%`
  - `alt_sloped_channel_v1`: `28`, `+4.90%`
  - `btc_eth_midterm_pullback`: `34`, `+6.35%`
  - `inplay_breakout`: `19`, `-1.06%`

**Main learning:**
- The mismatch is concentrated in the same momentum sleeves:
  - `inplay_breakout`
  - `alt_inplay_breakdown_v1`
- The quieter sleeves stayed broadly positive.
- So the regression failure does **not** look like “everything is randomly broken”.

**Current working hypothesis:**
- More likely:
  - data path drift
  - cache/fetch drift
  - hidden engine assumption drift
- Less likely:
  - one giant rewrite of the quiet sleeves

**Reason:**
- Core code drift in the affected annual stack exists, but the direct diffs are not huge:
  - [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py)
  - [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py)
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py)
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py)
  - [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)

So the next right step remains:
- deeper apples-to-apples forensics on data slices and engine assumptions
- only then fresh optimizer sweeps

## 2026-04-03 - Two Fresh Sweeps Started

**Why only two, not all five:**
- We do want higher доход, более частые входы и сильнее edge.
- But after the failed annual reproducibility check, launching all five new fronts at once would create too much noise.
- So the bounded choice is:
  1. one current-market income candidate
  2. one current-market momentum/short repair candidate

**Started now:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
  - run dir: [autoresearch_20260403_103012_range_scalp_v1_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_103012_range_scalp_v1_sweep_v1)
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
  - run dir: [autoresearch_20260403_103012_breakdown_v2_1h_bear_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_103012_breakdown_v2_1h_bear_sweep_v1)

**Current status:**
- Both `results.csv` files exist and currently contain only header rows.
- So they are genuinely just started; no verdict yet.

## 2026-04-03 - Sleeve-Specific Forensic Clue

**Breakout old vs fresh:**
- Trusted annual:
  - `94 TP`
  - `36 SL`
  - total `130` trades
- Fresh rerun:
  - `9 TP`
  - `10 SL`
  - total `19` trades

**Breakdown old vs fresh:**
- Trusted annual:
  - `92 TP`
  - `76 SL`
  - total `168` trades
  - strong symbols: `ETH`, `SOL`, `BTC`
- Fresh rerun:
  - `17 TP`
  - `50 SL`
  - total `67` trades
  - worst symbol: `SOL` around `-8.54%`

**Meaning:**
- This is not just “the bot traded less”.
- `breakdown` quality actually flipped.
- So the annual mismatch is concentrated and real.

## 2026-04-03 - Cache Gap Found for Trusted Annual

**New concrete clue:**
- In [.cache/klines](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.cache/klines), the exact trusted annual 5m slice for `2025-04-01 -> 2026-03-27` exists only for:
  - `LINKUSDT`
  - `BTCUSDT`
  - `ETHUSDT`
  - `SOLUSDT`
- It is missing for:
  - `ADAUSDT`
  - `ATOMUSDT`
  - `SUIUSDT`
  - `DOTUSDT`
  - `LTCUSDT`

**Why this matters:**
- [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) currently supports cache fallback.
- If fresh fetch fails, the engine can silently use the “best” cached slice from a different period.
- That is exactly the kind of evidence drift we were trying to eliminate.

**Action taken:**
- Started a stricter annual rerun with cache fallback disabled:
  - `BACKTEST_CACHE_FALLBACK_ENABLE=0`
- This run is now the next honest test of whether the annual mismatch is primarily cache-path drift.

## 2026-04-03 - Early Fresh Research Signal

**Range scalper:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json) started producing first rows.
- The first rows are all formal FAILs under the current constraints.
- But raw shape is already interesting:
  - some early combos around `net 8-10%`
  - PF around `1.9-2.6`
  - DD around `2.4-3.4`
- So `alt_range_scalp_v1` currently looks alive enough to keep running.

**Breakdown v2 1h:**
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json) is also running
- but had not yet produced visible result rows at this checkpoint.

## 2026-04-03 - Expanded Research Front, Alpaca Safe

**Alpaca / forex branch audit:**
- Confirmed the non-crypto branches were not lost during cleanup.
- The repo still contains the main equities/Alpaca bridge and configs:
  - [equities_alpaca_intraday_bridge.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equities_alpaca_intraday_bridge.py)
  - [run_equities_alpaca_paper.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_alpaca_paper.sh)
  - [alpaca_paper_v36_candidate.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/alpaca_paper_v36_candidate.env)
- The separate forex stack is also still present:
  - [forex/engine.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/forex/engine.py)
  - [run_forex_backtest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_backtest.py)

**Strict annual regression update:**
- The no-fallback annual rerun did not finish.
- It stopped on a Bybit `10006` rate-limit while exact-fetching `ADAUSDT`.
- That does not disprove the cache-drift hypothesis; it reinforces that exact data acquisition is the current blocker.

**Current research queue:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json) keeps producing encouraging raw rows:
  - multiple combos around `net 10-12%`
  - DD roughly `0.8-3.3`
  - still formal FAIL because of gate settings, not because the raw edge is absent
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json) is still printing zero-trade rows in the early block

**New sweeps started:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)

**Why this ordering:**
- We are expanding from the strongest current signal (`range_scalp`) and the need for diversification.
- We are not opening every front at once, because that would create noise before we restore trust in the annual baseline path.

## 2026-04-03 - Allocator and Safe Mode Layer Added

**What was built:**
- Added allocator policy:
  - [portfolio_allocator_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy.json)
- Added deterministic allocator builder:
  - [build_portfolio_allocator.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py)

**What it now does:**
- Reads:
  - orchestrator state
  - symbol router state
  - [strategy_health.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_health.json)
- Writes:
  - [portfolio_allocator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_latest.env)
  - [portfolio_allocator_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/portfolio_allocator_state.json)
  - [portfolio_allocator_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/portfolio_allocator_history.jsonl)

**Live-bot integration:**
- [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now:
  - reloads allocator overlay on startup and in pulse
  - multiplies base risk by both orchestrator and allocator
  - supports `BREAKOUT_RISK_MULT` and `MIDTERM_RISK_MULT`
  - can hard-block all new entries through `portfolio_can_open()` when allocator says data/control-plane is unsafe

**Current allocator verdict (local):**
- regime: `bear_chop`
- allocator status: `degraded`
- hard block: `off`
- global risk multiplier: `0.60`
- sleeves:
  - breakout: disabled
  - breakdown: enabled, trimmed to `0.7125` because health file marks it `WATCH`
  - flat: enabled, `1.05`
  - sloped: enabled, `0.81`
  - midterm: enabled, `0.60`

## 2026-04-03 - Research Queue Update

**Range scalper keeps improving as a current-market candidate:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
- multiple rows already around:
  - `net 11-12%`
  - DD around `0.3-0.8` in the best tiny-trade pockets
  - still formal FAIL under current gates, so we should not over-promote it yet

**Support bounce opened weak:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- first rows are consistently negative
- current read: this is not a leading candidate yet

## 2026-04-03 - Pump Fade V2 Was Crashing, Not Failing

**Concrete bug found:**
- [pump_fade_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/pump_fade_v2.py) expected `store.fetch_klines(...)`
- but the real portfolio selector passes `symbol + current bar`
- crash reproduced directly as:
  - `AttributeError: 'str' object has no attribute 'fetch_klines'`

**Fix applied:**
- Reworked `pump_fade_v2` to use its own rolling 5m bar buffer from sequential bar calls instead of asking for a store object.

**Verification:**
- `py_compile` passes
- 30d smoke backtest now completes cleanly at:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_144532_pump_fade_v2_smoke_fix/summary.csv)
- smoke result:
  - `0` trades
  - `0.00%`
  - no crash

**Important interpretation:**
- The currently running long `pump_fade_v2_sweep_v1` still contains many pre-fix crash rows.
- That active run is now contaminated as evidence and should be restarted later instead of treated as a valid strategy verdict.

**Follow-up completed:**
- The contaminated old `pump_fade_v2_sweep_v1` run was stopped.
- A fresh clean rerun from the same spec was started after the fix, so future rows can be interpreted normally.

## 2026-04-03 - Exact Annual Cache Gate Hardened

**Why this mattered:**
- We already had a strong suspicion that annual truth was getting distorted by cache fallback and environment drift.
- The old regression helper could still run on the wrong Python and could still attempt a baseline rerun without explicitly proving that the exact annual slices existed first.

**What changed:**
- Added:
  - [check_exact_kline_cache.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_exact_kline_cache.py)
- Updated:
  - [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py)

**New regression behavior:**
- It now computes the exact trusted annual 5m window from:
  - `days=360`
  - `end_date_utc=2026-03-27`
- It audits exact cache coverage for the full trusted union before running.
- In `require` mode, it refuses to run if any exact slice is missing.
- When exact slices exist, it forces:
  - `BACKTEST_CACHE_ONLY=1`
  - `BACKTEST_CACHE_FALLBACK_ENABLE=0`
- It now prefers project:
  - `.venv/bin/python3`
  instead of the system interpreter.

**What we learned immediately:**
- The trusted annual union currently has full exact 5m cache coverage for:
  - `ADA`
  - `ATOM`
  - `LINK`
  - `SUI`
  - `DOT`
  - `LTC`
  - `BTC`
  - `ETH`
  - `SOL`
- So the annual gate can now be rerun honestly from exact local slices instead of "best cached slice" fallback.

**Why this is good even before final annual numbers return:**
- If the new annual still fails, we can stop blaming missing exact slices.
- If it matches or improves, we finally have a reproducible path back to trusted annual truth.

**Extra environment fix caught on the way:**
- The first hardened rerun failed not on market logic, but because it launched `run_portfolio.py` under the system Python and hit:
  - `ModuleNotFoundError: numpy`
- That is now fixed by preferring the project `.venv`, so the annual gate is no longer polluted by interpreter drift.

## 2026-04-03 - Research Queue Reality Check

**Range scalper still leads:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
- By row `240`, the visible positive pockets are still there:
  - roughly `+6.9%` to `+9.85%`
  - drawdown still very small: `~0.33-1.24`
- The main reason it keeps showing as FAIL is still:
  - `trades < 40`
- Interpretation:
  - not promoted yet
  - but still the best current-market candidate in the queue

**Breakdown v2 1h is not waking up yet:**
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
- Through row `121`, the visible block is still all:
  - `0 trades`
  - `0 net`
  - `0 PF`
- Interpretation:
  - this is now more than just "warming up"
  - the current search region looks weak

**Support bounce remains weak:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- Through row `68`, rows are still failing on:
  - PF
  - negative months
  - negative streak
- Net is positive in spots (`~+3.6%` to `+4.4%`), but the quality is not good enough.

**Pump fade v2 is fixed technically, but weak strategically so far:**
- [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)
- The clean rerun is now producing real rows instead of crash spam.
- First visible honest rows are still poor:
  - net around `-2.8%` to `-41%`
  - DD around `12-52`
- Interpretation:
  - interface bug is solved
  - current parameter zone is not good

## 2026-04-03 - Honest Annual Verdict and What It Means

**Big truth update:**
- The hardened annual rerun is finished.
- It used:
  - exact annual 5m cache slices
  - project `.venv`
  - the trusted symbol union
  - the trusted overlay
- And it still did **not** reproduce the historical golden annual.

**Expected vs actual:**
- trusted annual reference:
  - `+89.65%`
  - PF `2.121`
  - DD `2.88`
  - `427` trades
- honest rerun:
  - `+11.24%`
  - PF `1.148`
  - DD `8.77`
  - `211` trades

**What this means now:**
- The old mismatch is no longer explainable by:
  - missing exact annual slices
  - system Python drift
- So the next suspect class is:
  - strategy logic drift
  - shared engine drift
  - changed defaults in the portfolio path

**Per-strategy contribution on the honest rerun:**
- positive:
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) about `+13.49`
  - [btc_eth_midterm_pullback.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/btc_eth_midterm_pullback.py) about `+6.35`
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py) about `+4.90`
- negative:
  - [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py) about `-1.06`
  - [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) about `-12.44`

**Immediate interpretation:**
- `alt_inplay_breakdown_v1` is now the clearest rewrite / retirement candidate.
- `inplay_breakout` is not dead, but it is not carrying the stack and should stay in repair rather than live-trusted status.
- `fade`, `midterm`, and `sloped` currently look healthier than the momentum sleeves.

## 2026-04-03 - Plain-Language Forensic Read of the Momentum Sleeves

**Whole honest annual rerun:**
- portfolio:
  - `+11.24%`
  - winrate `40.8%`
  - max DD `8.77%`
  - `211` trades
  - `4` red months
  - `8` green months
- monthly shape:
  - `2025-04 -0.88%`
  - `2025-05 -2.08%`
  - `2025-06 +5.15%`
  - `2025-07 -0.40%`
  - `2025-08 +1.86%`
  - `2025-09 +1.12%`
  - `2025-10 +2.71%`
  - `2025-11 +1.04%`
  - `2025-12 -2.06%`
  - `2026-01 +2.43%`
  - `2026-02 +2.18%`
  - `2026-03 +0.55%`

**Breakout vs historical baseline:**
- trusted annual:
  - `130` trades
  - `72.3%` winrate
  - `+17.41%`
- honest rerun:
  - `19` trades
  - `47.4%` winrate
  - `-1.06%`
  - `4` red months / `3` green months

**Breakdown v1 vs historical baseline:**
- trusted annual:
  - `168` trades
  - `54.8%` winrate
  - `+34.24%`
- honest rerun:
  - `67` trades
  - `25.4%` winrate
  - `-12.44%`
  - `9` red months / `3` green months

**Most important code-level insight:**
- [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) is only a thin wrapper.
- It delegates to [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py).
- And that wrapper delegates the real momentum logic to:
  - [sr_inplay_retest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/sr_inplay_retest.py)

**Practical implication:**
- If the original breakout/retest engine changed over time, both sleeves would drift together.
- That fits the evidence much better than "random market bad luck".

**Approximate per-strategy drawdown on the honest annual rerun**
using trade-sequence equity from `pnl_pct_equity` as a quick forensic proxy:
- `alt_inplay_breakdown_v1`: about `12.75%`
- `alt_resistance_fade_v1`: about `3.62%`
- `alt_sloped_channel_v1`: about `2.34%`
- `btc_eth_midterm_pullback`: about `2.91%`
- `inplay_breakout`: about `2.33%`

This strengthens the same conclusion:
- `breakdown_v1` is not just slightly negative; it is the sleeve with the nastiest standalone damage profile in the current honest annual rerun.

## 2026-04-03 - Audit Fixes Landed

**Autopilot truth-path fixed**
- [equity_curve_autopilot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equity_curve_autopilot.py)
- Default run selection no longer grabs the newest random `portfolio_*`.
- It now prefers the latest trusted baseline regression artifact and rejects exploratory runs by default unless `--allow-exploratory` is passed.
- Verification:
  - running in quiet mode now rewrites [strategy_health.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_health.json) from:
    - `portfolio_20260403_150051_validated_baseline_regression_20260403_120047`

**Allowlist watcher dry-run fixed**
- [allowlist_watcher.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/allowlist_watcher.py)
- Standalone `apply_now()` now resolves the file path correctly instead of crashing on undefined `ALLOWLIST_FILE`.
- Verification:
  - `python3 bot/allowlist_watcher.py --dry-run` works

**Health gate coverage improved**
- [health_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/health_gate.py)
- Added mappings for:
  - `micro_scalper_v1`
  - `alt_support_reclaim_v1`
- Missing known live sleeves no longer silently read as `OK`; they default to `WATCH`.
- Verification:
  - `micro_scalper_v1 -> WATCH`
  - `alt_support_reclaim_v1 -> WATCH`

**Smoke test honesty improved**
- [tests/smoke_test.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/tests/smoke_test.py)
- It now fails if indicator imports are missing, unless explicitly allowed by env.
- This is intentional: green smoke tests should no longer hide fallback-indicator mode.

## 2026-04-03 - Strategy Design Conclusion Locked In

The user's explanation matches the current evidence well enough to treat it as a design correction, not just a preference:
- `inplay_breakout` should remain a long-biased family:
  - impulse
  - pullback / retest
  - continuation toward the next overhead level
- The current `alt_inplay_breakdown_v1` mirrored short logic looks conceptually weaker than the original long concept.
- So the short side should likely evolve into:
  - dump continuation
  - bearish reclaim failure
  - fast breakdown / panic unwind
rather than a symmetric "in-play but down" clone.

## 2026-04-03 - Breakdown V1 No Longer Mirrors Long InPlay

We acted on that design correction immediately.

- Stopped the stale fresh-data sweeps so we do not keep optimizing around the old short logic.
- Replaced [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) with a standalone short engine.
- It keeps the existing `BREAKDOWN_*` env names, so live and backtest plumbing do not need renaming.

New short logic:
- detect a real 1h support break / dump
- arm a short setup around that broken level
- enter either on:
  - a weak 5m reclaim that fails below support
  - or continuation while price stays compressed under the broken level

Important consequence:
- `inplay_breakout` can now stay a long-family without dragging a conceptually weak mirrored short behind it.
- The next backtests should therefore be treated as a clean test of the new short thesis, not another variation of the old mirror wrapper.

## 2026-04-03 - Review Confirmed And New Run Pack Started

The extra code review was useful, but the good news is that the reported fixes were already present in the tree by the time we checked them:
- `run_portfolio.py` already dispatches the new strategies through proper OHLCV bars and uses `maybe_signal(...)` where needed
- `alt_inplay_breakdown_v2.py` already excludes the current bar from its 5m volume baseline and uses the corrected stop reason text
- `elder_triple_screen_v2.py` already has a real `stoch_rsi` path instead of a dead copy-paste branch

What we changed after verification:
- added a dedicated fresh-data sweep config for the rewritten short sleeve:
  - [breakdown_v1_bear_failed_reclaim_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_bear_failed_reclaim_sweep_v1.json)
- restarted the relevant overnight research around the new logic instead of the old mirrored one

Active overnight package:
- `range_scalp_v1_sweep_v1`
- `breakdown_v1_bear_failed_reclaim_sweep_v1`
- `elder_ts_v2_sweep_v1`
- trusted-overlay `current90` portfolio probe with rewritten `alt_inplay_breakdown_v1`

Operational note:
- the local shell environment is awkward for detached background jobs, so the most important runs were left in live exec sessions to guarantee they continue computing.

## 2026-04-03 - New Current90 Control Point

We now have a real post-rewrite control point for the crypto package on the most relevant recent window:
- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_175621_breakdown_v1_rewrite_current90_probe/summary.csv)

Result:
- `90d`
- `+13.97%`
- `47` trades
- `PF 2.059`
- `winrate 57.4%`
- `max DD 2.48%`

Per-strategy contribution:
- `alt_inplay_breakdown_v1`: `+7.23%`, `22` trades, WR `59.1%`
- `alt_resistance_fade_v1`: `+5.81%`, `9` trades, WR `77.8%`
- `alt_sloped_channel_v1`: `+1.43%`
- `btc_eth_midterm_pullback`: roughly flat
- `inplay_breakout`: `-0.53%`, `1` trade

Interpretation:
- the rewritten short-side logic is the first real structural improvement we have seen in the momentum family on a current window
- this package should be treated as a saved control point, not as final truth for all regimes

## 2026-04-03 - Focused Breakdown Search Started

Instead of continuing the broad annual search, we narrowed around what is actually working now.

New specs:
- [breakdown_v1_current90_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_current90_focus_v1.json)
- [breakdown_v1_recent180_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_recent180_focus_v1.json)

Why:
- the wide `360d` breakdown sweep was too blunt and mostly told us the strategy is not a universal all-regime engine
- the saved `current90` package told us the new short logic *is* live on the actual recent market
- so the next correct move is to optimize locally around that successful region, then test robustness on `180d`

Early signal:
- the very first `current90` focused row already opened with:
  - `PASS`
  - `net 9.09`
  - `PF 3.771`
  - `WR 70.8%`
  - `DD 1.97%`

This is not final validation yet, but it is exactly the kind of signal we wanted before going to sleep: recent-window strength that survives a tighter sweep instead of disappearing immediately.

## 2026-04-03 - Weak Sleeve Triage and New Focused Repairs

Three useful conclusions came out of the next decomposition pass.

1. `inplay_breakout` is not mainly failing because TP is "a little too far". In the honest annual run it had `19` trades, and all `10` losing trades were direct `breakout_retest_long+SL` stop-outs. That points to marginal retests / late reclaim entries, not to a target that is simply too ambitious.

2. `alt_sloped_channel_v1` is modest but alive. In the saved current-window package it contributed `+1.43%` across `9` trades, mostly on `ATOM`, `LINK`, and `ADA`. The right question is not "is it dead?", but "can we make it more explicitly short-only and more selective in bear-chop?"

3. `btc_eth_midterm_pullback` is not missing a short side; the code already has one. The issue is that, right now, it behaves like a low-frequency stabilizer rather than a driver.

New focused specs prepared from those conclusions:
- [arf1_current90_density_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/arf1_current90_density_focus_v1.json)
- [asc1_bear_short_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_bear_short_focus_v1.json)
- [breakout_current90_repair_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakout_current90_repair_focus_v1.json)

These are the next honest tests:
- `ARF1`: can we widen the current bear-chop fade pocket without killing the edge?
- `ASC1`: does short-only sloped-range behavior work better than the current mixed profile?
- `breakout`: can stricter reclaim quality and less-late retests recover the long in-play family without pretending a lower TP magically solves bad entries?

Those focused sweeps are now actually running:
- [autoresearch_20260403_204839_arf1_current90_density_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204839_arf1_current90_density_focus_v1)
- [autoresearch_20260403_204906_asc1_bear_short_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204906_asc1_bear_short_focus_v1)
- [autoresearch_20260403_204906_breakout_current90_repair_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204906_breakout_current90_repair_focus_v1)

## 2026-04-04 - What The Breakout Review Actually Meant

The latest `breakout` review contained one useful hardening idea and two claims that looked scarier than they are in this repo.

- Useful hardening:
  - [strategies/inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py) now keeps a per-symbol engine map (`_impl_by_symbol`) instead of relying only on a single `self.impl`.
  - In practice, both live and portfolio backtest were already creating one wrapper per symbol, so this was not the root cause of the strategy's recent losses.
  - But it removes a real future footgun and makes the wrapper API safer.

- Not a current production bug:
  - The async warning does **not** match the current code path, because both live and backtest `fetch_klines(...)` entry points are synchronous today.
  - The "no caching" warning is also overstated for live, because [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) already caches raw public klines in `_KLINE_RAW_CACHE`.

So the diagnosis stays the same:
- coin selection matters a lot
- timeframe choice matters some
- but the main `breakout` problem still looks like poor retest quality / late entries, not async/caching architecture

## 2026-04-04 - The First Night Package That Actually Looks Like A Core

We now have a clear package-level winner on the fresh `current90` window:

- [portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv)
  - `+19.05%`
  - `55` trades
  - PF `2.691`
  - WR `61.8%`
  - max DD `4.43%`

The strategy split is exactly what we hoped to see from the repaired crypto stack:

- `alt_inplay_breakdown_v1`: `42` trades, `+13.9582`, WR `59.5%`
- `alt_resistance_fade_v1`: `13` trades, `+5.0922`, WR `69.2%`

We also confirmed what is hurting the larger mixed package:

- [portfolio_20260404_003719_overnight_current90_core4_no_breakout_tuned/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core4_no_breakout_tuned/summary.csv) only managed `+10.08%` with PF `1.356`
- the main drag inside that package was `alt_sloped_channel_v1`, which lost `-9.1036` over `34` trades

That means the night package should not be "run everything and hope." The current honest focus is:

- keep `ARF1` density research alive:
  - [autoresearch_20260403_204839_arf1_current90_density_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204839_arf1_current90_density_focus_v1)
  - current clean PASS pocket: `+4.59%`, PF `2.571`, WR `64.3%`, DD `1.69%`
- keep `breakdown_v1` `180d` focus alive:
  - [autoresearch_20260403_200428_breakdown_v1_recent180_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_200428_breakdown_v1_recent180_focus_v1)
  - current strong pocket: `+13.05%`, PF `2.113`, DD `3.91%`
- keep the package probe alive for the two sleeves that are actually paying:
  - `overnight_recent180_core2_fade_breakdown`

And for now, do **not** let `ASC1` or `breakout` dominate the overnight queue until they earn their way back in.

## 2026-04-04 - Morning Verdict

The night finished with a clear answer: the strongest crypto core right now is not "everything together." It is:

- `alt_inplay_breakdown_v1`
- `alt_resistance_fade_v1`

Fresh package results:

- [portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv)
  - `+19.05%`
  - `55` trades
  - PF `2.691`
  - WR `61.8%`
  - DD `4.43%`
- [portfolio_20260404_004652_overnight_recent180_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_004652_overnight_recent180_core2_fade_breakdown/summary.csv)
  - `+27.23%`
  - `148` trades
  - PF `1.748`
  - WR `53.4%`
  - DD `10.32%`

Decomposition:

- `alt_inplay_breakdown_v1` remains the main motor:
  - `current90`: `42` trades, `+13.9582`, WR `59.5%`
  - `recent180`: `107` trades, `+22.4814`, WR `54.2%`
- `alt_resistance_fade_v1` is the quality stabilizer:
  - `current90`: `13` trades, `+5.0922`, WR `69.2%`
  - `recent180`: `41` trades, `+4.7510`, WR `51.2%`

Focused research also improved:

- `ARF1` density search now reaches about `+8.77%`, PF `4.156`, WR `68.8%` on `current90`
- `breakdown_v1` `recent180` focus now reaches about `+22.20%`, PF `1.801`, WR `51.8%`

We also fixed an execution-level weakness in the live bot:

- The scary external diagnosis about `position_manager.py` did **not** match this repo.
- Real live TP/SL here goes through [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) and Bybit `v5/position/trading-stop`, not a standalone stop order.
- But the real risk was still valid in spirit: if exchange TP/SL placement keeps failing, the position could stay open too long.
- So the bot now arms a TP/SL failsafe and force-closes the position if it remains unprotected past a short grace window.

That means the next move is not random exploration. It is:

- treat `fade + new breakdown` as the current crypto candidate core
- keep repairing `breakout` separately
- keep `ASC1` and `midterm` on reduced influence until they earn their way back in

## 2026-04-04 - New Chop Sleeve Added: `AVW1`

To keep the bot adaptive instead of frozen around the current `bear_chop` winner, we added a brand new sleeve:

- [alt_vwap_mean_reversion_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_vwap_mean_reversion_v1.py)

What it is:

- intraday VWAP mean reversion on `15m`
- meant for chop/range environments
- fades statistically stretched moves back toward session VWAP
- uses low ER, RSI extremes, ATR distance from VWAP, and a rejection/reclaim bar

It is already wired into the project properly:

- portfolio backtester:
  - [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- router profiles:
  - [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json)
- allowlist fallback path:
  - [dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py)
- strategy fit scorer:
  - [strategy_scorer.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/strategy_scorer.py)
- research sweep:
  - [vwap_mean_reversion_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/vwap_mean_reversion_v1_sweep_v1.json)

First smoke result:

- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_084344_avw1_smoke_30d/summary.csv)
  - `-6.63%`
  - `122` trades
  - PF `0.620`
  - WR `49.2%`
  - DD `7.81%`

That is not a failure of integration. It is a useful strategic answer:

- the sleeve is alive
- it clearly adds frequency
- but in its raw default form it is far too loose and noisy

So the next honest step for `AVW1` is:

- do not promote it
- tighten its filters
- run the focused sweep
- only then decide if it deserves a place next to `ARF1 + breakdown`

2026-04-04 09:55 UTC

We completed the first real server-side transition from the old mixed crypto stack to the new canary overlay.

- Uploaded the selected files to `/root/by-bot`
- Backed up the remote `.env`
- Applied [live_candidate_core2_breakdown_arf1_20260404.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/live_candidate_core2_breakdown_arf1_20260404.env)
- Restarted the live bot

The live intention is now clear and narrow:

- `alt_inplay_breakdown_v1` is the primary short momentum sleeve
- `alt_resistance_fade_v1` remains the stabilizing range/fade sleeve
- legacy sleeves are intentionally not part of the current canary core

On the local research side:

- `VWAP` is alive but still strategically weak
- `range_scalp` has been re-launched as the main additive frequency candidate
- `breakout` repair has been re-launched as its own explicit track
- `ASC1` bear-short focus has also been re-launched, but its early rows are still mostly weak/negative

Current honest shortlist:

- live candidate core: `ARF1 + new breakdown`
- next additive candidate: `range_scalp`
- repair candidate: `breakout`
- still-unproven secondary sleeve: `ASC1`
- research-only/no-promotion: `VWAP`

2026-04-04 10:45 UTC

I cleaned up the active queue and replaced one stale tool with a current one.

The old generic walk-forward script is not trustworthy for the current crypto stack:

- it imports archived/dead strategies
- it fails before execution
- it is not the right foundation for evaluating the current `ARF1 + breakdown` core

So instead of trying to salvage it blindly, I added a dedicated runner:

- [run_crypto_core_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_crypto_core_walkforward.py)

This new runner:

- uses the real `.venv`
- calls the live [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- runs rolling windows
- writes CSV + Markdown + JSON summaries

It is now running on the current core:

- symbols: `ADA,SUI,LINK,DOT,LTC,BTC,ETH,SOL`
- strategies: `alt_resistance_fade_v1 + alt_inplay_breakdown_v1`
- horizon: `180d`
- windows: `30d`
- step: `15d`

I also explicitly stopped the `VWAP` sweep.

That was the right call:

- the sweep had already shown extreme persistent weakness
- it was consuming process budget
- it had not produced a single credible rescue signal

So the active queue is cleaner now:

- running: `core2 walk-forward`
- running: `breakout repair`
- running: `pump_fade_v2`
- completed earlier and available for reading: `ARF1 density`, `breakdown focus`, `range_scalp`
- stopped/deprioritized: `VWAP`, `ASC1`

2026-04-04 11:30 UTC

Two concrete architecture fixes landed, and one of them is already validated.

First, `breakdown` no longer has to trade blind into the next support.

In [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) the strategy now:

- scans for the next lower support cluster
- stores it at arm time
- moves TP up in front of that level when it would otherwise overshoot it

This is not just theoretical. The smoke run:

- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_112212_breakdown_level_tp_smoke_90d/summary.csv)
  - `+10.20%`
  - `39` trades
  - PF `2.345`
  - WR `59.0%`
  - DD `3.48%`

And the trade reasons confirm the new path is active:

- `bd1_failed_reclaim+level_tp+TP1+TP2`

Second, `elder` now has a cleaner risk model.

In [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) I added:

- `ETS2_RISK_TF`

That means stop/target ATR can come from a slower timeframe than the raw entry trigger. The new sweep:

- [elder_ts_v2_sweep_v2.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_sweep_v2.json)

now fixes risk ATR on `60m` while still comparing `15m` vs `60m` entry timing honestly.

Early result is still bad:

- `r001-r004` all fail badly

So `elder` is still research, not promotion.

Finally, the active queue is narrower and healthier:

- running: `core2 walk-forward` with overlay-bound env
- running: `elder v2`
- stopped: `VWAP`
- stopped: `pump_fade_v2`
- stopped: `breakout repair current sweep`

That is a much cleaner place to leave the machine for the next hour.

- 2026-04-04 12:40 UTC — Found and fixed a real honesty bug in `run_portfolio`: on Bybit rate-limit fallback it could reuse a wide cached slice without trimming back to the requested time window, which made separate walk-forward windows replay the same trade history. Patched candle trimming by `start_ms/end_ms`, recompiled, and restarted the validation run under `core2_walkforward_180d_overlay_v2`. `elder_ts_v2_sweep_v2` finished with zero PASS rows; best raw was still negative (`r136`, net `-3.21`, PF `0.938`), so `elder` remains bench/research only. `breakdown_v2_1h_bear_sweep_v1` was stopped after `122` straight zero-trade rows — not enough signal to justify more process budget. Also refreshed the DeepSeek operator layer: removed stale hard-coded portfolio lore from `bot/deepseek_overlay.py`, added current `core2` candidate context to `bot/deepseek_autoresearch_agent.py`, and added explicit truth fields to the live snapshot in `smart_pump_reversal_bot.py`. Immediate rollout of those AI/runtime files to the server is currently blocked by SSH/SCP timeouts to `167.172.191.107`, so that part is waiting on connectivity, not on code. While the repaired walk-forward runs, launched `flat_arf1_expansion_v2` as the next useful frontier.
- 2026-04-04 13:10 UTC — The server confusion was not a broken key but a stale IP. The live server in the repo surface is `64.226.73.119`, not `167.172.191.107`. Connected to the real host, confirmed `/root/by-bot` and the live `smart_pump_reversal_bot.py` process, uploaded refreshed `smart_pump_reversal_bot.py`, `bot/deepseek_overlay.py`, `bot/deepseek_autoresearch_agent.py`, and `backtest/run_portfolio.py`, then restarted the live bot successfully. That means server AI now has the refreshed truth-oriented prompt/context and server backtests now include the cache-window trimming fix. Research-wise, `range_scalp_v1_sweep_v1` is now the strongest next additive sleeve with multiple PASS pockets (best `r364`: `+15.84%`, PF `2.212`, DD `4.70`), while `flat_arf1_expansion_v2` stays promising but still under its strict PF gate and `support_bounce_v1_bull_sweep_v1` remains weak in the current market. Launched two package probes to test the real next question: does adding `range_scalp` improve the current `core2`? Running tags: `core3_current90_breakdown_arf1_range_probe` and `core3_recent180_breakdown_arf1_range_probe`.
- 2026-04-04 13:35 UTC — The next useful question is no longer “is `range_scalp` good alone?” but “does it actually expand the package when it stops fighting core2 for the same inventory?” A trade-cut made the overlap obvious: the standalone winner in [portfolio_20260404_132235_range_scalp_best_current90_probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_132235_range_scalp_best_current90_probe) trades mostly `DOT/LINK/SUI/ADA/LTC/ATOM`, while the current core already occupies `ADA/LINK/LTC/SUI/DOT` through `breakdown` and `ARF1`. So I did not force a false conclusion from the first core3 package probe. Instead I launched [core3_range_additivity_current90_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/core3_range_additivity_current90_v1.json), which gives `range_scalp` tuned best-pocket params, a semi-disjoint `ARS1_SYMBOL_ALLOWLIST`, and slightly wider `max_positions` to test real additivity rather than pure competition. In parallel I launched [pump_momentum_v1_current90_zoom_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_momentum_v1_current90_zoom_v1.json) as the cleaner answer to “what if we trade continuation without waiting for the reclaim?” Both are now running while `core2` walk-forward and `flat_arf1_expansion_v2` continue.
- 2026-04-05 00:05 UTC — The finished answer was stricter than the hopeful one. `core3_range_additivity_current90_v1` did complete with many PASS rows and a best pocket of `+19.11`, PF `2.919`, DD `3.56`, but decomposing the trades showed the same two current sleeves doing all the work: `alt_inplay_breakdown_v1` and `alt_resistance_fade_v1`. Even at `MAX_POSITIONS=5`, `alt_range_scalp_v1` still produced zero package trades. The direct recent180 probe told the same story: [portfolio_20260404_134600_core3_range_additivity_recent180_bestprobe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_134600_core3_range_additivity_recent180_bestprobe) came in at `+21.78`, PF `1.696`, DD `10.21`, again with no actual `range_scalp` participation and still weaker than the older recent180 `core2` benchmark. So the honest next conclusion is: `range_scalp` is still real as a standalone idea, but not yet proven as the third live sleeve; the best immediate portfolio improvement signal came from giving the current `core2` more room, not from adding a new family. `pump_momentum_v1_current90_zoom_v1` also finished cleanly with zero PASS rows, so the “trade the pump directly without waiting for a reclaim” hypothesis did not revive the long side. Separately, the operator’s `NO_DATA` alert was confirmed as a monitoring weakness, not evidence of two bots or a dead engine: the guard treated a fully empty 2h window as critical even when `smart_pump_reversal_bot.py` was alive. That path is now patched locally and on the real server `64.226.73.119` so empty quiet windows downgrade to `LOW_SAMPLE` instead of paging as a crisis.
- 2026-04-05 02:25 UTC — Wrote down the current best-known baseline explicitly in [core2_research_best_20260405.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core2_research_best_20260405.env) so the strongest current research pocket is no longer spread across chat + logs. It keeps `ARF1` on the live candidate values and upgrades `breakdown` to the strongest finished `current90` pocket from [breakdown_v1_current90_focus_v1 results](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_223512_breakdown_v1_current90_focus_v1/results.csv) row `r483`: `LOOKBACK_H=60`, `MIN_BREAK_ATR=0.25`, `RSI_MAX=60`, `SL_ATR=1.8`, `RR=2.4`, five-coin allowlist (`BTC,ETH,SOL,LINK,ADA`). That gives us one obvious source-of-truth file for “what currently works best” while we keep searching for more sleeves.
- 2026-04-05 02:25 UTC — Instead of grinding the old breakout reclaim family again, I started a new long-side research branch: [impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py). The logic is intentionally different from both old `inplay_breakout` and failed `pump_momentum`: detect a real high-volume 5m impulse through local highs, arm the setup, wait for a shallow retrace back toward the defended breakout zone, then only enter on a bullish reclaim while the level still holds. Wired it into [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py), verified syntax, and ran a first smoke [portfolio_20260405_022015_impulse_volume_breakout_v1_smoke_30d](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_022015_impulse_volume_breakout_v1_smoke_30d): technically healthy but strategically weak so far (`-0.90`, `7` trades, PF `0.417`). That is still useful because it proves the new family is wired and tradable; now it needs honest search, not speculation.
- 2026-04-05 02:25 UTC — Launched two first-wave autoresearch sweeps for the new long family: [impulse_volume_breakout_v1_current90_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_current90_sweep_v1.json) and [impulse_volume_breakout_v1_recent180_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_recent180_sweep_v1.json). Output directories are already created: [autoresearch_20260404_232131_impulse_volume_breakout_v1_current90_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_232131_impulse_volume_breakout_v1_current90_sweep_v1) and [autoresearch_20260404_232131_impulse_volume_breakout_v1_recent180_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_232131_impulse_volume_breakout_v1_recent180_sweep_v1). That is the cleanest current answer to “try something new if the old runs are low-quality”: keep the live core stable, and search a genuinely different long sleeve in parallel.
- 2026-04-05 10:35 UTC — Added two practical live protections around the current `core2`. First, [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now computes a recent close-trade health state for `alt_inplay_breakdown_v1` from `trade_events` and applies a configurable `breakdown` sleeve breaker: soft risk cut when the 30d net slips below a soft threshold, and full block when it breaches a hard threshold after enough closes. Second, the live bot now writes structured trade lifecycle events to [runtime/live_trade_events.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_trade_events.jsonl) so the operator and the DeepSeek overlay can see `order_submitted`, `entry_filled`, `close`, and `failsafe_close_sent` directly instead of reverse-engineering them from pulse counters. I also bound the runtime knobs into [live_candidate_core2_breakdown_arf1_20260404.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/live_candidate_core2_breakdown_arf1_20260404.env), which means the current live candidate now has an explicit path both for safer `breakdown` behavior and for better trade forensics.
## 2026-04-05 | Codex (session 24b — Alpaca intraday revival + dynamic paper rollout)

- Разобрался, почему Alpaca intraday не выглядела живой: дело было не в “сломанных входах”, а в том, что активной оставалась monthly-paper ветка, а intraday контур фактически не был доведён до полноценного операционного запуска.
- Подтвердил, что `v36 monthly` сейчас действительно статична по дизайну:
  - `ALPACA_SEND_ORDERS=0`
  - `ALPACA_CLOSE_STALE_POSITIONS=0`
  - `latest_advisory.json` показывает `dry_run_no_current_cycle`
  - old `GOOGL/TSLA` в advisory были ghost-state из старого monthly paper snapshot, а не реальные текущие live-paper позиции.
- В [equities_alpaca_intraday_bridge.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equities_alpaca_intraday_bridge.py) добавлена важная защита:
  - bridge теперь видит remote Alpaca positions, которых нет в `intraday_state.json`
  - считает их занятыми слотами
  - умеет принудительно закрывать такие stale remote paper positions через `INTRADAY_CLOSE_UNKNOWN_REMOTE_POSITIONS=1`
- Добавлен отдельный dynamic Alpaca candidate:
  - [configs/alpaca_intraday_dynamic_v1.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/alpaca_intraday_dynamic_v1.env)
  - [scripts/run_equities_alpaca_intraday_dynamic_v1.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_alpaca_intraday_dynamic_v1.sh)
  - [scripts/setup_cron_alpaca_intraday_dynamic_v1.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_cron_alpaca_intraday_dynamic_v1.sh)
- Исправлен SPY regime fallback:
  - если live Alpaca daily bars по SPY приходят пустыми в weekend/holiday окне, gate теперь берёт cached SPY closes из `data_cache/equities_1h/SPY_M5.csv`, а не делает слепой pass-through.
- Локальный live-paper запуск новой intraday ветки прошёл честно:
  - dynamic watchlist rebuilt successfully
  - account clean (`equity ≈ cash`, no open positions)
  - no entries because `SPY < SMA50`, so the long-only intraday lane is correctly blocked by bearish regime, not by a hidden bug
- Серверный rollout завершён:
  - files uploaded to `64.226.73.119:/root/by-bot`
  - remote one-shot run succeeded
  - cron installed: `*/5 14-21 Mon-Fri -> run_equities_alpaca_intraday_dynamic_v1.sh --once`
- Итог: Alpaca снова не “старый paper-призрак”, а отдельная живая dynamic lane с honest gates и понятным operational path. Следующий шаг по equities — либо ослабить/модифицировать long-only intraday gate под bear regimes, либо добавить отдельный short/reversion sleeve на equities, если хотим активность даже в risk-off.

## 2026-04-05 | Codex (session 24c — Alpaca dynamic research truth layer)

- Чтобы не принимать решения по Alpaca “на глаз”, добавил честный recent-window research path:
  - [scripts/run_forex_backtest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_backtest.py) теперь умеет `--start-date/--end-date`
  - [scripts/run_forex_combo_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_combo_walkforward.py) тоже режет окна по датам
  - [scripts/run_equities_strategy_scan.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_strategy_scan.sh) и [scripts/run_equities_walkforward_gate.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_walkforward_gate.sh) получили env-управление recent-window диапазоном и безопасные `RUN_SUFFIX`, чтобы параллельные dry-run не били друг другу out-dir.
- Для этого добавил новый orchestrator:
  - [scripts/run_equities_intraday_dynamic_research.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_research.sh)
  - он сам:
    - rebuild-ит dynamic watchlist,
    - вычисляет recent окно (`EQ_RECENT_DAYS`),
    - запускает scan,
    - потом сразу walkforward gate.
- Первые честные front’ы показали неприятную, но полезную правду:
  - [equities_scan_20260405_085619_alpaca_dyn90/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_scan_20260405_085619_alpaca_dyn90/summary.csv)
  - [equities_scan_20260405_085619_alpaca_dyn180/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_scan_20260405_085619_alpaca_dyn180/summary.csv)
  - [equities_wf_gate_20260405_085646_alpaca_dyn90/raw_walkforward.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_wf_gate_20260405_085646_alpaca_dyn90/raw_walkforward.csv)
  - dynamic watchlist выглядит разумно, но current gate слишком жёсткий для `90d`: `No candidates from scan passed prefilter`.
- Поэтому сразу открыл четыре новые dry-run ветки с более реалистичным recent-window gate:
  - `alpaca_dyn90_relaxed`
  - `alpaca_dyn90_wide_relaxed`
  - `alpaca_dyn90_breakout_bias`
  - `alpaca_dyn90_reversion_bias`
- Логика простая: сначала честно доказать, что dynamic equities вообще дают устойчивые recent-window кандидаты под более реалистичный trade-count, и только потом думать о promotion или о включении ордеров.

## 2026-04-05 | Codex (session 24d — Alpaca annual truth without watchlist lookahead)

- Нашёл ещё одну важную дыру в честности Alpaca research: [build_equities_intraday_watchlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_equities_intraday_watchlist.py) до этого ранжировал symbols по самым свежим cached M5 барам, даже если сам backtest запускался на историческом окне. Это означало скрытый lookahead на уровне выбора watchlist.
- Исправил это:
  - builder теперь принимает `--start-date/--end-date`
  - перед расчётом metrics режет candles по историческому окну
  - [run_equities_intraday_dynamic_research.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_research.sh) теперь передаёт `EQ_END_DATE` в watchlist build
- Это ещё не “идеальный daily-rolling annual sim”, но уже убирает самый грубый вид lookahead и делает recent-window dynamic research честнее.
- Чтобы получить годовую правду без этой дырки, добавил:
  - [run_equities_intraday_dynamic_annual_segments.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_annual_segments.sh)
- Он запускает 4 non-overlapping сегмента по `90d`, каждый раз:
  - rebuild-ит dynamic watchlist на историческую дату конца сегмента,
  - запускает scan,
  - затем walkforward gate,
  - и пишет manifest по всем сегментам.
- Уже запущены 2 honest annual dry-run фронта:
  - `alpaca_annual_seg_relaxed`
  - `alpaca_annual_seg_wide`
- Честный промежуточный вывод остаётся таким:
  - на latest `90d` проблема уже не в старом gate и не в старых Alpaca-висяках;
  - проблема в том, что текущие equity session combos пока не дают положительный recent-window edge.

## 2026-04-05 | Codex (session 24e — annual Alpaca verdict + crypto Elder logic repair)

- Honest annual Alpaca segmented dry-runs завершились:
  - [alpaca_annual_seg_relaxed](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_intraday_dynamic_annual_20260405_091048_alpaca_annual_seg_relaxed)
  - [alpaca_annual_seg_wide](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_intraday_dynamic_annual_20260405_091048_alpaca_annual_seg_wide)
- Жёсткая, но полезная правда:
  - все `4/4` сегмента по `90d` в обеих annual-ветках закончились без validated candidates
  - соответствующие `raw_walkforward.csv` пустые
  - значит **честного долгого Alpaca return % к депозиту сейчас нет**, потому что нет ни одного кандидата, который прошёл наш годовой validation path
- При этом raw scan внутри сегментов не совсем мёртвый:
  - в latest quarter есть положительные low-trade pockets вроде `AAPL trend_pullback_rebound_v1`, `TSLA trend_pullback_rebound_v1`
  - в oldest segment живее смотрится `AVGO breakout_continuation_session_v1`
  - но это ещё не годится для promotion, потому что trade count и stability пока слишком слабые
- На сервере Alpaca теперь чище:
  - old monthly trading cron снят
  - legacy duplicate intraday cron снят
  - осталась одна новая dynamic dry-run lane + TG reports
- После этого фокус снова переведён в crypto:
  - [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) получил реальную logic repair в `Screen 3`
  - вместо raw breakout теперь entry идёт через entry-TF retest/reclaim с `touch ATR buffer` и `minimum body fraction`
  - под это запущен новый rescue-run:
    - [elder_ts_v2_retest_reclaim_v4.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_retest_reclaim_v4.json)
- Разбор сегодняшнего live breakdown-шорта оказался полезным не как “ой, стоп словили”, а как логический сигнал:
  - это был скорее stale breakdown / возврат в диапазон, а не missed long
  - под это я усилил [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py)
  - добавлены:
    - `BREAKDOWN_FRESH_BREAK_BARS_5M`
    - `BREAKDOWN_FLAT_FILTER_BARS_5M`
    - `BREAKDOWN_FLAT_FILTER_MAX_RANGE_ATR`
    - `BREAKDOWN_FLAT_FILTER_LEVEL_BAND_ATR`
  - смысл простой: не шортить слишком поздно и не шортить, когда пробой уже умер и превратился в пилу вокруг уровня
- Быстрый sanity-probe на узком core2-баскете после этого остался положительным:
  - [core2_breakdown_fresh_flat_probe_90d](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_125802_core2_breakdown_fresh_flat_probe_90d/summary.csv)
  - `+4.44%`, PF `1.369`, DD `3.95`
  - это не новый финальный baseline, а просто первый чек, что guardrail-фикс не убил стратегию сразу
- По `core3 + impulse` картина стала наконец-то честно трёхслойной, а не только “есть красивый solo-run”:
  - [recent180 package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_134236_core3_impulse_best_recent180_probe/summary.csv): `+28.65%`, PF `1.356`, DD `9.32`
  - там [impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py) реально добавила edge (`102` trades, about `+7.80%`)
  - [current90 package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_135423_core3_impulse_best_current90_probe/summary.csv): `+16.30%`, PF `1.462`, DD `3.74`
  - но на `90d` `impulse` сама дала почти flat contribution (about `-0.09%`), то есть promotion ещё рано
  - [annual package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_140930_core3_impulse_best_annual_probe/summary.csv): только `+2.26%`, PF `1.029`, DD `16.35`
  - это хороший разворот в research, но пока не live-ready 3rd sleeve
- Закрыл ещё один старый пробел в tooling: в [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) теперь есть первый `chart inbox` путь для Telegram-графиков:
  - входящие фото сохраняются в `runtime/chart_inbox`
  - сохраняется `latest.json` с метаданными
  - появился `/chart_last`
  - это ещё не полноценное vision/CV, но теперь бот хотя бы умеет принять живой скрин графика и держать его как structured input для следующего визуального слоя

## 2026-04-08 | Codex (session 27a — historical control-plane replay now uses historical symbol scans)

- Finished the next real control-plane step in [run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py): replay can now run in `historical_scan` mode instead of only replaying frozen overlay symbols.
- The historical router now reconstructs candidate baskets from cached `60m` bars or aggregated `5m` bars, scores them against registry thresholds (`turnover`, `ATR%`, `listing age`, excludes, `top_n`), and falls back to frozen overlay / anchors only when that is genuinely necessary.
- Also fixed an important truth bug: registry entries with explicit `fixed_symbols: []` are now treated as intentional `OFF` profiles instead of silently falling through into fallback symbols.
- Honest replay outputs after this upgrade:
  - smoke neutral replay: [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_091552_smoke_cp_hist_20260408/summary.json) → `7` checkpoints, allocator `ok=7`, average global risk `0.8429`
  - annual constrained replay: [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_091552_annual_cp_hist_20260408/summary.json) → allocator `degraded=25`, mainly `flat=22` and `breakdown=4`, average global risk `0.672`
  - annual neutral-health replay: [summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/control_plane_replay_20260408_091552_annual_cp_hist_neutral_20260408/summary.json) → allocator `ok=25`, enabled sleeves `breakout=21`, `sloped=25`, `midterm=25`, `flat=22`, `breakdown=4`, average global risk `0.896`
- This is a useful truth milestone: the historical router itself is no longer the obvious bottleneck; the next structural question is how strict live `strategy_health` should be versus what annual replay says the system *could* have run.

## 2026-04-08 | Codex (session 27b — deterministic geometry engine landed)

- Added [bot/chart_geometry.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/chart_geometry.py) as the first reusable pre-vision geometry layer.
- It currently provides:
  - pivot highs/lows
  - clustered horizontal levels
  - regression channel with `r2`, width, and position-in-channel
  - short-vs-long range compression state
- Added [run_geometry_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_geometry_snapshot.py) so we can inspect symbol geometry directly from cache without any image model or external API key.
- Verified on cached data:
  - `BTCUSDT 60m`: channel `r2=0.364`, width `3.42%`, compression ratio `0.392`, nearest resistance cluster around `67022.97`
  - `ETHUSDT 60m`: channel `r2=0.485`, width `5.04%`, compression ratio `0.424`, nearest resistance clusters around `2056.62` and `2060.56`
- This gives us a real foundation for level-aware routing and future `approach / reject / accept` sleeves before we spend latency or tokens on vision.

## 2026-04-08 | Codex (session 27c — live control-plane watchdog activated on the server)

- Verified the production server state directly instead of trusting stale assumptions:
  - live host `64.226.73.119`
  - `bybot.service` is active
  - server control-plane files are fresh on April 8:
    - [configs/regime_orchestrator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/regime_orchestrator_latest.env)
    - [configs/dynamic_allowlist_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/dynamic_allowlist_latest.env)
    - [configs/portfolio_allocator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_latest.env)
- Found one real live gap: `ROUTER_HEALTH_ENABLE` and `PORTFOLIO_ALLOCATOR_ENABLE` were not set in the server `.env`, so router/allocator guardrails were not actually enabled even though the files and cron jobs existed.
- Closed that gap with two new scripts:
  - [scripts/apply_live_control_plane_env_patch.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/apply_live_control_plane_env_patch.py)
  - [scripts/control_plane_watchdog.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/control_plane_watchdog.py)
- Also upgraded [scripts/setup_server_crons.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_server_crons.sh):
  - router now rebuilds every `6h` instead of once per day
  - a new watchdog runs every `15m`
  - watchdog can rebuild `regime -> router -> allocator` in dependency order if freshness falls behind
- After deploy on the server:
  - `.env` now explicitly has:
    - `REGIME_OVERLAY_ENABLE=1`
    - `ROUTER_HEALTH_ENABLE=1`
    - `PORTFOLIO_ALLOCATOR_ENABLE=1`
    - `REGIME_OVERLAY_MAX_AGE_SEC=7200`
    - `ROUTER_OVERLAY_MAX_AGE_SEC=28800`
    - `ROUTER_STATE_MAX_AGE_SEC=28800`
    - `PORTFOLIO_ALLOCATOR_MAX_AGE_SEC=10800`
  - crontab now contains:
    - hourly regime build
    - `6h` router rebuild
    - hourly allocator build
    - `15m` control-plane watchdog repair
  - watchdog status after repair is `ok` in `/root/by-bot/runtime/control_plane/control_plane_watchdog_state.json`
- Practical meaning:
  - control-plane now genuinely lives on the server, not only in docs or local tooling
  - router/allocator freshness is enforced in live
  - the system can self-heal stale control-plane artifacts instead of waiting silently for manual intervention | done

## 2026-04-08 | Codex (session 27d — dynamic annual harness now exists and passed first stitched smoke)

- Added a real end-to-end dynamic system harness in [run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py).
- This is different from the earlier control-plane replay:
  - replay validated the *brain* (`regime -> router -> allocator`)
  - the new harness validates the *whole dynamic package* over sequential windows by actually running [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) on each window with:
    - historical regime state
    - historical symbol baskets
    - historical health snapshot
    - allocator-driven enabled sleeves
    - allocator/orchestrator risk multipliers
- Also upgraded [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) so allocator backtests can read per-sleeve risk envs (`BREAKDOWN_RISK_MULT`, `FLAT_RISK_MULT`, `SLOPED_RISK_MULT`, `MIDTERM_RISK_MULT`, etc.) instead of only the old simplified breakout/midterm flat-vs-trend risk shim.
- Important honesty hardening:
  - the first smoke run exposed a structural handoff bug (`router -> allocator -> harness` lost symbol baskets), which is now fixed
  - the second smoke run exposed a reproducibility problem (`run_portfolio` could still drift into live fetches), so the harness now forces `BACKTEST_CACHE_ONLY=1`
  - a final smoke pass then completed fully offline and produced the first real stitched result for the new system
- First stitched dynamic result:
  - [dynamic_system_smoke90_v4 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133617_dynamic_system_smoke90_v4/summary.json)
  - `90d`
  - `+11.54%`
  - PF `2.2167`
  - winrate `58.89%`
  - max DD `1.8463%`
  - negative months `0`
- Window-level truth:
  - [dynamic_windows.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133617_dynamic_system_smoke90_v4/dynamic_windows.csv)
  - all three windows classified into applied `bear_chop`
  - window 1: `breakdown + flat + sloped`, `+9.40`, PF `2.515`
  - window 2: `flat + sloped`, `-0.15`, PF `0.939`
  - window 3: `breakdown + flat`, `+2.29`, PF `3.712`
- Monthly stitched profile:
  - [stitched_monthly_returns.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133617_dynamic_system_smoke90_v4/stitched_monthly_returns.csv)
  - `2026-01 +5.21%`
  - `2026-02 +3.72%`
  - `2026-03 +1.13%`
  - `2026-04 +1.07%`
- Practical meaning:
  - the new foundation is now strong enough to generate a *real* dynamic stitched PnL result, not only static sleeve probes
  - next correct step is full `360d` stitched validation, then compare:
    - dynamic system vs old static package
    - return
    - DD
    - bad months
    - sleeve contribution | done

## Codex Session 27e - 2026-04-08

Summary:
- The first full `360d` stitched dynamic system run is now complete, so we have the first honest annual result for the rebuilt stack instead of only smoke runs and control-plane replays.
- I also launched the next validation set immediately:
  - `core2_honest_wf_360d_20260408`
  - `ivb1_ema_wf_360d_20260408`
  - `ivb1_off_wf_360d_20260408`
  - `pump_fade_v4r_bear_window`

Key findings:
- Full stitched annual result:
  - [dynamic_system_annual_v1 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133825_dynamic_system_annual_v1/summary.json)
  - `+2.97%`
  - PF `1.0636`
  - WR `46.89%`
  - DD `8.6842%`
  - `6` negative months
- Window truth:
  - [dynamic_windows.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133825_dynamic_system_annual_v1/dynamic_windows.csv)
  - the system stayed mostly in applied `bull_chop`
  - enabled sleeves were dominated by `breakout + sloped + flat`
  - weak summer windows (`2025-04 .. 2025-08`) are still the main drag
- Early IVB1 regime-gating signal:
  - `ema` is not an instant win; first windows are still weak/negative
  - `off` is also weak in the same early window, with even more trades and larger loss
- Practical meaning:
  - the rebuilt base is now honest enough to show that the system survives the year, but it does **not** yet produce promotion-quality annual numbers
  - next decisions must come from:
    - honest `core2` walk-forward
    - honest `IVB1 off vs ema` walk-forward
    - fresh `pump_fade_v4r` bear-window research
- Fresh follow-up truth:
  - `pump_fade_v4r_bear_window` finished `81/81` and every row failed with the same weak outcome (`net=-0.27`, `PF=0.000`), so this sleeve is not a hidden bear-market savior right now
  - `core2_honest_wf_360d_20260408` had to be restarted as cache-only because the first version drifted into a stuck network-backed run instead of clean offline validation

## Codex Session 27f - 2026-04-08

Summary:
- Closed a real live bug instead of debating it abstractly: `IVB1` was indeed not wired into the live bot, and the server foundation deploy initially broke because the new bot import landed before the actual strategy file was copied to `/root/by-bot/strategies`.
- Repaired the live path, patched the watchdog/env gap, and refreshed the honest research verdicts.

Key findings:
- Live wiring:
  - [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now imports and schedules `impulse_volume_breakout_v1`
  - [configs/portfolio_allocator_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy.json) now contains an `impulse` sleeve
  - minimum notional is now env-driven via `MIN_NOTIONAL_USD`, default `5.0`
- Foundation repair:
  - [scripts/bot_health_watchdog.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/bot_health_watchdog.sh) and [scripts/check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh) now source live `.env`, so `WATCHDOG_AUTO_RESTART=1` actually works under cron
  - [scripts/deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh) now uploads [strategies/impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py) and is resilient if the first `systemd` start fails
  - server status is green again: `systemd RUNNING`, heartbeat fresh, control-plane files fresh, watchdog cron installed, `WATCHDOG_AUTO_RESTART=1`, `MIN_NOTIONAL_USD=5.0`
- Honest strategy truth at this point:
  - `pump_fade_v4r_bear_window`: still dead, `81/81` fail
  - `ivb1_ema_wf_360d_20260408`: weak, cumulative `net=-0.93`, positive windows `7/23`
  - `ivb1_off_wf_360d_20260408`: materially better, cumulative `net=+13.78`, positive windows `18/23`
  - `core2_honest_wf_360d_cache_20260408`: mixed but alive, cumulative `net=+12.79`, positive windows `11/23`
- Practical meaning:
  - the useful result is not “IVB1 is ready”, but “the current EMA regime gate hurts IVB1 more than it helps”
  - live `IVB1` is now wired and allocator-aware, but still intentionally not enabled in production because promotion truth is not there yet

## Codex Session 27g - 2026-04-08

Summary:
- Confirmed the user's suspicion that the old stitched annual truth was still contaminated by a stale strategy mix: it was running `inplay_breakout` even after that sleeve had effectively been retired from the real direction of the project.
- Closed the missing router leg for `IVB1`, refreshed live router/allocator state on the server, and restarted honest stitched compares with the repaired profile registry.

Key findings:
- The stale Telegram `BOT UNRESPONSIVE` alert at `15:44/15:46 UTC` was not a mysterious hang in a healthy bot; it happened during the broken deploy / restart window. After recovery, watchdog returned to a clean cadence with repeated `OK` lines and fresh heartbeat age.
- The previous stitched annual run [dynamic_system_annual_v1/dynamic_windows.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_133825_dynamic_system_annual_v1/dynamic_windows.csv) really did use:
  - `inplay_breakout`
  - `alt_sloped_channel_v1`
  - `alt_resistance_fade_v1`
  instead of the intended modern `core2 + impulse` direction.
- The policy itself was already partly repaired (`breakout` base risk now `0.0` in every regime), but the router registry still had **no `IVB1` profile at all**, so `impulse` could not receive symbols in dynamic routing.
- Added new `IVB1_SYMBOL_ALLOWLIST` profiles to [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json):
  - `ivb1_bull_core`
  - `ivb1_chop_reduced`
  - `ivb1_bear_off`
- After pushing that registry to the server and rebuilding router+allocator, live control-plane now shows:
  - `impulse: enabled=1`
  - `risk=1.00`
  - `count=8`
  - health `OK`
  in `bull_trend`
- Fresh stitched compare reruns are now active:
  - `dynamic_core3_impulse_candidate_recent180_v2`
  - `dynamic_core3_impulse_candidate_annual_v2`
- First repaired window is directionally sane:
  - `recent180_v2 w01`: sleeves `flat, sloped, impulse`, PF `1.188`, net `+0.87`
  - `annual_v2 w01`: sleeves `sloped, impulse`, PF `0.852`, net `-0.71`

Practical meaning:
- The earlier `+2.97% annual` stitched result should no longer be treated as the final truth for the rebuilt system.
- It was honest about the old stack it actually ran, but it was **not** yet the honest result for the intended modern stack.
- After the router/profile repair, stitched research must be rerun before making any judgement like “systems made everything worse.”

## Codex Session 28 - 2026-04-08

Summary:
- Tightened live observability around `IVB1`/impulse so the bot stops looking artificially “dead” when the control-plane has actually enabled the sleeve.
- Opened the next focused annual repair frontier around `alt_range_scalp_v1`, because the repaired dynamic stack is now directionally alive but still suffers from too many red months.

Key findings:
- A real visibility gap remained after the live IVB1 wiring:
  - [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py) still did **not** emit any `ivb1_*` counters in the compact runtime snapshot, even though the live bot was incrementing:
    - `ivb1_sched`
    - `ivb1_try`
    - `ivb1_entry`
    - `ivb1_skip_*`
- [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) also lacked an explicit `impulse-universe` line in status/universe notifications, so Telegram could still make the stack look narrower than it really was.
- After the dynamic routing repair, the stitched annual result for the intended stack is materially better than the stale-stack benchmark:
  - [dynamic_core3_impulse_candidate_annual_v2 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_161044_dynamic_core3_impulse_candidate_annual_v2/summary.json)
  - `+13.17%`
  - PF `1.2182`
  - DD `5.2386`
  - but still `6` negative months
- This means the immediate annual problem is no longer “system dead” but “red-month control still too weak.”

Changes made:
- Added IVB1 counters to the compact runtime snapshot in [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py):
  - `ivb1_sched`
  - `ivb1_try`
  - `ivb1_entry`
  - `ivb1_skip_max_open`
  - `ivb1_skip_portfolio`
  - `ivb1_skip_symbol_lock`
- Extended [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) so:
  - strategy runtime stats include `ivb1=...`
  - `status_full` shows the `impulse` router profile
  - `status_full` shows `impulse-universe`
  - universe refresh notifications now emit `🧩 impulse-universe: ...`
- Added new focused frontier spec [range_scalp_v1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_annual_repair_v1.json):
  - based on the already strong recent-180 package
  - now explicitly optimized for fewer negative months / shorter negative streaks
  - includes stricter `ARS1` annual repair grid:
    - `MAX_POSITIONS`
    - symbol basket
    - `ARS1_TIME_STOP_BARS_5M`
    - `ARS1_ALLOW_LONGS`
    - `ARS1_RSI_LONG_MAX`
    - `ARS1_RSI_SHORT_MIN`
    - `ARS1_SL_ATR_MULT`
- Updated [run_crypto_foundation_frontier.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_crypto_foundation_frontier.sh) so future batch launches include the new annual range repair too.

Practical meaning:
- The next bottleneck is clearer than before:
  - not “connect another sleeve at random”
  - but “reduce red months without lying about annual truth”
- `range_scalp` is currently the best candidate for that repair pass because it already proved strong additivity on recent windows without needing a brand-new strategy family.

## Codex Session 29 - 2026-04-08

Summary:
- Repaired two operator-layer problems that were making the bot harder to trust in live Telegram use:
  - operator answers were being hard-trimmed to one short message even though Telegram splitting already existed
  - operator had effectively no persistent memory across restarts / long pauses beyond the immediate snapshot

Key findings:
- `tg_send()` was already able to split long Telegram messages safely, so the real bug was not Telegram itself.
- The truncation came from [_ai_operator_emit()](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py), which was always passing its final answer through `_ai_operator_trim(...)` before sending.
- Operator context also had no rolling persistent journal. [build_operator_snapshot()](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py) could report live state, geometry, and health, but not “what the operator itself recently concluded.”

Changes made:
- [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py):
  - `_ai_operator_emit()` now stores a trimmed summary for memory, but sends the **full** answer to Telegram so `tg_send()` can split it into multiple messages as designed
  - `/ai_reset` now clears both overlay history and the new operator memory file
- [bot/operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py):
  - added persistent operator memory at `runtime/ai_operator/memory.jsonl`
  - added `append_operator_memory(...)`
  - added snapshot exposure of recent memory entries
  - added memory summary to `format_operator_snapshot_text(...)`

Practical meaning:
- The operator is now less likely to keep repeating stale partial audits because it can see a short persistent trail of its own recent verdicts.
- Telegram should stop silently cutting operator reasoning down to a misleading one-message fragment.

## Codex Session 30 - 2026-04-08

Summary:
- Found and repaired a deeper distortion in the stitched annual truth itself: the historical regime layer was over-sticky and was biasing too many monthly windows toward `bull_chop`, which made the repaired dynamic annual stack look flatter and less context-aware than it really was.

Key findings:
- The mixed-sign part of the regime classifier in [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py) was too broad:
  - `bull_ema or above_55` was enough to classify many ambiguous windows as `bull_chop`
  - this hid bear-chop / bear-trend pockets inside the stitched annual replay
- Historical stitched validation was also inheriting live-style hysteresis too literally:
  - monthly windows were effectively behaving as if they needed multiple disagreeing checkpoints before a regime could switch
  - this was especially misleading when `historical_hold_cycles=1` should have meant “switch immediately on the next stitched window”

Changes made:
- [scripts/build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py):
  - added mixed-sign bias scoring using:
    - `ORCH_MIXED_SIGN_PRICE_WEIGHT`
    - `ORCH_MIXED_SIGN_EMA_WEIGHT`
    - `ORCH_MIXED_SIGN_EDGE_PCT`
  - now emits:
    - `ema_gap_pct`
    - `close_vs_ema55_pct`
    - `mixed_bias`
    - `bull_strength`
    - `bear_strength`
    - `bias_edge_pct`
  - bumped regime state version to `2`
- [scripts/run_control_plane_replay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_control_plane_replay.py):
  - fixed `_advance_hysteresis(...)` so `min_hold_cycles=1` truly allows an immediate regime switch in historical replay
- [scripts/run_dynamic_crypto_annual.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py):
  - added explicit `--historical-hold-cycles`
  - writes `historical_hold_cycles` into stitched annual outputs

Observed effect:
- Raw regime distribution across the annual stitched checkpoints is no longer almost all `bull_chop`; it now includes real `bear_chop`, `bear_trend`, and `bull_trend` windows.
- A new corrected stitched run is now active:
  - [dynamic_core3_impulse_candidate_annual_v3_hold1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_172157_dynamic_core3_impulse_candidate_annual_v3_hold1)
- The first corrected window already diverged materially from the stale truth:
  - `w01`: `regime=bull_chop`, sleeves `sloped,impulse`, `net=-3.03`, PF `0.148`

Practical meaning:
- We now have a concrete reason to rerun stitched annual before judging whether the new protective layers “help” or “suffocate” the bot.
- If annual v3 improves regime diversity and red-month behaviour, that confirms the previous annual harness was understating the repaired stack.
- If annual v3 still looks weak after this fix, the next bottleneck is sleeve logic / promotion truth, not router stickiness.

Final result:
- [dynamic_core3_impulse_candidate_annual_v3_hold1 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_172157_dynamic_core3_impulse_candidate_annual_v3_hold1/summary.json)
  - `+7.27%`
  - PF `1.1074`
  - `5` negative months
  - `historical_hold_cycles=1`
- Compared with [dynamic_core3_impulse_candidate_annual_v2 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_161044_dynamic_core3_impulse_candidate_annual_v2/summary.json):
  - returns fell from `+13.17%` to `+7.27%`
  - negative months improved from `6` to `5`

What that means:
- The previous annual truth was indeed partially inflated by stitched regime stickiness.
- The repair did not kill the system; it made the annual stack more honest.
- But it also proved that router truth alone will not get us back to the old “big numbers.”
- The next repair focus should stay on:
  - reducing red months
  - improving sleeve quality inside real bear/bull windows
  - especially `flat`/`range` frequency-quality tradeoffs and `impulse` annual consistency

Overnight research state:
- Existing annual-repair fronts still running:
  - [impulse_volume_breakout_v1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_annual_repair_v1.json)
  - [range_scalp_v1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_annual_repair_v1.json)
  - [flat_horizontal_core_v3_frontier.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_horizontal_core_v3_frontier.json)
- Added a new sloped annual-repair frontier:
  - [asc1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_annual_repair_v1.json)
- Why this was added:
  - `alt_sloped_channel_v1` appears repeatedly inside corrected stitched annual windows
  - it is still research-only and often treated as a contextual near-miss
  - we need an honest yearly answer on whether it reduces portfolio weakness or only adds more noisy months

Morning verdict:
- `impulse` is no longer only a “promising recent180 story”:
  - [impulse annual repair results.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260408_130107_impulse_volume_breakout_v1_annual_repair_v1/results.csv)
  - strong annual PASS rows already exist
  - current best-score row:
    - `+12.85%`
    - PF `1.978`
    - WR `0.642`
    - DD `2.2835`
    - `3` negative months
- `flat` also produced real yearly PASS rows instead of only “almost there” scans:
  - [flat frontier results.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260408_172507_flat_horizontal_core_v3_frontier/results.csv)
  - current best-score row:
    - `+7.08%`
    - PF `5.523`
    - WR `0.818`
    - DD `0.8048`
    - `0` negative months
    - best basket: `LINKUSDT,LTCUSDT,SUIUSDT`
- `sloped` did not convert into an annual candidate:
  - [asc1 annual repair results.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260408_174815_asc1_annual_repair_v1/results.csv)
  - no PASS rows
  - best rows still fail on annual red-month / streak criteria
- `Elder` remains structurally broken rather than under-tuned:
  - `elder_ts_v2_retest_reclaim_v4` = effectively `0` trades across the whole sweep
  - `elder_ts_v2_recent180_focus_v3` = many trades but PF only around `0.5`

Immediate action taken:
- Created a new repaired candidate overlay:
  - [core3_flat_impulse_candidate_20260409.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core3_flat_impulse_candidate_20260409.env)
- Created a no-sloped comparison policy:
  - [portfolio_allocator_policy_no_sloped_20260409.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy_no_sloped_20260409.json)
- Launched two new stitched annual compares:
  - `dynamic_core3_flat_impulse_annual_v1`
  - `dynamic_core3_flat_impulse_nosloped_annual_v1`

- 2026-04-09 06:55 UTC — validated the live/server truth after laptop reopen, wired Elder into the live bot, and opened a focused Elder rescue frontier. Server truth today is fresh and alive (`systemd` running, heartbeat fresh, control-plane fresh) but current regime is `bull_chop`, not the stale local `bear_chop` guess. That matters because `IVB1` is not dead anymore; it is already wired and trying live checks (`ivb1_sched/try` rising), just not entering yet. I confirmed a real gap in code: `elder_triple_screen_v2` had an allocator sleeve but was still absent from the live entry loop. Fixed that in [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py): added live import, env/risk plumbing, lazy per-symbol engine, scheduler hook, universe/status reporting, and entry execution path. Also upgraded [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py) so `IVB1` now records grouped no-signal reasons instead of only `try/entry`, and added parallel grouped no-signal diagnostics for `Elder`. Softened [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) defaults to crypto-realistic values (`OSC 42/58`, wider retest window, smaller TP, tighter cooldown, higher daily cap) without pretending that this alone proves the sleeve. Opened [elder_ts_v2_live_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_live_repair_v1.json) and launched it so the next verdict is based on fresh evidence, not on chat theory. In parallel, the new stitched annual compare remains the current strongest truth: [dynamic_core3_flat_impulse_nosloped_annual_v1 summary.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260409_033346_dynamic_core3_flat_impulse_nosloped_annual_v1/summary.json) sits at `+21.31%`, PF `1.6004`, DD `4.80%`, `3` red months, and a new rolling `360d` walk-forward run (`core3_flat_impulse_nosloped_wf360_v1`) is now active to test whether that stitched annual strength survives rolling windows. 

- 2026-04-09 07:36 UTC — added the missing full-stack rolling validator so we can test strategies on a full year without falling back to static symbols or stitched-only optimism. New file: [run_dynamic_crypto_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py). It replays historical `regime -> router -> allocator -> health timeline` per window, builds the same sleeve/env package the live stack would see, and then runs [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) on those live-style symbols and sleeves. This closes the biggest remaining truth gap between stitched annual and rolling validation. Immediately launched `dynamic_core3_flat_impulse_nosloped_wf360_v1` on the current best no-sloped core. First window already came back honest but not promotional: `bear_chop`, sleeve `flat` only, `+1.58`, PF `inf`, DD `0.02`, `3` trades, `pass=False` because the pass gate still requires enough trades and a real sample size. That is exactly the kind of answer we need now: the foundation is not auto-failing good windows anymore, but it is also not handing out fake PASS labels on tiny samples. 

- 2026-04-09 08:00 UTC — shifted the next debugging step from “more ideas” to concrete live entry telemetry. I inspected the actual server status after the latest deploy and confirmed the current live shape: regime `bull_chop`, `flat=True`, `ivb1=True`, `elder=False`, heartbeat fresh, no open trades. Before this patch, `flat` exposed only `try/entry` counts and `IVB1` collapsed most no-signal outcomes into `other`, which made the bot look more mysterious than it really was. I upgraded [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) to emit explicit no-signal reasons (`regime`, `same bar`, `range`, `touch`, `reject`, `body`, `distance`, `RSI`, `EMA`, `risk`), added a `last_no_signal_reason()` accessor in [flat_resistance_fade_live.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/flat_resistance_fade_live.py), expanded [bot/diagnostics.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/diagnostics.py) with grouped `flat_*` counters plus a more specific `IVB1` breakout bucket, and wired those counters into [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py). Server-side live params also explain part of the current silence: `flat` is still running on `ARF1_SIGNAL_TF=60m`, `ARF1_MIN_RSI=58`, `ARF1_REJECT_BELOW_RES_ATR=0.12`, while `IVB1` is largely on defaults. This means many `flat_try` events were probably not real setups at all but repeated checks inside the same hourly bar, and many `IVB1` misses were hidden inside one coarse `other` bucket. The new counters are now deployed and should let the next Telegram/log pulses show actual blockers instead of only “try went up, entry stayed zero.” 

- 2026-04-09 08:10 UTC — traced the annual weakness down to one concrete quadrant instead of blaming the whole stack. The `+21.31% / 3 red months` stitched annual is real progress versus the earlier repaired stack, but the weak point is now explicit: messy `bear_chop`. In [dynamic_core3_flat_impulse_nosloped_annual_v1 window 2025-05-13→2025-06-12](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260409_063414_dynamic_core3_flat_impulse_nosloped_annual_v1_w02_20250612/summary.csv), `breakdown + flat` lost `-2.77` with PF `0.678`. Breaking the trades down shows the real culprit: `alt_inplay_breakdown_v1` lost `-4.37` across `33` trades while `alt_resistance_fade_v1` actually added `+1.60`; the worst damage came from repeated short whipsaws on `ADA`, `ETH`, `SOL`, and `LINK`. This is the useful part of the analysis: we now know the current core is not “generally bad”, it is specifically over-firing the breakdown sleeve in noisy bear-chop. I also verified that our first sloped annual repair was not a complete verdict on sloped structure in general because [asc1_annual_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_annual_repair_v1.json) was explicitly `short-only` (`ASC1_ALLOW_LONGS=0`, `ASC1_ALLOW_SHORTS=1`). That means the right next step is not “give up on sloped levels”, but “test them honestly as a bidirectional structure and separately repair the exact bear-chop failure mode.” I translated that directly into two new frontiers: [bear_chop_core_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/bear_chop_core_repair_v1.json) and [asc1_bidirectional_annual_probe_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_bidirectional_annual_probe_v1.json), and both are now running. 

- 2026-04-09 08:45 UTC — turned two user hypotheses into direct annual tests instead of treating them as opinions. First, I validated the code path behind the “ARF1 can probably trade more often” idea: [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) really does expose exactly the levers the user pointed at (`ARF1_SIGNAL_TF`, `ARF1_SIGNAL_LOOKBACK`, `ARF1_MIN_RSI`, allowlist breadth), so I opened a dedicated annual frequency probe [flat_frequency_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_frequency_repair_v1.json) to answer the real question: can ARF1 trade materially more often without wrecking annual quality? Second, I checked the “we are missing a real horizontal long support/reclaim sleeve” hypothesis against existing data instead of reinventing it from scratch. [support_bounce_v1_regime_gap_repair_v1 results](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260408_130107_support_bounce_v1_regime_gap_repair_v1/results.csv) already contain usable annual candidates around `+15.9..16.7%`, PF `1.44..1.48`, `3` red months, so rather than opening another isolated sweep first, I built a new dynamic portfolio overlay [core4_flat_impulse_bounce_candidate_20260409.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core4_flat_impulse_bounce_candidate_20260409.env) and launched `dynamic_core4_flat_impulse_bounce_annual_v1`. That is the most direct test of whether the missing long-horizontal quadrant actually reduces red months at the portfolio level rather than just looking pretty as a standalone curve. 

- 2026-04-09 09:25 UTC — hardened the router around the exact failure mode the user flagged and removed the “fresh but silently degraded” blind spot. I confirmed the concern was valid: when Bybit scan data is unavailable, the router can still look healthy by age while operating in degraded fallback mode, and older fallback behavior could reuse last-known-good overlays too freely. I extended [scripts/dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py) and [scripts/build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) with stricter profile-level controls: `bt_require_history` now allows sleeves to reject symbols with no backtest evidence, and `fallback_mode` lets a profile degrade directly to anchors instead of stale overlay symbols. I then tightened [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json) so core sleeves such as `BREAKOUT`, `BREAKDOWN`, `BREAKDOWN2`, `ASC1`, `ARF1`, `ARS1`, `AVW1`, `IVB1`, `PF2`, and `ETS2` use `anchor_only` degraded fallback, and the core breakdown/breakout families explicitly exclude obvious degraded-mode leak symbols like `FARTCOINUSDT`, `HYPEUSDT`, and `1000PEPEUSDT`. I also closed an operational gap in the new backtest-gated path: [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) now reads `ROUTER_TRADES_CSV` from the project `.env` as well as the process environment, so server cron can use symbol-level backtest gating without ad hoc exports. Finally, I upgraded [check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh) and [server_status.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/server_status.sh) to parse live router/allocator JSON and surface `router_status`, `scan_ok`, fallback count, and allocator degraded/safe-mode state instead of only checking file freshness. Dry-run proof in the same offline environment now shows `BREAKOUT`, `BREAKDOWN`, and `BREAKDOWN2` degrading to anchor baskets rather than stale overlay drift, which directly removes the earlier degraded fallback path that could leak meme-like symbols into core sleeves. 

- 2026-04-09 09:50 UTC — fixed the operator reply truncation path so Telegram no longer depends on manual “send next” nudges. The immediate issue was not Telegram chunking itself — [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) already splits long outgoing messages — but the fact that DeepSeek responses were often cut at the API layer before Telegram ever saw them. I upgraded both [bot/deepseek_overlay.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/deepseek_overlay.py) and [bot/deepseek_autoresearch_agent.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/deepseek_autoresearch_agent.py) with automatic continuation loops: when DeepSeek stops because of `finish_reason=length`, the bot now immediately asks it to continue from the stopping point instead of waiting for a human prompt. This applies both to direct `/ai` operator replies and to internal audit/code-review style DeepSeek helpers. I also updated [deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh) so future foundation deploys actually ship the two DeepSeek modules; before this, operator-side fixes could silently remain local. The intended behaviour now is: one request in Telegram -> DeepSeek auto-continues until done or until the configured continuation cap is reached -> Telegram sends every chunk automatically in order. 

- 2026-04-09 10:05 UTC — added a bounded nightly-research queue scaffold so “self-improvement” does not mean “turn the live box into a backtest farm.” New [run_nightly_research_queue.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_nightly_research_queue.py) reads [research_nightly_queue.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/research_nightly_queue.json), checks how many `run_strategy_autoresearch.py` processes are already active, and refuses to launch more once the configured cap is reached. It writes queue state to `runtime/research_nightly/status.json`, appends a small history ledger to `runtime/research_nightly/history.jsonl`, and routes anything not pre-approved through [deepseek_research_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/deepseek_research_gate.py) instead of auto-running arbitrary specs. On the current busy laptop queue the dry-run correctly lands in `busy_skip`, which is the safe behavior we want before ever thinking about server deployment. 

- 2026-04-09 12:50 UTC — tightened observability around allocator degradation and wired nightly-research status into the operator truth pack. The live server itself is not “unstable cron-wise” right now; direct status check shows fresh heartbeat, fresh regime/router/allocator files, `router_status=ok`, and the current allocator degradation comes only from `degraded_reasons=['overall_health_watch']`. To stop misleading Telegram alerts, [check_control_plane_health.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh) now separates scheduler freshness problems from state-quality problems and includes allocator reasons in the message instead of always claiming cron may be broken. I also extended [operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py) so nightly-research queue state can appear in the operator snapshot once the queue runs on the chosen host, and updated [server_status.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/server_status.sh) plus [deploy_foundation.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/deploy_foundation.sh) accordingly. Uploaded the non-disruptive snapshot/health files to the server without restarting `bybot`; a manual server-side run of the new health check now reports the truthful issue: `Portfolio allocator: DEGRADED ... reason=overall_health_watch`. 

- 2026-04-09 13:05 UTC — made the nightly-research scaffold respect a real quiet UTC window and surfaced backtest-gate truth more clearly. [research_nightly_queue.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/research_nightly_queue.json) now defines a default `04:00-06:00 UTC` quiet window, and [run_nightly_research_queue.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_nightly_research_queue.py) will now report `outside_window` instead of attempting launches at the wrong time. I also extended [operator_snapshot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py) and [server_status.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/server_status.sh) so the router shows whether the backtest gate is actually on. Direct server inspection confirmed the last missing piece: `ROUTER_TRADES_CSV` is not set in server `.env`, the live router writes `backtest_path=\"\"`, and there are `0` validated baseline `trades.csv` files on the server. So the backtest gate is still logically implemented but operationally off until we seed a curated trades file onto the server and point `ROUTER_TRADES_CSV` at it. 

- 2026-04-09 13:20 UTC — completed the last mile of server-side backtest gating without restarting `bybot`. I added [refresh_router_backtest_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/refresh_router_backtest_gate.py), which copies the latest validated baseline `trades.csv` into a curated control-plane location: `runtime/control_plane/router_trades_baseline.csv`, with metadata in `router_trades_baseline_meta.json`. Then I updated [apply_live_control_plane_env_patch.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/apply_live_control_plane_env_patch.py) so live `.env` carries `ROUTER_TRADES_CSV=runtime/control_plane/router_trades_baseline.csv`. I uploaded the curated CSV and the patched env helper to the server, re-ran `build_symbol_router.py` and `build_portfolio_allocator.py`, and verified the live router now reports `backtest_path=/root/by-bot/runtime/control_plane/router_trades_baseline.csv` while keeping `router_status=ok` and `scan_ok=True`. This means `bt_require_history` is no longer just architectural intent on the server; symbol routing now has an actual historical evidence file to consult. 
