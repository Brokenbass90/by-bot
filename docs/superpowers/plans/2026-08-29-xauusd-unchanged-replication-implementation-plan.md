# XAUUSD Unchanged Replication V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproduce the frozen XAUUSD H1 `session_breakout_retest` diagnostic on an independent causal feed, audit it against matched controls and executable costs, and—only after every gate passes—start a zero-order MT5 demo journal with no broker-order authority.

**Architecture:** Keep the old close-fill result as an explicitly diagnostic, bit-reproducible lane and build independent data, next-open/bid-ask repricing, matched-control inference, and audit layers around it. Every layer consumes hash-pinned inputs and emits immutable receipts; no layer can silently upgrade a diagnostic result into shadow or money authority.

**Tech Stack:** Python 3 standard library, pytest, existing `bot.fx_harness`, `bot.fx_setups`, `bot.xau_mt5_zero_order_paper`, JSON/JSONL/CSV receipts, SHA-256, OANDA public market-data materializer or owner-provided Bullwaves MT5 demo export.

**Spec:** `docs/superpowers/specs/2026-08-29-money-research-sprint-v1-design.md`

## Global Constraints

- Authority is exactly `research_only_no_live_or_promotion`; `promotion_authority`, `network_authority`, `private_api_authority`, `order_authority`, and `live_write_authority` are all `false` in every generated manifest and receipt.
- Do not modify live risk, live geometry, slots, Alpaca `SAFE_HOLD`, broker orders, credentials, or money authority.
- Repeat exactly one setup: XAUUSD, H1 aggregated from M5, `session_breakout_retest`, `sessions=(london,london_ny_overlap,newyork)`, `level_lookback=120`, `events=None`, `tp_rr=2.0`, `sl_atr=1.5`, `max_hold=6`, stop-first, force-flat at the first subsequent complete H1 bar at or after 20:55 UTC.
- Static UTC sessions are immutable: London `[07:00,12:00)`, overlap `[12:00,16:00)`, New York `[16:00,21:00)`; DST does not shift labels.
- Base costs are `fee/spread_proxy_bps_per_side=1.0` plus `slippage_bps_per_side=0.5`; stress costs are `2.0 + 1.0` until broker-calibrated spread, slippage, swap, and commission data exist.
- The unchanged close-fill replay may emit only `DIAGNOSTIC_REPLICATION_PASS`, `DIAGNOSTIC_REPLICATION_FAIL`, or `BLOCKED_DATA_OR_PARITY`.
- `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` requires independent feed parity, next-open/bid-ask repricing parity, broker-calibrated costs, every historical statistical gate, and an independent audit PASS.
- Raw M5 schema is exactly `[open_ts_utc_seconds, open, high, low, close, volume]`; rows are half-open `[open_ts, open_ts+300)`, strictly increasing, unique, and valid OHLC.
- H1 bucket is `floor(open_ts/3600)*3600`; ordinary incomplete buckets are rejected, scheduled closure/holiday boundaries are explicit receipt rows and are never interpolated.
- The common control contract is `configs/research/money_research_sprint_v1_control_contract.json`: 20 deterministic controls, 999 blocked permutations, 9999 UTC-entry-session-date cluster bootstrap replicates.
- All historical windows are exposed diagnostics. A positive result can authorize only a preregistered zero-risk shadow; it cannot authorize live trading.
- Exceptions, missing hashes, missing future bars, absent bid/ask, fewer than 20 eligible controls, stale quotes, source drift, or reconciliation incidents fail closed and remain visible in terminal receipts.
- Secrets are never printed, persisted, hashed into public receipts, or read by tests. OANDA download is an owner-authorized market-data action; Bullwaves input is a deterministic demo export only after token rotation and demo-identity confirmation.

---

## File and interface map

- `configs/research/xauusd_unchanged_replication_v1.json`: frozen machine-readable experiment contract.
- `research_lab/prereg/PREREG_XAUUSD_UNCHANGED_REPLICATION_V1_2026_08_29.md`: human preregistration and reopen conditions.
- `research_lab/xau_data_contract_v1.py`: raw-M5 validation, closure-map validation, complete-H1 aggregation, and feed-overlap reconciliation.
- `scripts/preflight_xauusd_unchanged_replication_v1.py`: pin config/code/prereg/control/data hashes and emit a fail-closed preflight receipt.
- `research_lab/xau_unchanged_replication_v1.py`: exact diagnostic close-fill replay wrapper and canonical ledgers.
- `research_lab/xau_execution_parity_v1.py`: next-open/bid-ask repricing and broker-cost parity without changing the unchanged ledger.
- `research_lab/xau_matched_control_v1.py`: XAU-specific eligible-set construction over the shared deterministic control primitives.
- `scripts/run_xauusd_unchanged_replication_v1.py`: ordered preflight, diagnostic, repricing, control, and verdict orchestration.
- `scripts/audit_xauusd_unchanged_replication_v1.py`: independent hash and arithmetic recomputation from raw ledgers.
- `scripts/run_xauusd_zero_order_shadow_v1.py`: public-quote/demo-only shadow journal; imports no order client.
- `tests/fixtures/xau_replication_v1/`: synthetic M5, closure-map, bid/ask, and cost fixtures with no credentials.
- `tests/test_xau_data_contract_v1.py`, `tests/test_xau_unchanged_replication_v1.py`, `tests/test_xau_execution_parity_v1.py`, `tests/test_xau_matched_control_v1.py`, `tests/test_audit_xauusd_unchanged_replication_v1.py`, `tests/test_run_xauusd_zero_order_shadow_v1.py`: focused TDD suites.

The shared control module and its exact signatures are produced by the XSEC PIT V5 plan before Task 5 executes:

- `hash_rank(seed_parts: Sequence[str], values: Sequence[str]) -> list[str]`
- `one_sided_p_value(observed: float, permuted: Sequence[float]) -> float`
- `percentile_interval(values: Sequence[float], *, lower_pct: float = 2.5, upper_pct: float = 97.5) -> tuple[float, float]`
- `cluster_bootstrap_indices(experiment_id: str, config_fingerprint: str, cluster_count: int, *, sample_size: int | None = None, replicates: int = 9999) -> list[list[int]]`
- `paired_label_permutations(cluster_ids: Sequence[str], family_id: str, config_fingerprint: str, *, permutations: int = 999) -> list[dict[str, int]]`

Task 5 must stop with `BLOCKED_SHARED_CONTROL_CONTRACT` if these symbols or the pinned shared-config SHA are absent; it must not create a local RNG substitute.

### Task 1: Freeze the XAU experiment and preflight contract

**Files:**
- Create: `configs/research/xauusd_unchanged_replication_v1.json`
- Create: `research_lab/prereg/PREREG_XAUUSD_UNCHANGED_REPLICATION_V1_2026_08_29.md`
- Create: `scripts/preflight_xauusd_unchanged_replication_v1.py`
- Test: `tests/test_preflight_xauusd_unchanged_replication_v1.py`

**Interfaces:**
- Consumes: the approved design spec, `configs/research/money_research_sprint_v1_control_contract.json`, a data manifest path supplied on the CLI, and exact code paths named in the config.
- Produces: `build_preflight(config_path: Path, data_manifest_path: Path) -> dict[str, Any]` and a JSON receipt whose `verdict` is `PASS` or `BLOCKED_DATA_OR_PARITY`.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_preflight_pins_authority_engine_and_all_inputs(tmp_path):
    receipt = build_preflight(CONFIG, fixture_manifest(tmp_path))
    assert receipt["authority"] == "research_only_no_live_or_promotion"
    assert all(receipt[name] is False for name in (
        "promotion_authority", "network_authority", "private_api_authority",
        "order_authority", "live_write_authority",
    ))
    assert receipt["measurement"]["setup_kwargs"] == {
        "events": None,
        "level_lookback": 120,
        "sessions": ["london", "london_ny_overlap", "newyork"],
    }
    assert receipt["measurement"]["tp_rr"] == 2.0
    assert receipt["measurement"]["sl_atr"] == 1.5
    assert receipt["measurement"]["max_hold_h1_bars"] == 6
    assert receipt["hashes"]["control_contract_sha256"]

def test_preflight_fails_closed_on_hash_or_authority_drift(tmp_path):
    manifest = fixture_manifest(tmp_path)
    manifest.write_text('{"authority":"live"}\n', encoding="utf-8")
    receipt = build_preflight(CONFIG, manifest)
    assert receipt["verdict"] == "BLOCKED_DATA_OR_PARITY"
    assert "data_manifest_authority" in receipt["failures"]
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest -q tests/test_preflight_xauusd_unchanged_replication_v1.py`

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.preflight_xauusd_unchanged_replication_v1'`.

- [ ] **Step 3: Write the frozen JSON and human preregistration**

The JSON must contain this exact core, plus the file-hash list and terminal gates copied from the spec:

```json
{
  "schema_id": "xauusd_unchanged_replication_v1",
  "experiment_id": "xauusd_unchanged_replication_v1_20260829",
  "authority": "research_only_no_live_or_promotion",
  "promotion_authority": false,
  "network_authority": false,
  "private_api_authority": false,
  "order_authority": false,
  "live_write_authority": false,
  "symbol": "XAUUSD",
  "source_timeframe": "M5",
  "decision_timeframe": "H1",
  "setup": "session_breakout_retest",
  "setup_kwargs": {
    "events": null,
    "level_lookback": 120,
    "sessions": ["london", "london_ny_overlap", "newyork"]
  },
  "tp_rr": 2.0,
  "sl_atr": 1.5,
  "max_hold_h1_bars": 6,
  "force_flat_utc_minute": 1255,
  "intrabar_priority": "stop_first",
  "diagnostic_entry": "signal_h1_close",
  "executable_candidate_entry": "next_complete_h1_open_side_correct_bid_ask",
  "base_cost_bps_per_side": {"fee_spread_proxy": 1.0, "slippage": 0.5},
  "stress_cost_bps_per_side": {"fee_spread_proxy": 2.0, "slippage": 1.0},
  "matched_control_draws": 20,
  "blocked_permutations": 999,
  "cluster_bootstraps": 9999,
  "cluster_unit": "utc_entry_session_date",
  "control_contract_path": "configs/research/money_research_sprint_v1_control_contract.json"
}
```

The Markdown preregistration must state the known old diagnostic (`N=13`, base `+3.915R`, stress `+3.012R`, stress PF `1.526`, 3/4 positive folds), mark `N<30` as binding, and state that unchanged history cannot authorize money.

- [ ] **Step 4: Implement minimal hash-bound preflight**

