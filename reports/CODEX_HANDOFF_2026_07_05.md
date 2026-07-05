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

Normal server `git pull --ff-only` is blocked. Fix this carefully:

1. inventory dirty server files;
2. preserve server-only configs/runtime;
3. commit/archive legitimate server-local code;
4. restore clean deploy path.

No destructive reset.

### P1 — keep ATT1 live clean

Monitor:

- `runtime/bot_heartbeat.json`
- `runtime/decision_bus.jsonl`
- `runtime/att1_edge_health.json`
- `att1_try`, `att1_no_signal`, `att1_signal`, `att1_entry`

If no trade but reasons are `trendline`, it is not broken.

### P2 — IVB1 long shadow

Deploy IVB1 r003 as shadow only:

- `ENABLE_IVB1_TRADING=1`
- `IVB1_RISK_MULT=0.00`
- use `configs/ivb1_long_r003_shadow_20260705.env`

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

