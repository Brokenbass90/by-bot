# Execution Checkpoint — 2026-07-10 Evening

## Outcome first

- Web login recovered on VPS. Root cause was an empty server user map, not a wrong UI password.
- Alpaca real account placed into safe-hold: protect current positions, block new entries and daily/stale/midmonth rotation.
- ATT1 remains unchanged in live. Its historical base is coherent, but the proposed simple slope/RSI filter failed the exact rerun requirement.
- The first repaired crypto candidate is a short-only horizontal resistance sweep/fade. It passed exploration narrowly but failed the strict cost/concentration gate, so it is not shadow/canary-ready.
- Long-only support reclaim and both strict Elder variants failed this wave.
- Git and live safety changes were separated. No new Bybit money sleeve or risk increase occurred.

## Web P0

Server `configs/web_config.json` contained zero users. Restored the existing password/TOTP record, set permissions to `600`, restarted `trading-journal-web`, and verified:

- service: `active`;
- `/ping`: `{"pong":true}`;
- configured users: `1`.

Normal deploy now preserves the instance-owned auth file. It uploads auth state only with explicit `DEPLOY_WEB_AUTH_CONFIG=1`.

## Alpaca audit and containment

Direct broker fills showed that nominal monthly v38 was actually rotating daily:

- 7 closed roundtrips in 3 trading days;
- 2 wins / 5 losses;
- realized about `-$5.716`;
- gross PF about `0.44`.

This cannot be compared honestly with the research artifact that produced about 15 OOS trades per year.

Safe-hold now enforces:

- `ALPACA_ALLOW_NEW_ENTRIES=0`;
- `ALPACA_CLOSE_STALE_POSITIONS=0`;
- `MONTHLY_MIDMONTH_ROTATION=0`;
- daily v38 refresh cron disabled with backup;
- stop/trail exits create an immediate re-entry block before the buy loop.

Dry-run after deploy saw `ABBV,ABNB,GE,SCHW`, broker stop coverage `4/4`, no new buys or rotation actions.

Intraday v1/v3 operational fixes are deployed only to paper/shadow. The old v1 equity/PnL history is `DATA_INVALID`: one AAPL fill near `+$1.21` was recorded repeatedly, creating roughly `+$442` of false PnL. It must be reconstructed from broker fills before curve gates are trusted.

The refresh research runner also had a cardinality mismatch: its simulator was hard-coded to `top_n=3` while the v38 live config advertised four positions. The runner now accepts `EQ_V36_SIM_TOP_N`, v38 explicitly sets it to `4`, and research-only mode can use the existing cache without fetching data or publishing live picks.

Cache-only A/B on the documented 2024-05..2026-04 window reproduced both cardinalities:

- top3 control: 28 trades, PF `7.326`, compounded `+53.28%`, max monthly DD `-3.86%`;
- top4 live-cardinality: 33 trades, PF `6.744`, compounded `+50.75%`, max monthly DD `-3.86%`.

This confirms the old top4 headline is reproducible. It does not make it fresh OOS. The local cache stops at `2026-04-27`, so the frozen May-June pulse had no data. The VPS mirror has a newer top3 report through `2026-07-08` (`30` trades, PF `6.467`, compounded `+63.06%`), but that is still cardinality-mismatched with four live slots. A separate isolated-cache refresh script is ready; execution was blocked by the current environment's external-network/usage limit, not by strategy code.

Intraday PnL idempotency is implemented and tested locally: confirmed exits use durable broker order IDs, atomic ledger-first writes, duplicate recovery and fail-closed conflict detection. It is intentionally not deployed until the corrupted historical log is backed up and reconstructed from broker fills, because first-run baseline migration must not preserve the false `+$442`.

## ATT1 verdict

Historical base, exact 4 x 90d folds:

- 379 trades;
- PF `1.277`;
- WR `57.9%`;
- 4/4 positive folds;
- net `+18.78` portfolio PnL units in the runner.

Post-filtering the base cohort suggested descending slope plus RSI 50..70, but that was not executable proof. The mandatory full rerun, which changes cooldown and available portfolio slots, produced:

- 231 trades;
- PF `1.327`;
- WR `57.7%`;
- 3/4 positive folds;
- net `+13.35`.

Verdict: reject live change. It slightly raises PF, does not raise win rate, cuts frequency/net and loses one fold. Next ATT1 work needs richer entry cards and causal universe expansion, not another simple threshold.

## Repaired level-memory wave

