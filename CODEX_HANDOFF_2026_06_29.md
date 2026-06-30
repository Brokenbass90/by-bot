# CODEX HANDOFF — 2026-06-29

Branch: `codex/dynamic-symbol-filters`. Stage only explicit paths; the worktree
still contains many old untracked docs/scripts and generated proof-of-life files.

## 2026-06-30 midday update — current truth

Live crypto:

- Server live check at `2026-06-30T11:07:35Z`: `trade_on=true`,
  `dry_run=false`, `open_trades=0`, regime `bear_chop`, uptime about `4h44m`.
- Operator canary override is still loaded:
  `OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env`.
- Active risk is intentionally clean:
  `att1=0.10`; `flat/range/breakdown/ivb1/midterm/bounce1=0.0`.
- ATT1 breaker is armed and not blocking:
  `enabled=true`, `blocked=false`, `expired=false`, old window
  `trades=4`, `net_pnl=-0.7206`, `winrate=25%`, below `min_trades=6`.
- Since latest restart, ATT1 had `36` tries and `0` entries. Rejections are
  normal strict-setup rejects: `trendline=24`, `touch=5`, `rsi=1`,
  `first_bar=6`. Conclusion: live is not frozen; only one rare short-trendline
  canary has risk, so it can wait many hours without a trade.

Research results:

- ARF2 (`alt_resistance_fade_v2`) full 240d sweep completed with `63/192` PASS,
  but the safe-subset OOS did **not** justify live risk:
  - fresh 60d mostly `0` trades; r055 had `1` trade for `-0.50R`;
  - 360d safe-subset r055/r121/r125 stayed positive but low-frequency
    (`14-19` trades, PF about `1.8-1.94`);
  - more frequent r065/r067/r069 degraded to PF about `0.95-1.00` with
    `5.5R-7R` DD.
  Verdict: ARF2 remains research/watchlist, not canary.
- ASB2/ACB1 240d post queue completed and was negative:
  - ASB2 default: `245` trades, `-6.83R`, PF `0.845`, DD `10.61`;
  - ASB2 + HVN: `180` trades, `-9.24R`, PF `0.731`, DD `11.82`;
  - ACB1 default: `208` trades, `-4.99R`, PF `0.854`, DD `7.43`;
  - ACB1 + HVN: `140` trades, `-1.46R`, PF `0.936`, DD `6.09`.
  Verdict: no live risk; ACB1+HVN is the least bad research baseline.
- InPlay 240d comparison:
  - base: `210` trades, `-4.31R`, PF `0.868`, DD `6.47`;
  - `VOLUME_EXIT_ENABLE=1`: `232` trades, `-8.00R`, PF `0.701`, DD `8.68`.
  Verdict: current volume-exit wiring worsened this tested InPlay package; keep
  disabled until redesigned.
- SpikeFadeV3 LINK short remains the cleanest crypto diversifier candidate:
  `32` trades, `+5.10R`, PF `1.987`, WR `59.4%`, DD `1.27`, red months `2`.
  Next required step: bounded OOS/replay on fresh cache before tiny canary.
- PFS1 pump-fade autoresearch was stopped manually on `2026-06-30` because it
  repeatedly timed out / produced `0` trades and consumed about `25%` RAM next
  to live. Available RAM improved from roughly `285MB` to `484MB`.

FX / metals:

- `screen fx_deep_after_crypto_20260630` is running a stricter free-data FX
  gate. No OANDA keys are needed for research; OANDA is only for demo/live
  execution later.
- Previous loose FX gate produced three CANARY rows (`GBPJPY` conservative,
  `GBPUSD` eurusd_canary/active), but those are not live-ready until the strict
  gate confirms positive stress return and acceptable DD.
- Metals scout previously had no PASS; treat XAU/XAG as separate strategies
  with instrument-specific spread/swap/session models, not a direct crypto port.

Local code batch status:

- AdaptiveContextProvider / market-context freshness / HVN/adaptive hooks are
  local and tested, but not deployed to live yet.
- Local checks passed:
  - `35 passed`: adaptive context, market context, ASB2, ACB1;
  - `70 passed`: strategy catalog, live closed-candle parity, next-open,
    strategy breaker, market context, adaptive context, ASB2/ACB1,
    SpikeFadeV3, BreakdownRetestV3.
