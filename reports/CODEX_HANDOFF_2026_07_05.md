# CODEX HANDOFF — 2026-07-05

## Project in plain words

This is not just a trading bot anymore. It is becoming a research-to-live trading system:

1. **Live execution layer** — Bybit crypto now; Alpaca equities next; FX/CFD later.
2. **Strategy sleeve layer** — each strategy/side is treated as a separate sleeve, not as one mixed black box.
3. **Control plane** — regime, allocator, symbol router, breakers, expiry, telemetry, edge monitor.
4. **Research factory** — backtests, preflight, OOS, stress costs, symbol-OOS, data coverage gates.
5. **Future ML/data moat** — decision bus, live trades, liquidation stream, orderbook density, funding/OI.

The product goal is an electronic trader that can:

- trade only proven sleeves;
- collect evidence when a sleeve is silent or failing;
- prevent accidental live-risk from unproven research;
- keep improving through gated experiments rather than repeated rewrites.

The money goal is narrower and more urgent:

- get from one live crypto sleeve to a small portfolio of 2–3 proven sleeves;
- add Alpaca as the first non-crypto stabilizer once owner funds it;
- continue FX/CFD only after data/cost gates are clean.

## Why progress has felt stuck

The project has been stuck for three concrete reasons, not because “nothing works”:

1. **Strategy edge was overestimated by bad selection.**
   Old wins often came from post-hoc symbol pockets, nested “OOS” windows ending at the same date, tiny-N PF spikes, or signal-price execution.

2. **Data/control-plane bugs polluted verdicts.**
   Recent examples:
   - `missing_candles` made old range/live forensics unreliable;
   - FX M5 cost/ATR issue made EURUSD look dead for the wrong reason;
   - `dynamic_allowlist_latest.env` overwrote the ATT1 r001 canary universe in live.

3. **The live portfolio is structurally too narrow.**
   Right now crypto live money is only `ATT1 short-only`. In `bull_trend`, a short-only trendline sleeve can stay silent for days without being broken.

The right response is not “rewrite everything”. The right response is:

- fix data/control-plane bugs immediately;
- keep the one proven live sleeve clean;
- add a second sleeve only after gates;
- prioritize bull/long candidates because the current live sleeve is short-only.

## Current live state

As of the latest 2026-07-05 sync:

- Bybit equity: about `1019 USDT`.
- `dry_run=false`
- `trade_on=true`
- `open_trades=0`
- regime: `bull_trend`
- only money-bearing crypto sleeve: `ATT1 short r001`, `risk_mult=0.10`
- ATT1 breaker: enabled, not blocked, not expired
- `flat/range/ivb1/midterm/bounce/breakdown`: visible in runtime, but `risk_mult=0.0`; do not call them live-money sleeves.

ATT1 after the hotfix:

- active universe is now correct:
  `ADAUSDT,BTCUSDT,DOTUSDT,ETHUSDT,LINKUSDT,LTCUSDT,SOLUSDT,SUIUSDT`
- recent counters after restart:
  `att1_try=24`, `att1_no_signal=24`, reasons mostly `trendline/first_bar`
- meaning: it is waiting for a valid short trendline setup; it is not globally frozen.

## Critical fix applied on 2026-07-05

Problem:

- `OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_r001_canary_20260702.env` was loaded.
- But `AllowlistWatcher` then hot-reloaded `configs/dynamic_allowlist_latest.env`.
- That file contained:
  `ATT1_SYMBOL_ALLOWLIST=1000BONKUSDT,ADAUSDT,NEARUSDT,WLDUSDT,XLMUSDT`
- So live ATT1 had r001 risk/config but not the validated r001 universe.

Fix:

- Commit: `a643032 fix: protect operator canary override from dynamic allowlist`
- `bot/allowlist_watcher.py` now skips overlay vars that are explicitly present in active operator override.
- Tests:
  - `tests/test_allowlist_watcher_operator_override.py` → `4 passed`
  - with pause/proof-of-life contracts → `10 passed`
- Server `git pull` was blocked by dirty worktree, so the urgent live file was copied via `scp` and `bybot.service` restarted.
- Post-restart heartbeat confirmed correct r001 universe.

Open operational debt:

- Server worktree is dirty; normal deploy path is blocked.
- Do not `reset --hard`.
- Need inventory/preserve/commit/archive server-local changes so future deploys are normal again.

## Fresh research verdicts

### ATT1 universe expansion

Report:

- `reports/ATT1_UNIVERSE_EXPANSION_VERDICT_2026_07_04.md`

Verdict:

- FAIL.
- Base 6/2 bps: `353 trades`, `+7.93R`, `PF 1.081`, `DD 9.16R`
- Stress 10/5 bps: `364 trades`, `-9.24R`, `PF 0.913`
- Do not expand ATT1 to the tested 11-symbol group.

### FX H1 trend

Report:

- `reports/research/fx_h1_trend_after_att1_20260705/summary.md`

Verdict:

- FAIL / no candidate.
- 108 rows; no trade-bearing deployable candidate.

