# XSEC PIT V5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild XSEC V4 as a point-in-time, delisting-aware, executable-cost XSEC PIT V5 study that produces an independently audited diagnostic verdict and can only authorize a zero-risk prospective shadow.

**Architecture:** A write-once preregistration binds the published 36-arm family, centre/reference arm, bounded archives, manifests, code hashes, and the shared deterministic control contract. A causal replay produces strategy and 20 matched-control ledgers using next-open execution, funding, executable quantity constraints, and base/stress costs; inference then recomputes all 36 arms under stratified score permutations and nested month/control bootstraps. A read-only independent auditor recomputes the primary metrics and a separate gate emits only a diagnostic/shadow verdict, never money authority.

**Tech Stack:** Python 3.11+, pytest, stdlib `hashlib`/`json`/`dataclasses`, existing pandas/numpy archive readers, JSON/JSONL write-once manifests and ledgers, `research_lab.run_passport` and `research_lab.experiment_lifecycle` for hash-bound provenance.

**Spec:** `docs/superpowers/specs/2026-08-29-money-research-sprint-v1-design.md` (sections 2, 4, 7, and 8)

## Global Constraints

- `Authority: research-only; без live, broker orders, изменения риска, promotion или money authority`.
- Repeat exactly the published `configs/preregistered/xsec_v4_family_landscape_20260728.json` 36-cell family; no parameter is added after PIT results are observed.
- Published champion is trial 8: `lookbacks=[7,14,21,30,45]`, `rebalance_days=3`, `basket_k=5`, `target_annual_vol=0.15`.
- Centre/reference is fixed before PIT scoring: `lookbacks=[7,14,30]`, `rebalance_days=3`, `basket_k=3`, `target_annual_vol=0.10`; it is reported separately and cannot bypass the family gate.
- Listing/launch timestamp, `>=390` closed daily bars, delisted history, causal turnover, funding, metadata, next-open execution, executable minimum/step constraints, and explicit missing-data reason codes are required; survivor-only approximation blocks the run.
- The shared control contract uses exactly 20 matched draws per unit, 999 blocked permutations, and 9999 cluster-bootstrap replicates, with the SHA-256 seed algorithms in section 2.1.
- XSEC permutations reassign factor scores only inside causal maturity/liquidity/volatility strata, use one mapping for all 36 arms, and recompute baskets, controls, next-open fills, funding, and costs from zero.
- The XSEC primary effect is monthly stress excess over each arm's own 20 matched controls; family statistic is the median of 36 arm-level annualized excess values.
- Analysis calendar contains every full UTC month from the first post-warmup month through the last bounded full month; any arm/month without one terminal strategy unit and 20 terminal controls blocks the family run.
- Every run publishes preregistration/config/input/code hashes, immutable membership and liquidity manifests, integrity receipt, raw strategy/trade/control ledgers, base/stress metrics, independent audit, terminal verdict, and reopen condition.
- Missing, stale, malformed, future, open, boundary, duplicate, or hash-mismatched input fails closed; exceptions never become `no signal`, zero PnL, or a positive result.
- Historical PIT evidence is diagnostic because the periods were previously studied; `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` authorizes only zero-risk shadow. `PROSPECTIVE_SHADOW_EVIDENCE_PASS` requires 90 UTC days, 30 terminal reference-arm intervals, 12 UTC weeks, positive stress excess over a concurrently running control, a positive 95% lower bound, and zero integrity incidents; it still grants no money authority.
- AI/Ollama remains proposal/classification-only and cannot select parameters, rewrite a verdict, merge code, place orders, or change risk.

---

## File map

Create the shared deterministic implementation in `research_lab/money_research_controls_v1.py` so XAU can consume the same contract without a second seed or bootstrap implementation. XSEC-specific PIT admission and factor/replay logic lives in `research_lab/xsec_pit_v5_data.py` and `research_lab/xsec_pit_v5_replay.py`; inference, audit, runner, and shadow gate remain separate so a negative arm cannot be hidden by an orchestrator.

### Task 1: Freeze the shared control contract and XSEC family

**Files:**
- Create: `configs/research/money_research_sprint_v1_control_contract.json`
- Create: `configs/research/xsec_pit_v5_preregistration.json`
- Create: `research_lab/money_research_controls_v1.py`
- Test: `tests/test_money_research_controls_v1.py`
- Test: `tests/test_xsec_pit_v5_preregistration.py`

**Interfaces:**
- Produces `load_control_contract(path: Path) -> dict[str, Any]`, `stable_u64(seed: str) -> int`, `stable_index(seed: str, size: int) -> int`, `hash_rank(seed_parts: Sequence[str], values: Sequence[str]) -> list[str]`, `permutation_seed(family_id: str, config_fingerprint: str, permutation_index: int, block_id: str) -> str`, `paired_label_permutations(cluster_ids: Sequence[str], family_id: str, config_fingerprint: str, *, permutations: int = 999) -> list[dict[str, int]]`, `cluster_bootstrap_indices(experiment_id: str, config_fingerprint: str, cluster_count: int, *, sample_size: int | None = None, replicates: int = 9999) -> list[list[int]]`, `percentile_interval(values: Sequence[float], *, lower_pct: float = 2.5, upper_pct: float = 97.5) -> tuple[float, float]`, and `one_sided_p_value(observed: float, permuted: Sequence[float]) -> float`.
- Produces `load_xsec_preregistration(path: Path) -> XsecPreregistration`, where `XsecPreregistration.arms` is the exact ordered 36-tuple and `.champion` and `.reference` are frozen `XsecArm` values consumed by Tasks 2–5.
- The contract is also the interface consumed by the XAU plan: `draws_per_unit == 20`, `permutations == 999`, and `bootstrap_replicates == 9999` are immutable fields, not CLI overrides.

- [ ] **Step 1: Write the failing contract tests.**

```python
def test_shared_counts_and_hash_mapping_are_frozen():
    contract = load_control_contract(ROOT / "configs/research/money_research_sprint_v1_control_contract.json")
    assert contract["draws_per_unit"] == 20
    assert contract["permutations"] == 999
    assert contract["bootstrap_replicates"] == 9999
    assert stable_u64("abc") == int(hashlib.sha256(b"abc").hexdigest()[:16], 16)
    assert stable_index("abc", 7) == stable_u64("abc") % 7

def test_generic_hash_rank_and_permutation_seed_are_cross_project_stable():
    assert hash_rank(("cfg", "2024-01-04", "0"), ["B", "A", "C"]) == sorted(
        ["B", "A", "C"],
        key=lambda value: (stable_u64("cfg||2024-01-04||0||" + value), value),
    )
    expected = hashlib.sha256(b"perm_v1||family||cfg||7||2024-01-04").hexdigest()
    assert permutation_seed("family", "cfg", 7, "2024-01-04") == expected

def test_paired_label_permutations_share_one_bit_per_cluster():
    rows = paired_label_permutations(["2024-01-01", "2024-01-02"], "family", "cfg")
    assert len(rows) == 999
    assert set(rows[0]) == {"2024-01-01", "2024-01-02"}
    assert all(bit in {0, 1} for row in rows for bit in row.values())
    assert rows[0]["2024-01-01"] == int(permutation_seed("family", "cfg", 0, "2024-01-01")[:16], 16) & 1

def test_cluster_bootstrap_has_9999_replicates_and_nested_sample_size():
    draws = cluster_bootstrap_indices("exp", "cfg", 3, sample_size=5)
    assert len(draws) == 9999
    assert all(len(row) == 5 and all(0 <= index < 3 for index in row) for row in draws)
    assert draws == cluster_bootstrap_indices("exp", "cfg", 3, sample_size=5)

def test_percentile_interval_is_deterministic_linear_percentile():
    assert percentile_interval([1.0, 2.0, 3.0, 4.0]) == pytest.approx((1.075, 3.925))

def test_xsec_prereg_has_exact_family_and_fixed_arms():
    prereg = load_xsec_preregistration(ROOT / "configs/research/xsec_pit_v5_preregistration.json")
    assert len(prereg.arms) == 36
    assert prereg.champion == XsecArm("trial_08", (7, 14, 21, 30, 45), 3, 5, 0.15)
    assert prereg.reference == XsecArm("reference", (7, 14, 30), 3, 3, 0.10)
    assert {arm.arm_id for arm in prereg.arms} == {f"trial_{i:02d}" for i in range(1, 37)}

def test_one_sided_p_value_uses_999_denominator():
    assert one_sided_p_value(2.0, [1.0] * 999) == 1 / 1000
    assert one_sided_p_value(2.0, [2.0] * 999) == 1.0

def test_bootstrap_seed_is_reproducible_and_rejects_empty_clusters():
    first = cluster_bootstrap_indices("xsec_pit_v5_20260829", "cfg", 3, sample_size=4)
    assert first == cluster_bootstrap_indices("xsec_pit_v5_20260829", "cfg", 3, sample_size=4)
    with pytest.raises(ValueError, match="cluster_count"):
        cluster_bootstrap_indices("exp", "cfg", 0)
```

