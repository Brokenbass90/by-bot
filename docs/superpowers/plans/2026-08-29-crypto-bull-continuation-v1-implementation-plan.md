# Crypto Bull Continuation V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only Crypto Bull Continuation V1 experiment that evaluates independent horizontal and sloped long arms through a causal H4/D1 → H1 → M15 → next-M5-open contract, a frozen 2×2×2 development matrix, matched controls, diagnostic holdback, and an independent audit, without adding money, broker, order, risk, or promotion authority.

**Architecture:** Reuse the existing immutable `LevelSnapshotV1`, `SlopedLevelSnapshotV1`, closed-M5 aggregation, and horizontal MTF event state machine for Arm H. Add a separate `SlopedContinuationEventV1` adapter and a separate full-2R executor for Arm S/H matrix contracts; no event or trade identity crosses geometries. A bounded runner materializes causal decisions, execution receipts, 20 matched ledgers, 999 blocked permutations, 9,999 cluster-bootstrap intervals, and fail-closed receipts before scoring; a separate audit recomputes key metrics from raw ledgers.

**Tech Stack:** Python 3, frozen dataclasses, canonical JSON/SHA-256 identities, pytest, JSON/JSONL manifests and ledgers, existing `bot.closed_bar_aggregation_v1`, `bot.level_snapshot_v1`, `bot.sloped_level_snapshot_v1`, `strategies.event_expansion_retest_long_mtf_v1`, `bot.event_long_execution_v1`, and `research_lab.run_passport`.

**Spec:** `docs/superpowers/specs/2026-08-29-money-research-sprint-v1-design.md` (section 5 plus section 2.1 shared matched-control contract and sections 7–8 fail-closed/artifact requirements)

## Global Constraints

- Authority is exactly `research_only_no_live_or_promotion`; no broker/private API/network/order/risk/promotion authority is introduced.
- Development window is `[2023-01-01T00:00:00Z, 2024-07-01T00:00:00Z)`; purge/embargo is `[2024-07-01T00:00:00Z, 2024-08-01T00:00:00Z)`; diagnostic holdback is `[2024-08-01T00:00:00Z, 2025-10-01T00:00:00Z)`; the holdback is diagnostic, not untouched OOS.
- Bull regime is causal: last closed D1 close > EMA200 and D1 EMA200 slope over 20 closed D1 bars > 0, and last closed H4 close > EMA50 and H4 EMA50 slope over 12 closed H4 bars > 0; missing warmup is `not_admitted`.
- H1/H4/D1/M15/M5 inputs are closed and contiguous; H1 geometry/impulse precedes M15 hold/retest/confirmation; intended fill is the exact first M5 open after the confirming M15 close.
- BTC and ETH are fixed cohorts; the alt cohort is derived from source fixed-51 universe SHA `fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19` by removing BTCUSDT and ETHUSDT, then recorded as an exact 49-symbol canonical JSON list with its own SHA `fccae9d397d7653b1d91aef8bfc105f9555bad6239017b77edb282f535eb4693`; no symbol is replaced after a causal coverage failure.
- Arm H uses `LevelSnapshotV1` and the existing horizontal MTF state machine; Arm S uses `SlopedLevelSnapshotV1` and an independent `SlopedContinuationEventV1`; their event IDs, trades, controls, ledgers, metrics, and verdicts remain separate.
- Horizontal config is exactly `lookback_bars=120`, `atr_period=14`, `pivot_left=2`, `pivot_right=2`, `min_confirmed_pivots=2`, `cluster_tolerance_atr=0.30`, `zone_half_width_atr=0.18`, `max_distance_atr=5.0`, `approach_lookback_bars=3`, `min_approach_bars=2`, `min_approach_depth_atr=0.30`, `reaction_lookahead_bars=3`, `min_reaction_atr=0.30`, `close_break_tolerance_atr=0.0`, `require_contiguous_source=true`.
- Sloped config is exactly `lookback_bars=240`, `pivot_left=2`, `pivot_right=2`, `min_confirmed_pivots=3`, `min_r_squared=0.80`, `require_contiguous_source=true`, `require_unbroken_closes=true`; only positive-slope support lines qualify.
- H1 expansion is exactly range `>=1.25ATR`, bullish body fraction `>=0.45`, close return from prior close `>=1%`, volume `>=1.25x` the previous 24 H1 mean; Arm S additionally requires open/close above projected support and close above the previous 20-H1 high plus `0.08ATR`.
- Arm S requires two consecutive M15 closes at least `0.03ATR` above projection, then first touch in `projection-0.20ATR <= low <= projection+0.10ATR` with close >= projection; any later close below projection invalidates; acceptance is close >= projection + `0.03ATR` and above the previous M15 close; structure break uses higher-low `left=1/right=2`, at least `0.02ATR` above first-retest low, then a later close above pre-retest structure high plus `0.05ATR`; expiry is 48 M15 bars.
- The development matrix has exactly eight contracts: geometry H/S × confirmation close acceptance/confirmed structure break × exit full size at 2R/50% at 1R plus 50% at 2R. Every exit has deterministic max hold 96 M5 bars.
- Partial exits use `bot/event_long_execution_v1.py`; full-2R exits use a separate research-only `bot/event_long_full_2r_execution_v1.py` with `tp1_fraction=0`, `tp2_fraction=1`, its own schema/config/code hashes, and a conformance suite.
- Stop freezes at decision: H `min(first_retest_low, zone_low)-0.10*H1_ATR`; S `min(first_retest_low, projected_support_at_decision)-0.10*H1_ATR`; actual M5 open re-anchors R and targets; a gap through stop is adverse `stop_gap`; stop-first applies.
- Costs are base `6 fee + 2 slippage bps` per side and stress `10 + 5 bps` per side; stress funding credits are zero and every positive funding event has at least a 5-bps debit; missing funding blocks the run.
- One symbol has at most one event and cooldown lasts to terminal exit; maximum event-to-outcome window is 20 hours; overlapping same-symbol/same-side windows collapse to the earliest causal event; same UTC calendar date is one market cluster.
- Every decision/episode receives exactly 20 deterministic matched controls using `SHA256(config_fingerprint || event_id || draw_index)` and the same symbol, UTC month, bull state, H1 ATR decile, horizon, fill, stop-distance, exit, cost, and funding rules; fewer than 20 non-overlapping paths yields `control_unavailable` and blocks that arm.
- Each family receives exactly 999 blocked Westfall–Young permutations with one label bit per UTC-date cluster across all eight contracts; one-sided p-value is `(1 + count(permuted_stat >= observed_stat)) / 1000`; 9,999 cluster-bootstrap replicates with replacement produce percentile `[2.5%,97.5%]` intervals.
- Development selection is deterministic and development-only: an arm needs positive stress net, 3/4 positive folds, positive top-5%-trimmed result, positive matched-control excess, and largest positive symbol contribution `<=35%`; select at most one arm per geometry by maximum worst-fold stress net R, then lower drawdown, then lexicographically smaller config fingerprint.
- Holdback uses only the two frozen geometry survivors, applies Holm-adjusted one-sided p-values (or equivalent maxT), and never returns a failed bundle to search; no contrast or average can rescue a failed bundle.
- Historical shadow gate requires at least 40 symbol episodes, 20 market clusters, positive base/stress net R, positive halves and at least 3/4 stress folds, positive top-tail-trimmed stress result, mean stress excess `>=0.05R` per episode, PF `>=1.20`, adjusted p `<=0.05`, 95% cluster-bootstrap lower bound > 0, control-distribution separation > 1 sample standard deviation, contribution <=35%, and no causal/mechanical/portfolio failure. It authorizes zero-risk shadow only.
- All missing, stale, malformed, non-causal, duplicate, hash-mismatched, impossible, censored, or incomplete inputs are explicit receipts; exceptions never become `no signal` or a positive result. AI/Ollama is not used for parameter selection or verdicts.