```python
REQUIRED_FALSE = (
    "promotion_authority", "network_authority", "private_api_authority",
    "order_authority", "live_write_authority",
)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def build_preflight(config_path: Path, data_manifest_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = json.loads(data_manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if config.get("authority") != "research_only_no_live_or_promotion":
        failures.append("config_authority")
    if data.get("authority") != "research_only_no_live_or_promotion":
        failures.append("data_manifest_authority")
    failures.extend(name for name in REQUIRED_FALSE if config.get(name) is not False)
    hashes = {path: sha256_file(ROOT / path) for path in config["pinned_paths"]}
    return {
        "schema_id": "xauusd_unchanged_replication_preflight_v1",
        **{name: config[name] for name in ("authority", *REQUIRED_FALSE)},
        "measurement": {key: config[key] for key in (
            "setup", "setup_kwargs", "tp_rr", "sl_atr", "max_hold_h1_bars",
            "force_flat_utc_minute", "intrabar_priority", "diagnostic_entry",
        )},
        "hashes": {**hashes, "data_manifest_sha256": sha256_file(data_manifest_path)},
        "failures": sorted(set(failures)),
        "verdict": "PASS" if not failures else "BLOCKED_DATA_OR_PARITY",
    }
```

- [ ] **Step 5: Run the focused tests and preflight fixture**

Run: `pytest -q tests/test_preflight_xauusd_unchanged_replication_v1.py`

Expected: all tests pass; fixture receipt contains no absolute credential path or token-shaped value.

- [ ] **Step 6: Commit the frozen contract**

```bash
git add configs/research/xauusd_unchanged_replication_v1.json research_lab/prereg/PREREG_XAUUSD_UNCHANGED_REPLICATION_V1_2026_08_29.md scripts/preflight_xauusd_unchanged_replication_v1.py tests/test_preflight_xauusd_unchanged_replication_v1.py
git commit -m "research: freeze XAUUSD unchanged replication contract"
```

### Task 2: Build the independent XAU data/parity contract

**Files:**
- Create: `research_lab/xau_data_contract_v1.py`
- Create: `tests/fixtures/xau_replication_v1/m5_complete.csv`
- Create: `tests/fixtures/xau_replication_v1/m5_incomplete.csv`
- Create: `tests/fixtures/xau_replication_v1/closure_map.json`
- Create: `tests/test_xau_data_contract_v1.py`
- Create: `scripts/import_xau_mt5_demo_export_v1.py`
- Create: `tests/test_import_xau_mt5_demo_export_v1.py`
- Modify: `scripts/materialize_xau_oanda_preholdout.py:33-286`

**Interfaces:**
- Consumes: raw OANDA M5 rows or an owner-provided Bullwaves demo export, explicit `[start_utc,end_utc)` bounds, and a closure map.
- Produces: `validate_m5_rows(rows: Sequence[M5Bar]) -> list[str]`, `aggregate_complete_h1(rows: Sequence[M5Bar], closures: Sequence[Closure]) -> tuple[list[H1Bar], list[dict[str, Any]]]`, `reconcile_overlap(candidate: Sequence[M5Bar], reference: Sequence[M5Bar]) -> dict[str, Any]`, `import_mt5_demo_export(input_path: Path, demo_identity_path: Path, out_dir: Path) -> Path`, `select_independent_source(oanda_manifest: Path | None, mt5_manifest: Path | None) -> dict[str, Any]`, `load_xau_dataset(manifest_path: Path) -> XauDataset`, and an immutable `xau_data_manifest_v1`.

- [ ] **Step 1: Write RED tests for row integrity and complete aggregation**

```python
def test_m5_contract_rejects_duplicate_non_monotonic_and_invalid_ohlc():
    assert validate_m5_rows([bar(0), bar(0)]) == ["duplicate_timestamp:0"]
    assert "high_below_body:300" in validate_m5_rows([bar(0), bar(300, high=99.0, close=100.0)])

def test_h1_requires_twelve_constituents_and_never_interpolates():
    full = [bar(i * 300) for i in range(12)]
    h1, receipt = aggregate_complete_h1(full, [])
    assert len(h1) == 1 and h1[0].open_ts == 0
    incomplete, receipt = aggregate_complete_h1(full[:-1], [])
    assert incomplete == []
    assert receipt[0]["reason"] == "ordinary_incomplete_hour"

def test_scheduled_closure_is_explicit_not_synthesized():
    h1, receipt = aggregate_complete_h1([], [Closure(0, 3600, "holiday")])
    assert h1 == []
    assert receipt == [{"bucket_open_ts": 0, "state": "closed", "reason": "holiday"}]
```

- [ ] **Step 2: Run the data tests and verify RED**

Run: `pytest -q tests/test_xau_data_contract_v1.py`

Expected: import fails because `research_lab.xau_data_contract_v1` does not exist.

- [ ] **Step 3: Implement typed bars, validation, and aggregation**

```python
@dataclass(frozen=True)
class M5Bar:
    open_ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass(frozen=True)
class Closure:
    start_ts: int
    end_ts: int
    reason: str

@dataclass(frozen=True)
class H1Bar:
    open_ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_row(self) -> list[float]:
        return [float(self.open_ts), self.open, self.high, self.low, self.close, self.volume]

@dataclass(frozen=True)
class XauDataset:
    h1_rows: Sequence[Sequence[float]]
    candidate_paths_path: Path
    bid_ask_manifest_path: Path
    broker_cost_contract_path: Path
    manifest_sha256: str

class DataContractError(ValueError):
    """The independent XAU data contract cannot be proven."""

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_h1_csv(path: Path) -> list[H1Bar]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            H1Bar(int(row["ts"]), float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]), float(row.get("v") or 0.0))
            for row in csv.DictReader(handle)
        ]

def aggregate_complete_h1(rows: Sequence[M5Bar], closures: Sequence[Closure]) -> tuple[list[H1Bar], list[dict[str, Any]]]:
    buckets: dict[int, list[M5Bar]] = defaultdict(list)
    for row in rows:
        buckets[(row.open_ts // 3600) * 3600].append(row)
    output, receipt = [], []
    for bucket in range(min_bucket, max_bucket + 1, 3600):
        members = sorted(buckets.get(bucket, []), key=lambda row: row.open_ts)
        expected = list(range(bucket, bucket + 3600, 300))
        if [row.open_ts for row in members] == expected:
            output.append(H1Bar(bucket, members[0].open, max(x.high for x in members), min(x.low for x in members), members[-1].close, sum(x.volume for x in members)))
            receipt.append({"bucket_open_ts": bucket, "state": "complete", "reason": "twelve_m5"})
        elif closure_reason(bucket, bucket + 3600, closures):
            receipt.append({"bucket_open_ts": bucket, "state": "closed", "reason": closure_reason(bucket, bucket + 3600, closures)})
        else:
            receipt.append({"bucket_open_ts": bucket, "state": "rejected", "reason": "ordinary_incomplete_hour"})
    return output, receipt

def load_xau_dataset(manifest_path: Path) -> XauDataset:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("verdict") != "PASS":
        raise DataContractError("data manifest is not PASS")
    if sha256_file(Path(manifest["h1_path"])) != manifest["h1_sha256"]:
        raise DataContractError("h1_sha256")
    h1_rows = tuple(row.as_row() for row in load_h1_csv(Path(manifest["h1_path"])))
    return XauDataset(
        h1_rows=h1_rows,
        candidate_paths_path=Path(manifest["candidate_paths_path"]),
        bid_ask_manifest_path=Path(manifest["bid_ask_manifest_path"]),
        broker_cost_contract_path=Path(manifest["broker_cost_contract_path"]),
        manifest_sha256=sha256_file(manifest_path),
    )
```

The implementation must compute `min_bucket`/`max_bucket` from declared input bounds, not from the first and last surviving row, so boundary holes remain visible.

- [ ] **Step 4: Add overlap-reconciliation tests**

```python
def test_overlap_reconciliation_reports_price_and_timestamp_drift():
    receipt = reconcile_overlap([bar(0, close=2000.0)], [bar(0, close=2000.4)])
    assert receipt["matched_rows"] == 1
    assert receipt["max_close_abs"] == pytest.approx(0.4)
    assert receipt["candidate_only_rows"] == 0

def test_independent_replication_rejects_existing_local_csv_identity():
    result = build_data_manifest(source="existing_local_csv", rows=[bar(0)], closures=[])
    assert result["verdict"] == "BLOCKED_DATA_OR_PARITY"
    assert "source_not_independent" in result["failures"]

def test_source_order_prefers_authorized_oanda_then_demo_mt5(tmp_path):
    assert select_independent_source(pass_oanda(tmp_path), pass_mt5(tmp_path))["source_kind"] == "oanda_market_data"
    assert select_independent_source(blocked_oanda(tmp_path), pass_mt5(tmp_path))["source_kind"] == "bullwaves_mt5_demo_export"
    assert select_independent_source(None, None)["verdict"] == "BLOCKED_DATA_OR_PARITY"

def test_mt5_import_requires_rotated_demo_identity_and_never_reads_credentials(tmp_path):
    identity = write_demo_identity(tmp_path, account_mode="demo", token_rotated=True)
    manifest_path = import_mt5_demo_export(MT5_EXPORT, identity, tmp_path / "normalized")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_kind"] == "bullwaves_mt5_demo_export"
    assert manifest["private_api_authority"] is False
    assert "token" not in json.dumps(manifest).lower()
```

- [ ] **Step 5: Implement source precedence, deterministic MT5-demo import, and OANDA receipts**

The MT5 path imports an already-exported CSV only. It never imports `MetaTrader5`, reads an environment variable, opens a network connection, or receives a credential. The owner-supplied identity receipt contains non-secret broker/server/account-mode metadata and proof that the previously exposed token was rotated.

```python
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)

def parse_mt5_export_row(row: Mapping[str, str]) -> M5Bar:
    opened = datetime.fromisoformat(row["time_utc"].replace("Z", "+00:00"))
    if opened.tzinfo is None or opened.second != 0 or opened.minute % 5 != 0:
        raise DataContractError("mt5_time_not_utc_m5_open")
    return M5Bar(
        int(opened.timestamp()), float(row["open"]), float(row["high"]),
        float(row["low"]), float(row["close"]), float(row.get("tick_volume") or 0.0),
    )

def serialize_m5_csv(rows: Sequence[M5Bar]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ts", "o", "h", "l", "c", "v"])
    for row in rows:
        writer.writerow([row.open_ts, row.open, row.high, row.low, row.close, row.volume])
    return buffer.getvalue()

def import_mt5_demo_export(input_path, demo_identity_path, out_dir):
    identity = json.loads(demo_identity_path.read_text(encoding="utf-8"))
    if identity.get("broker") != "Bullwaves" or identity.get("account_mode") != "demo":
        raise DataContractError("bullwaves_demo_identity")
    if identity.get("previous_token_rotated") is not True:
        raise DataContractError("mt5_token_rotation_not_confirmed")
    with input_path.open(newline="", encoding="utf-8") as handle:
        rows = tuple(parse_mt5_export_row(row) for row in csv.DictReader(handle))
    failures = validate_m5_rows(rows)
    if failures:
        raise DataContractError(";".join(failures))
    normalized = out_dir / "XAUUSD_M5.csv"
    _atomic_write_text(normalized, serialize_m5_csv(rows))
    manifest = {
        "schema_id": "xau_independent_data_manifest_v1",
        "source_kind": "bullwaves_mt5_demo_export",
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "data_path": str(normalized),
        "data_sha256": sha256_file(normalized),
        "demo_identity_sha256": sha256_file(demo_identity_path),
        "verdict": "PASS",
    }
    manifest_path = out_dir / "data_manifest.json"
    _atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path

def select_independent_source(oanda_manifest, mt5_manifest):
    for expected_kind, path in (("oanda_market_data", oanda_manifest), ("bullwaves_mt5_demo_export", mt5_manifest)):
        if path is None:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("verdict") == "PASS" and payload.get("source_kind") == expected_kind:
            return payload
    return {"verdict": "BLOCKED_DATA_OR_PARITY", "failures": ["no_independent_xau_source"]}
```

