# Breakout bridge V2 — orders-OFF engineering delivery

**BRIDGE_V2_ENGINEERING_PASS**. Claude's reported source-scope defect is
reproduced and corrected in a separate local V2. The Mac shadow has **not** been
updated, rebridged, started or restarted. No broker/live integration or edge verdict.

The latest Brain A5/A6 work is already complete/spent, contrary to the forwarded
summary's future tense: its single filter terminated BLOCKED_DATA because the
SF3 GRASS notional/cost contract made capital nonpositive. Read
`BRAIN_V2_A5_A6_SINGLE_FILTER_2026_10_12.md`; no additional Brain attempt occurred.

## Defect and correction

V1 line464 compares `provenance.output_sha256` (the complete HTF aggregation)
with `level.source_bars_sha256` (the selected lookback window). The level builder
correctly hashes only that window. The hashes differ when the aggregate is longer;
the original short synthetic fixture never reached this condition.

The MTF config uses **120** lookback bars; standalone LevelSnapshot defaults to
240. No configuration was changed. A 300-hour synthetic fixture reproduced the
V1 failure, followed by GREEN using V2. Original V1, MTF, levels, aggregation,
market-context and execution simulator files remain byte-identical.

New API:

```python
from bot.event_long_mtf_execution_bridge_v2 import bridge_mtf_research_plan_v2

result = bridge_mtf_research_plan_v2(
    plan, persisted_state, raw_closed_m5=exact_saved_decision_prefix,
)
```

V2 retains the original nested identity/outbox/time/risk/research-only validators.
It requires the exact saved raw M5 source at the persisted plan boundary, then:

1. Verifies full raw prefix hash/count/start/grid/end against persisted state.
2. Reconstructs and matches the complete level aggregation provenance.
3. Selects only the recorded level window, verifying its start/end/count/hash.
4. Independently matches original event H1 and plan M15 aggregates to that source.
5. Binds full aggregate and window hashes/spans in a distinct V2 receipt/schema.

The entry reference, stop, timing, signal, universe, risk/config and economics
remain unchanged. V2 receipt and execution-plan IDs change because the evidence
schema changes; the **original MTF plan IDs remain identical**. The function is
pure: no state mutation/acknowledgement, source fetching, sizing or orders.

## Measured validation

**96 targeted local tests PASS**: 14 V2 tests plus 82 preserved bridge/aggregation/
level/MTF/state-store/execution tests. Covered: long and short source histories,
H4 window component, exact restart receipts, independently corrupted window/full
hashes, data edits inside/outside lookback, missing/future/truncated rows, acknowledged
outbox and unchanged synthetic entry/stop/fee/slippage/exit economics.

Command:

```bash
.venv/bin/python -m pytest -q tests/test_event_long_mtf_execution_bridge_v2.py tests/test_event_long_mtf_execution_bridge_v1.py tests/test_level_snapshot_v1.py tests/test_closed_bar_aggregation_v1.py tests/test_event_expansion_retest_long_mtf_v1.py tests/test_event_expansion_retest_long_mtf_state_store.py tests/test_event_long_execution_v1.py
```

Bounded **source/bridge-only** AVAX replay on already parity-consumed
BREAKOUT_M5_V2 `[2026-08-12, 2026-10-11)`:

| MTF plan | Known at UTC | V1 | V2 |
|---|---|---|---|
| `2834ab795c880c1c1360763b88bc8570` | 2026-09-03 13:00 | source-scope BLOCKED | PASS |
| `332876cdcce3c9033df3d070cf3a1d83` | 2026-09-18 10:30 | source-scope BLOCKED | PASS |

Ordered plan-ID hash **8f4d220a69c5dd0950fc4fc055e2d67cdfdce97c40a6f3195b3f81f67948d425**
exactly matches Claude's preserved parity report. Both V2 results are exact after
state deserialization. Three AVAX month-file decoded hashes match the immutable
manifest. The fixture retains **10,782 M5 rows**, ending at the second decision;
each case supplies only its own prefix, with no future tail passed to the bridge.

Initial source loader rejected seven-column venue rows before strategy execution.
It was corrected to the **existing published six-column OHLCV projection** (the
seventh field is turnover). No source repinning/strategy repair or outcome retry.
The successful replay performs zero outcome simulations/judges. Only synthetic
execution prices are used in execution-parity tests.

Evidence: `reports/evidence/breakout_bridge_v2_20261012/` contains source replay,
two original `state_pri_plane` envelopes, V2 results, bounded raw-prefix fixture,
source hashes, external Claude plan parity and validation receipt. Core sources
match local research ref **e22c0e0b4837b9dbfea89fb6ea72baa1a510f5d7**; actual research
origin at intake was still **e2d668ce415c82c1c22c44454df84e168a8c5f7d**. The new local
Claude artifacts were read from their immutable ref, not silently merged/pushed.
Root bounded review checked V1→V2 diff and exact source bindings. Prior independent
reviewer quota failure was not retried/replaced; no independent financial signoff.
Full-suite historically NOT_GREEN and not rerun; no VPS/broker check in this cycle.

## Minimal handoff to Claude

Consume the reviewed V2 and its tests after this recovery commit is published.
Do not merely delete the V1 comparison, replace its SHA silently, or claim his
unchanged `--perebridge` now uses V2: it still imports V1 and passes no raw prefix.
Use an explicitly versioned adapter/source migration receipt before rebridging:

```python
# Existing epoch/cache source starts at state.source_start_open_ts_ms.
prefix = exact_epoch_m5_rows[:state.source_count]
result = bridge_mtf_research_plan_v2(plan, state, raw_closed_m5=prefix)
# Persist receipt + frozen_plan together, retaining original MTF plan_id,
# old bridge-error record and all original epoch/source/config identities.
```

For saved plans use the exact `state_pri_plane` and the original epoch M5 prefix;
missing/mutated source remains BLOCKED. Do not rescan signals or recreate levels
from later prices to make an old plan valid. Keep original sealed manifests and
code identities; record V2 implementation pins and transition separately. The
existing observer's source advancement/outbox handoff remains its owner's scope.
No duplicate terminal outcomes or silent overwrite of old plan/receipt history.

This closes the **specific bridge engineering defect**. Actual running-shadow
source identity, causal fill/funding/finality and sufficient prospective closed
decisions remain separate research gates. No future profitability/date promise.

Alpaca NET original PAPER opener/guard and LIVE HALT/caps remain untouched; actual
Monday 16:30–16:35 Cyprus PAPER result is still an independent check. No Mac/VPS
process changes, research branch edits, Claude messages, money orders, Brain/B3
rerun, ATT1/KITY change or new strategy family was performed.