- Because ASB2/ACB1 OOS is negative and `market_context` is shared
  infrastructure, deploy this batch as research/foundation only after explicit
  review; do not use it to enable new live risk.

Alpaca:

- Alpaca v38 remains the fastest real-money path. Action is operational, not
  research: create/fund real Alpaca account with about `$500`, generate live API
  keys, create server-only `configs/alpaca_live_v38.env`, run live-account
  dry-run with `ALPACA_SEND_ORDERS=0`, then enable send-orders only after owner
  OK during market hours.

2026-06-30 later update:

- Claude batch added local research-only `strategies/inplay_retest_v4.py` and
  `scripts/market_survey.py`.
- Found and fixed two wiring issues before committing:
  - `AltChannelBounceV1Strategy` import in `backtest/run_portfolio.py` had an
    accidental third argument;
  - `inplay_retest_v4` was not in `run_portfolio.py` allowed strategy list /
    risk env map.
- Local checks after fix:
  - `38 passed`: InPlay V4, next-open, strategy catalog, market context,
    adaptive context;
  - `py_compile` passed for `backtest/run_portfolio.py`,
    `strategies/inplay_retest_v4.py`, `scripts/market_survey.py`;
  - smoke run completed:
    `LINKUSDT,SUIUSDT`, 30d, next-open, 6/2 bps,
    `9` trades, `-0.33R`, PF `0.761`, DD `0.9167`.
    This is only a routing smoke, not a verdict on V4.
- `market_survey.py` smoke found 60 symbols:
  `38` LEVELS/mixed, `16` RANGE/BOUNCE, `6` HIGH_VOL. It is a scouting dashboard,
  not a signal generator.
- Server cleanup: stopped stale `support_bounce_v1_annual_repair_v2` after
  `406` rows / `0` PASS. Best rows had PF around `1.31-1.37` but failed
  monthly stability (`5-6` red months, red streak `3`). Available RAM recovered
  to about `467MB`.

2026-06-30 night update:

- User asked whether horizontal levels are live. Current answer: **no live
  horizontal price sleeve has risk**. The canary override leaves only ATT1
  short-only (`risk=0.10`) live. `flat/range/bounce/ivb1/midterm/breakdown`
  remain `risk=0.0`. Horizontal/range/pump/breakout helpers are research until
  wired + WF/OOS pass.
- Stopped another stale live-VPS research process:
  `inplay_breakout_retest_focus_v1` was consuming about `41%` RAM and left only
  ~`153MB` available. After kill, available RAM recovered to ~`494MB`. Rule:
  do not run heavy sweeps on the 1GB live VPS; use local or separate research
  VPS.
- New helper-layer batch from Claude exists locally and is validated:
  - `bot/range_filter.py` — unified range/chop + side split;
  - `bot/pump_exhaustion.py` — pump/dump exhaustion fade gate;
  - `bot/retest_quality.py` — shared retest quality scorer;
  - `bot/elder_filter.py` — Elder as confluence filter, not standalone engine;
  - `bot/breakout_confirm.py` — confirmed breakout + anti-fakeout.
- Local validation:
  `73 passed` for range/pump/retest/elder/breakout helpers plus market_context,
  adaptive_context, IRV4, next-open and strategy catalog.
- These helpers are not yet wired into live sleeves. Next engineering step is
  phased wiring, not enabling risk:
  1. `range_filter` -> ARF2/ASB2/ACB1/forex range;
  2. `retest_quality` -> IRV4/support/channel/breakout retests;
  3. `pump_exhaustion` -> pump/spike fade;
  4. `breakout_confirm` -> breakout legs;
  5. `elder_filter` -> optional confluence gate in sweeps.
- Alpaca paper messages are useful telemetry, not live proof:
  `Equities PAPER` / `[DRY-RUN]` means no real broker live money yet.
  Create real Alpaca account + `$500`, then dry-run live account first.

## What changed today

Pushed commits:

