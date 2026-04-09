# Project Roadmap - 2026-04-02 Reset

## Purpose

Turn the bot from a fragile collection of strategies into a controlled adaptive system.

Order of work:
- truth and validation first
- control plane second
- live strategy repair third
- new strategies and new markets only after the core is stable

## Current Reality

- Historical `v5` annual crypto results were real and strong on the validated stack.
- Fresh exact-overlay holdouts are weaker and show regime degradation.
- The main current damage on fresh crypto windows comes from:
  - `inplay_breakout`
  - `alt_inplay_breakdown_v1`
- `alt_resistance_fade_v1`, `alt_sloped_channel_v1`, and `btc_eth_midterm_pullback` are not the main source of damage on the fresh window.
- Crypto live now has the basic control-plane artifacts deployed on server:
  - regime overlay
  - symbol router output
  - portfolio allocator overlay
- Crypto live now also has external observability / self-heal layers:
  - bot heartbeat file
  - heartbeat watchdog cron
  - control-plane freshness alert cron
  - control-plane repair watchdog cron
- Deterministic chart-geometry is now active without any image API:
  - reusable cache loader
  - geometry state builder
  - hourly server-side geometry snapshots for active symbols
- Geometry-aware routing now exists:
  - router can score symbols against sleeve-specific geometry context
  - router state records geometry reasons / keep flags
  - weak symbols can be filtered before they reach live sleeves
- Weak-trend softeners now also exist in the regime layer:
  - `flat` is no longer hard-disabled in every `bull_trend`
  - weak `bull_trend` can re-enable `flat` in reduced mode
- Router symbol-quality truth is now stronger locally:
  - per-symbol memory can be built from real `trades.csv` history
  - router can consume soft symbol penalties per sleeve and regime
  - router-quality audit can now flag currently selected symbols that already look toxic by historical evidence
  - historical control-plane replay / dynamic annual / walk-forward can now be wired against the same memory layer
- Server foundation is now close to a real single-live-truth loop:
  - systemd service
  - heartbeat
  - watchdog
  - control-plane health checks
  - geometry snapshots
  - operator truth pack
- AI/operator context is stronger than before:
  - live `/ai` snapshot now includes compact operator context
  - weekly AI cron can consume the same compact operator context
  - server now writes a compact `runtime/operator/operator_snapshot.*` truth pack hourly
- Historical strategy health is no longer just one frozen current file:
  - local replay can now consume a real `strategy_health_timeline.json`
  - operator truth pack now includes current health summary plus timeline metadata
- Portfolio overlap / exposure haircuts now exist inside the allocator.
- Explicit promotion gate now exists as policy + evaluator:
  - annual
  - walk-forward
  - portfolio compare
- Crypto live still needs promotion discipline on top of the rebuilt control plane:
  - now enforce it through the explicit policy artifacts instead of only docs language
- Websocket transport remains a real live risk:
  - recent `12h` diagnostic windows still show degraded reconnect / handshake quality
  - the bot now has a transport guard, but the transport itself still needs hardening
- Strategy work has now restarted on top of the rebuilt base:
  - `range_scalp` additivity truth fronts reopened on `recent180` and `annual`
  - `support_bounce` got a real regime-filter repair instead of more blind sweeps
  - `impulse` now has a dedicated annual-repair research front
- The current `core3 impulse` candidate is promising on `180d`, but the old `360d` probe stayed weak because:
  - early `2025-04..2025-09` months hurt badly
  - `alt_inplay_breakdown_v1` was the main loser
  - `ARF1` did not actually participate in those old `core3` probes
- Chart vision is partially wired:
  - Telegram chart inbox exists
  - `/chart_ai` exists in code
  - server-side image analysis still needs an image-capable API key

## Source of Truth

Only the following result classes may drive decisions:

1. `validated_baseline`
- frozen stack
- frozen symbols
- frozen env overlay
- frozen fees and slippage

2. `exact_holdout`
- same stack and overlay as the validated baseline
- different recent window
- used to test robustness

3. `fresh_server_rerun`
- rerun from cleaned cache and current server-side data
- used to confirm the result is reproducible on fresh data

