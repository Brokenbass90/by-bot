# CODEX HANDOFF — 2026-06-20

Technical continuation point for Bybit crypto, Alpaca paper, validation, and
runtime safety. Read `PROJECT_MAP.md` first, then this file. Do not treat old
research headlines as current evidence without reproducing them.

## 1. Repository safety

- Branch: `codex/dynamic-symbol-filters`.
- The worktree contains many unrelated/untracked historical files. Stage only
  explicit paths; never use `git add .`.
- `configs/web_config.json` and live env files can contain secrets and must not
  be committed.
- Upstream commits reviewed in this session:
  - `5835dca` — ARS1 ADX repair;
  - `72600ca` — crypto promotion evidence gate;
  - `4aba49f` — per-symbol liquidation research;
  - `fd4dee4` — project map refresh.
- This session commit `a2a00fc` contains the canonical ADX correction, its
  numerical regression test, the refreshed project map and this handoff; it is
  pushed to `origin/codex/dynamic-symbol-filters`.

## 2. Verified live state

Read-only server check on 2026-06-20:

- `bybot.service`: active;
- `trade_on=true`, `dry_run=false`, `open_trades=0`;
- regime: `bear_chop`;
- Bybit message counter was increasing (`3,017,075` at inspection);
- live risk: `flat_resistance_fade=0.30x`, legacy Range short-only `0.25x`;
- ATT1, bounce, breakdown, IVB1 and midterm are enabled for scan/shadow but
  have `risk_mult=0.0`;
- Elder, ASB1 slope-break and HZBO1 are disabled for entry risk.

Available live evidence remains 40 closed trades, approximately `-3.81 USDT`,
PF `0.517`. There is no proven live edge to scale yet.

## 3. Review findings from the 2026-06-19 commits

### ARS1 ADX

`5835dca` fixed the original catastrophic ADX≈100 defect, but still averaged
the last DX values instead of applying Wilder's recursive smoothing to ADX.
Against a canonical reference on 200 deterministic random series, mean absolute
difference was about `4.70` ADX points and maximum difference `21.12` points.

Local correction in this session:

- `strategies/alt_range_scalp_v1.py` now uses Wilder smoothing for TR, DM and
  ADX;
- `tests/test_alt_range_scalp_adx.py` contains a fixed numerical reference;
- the old positive ARS1 r004 used `ARS1_MAX_ADX=0` and is unaffected by this
  particular bug;
- the 64-run `range_scalp_v1_regime_repair_v1` matrix used ADX thresholds and
  must be rerun after deploying the canonical correction.

The corrected strategy module was copied to `/root/by-bot` without restarting
`bybot.service`; backup:
`runtime/alt_range_scalp_v1.py.pre_wilder_20260620.bak`.
Server screen `ars1_wilder_recheck_20260620` is queued behind the already
running ASB1 autoresearch process and will start the compact 64-run matrix when
that process exits. Log: `logs/ars1_wilder_recheck_20260620.log`.

### Promotion gate

The new gate correctly checks candidate next-open metadata, minimum costs,
monthly stability and WF summary fields. It is not yet sufficient for automatic
promotion:

- it does not bind the WF file to the same strategy, parameters, symbols, dates
  and candidate summary;
- it can compare a standalone sleeve against a historical full-stack summary;
- it does not require equal windows/universes or a freshly reproduced baseline;
- the default golden summary has no next-open/cost metadata and is known not to
  reproduce under the later exact-cache regression;
- the CLI exits `0` even when `promotion_passed=false`.

Until those contracts are fail-closed, treat evaluator output as a report, not
an automated deployment authorization.

### Live/backtest candle parity

`backtest.engine.KlineStore` returns completed candles only. The shared live
`fetch_klines()` returns Bybit's current incomplete final candle. `_IVB1Store`
and `_ElderStore` pass it through directly, while their strategy code consumes
`rows[-1]`. This means live/shadow timing can differ from next-open research.
The repository already has `strategies.live_kline_utils.fetch_closed_klines`;
wire it into the live adapters and add parity tests before either strategy gets
non-zero risk. ARS1 needs the same closed-candle adapter when wired live.

### Project map and tests

- `PROJECT_MAP.md` again names both `backtest/promotion_gate` and
  `scripts/evaluate_crypto_promotion.py`.
- Full local suite after the local fixes: `410 passed`.

## 4. Completed server research

### ARS1 — Bollinger/RSI range scalp

Canonical trader name: range mean-reversion / trading both edges of a range.

- Prior next-open r004, with ADX disabled: 108 trades, `+16.61%`, PF `1.682`,
  DD `6.68%`, costs `6 bps fee + 2 bps slippage per side`.
- It failed monthly stability: October and November 2025 were red; both long
  and short lost in October.