Then extend the OANDA materializer without weakening its security boundary.

Keep `materialize(args)` read-only and add only deterministic manifest fields: `source_kind=oanda_market_data`, source endpoint without query/token, `[start,end)`, row schema, SHA-256, symbol digits if published, closure-map SHA, aggregation receipt SHA, and overlap receipt SHA. The token must remain in-memory only.

```python
status["authority"] = "research_only_no_live_or_promotion"
status.update({
    "promotion_authority": False,
    "network_authority": False,
    "private_api_authority": False,
    "order_authority": False,
    "live_write_authority": False,
    "row_schema": ["open_ts_utc_seconds", "open", "high", "low", "close", "volume"],
    "interval_semantics": "half_open_300_seconds",
})
```

`network_authority=false` describes the resulting research artefact, while the owner-authorized downloader itself remains a bounded public market-data fetch. Add `fetch_performed=true/false` and `owner_market_data_authorization_required=true` so these meanings cannot be confused.

- [ ] **Step 6: Run focused and regression tests**

Run: `pytest -q tests/test_xau_data_contract_v1.py tests/test_import_xau_mt5_demo_export_v1.py tests/test_materialize_xau_oanda_preholdout.py tests/test_materialize_xau_dukascopy_preholdout.py`

Expected: all pass; the security test still proves no token is persisted or printed.

- [ ] **Step 7: Commit the data contract**

```bash
git add research_lab/xau_data_contract_v1.py scripts/import_xau_mt5_demo_export_v1.py scripts/materialize_xau_oanda_preholdout.py tests/fixtures/xau_replication_v1 tests/test_xau_data_contract_v1.py tests/test_import_xau_mt5_demo_export_v1.py tests/test_materialize_xau_oanda_preholdout.py
git commit -m "research: add independent XAU feed parity contract"
```

### Task 3: Reproduce the unchanged close-fill diagnostic exactly

**Files:**
- Create: `research_lab/xau_unchanged_replication_v1.py`
- Create: `tests/test_xau_unchanged_replication_v1.py`
- Modify: `scripts/run_fx_native_harness.py:81-152`
- Modify: `bot/fx_harness.py:81-166`

**Interfaces:**
- Consumes: complete H1 bars from Task 2 and the frozen config from Task 1.
- Produces: `run_unchanged(rows: Sequence[Sequence[float]], contract: Mapping[str, Any], costs: CostCase) -> ReplicationLedger` and `evaluate_latest_closed_h1_signal(rows: Sequence[Sequence[float]], config_path: Path) -> ReplicationDecision | None` with decisions, trades, censored outcomes, folds, and close-fill diagnostic metrics.

- [ ] **Step 1: Pin current engine semantics with RED characterization tests**

```python
def test_unchanged_entry_is_signal_close_and_exit_starts_next_bar():
    result = run_unchanged(close_signal_fixture(), CONTRACT, BASE)
    trade = result.trades[0]
    assert trade.entry_reference == pytest.approx(2001.0)
    assert trade.entry_model == "signal_h1_close_diagnostic"
    assert trade.exit_ts > trade.entry_ts

def test_same_bar_stop_and_target_is_stop_first():
    trade = run_unchanged(tie_fixture(), CONTRACT, BASE).trades[0]
    assert trade.exit_reason == "stop"
    assert trade.gross_r == -1.0

def test_missing_2100_bar_takes_next_complete_open_and_gap():
    trade = run_unchanged(holiday_gap_fixture(), CONTRACT, BASE).trades[0]
    assert trade.exit_reason == "force_flat_utc"
    assert trade.exit_ts == next_complete_h1_ts
    assert trade.exit_reference == next_complete_h1_open

def test_no_later_complete_bar_is_censored_not_last_close():
    result = run_unchanged(end_of_input_fixture(), CONTRACT, BASE)
    assert result.trades == []
    assert result.censored[0].reason == "no_complete_h1_after_force_flat_boundary"
```

- [ ] **Step 2: Run tests and verify RED against the current harness**

Run: `pytest -q tests/test_xau_unchanged_replication_v1.py`

Expected: tests fail because the existing harness has no typed ledger/censored interface and currently falls back to a bounded close.

- [ ] **Step 3: Extract complete-H1 aggregation without altering existing output**

Modify `_aggregate_rows_seconds` to accept a keyword-only completeness policy and return rejected-bucket receipts through a new wrapper; preserve the old default for unrelated callers.

```python
def aggregate_fx_rows_with_receipt(
    rows: Sequence[Sequence[float]], *, interval_min: int,
    closure_map: Sequence[Mapping[str, Any]], require_complete: bool,
) -> tuple[list[list[float]], list[dict[str, Any]]]:
    if interval_min != 60 or not require_complete:
        return _aggregate_rows_seconds(rows, interval_min), []
    m5_rows = tuple(
        M5Bar(
            open_ts=int(float(row[0])), open=float(row[1]), high=float(row[2]),
            low=float(row[3]), close=float(row[4]),
            volume=float(row[5]) if len(row) > 5 else 0.0,
        )
        for row in rows
    )
    failures = validate_m5_rows(m5_rows)
    if failures:
        raise DataContractError(";".join(failures))
    closures = tuple(
        Closure(int(item["start_ts"]), int(item["end_ts"]), str(item["reason"]))
        for item in closure_map
    )
    h1_rows, receipt = aggregate_complete_h1(m5_rows, closures)
    return [
        [float(row.open_ts), row.open, row.high, row.low, row.close, row.volume]
        for row in h1_rows
    ], receipt
```

The wrapper must delegate raw validation to `xau_data_contract_v1` for XAU and must not interpolate bars.

- [ ] **Step 4: Implement an explicit terminal-state replay loop**

```python
@dataclass(frozen=True)
class CostCase:
    name: str
    fee_spread_proxy_bps: float
    slippage_bps: float

    @classmethod
    def from_config(cls, config: Mapping[str, Any], name: str) -> "CostCase":
        payload = config[f"{name}_cost_bps_per_side"]
        return cls(name, float(payload["fee_spread_proxy"]), float(payload["slippage"]))

@dataclass(frozen=True)
class ReplicationDecision:
    event_id: str
    source_h1_open_ts: int
    signal_close_ts: int
    side: str
    entry: float
    stop: float
    target: float
    session: str
    h1_atr_decile: int
    config_fingerprint: str

@dataclass(frozen=True)
class ReplicationTrade:
    event_id: str
    side: str
    source_h1_open_ts: int
    entry_ts: int
    entry_reference: float
    entry_model: str
    stop: float
    target: float
    exit_ts: int
    exit_reference: float
    exit_reason: str
    gross_r: float
    net_r: float
    utc_entry_session_date: str

@dataclass(frozen=True)
class ReplicationLedger:
    decisions: Sequence[ReplicationDecision]
    trades: Sequence[ReplicationTrade]
    censored: Sequence[Mapping[str, Any]]
    metrics: Mapping[str, Any]

def _resolve_unchanged(rows, *, entry_index, side, entry, stop, target, max_hold, cutoff_minute):
    entry_day = datetime.fromtimestamp(float(rows[entry_index][0]), timezone.utc).date()
    last_index = min(len(rows) - 1, entry_index + max_hold)
    for exit_index in range(entry_index + 1, last_index + 1):
        exit_dt = datetime.fromtimestamp(float(rows[exit_index][0]), timezone.utc)
        exit_minute = exit_dt.hour * 60 + exit_dt.minute
        if exit_dt.date() != entry_day or exit_minute >= cutoff_minute:
            price = float(rows[exit_index][1])
            gross_r = ((price - entry) if side == "long" else (entry - price)) / abs(entry - stop)
            return exit_index, price, "force_flat_utc", gross_r
        high, low = float(rows[exit_index][2]), float(rows[exit_index][3])
        stop_hit = low <= stop if side == "long" else high >= stop
        target_hit = high >= target if side == "long" else low <= target
        if stop_hit:
            return exit_index, stop, "stop", -1.0
        if target_hit:
            return exit_index, target, "target", 2.0
    if entry_index + max_hold >= len(rows):
        return None
    price = float(rows[last_index][4])
    gross_r = ((price - entry) if side == "long" else (entry - price)) / abs(entry - stop)
    return last_index, price, "time", gross_r

def _replication_metrics(trades):
    values = [float(trade.net_r) for trade in trades]
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    return {
        "n": len(values),
        "net_r": sum(values),
        "pf": gains / losses if losses > 0.0 else (float("inf") if gains > 0.0 else 0.0),
    }

def causal_atr_decile(rows, index, current_atr):
    finite_sums, counts = _prefix_atr_arrays(rows)
    history = [
        _atr_at(finite_sums, counts, cursor, 14)
        for cursor in range(16, index + 1)
    ]
    history = [value for value in history if math.isfinite(value) and value > 0.0]
    if len(history) < 100:
        raise DataParityError("fewer_than_100_causal_atr_observations")
    percentile = sum(value <= current_atr for value in history) / len(history)
    return min(9, int(percentile * 10.0))

def run_unchanged(rows, contract, costs):
    decisions, trades, censored = [], [], []
    finite_sums, counts = _prefix_atr_arrays(rows)
    index = max(120, 16)
    while index < len(rows) - 1:
        atr_value = _atr_at(finite_sums, counts, index, 14)
        signal = session_breakout_retest(
            _PrefixView(rows, index + 1),
            events=None,
            sessions=("london", "london_ny_overlap", "newyork"),
            level_lookback=120,
        )
        if signal.side not in {"long", "short"} or not math.isfinite(atr_value) or atr_value <= 0.0:
            index += 1
            continue
        entry = float(rows[index][4])
        risk = float(contract["sl_atr"]) * atr_value
        stop = entry - risk if signal.side == "long" else entry + risk
        target = entry + 2.0 * risk if signal.side == "long" else entry - 2.0 * risk
        event_id = hashlib.sha256(f"{contract['experiment_id']}|{int(rows[index][0])}|{signal.side}".encode()).hexdigest()[:24]
        decisions.append(ReplicationDecision(
            event_id=event_id,
            source_h1_open_ts=int(rows[index][0]),
            signal_close_ts=int(rows[index][0]) + 3600,
            side=signal.side,
            entry=entry,
            stop=stop,
            target=target,
            session=session_of(float(rows[index][0])),
            h1_atr_decile=causal_atr_decile(rows, index, atr_value),
            config_fingerprint=str(contract["_config_fingerprint"]),
        ))
        resolved = _resolve_unchanged(
            rows, entry_index=index, side=signal.side, entry=entry, stop=stop,
            target=target, max_hold=int(contract["max_hold_h1_bars"]),
            cutoff_minute=int(contract["force_flat_utc_minute"]),
        )
        if resolved is None:
            censored.append({"event_id": event_id, "reason": "no_complete_h1_after_force_flat_boundary"})
            break
        exit_index, exit_price, reason, gross_r = resolved
        risk_fraction = risk / entry
        round_trip_bps = 2.0 * (float(costs.fee_spread_proxy_bps) + float(costs.slippage_bps))
        net_r = gross_r - (round_trip_bps / 10_000.0) / risk_fraction
        entry_date = datetime.fromtimestamp(float(rows[index][0]), timezone.utc).date().isoformat()
        trades.append(ReplicationTrade(event_id, signal.side, int(rows[index][0]), int(rows[index][0]) + 3600, entry, "signal_h1_close_diagnostic", stop, target, int(rows[exit_index][0]), exit_price, reason, gross_r, net_r, entry_date))
        index = exit_index + 1
    return ReplicationLedger(tuple(decisions), tuple(trades), tuple(censored), _replication_metrics(trades))

def evaluate_latest_closed_h1_signal(rows, config_path):
    contract = json.loads(config_path.read_text(encoding="utf-8"))
    contract["_config_fingerprint"] = sha256_file(config_path)
    if len(rows) < 121:
        return None
    finite_sums, counts = _prefix_atr_arrays(rows)
    index = len(rows) - 1
    atr_value = _atr_at(finite_sums, counts, index, 14)
    signal = session_breakout_retest(
        _PrefixView(rows, index + 1), events=None,
        sessions=("london", "london_ny_overlap", "newyork"), level_lookback=120,
    )
    if signal.side not in {"long", "short"} or not math.isfinite(atr_value) or atr_value <= 0.0:
        return None
    entry = float(rows[index][4])
    risk = float(contract["sl_atr"]) * atr_value
    stop = entry - risk if signal.side == "long" else entry + risk
    target = entry + 2.0 * risk if signal.side == "long" else entry - 2.0 * risk
    event_id = hashlib.sha256(f"{contract['experiment_id']}|{int(rows[index][0])}|{signal.side}".encode()).hexdigest()[:24]
    return ReplicationDecision(
        event_id, int(rows[index][0]), int(rows[index][0]) + 3600,
        signal.side, entry, stop, target, session_of(float(rows[index][0])),
        causal_atr_decile(rows, index, atr_value), str(contract["_config_fingerprint"]),
    )
```