- `639339b` — `bot/strategy_breaker.py`, `bot/market_context.py`, ATT1/Alpaca docs.
- `0b67a19` — corrected ATT1 strong short-only + ARS1 additivity research spec.
- `0f7aff0` — wired ATT1 canary breaker into `smart_pump_reversal_bot.py`.
- `c74abad` — isolated ATT1 canary env from other sleeves.
- `93ab864` — added explicit operator live override layer loaded after
  `runtime/strategy_pause.env`.
- `edf5a1d` — operational handoff for the ATT1 canary / Alpaca gate.
- `189b82e` — research-only expansion: `volume_exit`, `carry_neutral`,
  `alt_support_bounce_v2`, `alt_channel_bounce_v1`, `classify_channel` /
  HVN confluence, Alpaca live env template, strategy inventory and rehab docs.

Server deploy status:

- Code through `189b82e` copied to `/root/by-bot` via explicit tar overlay.
  `git pull --ff-only` was intentionally not used because the server worktree is
  dirty with many historical local files/untracked artifacts.
- `bybot.service` restarted with current env only; no ATT1 risk was enabled.
- Server checks passed:
  - `python -m py_compile smart_pump_reversal_bot.py`
  - `pytest tests/test_strategy_pause_contract.py`
- Additional local checks for `189b82e`:
  - `42 passed`: `test_volume_exit`, `test_alt_support_bounce_v2`,
    `test_alt_channel_bounce_v1`, `test_market_context`, `test_carry_neutral`
  - `24 passed`: closed-candle / next-open / strategy catalog focused suite
- Additional server checks for `189b82e`:
  - py_compile for `portfolio_engine.py`, `run_portfolio.py`, `volume_exit.py`,
    `market_context.py`, `carry_neutral.py`, ASB2 and ACB1
  - same 42 focused tests passed on server
- Live heartbeat after restart: `open_trades=0`, `trade_on=true`, `dry_run=false`,
  regime `bear_chop`.
- Latest live heartbeat snapshot after research deploy:
  - service active; `open_trades=0`, `trade_on=true`, `dry_run=false`,
    regime `bear_chop`, `ws_guard_active=0`, messages growing
  - `allocator_hard_block=false`, `allocator_safe_mode=false`
  - `strategy_runtime_config.risk_mult.att1=0.0`, `flat=0.3`,
    `range=0.0`, `breakdown=0.0`, `ivb1=0.0`, `midterm=0.0`
  - operator override disabled/unloaded

## ATT1 short-only canary

Execution-accurate evidence:

- `att1_short_only_exact_local_20260629`: 296 trades, net `+28.17R`, PF `1.402`,
  WR `59.1%`, max DD `6.59`, red months `2`, max red streak `1`.
- Strong bidirectional revalidate r005: 457 trades, net `+37.35R`, PF `1.325`.
- Short side is the main edge; long side is for a later bull-regime package.

Important runtime fact:

- `runtime/strategy_pause.env` currently contains `ATT1_RISK_MULT=0.0` because
  the live-vs-backtest monitor marked old `att1_trendline_touch` performance as
  degraded.
- Therefore the canary must be enabled through the new explicit operator override,
  not by editing/deleting `strategy_pause.env`.

Canary file:

- `configs/att1_short_canary_20260629.env`
- Sets `ENABLE_ATT1_TRADING=1`, `ATT1_RISK_MULT=0.10`, `ATT1_ALLOW_LONGS=0`,
  `ATT1_ALLOW_SHORTS=1`, `MAX_POSITIONS=3`, `ATT1_MAX_OPEN_TRADES=3`.
- Pauses other price sleeves for clean attribution: `FLAT_RISK_MULT=0.0`,
  `RANGE_RISK_MULT=0.0`, `BREAKDOWN_RISK_MULT=0.0`, etc.
- Arms breaker: `ATT1_BREAKER_ENABLE=1`,
  `ATT1_BREAKER_STRATEGY_NAME=att1_trendline_touch`, soft/hard PnL gates,
  consecutive-loss gate, expiry `2026-07-20`.

Dry env simulation on server confirmed:

- without operator override: `ATT1_RISK_MULT=0.0`, `FLAT_RISK_MULT=0.30`;
- with canary override: `ATT1_RISK_MULT=0.10`, `FLAT_RISK_MULT=0.0`,
  breaker enabled.