---

## Repository Map and Interfaces

Existing surfaces to preserve and consume:

- `bot/closed_bar_aggregation_v1.py`: `ClosedBarAggregationConfigV1`, `aggregate_closed_m5_bars`, `canonical_bars_sha256`.
- `bot/level_snapshot_v1.py`: `LevelSnapshotConfigV1`, `LevelSnapshotV1`, `build_resistance_snapshot_v1`, `flip_level_snapshot_v1`, `level_snapshot_to_dict`.
- `bot/sloped_level_snapshot_v1.py`: `SlopedLevelConfigV1`, `SlopedLevelSnapshotV1`, `SlopedLevelBuildResultV1`, `build_sloped_level_snapshot_v1`.
- `strategies/event_expansion_retest_long_mtf_v1.py`: `EventExpansionRetestLongMTFConfigV1`, `MTFExpansionEventV1`, `MTFResearchPlanV1`, `process_closed_m5_prefix`, `state_to_json`, `state_from_json`.
- `bot/event_long_execution_v1.py`: `FrozenLongPlanV1`, `HistoricalFundingEventV1`, `simulate_frozen_long_plan_v1`, `verify_trade_receipt_v1`.
- `research_lab/run_passport.py`: `build_passport`, `write_passport`, `validate_passport`, and authority `research_only_no_live_or_promotion`.

New implementation boundaries:

- `configs/research/money_research_sprint_v1_control_contract.json` and `research_lab/money_research_controls_v1.py`: XSEC Task 1 owns the shared deterministic draws, blocked permutations, and cluster-bootstrap implementation consumed by Bull/XSEC/XAU.
- `research_lab/bull_continuation_contract_v1.py`: Bull-only validation of the frozen cohort, eight matrix cells, windows, thresholds, and authority fields.
- `configs/research/bull_continuation_fixed51_alt_cohort_v1.json`, `configs/research/crypto_bull_continuation_v1.json`, and `research_lab/prereg/PREREG_CRYPTO_BULL_CONTINUATION_V1_20260829.md`: frozen cohort, experiment contract, windows, costs, matrix, and authority.
- `strategies/sloped_continuation_event_v1.py`: Arm S event identity/state machine; no import of Arm H state or event IDs.
- `bot/event_long_full_2r_execution_v1.py`: separate full-size 2R executor and receipt schema.
- `research_lab/bull_continuation_engine_v1.py`: causal regime/aggregation/arm replay and episode ledgers.
- `research_lab/bull_continuation_scoring_v1.py`: matrix ranking, controls, permutations, bootstrap, gates, and terminal verdict.
- `research_lab/run_bull_continuation_v1.py`: preflight, bounded input loading, manifest/passport, atomic output, and CLI.
- `research_lab/audit_bull_continuation_v1.py`: independent raw-ledger recomputation.
- `research_lab/bull_continuation_shadow_v1.py`: zero-order prospective parity journal, enabled only after a diagnostic gate receipt.

## Implementation Tasks

### Task 1: Freeze Bull preregistration using the shared control contract

**Files:**
- Create: `configs/research/bull_continuation_fixed51_alt_cohort_v1.json`
- Create: `configs/research/crypto_bull_continuation_v1.json`
- Create: `research_lab/prereg/PREREG_CRYPTO_BULL_CONTINUATION_V1_20260829.md`
- Create: `research_lab/bull_continuation_contract_v1.py`
- Test: `tests/test_bull_continuation_contracts_v1.py`

**Interfaces:**
- Consumes the XSEC-owned `load_control_contract(path: Path) -> dict[str, Any]`, `stable_u64(seed: str) -> int`, `stable_index(seed: str, size: int) -> int`, `hash_rank(seed_parts: Sequence[str], values: Sequence[str]) -> list[str]`, `permutation_seed(family_id: str, config_fingerprint: str, permutation_index: int, block_id: str) -> str`, `paired_label_permutations(cluster_ids: Sequence[str], family_id: str, config_fingerprint: str, *, permutations: int = 999) -> list[dict[str, int]]`, `cluster_bootstrap_indices(experiment_id: str, config_fingerprint: str, cluster_count: int, *, sample_size: int | None = None, replicates: int = 9999) -> list[list[int]]`, `percentile_interval(values: Sequence[float], *, lower_pct: float = 2.5, upper_pct: float = 97.5) -> tuple[float, float]`, and `one_sided_p_value(observed: float, permuted: Sequence[float]) -> float` from `research_lab.money_research_controls_v1`; do not add a Bull-specific seed, permutation, or bootstrap implementation.
- Produces `validate_bull_config(config: Mapping[str, Any]) -> BullContractV1` from `research_lab.bull_continuation_contract_v1`, whose exact matrix is eight `(geometry, confirmation, exit)` tuples and whose cohort fields include BTCUSDT, ETHUSDT, the 49-symbol alt list, source SHA, development/embargo/holdback windows, and authority flags.
- The exact alt list in `bull_continuation_fixed51_alt_cohort_v1.json` is `1000BONKUSDT,1000PEPEUSDT,1000RATSUSDT,AAVEUSDT,ACEUSDT,ADAUSDT,ALGOUSDT,APTUSDT,ARBUSDT,ATOMUSDT,AVAXUSDT,BCHUSDT,BICOUSDT,BNBUSDT,C98USDT,COTIUSDT,CRVUSDT,DOGEUSDT,ETCUSDT,FILUSDT,GALAUSDT,HBARUSDT,HFTUSDT,ICPUSDT,INJUSDT,JTOUSDT,LDOUSDT,MNTUSDT,ONDOUSDT,OPUSDT,ORDIUSDT,PAXGUSDT,PEOPLEUSDT,SEIUSDT,SHIB1000USDT,SOLUSDT,STRKUSDT,SUIUSDT,TAOUSDT,TIAUSDT,TRXUSDT,UNIUSDT,USDCUSDT,WIFUSDT,WLDUSDT,XLMUSDT,XMRUSDT,XRPUSDT,ZECUSDT`; preserve this lexical order and hash it before scoring.

- [ ] **Step 1: Write failing Bull contract tests.** Load the existing shared contract and assert its immutable `draws_per_unit == 20`, `permutations == 999`, `bootstrap_replicates == 9999`, and seed algorithm strings. Assert that `validate_bull_config` rejects a changed cohort SHA, a non-49-symbol alt list, fewer than eight matrix cells, changed windows, changed costs, or any authority flag that is not false.

```python
def test_bull_consumes_xsec_owned_control_contract():
    shared = load_control_contract(ROOT / "configs/research/money_research_sprint_v1_control_contract.json")
    assert shared["draws_per_unit"] == 20
    assert shared["permutations"] == 999
    assert shared["bootstrap_replicates"] == 9999

def test_bull_contract_has_eight_exact_cells():
    contract = validate_bull_config(json.loads(BULL_CONFIG.read_text()))
    assert len(contract.development_matrix) == 8
    assert contract.authority == "research_only_no_live_or_promotion"
    assert contract.source_universe_sha256 == "fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19"
    assert contract.alt_symbols_sha256 == "fccae9d397d7653b1d91aef8bfc105f9555bad6239017b77edb282f535eb4693"
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_bull_continuation_contracts_v1.py`