- Its previous stack comparison reduced PF from `1.68` bare to about `1.46`
  stacked. The control plane therefore affected the result negatively in that
  simulation.
- The ADX-threshold repair matrix completed 64/64 with zero passes. Its best
  rows had positive PF but insufficient net/trades and unstable months. Because
  the ADX implementation was still non-canonical, rerun this compact matrix
  after the local ADX correction; do not rerun the old 15k grid.

ARS1 diversification is not established. It cannot be added arithmetically to
the historical `+89%/+120%` package. Required evidence is a fresh current-code
baseline and an apples-to-apples `baseline + ARS1` portfolio run with shared
capital, slot limits, costs and aligned monthly PnL.

### IVB1 — impulse breakout with pullback

The 8-run next-open server recheck completed:

- net range: `+11.30…+15.23%`;
- PF range: `1.213…1.250`;
- win rate: about `54.1…54.7%`;
- DD range: `8.35…10.13%`;
- all eight failed only the current `DD <= 8%` constraint.

Best result was r005: 6-symbol universe, `+15.23%`, PF `1.250`, WR `54.7%`,
DD `8.46%`. This is a near-candidate, not a live approval. Next evidence:
monthly table, multi-window WF, lower-risk portfolio replay, true full-stack
comparison, closed-candle live parity, then shadow execution.

### ASB1 support bounce

`asb1_bull_chop_repair_v1` was still running on the server at r045 during the
check. Completed rows were all FAIL. Some pockets were mildly positive but PF,
DD, net and monthly stability remained below gate requirements. Let the bounded
queue finish; do not expand its grid without a distinct entry hypothesis.

### Liquidations

- Collector is active in screen `bybit_liquidations_collector_20260616`.
- File contained `13,442` events at inspection.
- Research now separates clusters and price bars by symbol.
- Independent review still needs to verify event timestamp semantics, candle
  alignment, post-event entry timing and the exact fee/slippage model.

## 5. Historical baseline warning

The old golden package summary at about `+89.65%`, PF `2.121`, DD `2.88%` is a
historical artifact, not a current reproducible baseline. Project history records
an exact-cache rerun at about `+11.24%`, PF `1.148`, DD `8.77%`, with breakdown
and old in-play sleeves causing most of the collapse. Never use the old headline
to project combined annual returns or to approve new risk. Reconstruct a fresh
baseline from current code and execution assumptions first.

## 6. Elder status and audit scope

Source: `strategies/elder_triple_screen_v2.py`.

- 541 completed variants all failed;
- PF was roughly `0.57…0.84`, with very large losses/DD and thousands of trades
  in many variants;
- parameter tuning is stopped; this is a design/parity review.

Audit these contracts before a v3 rewrite:

1. completed-candle parity across 4h/1h/15m in live and backtest;
2. Screen 3 semantics: actual stop-entry trigger versus close-confirmed signal
   followed by next-open fill;
3. separate long and short trend/wave thresholds;
4. per-symbol/day frequency and timestamp-based cooldown;
5. realistic order type, costs, TP1/breakeven/runner behavior;
6. side/symbol/month attribution before any new optimization grid.

## 7. Alpaca adaptive paper

`alpaca_adaptive_v1` baseline is the current order-driving paper manager, not
v38. Server cron refreshes selection daily and manages it every 30 minutes.
The lively preset remains no-order shadow.

Read-only broker check on 2026-06-20 found:

- AAPL: market value about `$261.44`, unrealized `+$0.32`;
- JPM: market value about `$251.75`, unrealized `-$2.58`;
- UNH: market value about `$182.90`, unrealized `-$0.52`;
- broker stop orders existed for all three positions in the manager log;
- adaptive paper capital model is `$1,000`, target allocation `70%`.

The first formal review remains after the US close on 2026-06-26. It is a gate,
not an automatic transfer date: verify ownership, fills, no duplicate orders,
all broker stops, realized/unrealized PnL and software trailing behavior before
considering the first real `$500`.

## 8. Continuation order

1. Poll `asb1_bull_chop_repair_v1`, then
   `ars1_wilder_recheck_20260620`; the canonical ADX module is already deployed
   and the compact 64-combination rerun is queued.
2. Fix completed-candle live adapters for IVB1/Elder/ARS1 and add live-vs-
   backtest decision parity tests.
3. Harden promotion evidence provenance and require a fresh matching combined
   portfolio summary; make machine mode fail with a non-zero exit code.
4. Rebuild the current reproducible baseline, then run baseline+IVB1 and
   baseline+ARS1 on the same data/cost/control-plane contract.
5. Finish bounded ASB1 research and publish monthly/side/symbol attribution.
6. Review Alpaca adaptive after 2026-06-26; keep real capital out until that
   execution review is complete.