The following are not promotion evidence:
- exploratory sweeps
- cache-dirty runs
- broken runs
- partial env reconstructions
- manual "close enough" comparisons

## Working Rules

Before every new task:
- read this roadmap
- confirm the task belongs to the highest active priority
- avoid starting a lower-priority front unless it unblocks the current one

After every material step:
- update `docs/WORKLOG.md`
- update `docs/JOURNAL.md`
- record what changed, what was learned, and what is next

General rules:
- prefer fresh data over old cache if there is any doubt
- prefer exact overlays over reconstructed env
- no live promotion from a single lucky run
- no self-retuning live parameters without offline validation and promotion

Long-horizon hardening still worth adding:
- append-only event / decision ledger for runtime truth
- config schema versioning + migration checks before deploy
- singleton job locks for cron / repair tasks
- off-host backup + bare-metal restore drill
- automatic canary rollback rules after promotion
- latency / fill-quality histograms as first-class health signals
- shadow mode for every sleeve before canary
- explicit strategy lifecycle states:
  - `research`
  - `candidate`
  - `shadow`
  - `canary`
  - `live`
  - `watch`
  - `banned`

## Priority Queue

### P0 - Validation Discipline and Live Damage Control

Goal:
- stop making decisions from mixed or low-trust evidence
- reduce live damage while we rebuild the control plane

Tasks:
1. Keep validation labels strict:
   - `validated_baseline`
   - `exact_holdout`
   - `fresh_server_rerun`
   - `exploratory`
   - `broken`
2. Keep archived high-trust runs and clean working directories.
3. Compare live env against the last trusted overlay before each deploy.
4. Apply temporary live damage control if fresh exact holdouts still show the same result:
   - reduce or disable `breakout`
   - reduce or disable `breakdown`
   - keep `flat`, `sloped`, `midterm` alive at reduced overall risk
5. Require exact base-candle coverage for trusted annual regression:
   - exact cache audit for the full symbol union
   - no "best cached slice" fallback inside `validated_baseline`
   - run the regression under project `.venv`, not system Python
6. Keep websocket transport guarded:
   - block new entries when WS health stays critical across multiple windows
   - persist WS guard state in runtime
   - only allow controlled restart when no open trades or an explicit rule says it is safe
7. Use full-year probes as mandatory truth for promotion:
   - no promotion from `180d` only
   - explain bad months instead of hiding them

Exit criteria:
- fresh reruns are clearly labeled and reproducible
- live config drift is documented
- temporary live damage-control decision is documented
- transport degradation no longer results in blind new entries

### P1 - Regime Orchestrator

Goal:
- give the bot a deterministic portfolio brain

What it must do:
- classify market regime on a fixed schedule
- apply hysteresis so the regime does not flip too easily
- write a JSON state and env overlay
- enable or disable sleeves:
  - breakout
  - breakdown
  - flat/fade
  - midterm
- apply a global risk multiplier
- send alerts on regime changes
- fail safe if state is missing, stale, or malformed

Immediate tasks:
1. Finalize local integration into the live bot.
2. Isolate orchestrator changes into a clean commit/branch.
3. Add control-plane audit trail:
   - orchestrator history
   - router history
4. Add a validated-baseline regression gate before server rollout.
5. Run local dry-run and one real run.
6. Deploy to server in dry-run mode.
7. Add cron only after dry-run output is sane.
8. Confirm live bot actually reloads and applies the overlay.
9. Replay the control-plane historically on annual checkpoints:
   - real BTC 4H regime timeline
   - frozen-router profile replay
   - allocator decision timeline
10. After the first replay:
   - keep historical health timeline support in the loop
   - replace frozen-router replay with historical symbol selection
   - compare control-plane timelines against portfolio annual windows
11. Feed deterministic geometry state into advisory / routing decisions:
   - levels
   - channels
   - compression
   - near-support / near-resistance context
12. Feed portfolio overlap / exposure into allocator decisions:
   - global overlap haircut
   - per-sleeve overlap haircut

Exit criteria:
- orchestrator runs cleanly on schedule
- live bot consumes the overlay
- bad state does not break trading
- router / allocator behaviour can be replayed historically on annual windows

### P2 - Dynamic Symbol Router and Strategy Profiles