- [ ] **Step 2: Run the focused tests to verify the red state.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_xsec_pit_v5_preregistration.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.money_research_controls_v1'`.

- [ ] **Step 3: Add the exact machine-readable contract and preregistration.**

`money_research_sprint_v1_control_contract.json` must contain:

```json
{
  "schema_id": "money_research_sprint_v1_control_contract",
  "authority": "research_only_no_live_or_promotion",
  "draws_per_unit": 20,
  "permutations": 999,
  "bootstrap_replicates": 9999,
  "hash_integer": "unsigned_integer_from_first_16_hex_sha256",
  "matched_seed": "SHA256(config_fingerprint || event_id || draw_index)",
  "permutation_seed": "SHA256(perm_v1 || family_id || config_fingerprint || permutation_index || block_id)",
  "bootstrap_seed": "SHA256(bootstrap_v1 || experiment_id || config_fingerprint || replicate || draw_index)",
  "one_sided_p_value": "(1 + count(permuted_stat >= observed_stat)) / 1000",
  "cluster_bootstrap": "percentile_2_5_to_97_5_with_replacement",
  "strategy_control_rules": "same_symbol_or_causal_universe_side_month_regime_bucket_horizon_gross_exposure_and_fill_cost_exit_rules"
}
```

`xsec_pit_v5_preregistration.json` must copy the three lookback sets, rebalance days `[2,3,5]`, basket sizes `[3,5]`, vol targets `[0.10,0.15]`, `n_trials_planned: 36`, maturity `390`, base `15` bps, stress `30` bps, `champion: trial_08`, the reference arm, the bounded archive paths, and the diagnostic verdict thresholds from section 4.4. The file must set `research_only: true`, `capital_authorized: false`, and `promotion_authority: false`.

- [ ] **Step 4: Implement deterministic helpers without `random` or hidden global state.**

```python
def stable_u64(seed: str) -> int:
    if not isinstance(seed, str) or not seed:
        raise ValueError("seed must be non-empty")
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16)

def stable_index(seed: str, size: int) -> int:
    if size <= 0:
        raise ValueError("size must be positive")
    return stable_u64(seed) % size

def hash_rank(seed_parts: Sequence[str], values: Sequence[str]) -> list[str]:
    parts = [str(part) for part in seed_parts]
    symbols = [str(value) for value in values]
    if not parts or not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("seed_parts and unique values are required")
    return sorted(symbols, key=lambda value: (stable_u64("||".join([*parts, value])), value))

def permutation_seed(family_id: str, config_fingerprint: str, permutation_index: int, block_id: str) -> str:
    if permutation_index < 0:
        raise ValueError("permutation_index must be non-negative")
    payload = f"perm_v1||{family_id}||{config_fingerprint}||{permutation_index}||{block_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def paired_label_permutations(
    cluster_ids: Sequence[str], family_id: str, config_fingerprint: str, *, permutations: int = 999
) -> list[dict[str, int]]:
    clusters = [str(cluster_id) for cluster_id in cluster_ids]
    if not clusters or len(clusters) != len(set(clusters)) or permutations != 999:
        raise ValueError("paired labels require unique clusters and exactly 999 permutations")
    return [
        {
            cluster_id: int(permutation_seed(family_id, config_fingerprint, index, cluster_id)[:16], 16) & 1
            for cluster_id in clusters
        }
        for index in range(permutations)
    ]

def cluster_bootstrap_indices(
    experiment_id: str, config_fingerprint: str, cluster_count: int, *, sample_size: int | None = None,
    replicates: int = 9999
) -> list[list[int]]:
    if cluster_count <= 0:
        raise ValueError("cluster_count must be positive")
    if replicates != 9999:
        raise ValueError("replicates must equal 9999")
    size = cluster_count if sample_size is None else sample_size
    if size <= 0:
        raise ValueError("sample_size must be positive")
    return [
        [stable_index(f"bootstrap_v1||{experiment_id}||{config_fingerprint}||{replicate}||{draw}", cluster_count)
         for draw in range(size)]
        for replicate in range(replicates)
    ]

def percentile_interval(
    values: Sequence[float], *, lower_pct: float = 2.5, upper_pct: float = 97.5
) -> tuple[float, float]:
    ordered = sorted(float(value) for value in values)
    if not ordered or not 0.0 <= lower_pct <= upper_pct <= 100.0:
        raise ValueError("values and ordered percentile bounds are required")
    def quantile(percentile: float) -> float:
        position = (len(ordered) - 1) * percentile / 100.0
        left = int(position)
        right = min(left + 1, len(ordered) - 1)
        return ordered[left] + (ordered[right] - ordered[left]) * (position - left)
    return quantile(lower_pct), quantile(upper_pct)

def one_sided_p_value(observed: float, permuted: Sequence[float]) -> float:
    if len(permuted) != 999:
        raise ValueError("permuted must contain exactly 999 values")
    return (1 + sum(value >= observed for value in permuted)) / 1000.0
```

The loader rejects any count or algorithm drift. `hash_rank` is the generic sorted eligible-set mapping used by XSEC, Bull, and XAU. `paired_label_permutations` assigns one hash-derived bit to every row in a cluster, so every arm shares the same strategy/control label swap. `cluster_bootstrap_indices` uses the first 16 SHA-256 hex characters and modulo `cluster_count` for each draw, with exact seed `bootstrap_v1 || experiment_id || config_fingerprint || replicate || draw_index`; its output is a list of 9999 replicate index lists. `percentile_interval` is the shared linear percentile implementation for every 95% interval.