The implementer must copy the current arithmetic exactly into this focused module, then prove equivalence to `backtest_fx_setup` on fixtures where no censor edge is present. Do not change `session_breakout_retest` geometry.

- [ ] **Step 5: Add equivalence and immutable-ledger tests**

```python
def test_new_wrapper_matches_legacy_harness_on_non_edge_fixture():
    legacy = backtest_fx_setup(ROWS, session_breakout_retest, setup_kwargs=KWARGS, tp_rr=2.0, sl_atr=1.5, max_hold=6, force_flat_utc_minute=1255)
    current = run_unchanged(H1_ROWS, CONTRACT, BASE)
    assert [(t.source_h1_open_ts, t.exit_ts, round(t.net_r, 4), t.side) for t in current.trades] == [
        (int(t["entry_ts"]), int(t["exit_ts"]), float(t["r"]), t["side"]) for t in legacy
    ]

def test_input_order_or_hash_drift_blocks_replay():
    with pytest.raises(DataParityError, match="input_sha256"):
        run_unchanged(reversed(H1_ROWS), CONTRACT, BASE)
```

- [ ] **Step 6: Run the engine tests**

Run: `pytest -q tests/test_xau_unchanged_replication_v1.py tests/test_fx_native_harness_window.py tests/test_fx_setups.py tests/test_audit_xau_intraday_flat_baseline_v2.py`

Expected: all pass; old diagnostic remains reproducible, and the new bounded-edge semantics are explicit.

- [ ] **Step 7: Commit the unchanged replay**

```bash
git add research_lab/xau_unchanged_replication_v1.py scripts/run_fx_native_harness.py bot/fx_harness.py tests/test_xau_unchanged_replication_v1.py
git commit -m "research: reproduce XAU unchanged close-fill diagnostic"
```

### Task 4: Add executable next-open and bid/ask repricing parity

**Files:**
- Create: `research_lab/xau_execution_parity_v1.py`
- Create: `tests/fixtures/xau_replication_v1/bid_ask_h1.csv`
- Create: `tests/fixtures/xau_replication_v1/broker_cost_contract.json`
- Create: `tests/test_xau_execution_parity_v1.py`

**Interfaces:**
- Consumes: Task 3 decisions, next complete H1 open bid/ask observations, symbol/contract/session metadata, and a broker-calibrated cost contract.
- Produces: `load_bid_ask_bars(manifest_path: Path) -> Sequence[BidAskBar]`, `reprice_decisions(decisions: Sequence[ReplicationDecision], quotes: Sequence[BidAskBar], costs: BrokerCostContract) -> ExecutionParityLedger`, `to_signal_event(decision: ReplicationDecision, costs: BrokerCostContract) -> SignalEvent`, `to_cost_contract(costs: BrokerCostContract) -> CostContract`, `is_forced_flat_or_max_hold(decision: ReplicationDecision, bar: BidAskBar) -> bool`, `swap_cash_for_position(position: PaperPosition, terminal: PaperOutcome, costs: BrokerCostContract) -> float`, and explicit `pending/censored/blocked` rows.

- [ ] **Step 1: Write RED tests for side-correct next-open fills**

```python
def test_long_uses_next_open_ask_and_short_uses_next_open_bid():
    ledger = reprice_decisions([long_decision(), short_decision()], BID_ASK, COSTS)
    assert ledger.trades[0].entry_reference == BID_ASK[1].ask_open
    assert ledger.trades[1].entry_reference == BID_ASK[3].bid_open
    assert all(trade.entry_ts > trade.signal_close_ts for trade in ledger.trades)

def test_missing_bid_ask_or_contract_metadata_blocks_not_mid_fills():
    ledger = reprice_decisions([long_decision()], MID_ONLY, COSTS)
    assert ledger.trades == ()
    assert ledger.blocked[0].reason == "missing_bid_ask"

def test_gap_through_stop_uses_first_executable_side_correct_quote():
    trade = reprice_decisions([gap_decision()], GAP_QUOTES, COSTS).trades[0]
    assert trade.exit_reason == "gap"
    assert trade.exit_reference == GAP_QUOTES[2].bid_open

def test_overnight_swap_and_triple_day_are_in_net_r():
    trade = reprice_decisions([overnight_decision()], OVERNIGHT_QUOTES, STRESS_COSTS).trades[0]
    assert trade.swap_cash < 0.0
    assert trade.net_r == pytest.approx(EXPECTED_TERMINAL_R + trade.swap_cash / EXPECTED_RISK_CASH)
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_xau_execution_parity_v1.py`

Expected: module import fails.

- [ ] **Step 3: Implement immutable quote and broker-cost contracts**

```python
@dataclass(frozen=True)
class BidAskBar:
    open_ts: int
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    source_hash: str

    def open_snapshot(self) -> QuoteSnapshot:
        observed = datetime.fromtimestamp(self.open_ts, timezone.utc)
        return QuoteSnapshot(observed, self.bid_open, self.ask_open, self.source_hash, 0.0)

    def range_snapshot_for_side(self, side: str) -> QuoteSnapshot:
        observed = datetime.fromtimestamp(self.open_ts + 3600, timezone.utc)
        low = self.bid_low if side == "long" else self.ask_low
        high = self.bid_high if side == "long" else self.ask_high
        return QuoteSnapshot(observed, self.bid_close, self.ask_close, self.source_hash, 0.0, low=low, high=high)

@dataclass(frozen=True)
class BrokerCostContract:
    symbol: str
    scenario: str
    digits: int
    contract_size: float
    commission_per_lot_round_turn: float
    additional_spread_bps: float
    slippage_bps_per_side: float
    swap_long_per_lot_day: float
    swap_short_per_lot_day: float
    rollover_utc_hour: int
    triple_swap_weekday: int
    effective_from_utc: str
    source_sha256: str

    @classmethod
    def from_path(cls, path: Path, scenario: str) -> "BrokerCostContract":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if scenario not in {"base", "stress"}:
            raise ExecutionParityError("scenario")
        common = {key: value for key, value in payload.items() if key != "scenarios"}
        return cls(scenario=scenario, **common, **payload["scenarios"][scenario])

class ExecutionParityError(ValueError):
    """The bid/ask execution contract cannot be reproduced safely."""

def coerce_bid_ask_row(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        "open_ts": int(row["open_ts"]),
        "bid_open": float(row["bid_open"]), "bid_high": float(row["bid_high"]),
        "bid_low": float(row["bid_low"]), "bid_close": float(row["bid_close"]),
        "ask_open": float(row["ask_open"]), "ask_high": float(row["ask_high"]),
        "ask_low": float(row["ask_low"]), "ask_close": float(row["ask_close"]),
        "source_hash": row["source_hash"],
    }

@dataclass(frozen=True)
class ExecutionTrade:
    event_id: str
    signal_close_ts: int
    entry_ts: int
    entry_reference: float
    exit_ts: int
    exit_reference: float
    exit_reason: str
    net_r: float
    swap_cash: float
    utc_entry_session_date: str
    session: str
    side: str
    h1_atr_decile: int
    scenario: str
    utc_month: str
    event_forward_start_ts: int
    event_forward_end_ts: int

@dataclass(frozen=True)
class ExecutionBlock:
    event_id: str
    reason: str

@dataclass(frozen=True)
class ExecutionParityLedger:
    trades: Sequence[ExecutionTrade]
    censored: Sequence[ExecutionBlock]
    blocked: Sequence[ExecutionBlock]

def load_bid_ask_bars(manifest_path: Path) -> Sequence[BidAskBar]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = Path(manifest["path"])
    if sha256_file(source_path) != manifest["sha256"]:
        raise ExecutionParityError("bid_ask_sha256")
    with source_path.open(newline="", encoding="utf-8") as handle:
        return tuple(BidAskBar(**coerce_bid_ask_row(row)) for row in csv.DictReader(handle))

def to_signal_event(decision: ReplicationDecision, costs: BrokerCostContract) -> SignalEvent:
    signal_close = datetime.fromtimestamp(decision.signal_close_ts, timezone.utc)
    return SignalEvent(
        signal_id=decision.event_id,
        strategy="xauusd_unchanged_replication_v1",
        strategy_version="1",
        symbol=costs.symbol,
        side=decision.side,
        event_at=signal_close,
        source_candle_end=signal_close,
        data_source_hash=costs.source_sha256,
        entry=decision.entry,
        stop=decision.stop,
        take_profit=decision.target,
        validity_until=signal_close + timedelta(hours=2),
        regime="unchanged_static_session",
        feature_snapshot_hash=decision.event_id,
        prereg_hash=decision.config_fingerprint,
        evidence_universe_role="xauusd_independent_replication",
    )

def to_cost_contract(costs: BrokerCostContract) -> CostContract:
    return CostContract(
        spread_bps=costs.additional_spread_bps,
        slippage_bps=costs.slippage_bps_per_side,
        commission_per_unit=costs.commission_per_lot_round_turn / 2.0,
        point_value=costs.contract_size,
    )

def is_forced_flat_or_max_hold(decision: ReplicationDecision, bar: BidAskBar) -> bool:
    entry_boundary = decision.signal_close_ts
    elapsed_bars = (bar.open_ts - entry_boundary) // 3600
    current = datetime.fromtimestamp(bar.open_ts, timezone.utc)
    entry_date = datetime.fromtimestamp(entry_boundary, timezone.utc).date()
    return elapsed_bars >= 6 or current.date() != entry_date or current.hour * 60 + current.minute >= 1255

def swap_cash_for_position(position, terminal, costs):
    cursor = position.entry_at.astimezone(timezone.utc).replace(
        hour=costs.rollover_utc_hour, minute=0, second=0, microsecond=0,
    )
    if cursor <= position.entry_at:
        cursor += timedelta(days=1)
    daily = costs.swap_long_per_lot_day if position.side == "long" else costs.swap_short_per_lot_day
    total = 0.0
    while cursor <= terminal.closed_at:
        multiplier = 3 if cursor.weekday() == costs.triple_swap_weekday else 1
        applied = daily * multiplier
        if costs.scenario == "stress" and applied > 0.0:
            applied = 0.0
        total += applied
        cursor += timedelta(days=1)
    return total * position.quantity

def to_execution_trade(decision, position, terminal, costs):
    swap_cash = swap_cash_for_position(position, terminal, costs)
    risk_cash = position.quantity * abs(position.entry_fill - position.stop) * position.point_value
    return ExecutionTrade(
        event_id=decision.event_id,
        signal_close_ts=decision.signal_close_ts,
        entry_ts=int(position.entry_at.timestamp()),
        entry_reference=position.entry_reference_price,
        exit_ts=int(terminal.closed_at.timestamp()),
        exit_reference=float(terminal.exit_reference),
        exit_reason=terminal.close_reason,
        net_r=terminal.r + swap_cash / risk_cash,
        swap_cash=swap_cash,
        utc_entry_session_date=position.entry_at.date().isoformat(),
        session=decision.session,
        side=decision.side,
        h1_atr_decile=decision.h1_atr_decile,
        scenario=costs.scenario,
        utc_month=position.entry_at.strftime("%Y-%m"),
        event_forward_start_ts=decision.signal_close_ts,
        event_forward_end_ts=int(terminal.closed_at.timestamp()),
    )
```