Goal:
- stop treating symbol selection as static and manual
- centralize symbol picking instead of duplicating it inside every strategy

What it must do:
- build per-strategy allowlists
- support multiple profiles for the same strategy
- map strategy profiles to symbol families
- refresh safely on a fixed cadence
- output env overlays that the bot can hot-reload safely

Design rules:
- dynamic:
  - active sleeves
  - allowlists
  - profile choice
- not dynamic in live:
  - uncontrolled self-retuning of core strategy parameters

Immediate tasks:
1. Audit current pieces:
   - `scripts/dynamic_allowlist.py`
   - `bot/allowlist_watcher.py`
   - `configs/dynamic_allowlist_latest.env`
2. Define a profile registry:
   - strategy name
   - profile name
   - eligible symbol family
   - active regimes
3. Connect router output to orchestrator decisions.
4. Add safe reload and logging.
5. Keep sleeve selection explainable:
   - record geometry reasons
   - record fallback reasons
   - avoid silent empty sleeves unless the strategy is truly off

Exit criteria:
- router writes usable per-strategy allowlists
- live bot can consume them without restart loops
- profile selection is documented and reproducible

### P3 - Repair Current Live Crypto Sleeves

Goal:
- rebuild a crypto stack that survives fresh recent windows

Order:
1. `inplay_breakout`
2. `alt_inplay_breakdown_v1`
3. `alt_resistance_fade_v1`
4. `alt_sloped_channel_v1`
5. `btc_eth_midterm_pullback`

Repair rules:
- start from fresh data only
- use exact holdouts
- test strategy alone and in portfolio context
- do not trust isolated wins that fail inside the stack

Current expectations:
- `breakout` needs tighter quality filters and regime/context repair
- `breakdown` needs both bug cleanup and logic repair
- `fade` should be treated as a regime sleeve, not always-on
- `sloped` may stay a lower-frequency geometry sleeve
- `midterm` is a stabilizer, not the main engine

Promotion gate for a repaired live sleeve:
- recent 90d standalone result above breakeven
- acceptable drawdown
- does not destroy portfolio-level recent holdout
- configuration documented and reproducible

Stop conditions:
- if `breakout` still fails after two more bounded repair cycles, move it to research-only
- if `breakdown` still fails after bugfix plus two bounded repair cycles, move it to research-only

### P4 - Promote New or Repaired Strategy Families

Goal:
- only promote new sleeves after the control plane is in place

Current candidates:
1. `pump_momentum_v1`
2. `pump_fade_v4r`
3. `alt_inplay_breakdown_v2`
4. `pump_fade_v2`
5. `alt_support_bounce_v1`
6. `alt_range_scalp_v1`
7. `elder_triple_screen_v2`
8. `ts132` / Elder family
9. future support-bounce or sweep-reclaim families
10. `funding carry / funding harvest`

Rules:
- no live promotion before P1 and P2 are functioning
- every candidate must pass:
  - smoke
  - fresh recent-window test
  - portfolio interaction test

Funding-specific note:
- `funding carry` is the first non-directional sleeve worth pursuing after P1/P2, because it complements chop periods when directional momentum is weak
- but it still needs:
  - a clean runnable backtest path
  - symbol-selection validation
  - execution/venue safety review

Current-market research order after baseline reproducibility is explained:
1. `alt_range_scalp_v1`
2. `alt_inplay_breakdown_v2`
3. `alt_support_bounce_v1`
4. `pump_fade_v2`
5. `elder_triple_screen_v2`

### P4b - Capital-Efficient and Non-Directional Income Sleeves

Goal:
- add lower-correlation yield/carry sleeves after crypto control-plane is stable

Priority order:
1. Bybit funding harvest / delta-neutral carry
2. Hyperliquid as second perp venue
3. treasury deployment for idle stablecoin cash:
   - CEX Earn
   - Aave / similar lending
4. later:
   - cross-venue basis / perp arb
   - stable LP / DeFi automation

Rules:
- these sleeves must not bypass the same validation discipline
- simple APY claims are not enough; we need:
  - realistic fees
  - venue / borrow assumptions
  - cash lock-up assumptions
  - correlation to existing crypto sleeves