- [ ] **Step 5: Run the focused tests to verify green and inspect the frozen values.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_xsec_pit_v5_preregistration.py`

Expected: all tests PASS; the test output reports `36` arms, champion `trial_08`, reference `reference`, and contract counts `20/999/9999`.

- [ ] **Step 6: Commit the contract boundary.**

```bash
git add configs/research/money_research_sprint_v1_control_contract.json configs/research/xsec_pit_v5_preregistration.json research_lab/money_research_controls_v1.py tests/test_money_research_controls_v1.py tests/test_xsec_pit_v5_preregistration.py
git commit -m "feat: freeze shared controls and XSEC PIT family"
```

### Task 2: Build point-in-time membership, delisting, and liquidity manifests

**Files:**
- Create: `research_lab/xsec_pit_v5_data.py`
- Create: `scripts/preflight_xsec_pit_v5.py`
- Test: `tests/test_xsec_pit_v5_data.py`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/preflight/membership_manifest.jsonl`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/preflight/liquidity_manifest.jsonl`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/preflight/input_manifest.json`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/preflight/receipt.json`

**Interfaces:**
- `load_listing_intervals(path: Path) -> dict[str, dict[str, Any]]` reads `research_lab/data/bybit_public_archive_2023/listing_intervals.json`, validates its payload hash and retains launch and delivery/delisting timestamps for `Trading` and `Closed` records.
- `build_membership_manifest(listing_path: Path, instrument_path: Path, symbols: Sequence[str], as_of_utc: datetime) -> list[dict[str, Any]]` emits rows with `instrument_id`, `symbol`, `listed_at_utc`, `delisted_at_utc`, `source_as_of_utc`, `source_uri_or_record_id`, `status`, `contract_type`, `quote`, `min_qty`, `qty_step`, `tick_size`, and explicit `reason_code`.
- `build_liquidity_manifest(daily_root: Path, membership: Sequence[dict[str, Any]]) -> list[dict[str, Any]]` emits one row per symbol/day with `timestamp_utc`, causal `turnover`, `unit`, `source`, and `source_sha256`; it rejects duplicate/non-monotonic bars and never forward-fills turnover.
- `eligible_at_rebalance(rebalance_ts: datetime, membership: Mapping[str, dict[str, Any]], liquidity: Mapping[str, Sequence[dict[str, Any]]], closes: Mapping[str, Sequence[dict[str, Any]]], maturity_days: int = 390) -> tuple[list[str], dict[str, str]]` returns only causally eligible symbols and reason codes for every excluded symbol.
- `run_preflight(listing_path: Path, instrument_path: Path, daily_root: Path, funding_root: Path, out_dir: Path, start_utc: datetime, end_utc_exclusive: datetime) -> dict[str, Any]` writes all four outputs atomically/write-once and returns `BLOCKED_DATA_OR_PARITY` if a delisted universe, daily history, funding path, or instrument metadata cannot be reconstructed.

- [ ] **Step 1: Write failing PIT manifest tests.**

```python
def test_membership_preserves_closed_instrument_and_quantity_metadata(tmp_path):
    listing = tmp_path / "listing.json"
    listing.write_text(json.dumps({"payload_sha256": sha(records), "provider_snapshot": {"records": records}}))
    rows = build_membership_manifest(listing, listing, ["OLDUSDT"], datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert rows[0]["listed_at_utc"] == "2022-01-01T00:00:00Z"
    assert rows[0]["delisted_at_utc"] == "2023-06-01T00:00:00Z"
    assert rows[0]["qty_step"] == "0.1"

def test_future_liquidity_is_not_visible_at_rebalance(tmp_path):
    manifest = build_liquidity_manifest(tmp_path / "bars", membership_for("AAAUSDT"))
    eligible, reasons = eligible_at_rebalance(ts("2024-01-03"), membership, liquidity, closes)
    assert eligible == ["AAAUSDT"]
    assert all(row["timestamp_utc"] <= "2024-01-03T00:00:00Z" for row in manifest)

def test_missing_delisted_history_blocks_instead_of_creating_survivor_universe(tmp_path):
    with pytest.raises(PitDataError, match="delisted universe"):
        run_preflight(listing_path=tmp_path / "missing.json", daily_root=tmp_path, funding_root=tmp_path, out_dir=tmp_path / "out")
```

- [ ] **Step 2: Run the red tests.**

Run: `pytest -q tests/test_xsec_pit_v5_data.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.xsec_pit_v5_data'`.

- [ ] **Step 3: Implement causal archive validation and immutable manifests.**

Use the existing archive shapes (`bars/<SYMBOL>.json`, `funding/<SYMBOL>.json`, and `listing_intervals.json`) and `research_lab.run_passport.sha256_file`. Validate authority flags, status `complete`, requested symbols, payload SHA, closed-bar timestamps, OHLC positivity, and funding timestamps before any scoring. A membership row with unknown `min_qty`, `qty_step`, or `tick_size`, missing listing interval, or missing source record must carry a non-empty reason code; it must not be coerced to zero. Delisted symbols remain eligible only when `listed_at_utc <= rebalance_ts < delisted_at_utc`.

The preflight receipt must contain `schema_id: xsec_pit_v5_preflight_v1`, exact source/config hashes, manifest hashes, `authority: research_only_no_live_or_promotion`, `private_api_calls: false`, `orders_or_risk_mutation: false`, `survivorship_resolved: true|false`, and terminal `status: PASS|BLOCKED_DATA_OR_PARITY`.

```python
def eligible_at_rebalance(rebalance_ts, membership, liquidity, closes, maturity_days=390):
    eligible, reasons = [], {}
    for symbol in sorted(membership):
        row = membership[symbol]
        listed = parse_utc(row["listed_at_utc"])
        delisted = parse_utc(row["delisted_at_utc"]) if row["delisted_at_utc"] else None
        if listed > rebalance_ts or (delisted and rebalance_ts >= delisted):
            reasons[symbol] = "not_listed_or_already_delisted"
            continue
        if len(closes.get(symbol, ())) < maturity_days:
            reasons[symbol] = "insufficient_closed_daily_bars"
            continue
        if not liquidity.get(symbol):
            reasons[symbol] = "missing_causal_daily_liquidity"
            continue
        if row.get("reason_code"):
            reasons[symbol] = str(row["reason_code"])
            continue
        eligible.append(symbol)
    return eligible, reasons

def build_liquidity_manifest(daily_root, membership):
    output = []
    for symbol in sorted(membership):
        payload = read_json(daily_root / "bars" / f"{symbol}.json")
        rows = payload.get("records") or []
        verify_payload_hash(payload, rows, symbol)
        previous = None
        for row in rows:
            timestamp = int(row["ts_ms"])
            if previous is not None and timestamp <= previous:
                raise PitDataError(f"{symbol}: non-monotonic daily bars")
            previous = timestamp
            turnover = float(row["turnover"])
            if not math.isfinite(turnover) or turnover < 0:
                raise PitDataError(f"{symbol}: invalid daily turnover")
            output.append({
                "instrument_id": membership[symbol]["instrument_id"],
                "symbol": symbol,
                "timestamp_utc": iso_utc(timestamp),
                "causal_value": turnover,
                "unit": "USDT_turnover",
                "source": f"{daily_root}/bars/{symbol}.json",
                "source_sha256": sha256_file(daily_root / "bars" / f"{symbol}.json"),
            })
    return output
```

- [ ] **Step 4: Run the green unit tests and the archive preflight.**

Run: `pytest -q tests/test_xsec_pit_v5_data.py`

Expected: all unit tests PASS, including a failure for an absent delisted archive and an as-of join that excludes future turnover.

Run: `python scripts/preflight_xsec_pit_v5.py --listing research_lab/data/bybit_public_archive_2023/listing_intervals.json --instruments research_lab/data/bybit_instruments_linear.json --daily research_lab/data/bybit_daily_preholdout_2023_20250930 --funding research_lab/data/bybit_public_preholdout_2023_20250930 --out-dir research_lab/results/xsec_pit_v5_20260829/preflight`

Expected: exit `0` and `receipt.json.status == "PASS"` only when PIT membership, daily liquidity, funding, and metadata closure are complete; otherwise exit `2` with `status == "BLOCKED_DATA_OR_PARITY"` and a concrete `reason_code`.

- [ ] **Step 5: Commit the manifest boundary.**

```bash
git add research_lab/xsec_pit_v5_data.py scripts/preflight_xsec_pit_v5.py tests/test_xsec_pit_v5_data.py
git commit -m "feat: add XSEC PIT membership and liquidity preflight"
```

### Task 3: Implement the causal 36-arm replay and executable ledgers

**Files:**
- Create: `research_lab/xsec_pit_v5_replay.py`
- Test: `tests/test_xsec_pit_v5_replay.py`
- Reuse without changing: `research_lab/xsec_v3_reference.py`, `research_lab/xsec_causal_contract.py`, `research_lab/run_passport.py`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/strategy_ledger.jsonl`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/control_ledger.jsonl`

**Interfaces:**
- `@dataclass(frozen=True) class XsecArm: arm_id: str; lookbacks: tuple[int, int, int] | tuple[int, int, int, int, int]; rebalance_days: int; basket_k: int; target_annual_vol: float`.
- `factor_scores(closed_history: Mapping[str, Sequence[float]], arm: XsecArm) -> dict[str, float]` reproduces V4 momentum-rank-plus-volatility-rank, post-event noise exclusion, and deterministic lexical tie-breaks using closed daily data only.
- `build_strategy_weights(scores: Mapping[str, float], arm: XsecArm, prior_returns: Sequence[float], executable: Mapping[str, InstrumentSpec]) -> dict[str, ExecutableOrder]` preserves V4 long/short counts and volatility target, then applies minimum quantity and quantity-step constraints; a target that cannot be executed returns a reason code rather than a silently altered exposure.
- `replay_arm(arm: XsecArm, inputs: PitInputs, cost_bps: float, control_mode: bool = False) -> list[dict[str, Any]]` returns one terminal closed-rebalance portfolio unit per scheduled rebalance or raises `ReplayBlocked` on missing next-open, funding, metadata, liquidity, or terminal exit paths.
- `replay_family(prereg: XsecPreregistration, inputs: PitInputs) -> dict[str, list[dict[str, Any]]]` produces base and stress strategy ledgers for all 36 arms with `decision_id`, `arm_id`, `signal_ts_utc`, `entry_ts_utc`, `exit_ts_utc`, `cluster_id`, `symbols`, `weights`, `turnover`, `funding_cashflow`, `cost`, `net_log_return`, `status`, and `reason_code`.

- [ ] **Step 1: Write mechanical red tests before implementation.**

```python
def test_signal_uses_next_allowed_open_and_rebalance_exit():
    row = replay_arm(arm, synthetic_inputs(signal_close="2024-01-03", next_open="2024-01-04", exit_open="2024-01-07"), 15.0)[0]
    assert row["entry_ts_utc"] == "2024-01-04T00:00:00Z"
    assert row["exit_ts_utc"] == "2024-01-07T00:00:00Z"
    assert row["entry_ts_utc"] != row["signal_ts_utc"]

def test_missing_next_open_or_funding_is_blocking():
    with pytest.raises(ReplayBlocked, match="next_open"):
        replay_arm(arm, inputs_without_next_open(), 15.0)
    with pytest.raises(ReplayBlocked, match="funding"):
        replay_arm(arm, inputs_without_funding(), 15.0)

def test_target_weight_and_executable_order_parity_is_explicit():
    orders = build_strategy_weights(scores, arm, [], executable_metadata)
    assert all(order.qty % metadata[order.symbol].qty_step == 0 for order in orders.values())
    assert sum(abs(order.notional) for order in orders.values()) <= 1.0

def test_funding_and_costs_are_included_in_stress_ledger():
    base = replay_arm(arm, synthetic_inputs(funding_rate=0.001), 15.0)[0]
    stress = replay_arm(arm, synthetic_inputs(funding_rate=0.001), 30.0)[0]
    assert stress["cost"] > base["cost"]
    assert stress["funding_cashflow"] <= base["funding_cashflow"]
```

- [ ] **Step 2: Run the red replay tests.**

Run: `pytest -q tests/test_xsec_pit_v5_replay.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.xsec_pit_v5_replay'`.

- [ ] **Step 3: Implement closed-data factor scoring and all 36 frozen arms.**

Call only the already published factor semantics from `research_lab.xsec_v3_reference.py`; do not normalize away its netted long/short weights. `factor_scores` may read no row later than the closed signal daily bar. Use stable `symbol` lexical order on rank ties. For every arm, retain `factor_scores`, eligible symbols, maturity/liquidity/volatility strata, and the exact `config_fingerprint` in the decision ledger so permutation replays can replace scores without using outcomes.

- Factor implementation body:

```python
def factor_scores(closed_history, arm):
    required = max(arm.lookbacks) + 1
    usable = {symbol: list(values) for symbol, values in closed_history.items()
              if len(values) >= required and values[-1] > 0}
    score = {symbol: 0.0 for symbol in usable}
    used = 0
    for lookback in arm.lookbacks:
        factors = []
        for symbol in sorted(usable):
            values = usable[symbol]
            volatility = daily_volatility(values[-lookback - 1:])
            if volatility is None or volatility <= 0:
                continue
            momentum = values[-1] / values[-1 - lookback] - 1.0
            if abs(values[-1] / values[-2] - 1.0) > 3.0 * volatility:
                continue
            factors.append((symbol, momentum, volatility))
        if len(factors) < 2 * arm.basket_k + 4:
            continue
        momentum_order = {symbol: rank for rank, (symbol, _, _) in enumerate(sorted(factors, key=lambda row: (row[1], row[0])))}
        volatility_order = {symbol: rank for rank, (symbol, _, _) in enumerate(sorted(factors, key=lambda row: (row[2], row[0])))}
        for symbol, _, _ in factors:
            score[symbol] += momentum_order[symbol] + volatility_order[symbol]
        used += 1
    return {} if used == 0 else {symbol: value / used for symbol, value in score.items() if value != 0.0}
```

- [ ] **Step 4: Implement next-open, funding, costs, and executable constraints.**

For each closed daily signal, use the next allowed daily open and the open exactly `rebalance_days` later. Apply the existing funding sign convention (`-weight * rate` for each event strictly after entry and through exit), but convert missing funding coverage to `ReplayBlocked`. Apply base `15 bps` and stress `30 bps` round-trip costs plus actual funding; retain turnover and each order's `min_qty`, `qty_step`, and `tick_size`. Reject non-finite/non-positive prices, missing next-open/exit-open, duplicate decisions, and any target-to-executable mismatch. Write one terminal strategy unit and preserve open/pending/censored outcomes as explicit non-terminal states that block the required analysis month.

- Replay implementation body:

```python
def replay_unit(weights, opens, funding, signal_ts_ms, entry_index, exit_index, cost_bps):
    if entry_index >= len(opens) or exit_index >= len(opens):
        raise ReplayBlocked("next_open_or_exit_open_unavailable")
    entry = {symbol: float(opens[symbol][entry_index]) for symbol in weights}
    exit_ = {symbol: float(opens[symbol][exit_index]) for symbol in weights}
    if any(not math.isfinite(price) or price <= 0 for price in [*entry.values(), *exit_.values()]):
        raise ReplayBlocked("invalid_executable_price")
    exit_ts_ms = int(opens.index[exit_index])
    if not funding_covers(funding, signal_ts_ms, exit_ts_ms):
        raise ReplayBlocked("funding_path_unavailable")
    result = period_return(
        weights, entry, exit_, funding,
        entry_ts_ms=int(opens.index[entry_index]),
        exit_ts_ms=exit_ts_ms,
        round_trip_cost_fraction=cost_bps / 10000.0,
    )
    return {
        "entry_ts_utc": iso_utc(int(opens.index[entry_index])),
        "exit_ts_utc": iso_utc(exit_ts_ms),
        "funding_cashflow": result["funding_cashflow"],
        "cost": result["cost"],
        "net_log_return": math.log1p(result["net_return"]),
        "status": "terminal",
    }
```

- [ ] **Step 5: Run the replay tests and verify the family count.**

Run: `pytest -q tests/test_xsec_pit_v5_replay.py tests/test_xsec_causal_contract.py`

Expected: all tests PASS; the family fixture emits exactly 36 arm IDs, signal timestamps precede entry timestamps, and stress costs are never below base costs.

- [ ] **Step 6: Commit causal replay.**

```bash
git add research_lab/xsec_pit_v5_replay.py tests/test_xsec_pit_v5_replay.py
git commit -m "feat: add XSEC PIT next-open executable replay"
```

### Task 4: Add matched controls, stratified permutations, and nested bootstrap inference

**Files:**
- Create: `research_lab/xsec_pit_v5_inference.py`
- Test: `tests/test_xsec_pit_v5_inference.py`
- Consume without modifying: `research_lab/money_research_controls_v1.py`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/matched_control_ledger.jsonl`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/permutation_ledger.jsonl`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/bootstrap_receipt.json`

**Interfaces:**
- `matched_baskets(eligible_symbols: Sequence[str], strategy_symbols: set[str], arm: XsecArm, config_fingerprint: str, rebalance_ts: str, event_id: str, draw_index: int, weights: Mapping[str, float]) -> dict[str, float]` returns one deterministic random long/short basket with the same counts, gross weights, volatility target, and executable constraints; the 20 draw indices are never replaced after seeing outcomes.
- `monthly_stress_excess(strategy_rows: Sequence[Mapping[str, Any]], control_rows: Sequence[Mapping[str, Any]]) -> dict[str, float]` groups paired units into UTC calendar months and subtracts the mean of that arm/month's 20 control net log-return ledgers.
- `build_causal_strata(eligible_rows: Sequence[Mapping[str, Any]]) -> dict[str, Sequence[str]]` computes only pre-rebalance maturity (`390 through 729` or `>=730`), causal 30-day median dollar-turnover tercile, and causal 30-day realized-volatility tercile; ties are lexical.
- `permutation_mapping(strata: Mapping[str, Sequence[str]], config_fingerprint: str, permutation_index: int, rebalance_ts: str) -> dict[str, Sequence[str]]` returns one symbol mapping per stratum and leaves strata smaller than four symbols fixed.
- `run_xsec_permutations(family: XsecPreregistration, strategy_inputs: PitInputs, control_contract: Mapping[str, Any], observed: Mapping[str, Any]) -> list[dict[str, Any]]` runs exactly 999 permutations, one score mapping across all 36 arms, and full fresh basket/control/next-open/funding/cost replays.
- `nested_family_bootstrap(month_rows: Sequence[Mapping[str, Any]], experiment_id: str, config_fingerprint: str) -> dict[str, Any]` performs exactly 9999 UTC-month cluster resamples with replacement and, inside each sampled month, resamples the 20 control-ledger indices with replacement before recomputing the family median.
- `infer_family(observed, permutations, bootstrap) -> dict[str, Any]` returns family median annualized stress excess, champion/reference maxT-adjusted p-values, family p-value, percentile interval, control standard deviations, and independent UTC-month/rebalance counts.

- [ ] **Step 1: Write failing inference tests.**

```python
def test_matched_draws_are_deterministic_and_preserve_exposure():
    draws = [matched_baskets(symbols, {"A", "B"}, arm, "cfg", "2024-01-04", "evt", i, weights) for i in range(20)]
    assert draws == [matched_baskets(symbols, {"A", "B"}, arm, "cfg", "2024-01-04", "evt", i, weights) for i in range(20)]
    assert all(sum(v > 0 for v in draw.values()) == arm.basket_k for draw in draws)
    assert all(sum(v < 0 for v in draw.values()) == arm.basket_k for draw in draws)

def test_strata_are_causal_and_small_strata_remain_fixed():
    strata = build_causal_strata(rows_known_at_rebalance)
    assert set(strata) == {"maturity_390_729|liq_0|vol_0", "maturity_ge_730|liq_2|vol_2"}
    assert permutation_mapping(strata, "cfg", 0, "2024-01-04")["small"] == ("small",)

def test_permutation_recomputes_controls_and_uses_all_36_arms():
    rows = run_xsec_permutations(family, inputs, contract, observed)
    assert len(rows) == 999
    assert all(set(row["arm_ids"]) == {f"trial_{i:02d}" for i in range(1, 37)} for row in rows)
    assert any(row["control_ledger_sha256"] != observed["control_ledger_sha256"] for row in rows)

def test_nested_bootstrap_resamples_controls_inside_sampled_month():
    receipt = nested_family_bootstrap(month_rows, "exp", "cfg")
    assert receipt["replicates"] == 9999
    assert receipt["cluster_unit"] == "utc_calendar_month"
    assert receipt["control_resampling"] == "20_indices_with_replacement_per_sampled_month"
```

- [ ] **Step 2: Run the red inference tests.**

Run: `pytest -q tests/test_xsec_pit_v5_inference.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.xsec_pit_v5_inference'`.

- [ ] **Step 3: Implement the 20 matched controls.**

Sort the causal eligible set by `SHA256(config_fingerprint || rebalance_ts || draw_index || symbol)`. Assign the first `basket_k` symbols long and the next `basket_k` short with the strategy's exact gross weights and executable constraints. Ranked strategy symbols are excluded only from their own event path, not from the broader eligible universe. If eligible count, funding path, or next-open path is insufficient, mark that paired rebalance blocked and stop the family; never redraw after observing an outcome.

```python
def matched_baskets(eligible_symbols, strategy_symbols, arm, config_fingerprint, rebalance_ts, event_id, draw_index, weights):
    candidates = sorted(set(eligible_symbols) - set(strategy_symbols))
    ranked = hash_rank((config_fingerprint, rebalance_ts, str(draw_index)), candidates)
    if len(ranked) < 2 * arm.basket_k:
        raise ReplayBlocked("matched_control_universe_too_small")
    long_gross = sum(value for value in weights.values() if value > 0)
    short_gross = sum(-value for value in weights.values() if value < 0)
    return {
        **{symbol: long_gross / arm.basket_k for symbol in ranked[:arm.basket_k]},
        **{symbol: -short_gross / arm.basket_k for symbol in ranked[arm.basket_k:2 * arm.basket_k]},
    }
```

- [ ] **Step 4: Implement the XSEC stratified null and maxT.**

For each permutation `p`, arm, rebalance, and stratum, rank symbols by `SHA256("xsec_rank_perm_v1" || config_fingerprint || p || rebalance_ts || stratum_id || symbol)`, then reassign causal factor scores only within exact Cartesian strata. Leave strata with fewer than four symbols fixed. Block if fewer than 80% of eligible symbols are in permutable strata or if any arm's long or short basket contains no permutable symbol. Use one mapping for all 36 arms, rebuild weights, all 20 controls, next-open fills, funding, and base/stress costs from zero, and record complete permutation ledgers. Compute the family one-sided p-value with `(1 + count(permuted_stat >= observed_stat)) / 1000`. Compute maxT from studentized mean excess across all 36 arms, with standard errors formed from UTC-month clusters rather than trade rows.

```python
def permutation_mapping(strata, config_fingerprint, permutation_index, rebalance_ts):
    mapping = {}
    for stratum_id in sorted(strata):
        symbols = tuple(strata[stratum_id])
        if len(symbols) < 4:
            mapping[stratum_id] = symbols
            continue
        mapping[stratum_id] = tuple(hash_rank(
            ("xsec_rank_perm_v1", config_fingerprint, str(permutation_index), rebalance_ts, stratum_id),
            symbols,
        ))
    return mapping

def studentized_max_t(arm_month_excess):
    means = {arm: statistics.fmean(values) for arm, values in arm_month_excess.items()}
    standard_errors = {
        arm: statistics.stdev(values) / math.sqrt(len(values))
        if len(values) > 1 and statistics.stdev(values) > 0 else 0.0
        for arm, values in arm_month_excess.items()
    }
    return max((means[arm] / standard_errors[arm] if standard_errors[arm] else 0.0) for arm in sorted(means))
```

- [ ] **Step 5: Implement the nested UTC-month bootstrap and primary effect.**

Aggregate each arm's monthly stress excess as strategy net log return minus the mean of its 20 same-month control net log-return ledgers. Compute arm annualized excess as `100 * (exp(12 * mean(monthly_excess)) - 1)` percentage points and family statistic as the median of the 36 arm statistics. For each of 9999 replicates, sample UTC months with replacement using `bootstrap_v1`; within each sampled month sample the 20 control indices with replacement, recompute means, then recompute the family median. Return percentile `[2.5%, 97.5%]`, raw rebalance units, and independent UTC-month counts.

```python
def nested_family_bootstrap(month_rows, experiment_id, config_fingerprint):
    months = sorted(month_rows)
    sampled = cluster_bootstrap_indices(experiment_id, config_fingerprint, len(months), sample_size=len(months))
    statistics_by_replicate = []
    for replicate, month_indices in enumerate(sampled):
        arm_values = {arm: [] for arm in sorted(month_rows[months[0]])}
        for draw_index, month_index in enumerate(month_indices):
            month = month_rows[months[month_index]]
            control_indices = [stable_index(
                f"bootstrap_v1||{experiment_id}||{config_fingerprint}||{replicate}||{draw_index}||{control_index}", 20
            ) for control_index in range(20)]
            for arm in sorted(arm_values):
                row = month[arm]
                control_mean = statistics.fmean(row["controls"][index] for index in control_indices)
                arm_values[arm].append(row["strategy"] - control_mean)
        annualized = [100.0 * (math.exp(12.0 * statistics.fmean(values)) - 1.0) for values in arm_values.values()]
        statistics_by_replicate.append(statistics.median(annualized))
    return {
        "replicates": 9999,
        "cluster_unit": "utc_calendar_month",
        "control_resampling": "20_indices_with_replacement_per_sampled_month",
        "percentile_interval": percentile_interval(statistics_by_replicate),
    }
```

- [ ] **Step 6: Run inference tests and arithmetic checks.**

Run: `pytest -q tests/test_xsec_pit_v5_inference.py tests/test_money_research_controls_v1.py`

Expected: all tests PASS; seed replay is byte-identical, permutation count is 999, bootstrap count is 9999, all 36 arms share one mapping per permutation, and the bootstrap receipt proves controls were resampled inside months.

- [ ] **Step 7: Commit inference.**

```bash
git add research_lab/xsec_pit_v5_inference.py tests/test_xsec_pit_v5_inference.py
git commit -m "feat: add XSEC matched controls and cluster inference"
```

### Task 5: Add independent audit, terminal diagnostic verdict, and runner

**Files:**
- Create: `research_lab/audit_xsec_pit_v5.py`
- Create: `scripts/run_xsec_pit_v5.py`
- Test: `tests/test_audit_xsec_pit_v5.py`
- Test: `tests/test_run_xsec_pit_v5.py`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/run_passport.json`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/result.json`
- Output (write-once): `research_lab/results/xsec_pit_v5_20260829/independent_audit.json`

**Interfaces:**
- `audit_xsec_result(result_dir: Path) -> dict[str, Any]` reads only manifests, raw strategy/control/permutation ledgers, and passport; independently recomputes all key counts, costs, funding, monthly excess, annualized family median, p-values, bootstrap interval, concentration, folds, and champion/reference values.
- `diagnostic_verdict(metrics: Mapping[str, Any], audit: Mapping[str, Any]) -> str` returns exactly one of `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW`, `FAIL_RESEARCH`, or `BLOCKED_DATA_OR_PARITY`.
- `run_once(prereg_path: Path, control_path: Path, preflight_dir: Path, out_dir: Path, owner_token: str) -> dict[str, Any]` writes the passport before scoring, rejects a reused output or wrong token, runs all arms/inference, runs the independent audit, and writes a result with `promotion_authority: false`.

- [ ] **Step 1: Write failing audit and runner tests.**

```python
def test_audit_recomputes_monthly_excess_and_detects_ledger_drift(tmp_path):
    write_valid_xsec_tree(tmp_path)
    assert audit_xsec_result(tmp_path)["verdict"] == "AUDIT_PASS_RESEARCH_ONLY"
    tamper_jsonl(tmp_path / "strategy_ledger.jsonl", field="net_log_return", value=0.5)
    assert audit_xsec_result(tmp_path)["verdict"] == "AUDIT_FAIL"

def test_runner_is_write_once_and_never_promotes(tmp_path):
    result = run_once(PREREG, CONTRACT, PREFLIGHT, tmp_path, "RUN_XSEC_PIT_V5_ONCE")
    assert result["promotion_authority"] is False
    assert result["verdict"] in {"DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW", "FAIL_RESEARCH", "BLOCKED_DATA_OR_PARITY"}
    with pytest.raises(RunBlocked, match="write-once"):
        run_once(PREREG, CONTRACT, PREFLIGHT, tmp_path, "RUN_XSEC_PIT_V5_ONCE")

def test_failed_pit_never_becomes_positive_result(tmp_path):
    metrics = metrics_with_missing_terminal_month()
    assert diagnostic_verdict(metrics, {"verdict": "AUDIT_FAIL"}) == "BLOCKED_DATA_OR_PARITY"
```

- [ ] **Step 2: Run the red tests.**

Run: `pytest -q tests/test_audit_xsec_pit_v5.py tests/test_run_xsec_pit_v5.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.audit_xsec_pit_v5'`.

- [ ] **Step 3: Implement the independent arithmetic audit.**

Do not import the replay's metric functions into the audit. Re-read raw ledgers and verify: exact 36 arm IDs; one closed strategy unit and 20 closed controls for every scheduled rebalance/month; chronological signal < next-open entry < exit; funding and costs equal ledger components; no duplicate decision/event IDs; manifests/passport/config hashes match; all 999 permutation rows and 9999 bootstrap metadata are present; maxT includes all arms; and no terminal integrity receipt is hidden. Emit `schema_id: xsec_pit_v5_independent_audit_v1`, `verdict: AUDIT_PASS_RESEARCH_ONLY|AUDIT_FAIL`, `errors`, `recomputed`, `source_hashes`, and `capital_authorized: false`.

```python
def audit_xsec_result(result_dir):
    errors = []
    strategy = read_jsonl(result_dir / "strategy_ledger.jsonl")
    controls = read_jsonl(result_dir / "control_ledger.jsonl")
    expected_arms = {f"trial_{index:02d}" for index in range(1, 37)}
    if {row["arm_id"] for row in strategy} != expected_arms:
        errors.append("strategy_arm_set_mismatch")
    grouped = group_by((row["arm_id"], row["decision_id"]) for row in controls)
    for key, rows in grouped.items():
        terminal = [row for row in rows if row["status"] == "terminal"]
        if len(terminal) != 20:
            errors.append(f"control_count:{key[0]}:{key[1]}")
    for row in [*strategy, *controls]:
        if row["status"] == "terminal" and not (row["signal_ts_utc"] < row["entry_ts_utc"] < row["exit_ts_utc"]):
            errors.append(f"causal_order:{row['decision_id']}")
    recomputed = recompute_monthly_effects(strategy, controls)
    expected = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    if recomputed["family_median_annualized_excess"] != expected["metrics"]["family_median_annualized_excess"]:
        errors.append("family_metric_drift")
    return {
        "schema_id": "xsec_pit_v5_independent_audit_v1",
        "verdict": "AUDIT_PASS_RESEARCH_ONLY" if not errors else "AUDIT_FAIL",
        "errors": errors,
        "recomputed": recomputed,
        "capital_authorized": False,
    }
```

- [ ] **Step 4: Implement the diagnostic gate with exact thresholds.**

Return `BLOCKED_DATA_OR_PARITY` for any PIT, funding, execution, integrity, audit, or missing-terminal-unit failure. Otherwise return `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` only when PIT checks pass; base and stress family median, champion stress, and reference stress are strictly positive; at least 3/4 folds are positive; at least 24/36 arms are stress-positive; largest positive symbol contribution is `<=35%`; family median stress excess over controls is at least `2` annualized percentage points; family p-value is `<=0.05`; champion and reference maxT-adjusted p-values are `<=0.05`; and reference excess exceeds one standard deviation of its control outcomes. Any other complete run returns `FAIL_RESEARCH`. Include the diagnostic-only reopen condition and never emit a prospective or capital verdict from this function.

```python
def diagnostic_verdict(metrics, audit):
    if audit.get("verdict") != "AUDIT_PASS_RESEARCH_ONLY" or metrics.get("pit_execution_checks") != "PASS":
        return "BLOCKED_DATA_OR_PARITY"
    passes = (
        metrics["base_family_median"] > 0
        and metrics["stress_family_median"] > 0
        and metrics["champion_stress"] > 0
        and metrics["reference_stress"] > 0
        and metrics["positive_folds"] >= 3
        and metrics["positive_arms"] >= 24
        and metrics["largest_symbol_contribution"] <= 0.35
        and metrics["stress_excess_annualized"] >= 2.0
        and metrics["family_p_value"] <= 0.05
        and metrics["champion_max_t_p_value"] <= 0.05
        and metrics["reference_max_t_p_value"] <= 0.05
        and metrics["reference_excess_over_control_sd"] > 1.0
    )
    return "DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW" if passes else "FAIL_RESEARCH"
```

- [ ] **Step 5: Implement the write-once CLI and passport binding.**

The CLI must accept exactly these research inputs and no network/broker flags:

```bash
python scripts/run_xsec_pit_v5.py \
  --prereg configs/research/xsec_pit_v5_preregistration.json \
  --control-contract configs/research/money_research_sprint_v1_control_contract.json \
  --preflight-dir research_lab/results/xsec_pit_v5_20260829/preflight \
  --out-dir research_lab/results/xsec_pit_v5_20260829 \
  --owner-token RUN_XSEC_PIT_V5_ONCE
```

Build `research_run_passport_v1` before opening outcome rows using `research_lab.run_passport.build_passport`; bind every code path, prereg, shared contract, three manifests, archive status, and data window to `experiment_id: xsec_pit_v5_20260829`. Append lifecycle stages through `research_lab.experiment_lifecycle.LifecycleLedger`; a nonzero preflight, result, or independent audit cannot pass. Use `write_once` for every result artifact.

```python
def run_once(prereg_path, control_path, preflight_dir, out_dir, owner_token):
    if owner_token != "RUN_XSEC_PIT_V5_ONCE":
        raise RunBlocked("exact owner token required")
    if (out_dir / "result.json").exists() or (out_dir / "run_passport.json").exists():
        raise RunBlocked("write-once output already exists")
    preflight = read_json(preflight_dir / "receipt.json")
    if preflight.get("status") != "PASS":
        return write_terminal_result(out_dir, "BLOCKED_DATA_OR_PARITY", preflight["reason_code"])
    passport = build_passport(build_xsec_passport_request(prereg_path, control_path, preflight_dir), project_root=ROOT)
    write_passport(out_dir / "run_passport.json", passport)
    observed = replay_and_infer(load_prereg(prereg_path), load_inputs(preflight_dir), load_control_contract(control_path))
    audit = audit_xsec_result(out_dir)
    verdict = diagnostic_verdict(observed["metrics"], audit)
    result = {"experiment_id": "xsec_pit_v5_20260829", "verdict": verdict, "metrics": observed["metrics"], "promotion_authority": False, "capital_authorized": False}
    write_once(out_dir / "result.json", result)
    write_once(out_dir / "independent_audit.json", audit)
    return result
```

- [ ] **Step 6: Run targeted tests and the bounded runner.**

Run: `pytest -q tests/test_audit_xsec_pit_v5.py tests/test_run_xsec_pit_v5.py tests/test_xsec_pit_v5_data.py tests/test_xsec_pit_v5_replay.py tests/test_xsec_pit_v5_inference.py`

Expected: all tests PASS, and the runner's `result.json` contains exactly one diagnostic terminal verdict, `capital_authorized: false`, `promotion_authority: false`, and SHA references to every ledger and audit.

- [ ] **Step 7: Commit the audited runner.**

```bash
git add research_lab/audit_xsec_pit_v5.py scripts/run_xsec_pit_v5.py tests/test_audit_xsec_pit_v5.py tests/test_run_xsec_pit_v5.py
git commit -m "feat: add independently audited XSEC PIT verdict"
```

### Task 6: Add the prospective zero-risk shadow gate and final verification

**Files:**
- Create: `research_lab/xsec_pit_v5_shadow_gate.py`
- Create: `scripts/xsec_pit_v5_shadow.py`
- Create: `scripts/run_xsec_pit_v5_shadow_loop.sh`
- Test: `tests/test_xsec_pit_v5_shadow_gate.py`

**Interfaces:**
- `evaluate_shadow_authority(diagnostic_result: Mapping[str, Any]) -> dict[str, Any]` returns `allowed: true` only for `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` with a passing independent audit and all authority flags false.
- `evaluate_prospective_shadow(rows: Sequence[Mapping[str, Any]], now_utc: datetime) -> dict[str, Any]` returns `PROSPECTIVE_SHADOW_EVIDENCE_PASS` only after `>=90` UTC days, `>=30` terminal reference-arm intervals, `>=12` UTC weeks, positive stress excess over a concurrently operating control, 95% cluster-bootstrap lower bound above zero, and zero integrity incidents; otherwise returns `IN_PROGRESS` or `FAIL_PROSPECTIVE_SHADOW` without altering historical parameters.
- `run_shadow_tick(inputs: ShadowInputs, output: Path) -> dict[str, Any]` records signal timestamp, intended/observable next fill, latency, gaps, stop/target lifecycle, decision reason codes, control outcome, heartbeat, and reconciliation, with `orders_sent: false`, `private_api_calls: false`, and `live_write_authority: false`.
- `build_public_snapshot_receipt(inputs: ShadowInputs) -> dict[str, Any]` validates an already-materialized public snapshot and emits no network call; `append_write_once_jsonl(output: Path, receipt: Mapping[str, Any]) -> None` rejects a duplicate event ID with different bytes.
- `cluster_bootstrap_lower_bound(rows: Sequence[Mapping[str, Any]]) -> float` uses the shared 9999-replicate UTC-date cluster bootstrap and returns its 2.5th percentile.

- [ ] **Step 1: Write failing shadow-gate tests.**

```python
def test_only_diagnostic_support_allows_zero_risk_shadow():
    safe = {
        "verdict": "DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW", "audit_pass": True,
        "promotion_authority": False, "capital_authorized": False,
        "order_authority": False, "private_api_authority": False,
        "live_write_authority": False,
    }
    assert evaluate_shadow_authority(safe)["allowed"] is True
    assert evaluate_shadow_authority({**safe, "order_authority": True})["allowed"] is False
    assert evaluate_shadow_authority({**safe, "verdict": "FAIL_RESEARCH"})["allowed"] is False

def test_prospective_gate_requires_all_freshness_and_control_conditions():
    assert evaluate_prospective_shadow(rows(days=89), now_utc())["verdict"] == "IN_PROGRESS"
    result = evaluate_prospective_shadow(rows(days=90, reference_intervals=30, weeks=12, lower_bound=0.01), now_utc())
    assert result["verdict"] == "PROSPECTIVE_SHADOW_EVIDENCE_PASS"
    assert evaluate_prospective_shadow(rows(days=90, reference_intervals=30, weeks=12, incidents=1), now_utc())["verdict"] == "FAIL_PROSPECTIVE_SHADOW"

def test_shadow_tick_is_orderless_and_reconciles_intended_fill():
    receipt = run_shadow_tick(synthetic_shadow_inputs(), tmp_path / "shadow.jsonl")
    assert receipt["orders_sent"] is False
    assert receipt["private_api_calls"] is False
    assert receipt["live_write_authority"] is False
    assert receipt["intended_fill_ts_utc"] < receipt["exit_ts_utc"]
```

- [ ] **Step 2: Run the red tests.**

Run: `pytest -q tests/test_xsec_pit_v5_shadow_gate.py`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'research_lab.xsec_pit_v5_shadow_gate'`.

- [ ] **Step 3: Implement the orderless shadow receipt and gate.**

Consume only the immutable diagnostic result and new public market snapshots. Do not import private-client/order/cancel/replace/close paths. The shell loop must use the existing research lock pattern and run `python scripts/xsec_pit_v5_shadow.py` with a separate `runtime/xsec_pit_v5_shadow` path; a failed tick remains a failure receipt and is not swallowed as a no-signal tick.

```python
@dataclass(frozen=True)
class ShadowInputs:
    experiment_id: str
    config_fingerprint: str
    event_id: str
    source_hash: str
    signal_ts_utc: str
    next_open_ts_utc: str
    exit_ts_utc: str
    observable_fill: float
    control_outcome: float
    reconciliation: Mapping[str, Any]
    terminal_reference_interval: bool
    stress_excess: float

def build_public_snapshot_receipt(inputs):
    if not inputs.event_id or not inputs.source_hash:
        raise ValueError("event_id_and_source_hash_required")
    if inputs.signal_ts_utc >= inputs.next_open_ts_utc or inputs.next_open_ts_utc >= inputs.exit_ts_utc:
        raise ValueError("non_causal_shadow_timestamps")
    return {
        "experiment_id": inputs.experiment_id,
        "config_fingerprint": inputs.config_fingerprint,
        "event_id": inputs.event_id,
        "source_hash": inputs.source_hash,
        "heartbeat_utc": datetime.now(timezone.utc).isoformat(),
        "terminal_reference_interval": inputs.terminal_reference_interval,
        "stress_excess": inputs.stress_excess,
    }

def append_write_once_jsonl(output, receipt):
    output.parent.mkdir(parents=True, exist_ok=True)
    canonical = json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"))
    existing = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()] if output.exists() else []
    same = [row for row in existing if row.get("event_id") == receipt.get("event_id")]
    if same and json.dumps(same[0], sort_keys=True, separators=(",", ":")) != canonical:
        raise ValueError("event_id_reused_with_different_receipt")
    if not same:
        with output.open("a", encoding="utf-8") as handle:
            handle.write(canonical + "\n")