Live canary status update:

- Enabled on server on 2026-06-29 around `13:17 UTC` after owner OK.
- `.env` backup: `/root/by-bot/runtime/env_backups/.env.pre_att1_canary_20260629_131703`
- Active server-only `.env` lines:
  - `ALLOW_OPERATOR_LIVE_OVERRIDES=1`
  - `OPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env`
- Post-restart heartbeat confirmed:
  - `operator_live_override.loaded=true`
  - `risk_mult.att1=0.10`
  - `risk_mult.flat=0.0`, `range=0.0`, `breakdown=0.0`, `ivb1=0.0`,
    `midterm=0.0`, `bounce1=0.0`
  - `enabled.elder=false`; heartbeat may still show `risk_mult.elder=0.05`
    because one overlay refresh applies an Elder risk floor, but the sleeve is
    disabled and will not trade
  - ATT1 breaker `enabled=true`, `blocked=false`, `expired=false`
  - `open_trades=0`, `trade_on=true`, `dry_run=false`, regime `bear_chop`
- `ATT1_CANARY_EXPIRY_UTC=2026-07-20` is present in the canary env and consumed
  by the ATT1 breaker.

Pre-sleep live check on 2026-06-29 `18:07 UTC`:

- Service still alive: `trade_on=true`, `dry_run=false`, `open_trades=0`,
  regime `bear_chop`, `ws_guard_active=0`.
- Operator override still loaded; active risk remains clean:
  `att1=0.10`; `flat/range/breakdown/ivb1/midterm/bounce1=0.0`.
- ATT1 had no live entry yet. Runtime counters since restart:
  `att1_try=48`, `att1_no_signal=48`, main rejects:
  `trendline=28`, `first_bar=8`, `same_bar=8`, `touch=2`, `reject=2`.
  This is normal waiting behaviour for a strict short trendline sleeve, not a
  freeze.
- ATT1 breaker: `enabled=true`, `blocked=false`, `expired=false`.
- Lightweight monitor `screen overnight_live_watch_20260629` started; it logs
  heartbeat, active risk, ATT1 breaker and runtime counters every 15 minutes to
  `logs/manual_research/overnight_live_watch_20260629.log`.

Morning live check on 2026-06-30 `04:30 UTC`:

- Bot is alive and not blocked: `trade_on=true`, `dry_run=false`,
  `open_trades=0`, `regime=bear_chop`, heartbeat age about 20s,
  `ws_guard_active=0`, Bybit messages growing.
- Operator override still loaded and clean:
  `att1=0.10`; `flat/range/breakdown/ivb1/midterm/bounce1=0.0`.
- ATT1 still has no live entry. Runtime counters since restart:
  `att1_try=126`, `att1_no_signal=126`; main rejects:
  `trendline=97`, `first_bar=8`, `same_bar=8`, `touch=6`, `reject=7`.
  Conclusion: no technical freeze; the strict short trendline canary is simply
  waiting for a valid setup.
- ATT1 breaker: `enabled=true`, `blocked=false`, `expired=false`, old-window
  stats now `trades=4`, `net_pnl=-0.7206`, `winrate=25%`; below `min_trades=6`
  so it does not block.

To enable canary only after owner OK (already done on 2026-06-29; kept for
reference / re-enable after rollback):

```bash
cd /root/by-bot
printf '\nALLOW_OPERATOR_LIVE_OVERRIDES=1\nOPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env\n' >> .env
systemctl restart bybot.service
```

Then confirm in `runtime/bot_heartbeat.json` /
`runtime/runtime_diagnostics.json`:

- `strategy_runtime_config.operator_live_override.loaded=true`;
- `risk_mult.att1=0.10`;
- `risk_mult.flat=0.0`, `risk_mult.range=0.0`, `risk_mult.breakdown=0.0`;
- `strategy_runtime_config.breaker.att1.enabled=true`;
- `open_trades=0` before enabling is preferred.

Rollback:

- remove/comment the two operator override lines from `.env`;
- `systemctl restart bybot.service`.

## Research queue / server

Currently running:

- `screen arf2_structured_20260629`
- spec: `configs/autoresearch/arf2_structured_resistance_fade_20260628.json`
- progress observed on 2026-06-29 12:42 UTC: running r071/192.
- progress observed on 2026-06-29 18:07 UTC: running r118/192 with 46 PASS rows
  and 72 FAIL rows so far.
- r019/r023/r031/r033/r035/r037/r039/r049/r051/r053/r055/r065/r067/r069
  and several others are PASS so far.
  - Examples: r055 net `+6.22`, PF `5.246`, WR `76.9%`, DD `0.90`;
    r067 net `+7.68`, PF `1.874`, WR `58.7%`, DD `2.517`.
- Better non-outlier current candidates include r065/r067/r069/r071/r081/r083/r087:
  roughly `+7R` to `+8.5R`, PF `1.75` to `2.27`, DD about `2R` to `3R`.
  Still require full sweep + monthly/OOS before any canary.
- Do not promote before full sweep + OOS/monthly review. But unlike ARF1 legacy,
  ARF2 has real passing rows and is a live portfolio candidate after validation.

Morning 2026-06-30 status:

- ARF2 sweep completed all `192/192`: `63` PASS rows.
- Best ranked row: r121, 15 trades, net `+6.10R`, PF `5.301`, WR `73.3%`,
  DD `0.8609`, `negative_months=0`, `positive_months=5`.
- Top rows are attractive but low-frequency. Higher-trade rows around 22-24
  trades (for example r113/r115) are also positive but have more red months.
- `screen arf2_oos_20260630` started on 2026-06-30 to replay 8 selected ARF2
  candidates on a fresh 60d OOS window ending 2026-06-30 plus a 360d stability
  window. No live risk is added until this passes.

2026-06-30 `08:15 UTC` update:

- ARF2 OOS safe-subset completed on
  `ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT,SOLUSDT`.
- Fresh 60d OOS was effectively dead: most variants produced `0` trades; r055
  produced `1` trade for `-0.50R`.
- 360d safe-subset:
  - r055: 19 trades, net `+3.90R`, PF `1.944`, DD `1.13`
  - r121: 16 trades, net `+2.91R`, PF `1.912`, DD `1.47`
  - r125: 14 trades, net `+2.16R`, PF `1.799`, DD `0.98`
  - more frequent r065/r067/r069 degraded to PF around `0.98/1.00/0.95` with
    DD `5.5R` to `7R`.
- Verdict: do **not** add ARF2 live risk yet. The attractive 240d sweep did not
  translate into a useful fresh 60d canary and the more frequent variants
  degraded. Keep ARF2 in research; next step is either full data refresh
  including missing ATOM/BTC/XRP slices or redesign the range/fade logic.

Queued after ARF2 completes:

- `screen post_arf2_queue_20260629`
- It waits with `pgrep -f "[a]rf2_structured_resistance_fade_20260628.json"` so it
  does not match itself.
- Then runs:
  1. `inplay_retest_v3` 240d baseline `irv3_base_240_20260629`
  2. `inplay_retest_v3` 240d with `VOLUME_EXIT_ENABLE=1`
     `irv3_vol_240_20260629`
  3. ASB2 240d `asb2_240_20260629`
  4. ACB1 240d `acb1_240_20260629`

Queued after the crypto queue, to avoid overloading the 1GB live VPS:

- `screen fx_after_crypto_queue_20260629`
- It waits for both `arf2_structured_20260629` and
  `post_arf2_queue_20260629` to finish.
- Then runs free-data FX research, no OANDA keys required for backtest:
  - majors/crosses overnight research:
    `EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY`
  - metals scout:
    `XAUUSD,XAGUSD` with trend-retest, range-bounce, breakout-continuation and
    liquidity-sweep strategies.
- Caveat: OANDA keys are only needed later for demo/live execution. Metals
  results are scout-only until the spread/pip/swap model is made instrument
  specific.

Corrected ATT1+ARS1 package:

- `configs/autoresearch/package_att1_strong_short_ars1_additivity_20260629.json`
- It replaces the invalid old `package_att1_short_ars1_additivity_20260628`,
  whose control rows used a weak ATT1 baseline.