- funding carry may progress earlier than other expansion ideas because it is closer to existing infrastructure and can help during chop regimes

### P4c - Capital Router (Regime-Aware Capital Allocation)

Goal:
- maximize capital utilization across regimes by shifting allocation between directional and non-directional sleeves

Concept:
- `bear_chop`: `funding_carry_weight=0.25`, `directional_weight=0.75`
- `bear_trend`: `funding_carry_weight=0.10`, `breakdown_weight=0.90`
- `bull_trend`: `funding_carry_weight=0.00`, `impulse_weight=1.00`

Implementation:
1. extend [build_portfolio_allocator.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py) with a `funding_carry` sleeve
2. output `CARRY_POSITION_USD` into [portfolio_allocator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_latest.env)
3. `funding_carry_executor.py` reads `CARRY_POSITION_USD`
4. run it on the same allocator cadence

Prerequisites:
- funding carry validated on `365d`
- regime router stable in production
- capital large enough that carry has a meaningful absolute contribution

Rule:
- platform stays Bybit-first; no cross-platform capital router until the single-venue version is stable

### P5 - Multi-Market Expansion

Goal:
- expand only after crypto core is stable

Markets:
1. Alpaca equities
2. OANDA forex/CFD
3. later:
   - Hyperliquid / second venue perps
   - DeFi automation
   - arbitrage-like systems

Rule:
- no major expansion while crypto control-plane is unfinished

## Acceptance Gates

The crypto core is considered healthy only if all of the following are true:

1. control-plane
- regime orchestrator is live and reliable
- dynamic symbol router is live and reliable
- portfolio allocator is live and reliable
- safe mode / hard-block is live and reliable

2. validation
- exact-overlay fresh reruns are reproducible
- no important decisions depend on cache-dirty or broken runs

3. portfolio quality
- recent 90d portfolio result is above breakeven
- holdout 180d portfolio result is above breakeven
- drawdown is controlled
- no single sleeve is causing most of the damage without being flagged
- mirror-short momentum logic is retired; short-side momentum must stand on its own thesis

4. operational safety
- live state, overlays, and allowlists are auditable
- bot alerts on regime changes and tracking mismatches

## Deferred Until Core Is Stable

These stay deferred unless they directly unblock P0-P3:
- fully autonomous LLM-driven live parameter changes
- copy trading expansion
- DeFi automation
- arbitrage systems
- large new market rollouts

## Session Rule

For the next sessions:
- start from this roadmap
- work the highest active priority
- write the result to `WORKLOG` and `JOURNAL`
- do not let side experiments replace core repair

## 2026-04-08 Addendum

New foundation rules:
- historical router/allocator replay must reconstruct symbol baskets from cached history, not only from frozen overlays
- deterministic geometry engine comes before heavy vision work
- vision may assist analysis later, but level-building and regime/routing truth must stay reproducible without external model calls
- stitched annual validation must stay offline/cache-reproducible; no hidden live fetches in “honest” system tests
- dynamic system promotion must use the new stitched harness, not only sleeve-level probes or brain-only replay
- live foundation deploy must remain resilient even if the first `systemd` start fails; env patching, cron repair, and final restart must still happen
- new sleeves are not considered “connected” until all three are true:
  - live bot imports and schedules them
  - allocator policy contains them
  - server deploy copies the actual strategy module
- router truth matters as much as policy truth:
  - a sleeve is still effectively disconnected if the registry has no matching symbol-router profile
