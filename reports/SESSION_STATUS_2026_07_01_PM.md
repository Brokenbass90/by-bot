# Session status — 2026-07-01 PM

## 1. Proof-of-life / Telegram stale snapshot

Root cause confirmed.

`scripts/proof_of_life.py` decided whether to refresh `reports/SERVER_SNAPSHOT_latest.json`
using only:

- `runtime/bot_heartbeat.json`

But the local/live mirror contains the fresh heartbeat at:

- `runtime/live_mirror/bot_heartbeat.json`
- `runtime/live_mirror/operator/operator_snapshot.json`

So proof-of-life could fall back to the stale committed snapshot from June and
show `bull_trend / flat / ivb1`, while current live state is `bear_chop` and
only `ATT1 x0.10` has live risk.

Fix implemented:

- `proof_of_life.py` now checks all runtime/live_mirror heartbeat/operator paths
  and refreshes when any is newer than `SERVER_SNAPSHOT_latest`.
- If latest snapshot is absent, proof-of-life attempts runtime refresh before
  failing.
- Generated `reports/PROOF_OF_LIFE_*.txt` and `reports/SERVER_SNAPSHOT_latest.*`
  are ignored and removed from tracked git index, so they do not become stale
  committed truth again.

Verification after fix:

- `STATUS: ALIVE`
- `regime=bear_chop`
- `dry_run=False`
- `open_trades=0`
- `LIVE (risk>0): att1 x0.1`
- shadow: `bounce1, flat, ivb1, midterm, range`

## 2. InPlay V4 mechanics gate result

Run:

- `reports/research/irv4_mechanics_gate_ada_doge_sui_20260701_20260701_093536/summary.md`

Verdict: `FAIL`, but informative.

- OOS folds: `4`
- OOS trades: `21`
- OOS net: `+0.87R`
- Reason: `unstable_frac_pos_0.50`
- Fold rows:
  - fold 1: `9 trades`, `+0.62R`, PF `1.620`
  - fold 2: `6 trades`, `+0.54R`, PF `2.009`
  - fold 3: `1 trade`, `-0.26R`, PF `0.000`
  - fold 4: `5 trades`, `-0.03R`, PF `0.947`

Interpretation:

- New mechanics improved the old late-entry problem.
- This is not canary-grade because only 2/4 OOS folds are profitable.
- The edge is not dead; it is unstable/thin.
- Next: full-grid check on the same universe, then regime/month/symbol diagnostics.

## 3. SpikeFadeV3 robust gate

Run:

- `reports/research/sfv3_robust_gate_20260701_v2_20260701_073903/summary.md`

Verdict: `FAIL`.

- OOS trades: `29`
- OOS net: `+0.93R`
- PF: `1.144`
- Fail: weak net/PF, one bad fold, fee-stress failure.

Action: do not canary SpikeFadeV3 LINK short. Keep research-only.

## 4. Liquidation/cascade status

Local real-data H4 test is blocked:

- missing `runtime/liquidations/bybit_liquidations.jsonl`
- missing full per-symbol OI/funding time series for H4 stack

Existing local/proxy runner:

- `backtest/liquidation_sweep_run.py`

Proxy mid-cap run on `SOL,DOGE,AVAX,LINK,ADA`:

- mode: price/volume proxy, not real liquidation data
- clusters: `596`
- trades: `596`
- win: `44.0%`
- expectancy: `-0.62R`
- PF: `0.26`

Interpretation:

- “Just fade sharp price/volume spikes” is bad.
- H4 hypothesis is still untested because it requires real liquidation + OI flush + funding extreme.
- Server/research-host task: collect/export real `bybit_liquidations.jsonl` + OI/funding series and run H4 gate on mid-caps.

## 5. Next running research

Started/queued after this report:

- full-grid InPlay V4 mechanics gate on `ADA,DOGE,SUI`;
- objective: check whether the 12-combo gate was too narrow.

This is still research-only. Live crypto remains ATT1 short-only canary.

## 6. Files to send to DeepSeek/Claude for external review

Primary:

- `scripts/inplay_v4_mechanics_gate.py`
- `strategies/inplay_retest_v4.py`
- `backtest/portfolio_engine.py`
- `reports/MECHANICS_WIRING_STATUS_2026_07_01.md`
- `reports/research/irv4_mechanics_gate_ada_doge_sui_20260701_20260701_093536/summary.md`
- `reports/research/irv4_mechanics_gate_ada_doge_sui_20260701_20260701_093536/runs.csv`

H4/cascade:

- `bot/cascade_reversal.py`
- `backtest/liquidation_sweep_run.py`
- `backtest/liquidation_sweep_research.py`
- `runtime/liquidation_sweep_run_latest.json`

Operational:

- `scripts/proof_of_life.py`
- `scripts/export_server_snapshot.py`