Expected: the existing shared-control tests pass or fail only on their own XSEC Task 1 state; the Bull contract test fails because `validate_bull_config` and the three Bull JSON/preregistration files do not exist yet.

- [ ] **Step 3: Implement the Bull-only validator and frozen JSON.** Consume the existing shared loader and validate Bull fields locally; do not copy its RNG code. The validator must have a concrete fail-closed shape:

```python
def validate_bull_config(raw: Mapping[str, Any]) -> BullContractV1:
    shared = load_control_contract(Path(raw["shared_control_contract_path"]))
    if (shared["draws_per_unit"], shared["permutations"], shared["bootstrap_replicates"]) != (20, 999, 9999):
        raise BullContractError("shared_control_contract_drift")
    if raw["authority"] != "research_only_no_live_or_promotion" or raw["promotion_authority"] is not False:
        raise BullContractError("unsafe_authority")
    if len(raw["development_matrix"]) != 8 or {tuple(item) for item in raw["development_matrix"]} != EXPECTED_MATRIX:
        raise BullContractError("development_matrix_mismatch")
    canonical_alt = json.dumps(raw["alt_symbols"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if raw["source_universe_sha256"] != FIXED51_SOURCE_SHA:
        raise BullContractError("source_cohort_mismatch")
    if hashlib.sha256(canonical_alt).hexdigest() != FIXED51_ALT_SHA or raw["alt_symbols_sha256"] != FIXED51_ALT_SHA:
        raise BullContractError("alt_cohort_hash_mismatch")
    if len(raw["alt_symbols"]) != 49:
        raise BullContractError("alt_cohort_mismatch")
    return BullContractV1.from_mapping(raw)
```

Write the JSON with `shared_control_contract_path: "configs/research/money_research_sprint_v1_control_contract.json"`, exact windows, costs, H/S configs, funding policy, 20-hour maximum window, holdback thresholds, and the literal 49-symbol list stated above. The preregistration must repeat the same values and record that historical holdback is diagnostic rather than OOS.

- [ ] **Step 4: Run tests to verify they pass.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_bull_continuation_contracts_v1.py`

Expected: PASS; Bull config validation consumes the shared contract without defining duplicate controls, and all eight matrix cells/49 alt symbols are byte-stable.

- [ ] **Step 5: Commit the contract boundary.**

```bash
git add configs/research/bull_continuation_fixed51_alt_cohort_v1.json configs/research/crypto_bull_continuation_v1.json research_lab/prereg/PREREG_CRYPTO_BULL_CONTINUATION_V1_20260829.md research_lab/bull_continuation_contract_v1.py tests/test_bull_continuation_contracts_v1.py
git commit -m "research: freeze bull continuation preregistration"
```

### Task 2: Add the causal Arm S sloped event adapter

**Files:**
- Create: `strategies/sloped_continuation_event_v1.py`
- Test: `tests/test_sloped_continuation_event_v1.py`
- Reuse without edits: `bot/sloped_level_snapshot_v1.py`, `bot/closed_bar_aggregation_v1.py`, `strategies/event_expansion_retest_long_mtf_v1.py`

**Interfaces:**
- Consumes `SlopedLevelSnapshotV1` with `side="support"`, `interval_ms=3_600_000`, `as_of_ms=last_closed_H1_open_ms + 3_600_000`, and H1/M15 closed bars.
- Produces frozen `SlopedContinuationEventV1` with `event_id`, symbol, snapshot ID, canonical H1/M15 source/output/config hashes, ATR14, projection parameters, `known_at_ms`, `expires_at_ms`, and `stage` values `expanded`, `held_above`, `first_retest_consumed`, `higher_low_confirmed`, `plan_ready`, `invalidated`, `expired`.
- Produces `detect_sloped_continuation_event_v1(symbol: str, h1_snapshot: SlopedLevelSnapshotV1, h1_bars: Sequence[Sequence[float]], *, provider_fingerprint: str, cfg: SlopedContinuationConfigV1) -> Optional[SlopedContinuationEventV1]` and `advance_sloped_continuation_event_v1(event: SlopedContinuationEventV1, m15_bars: Sequence[Sequence[float]], *, as_of_ms: int, cfg: SlopedContinuationConfigV1) -> SlopedContinuationStepV1`.

- [ ] **Step 1: Write failing causal and mechanical tests.** Use the existing sloped fixture pattern to prove three confirmed pivots, positive slope, R² floor, exact line snapshot identity, two consecutive M15 holds, first-touch consumption, later acceptance/structure-break causality, expiry, invalidation below projection, future-tail invariance, and distinct H/S event IDs.

```python
def test_future_tail_and_unconfirmed_pivot_cannot_change_sloped_event():
    result = build_sloped_level_snapshot_v1("TESTUSDT", "support", H1, rows,
                                           as_of_ms=rows[-1][0] + H1,
                                           cfg=SlopedLevelConfigV1())
    assert result.status == "accepted"
    event = detect_sloped_continuation_event_v1("TESTUSDT", result.snapshot, rows,
                                                provider_fingerprint=SHA,
                                                cfg=SlopedContinuationConfigV1())
    assert event is None or event.snapshot_id == result.snapshot.snapshot_id
    with pytest.raises(SlopedContinuationEventError, match="future"):
        advance_sloped_continuation_event_v1(event, rows_with_future_bar,
                                             as_of_ms=closed_boundary + M5,
                                             cfg=SlopedContinuationConfigV1())
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_sloped_continuation_event_v1.py`

Expected: FAIL because `strategies.sloped_continuation_event_v1` and its frozen event types do not exist.

- [ ] **Step 3: Implement the isolated Arm S state machine.** Derive projection at every M15 close as `intercept_at_anchor + slope_per_interval*((close_boundary-anchor_ts_ms)/3_600_000)`, reject nonpositive slope or changed snapshot identity, enforce the exact hold/touch/acceptance/structure-break thresholds, and hash all source/config/ATR/projection/pivot/expiry fields into the event ID. Never call or mutate Arm H state.

```python
def projection_at(snapshot: SlopedLevelSnapshotV1, close_boundary_ms: int) -> float:
    return snapshot.intercept_at_anchor + snapshot.slope_per_interval * (
        (close_boundary_ms - snapshot.anchor_ts_ms) / 3_600_000
    )

def advance_sloped_continuation_event_v1(event, m15_bars, *, as_of_ms, cfg):
    if event.snapshot_id != event.snapshot.snapshot_id or event.snapshot.slope_per_interval <= 0:
        raise SlopedContinuationEventError("snapshot_identity_or_slope_invalid")
    closed = tuple(row for row in m15_bars if int(row[0]) + 900_000 <= as_of_ms)
    if not closed or int(closed[-1][0]) + 900_000 != as_of_ms:
        raise SlopedContinuationEventError("M15 prefix is not exactly closed")
    current = event
    for row in closed:
        close_boundary = int(row[0]) + 900_000
        projection = projection_at(event.snapshot, close_boundary)
        if float(row[4]) < projection:
            current = replace(current, stage="invalidated", terminal_reason="close_below_projection")
            break
        current = advance_one_closed_m15(current, row, projection, cfg)
    return SlopedContinuationStepV1(event=current, plan=None, reason=current.terminal_reason)
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `pytest -q tests/test_sloped_level_snapshot_v1.py tests/test_sloped_continuation_event_v1.py tests/test_event_expansion_retest_long_mtf_v1.py`

Expected: PASS; existing H state-machine tests remain unchanged and S-specific negative fixtures fail closed.

- [ ] **Step 5: Commit the isolated sloped arm.**

```bash
git add strategies/sloped_continuation_event_v1.py tests/test_sloped_continuation_event_v1.py
git commit -m "feat: add causal sloped bull continuation events"
```