- current strategy direction after the latest honest truth:
  - `pump_fade` stays de-prioritized
  - `IVB1 off` is a stronger candidate than `IVB1 ema`
  - next portfolio compare should focus on `core2` vs `core2 + IVB1 off`
  - stitched `dynamic_system_annual_v1` should now be treated as a stale-stack benchmark, not the final annual answer for the repaired stack
  - after the repaired stack truth (`+13.17%`, PF `1.2182`, DD `5.24`, but `6` red months), the next repair focus is annual consistency rather than raw activation
  - `range_scalp_v1_annual_repair_v1` is now the active frontier for reducing red months / negative streaks without inventing a new sleeve family
  - live observability must treat `impulse/IVB1` as a first-class sleeve in pulse/status output, otherwise the stack keeps looking artificially narrower than it is
  - stitched annual truth must no longer inherit live-style regime stickiness by accident:
    - mixed-sign monthly checkpoints now need their own bias scoring instead of falling through to broad `bull_chop`
    - historical `hold=1` must mean immediate stitched switching, not “still wait another month”
  - [dynamic_core3_impulse_candidate_annual_v3_hold1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/dynamic_annual_20260408_172157_dynamic_core3_impulse_candidate_annual_v3_hold1) finished at `+7.27%`, PF `1.1074`, `5` red months:
    - better annual honesty
    - slightly better red-month count
    - worse raw return than `annual_v2`
  - current interpretation:
    - protection/routing layers were not “useless”
    - but the stack is still missing enough sleeve quality to translate cleaner routing into strong annual economics
  - immediate repair focus stays on:
    - fewer red months
    - better flat/range activation quality
    - stronger annual behaviour from `impulse`
    - an honest annual answer on whether `sloped` is additive or just noisy context
  - morning update changed the strategy hierarchy:
    - `impulse` now has real annual PASS rows
    - `flat` now has real annual PASS rows
    - `sloped` failed its first honest annual repair
    - `Elder` remains a rewrite candidate, not a tuning candidate
  - current top comparison task:
    - test the first promoted `flat + impulse` annual winners in stitched system form
    - compare with and without `sloped` before deciding whether `sloped` stays in the core package
  - next truth tasks now active:
    - validate `core3_flat_impulse_nosloped` on rolling `360d` walk-forward, not stitched annual only
    - use the new `IVB1` reason diagnostics to see whether live entry blockers are mostly regime, impulse quality, or retrace logic
    - re-test `Elder` only after live wiring and crypto-realistic defaults, so the next verdict is about actual sleeve quality instead of a missing integration
  - rolling validation has now been upgraded to the same truth standard as stitched annual:
    - [run_dynamic_crypto_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py) replays `regime -> router -> allocator -> health timeline` on each walk-forward window
    - this becomes the preferred validator for any future promotion decision once a stitched annual candidate looks good
    - the old static-symbol walk-forward remains useful only as a simpler baseline, not as the final truth layer
  - live observability next focus:
    - `flat` and `IVB1` no longer get treated as opaque `try up / entry zero` sleeves
    - future pulses should break `flat` down by `same_bar / regime / range / touch / reject / RSI / EMA / risk`
    - future pulses should break `IVB1` down by `no_breakout / impulse quality / retrace / stop / regime`
    - only after we see those live blockers clearly should we relax filters or lower timeframes
  - annual repair focus refined again:
    - the dominant weak quadrant is now explicit: `bear_chop`
    - current evidence says `breakdown` is overfiring in noisy down-chop while `flat` only partly offsets it
    - sloped research must no longer be judged only on a short-only annual run; it needs a bidirectional probe
  - new active frontiers:
    - [bear_chop_core_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/bear_chop_core_repair_v1.json)
    - [asc1_bidirectional_annual_probe_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_bidirectional_annual_probe_v1.json)
    - [flat_frequency_repair_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/flat_frequency_repair_v1.json)
  - new dynamic portfolio test:
    - [core4_flat_impulse_bounce_candidate_20260409.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core4_flat_impulse_bounce_candidate_20260409.env)
    - `dynamic_core4_flat_impulse_bounce_annual_v1`
  - interpretation:
    - if `support_bounce` stays mostly absent even in the new core4 annual run, the next fix is not “invent another long strategy” but loosen the router/health path that lets the bounce sleeve activate in bull-trend / bull-chop windows
  - router hardening priority update:
    - degraded fallback must no longer reuse stale overlay baskets for core sleeves
    - core router profiles should prefer `anchor_only` fallback plus explicit meme-symbol exclusions in degraded mode
    - symbol-level backtest gating should be plumbed through `ROUTER_TRADES_CSV` from `.env` so server cron can enforce historical evidence, not just local manual runs
    - ops visibility must treat `fresh but degraded` router state as a problem:
      - `check_control_plane_health.sh` should alert on `router_status != ok` or `scan_ok=0`
      - `server_status.sh` should show router fallback count and allocator degraded/safe-mode state