- Let ARF2 finish or pause it before launching this on the 1GB VPS.
- Manual aggregation of the old `package_att1_short_ars1_additivity_20260628`
  portfolio runs showed ARS1 is not additive in the current package:
  best observed rows around 404 trades, net `+9.07R`, PF `1.12`, DD `6.79`,
  which is materially worse than ATT1 short-only (`+28.17R`, PF `1.40`).
  Keep ARS1 research-only until repaired.

SpikeFadeV3:

- `spike_fade_v3_link_short_bounded_20260627` best r008:
  32 trades, net `+5.10`, PF `1.987`, WR `59.4%`, DD `1.27`.
- Candidate/diversifier only; low frequency, not first engine.

New ASB2/ACB1 / volume-density work:

- `strategies/alt_support_bounce_v2.py`: long-only support bounce on shared
  market context; horizontal support + lower channel line; optional HVN gate.
- `strategies/alt_channel_bounce_v1.py`: two-sided channel bounce; flat,
  ascending and descending channels; optional HVN gate.
- `bot/market_context.py`: added `classify_channel()` and `nearest_dist_atr()`.
- Smoke on local and server, 30d LINK/SOL:
  - ASB2: 7 trades, net `+0.76`, PF `2.155`, WR `71.4%`, DD `0.4076`
  - ACB1: 4 trades, net `+0.05`, PF `1.086`, WR `50%`, DD `0.4144`
- This only proves wiring and early signal sanity; 240d queued after ARF2.

Volume exit:

- `bot/volume_exit.py` wired into `backtest/portfolio_engine.py`, default off.
- Flag: `VOLUME_EXIT_ENABLE=1`; strategy filter:
  `VOLUME_EXIT_STRATEGIES=inplay`.
- It exits the remaining runner with reason `VOL_FADE` when a real volume impulse
  fades and price stalls.
- 240d IRV3 base-vs-volume comparison is queued after ARF2.

InPlay repair overnight result:

- `backtest_runs/autoresearch_20260629_231010_inplay_dd_repair_20260627`
- Only one PASS out of 24: r010, 102 trades, net `+4.36R`, PF `1.308`,
  WR `39.2%`, DD `2.2704`, red months `2`, max red streak `1`.
- This is a watchlist/research improvement, not a canary-quality engine yet.

InPlay volume-exit comparison (server, 2026-06-30):

- Baseline `irv3_base_240_20260630`: 210 trades, net `-4.31R`, PF `0.868`,
  WR `26.7%`, DD `6.47`.
- Volume exit `irv3_vol_240_20260630`: 232 trades, net `-8.00R`, PF `0.701`,
  WR `30.2%`, DD `8.68`.
- Verdict: current `volume_exit` wiring does not fix IRV3; it worsens the tested
  portfolio. Keep off by default, use only for further research.

ASB2/ACB1 240d queue:

- `screen post_oos_repair_queue_20260630` is running. It completed InPlay base
  vs volume and is now running ASB2/ACB1 240d default/HVN tests.

Stopped stale research:

- Killed old `package_att1_short_ars1_additivity_20260628` autoresearch on
  2026-06-30 because it was already no-go and was consuming live VPS RAM/CPU.

SpikeFadeV3 overnight recheck:

- `backtest_runs/autoresearch_20260629_230022_spike_fade_v3_link_short_bounded_20260627`
- 3 PASS out of 32. Best remains r008: 32 trades, net `+5.10R`, PF `1.987`,
  WR `59.4%`, DD `1.2715`, red months `2`, max red streak `1`.
- Candidate for a small diversifier after ATT1/ARF2, not a primary engine.

Funding/carry:

- Raw cross-exchange scan:
  `scripts/cross_exchange_funding_scan.py --min-spread-apr-pct 10 --top 30`
  saved `runtime/arb/cross_exchange_funding_latest.json`.
- Validator:
  `scripts/cross_exchange_funding_validate.py --in-json runtime/arb/cross_exchange_funding_latest.json --top 30 --out-json runtime/arb/cross_exchange_funding_validated_20260629.json --out-top 30 --notional-usd 20 --min-spread-apr-pct 10 --keep-failed`