All rows used 8 symbols, 180 days ending 2026-04-30, fixed lookback/respect/RR, 960 H1 memory warmup, full M5-derived H1 cache, corrected support/resistance approach semantics and no parameter grid.

| Arm | Elder | Trades | Net R | PF | WR | Folds+ | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| resistance sweep/fade short | off | 42 | +4.05 | 1.200 | 54.8% | 3/4 | PASS_EXPLORATION |
| resistance sweep/fade short | permissive | 28 | +2.04 | 1.149 | 53.6% | 3/4 | FAIL |
| resistance sweep/fade short | strict | 0 | 0 | 0 | — | 0/4 | FAIL |
| support sweep/reclaim long | off | 38 | -2.87 | 0.871 | 44.7% | 1/4 | FAIL |
| support sweep/reclaim long | permissive | 20 | -3.32 | 0.735 | 40.0% | 1/4 | FAIL |
| support sweep/reclaim long | strict | 0 | 0 | 0 | — | 0/4 | FAIL |

Elder did not help. Keep it out of this arm unless a future identical-signal A/B proves otherwise.

The short arm may proceed only to strict validation:

1. base and stress costs;
2. purged chronological folds;
3. unseen symbol/period holdout;
4. concentration limits;
5. H1 signal to M5 maker-fill replay;
6. shadow/risk=0 only after PASS.

Strict validation is now complete. The temporal selector passed (`33` test trades, `+5.411R`, 7/11 positive windows), and the unseen eight-symbol holdout was encouraging (`33` trades, `+14.106R`, PF `2.295`, WR `69.7%`, 75% positive symbols). However, the frozen base row failed the binding gates:

- stressed costs reduced PF from `1.200` to `1.003`;
- the top symbol supplied `38.0%` of positive PnL versus the `<35%` limit;
- one of four chronological folds remained negative.

Final verdict: `NO_PROMOTION`. Do not run the M5 execution/shadow gate yet. First diagnose fee sensitivity and symbol concentration without reopening a parameter grid.

## Inplay and pump fade

The idea remains valid as a research direction: event expansion can be a long/momentum arm, while exhaustion/failure can be a bear/pump-unwind short arm. The current inplay maker implementation is not promotable: latest stress result was PF `1.173`, 2/4 folds, below preregistration. Do not rerun the same grid. Next version should be event-first and combine relative-volume/expansion, real horizontal/sloped structure, level-memory failure/reclaim, regime-specific side separation and maker-fill execution.

## Alpaca upside path

There is room to improve, but the published backtest is selected research rather than a pristine untouched holdout. Priority is not adding more indicators. It is restoring exact parity and then comparing:

1. fixed true-monthly picks;
2. the accidental daily-rotation policy;
3. adaptive paper;
4. the same costs, fill-derived stops, turnover penalty, sector/beta concentration, bear-2022 and a new untouched period.

AI belongs in anomaly detection, regime/portfolio meta-control and research triage; it should not override broker risk or invent discretionary entries.

## Operations and Git

- Useless duplicate VPS liquidity-sweep grid was removed from the active slot; both automatic research queues are temporarily disabled with backups.
- Full fast suite: `897 passed`.
- Git pushed:
  - `07b0bdd` — web auth preservation + Alpaca safe-hold;
  - `0e7eb73` — ATT1/level-memory research repair.
  - `23f9446` — idempotent Alpaca accounting, explicit v38 parity, strict LM/ATT1 research gates.
- No new Bybit live sleeve, no live risk increase, no automatic promotion.
- ATT1 behavior-neutral entry cards completed on four newer 90-day windows through 2026-07-10. The base weakened to `346` trades, PF `1.205`, WR `56.3%`, `3/4`, net `+12.98`. A full executable `R² >= 0.80` challenger produced `264` trades, PF `1.285`, WR `57.6%`, `4/4`, net `+13.41`, with lower worst drawdown. It improves quality but reduces frequency about `24%`. Higher-cost stress then failed: `263` trades, PF `1.078`, only `1/4` positive folds and the latest fold negative. Verdict: no live/shadow promotion; measure actual execution and test maker/retest fills plus a genuinely fresh holdout.

## Next checkpoint

Return after `2-4 hours` for the Alpaca idempotent-ledger/parity result, or next morning for the consolidated work package. Stable income still cannot be promised by date; the fastest defensible route is one proven short crypto arm plus repaired Alpaca execution, not more live sleeves at once.