def evaluate_shadow_authority(diagnostic_result):
    allowed = (
        diagnostic_result.get("verdict") == "DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW"
        and diagnostic_result.get("audit_pass") is True
        and diagnostic_result.get("promotion_authority") is False
        and diagnostic_result.get("capital_authorized") is False
        and diagnostic_result.get("order_authority") is False
        and diagnostic_result.get("private_api_authority") is False
        and diagnostic_result.get("live_write_authority") is False
    )
    return {"allowed": allowed, "authority": "research_only_no_live_or_promotion"}

def run_shadow_tick(inputs, output):
    receipt = build_public_snapshot_receipt(inputs)
    receipt.update({
        "schema_id": "xsec_pit_v5_shadow_receipt_v1",
        "orders_sent": False,
        "private_api_calls": False,
        "live_write_authority": False,
        "signal_ts_utc": inputs.signal_ts_utc,
        "intended_fill_ts_utc": inputs.next_open_ts_utc,
        "exit_ts_utc": inputs.exit_ts_utc,
        "observable_fill": inputs.observable_fill,
        "control_outcome": inputs.control_outcome,
        "reconciliation": inputs.reconciliation,
    })
    append_write_once_jsonl(output, receipt)
    return receipt

def cluster_bootstrap_lower_bound(rows):
    if not rows:
        return 0.0
    clusters = sorted({row["signal_ts_utc"][:10] for row in rows})
    by_cluster = {
        cluster: statistics.fmean(row["stress_excess"] for row in rows if row["signal_ts_utc"].startswith(cluster))
        for cluster in clusters
    }
    indices = cluster_bootstrap_indices(
        rows[0]["experiment_id"], rows[0]["config_fingerprint"], len(clusters),
        sample_size=len(clusters), replicates=9999,
    )
    values = [statistics.fmean(by_cluster[clusters[index]] for index in sample) for sample in indices]
    return percentile_interval(values)[0]