### Midterm

Log:

- `logs/midterm_after_fx_20260705/run_20260704_151158.log`

Verdict:

- FAIL.
- `midterm_short_v2`: `4 trades`, `PF 0.011`
- `midterm_v3_macd_shorts`: `137 trades`, `PF 0.383`
- `midterm_v3_macd_rsi`: `117 trades`, `PF 0.200`

### Strict cascade gate

Verdict:

- Valid real-data coverage, but current strict trigger gives `0 trades`.
- Do not live.

### ASB2 support bounce

Smoke result:

- `580 trades`, `-32.18R`, `PF 0.756`, large DD.

Verdict:

- Frequent but bad. Not live.
- Needs redesign/gating, not risk.

### IVB1 long r003

Report:

- `reports/IVB1_LONG_R003_PREFLIGHT_VERDICT_2026_07_05.md`

Verdict:

- Top next crypto candidate, but not live money yet.

Evidence:

- preflight r003: `29 trades`, `+6.47R`, `PF 2.791`, `DD 1.67R`
- next-open 6/2 bps: `29 trades`, `+6.47R`, `PF 2.791`, `DD 1.59R`
- next-open stress 10/5 bps: `29 trades`, `+5.28R`, `PF 2.338`, `DD 1.72R`
- time folds: base/stress both `4/4` positive, `robust_plateau`
- symbol-OOS: FAIL, `58 trades`, `-0.22R`, `PF 0.985`, `2/4` positive folds

Decision:

- Do not enable money today.
- Shadow/risk=0.0 is acceptable.
- Shadow config exists:
  `configs/ivb1_long_r003_shadow_20260705.env`

## What not to do next

Do not spend the next session on:

- another broad rewrite of all strategies;
- live-enabling ARS1/range;
- expanding ATT1 by cherry-picked symbols;
- trusting FX/XAU before data coverage is clean;
- promoting IVB1 long without shadow or preregistered symbol-selection gate;
- calling visible-but-risk=0 strategies “portfolio”.

## What to do next

### P0 — restore deploy hygiene

Status after continuation:

- DONE for the active branch. Server `/root/by-bot` was fast-forwarded from `75de6bd` to `48af041`.
- Preserved dirty server state in `/root/by-bot-deploy-hygiene-20260705_092001`.
- Tracked dirty changes were saved in git stash: `server tracked dirty before deploy hygiene 20260705_092001`.
- `637` conflicting untracked files were moved into the archive.
- Post-pull: tracked modified files `0`, conflicting untracked files `0`; `864` non-conflicting untracked server-local files remain.
- Server validation after pull: `py_compile_ok=1`; focused pytest set -> `10 passed`.

Do not `reset --hard`. If further cleanup is needed, inspect the archive/stash first.

The normal deploy path is no longer blocked by the old dirty/conflicting worktree state.

### P1 — keep ATT1 live clean

Monitor:

- `runtime/bot_heartbeat.json`
- `runtime/decision_bus.jsonl`
- `runtime/att1_edge_health.json`
- `att1_try`, `att1_no_signal`, `att1_signal`, `att1_entry`

If no trade but reasons are `trendline`, it is not broken.

### P2 — IVB1 long shadow

Status after continuation:

- DONE as shadow only.
- Active server `.env` now uses `OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_r001_plus_ivb1_r003_shadow_20260705.env`.
- Effective heartbeat after restart:
  - `open_trades=0`
  - `operator_live_override.loaded=true`
  - `att1 risk=0.1`
  - `ivb1 risk=0.0`
  - `regime=bull_trend`
- IVB1 shadow counters started after restart: first fresh heartbeat showed `ivb1_try=6`, `ivb1_no_signal=6`.

Goal:

- collect live signal frequency and simulated R without money.
- If live shadow produces enough recent clean signals, then consider tiny canary with breaker/expiry.

### P3 — find a real bull-side sleeve

This is the portfolio bottleneck.

Allowed candidates:

- IVB1 long with preregistered symbol-selection;
- support bounce only after redesign/gate;
- filtered BOS/CHoCH, not raw;
- maybe HZBO/breakout retest long if data/entry model is clean.

Requirement:

- coverage/cost gate;
- next-open / execution-accurate;
- stress fees;
- time-OOS and symbol-OOS or preregistered universe selection.

### P4 — Alpaca

Alpaca remains the strongest external candidate, but owner must fund/provide keys.

Do not block crypto work on Alpaca.

## Communication rules for next chat

User is tired and angry for valid reasons. Do not reassure with vague optimism.

Every response should answer:

1. What changed factually?
2. Does it affect live money?
3. What is still blocked?
4. What exact process/test/deploy is running?
5. When should the user return?

Keep initiative, but stay disciplined:

- propose next actions without waiting for perfect instructions;
- run bounded tests;
- document verdicts;
- update handoff/ledger;
- never confuse research PASS with live GO.

## Afternoon Continuation — Bull-Side Repair Running