Validation rejects crossed bid/ask, missing values, non-positive contract fields, `rollover_utc_hour` outside `0..23`, `triple_swap_weekday` outside `0..6`, a contract effective after an entry, and a symbol mismatch.

- [ ] **Step 4: Implement repricing through existing zero-order accounting primitives**

Map decisions into `SignalEvent`, bars into `QuoteSnapshot`, and use `open_position`/`evaluate_position` from `bot.xau_mt5_zero_order_paper`. Preserve signal-close diagnostic fields beside executable fields; never overwrite Task 3 ledgers.

```python
def reprice_decisions(decisions, quotes, costs):
    ordered_quotes = tuple(sorted(quotes, key=lambda bar: bar.open_ts))
    trades, censored, blocked = [], [], []
    for decision in decisions:
        next_quote = next((bar for bar in ordered_quotes if bar.open_ts >= decision.signal_close_ts), None)
        if next_quote is None:
            censored.append(ExecutionBlock(decision.event_id, "no_next_complete_bid_ask_bar"))
            continue
        try:
            signal = to_signal_event(decision, costs)
            paper_costs = to_cost_contract(costs)
            position = open_position(
                signal, next_quote.open_snapshot(), quantity=1.0, costs=paper_costs,
            )
        except ValueError as exc:
            blocked.append(ExecutionBlock(decision.event_id, str(exc)))
            continue
        previous_reference = None
        terminal = None
        for bar in (item for item in ordered_quotes if item.open_ts >= next_quote.open_ts):
            snapshot = bar.range_snapshot_for_side(decision.side)
            time_exit = is_forced_flat_or_max_hold(decision, bar)
            try:
                terminal = evaluate_position(
                    position, snapshot, costs=paper_costs,
                    previous_exit_reference=previous_reference, time_exit=time_exit,
                )
            except ValueError as exc:
                if str(exc) != "quote does not close position":
                    blocked.append(ExecutionBlock(decision.event_id, str(exc)))
                    terminal = "blocked"
                    break
            previous_reference = snapshot.bid if decision.side == "long" else snapshot.ask
            if terminal is not None:
                break
        if terminal == "blocked":
            continue
        if terminal is None:
            censored.append(ExecutionBlock(decision.event_id, "no_terminal_bid_ask_bar"))
            continue
        trades.append(to_execution_trade(decision, position, terminal, costs))
    return ExecutionParityLedger(tuple(trades), tuple(censored), tuple(blocked))
```

- [ ] **Step 5: Add an execution-parity comparison test**

```python
def test_receipt_keeps_close_fill_and_next_open_results_separate():
    receipt = compare_execution_models(DIAGNOSTIC, EXECUTABLE)
    assert receipt["diagnostic_model"] == "signal_h1_close"
    assert receipt["candidate_model"] == "next_complete_h1_open_side_correct_bid_ask"
    assert set(receipt["deltas"]) >= {"entry_bps", "net_r", "exit_reason_changed"}
    assert receipt["shadow_eligible"] is False  # fixture lacks full historical gate
```

- [ ] **Step 6: Run parity and zero-order accounting regressions**

Run: `pytest -q tests/test_xau_execution_parity_v1.py tests/test_xau_mt5_zero_order_paper.py`

Expected: all pass, including stop-first and gap tests.

- [ ] **Step 7: Commit repricing parity**

```bash
git add research_lab/xau_execution_parity_v1.py tests/fixtures/xau_replication_v1/bid_ask_h1.csv tests/fixtures/xau_replication_v1/broker_cost_contract.json tests/test_xau_execution_parity_v1.py
git commit -m "research: add XAU next-open bid-ask parity"
```

### Task 5: Build XAU matched controls and selection-aware inference

**Files:**
- Create: `research_lab/xau_matched_control_v1.py`
- Create: `tests/test_xau_matched_control_v1.py`
- Consume without modifying: `research_lab/money_research_controls_v1.py`
- Consume without modifying: `configs/research/money_research_sprint_v1_control_contract.json`

**Interfaces:**
- Consumes: terminal executable XAU trades, all causal eligible H1 paths, the shared control module signatures in the file map, and the shared config SHA pinned by Task 1.
- Produces: `load_candidate_paths_v1(path: Path) -> Sequence[CandidatePath]`, `build_xau_controls(trades: Sequence[ExecutionTrade], paths: Sequence[CandidatePath], contract: SharedControlContract, costs: BrokerCostContract) -> XauControlLedger`, `score_xau_effect(strategy_rows: Sequence[ExecutionTrade], control_ledgers: Sequence[ControlLedger], contract: SharedControlContract) -> XauInferenceReceipt`, `recompute_mean_excess(strategy_rows: Sequence[ExecutionTrade], control_ledgers: Sequence[ControlLedger], label_map: Mapping[str, bool]) -> float`, `recompute_cluster_bootstrap_excess(strategy_rows: Sequence[ExecutionTrade], control_ledgers: Sequence[ControlLedger], sampled_indices: Sequence[Sequence[int]]) -> list[float]`, `aggregate_control_outcomes(control_ledgers: Sequence[ControlLedger]) -> list[float]`, `top_fraction_trim(strategy_rows: Sequence[ExecutionTrade], fraction: float) -> float`, and `max_positive_cluster_share(strategy_rows: Sequence[ExecutionTrade]) -> float`; outputs include 20 full matched ledgers, 999 permutation values, and 9999 bootstrap values.

- [ ] **Step 1: Write RED tests for exact eligibility and deterministic ranking**

```python
def test_controls_match_month_session_side_atr_decile_and_exclude_paths():
    ledger = build_xau_controls([TRADE], ELIGIBLE_PATHS, CONTROL_CONTRACT, CONTROL_COSTS)
    assert len(ledger.assignments[TRADE.event_id]) == 20
    for assignment in ledger.assignments[TRADE.event_id]:
        assert assignment.utc_month == TRADE.utc_month
        assert assignment.session == TRADE.session
        assert assignment.physical_side == TRADE.side
        assert assignment.h1_atr_decile == TRADE.h1_atr_decile
        assert not overlaps(assignment.path, (TRADE.event_forward_start_ts, TRADE.event_forward_end_ts))

def test_fewer_than_twenty_unique_paths_blocks_entire_arm():
    ledger = build_xau_controls([TRADE], ELIGIBLE_PATHS[:19], CONTROL_CONTRACT, CONTROL_COSTS)
    assert ledger.verdict == "BLOCKED_DATA_OR_PARITY"
    assert ledger.failures == ("event_has_fewer_than_20_matched_paths",)

def test_control_draws_are_repeatable_and_python_random_independent(monkeypatch):
    monkeypatch.setattr(random, "random", lambda: (_ for _ in ()).throw(AssertionError()))
    assert build_xau_controls([TRADE], ELIGIBLE_PATHS, CONTROL_CONTRACT, CONTROL_COSTS) == build_xau_controls([TRADE], ELIGIBLE_PATHS, CONTROL_CONTRACT, CONTROL_COSTS)
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_xau_matched_control_v1.py`

Expected: module import fails.

- [ ] **Step 3: Implement XAU-specific causal eligible sets over shared hash primitives**