def evaluate_prospective_shadow(rows, now_utc):
    terminal = [row for row in rows if row.get("terminal_reference_interval")]
    dates = {row["signal_ts_utc"][:10] for row in rows}
    weeks = {datetime.fromisoformat(row["signal_ts_utc"].replace("Z", "+00:00")).isocalendar()[:2] for row in rows}
    lower_bound = cluster_bootstrap_lower_bound(rows)
    incidents = [row for row in rows if row.get("reconciliation", {}).get("status") != "PASS"]
    observed_days = (now_utc.date() - min(datetime.fromisoformat(row["signal_ts_utc"].replace("Z", "+00:00")).date() for row in rows)).days + 1 if rows else 0
    if incidents:
        verdict = "FAIL_PROSPECTIVE_SHADOW"
    elif observed_days >= 90 and len(terminal) >= 30 and len(weeks) >= 12 and statistics.fmean(row["stress_excess"] for row in terminal) > 0.0 and lower_bound > 0.0:
        verdict = "PROSPECTIVE_SHADOW_EVIDENCE_PASS"
    else:
        verdict = "IN_PROGRESS"
    return {"verdict": verdict, "days": observed_days, "terminal_intervals": len(terminal), "weeks": len(weeks), "lower_bound": lower_bound, "integrity_incidents": len(incidents), "money_authority": False}