Owner pushed to stop waiting and actively repair/retest dead logic. Action taken:

- Added fresh current-window research-only specs:
  - `configs/autoresearch/ivb1_long_r003_symbol_matrix_20260705.json`
  - `configs/autoresearch/asc1_long_current360_repair_20260705.json`
  - `configs/autoresearch/support_reclaim_current360_repair_20260705.json`
  - `configs/autoresearch/gs1_smart_grid_current360_probe_20260705.json`
- Added runner:
  - `scripts/run_bull_side_repair_20260705.sh`
- Started local screen:
  - `screen=bull_side_repair_20260705`
  - logs: `logs/bull_side_repair_20260705/`

Scope:

- Research only, local Mac, no live-risk changes.
- Sequence:
  1. IVB1 r003 per-symbol matrix;
  2. ASC1 long current-code repair (`limit=96`);
  3. support reclaim long repair (`limit=96`);
  4. GS1 smart-grid current-window probe (`limit=64`).

Early progress:

- IVB1 BTC row completed and failed: `net=-0.44R`, `PF=0`, `trades<3`.
- IVB1 ETH row was tiny-N positive: `net=+0.85R`, `PF=inf`, but failed `trades<3`.

Interpretation:

- This is not standing still: the next bull-side and grid candidates are actively being rechecked on current data.
- Any PASS from this run is only a research candidate. It must still pass stress, time-fold/OOS, symbol-OOS or causal symbol-selection, and shadow before any live money.

## Alpaca Funding Status

Owner initiated Alpaca funding from Revolut via Alpaca/CurrencyCloud local currency transfer:

- amount: `-440 EUR`
- status shown by Revolut: transfer in progress
- expected next handoff/arrival: around `2026-07-06`
- Alpaca dashboard immediately after send still shows `$0` buying power

Next actions after buying power appears:

- generate live Alpaca API keys in dashboard;
- do not paste keys into chat;
- place keys in server-only env/config;
- first run against the live account with `ALPACA_SEND_ORDERS=0`;
- run guard self-test;
- only then, during US market hours, consider the `$500` live canary.

## Alpaca Live Key Setup Added

User wanted exact key-entry/deploy steps without sending secrets to chat.

Added:

- `scripts/setup_alpaca_live_v38_env.sh`
  - prompts in local Terminal for LIVE Alpaca key ID and secret;
  - writes `configs/alpaca_live_v38.env`;
  - sets permissions to `600`;
  - keeps `ALPACA_SEND_ORDERS=0`;
  - can deploy the env by `scp` to `root@64.226.73.119:/root/by-bot/configs/alpaca_live_v38.env`.
- `scripts/run_alpaca_live_v38_once.sh`
  - dry-run by default against the live account;
  - `--send-orders` explicitly sets `ALPACA_SEND_ORDERS=1`.

Important:

- `configs/alpaca_live_v38.env` is already gitignored.
- Do not ask the user to paste key/secret into chat.
- The "approval" model clarified to owner: not per-trade approval. It is one live-mode gate for the `$500` canary. After `ALPACA_SEND_ORDERS=1`, the bot trades autonomously under guards. Still require first live-account dry-run before enabling orders.

## Bull-Side Repair Progress

`screen=bull_side_repair_20260705` still running locally.

IVB1 symbol matrix finished:

- best row: `HYPEUSDT`, `net +1.09R`, `PF 3.081`, `WR 75%`, `DD 0.54R`;
- several other rows PASS;
- verdict: symbol-selection clue only, not money. Needs stress/time-fold/symbol-selection gate/shadow.

ASC1 repair is now running; early rows fail gates.

## Alpaca Live Env Deployed + Dry-Run

Owner filled `configs/alpaca_live_v38.env` locally and deployed it to VPS via `START_ALPACA_LIVE_DEPLOY_ENV.command`.

UX note:

- user first opened shell scripts in VS Code and got confused;
- helper files now exist:
  - `START_ALPACA_LIVE_KEY_SETUP.command` for terminal prompt flow;
  - `configs/alpaca_live_v38.env` for paste-in-VS-Code flow (gitignored, contains secrets after owner edit);
  - `scripts/deploy_alpaca_live_v38_env.sh`;
  - `START_ALPACA_LIVE_DEPLOY_ENV.command`.
- Do not read/print `configs/alpaca_live_v38.env` in future responses because it now contains live secrets.

Server precheck:

- file exists at `/root/by-bot/configs/alpaca_live_v38.env`;
- no placeholder strings;
- `ALPACA_BASE_URL=https://api.alpaca.markets`;
- `ALPACA_SEND_ORDERS=0`;
- script syntax OK.

First VPS dry-run:

- command: `bash scripts/run_alpaca_live_v38_once.sh`;
- mode: `dryrun`;
- orders: none;
- reason: market closed and `ALPACA_SEND_ORDERS=0`;
- live account read returned `buying_power=0.0`, `cash=0.0`, so owner funding has not settled yet;
- current planned v38 symbols: `SNOW, GE, ABBV, BAC`, with simple-stop protection planned.