### Task 3: Add the separate full-2R research executor

**Files:**
- Create: `bot/event_long_full_2r_execution_v1.py`
- Test: `tests/test_event_long_full_2r_execution_v1.py`
- Reuse as read-only reference: `bot/event_long_execution_v1.py`, `tests/test_event_long_execution_v1.py`

**Interfaces:**
- Produces `Full2RLongPlanV1`, `Full2RTradeReceiptV1`, `make_full_2r_long_plan_v1(*, event_id: str, level_id: str, strategy: str, symbol: str, signal_open_ts: int, entry_reference: float, frozen_stop: float, source_fingerprint: str, config_fingerprint: str, code_fingerprint: str) -> Full2RLongPlanV1`, `simulate_full_2r_long_plan_v1(plan: Full2RLongPlanV1, closed_m5_rows: Sequence[Sequence[Any]], *, as_of_ms: int, funding_events: Sequence[HistoricalFundingEventV1] = (), scenario: str = "base") -> Full2RTradeReceiptV1`, and `verify_full_2r_trade_receipt_v1(receipt: Full2RTradeReceiptV1) -> None`.
- The plan schema/contract name, plan ID, trade ID, receipt hash, source/config/code hash fields, and `FULL_2R_CONTRACT_NAME` are distinct from `FrozenLongPlanV1`; `tp1_fraction` is exactly `0.0`, `tp2_fraction` exactly `1.0`, and max hold exactly 96 M5 bars.
- Consumes the same exact next-M5 open, frozen-stop, stop-gap, stop-first, base/stress costs, funding completeness, and actual-open R re-anchoring rules as the existing executor, but never delegates a zero-TP1 plan to `simulate_frozen_long_plan_v1`.

- [ ] **Step 1: Write failing conformance tests.** Cover missing exact open, entry gap through stop, stop-first simultaneous target/stop, adverse stop gap, exact full-size 2R target, 96-bar max hold, base/stress costs, stress funding credit removal/minimum debit, contiguous rows, future funding rejection, and tamper detection. Assert that the existing partial executor rejects a full-2R geometry and the new executor accepts it.

```python
def test_full_2r_is_not_accepted_by_partial_executor():
    with pytest.raises(EventLongExecutionError, match="exit fractions"):
        replace(make_frozen_long_plan_v1(**PARTIAL_VALUES),
                tp1_fraction=0.0, tp2_fraction=1.0)

def test_full_2r_closes_entire_position_at_two_r():
    receipt = simulate_full_2r_long_plan_v1(plan, [row_reaching_two_r],
                                            as_of_ms=row_reaching_two_r[0] + M5)
    assert receipt.exit_reason == "tp2"
    assert receipt.remaining_fraction == 0.0
    assert [leg.fraction for leg in receipt.cost_legs] == [1.0, 1.0]
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_event_long_execution_v1.py tests/test_event_long_full_2r_execution_v1.py`

Expected: the existing test suite passes its baseline cases, while the new file fails with missing module/function names.

- [ ] **Step 3: Implement the independent full-2R executor.** Keep the implementation research-only and standalone; preserve exact leg-level cost accounting, funding event ordering, censored snapshot-end status, and receipt hash verification. Include an explicit `code_fingerprint` and `config_fingerprint` in every plan/receipt.

```python
def simulate_full_2r_long_plan_v1(plan, closed_m5_rows, *, as_of_ms,
                                  funding_events=(), scenario="base"):
    plan.__post_init__()
    rows = _validate_contiguous_closed_m5(closed_m5_rows, as_of_ms=as_of_ms)
    entry = _exact_row(rows, plan.valid_from_ts)
    if entry[1] <= plan.frozen_stop:
        return _rejected_receipt(plan, "rejected_gap_through_frozen_stop")
    risk = entry[1] - plan.frozen_stop
    target = entry[1] + 2.0 * risk
    legs = [_cost_leg("entry", "actual_next_open", entry[0], 1.0, entry[1], 0.0, risk, scenario)]
    for row in rows[rows.index(entry):rows.index(entry) + 96]:
        if row[1] <= plan.frozen_stop or row[3] <= plan.frozen_stop:
            return _close_full_position(plan, legs, row, "stop_gap" if row[1] < plan.frozen_stop else "stop", risk, scenario)
        if row[2] >= target:
            return _close_full_position(plan, legs, row, "tp2", risk, scenario, price=target)
    return _close_full_position(plan, legs, rows[min(len(rows), 96) - 1], "max_hold", risk, scenario)
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `pytest -q tests/test_event_long_execution_v1.py tests/test_event_long_full_2r_execution_v1.py`

Expected: PASS; partial executor remains unchanged and full-2R receipts are independently hash-verifiable.

- [ ] **Step 5: Commit the executor boundary.**

```bash
git add bot/event_long_full_2r_execution_v1.py tests/test_event_long_full_2r_execution_v1.py
git commit -m "feat: add isolated full two-r execution contract"
```

### Task 4: Build causal Bull replay and episode ledgers

**Files:**
- Create: `research_lab/bull_continuation_engine_v1.py`
- Test: `tests/test_bull_continuation_engine_v1.py`
- Modify only if required to expose a pure helper without behavior change: `strategies/event_expansion_retest_long_mtf_v1.py`

**Interfaces:**
- Produces `BullReplayConfigV1`, `BullRegimeSnapshotV1`, `BullEpisodeV1`, `BullDecisionLedgerRowV1`, `BullTradeLedgerRowV1`, `BullControlEligibilityV1`, and `BullReplayReceiptV1`.
- Produces `build_bull_regime_snapshot_v1(d1_closed: Sequence[Sequence[float]], h4_closed: Sequence[Sequence[float]], *, as_of_ms: int) -> BullRegimeSnapshotV1`, `replay_arm_h(symbol: str, raw_closed_m5: Sequence[Sequence[float]], *, as_of_ms: int, provider_identity: str, provider_fingerprint: str, cfg: EventExpansionRetestLongMTFConfigV1, confirmation: str, exit_contract: str) -> Sequence[BullDecisionLedgerRowV1]`, `replay_arm_s(symbol: str, raw_closed_m5: Sequence[Sequence[float]], *, as_of_ms: int, provider_identity: str, provider_fingerprint: str, cfg: SlopedContinuationConfigV1, confirmation: str, exit_contract: str) -> Sequence[BullDecisionLedgerRowV1]`, `materialize_episode_windows(rows: Sequence[BullDecisionLedgerRowV1], *, max_window_ms: int = 72_000_000) -> Sequence[BullEpisodeV1]`, and `build_matched_control_eligibility(episode: BullEpisodeV1, candidate_rows: Sequence[BullCandidatePathV1], *, config_fingerprint: str) -> BullControlEligibilityV1`. It also produces concrete `BullCandidatePathV1` and `BullControlLedgerRowV1` rows; the latter is the 20-draw control row type.
- Arm H calls `process_closed_m5_prefix` using a fully serialized `EventExpansionRetestLongMTFConfigV1` and converts only its causal plan boundary; Arm S calls `SlopedContinuationEventV1`; the engine rejects any cross-arm event ID, level ID, snapshot ID, or plan ID.
- Every ledger row carries `experiment_id`, `config_fingerprint`, `geometry`, `confirmation`, `exit`, symbol, event/episode/cluster IDs, all source aggregation hashes, decision/known/fill timestamps, stop reference, status/reason, and no fabricated outcome.

- [ ] **Step 1: Write failing replay tests.** Assert D1/H4 admission warmup, future-bar invariance, exact aggregation boundaries, H1 event known at H1 close, M15 confirmation before next M5 open, no same-bar collapse, first retest consumed once, S line invalidation, event window/cluster formation, earliest-overlap rule, and fewer-than-20 control paths blocking the arm.

```python
def test_regime_uses_only_last_closed_bars():
    before = build_bull_regime_snapshot_v1(d1_closed, h4_closed, as_of_ms=AS_OF)
    after = build_bull_regime_snapshot_v1(d1_closed + [future_d1], h4_closed,
                                          as_of_ms=AS_OF)
    assert after == before