```

- [ ] **Step 4: Run shadow tests and static authority checks.**

Run: `pytest -q tests/test_xsec_pit_v5_shadow_gate.py`

Expected: all tests PASS.

Run: `rg -n "(requests|urllib|ccxt|create_order|submit_order|cancel_order|replace_order|close_position|private_api_authority\s*=\s*True|order_authority\s*=\s*True)" research_lab/xsec_pit_v5_shadow_gate.py scripts/xsec_pit_v5_shadow.py scripts/run_xsec_pit_v5_shadow_loop.sh`

Expected: no matches; the zero-risk shadow reads only already-materialized public snapshots.

- [ ] **Step 5: Run the complete XSEC verification gate.**

Run: `pytest -q tests/test_money_research_controls_v1.py tests/test_xsec_pit_v5_preregistration.py tests/test_xsec_pit_v5_data.py tests/test_xsec_pit_v5_replay.py tests/test_xsec_pit_v5_inference.py tests/test_audit_xsec_pit_v5.py tests/test_run_xsec_pit_v5.py tests/test_xsec_pit_v5_shadow_gate.py tests/test_xsec_causal_contract.py tests/test_xsec_causal_replay.py`

Expected: all targeted tests PASS and no output claims OOS, promotion, money authority, or live execution.

Run: `git diff --check`

Expected: exit 0.

Run: `python3 -m py_compile research_lab/money_research_controls_v1.py research_lab/xsec_pit_v5_data.py research_lab/xsec_pit_v5_replay.py research_lab/xsec_pit_v5_inference.py research_lab/audit_xsec_pit_v5.py scripts/run_xsec_pit_v5.py research_lab/xsec_pit_v5_shadow_gate.py scripts/xsec_pit_v5_shadow.py`

Expected: exit 0.

- [ ] **Step 6: Commit the shadow boundary and hand off the exact evidence paths.**

```bash
git add research_lab/xsec_pit_v5_shadow_gate.py scripts/xsec_pit_v5_shadow.py scripts/run_xsec_pit_v5_shadow_loop.sh tests/test_xsec_pit_v5_shadow_gate.py
git commit -m "feat: gate XSEC PIT diagnostic into zero-risk shadow"
```

Report to the owner: `research_lab/results/xsec_pit_v5_20260829/result.json`, `independent_audit.json`, `preflight/receipt.json`, strategy/control/permutation ledgers, and the exact `config_fingerprint`. If any blocker occurs, retain all failure receipts and report `BLOCKED_DATA_OR_PARITY` with its reason code; never replace the run with survivor-only PnL.

## Self-review checklist

- [ ] Confirm the 36 arms come only from the published preregistered grid and no new champion can be selected.
- [ ] Confirm membership and liquidity manifests are immutable and every rebalance has a causal as-of audit.
- [ ] Confirm all 20 controls use the same gross exposure, side, month, maturity/regime/liquidity bucket, horizon, executable constraints, funding, and costs.
- [ ] Confirm 999 permutations rebuild all 36 strategy/control paths and use one stratified mapping; no sign-flip shortcut exists.
- [ ] Confirm 9999 bootstrap replicates resample UTC months and then control indices inside each sampled month.
- [ ] Confirm independent audit recomputes from raw ledgers without importing replay metric functions.
- [ ] Confirm diagnostic verdicts cannot emit prospective PASS or money authority and shadow receipts prove orders/private API/live writes are false.
- [ ] Confirm every code-changing step has a red test, exact command, expected result, and commit.