Telegram note:

- no TG alert is expected from env deployment/dry-run because this is not the main bot runtime notifier path.

## Evening Update — Live Stable, Fresh Crypto Research Running

Owner returned after ~2h and asked whether the system is moving or standing still.

Facts:

- Bybit live is stable:
  - `bybot.service=active`;
  - heartbeat fresh at `2026-07-05 15:31 UTC`;
  - `dry_run=false`, `trade_on=true`, `open_trades=0`, `regime=bull_trend`.
- Live money impact: none. Money sleeve remains `ATT1 short r001 risk_mult=0.10`; `IVB1` remains shadow with `risk_mult=0.0`.
- Alpaca live env works in dry-run, but account still unfunded:
  - `buying_power=0.0`;
  - `cash=0.0`;
  - `ALPACA_SEND_ORDERS=0`;
  - market closed until `2026-07-06 09:30 ET / 16:30 Cyprus`;
  - planned funded names: `SNOW, GE, ABBV, BAC`, each with broker protection planned.

Research facts:

- IVB1/HYPE original clue needed cache audit. Fresh `data_cache` HYPE follow-up:
  - base 360d: `10 trades`, `+1.76R`, `PF 2.160`, `WR 70%`, `DD 0.970R`;
  - stress 10/5 bps: `10 trades`, `+1.26R`, `PF 1.765`, `WR 70%`, `DD 1.056R`;
  - time folds are thin (`0/1/3/6 trades`), so HYPE is a symbol-selection candidate, not live money.
- ASC1 long repair: FAIL. Best row `31 trades`, `+2.06R`, `PF 1.206`, `DD 2.448R`, but `net<3.0; neg_months>4`.
- GS1 smart-grid first bounded probe: FAIL/current shape, `64/64` rows observed so far were zero-trade under current gates. No live/demo grid.
- Support-reclaim previous run was invalid as verdict: runner failed from missing default-cache `NEARUSDT`; it did not test the strategy properly.

New work launched:

- Added datacache specs:
  - `configs/autoresearch/ivb1_long_r003_symbol_matrix_datacache_20260705.json`
  - `configs/autoresearch/support_reclaim_current360_repair_datacache_20260705.json`
- Added runner:
  - `scripts/run_crypto_next_research_20260705.sh`
- Started:
  - `screen=crypto_next_research_20260705`
  - logs: `logs/crypto_next_research_20260705/`
  - sequence: IVB1 datacache symbol matrix -> support-reclaim datacache repair (`limit=96`).
- IVB1 datacache matrix finished:
  - best diagnostic row: `LINKUSDT`, `4 trades`, `+2.31R`, `PF=inf`, `WR 100%`, `DD 0.018R`;
  - next rows: `DOT +1.04R PF2.306`, `LTC +1.16R`, `HYPE +1.76R PF2.160`, `1000PEPE +1.70R PF1.538 with 17 trades`, `TAO +0.49R PF1.102 with 18 trades`;
  - interpretation: symbol-selection candidate set only. Several rows are tiny-N; no direct promotion.
- Support-reclaim datacache repair started and no longer crashes on missing `NEARUSDT` cache. Early rows are zero-trade; wait for bounded `limit=96` result.

Next operator:

1. Check `screen -ls` and `tail logs/crypto_next_research_20260705/02_support_reclaim_repair_datacache.log`.
2. If support-reclaim datacache finishes, summarize it; this is the repaired run after the cache issue.
3. Build the next IVB1 causal symbol-selection gate from the datacache candidate set (`LINK/DOT/LTC/HYPE/1000PEPE/TAO` are the interesting rows, but avoid cherry-pick promotion).
4. Recheck Alpaca buying power on Monday `2026-07-06` before US open and keep `ALPACA_SEND_ORDERS=0` until the live dry-run shows funds.

## Night Queue — Dynamic Selector + Crypto/FX Sleeve Hunt

Owner asked to stop standing still and run a 12h research queue for 2-3 new sleeves.

Support-reclaim update:

- corrected datacache support-reclaim rerun completed first bounded `96/288` rows;
- every row was `0 trades`;
- no runner/cache crash this time;
- verdict: current support-reclaim formula is too strict/no-signal. Treat as redesign backlog, not a candidate and not worth rerunning unchanged tonight.

Added:

- `scripts/run_ivb1_dynamic_symbol_selector_20260705.py`
  - causal selector: train per-symbol IVB1 r003 on prior windows, pick top-N symbols, test next OOS window;
  - grades policies through `bot.oos_selector`;
  - this is the requested dynamic coin-picking path for IVB1, not hindsight cherry-pick.
- `configs/autoresearch/hzbo1_current360_datacache_20260705.json`
  - HZBO/horizontal breakout long-only current 360d;
  - 32 bounded combos.
- `configs/autoresearch/inplay_breakout_retest_htf_current_datacache_20260705.json`
  - HTF breakout-retest long/both current 360d;
  - 96 bounded combos across 3 baskets.