```python
@dataclass(frozen=True)
class CandidatePath:
    path_id: str
    utc_month: str
    session: str
    physical_side: str
    h1_atr_decile: int
    start_ts: int
    end_ts: int
    decision: ReplicationDecision
    quotes: Sequence[BidAskBar]
    source_hash: str

def candidate_path_from_dict(row: Mapping[str, Any]) -> CandidatePath:
    return CandidatePath(
        path_id=str(row["path_id"]),
        utc_month=str(row["utc_month"]),
        session=str(row["session"]),
        physical_side=str(row["physical_side"]),
        h1_atr_decile=int(row["h1_atr_decile"]),
        start_ts=int(row["start_ts"]),
        end_ts=int(row["end_ts"]),
        decision=ReplicationDecision(**row["decision"]),
        quotes=tuple(BidAskBar(**item) for item in row["quotes"]),
        source_hash=str(row["source_hash"]),
    )

def load_candidate_paths_v1(path: Path) -> Sequence[CandidatePath]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return tuple(candidate_path_from_dict(row) for row in rows)

@dataclass(frozen=True)
class SharedControlContract:
    experiment_id: str
    config_fingerprint: str
    control_contract_sha256: str
    draws_per_unit: int
    permutations: int
    bootstrap_replicates: int

    @classmethod
    def from_paths(cls, shared_path: Path, experiment_path: Path) -> "SharedControlContract":
        shared = load_control_contract(shared_path)
        experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
        return cls(
            experiment_id=experiment["experiment_id"],
            config_fingerprint=sha256_file(experiment_path),
            control_contract_sha256=sha256_file(shared_path),
            draws_per_unit=shared["draws_per_unit"],
            permutations=shared["permutations"],
            bootstrap_replicates=shared["bootstrap_replicates"],
        )

@dataclass(frozen=True)
class XauControlAssignment:
    event_id: str
    draw_index: int
    path: CandidatePath

    @property
    def utc_month(self): return self.path.utc_month
    @property
    def session(self): return self.path.session
    @property
    def physical_side(self): return self.path.physical_side
    @property
    def h1_atr_decile(self): return self.path.h1_atr_decile

@dataclass(frozen=True)
class ControlLedger:
    event_id: str
    draw_index: int
    path_id: str
    utc_entry_session_date: str
    control_path_date: str
    stress_r: float

@dataclass(frozen=True)
class XauControlLedger:
    assignments: Mapping[str, Sequence[XauControlAssignment]]
    ledgers: Sequence[ControlLedger]
    contract: SharedControlContract
    verdict: str
    failures: Sequence[str]
    assignment_hash: str

class ControlPathError(ValueError):
    """A precommitted matched control cannot reach one terminal outcome."""

def path_key(path: CandidatePath) -> tuple[str, str, str, int]:
    return (path.utc_month, path.session, path.physical_side, path.h1_atr_decile)

def trade_key(trade: ExecutionTrade) -> tuple[str, str, str, int]:
    return (trade.utc_month, trade.session, trade.side, trade.h1_atr_decile)

def overlaps(path: CandidatePath, interval: tuple[int, int]) -> bool:
    return path.start_ts < interval[1] and interval[0] < path.end_ts

def canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def execute_control_path(trade: ExecutionTrade, assignment: XauControlAssignment, costs: BrokerCostContract) -> ControlLedger:
    entry_date = datetime.fromtimestamp(assignment.path.start_ts, timezone.utc).date().isoformat()
    replay = reprice_decisions([assignment.path.decision], assignment.path.quotes, costs)
    if replay.blocked or replay.censored or len(replay.trades) != 1:
        raise ControlPathError(f"non_terminal_control:{assignment.path.path_id}")
    return ControlLedger(
        event_id=trade.event_id,
        draw_index=assignment.draw_index,
        path_id=assignment.path.path_id,
        utc_entry_session_date=trade.utc_entry_session_date,
        control_path_date=entry_date,
        stress_r=replay.trades[0].net_r,
    )

def build_xau_controls(trades, paths, contract, costs):
    by_key = defaultdict(list)
    for path in paths:
        by_key[path_key(path)].append(path)
    path_by_id = {path.path_id: path for path in paths}
    assignments = {}
    ledgers = []
    for trade in trades:
        excluded = (trade.event_forward_start_ts, trade.event_forward_end_ts)
        candidates = [path for path in by_key[trade_key(trade)] if not overlaps(path, excluded)]
        eligible_ids = [path.path_id for path in candidates]
        if len(eligible_ids) < 20:
            return XauControlLedger({}, (), contract, "BLOCKED_DATA_OR_PARITY", ("event_has_fewer_than_20_matched_paths",), "")
        selected_ids = []
        for draw_index in range(20):
            remaining = [path_id for path_id in eligible_ids if path_id not in selected_ids]
            ranked = hash_rank((contract.config_fingerprint, trade.event_id, str(draw_index)), remaining)
            selected_ids.append(ranked[0])
        selected = tuple(
            XauControlAssignment(trade.event_id, draw_index, path_by_id[path_id])
            for draw_index, path_id in enumerate(selected_ids)
        )
        assignments[trade.event_id] = selected
        ledgers.extend(execute_control_path(trade, assignment, costs) for assignment in selected)
    assignment_hash = canonical_sha256({event_id: [item.path.path_id for item in rows] for event_id, rows in sorted(assignments.items())})
    return XauControlLedger(assignments, tuple(ledgers), contract, "PASS", (), assignment_hash)
```

Controls use the identical executable entry/exit/cost engine from Task 4, including forced-flat, gaps, swaps, and censored outcomes.

- [ ] **Step 4: Implement cluster inference and concentration metrics**

```python
@dataclass(frozen=True)
class XauInferenceReceipt:
    mean_stress_excess_r: float
    p_value: float
    bootstrap_95: tuple[float, float]
    control_std: float
    top5_trimmed_stress_r: float
    max_positive_session_contribution: float
    permutation_values: Sequence[float]
    bootstrap_values: Sequence[float]
    cluster_unit: str = "utc_entry_session_date"

def _paired_cluster_excess(strategy_rows, control_ledgers):
    strategy = defaultdict(list)
    controls = defaultdict(list)
    for row in strategy_rows:
        strategy[row.utc_entry_session_date].append(row.net_r)
    for row in control_ledgers:
        controls[row.utc_entry_session_date].append(row.stress_r)
    clusters = sorted(strategy)
    return clusters, {
        cluster: statistics.fmean(strategy[cluster]) - statistics.fmean(controls[cluster])
        for cluster in clusters
    }

def recompute_mean_excess(strategy_rows, control_ledgers, label_map):
    clusters, excess = _paired_cluster_excess(strategy_rows, control_ledgers)
    signed = [(-excess[cluster] if label_map.get(cluster, False) else excess[cluster]) for cluster in clusters]
    return statistics.fmean(signed)

def recompute_cluster_bootstrap_excess(strategy_rows, control_ledgers, sampled_indices):
    clusters, excess = _paired_cluster_excess(strategy_rows, control_ledgers)
    return [statistics.fmean(excess[clusters[index]] for index in replicate) for replicate in sampled_indices]

def aggregate_control_outcomes(control_ledgers):
    by_draw = defaultdict(list)
    for row in control_ledgers:
        by_draw[row.draw_index].append(row.stress_r)
    return [statistics.fmean(by_draw[index]) for index in sorted(by_draw)]

def top_fraction_trim(strategy_rows, fraction):
    values = sorted((row.net_r for row in strategy_rows), reverse=True)
    remove = math.ceil(len(values) * fraction)
    return sum(values[remove:])

def max_positive_cluster_share(strategy_rows):
    by_cluster = defaultdict(float)
    for row in strategy_rows:
        by_cluster[row.utc_entry_session_date] += row.net_r
    positive = [value for value in by_cluster.values() if value > 0.0]
    return max(positive) / sum(positive) if positive else 1.0

def score_xau_effect(strategy_rows, control_ledgers, contract):
    observed = statistics.fmean(row.net_r for row in strategy_rows) - statistics.fmean(row.stress_r for row in control_ledgers)
    clusters = sorted({row.utc_entry_session_date for row in strategy_rows})
    permutation_maps = paired_label_permutations(
        clusters,
        "xauusd_unchanged_replication_v1",
        contract.config_fingerprint,
        permutations=999,
    )
    permuted = [recompute_mean_excess(strategy_rows, control_ledgers, mapping) for mapping in permutation_maps]
    bootstrap = recompute_cluster_bootstrap_excess(strategy_rows, control_ledgers, cluster_bootstrap_indices(
        contract.experiment_id,
        contract.config_fingerprint,
        len(clusters),
        sample_size=len(clusters),
        replicates=9999,
    ))
    return XauInferenceReceipt(
        mean_stress_excess_r=observed,
        p_value=one_sided_p_value(observed, permuted),
        bootstrap_95=percentile_interval(bootstrap),
        control_std=statistics.stdev(aggregate_control_outcomes(control_ledgers)),
        top5_trimmed_stress_r=top_fraction_trim(strategy_rows, 0.05),
        max_positive_session_contribution=max_positive_cluster_share(strategy_rows),
        permutation_values=tuple(permuted),
        bootstrap_values=tuple(bootstrap),
    )
```

- [ ] **Step 5: Test exact replicate counts, cluster unit, and mutation resistance**

```python
def test_inference_uses_exact_counts_and_session_date_clusters():
    receipt = score_xau_effect(STRATEGY, CONTROLS, CONTRACT)
    assert len(receipt.permutation_values) == 999
    assert len(receipt.bootstrap_values) == 9999
    assert receipt.cluster_unit == "utc_entry_session_date"

def test_mutating_outcome_cannot_change_control_assignment():
    before = build_xau_controls(STRATEGY, PATHS, CONTRACT, CONTROL_COSTS).assignment_hash
    after = build_xau_controls(replace_outcomes(STRATEGY, 99.0), PATHS, CONTRACT, CONTROL_COSTS).assignment_hash
    assert before == after
```

- [ ] **Step 6: Run focused tests**

Run: `pytest -q tests/test_xau_matched_control_v1.py tests/test_money_research_controls_v1.py`

Expected: all pass; no local use of `random`, NumPy RNG, or a different seed contract.

- [ ] **Step 7: Commit XAU controls**

```bash
git add research_lab/xau_matched_control_v1.py tests/test_xau_matched_control_v1.py
git commit -m "research: add matched controls for XAU replication"
```

### Task 6: Orchestrate the one-shot diagnostic and independent audit

**Files:**
- Create: `scripts/run_xauusd_unchanged_replication_v1.py`
- Create: `scripts/audit_xauusd_unchanged_replication_v1.py`
- Create: `tests/test_audit_xauusd_unchanged_replication_v1.py`

**Interfaces:**
- Consumes: PASS receipts from Tasks 1–5 and their hash-pinned raw ledgers.
- Produces: `run_pipeline(config_path: Path, data_manifest_path: Path, output_root: Path) -> Path`, `audit_result(result_dir: Path) -> dict[str, Any]`, `deterministic_run_id(config_path: Path, data_manifest_path: Path) -> str`, `write_json(path: Path, payload: Any) -> None`, `write_jsonl(path: Path, rows: Sequence[Any]) -> None`, `hash_result_files(directory: Path) -> dict[str, str]`, `derive_runner_verdict(base: ReplicationLedger, stress: ReplicationLedger, execution_base: ExecutionParityLedger, execution_stress: ExecutionParityLedger, controls: XauControlLedger, inference: XauInferenceReceipt) -> dict[str, Any]`, and one terminal verdict receipt with exact reopen conditions.

- [ ] **Step 1: Write RED audit tests from synthetic raw ledgers**