def test_control_shortage_is_terminal_not_silently_dropped():
    eligibility = build_matched_control_eligibility(episode, candidate_rows[:19],
                                                     config_fingerprint=CFG_SHA)
    assert eligibility.status == "control_unavailable"
    assert eligibility.blocks_arm is True
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_bull_continuation_engine_v1.py`

Expected: FAIL with missing replay types/functions.

- [ ] **Step 3: Implement the causal replay engine.** Aggregate only contiguous closed M5 prefixes; use D1/H4 only for regime admission, H1 only for level/expansion, M15 only after the H1 event, and the exact next M5 open for intended fill. Apply the frozen H and S stop formulas, derive a 20-hour event window, assign `cluster_id=YYYY-MM-DD`, and retain `pending`/`censored` outcomes rather than dropping them.

```python
def build_bull_regime_snapshot_v1(d1_closed, h4_closed, *, as_of_ms):
    if len(d1_closed) < 220 or len(h4_closed) < 62:
        return BullRegimeSnapshotV1(status="not_admitted", reason="indicator_warmup", as_of_ms=as_of_ms)
    d1_ema = ema([float(row[4]) for row in d1_closed], 200)
    h4_ema = ema([float(row[4]) for row in h4_closed], 50)
    admitted = (d1_closed[-1][4] > d1_ema[-1] and d1_ema[-1] > d1_ema[-21]
                and h4_closed[-1][4] > h4_ema[-1] and h4_ema[-1] > h4_ema[-13])
    return BullRegimeSnapshotV1(status="admitted" if admitted else "not_admitted",
                                reason="causal_d1_h4_bull" if admitted else "trend_gate",
                                as_of_ms=as_of_ms)

def materialize_episode_windows(rows, *, max_window_ms=72_000_000):
    ordered = sorted(rows, key=lambda row: (row.symbol, row.side, row.event_known_at_ms))
    kept = []
    last_by_symbol_side = {}
    for row in ordered:
        key = (row.symbol, row.side)
        if row.event_known_at_ms - last_by_symbol_side.get(key, -max_window_ms - 1) <= max_window_ms:
            continue
        last_by_symbol_side[key] = row.event_known_at_ms
        kept.append(BullEpisodeV1.from_decision(row, cluster_id=utc_date(row.decision_at_ms)))
    return tuple(sorted(kept, key=lambda item: (item.cluster_id, item.symbol, item.event_id)))
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `pytest -q tests/test_level_snapshot_v1.py tests/test_sloped_level_snapshot_v1.py tests/test_event_expansion_retest_long_mtf_v1.py tests/test_bull_continuation_engine_v1.py`

Expected: PASS; all pre-existing causal primitive tests remain green and engine fixtures prove exact H/S separation.

- [ ] **Step 5: Commit replay and ledgers.**

```bash
git add research_lab/bull_continuation_engine_v1.py tests/test_bull_continuation_engine_v1.py
git commit -m "feat: build causal bull continuation replay ledgers"
```

### Task 5: Implement the eight-contract scoring, controls, and holdback gates

**Files:**
- Create: `research_lab/bull_continuation_scoring_v1.py`
- Test: `tests/test_bull_continuation_scoring_v1.py`
- Consume: `research_lab/money_research_controls_v1.py`, `research_lab/bull_continuation_engine_v1.py`, both executors, and frozen config files

**Interfaces:**
- Produces `ContractMetricsV1`, `BullFamilyLedgerV1`, `HoldbackMetricsV1`, `DevelopmentSelectionV1`, `PermutationSummaryV1`, `BootstrapIntervalV1`, `BullArmVerdictV1`, and `BullFamilyVerdictV1`.
- Produces `score_contract(ledger: Sequence[BullTradeLedgerRowV1], controls: Sequence[BullControlLedgerRowV1], *, scenario: str) -> ContractMetricsV1`, `rank_development_contracts(metrics: Sequence[ContractMetricsV1], *, development_folds: Sequence[str]) -> DevelopmentSelectionV1`, `run_blocked_permutations(family: BullFamilyLedgerV1, *, permutation_count: int = 999) -> PermutationSummaryV1`, `recompute_episode_excess(episodes: Sequence[BullEpisodeV1], controls: Sequence[BullControlLedgerRowV1], sampled_cluster_ids: Sequence[str]) -> float`, `cluster_bootstrap_excess(episodes: Sequence[BullEpisodeV1], controls: Sequence[BullControlLedgerRowV1], *, experiment_id: str, config_fingerprint: str, replicates: int = 9_999) -> BootstrapIntervalV1`, `evaluate_portfolio_compatibility(episodes: Sequence[BullEpisodeV1], *, sbr1_rows: Sequence[Mapping[str, Any]], range_long_rows: Sequence[Mapping[str, Any]]) -> PortfolioCompatibilityV1`, and `evaluate_bull_verdict(family: BullFamilyLedgerV1, selected: DevelopmentSelectionV1, holdback: HoldbackMetricsV1) -> BullFamilyVerdictV1`.
- Primary effect is mean stress excess R per symbol episode; controls use the same execution geometry/cost/funding path; permutations change paired labels by UTC-date cluster across all eight development contracts; bootstrap resamples market clusters and never individual trades/rows.

- [ ] **Step 1: Write failing scoring tests.** Assert exact 2×2×2 enumeration, no selection based on holdback, deterministic ranking tie-breaks, 20-control sample standard deviation, top-5%-trimmed metrics, 35% contribution cap, blocked permutations, one-sided p-value formula, maxT/Holm adjustment, 9,999 cluster resamples, symbol/side overlap, BTC/alt beta and correlation/cluster exposure checks, SBR1/range-long conflicts, and all historical holdback thresholds.

```python
def test_selection_keeps_at_most_one_arm_per_geometry():
    selected = rank_development_contracts(metrics, development_folds=FOUR_FOLDS)
    assert {item.geometry for item in selected.holdback_contracts} == {"H", "S"}
    assert len(selected.holdback_contracts) <= 2

def test_one_sided_p_value_uses_999_permutations():
    summary = run_blocked_permutations(observed_stat=0.2,
                                       permutation_stats=[0.2] + [-0.1] * 998,
                                       permutation_count=999)
    assert summary.p_value == pytest.approx(2 / 1000)

def test_holdback_fail_is_terminal():
    verdict = evaluate_bull_verdict(family=family_with_failed_s,
                                    selected=selection,
                                    holdback=failed_holdback)
    assert verdict.status == "FAIL_RESEARCH"
    assert verdict.reopen_condition == "new_preregistered_window"
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_bull_continuation_scoring_v1.py`

Expected: FAIL with missing scoring module/functions.

- [ ] **Step 3: Implement scoring and gates.** Compute base/stress net R, PF, folds/halves, top-tail removal, MFE/MAE/DD, symbol concentration, and control separation. Use exactly the shared hash seeds and blocked nulls; fail on any incomplete draw, missing path, changed cluster membership, or non-terminal unit. Keep family verdicts separate for H, S, BTC, ETH, and alt reporting.