- `scripts/run_overnight_sleeve_hunt_20260705.sh`
  - sequential queue:
    1. IVB1 dynamic symbol selector;
    2. HZBO current long;
    3. HTF breakout-retest current;
    4. FX/CFD multi-strategy range/sweep gate;
    5. FX native range/sweep harness.

Smoke before launch:

- IVB1 selector smoke technical OK.
- HZBO first row technical OK, bad result: `net -45.49`, `PF 0.666`, `DD 48.77`.
- Breakout-retest first row technical OK, bad result: `net -4.86`, `PF 0.677`, `DD 6.41`.
- These are not family verdicts; they only show specs execute.

Started:

- `screen=overnight_sleeve_hunt_20260705`
- start: `2026-07-05 16:33 UTC`
- logs: `logs/overnight_sleeve_hunt_20260705/`
- first log is active: `logs/overnight_sleeve_hunt_20260705/01_ivb1_dynamic_symbol_selector.log`
- output dir for first step: `reports/research/ivb1_dynsel_20260705_20260705_163337/`

FX/CFD policy:

- Current best first stack is `range detector -> false breakout / liquidity sweep / reclaim -> asymmetric RR -> spread/news/session gate`.
- Tonight tests this through `failure_reclaim_session_v1`, `liquidity_sweep_bounce_session_v1`, `asia_range_reversion_session_v1`, `range_bounce_session_v1`, `breakout_continuation_session_v1`, `trend_retest_session_v2`, and native `round_level_sweep/session_range_fade/session_breakout_retest/trend_pullback`.
- Do not promote raw grid/martingale. If grid is revisited, it must be bounded, hard-stop, no-martingale, and stress-cost gated.

Live money:

- No live-risk change.
- Bybit money sleeve remains only ATT1 short r001 at `risk_mult=0.10`.
- IVB1 remains shadow at `risk_mult=0.0`.
- Alpaca remains `ALPACA_SEND_ORDERS=0` until funds settle and live-account dry-run passes.

Next operator:

1. Check `screen -ls`.
2. Tail `logs/overnight_sleeve_hunt_20260705/01_ivb1_dynamic_symbol_selector.log`.
3. If step 1 finished, inspect `reports/research/ivb1_dynsel_20260705_20260705_163337/selector_summary.csv`.
4. Morning: summarize any PASS/FAIL into `PROJECT_STATE_LEDGER.md`.
5. Earliest promotion path: PASS -> shadow/risk=0.0; tiny canary only after clean shadow telemetry and owner live gate.

## Night Queue Restart + Parallelization

The first `overnight_sleeve_hunt_20260705` attempt died during IVB1 selector because `NEARUSDT` had no cached slice for one train window:

- error: `FileNotFoundError: No cached slice found for NEARUSDT`;
- this was a selector robustness bug, not an IVB1 strategy verdict.

Fix:

- `scripts/run_ivb1_dynamic_symbol_selector_20260705.py` now catches per-symbol train and OOS backtest failures;
- failed/missing symbols are written as `run_error` rows and excluded from eligibility;
- the selector continues instead of aborting.

Validation:

- `python3 -m py_compile scripts/run_ivb1_dynamic_symbol_selector_20260705.py` passed;
- missing-cache smoke passed.

Restarted:

- `screen=overnight_sleeve_hunt_20260705`
- started fresh at `2026-07-05 19:06 UTC`
- current output dir: `reports/research/ivb1_dynsel_20260705_20260705_190639/`
- current log: `logs/overnight_sleeve_hunt_20260705/01_ivb1_dynamic_symbol_selector.log`
- confirmed in log: `NEARUSDT` now logs `train-error` and IVB1 selector continues into OOS rows.

Parallel screens added so the remaining 10h produce results even if IVB1 is slow:

- `screen=crypto_breakout_overnight_20260705`
  - script: `scripts/run_crypto_breakout_overnight_20260705.sh`
  - logs: `logs/crypto_breakout_overnight_20260705/`
  - sequence: HZBO current long -> HTF breakout-retest current.
- `screen=fx_cfd_overnight_20260705`
  - script: `scripts/run_fx_cfd_overnight_20260705.sh`
  - logs: `logs/fx_cfd_overnight_20260705/`
  - sequence: FX/CFD multi-strategy range/sweep gate -> native FX range/sweep harness.

Selector/control architecture answer for the next operator:

- Yes, the repo already has selector pieces:
  - `bot/cross_sectional.py` = generic rank/top-k/z-score selector primitives;
  - `scripts/run_ars1_dynamic_range_picker.py` = ARS1 strategy-specific causal picker;
  - `scripts/run_ivb1_dynamic_symbol_selector_20260705.py` = new IVB1 strategy-specific causal picker;
  - `bot/oos_selector.py` = anti-overfit OOS gate;
  - `bot/research_orchestrator.py` = proposal layer for AI/operator review;
  - `bot/strategy_catalog.py` + `bot/ai_context.py` + web AI routes = AI can see live strategy/risk context;
  - Telegram status/notifier scripts exist, including `proof_of_life.py`, `universe_change_notifier.py`, and research-gate notifications.