```python
def test_audit_recomputes_every_gate_from_raw_rows(tmp_path):
    result_dir = write_complete_result_fixture(tmp_path)
    receipt = audit_result(result_dir)
    assert receipt["verdict"] == "PASS"
    assert receipt["recomputed"]["n"] == 30
    assert receipt["recomputed"]["positive_folds"] == 3
    assert receipt["recomputed"]["permutations"] == 999
    assert receipt["recomputed"]["bootstraps"] == 9999

def test_audit_fails_after_trade_or_manifest_mutation(tmp_path):
    result_dir = write_complete_result_fixture(tmp_path)
    mutate_first_trade(result_dir / "stress_trades.jsonl")
    receipt = audit_result(result_dir)
    assert receipt["verdict"] == "FAIL"
    assert "stress_trades_sha256" in receipt["failures"]
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_audit_xauusd_unchanged_replication_v1.py`

Expected: audit module import fails.

- [ ] **Step 3: Implement ordered, atomic orchestration**

```python
STAGES = ("preflight", "unchanged", "execution_parity", "matched_controls", "inference")

def run_pipeline(config_path: Path, data_manifest_path: Path, output_root: Path) -> Path:
    run_id = deterministic_run_id(config_path, data_manifest_path)
    staging = output_root / f".{run_id}.staging"
    final = output_root / run_id
    require_absent(final)
    preflight = build_preflight(config_path, data_manifest_path)
    write_receipt(staging / "preflight.json", preflight)
    if preflight["verdict"] != "PASS":
        return publish_terminal(staging, final, blocked_receipt(preflight))
    config = {**load_json(config_path), "_config_fingerprint": sha256_file(config_path)}
    dataset = load_xau_dataset(data_manifest_path)
    base = run_unchanged(dataset.h1_rows, config, CostCase.from_config(config, "base"))
    stress = run_unchanged(dataset.h1_rows, config, CostCase.from_config(config, "stress"))
    quotes = load_bid_ask_bars(dataset.bid_ask_manifest_path)
    broker_base_costs = BrokerCostContract.from_path(dataset.broker_cost_contract_path, "base")
    broker_stress_costs = BrokerCostContract.from_path(dataset.broker_cost_contract_path, "stress")
    execution_base = reprice_decisions(stress.decisions, quotes, broker_base_costs)
    execution_stress = reprice_decisions(stress.decisions, quotes, broker_stress_costs)
    shared = SharedControlContract.from_paths(ROOT / config["control_contract_path"], config_path)
    candidate_paths = load_candidate_paths_v1(dataset.candidate_paths_path)
    controls = build_xau_controls(execution_stress.trades, candidate_paths, shared, broker_stress_costs)
    inference = score_xau_effect(execution_stress.trades, controls.ledgers, controls.contract)
    write_jsonl(staging / "base_trades.jsonl", base.trades)
    write_jsonl(staging / "stress_trades.jsonl", stress.trades)
    write_jsonl(staging / "execution_base_trades.jsonl", execution_base.trades)
    write_jsonl(staging / "execution_stress_trades.jsonl", execution_stress.trades)
    write_jsonl(staging / "control_ledgers.jsonl", controls.ledgers)
    write_json(staging / "inference.json", asdict(inference))
    manifest = hash_result_files(staging)
    write_json(staging / "result_manifest.json", manifest)
    candidate = derive_runner_verdict(base, stress, execution_base, execution_stress, controls, inference)
    write_json(staging / "candidate_terminal_receipt.json", candidate)
    return publish_directory_atomically(staging, final)
```

The runner must publish negative and blocked terminal receipts atomically. It must refuse an existing run ID with different hashes and must never overwrite a previous result.

- [ ] **Step 4: Implement gate recomputation in the audit**

The independent audit reads only raw ledgers and pinned manifests. It recomputes:

```python
gates = {
    "feed_parity": feed_parity == "PASS",
    "execution_parity": execution_parity == "PASS",
    "base_net_positive": base_net_r > 0.0,
    "stress_net_positive": stress_net_r > 0.0,
    "n_at_least_30": n >= 30,
    "session_dates_at_least_20": len(session_dates) >= 20,
    "months_at_least_4": len(months) >= 4,
    "positive_folds_at_least_3": positive_folds >= 3,
    "pf_at_least_1_20": stress_pf >= 1.20,
    "mean_excess_at_least_0_05r": mean_stress_excess_r >= 0.05,
    "p_value_at_most_0_05": p_value <= 0.05,
    "bootstrap_lower_above_zero": bootstrap_95[0] > 0.0,
    "excess_above_one_control_sd": mean_stress_excess_r > control_std,
    "top5_trim_positive": top5_trimmed_stress_r > 0.0,
    "max_session_contribution_at_most_35pct": max_positive_session_contribution <= 0.35,
    "cost_contract_complete": all_required_cost_fields_present,
}
```

If unchanged replay passes but broker costs or bid/ask are missing, terminal is `DIAGNOSTIC_REPLICATION_PASS` with `shadow_eligible=false`, not an overall false PASS. Only `all(gates.values())` produces `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW`.

- [ ] **Step 5: Test negative-result publication and audit independence**

```python
def test_negative_result_is_published_with_reopen_condition(tmp_path):
    result = run_pipeline(CONFIG, NEGATIVE_DATA, tmp_path)
    candidate = json.loads((result / "candidate_terminal_receipt.json").read_text())
    assert candidate["verdict"] == "DIAGNOSTIC_REPLICATION_FAIL"
    assert candidate["reopen_condition"] == "new_independent_feed_or_separately_preregistered_XAU_Trend_Pullback_V1"
    audited = audit_result(result)
    assert audited["published_terminal_verdict"] == "DIAGNOSTIC_REPLICATION_FAIL"

def test_runner_does_not_import_auditor():
    source = Path("scripts/run_xauusd_unchanged_replication_v1.py").read_text()
    assert "audit_xauusd_unchanged_replication_v1" not in source
```

- [ ] **Step 6: Run the audit suite and CLI help smoke**

Run: `pytest -q tests/test_audit_xauusd_unchanged_replication_v1.py && python3 scripts/run_xauusd_unchanged_replication_v1.py --help && python3 scripts/audit_xauusd_unchanged_replication_v1.py --help`

Expected: tests pass and both commands exit 0 without reading network, secrets, or result data.

- [ ] **Step 7: Commit runner and independent audit**

```bash
git add scripts/run_xauusd_unchanged_replication_v1.py scripts/audit_xauusd_unchanged_replication_v1.py tests/test_audit_xauusd_unchanged_replication_v1.py
git commit -m "research: add audited XAU replication pipeline"
```

### Task 7: Start a zero-order MT5 demo shadow only after PASS

**Files:**
- Create: `scripts/run_xauusd_zero_order_shadow_v1.py`
- Create: `tests/test_run_xauusd_zero_order_shadow_v1.py`
- Modify: `bot/xau_mt5_zero_order_paper.py:77-553`

**Interfaces:**
- Consumes: a terminal `DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW` receipt, current public/demo bid/ask snapshots supplied as files/stdin, and the Task 4 broker-cost contract.
- Produces: `validate_shadow_gate(receipt: Mapping[str, Any], receipt_sha256: str) -> ShadowGate`, `load_public_quote(path: Path) -> dict[str, Any]`, `evaluate_and_journal_without_orders(gate: ShadowGate, quote: Mapping[str, Any], runtime_dir: Path) -> dict[str, Any]`, `prospective_status(runtime_dir: Path) -> dict[str, Any]`, and append-only `signal.jsonl`, `decision.jsonl`, `intended_fill.jsonl`, `outcome.jsonl`, `heartbeat.jsonl`, and `reconciliation.jsonl`; never submits an order.

- [ ] **Step 1: Write RED safety and lifecycle tests**

```python
def test_shadow_refuses_non_shadow_verdict(tmp_path):
    result = shadow_once(DIAGNOSTIC_ONLY_RECEIPT, QUOTE_FILE, tmp_path)
    assert result["state"] == "blocked"
    assert result["reason"] == "historical_shadow_gate_not_passed"

def test_shadow_journals_full_zero_order_lifecycle(tmp_path):
    result = shadow_once(SHADOW_PASS_RECEIPT, QUOTE_FILE, tmp_path)
    assert result["state"] in {"no_signal", "pending", "open", "closed"}
    assert (tmp_path / "heartbeat.jsonl").exists()
    assert all(json.loads(line)["order_authority"] is False for line in (tmp_path / "heartbeat.jsonl").read_text().splitlines())

def test_static_surface_has_no_order_or_private_client():
    source = Path("scripts/run_xauusd_zero_order_shadow_v1.py").read_text()
    for forbidden in ("order_send", "place_order", "submit_order", "private_api", "MetaTrader5"):
        assert forbidden not in source
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_run_xauusd_zero_order_shadow_v1.py`

Expected: module import fails.

- [ ] **Step 3: Extend immutable signal and journal payloads**

Add optional fields to `SignalEvent` with safe defaults only if needed for exact reconciliation: `session_label`, `h1_atr_decile`, `decision_config_hash`, and `control_contract_hash`. Existing tests must remain source compatible.

```python
@dataclass(frozen=True)
class ShadowGate:
    experiment_id: str
    terminal_receipt_sha256: str
    prereg_hash: str
    config_hash: str
    data_contract_hash: str
    broker_cost_contract_hash: str

class ShadowGateError(ValueError):
    """The immutable diagnostic receipt does not authorize zero-risk shadow."""

class ShadowInputError(ValueError):
    """The already-materialized public/demo quote payload is incomplete."""

def validate_shadow_gate(receipt: Mapping[str, Any], receipt_sha256: str) -> ShadowGate:
    if receipt.get("verdict") != "DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW":
        raise ShadowGateError("historical_shadow_gate_not_passed")
    if receipt.get("order_authority") is not False:
        raise ShadowGateError("order_authority_not_false")
    hashes = receipt["hashes"]
    return ShadowGate(
        experiment_id=str(receipt["experiment_id"]),
        terminal_receipt_sha256=receipt_sha256,
        prereg_hash=str(hashes["prereg_sha256"]),
        config_hash=str(hashes["config_sha256"]),
        data_contract_hash=str(hashes["data_manifest_sha256"]),
        broker_cost_contract_hash=str(hashes["broker_cost_contract_sha256"]),
    )
```

- [ ] **Step 4: Implement one deterministic zero-order iteration**