```python
def score_contract(ledger, controls, *, scenario):
    terminal = [row for row in ledger if row.scenario == scenario and row.status == "filled_closed"]
    if not terminal or len(controls) != 20 or any(row.status != "filled_closed" for row in controls):
        raise ScoringBlocked("non_terminal_strategy_or_control_unit")
    control_mean = statistics.fmean(row.net_r for row in controls)
    return ContractMetricsV1(
        scenario=scenario,
        net_r=sum(row.net_r for row in terminal),
        pf=_profit_factor([row.net_r for row in terminal]),
        stress_excess_per_episode=statistics.fmean(row.net_r for row in terminal) - control_mean,
        control_std=statistics.stdev(row.net_r for row in controls),
        top_trimmed_net_r=_trim_top_five_percent([row.net_r for row in terminal]),
        max_symbol_contribution=_largest_positive_symbol_share(terminal),
    )

def run_blocked_permutations(family, *, permutation_count=999):
    if permutation_count != 999:
        raise ScoringBlocked("permutation_count_is_frozen")
    labels = paired_label_permutations(
        sorted(family.utc_date_clusters), family.family_id,
        family.config_fingerprint, permutations=999,
    )
    stats = tuple(family.recompute_stat(label_map) for label_map in labels)
    return PermutationSummaryV1(
        p_value=one_sided_p_value(family.observed_stat, stats),
        stats=stats,
    )

def recompute_episode_excess(episodes, controls, sampled_cluster_ids):
    strategy_by_cluster = defaultdict(list)
    control_by_cluster = defaultdict(list)
    for row in episodes:
        strategy_by_cluster[row.cluster_id].append(row.stress_r)
    for row in controls:
        control_by_cluster[row.cluster_id].append(row.net_r)
    effects = [
        statistics.fmean(strategy_by_cluster[cluster_id]) - statistics.fmean(control_by_cluster[cluster_id])
        for cluster_id in sampled_cluster_ids
    ]
    return statistics.fmean(effects)

def cluster_bootstrap_excess(episodes, controls, *, experiment_id, config_fingerprint, replicates=9_999):
    clusters = sorted({episode.cluster_id for episode in episodes})
    indices = cluster_bootstrap_indices(
        experiment_id, config_fingerprint, len(clusters),
        sample_size=len(clusters), replicates=replicates,
    )
    effects = [recompute_episode_excess(episodes, controls, [clusters[index] for index in sample]) for sample in indices]
    lower, upper = percentile_interval(effects)
    return BootstrapIntervalV1(lower=lower, upper=upper, replicates=replicates, cluster_unit="utc_calendar_date")
```

- [ ] **Step 4: Run tests to verify they pass.**

Run: `pytest -q tests/test_bull_continuation_scoring_v1.py tests/test_research_significance.py`

Expected: PASS; no score can be emitted for an incomplete or hash-mismatched ledger.

- [ ] **Step 5: Commit scoring and gates.**

```bash
git add research_lab/bull_continuation_scoring_v1.py tests/test_bull_continuation_scoring_v1.py
git commit -m "feat: add bull continuation controls and diagnostic gates"
```

### Task 6: Add the bounded research runner, preflight, manifests, and reports

**Files:**
- Create: `research_lab/run_bull_continuation_v1.py`
- Test: `tests/test_run_bull_continuation_v1.py`
- Consume: `research_lab/run_passport.py`, the frozen configs, engine, scoring, and both executors

**Interfaces:**
- CLI: `python3 -m research_lab.run_bull_continuation_v1 --config configs/research/crypto_bull_continuation_v1.json --control-contract configs/research/money_research_sprint_v1_control_contract.json --alt-cohort configs/research/bull_continuation_fixed51_alt_cohort_v1.json --data-root research_lab/data --out research_lab/results/crypto_bull_continuation_v1_20260829`.
- Produces `preflight_receipt.json`, `input_manifest.json`, `run_passport.json`, `decision_ledger.jsonl`, `trade_ledger.jsonl`, `control_ledger.jsonl`, `permutation_ledger.jsonl`, `bootstrap_ledger.jsonl`, `metrics.json`, `fragility_report.json`, `terminal_verdict.json`, and `completion.json` only after all required checks pass.
- Produces `preflight(root: Path, config_path: Path, control_path: Path, cohort_path: Path, data_root: Path) -> dict[str, Any]`, `run(args: argparse.Namespace) -> dict[str, Any]`, and a nonzero exit status for `BLOCKED_DATA_OR_PARITY`/`FAIL_RESEARCH` technical failures while still persisting the terminal receipt.

- [ ] **Step 1: Write failing runner tests.** Assert explicit data-root bounds, fixed cohort SHA, no sealed holdout reads, source/code/config hashes before scoring, full 49-symbol list, minimum 30 alt full-coverage gate, exact development/embargo/holdback windows, research-only authority fields, atomic output behavior, and no network/broker imports.

```python
def test_preflight_blocks_alt_cohort_without_30_full_coverage(tmp_path):
    receipt = preflight(ROOT, CONFIG, CONTROL, COHORT, tmp_path / "only_btc")
    assert receipt["status"] == "BLOCKED_DATA_OR_PARITY"
    assert receipt["reason"] == "alt_full_causal_coverage_below_30"

def test_runner_writes_failure_receipt_without_fake_metrics(tmp_path):
    result = run_with_paths(data_root=tmp_path / "missing", out=tmp_path / "run")
    assert result["terminal_verdict"] == "BLOCKED_DATA_OR_PARITY"
    assert not (tmp_path / "run" / "metrics.json").exists()
    assert (tmp_path / "run" / "terminal_verdict.json").is_file()
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_run_bull_continuation_v1.py`

Expected: FAIL with missing runner module/CLI and absent manifest receipts.

- [ ] **Step 3: Implement preflight and bounded run.** Resolve only explicit paths under the repository data root; hash every code/config/input file; build the passport before any metrics; reject overlap with the declared purge/holdback policy; verify source bars, funding, instrument metadata, and coverage; run development only, then freeze the two selected geometry bundles before diagnostic holdback. Never fetch data or call a broker.

```python
def preflight(root, config_path, control_path, cohort_path, data_root):
    config = validate_bull_config(read_json(config_path))
    shared = load_control_contract(root / config.shared_control_contract_path)
    if root.resolve() not in data_root.resolve().parents:
        raise RunnerBlocked("data_root_outside_repository")
    manifest = build_input_manifest(root, data_root, config.symbols)
    if manifest["alt_full_causal_coverage"] < 30:
        return terminal_block("alt_full_causal_coverage_below_30", manifest)
    passport = build_passport(build_passport_request(config, manifest, control_path, cohort_path), project_root=root)
    write_once(root / "research_lab/results" / "crypto_bull_continuation_v1_20260829" / "run_passport.json", passport)
    return {"status": "PASS", "manifest": manifest, "shared_contract": shared}
```

- [ ] **Step 4: Implement fragility and report serialization.** Re-score only the frozen bundles with one-M5-later fill and prescribed cost worsening; publish this as a diagnostic fragility report, never as a new search candidate. Write raw ledgers and compact summaries with all counts (raw rows, symbol episodes, market clusters, rebalance/decision units), hashes, reasons, and reopen conditions.