- Missing product layer:
  - unified selector API contract: common gates for data coverage/liquidity/spread/news + per-strategy scores;
  - `runtime/selector_status.json` or equivalent;
  - web dashboard card and TG command showing selected symbols, ejected symbols, reason, OOS status, shadow/canary stage.

## Morning 2026-07-06 — What Changed

Night screens completed; they did not remain stuck:

- `logs/overnight_sleeve_hunt_20260705/DONE.txt`
- `logs/crypto_breakout_overnight_20260705/DONE.txt`
- `logs/fx_cfd_overnight_20260705/DONE.txt`

Live money impact:

- none;
- Bybit live money remains only `ATT1 short r001 risk_mult=0.10`;
- `IVB1` remains shadow/risk `0.0`;
- Alpaca remains live-env dry-run only with `ALPACA_SEND_ORDERS=0` until funds settle and a funded dry-run passes.

Night verdicts:

- IVB1 dynamic selector FAIL: `reports/research/ivb1_dynsel_20260705_20260705_190639/selector_summary.csv`, 12 policies, 0 PASS. Do not promote IVB1 to money.
- HZBO current long FAIL: `backtest_runs/autoresearch_20260705_190936_hzbo1_current360_datacache_20260705/ranked_results.csv`, 32 rows, 0 PASS.
- HTF inplay breakout-retest is the only promising crypto clue: `backtest_runs/autoresearch_20260705_202858_inplay_breakout_retest_htf_current_datacache_20260705/ranked_results.csv`, 8 base-screen PASS rows on `DOGE/ADA/SUI/1000PEPE/TAO`, roughly `152-177 trades`, PF `1.33-1.48`, DD `1.0-1.74`. This is not live-ready; it needs strict gates.
- FX/CFD not ready for capital. Current results are either negative after stress/risk estimate or tiny-N. Data coverage is also weak: annual FX/CFD cache coverage on tested majors/XAU is only about `13-47%`; 120d/60d checks also fail. First FX task is data/backfill quality, not live money.

New files:

- `scripts/preflight_cache_coverage.py`
  - generic cache coverage check for crypto JSON cache and FX/CFD CSV cache;
  - use before long research queues so missing/partial cache is caught before hours of compute.
- `scripts/run_inplay_breakout_retest_strict_gate_20260706.py`
  - fixed r061 params;
  - base/stress 360d;
  - 4x90d base/stress time folds;
  - per-symbol checks;
  - leave-one-out concentration checks.

Started:

- `screen=inplay_br_strict_20260706`
- log: `logs/strict_gates_20260706/inplay_br_strict_20260706.log`
- output: `reports/research/inplay_br_strict_20260706_*`

Next operator:

1. Check `screen -ls`.
2. Tail `logs/strict_gates_20260706/inplay_br_strict_20260706.log`.
3. When done, inspect `reports/research/inplay_br_strict_20260706_*/verdict.json` and `strict_runs.csv`.
4. PASS means shadow/risk=0.0 candidate only; FAIL means redesign. No automatic live money.

Promotion contract:

Every new sleeve must pass:

`data/cache gate -> backtest -> stress costs -> time-OOS -> symbol-OOS or causal dynamic selector -> shadow/risk=0.0 -> clean telemetry -> tiny canary`.

New strategies should plug into common gates plus a strategy-specific scorer. Do not create a separate ad-hoc promotion path per strategy.

## Fresh Live Check 2026-07-06 — ATT1 Has Opened A Real Trade

Direct VPS read-only check:

- `bybot.service=active`
- `dry_run=false`
- `trade_on=true`
- `regime=bull_trend`
- `open_trades=1`

Current position:

- `ADAUSDT Sell`
- strategy: `att1_trendline_touch`
- entry: `0.189137`
- current at check: about `0.187`
- qty: `191`
- exchange SL: `0.1936`
- runner ladder enabled; targets around `0.183584` and `0.177717`
- uPnL at check: about `+0.4081 USDT`

Interpretation:

- The owner statement "bot did not trade" is no longer current. It opened a real Bybit ATT1 short. This is the only live-money sleeve already approved (`ATT1 risk_mult=0.10`), not IVB1/FX/Alpaca.
- Alpaca remains disabled for orders: VPS env still has `ALPACA_SEND_ORDERS=0`.

Live issue found:

- `live_positions.json` showed position `qty=191`, but runner `initial_qty=97`, `remaining_qty=97`.
- Root cause: during pending-entry fill sync, the bot updates `tr.qty` from exchange `size`, but did not update runner quantities to the actual filled size.
- Risk assessment: exchange SL is set for the position, so this is not an unprotected trade. The affected surface is runner partial exits / time-stop under-closing.

Local fix added and validated:

- `bot/runner_state.py::sync_runner_qty_after_fill`
- `smart_pump_reversal_bot.py` calls it after `tr.qty = float(size)`.
- New tests: `tests/test_runner_state_fill_sync.py`
- Validation:
  - `python3 -m py_compile bot/runner_state.py smart_pump_reversal_bot.py scripts/preflight_cache_coverage.py scripts/run_inplay_breakout_retest_strict_gate_20260706.py`
  - `.venv/bin/pytest tests/test_runner_state_fill_sync.py tests/test_live_position_view.py tests/test_tpsl_policy.py`
  - result: `15 passed`

Operational note:

- Patch is local at this point. Do not blindly restart the live bot while `open_trades=1`.
- Current ADA position has exchange SL. Deploy/restart should wait for flat state or be done deliberately with owner approval and a position-state plan.

## Final Codex Session Before Pause — 2026-07-06

ADA forensics:

- Direct Bybit API evidence says ADAUSDT was not stopped out.
- At `2026-07-06 06:33 UTC`, Bybit had open `ADAUSDT Sell size=191`, `avgPrice=0.18913665`, `markPrice≈0.1837`, `unrealisedPnl≈+1.04 USDT`, `stopLoss=0.1936`.
- Bybit `closed_pnl` for the last 96h was empty.
- Follow-up at `2026-07-06 06:56 UTC`: Bybit shows one reduce-only buy `53 ADA @ 0.1837`, `closedPnl=+0.27827803` USDT, and remaining `ADAUSDT Sell size=138`, `markPrice≈0.1836`, `unrealisedPnl≈+0.7641` USDT, `stopLoss=0.1936`. This was partial profit-taking, not a stop-out.
- Executions show two bot market sells:
  - `97 ADA @ 0.1883`, `2026-07-05 20:26:30 UTC`, order `7409c106-...`;
  - `94 ADA @ 0.1900`, `2026-07-05 23:42:40 UTC`, order `6fea253e-...`.
- `runtime/order_link_id_log.jsonl` confirms both orders were generated by the bot.
- `runtime/live_trade_events.jsonl` logged only the first order/fill and missed the second order. `runtime/trades.db` is stale/empty for this evidence path. Treat this as a reporting/telemetry incident, not an exchange mystery.

Safety patches:

- Added hard remote-position entry guard in `smart_pump_reversal_bot.py::_reserve_entry_slot()`: if Bybit already has size for the symbol, or remote check fails, no new entry is reserved/submitted.
- Added runner qty sync in `bot/runner_state.py::sync_runner_qty_after_fill()` and called it after fill sync updates `tr.qty`.
- Added `scripts/live_bybit_evidence_20260706.py` for sanitized Bybit/runtime evidence.
- Validation passed locally: py_compile plus `15 passed` for runner/live-position/tpsl tests. Server py_compile passed after copying files.
- Important current-state note: running live process still has the old ADA runner state (`initial_qty=97`, `remaining_qty=43.65`) while exchange size is `138`. Exchange SL covers the full remaining position, but residual profit-taking is under-sized until flat/restart or deliberate manual intervention.
- Files were copied to VPS disk. The running `bybot.service` was not restarted while ADA is open.
- VPS watcher running: `screen=restart_when_flat_20260706`, log `logs/restart_when_flat_20260706.log`. It restarts `bybot.service` only after 5 flat confirmations, applying the disk patch safely.

Research launched:

- `screen=inplay_br_maker_cost_20260706`
  - log: `logs/inplay_br_maker_cost_gate_20260706/run.log`
  - same inplay r061 fixed params, cost proxy `base fee/slip=1/0 bps`, `stress=2/0.5 bps`.
  - final PASS / `strict_gate_pass`: `base_360 152 trades +7.66R PF 2.006 DD 0.87`; `stress_360 +6.91R PF 1.865`; `3/4` base folds positive; `5/5` individual symbols positive; leave-one-out all positive; symbol concentration `0.279948`.
  - This validates the cost-drag hypothesis. It is not live money yet: next gate is true maker-fill / limit-entry simulation, then shadow/risk=0.0.
- `screen=inplay_br_limit_scan_20260706`
  - log: `logs/inplay_br_limit_scan_20260706/screen.log`
  - output: `reports/research/inplay_br_limit_scan_20260706_*`
  - `strategies/inplay_breakout.py` now has a default-off research switch: `BREAKOUT_USE_LIMIT_ENTRY=1`, `BREAKOUT_LIMIT_ENTRY_VALIDITY_BARS`, `BREAKOUT_LIMIT_ENTRY_OFFSET_ATR`.
  - First exact-level strict attempt (`inplay_br_limit_entry_20260706`) was stopped after `base_360: 0 trades`; exact level with validity `6` bars is too strict.
  - The active scan tests offsets `0,0.05,0.10,0.20,0.35` and validities `6,12,24,48` under base/stress maker-ish costs. A good scan row still needs the full strict gate before shadow.