- Validated PASS examples:
  - `GWEIUSDT:binance->bybit`: net_hold `0.5071%`, spread/month `22.72%`,
    entry basis `0.4998%`, persistence `2`
  - `SLXUSDT:binance->bybit`: net_hold `0.3592%`, spread/month `18.225%`,
    entry basis `0.358%`, persistence `3`
  - `TACUSDT`, `MANTAUSDT`, `SKHYNIXUSDT`, `MAGICUSDT`, `VELVETUSDT` also passed
    at smaller expected net.
- Historical funding capture on validated-ish symbols:
  `backtest_runs/funding_20260629_123907_funding_spike_scan_20260629`
  - 90d, $20/symbol, net `+$8.85`, PF `999`, WR `91.8%`, DD `0`
  - but concentration is high: top symbol share `57.35%` (ESPORTSUSDT).
  - Treat as carry/shadow candidate only; requires hedge/balance/orderbook
    execution validation before any capital.

## Forex / metals overnight research

Completed after crypto queue on 2026-06-29/30:

- Fast FX scout produced many pass rows, then full confirm narrowed to 3 CANARY
  combos:
  - `GBPJPY trend_retest_session_v1:conservative`: stress `+212.17` pips,
    recent stress `+48.43` pips, 84 trades, stress DD `289.62` pips.
  - `GBPUSD trend_retest_session_v1:eurusd_canary`: stress `+74.68` pips,
    recent stress `+129.00` pips, 106 trades, stress DD `107.79` pips.
  - `GBPUSD trend_retest_session_v1:active`: stress `+11.54` pips,
    recent stress `+87.42` pips, 142 trades, stress DD `162.81` pips.
- State files:
  - `docs/forex_combo_state_latest.csv`
  - `docs/forex_live_filter_latest.csv`
- The exporter marks these as CANARY, not ACTIVE. Estimated stress returns in
  the full confirm are negative, so this is not ready for money; it needs demo
  execution/cost-model work.
- Metals scout `XAUUSD/XAGUSD`: 0 pair+strategy passed current gate.

Next FX queue:

- `screen fx_deep_after_crypto_20260630` started on 2026-06-30.
- It waits for `post_oos_repair_queue_20260630`, then runs a stricter FX gate
  with positive stress-return requirements and a separate strict metals gate.
- Crypto strategies are not being ported into FX; this uses the isolated
  `forex/` strategy set.

## Alpaca

Status:

- Candidate remains monthly v38 hybrid top4.
- Evidence in `reports/ALPACA_500_LIVE_GO_NOGO_2026_06_29.md`: about `22–23%`
  annualized in research, small sample, suitable for a $500 pipeline canary.
- Server has paper configs only. No committed live profile was found, which is
  correct for secrets.
- Latest monthly refresh files are from `2026-06-26T12:32:15Z`; daily refresh cron
  is scheduled at `12:30 UTC` Mon–Fri.
- US market open on 2026-06-29 is `13:30 UTC` / `16:30 Asia/Nicosia`.

For live $500:

1. Owner must create server-only `configs/alpaca_live_v38.env` with real keys.
2. First run must be `ALPACA_SEND_ORDERS=0` dry-run against the live account.
3. Guard self-test should fail closed if confirm vars are missing.
4. Only after owner confirms real account/buying power/open orders, set
   `ALPACA_SEND_ORDERS=1` after market open.

Do not place Alpaca live orders from Codex without explicit owner confirmation.

## Next practical steps

1. Ask owner for explicit OK before enabling ATT1 crypto canary.
2. If OK: apply operator override, restart, verify heartbeat, then monitor signals
   and first closes.
3. At/after `12:30 UTC`, verify Alpaca daily refresh; after `13:30 UTC`, run live
   dry-run if owner supplied real env.
4. Continue ARF2 research; if no PASS after full sweep, keep ARF2 research-only and
   launch corrected ATT1+ARS1 additivity.
5. When ARF2 finishes, read `post_arf2_queue_20260629` results and send Claude:
   IRV3 base/vol summaries, ASB2/ACB1 240d summaries, and ARF2 ranked/top rows.
6. Build owner volume-inflow layer from `reports/OWNER_STRATEGY_SPEC_2026_06_25.md`.