```python
def serialize_run(run_dir, replay, scores, verdict):
    write_jsonl_once(run_dir / "decision_ledger.jsonl", replay.decisions)
    write_jsonl_once(run_dir / "trade_ledger.jsonl", replay.trades)
    write_jsonl_once(run_dir / "control_ledger.jsonl", replay.controls)
    write_jsonl_once(run_dir / "permutation_ledger.jsonl", scores.permutations)
    write_jsonl_once(run_dir / "bootstrap_ledger.jsonl", scores.bootstrap)
    write_json_once(run_dir / "metrics.json", scores.metrics)
    write_json_once(run_dir / "fragility_report.json", run_fragility_only(replay, scores.frozen_contracts))
    write_json_once(run_dir / "terminal_verdict.json", verdict)
    write_json_once(run_dir / "completion.json", {"run_id": run_dir.name, "terminal_verdict": verdict["status"]})
```

- [ ] **Step 5: Run the runner tests and a bounded smoke invocation.**

Run: `pytest -q tests/test_run_bull_continuation_v1.py tests/test_experiment_preflight.py tests/test_run_passport.py`

Expected: PASS; smoke invocation exits nonzero with `BLOCKED_DATA_OR_PARITY` if the current bounded data cannot supply 30 alt symbols, and writes no positive metrics.

- [ ] **Step 6: Commit the runner and artifacts contract.**

```bash
git add research_lab/run_bull_continuation_v1.py tests/test_run_bull_continuation_v1.py
git commit -m "feat: add bounded bull continuation research runner"
```

### Task 7: Build the independent raw-ledger audit

**Files:**
- Create: `research_lab/audit_bull_continuation_v1.py`
- Test: `tests/test_audit_bull_continuation_v1.py`

**Interfaces:**
- Produces `audit_run(root: Path, run_dir: Path) -> dict[str, Any]` and CLI `python3 -m research_lab.audit_bull_continuation_v1 --run-dir research_lab/results/crypto_bull_continuation_v1_20260829`.
- Recomputes SHA chains, counts, episode/cluster membership, net R, PF, folds/halves, top-tail trim, concentration, 20-control means/standard deviations, permutation p-values, bootstrap intervals, and terminal-gate booleans without importing runner scoring functions.
- Writes `independent_audit.json` with `audit_status` exactly `PASS`, `FAIL`, or `BLOCKED_DATA_OR_PARITY`; a changed raw ledger, missing row, mismatched config/input hash, or nonzero authority flag is not a warning.

- [ ] **Step 1: Write failing audit tests.** Build a small valid fixture and assert the audit recomputes its metrics; mutate a trade net R, control draw, cluster ID, permutation seed, bootstrap count, or authority flag and assert a blocking audit result.

```python
def test_audit_recomputes_and_detects_raw_ledger_tamper(tmp_path):
    run_dir = make_valid_run_fixture(tmp_path)
    assert audit_run(ROOT, run_dir)["audit_status"] == "PASS"
    append_jsonl(run_dir / "trade_ledger.jsonl", {"net_r": 999.0})
    report = audit_run(ROOT, run_dir)
    assert report["audit_status"] == "FAIL"
    assert "ledger_hash" in report["failures"]
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_audit_bull_continuation_v1.py`

Expected: FAIL because the independent audit module does not exist.

- [ ] **Step 3: Implement the independent recomputation.** Read only manifest/config/raw ledgers and standard-library math; reproduce the shared seed formulas locally; verify exact 999/9,999 cardinalities and cluster bootstrap units; compare recomputed values to published metrics and verdict conditions.

```python
def audit_run(root, run_dir):
    manifest = read_json(run_dir / "input_manifest.json")
    trades = read_jsonl(run_dir / "trade_ledger.jsonl")
    controls = read_jsonl(run_dir / "control_ledger.jsonl")
    if sha256_file(run_dir / "trade_ledger.jsonl") != manifest["trade_ledger_sha256"]:
        return {"audit_status": "FAIL", "failures": ["ledger_hash"]}
    if len(controls) != 20 * len({row["episode_id"] for row in trades}):
        return {"audit_status": "FAIL", "failures": ["control_cardinality"]}
    recomputed = recompute_metrics_from_raw(trades, controls, read_jsonl(run_dir / "permutation_ledger.jsonl"),
                                            read_jsonl(run_dir / "bootstrap_ledger.jsonl"))
    return compare_published_metrics(run_dir, recomputed)
```

- [ ] **Step 4: Run audit tests and the runner/audit integration.**

Run: `pytest -q tests/test_audit_bull_continuation_v1.py tests/test_run_bull_continuation_v1.py`

Expected: PASS; audit status is terminal and cannot be upgraded by the runner.

- [ ] **Step 5: Commit the audit.**

```bash
git add research_lab/audit_bull_continuation_v1.py tests/test_audit_bull_continuation_v1.py
git commit -m "test: add independent bull continuation ledger audit"
```

### Task 8: Add zero-order prospective shadow parity, gated by the diagnostic receipt

**Files:**
- Create: `research_lab/bull_continuation_shadow_v1.py`
- Test: `tests/test_bull_continuation_shadow_v1.py`
- Do not modify: live routers, broker adapters, risk controls, Alpaca SAFE_HOLD, or any money-release gate.

**Interfaces:**
- Produces `BullShadowJournalV1` and `BullShadowEventV1` with signal timestamp, intended next-M5 open, observable fill, latency, gaps, frozen stop/target lifecycle, decision reason, source/config hashes, heartbeat, and reconciliation fields.
- Produces `open_shadow(run_dir: Path, *, verdict_path: Path, now_ms: int) -> BullShadowJournalV1`, `append_observation(journal: BullShadowJournalV1, observation: Mapping[str, Any]) -> BullShadowJournalV1`, and `reconcile_shadow(journal: BullShadowJournalV1, *, now_ms: int) -> dict[str, Any]`.
- `open_shadow` accepts only an exact `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` verdict plus a passing independent audit; it rejects every other verdict and never emits an order intent.
- Produces `prospective_status(journal: BullShadowJournalV1, *, now_ms: int) -> dict[str, Any]`; it can emit `PROSPECTIVE_SHADOW_EVIDENCE_PASS` only after at least 60 UTC days since preregistration, 50 terminal symbol episodes, 20 UTC-date market clusters, positive stress excess over the concurrent controls, a strictly positive 95% cluster-bootstrap lower bound, and zero integrity incidents. The verdict still carries `money_authority=false`.

- [ ] **Step 1: Write failing shadow tests.** Assert non-PASS verdicts are rejected, a PASS opens a research-only journal, duplicate event IDs are rejected, intended fill must equal the exact next M5 open, missing/late observations are explicit, and no module import contains broker/order/private API symbols.

```python
def test_shadow_requires_diagnostic_pass_and_has_no_order_authority(tmp_path):
    with pytest.raises(ShadowError, match="diagnostic verdict"):
        open_shadow(tmp_path, verdict_path=failed_verdict, now_ms=NOW)
    journal = open_shadow(tmp_path, verdict_path=passed_verdict, now_ms=NOW)
    assert journal.authority == "research_only_no_live_or_promotion"
    assert journal.order_authority is False

def test_prospective_gate_requires_every_frozen_condition():
    assert prospective_status(journal(days=59, episodes=50, clusters=20), now_ms=NOW)["verdict"] == "COLLECTING_ZERO_RISK_EVIDENCE"
    passed = prospective_status(journal(days=60, episodes=50, clusters=20, stress_excess=0.01, lower_bound=0.001), now_ms=NOW)
    assert passed["verdict"] == "PROSPECTIVE_SHADOW_EVIDENCE_PASS"
    assert passed["money_authority"] is False
    assert prospective_status(journal(days=60, episodes=50, clusters=20, incidents=1), now_ms=NOW)["verdict"] == "FAIL_PROSPECTIVE_SHADOW"
```

- [ ] **Step 2: Run tests to verify they fail.**

