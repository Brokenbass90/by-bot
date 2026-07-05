# Morning live + research status — 2026-07-05

## Executive verdict

The bot was not globally frozen. It was live, `dry_run=false`, `trade_on=true`, with `open_trades=0`.

The practical reason for no trades was twofold:

1. The only money-bearing crypto sleeve was `ATT1 short-only` at `risk_mult=0.10`, while current live regime was `bull_trend`. A short-only trendline-touch sleeve can naturally be quiet in that regime.
2. A real live-control bug was found and fixed: `configs/dynamic_allowlist_latest.env` was hot-reloading `ATT1_SYMBOL_ALLOWLIST` over the explicit r001 canary override. This meant live ATT1 risk/geometry were r001, but the active universe was not the validated r001 universe.

## Live fix applied

Commit:

- `a643032 fix: protect operator canary override from dynamic allowlist`

Changed:

- `bot/allowlist_watcher.py`
- `tests/test_allowlist_watcher_operator_override.py`

Behavior after fix:

- If `ALLOW_OPERATOR_LIVE_OVERRIDES=1` and `OPERATOR_LIVE_OVERRIDE_ENV` points to an explicit canary env, variables present in that override are owner-controlled.
- Dynamic router / auto-apply overlays can no longer silently overwrite those variables.
- This protects `ATT1_SYMBOL_ALLOWLIST`, `ATT1_RISK_MULT`, and other canary gate variables.

Validation:

- `pytest tests/test_allowlist_watcher_operator_override.py` → `4 passed`
- `pytest tests/test_strategy_pause_contract.py tests/test_proof_of_life_digest.py tests/test_allowlist_watcher_operator_override.py` → `10 passed`

Deployment:

- GitHub push succeeded: `2dfee2d..a643032`
- Server `git pull --ff-only` is blocked by dirty server worktree; no destructive cleanup was performed.
- Minimal live patch was applied by copying only `bot/allowlist_watcher.py` to `/root/by-bot/bot/allowlist_watcher.py`.
- `bybot.service` restarted successfully and is active.

Post-restart live heartbeat:

- `dry_run=false`
- `trade_on=true`
- `open_trades=0`
- `regime=bull_trend`
- `operator_live_override.loaded=true`
- `operator_live_override.env=configs/att1_short_r001_canary_20260702.env`
- `att1 risk_mult=0.10`
- `ATT1_SYMBOL_ALLOWLIST=ADAUSDT,BTCUSDT,DOTUSDT,ETHUSDT,LINKUSDT,LTCUSDT,SOLUSDT,SUIUSDT`
- `att1 breaker`: enabled, not blocked, not expired, trades=0
- Bybit equity snapshot: about `1019 USDT`

## Research results available this morning

### ATT1 universe expansion

Report:

- `reports/ATT1_UNIVERSE_EXPANSION_VERDICT_2026_07_04.md`

Result:

- Base 6/2 bps: `353 trades`, `+7.93R`, `PF 1.081`, `DD 9.16R`, `3 red months`
- Stress 10/5 bps: `364 trades`, `-9.24R`, `PF 0.913`, `DD 13.53R`, `6 red months`

Verdict:

- FAIL. Do not expand ATT1 to the tested 11-symbol group.
- No post-hoc cherry-picking of DOGE/1000PEPE/ONDO.
- Keep ATT1 r001 on the validated base universe only.

### FX H1 trend pass

Report:

- `reports/research/fx_h1_trend_after_att1_20260705/summary.md`

Result:

- `108` configurations.
- Coverage and cost guards were active.
- No trade-bearing candidate emerged; all rows were zero-trade or cost-infeasible.

Verdict:

- FAIL / no candidate. Current FX H1 trend-pullback/session-retest pass does not produce a deployable sleeve.

### Midterm refresh

Log:

- `logs/midterm_after_fx_20260705/run_20260704_151158.log`

Result:

- `midterm_short_v2_refresh_20260705_annual`: `4 trades`, `PF 0.011`, `net -0.17R`
- `midterm_short_v2_refresh_20260705_wf22`: `0 trades/window`, verdict `WEAK`
- `midterm_v3_refresh_20260705_macd_shorts`: `137 trades`, `PF 0.383`, `net -5.44R`
- `midterm_v3_refresh_20260705_macd_rsi`: `117 trades`, `PF 0.200`, `net -6.26R`

Verdict:

- FAIL. Do not deploy current midterm short_v2/v3.

### Cascade strict gate

Status from previous fixed run:

- Loader bug fixed: the gate now merges and filters all matching cache files by requested window instead of accidentally picking the largest unrelated cache file.
- Valid data coverage: `1.000`
- Symbols: `12`
- Liquidation events: `73,681`
- Window: `2026-06-16..2026-07-04`
- Trades: `0`

Verdict:

- Current strict cascade trigger is not a live candidate. It may need looser/composite logic, but not live risk now.

## Operational issue still open

The server worktree is dirty and blocks normal `git pull --ff-only`.

Do not use `git reset --hard` or blanket stash without review. Required cleanup path:

1. Inventory server-only changes.
2. Preserve runtime/config files that are intentionally server-local.
3. Either commit server-local code that must survive or archive it.
4. Restore normal deploy path so future fixes do not require one-file scp.

## Next work queue

Priority order:

1. Let restarted ATT1 r001 run with the correct universe; collect `att1_try/no_signal/signal` counters for several hours.
2. Add/validate a bull-side crypto sleeve. The portfolio is currently structurally too narrow: one proven `short-only` sleeve cannot be active in every regime.
3. Revisit long candidates only through gates:
   - ASB/support-bounce long with clean data + preflight + OOS.
   - IVB1 long/short only after repaired stop geometry and OOS.
   - BOS/CHoCH only as a filtered composite, not raw.
4. Do not add ARS1/range, ATT1 universe expansion, midterm, FX H1 trend, or strict cascade to live based on current evidence.
5. Clean the server deploy state.