```python
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def load_public_quote(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    required = {"observed_at_utc", "closed_h1_rows", "bid_ask_bar", "source_hash", "source_path", "control_stress_r"}
    missing = sorted(required - payload.keys())
    if missing:
        raise ShadowInputError("missing:" + ",".join(missing))
    if payload["source_hash"] != sha256_file(Path(payload["source_path"])):
        raise ShadowInputError("source_hash")
    return payload

def evaluate_and_journal_without_orders(gate, quote, runtime_dir):
    decision = evaluate_latest_closed_h1_signal(
        quote["closed_h1_rows"],
        config_path=runtime_dir / "pinned_config.json",
    )
    if decision is None:
        return {"state": "no_signal", "order_authority": False}
    decision_payload = asdict(decision)
    HashChainJournal(runtime_dir / "signal.jsonl", stream="xau_shadow_signal_v1").append(
        decision_payload,
        idempotency_key=decision.event_id,
        prereg_hash=gate.prereg_hash,
        source_hash=quote["source_hash"],
    )
    HashChainJournal(runtime_dir / "decision.jsonl", stream="xau_shadow_decision_v1").append(
        decision_payload,
        idempotency_key=decision.event_id,
        prereg_hash=gate.prereg_hash,
        source_hash=quote["source_hash"],
    )
    bar = BidAskBar(**quote["bid_ask_bar"])
    execution = reprice_decisions(
        [decision], [bar], BrokerCostContract.from_path(runtime_dir / "broker_cost_contract.json", "stress"),
    )
    state = "closed" if execution.trades else ("pending" if execution.censored else "blocked")
    payload = {
        "event_id": decision.event_id,
        "state": state,
        "execution": asdict(execution),
        "order_authority": False,
    }
    HashChainJournal(runtime_dir / "intended_fill.jsonl", stream="xau_shadow_intended_fill_v1").append(
        payload,
        idempotency_key=decision.event_id,
        prereg_hash=gate.prereg_hash,
        source_hash=quote["source_hash"],
    )
    if execution.trades:
        outcome = {**asdict(execution.trades[0]), "state": "closed", "control_stress_r": quote["control_stress_r"]}
        HashChainJournal(runtime_dir / "outcome.jsonl", stream="xau_shadow_outcome_v1").append(
            outcome, idempotency_key=decision.event_id,
            prereg_hash=gate.prereg_hash, source_hash=quote["source_hash"],
        )
    reconciliation = {
        "event_id": decision.event_id,
        "status": "PASS" if not execution.blocked else "FAIL",
        "blocked": [asdict(row) for row in execution.blocked],
        "order_authority": False,
    }
    HashChainJournal(runtime_dir / "reconciliation.jsonl", stream="xau_shadow_reconciliation_v1").append(
        reconciliation, idempotency_key=decision.event_id,
        prereg_hash=gate.prereg_hash, source_hash=quote["source_hash"],
    )
    return payload

def shadow_once(gate_receipt: Path, quote_file: Path, runtime_dir: Path) -> dict[str, Any]:
    try:
        gate = validate_shadow_gate(load_json(gate_receipt), sha256_file(gate_receipt))
    except ShadowGateError as exc:
        return {"state": "blocked", "reason": str(exc), "order_authority": False}
    quote = load_public_quote(quote_file)
    heartbeat = {
        "authority": "research_only_no_live_or_promotion",
        "promotion_authority": False,
        "network_authority": False,
        "private_api_authority": False,
        "order_authority": False,
        "live_write_authority": False,
        "quote_source_hash": sha256_file(quote_file),
        "gate": asdict(gate),
    }
    HashChainJournal(runtime_dir / "heartbeat.jsonl", stream="xau_shadow_heartbeat_v1").append(
        heartbeat, idempotency_key=quote["observed_at_utc"], prereg_hash=gate.prereg_hash, source_hash=heartbeat["quote_source_hash"],
    )
    return evaluate_and_journal_without_orders(gate, quote, runtime_dir)
```

The runner accepts observed quotes only from an already-materialized file or stdin. It has no MT5 import and no credential/environment lookup. A separate owner-controlled export process may produce the quote file after token rotation.

- [ ] **Step 5: Add prospective gate counters and incident semantics**

```python
def _journal_payloads(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line)["payload"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def terminal_outcomes(runtime_dir: Path) -> list[dict[str, Any]]:
    return [row for row in _journal_payloads(runtime_dir / "outcome.jsonl") if row.get("state") == "closed"]

def observed_utc_days(runtime_dir: Path) -> int:
    dates = {row["observed_at_utc"][:10] for row in _journal_payloads(runtime_dir / "heartbeat.jsonl")}
    return len(dates)

def integrity_incidents(runtime_dir: Path) -> list[dict[str, Any]]:
    return [row for row in _journal_payloads(runtime_dir / "reconciliation.jsonl") if row.get("status") != "PASS"]

def paired_stress_excess(runtime_dir: Path) -> float:
    outcomes = terminal_outcomes(runtime_dir)
    return statistics.fmean(row["stress_r"] - row["control_stress_r"] for row in outcomes) if outcomes else 0.0

def prospective_status(runtime_dir: Path) -> dict[str, Any]:
    outcomes = terminal_outcomes(runtime_dir)
    dates = {row["utc_entry_session_date"] for row in outcomes}
    days = observed_utc_days(runtime_dir)
    incidents = integrity_incidents(runtime_dir)
    return {
        "utc_days": days,
        "terminal_demo_signals": len(outcomes),
        "session_dates": len(dates),
        "broker_cost_stress_excess_r": paired_stress_excess(runtime_dir),
        "integrity_incidents": len(incidents),
        "verdict": "PROSPECTIVE_SHADOW_EVIDENCE_PASS" if (
            days >= 60 and len(outcomes) >= 30 and len(dates) >= 20
            and paired_stress_excess(runtime_dir) > 0.0 and not incidents
        ) else "COLLECTING_ZERO_RISK_EVIDENCE",
        "money_authority": False,
    }
```

- [ ] **Step 6: Run safety and regression tests**

Run: `pytest -q tests/test_run_xauusd_zero_order_shadow_v1.py tests/test_xau_mt5_zero_order_paper.py`

Expected: all pass; static safety scan finds no order/private client surface.

- [ ] **Step 7: Commit the default-off shadow runner**

```bash
git add scripts/run_xauusd_zero_order_shadow_v1.py bot/xau_mt5_zero_order_paper.py tests/test_run_xauusd_zero_order_shadow_v1.py
git commit -m "research: add gated zero-order XAU demo shadow"
```

### Task 8: Verify the complete XAU lane and publish the handoff

**Files:**
- Modify: `reports/CURRENT_PROJECT_ROADMAP.md`
- Create: `reports/XAUUSD_UNCHANGED_REPLICATION_V1_RUNBOOK.md`
- Modify only after a real run: `reports/CODEX_SESSION_CHECKPOINT_2026_08_29.md`

**Interfaces:**
- Consumes: all committed tasks and either a real terminal receipt or an explicit `BLOCKED_DATA_OR_PARITY` receipt.
- Produces: one reproducible runbook and a checkpoint that distinguishes code readiness, data authority, historical diagnostic, shadow readiness, and money authority.

- [ ] **Step 1: Write the exact runbook commands**

```bash
python3 scripts/preflight_xauusd_unchanged_replication_v1.py \
  --config configs/research/xauusd_unchanged_replication_v1.json \
  --data-manifest research_lab/data/xauusd_replication_v1/data_manifest.json \
  --out research_lab/results/xauusd_unchanged_replication_v1/preflight.json

python3 scripts/run_xauusd_unchanged_replication_v1.py \
  --config configs/research/xauusd_unchanged_replication_v1.json \
  --data-manifest research_lab/data/xauusd_replication_v1/data_manifest.json \
  --output-root research_lab/results/xauusd_unchanged_replication_v1

python3 scripts/audit_xauusd_unchanged_replication_v1.py \
  --preflight research_lab/results/xauusd_unchanged_replication_v1/preflight.json
```

The auditor reads the exact `run_id` and expected result-directory hash from the preflight receipt; it must never discover a directory by “latest” or modification time.

- [ ] **Step 2: Run the complete focused suite from a clean process**

Run: `pytest -q tests/test_preflight_xauusd_unchanged_replication_v1.py tests/test_xau_data_contract_v1.py tests/test_import_xau_mt5_demo_export_v1.py tests/test_xau_unchanged_replication_v1.py tests/test_xau_execution_parity_v1.py tests/test_xau_matched_control_v1.py tests/test_audit_xauusd_unchanged_replication_v1.py tests/test_run_xauusd_zero_order_shadow_v1.py tests/test_xau_mt5_zero_order_paper.py tests/test_fx_native_harness_window.py tests/test_fx_setups.py`

Expected: all tests pass with no xfail or skip in the newly added files.

- [ ] **Step 3: Run syntax, authority, and secret-surface checks**

```bash
python3 -m py_compile research_lab/xau_data_contract_v1.py research_lab/xau_unchanged_replication_v1.py research_lab/xau_execution_parity_v1.py research_lab/xau_matched_control_v1.py scripts/import_xau_mt5_demo_export_v1.py scripts/preflight_xauusd_unchanged_replication_v1.py scripts/run_xauusd_unchanged_replication_v1.py scripts/audit_xauusd_unchanged_replication_v1.py scripts/run_xauusd_zero_order_shadow_v1.py
rg -n "order_send|submit_order|place_order|OANDA_API_TOKEN|MT5.*TOKEN|BYBIT.*KEY" research_lab/xau_*_v1.py scripts/*xauusd*v1.py tests/test_xau_*v1.py
```

Expected: `py_compile` exits 0. `rg` returns no credential access and no order-submission surface; documented forbidden-string assertions in tests may appear and must be reviewed as test text, not runtime imports.

- [ ] **Step 4: Independently verify Git scope and hashes**

Run: `git diff --check && git status --short && git diff --name-only HEAD~8..HEAD`

Expected: no whitespace errors; only XAU plan files, explicitly shared control dependencies, roadmap/checkpoint, and pre-existing approved sprint files are in scope.

- [ ] **Step 5: Record the truthful terminal state**

Use exactly one of these checkpoint statements:

```text
XAUUSD unchanged replication: BLOCKED_DATA_OR_PARITY — independent OANDA/Bullwaves demo feed or broker bid/ask cost contract is missing; no shadow, live, order, risk, promotion, or money authority.
```

```text
XAUUSD unchanged replication: DIAGNOSTIC_REPLICATION_FAIL — unchanged historical proxy did not pass the frozen gate; negative result and audit receipt published; no shadow or money authority.
```

```text
XAUUSD unchanged replication: DIAGNOSTIC_SUPPORTS_ZERO_RISK_SHADOW — independent feed, executable repricing, controls, stress, concentration, and audit passed; only the default-off zero-order demo journal is eligible; money authority remains false.
```

- [ ] **Step 6: Commit the runbook and checkpoint**

```bash
git add reports/XAUUSD_UNCHANGED_REPLICATION_V1_RUNBOOK.md reports/CURRENT_PROJECT_ROADMAP.md reports/CODEX_SESSION_CHECKPOINT_2026_08_29.md
git commit -m "docs: publish XAU replication runbook and gate"
```

- [ ] **Step 7: Push only after the branch is clean and tests are fresh**

Run: `git push origin codex/recovery-20260824`

Expected: push succeeds without force; local and remote branch tips match. If the branch has diverged, stop and publish `BLOCKED_GIT_DIVERGENCE` instead of rebasing or force-pushing automatically.