Run: `pytest -q tests/test_bull_continuation_shadow_v1.py`

Expected: FAIL with missing shadow module/types.

- [ ] **Step 3: Implement the append-only, zero-order journal.** Pin the diagnostic verdict/audit/config hashes at open, record intended versus observed next-M5 fill and all lifecycle/reconciliation facts, and classify gaps or incomplete exits as `pending`/`censored`; do not add a scheduler, network client, broker call, order schema, or risk mutation.

```python
def open_shadow(run_dir, *, verdict_path, now_ms):
    verdict = read_json(verdict_path)
    audit = read_json(run_dir / "independent_audit.json")
    if verdict["status"] != "DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW" or audit["audit_status"] != "PASS":
        raise ShadowError("diagnostic verdict or independent audit is not passing")
    return BullShadowJournalV1(
        opened_at_ms=now_ms,
        authority="research_only_no_live_or_promotion",
        order_authority=False,
        verdict_sha256=sha256_file(verdict_path),
        audit_sha256=sha256_file(run_dir / "independent_audit.json"),
        events=(),
    )

def prospective_status(journal, *, now_ms):
    terminal = [event for event in journal.events if event.outcome_state == "terminal"]
    clusters = {event.decision_ts_utc[:10] for event in terminal}
    bootstrap_lower = cluster_bootstrap_excess(
        terminal,
        experiment_id=journal.experiment_id,
        config_fingerprint=journal.config_fingerprint,
        replicates=9999,
    )[0]
    elapsed_days = (now_ms - journal.preregistration_ts_ms) // 86_400_000
    incidents = [event for event in journal.events if event.integrity_status != "PASS"]
    stress_excess = statistics.fmean(event.stress_r - event.control_stress_r for event in terminal) if terminal else 0.0
    complete = elapsed_days >= 60 and len(terminal) >= 50 and len(clusters) >= 20
    if incidents:
        verdict = "FAIL_PROSPECTIVE_SHADOW"
    elif complete and stress_excess > 0.0 and bootstrap_lower > 0.0:
        verdict = "PROSPECTIVE_SHADOW_EVIDENCE_PASS"
    else:
        verdict = "COLLECTING_ZERO_RISK_EVIDENCE"
    return {"verdict": verdict, "money_authority": False, "elapsed_utc_days": elapsed_days,
            "terminal_symbol_episodes": len(terminal), "market_clusters": len(clusters),
            "stress_excess_r": stress_excess, "bootstrap_95_lower": bootstrap_lower,
            "integrity_incidents": len(incidents)}
```

- [ ] **Step 4: Run shadow and full scoped verification.**

Run: `pytest -q tests/test_bull_continuation_shadow_v1.py tests/test_bull_continuation_engine_v1.py tests/test_bull_continuation_scoring_v1.py tests/test_run_bull_continuation_v1.py tests/test_audit_bull_continuation_v1.py tests/test_event_long_execution_v1.py tests/test_event_long_full_2r_execution_v1.py tests/test_event_expansion_retest_long_mtf_v1.py tests/test_level_snapshot_v1.py tests/test_sloped_level_snapshot_v1.py`

Expected: PASS; no test starts a broker, sends an order, changes risk, or reads a private endpoint.

- [ ] **Step 5: Commit the zero-risk shadow parity boundary.**

```bash
git add research_lab/bull_continuation_shadow_v1.py tests/test_bull_continuation_shadow_v1.py
git commit -m "feat: add gated zero-order bull shadow parity journal"
```

### Task 9: Final verification and handoff

**Files:**
- Verify only: all files listed above; no unrelated worktree files.

- [ ] **Step 1: Run the complete scoped test suite.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_bull_continuation_contracts_v1.py tests/test_sloped_level_snapshot_v1.py tests/test_sloped_continuation_event_v1.py tests/test_event_expansion_retest_long_mtf_v1.py tests/test_event_long_execution_v1.py tests/test_event_long_full_2r_execution_v1.py tests/test_bull_continuation_engine_v1.py tests/test_bull_continuation_scoring_v1.py tests/test_run_bull_continuation_v1.py tests/test_audit_bull_continuation_v1.py tests/test_bull_continuation_shadow_v1.py`

Expected: all unit and integration tests PASS; data availability is exercised separately in Step 3 and never turns a pytest failure into an accepted block.

- [ ] **Step 2: Run static and integrity checks.**

Run: `git diff --check`

Expected: exit 0.

Run: `python3 -m py_compile strategies/sloped_continuation_event_v1.py bot/event_long_full_2r_execution_v1.py research_lab/bull_continuation_contract_v1.py research_lab/bull_continuation_engine_v1.py research_lab/bull_continuation_scoring_v1.py research_lab/run_bull_continuation_v1.py research_lab/audit_bull_continuation_v1.py research_lab/bull_continuation_shadow_v1.py`

Expected: exit 0 without creating a verdict or runtime receipt.

Run: `rg -n "(requests|urllib|ccxt|create_order|submit_order|cancel_order|private_api|broker_calls\s*=\s*True|order_authority\s*=\s*True)" strategies/sloped_continuation_event_v1.py bot/event_long_full_2r_execution_v1.py research_lab/bull_continuation_engine_v1.py research_lab/bull_continuation_scoring_v1.py research_lab/run_bull_continuation_v1.py research_lab/audit_bull_continuation_v1.py research_lab/bull_continuation_shadow_v1.py`

Expected: no matches; test files may contain forbidden strings only as static assertions and are not included in this scan.

- [ ] **Step 3: Run the bounded CLI and independent audit.**

Run: `python3 -m research_lab.run_bull_continuation_v1 --config configs/research/crypto_bull_continuation_v1.json --control-contract configs/research/money_research_sprint_v1_control_contract.json --alt-cohort configs/research/bull_continuation_fixed51_alt_cohort_v1.json --data-root research_lab/data --out research_lab/results/crypto_bull_continuation_v1_20260829`

Expected: exit 0 with a complete diagnostic result, or exit 2 with a persisted `BLOCKED_DATA_OR_PARITY`/`FAIL_RESEARCH` receipt and concrete reopen condition.

Run: `python3 -m research_lab.audit_bull_continuation_v1 --run-dir research_lab/results/crypto_bull_continuation_v1_20260829`

Expected: exit 0 after recomputing a complete run, or exit 2 after independently confirming a persisted blocked receipt has no hidden positive metrics; no shadow activation occurs.

- [ ] **Step 4: Review scope and worktree state.**

Run: `git status --short`

Expected: only planned Bull/shared-control files are present.

Run: `git diff --stat`

Expected: only the planned Bull/control files are changed; do not stage or commit unrelated user work. This plan itself does not authorize deployment, shadow activation, promotion, or money decisions.

## Self-Review Checklist

- [ ] Section 5 physical hypothesis, fixed cohorts, windows, H/S geometry, exact thresholds, 2×2×2 matrix, separate full-2R executor, deterministic development selection, holdback, mechanical fixtures, episode independence, controls, gates, and prospective shadow requirements each map to a task above.
- [ ] Shared section 2.1 counts/seeds/nulls/bootstrap rules are owned by XSEC Task 1, validated by Bull Task 1, and consumed without duplication by Bull Tasks 5–7.
- [ ] `LevelSnapshotV1`, `SlopedLevelSnapshotV1`, exact H/M15/M5 causality, and existing execution conformance tests are named as consumed surfaces rather than reimplemented or merged.
- [ ] Every task has exact files, interfaces, failing test, red command, implementation boundary, green command, expected result, and frequent commit.
- [ ] No implementation, live, broker, risk, promotion, network, or destructive operation is included in this plan execution now.