- `screen=fx_cfd_backfill_gate_20260706`
  - script: `scripts/run_fx_cfd_backfill_and_gate_20260706.sh`
  - log: `logs/fx_cfd_backfill_gate_20260706/screen.log`
  - fetches 730d Dukascopy for `EURUSD,GBPUSD,USDJPY,EURJPY,GBPJPY,XAUUSD`, then runs data status, preflight, FX/CFD multi-strategy gate, and native range/sweep harness.
  - `scripts/fetch_forex_dukascopy.py` now scales `XAUUSD` with `1000`.
- Alpaca dry-run monitor on VPS:
  - `screen=alpaca_dryrun_monitor_20260706`
  - log: `logs/alpaca_dryrun_monitor_20260706.log`
  - dry-run only, `ALPACA_SEND_ORDERS=0`.
  - latest check: `buying_power=0.0`, `cash=0.0`, endpoint live, cap `500`.

Next operator checklist:

1. Run `screen -ls` locally and on VPS.
2. Check ADA with `scripts/live_bybit_evidence_20260706.py --symbol ADAUSDT --lookback-hours 96` on VPS.
3. If ADA is flat, confirm `restart_when_flat_20260706` restarted `bybot.service`; if not, inspect its log.
4. Inspect `inplay_br_limit_scan_20260706`; if it finds a viable fill row, run the full strict gate for that row before any inplay shadow promotion.
5. Inspect FX data status and native/multi-strategy outputs after `fx_cfd_backfill_gate_20260706` completes.
6. Do not enable Alpaca send-orders until buying power is nonzero and a funded dry-run is reviewed.
7. P0 technical debt: reconcile live reporting. Bybit executions, `live_trade_events`, `trades.db`, and Telegram must agree automatically.

## 2026-07-06 Mid-Morning Continuation — Alpaca Armed, Reports Fixed

Facts changed:

- Commit pushed and deployed: `a028213 ops: harden live sleeves and research gates`.
- VPS is now at `a028213` via fast-forward pull, no reset. Server runner/smart live patches were stashed/backed up before pull; runtime `configs/portfolio_allocator_latest.env` remains server-local dirty.
- Server validation passed:
  - py_compile for touched modules OK;
  - `pytest -q tests/test_daily_digest.py tests/test_inplay_breakout_limit_entry.py tests/test_runner_state_fill_sync.py tests/test_level_memory.py` -> `14 passed`.
- Telegram daily digest is wired and tested:
  - `python3 -m bot.daily_digest --root . --print` reports `ADAUSDT Sell | uPnL +0.67$ | SL 0.1893`;
  - `python3 scripts/tg_daily_digest.py` sent successfully at `2026-07-06 08:30 UTC`;
  - cron already has daily digest at `0 8 * * *`.

Live Bybit:

- ADA short is real and still open at last check.
- Partial profit was taken: `53 ADA @ 0.1837`, `closedPnl=+0.27827803`.
- Remaining exchange/runtime position around `138 ADA Sell`.
- Runtime shows exchange SL at `0.1893` (near breakeven). No visible Bybit TP is expected because TP model is runner ladder/trailing, not a normal exchange TP.
- Live risk impact: no new crypto risk. Still only ATT1 r001 with `risk_mult=0.10`.
- Residual caveat: running service may still have old runner qty state until flat/restart. Exchange SL covers full remaining size.

Alpaca:

- Funds settled: live API/account shows about `$494.90` cash/buying power/equity.
- Funded dry-run and pre-market `send_orders=1` smoke-run passed safely:
  - market closed;
  - no orders placed;
  - planned entries skipped as `skipped_market_closed`.
- Live v38 manager armed in cron:
  - `*/30 13-20 * * 1-5 /bin/bash -lc 'cd /root/by-bot && bash scripts/run_alpaca_live_v38_once.sh --send-orders >> logs/alpaca_live_v38_manager.log 2>&1' # alpaca_live_v38_manager`
  - first real attempt: `2026-07-06 13:30 UTC / 16:30 Cyprus`, if Alpaca clock is open.
- Constraints: live endpoint, cap `$500`, current top4, broker stop required, market-clock gate, Telegram action report.

Research verdicts:

- Inplay maker-cost proxy: PASS, validates cost-drag hypothesis.
- True limit-entry scan: FAIL/current implementation. All 20 offset/validity combos produced `0 trades`. Next repair must be a real maker-fill/queue model or softer retest execution, not another exact-limit grid.
- IVB1 causal dynamic selector: FAIL. Best policy only `2/4` positive OOS folds, aggregate PF about `0.36`. IVB1 remains shadow/risk `0.0`.
- Support-reclaim datacache repair: FAIL/no-signal. Bounded `96/288` rows all `0 trades`. Redesign with `level_memory`/respect-score/sweep-reclaim before more compute.
- FX/CFD backfill screen is alive locally but long/noisy: `730d x 6` Dukascopy fetch has poor progress logging and may take hours. No FX/CFD capital.

Next return:

- Best high-signal return: after `16:45 Cyprus` to see Alpaca first live manager run, or evening to see FX backfill progress.
- If owner worries about ADA before then, check Bybit position and SL; manual close/reduce is an owner risk decision, not automatic code work.
