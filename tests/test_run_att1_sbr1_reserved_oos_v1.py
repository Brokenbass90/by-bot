from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT"]
START_MS = 1_759_276_800_000
END_MS = 1_782_864_000_000
ROWS = 273 * 288


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _canonical_sha(value: object) -> str:
    return _sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _payload(symbol: str, *, gap: bool = False) -> bytes:
    from scripts.materialize_att1_sbr1_reserved_m5_v1 import canonical_sha

    rows = [
        {"ts_ms": START_MS + index * 300_000 + (300_000 if gap and index == 4 else 0),
         "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1, "turnover": 10}
        for index in range(ROWS)
    ]
    value = {
        "schema_id": "att1_sbr1_reserved_m5_payload_v1",
        "authority": "identity_only_materialized_without_scoring_no_live_no_broker",
        "symbol": symbol,
        "window": {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"},
        "timeframe_minutes": 5,
        "records": rows,
        "records_sha256": canonical_sha(rows),
        "performance_computed": False,
        "money_authority": False,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixture_tree(tmp_path: Path, *, with_authorization: bool = True) -> dict[str, object]:
    config = json.loads((ROOT / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json").read_text())
    candidate = json.loads((ROOT / config["candidate_manifest"]["path"]).read_text())
    paths = {row["path"] for row in config["source_pins"]}
    paths.update(row["path"] for row in candidate["source_files"])
    for relative in paths:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)

    runner = tmp_path / "scripts/run_att1_sbr1_reserved_oos_v1.py"
    runner.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "scripts/run_att1_sbr1_reserved_oos_v1.py", runner)
    audit = tmp_path / "scripts/audit_att1_sbr1_reserved_oos_v1.py"
    audit.write_text("# frozen audit placeholder\n", encoding="utf-8")
    payloads = {symbol: _payload(symbol) for symbol in SYMBOLS}
    inputs = []
    for symbol in SYMBOLS:
        relative = f"data_cache/immutable/att1_sbr1_reserved_m5_v1/{symbol}.json"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture-placeholder")
        inputs.append({"symbol": symbol, "source_path": relative, "sha256": _sha_bytes(payloads[symbol]),
                       "bytes": len(payloads[symbol]), "rows": ROWS, "first_ts_ms": START_MS,
                       "last_ts_ms": END_MS - 300_000})
    manifest = {
        "schema_id": "att1_sbr1_reserved_m5_input_manifest_v1",
        "authority": "identity_only_materialized_without_scoring_no_live_no_broker",
        "market_rows_decoded_by_preflight": 0, "performance_computed": False,
        "money_authority": False, "window": {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"},
        "timeframe_minutes": 5, "inputs": inputs,
    }
    manifest_path = tmp_path / "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json"
    _json(manifest_path, manifest)
    config["reserved_data_contract"]["reserved_m5_input_manifest"] = {
        "path": "configs/research/att1_sbr1_reserved_m5_input_manifest_v1.json", "sha256": _sha_file(manifest_path),
    }
    config["future_one_shot"].update({"runner_sha256": _sha_file(runner), "audit_sha256": _sha_file(audit)})
    config.pop("config_fingerprint_sha256", None)
    config["config_fingerprint_sha256"] = _canonical_sha(config)
    config_path = tmp_path / "configs/research/att1_sbr1_reserved_oos_diagnostic_v1.json"
    _json(config_path, config)
    authorization = {
        "schema_id": "att1_sbr1_reserved_oos_owner_authorization_v1",
        "authority": "owner_explicit_one_shot_reserved_diagnostic_only",
        "owner_authorization_id": "fixture-owner-auth-1", "execute_once": True,
        "known_contamination_acknowledged": True, "money_authority": False,
        "reserved_window": config["reserved_window"],
        "config_sha256": _sha_file(config_path), "input_manifest_sha256": _sha_file(manifest_path),
        "runner_sha256": _sha_file(runner), "audit_sha256": _sha_file(audit),
        "output_path": "research_lab/results/att1_sbr1_reserved_oos_v1",
        "claim_path": "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json",
    }
    authorization_path = tmp_path / "configs/research/att1_sbr1_reserved_oos_owner_authorization_v1.json"
    if with_authorization:
        _json(authorization_path, authorization)
    return {"config": config, "authorization": authorization, "authorization_path": authorization_path,
            "manifest": manifest, "manifest_path": manifest_path, "payloads": payloads}


def test_missing_authorization_never_opens_market_or_creates_claim(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    _fixture_tree(tmp_path, with_authorization=False)
    opened = 0

    def opener(_path: Path) -> bytes:
        nonlocal opened
        opened += 1
        raise AssertionError("market payload must remain unopened")

    with pytest.raises(OneShotViolation, match="authorization"):
        run_one_shot(tmp_path, market_opener=opener)

    assert opened == 0
    assert not (tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json").exists()


@pytest.mark.parametrize("mutation", ["malformed", "drifted"])
def test_invalid_authorization_never_opens_market_or_creates_claim(tmp_path: Path, mutation: str) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)
    authorization_path = fixture["authorization_path"]
    if mutation == "malformed":
        authorization_path.write_text("[]", encoding="utf-8")
    else:
        authorization = dict(fixture["authorization"])
        authorization["runner_sha256"] = "0" * 64
        _json(authorization_path, authorization)
    opened = 0

    def opener(_path: Path) -> bytes:
        nonlocal opened
        opened += 1
        raise AssertionError("market payload must remain unopened")

    with pytest.raises(OneShotViolation, match="authorization"):
        run_one_shot(tmp_path, market_opener=opener)
    assert opened == 0
    assert not (tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json").exists()


def test_claim_is_durable_before_scorer_callback(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)
    calls: list[str] = []

    def scorer(**_kwargs: object) -> dict[str, object]:
        claim = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json"
        assert claim.is_file()
        assert json.loads(claim.read_text())["state"] == "CLAIMED_BEFORE_MARKET_DECODE"
        calls.append("scored")
        return {"ATT1": {"base": [], "stress": []}, "SBR1": {"base": [], "stress": []}}

    with pytest.raises(OneShotViolation, match="unexpected scorer output"):
        run_one_shot(tmp_path, market_opener=lambda path: fixture["payloads"][path.stem], scorer=scorer)
    assert calls == ["scored"]
    receipt = json.loads((tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/receipt.json").read_text())
    assert receipt["market_decode_started_at_utc"]


def test_existing_claim_refuses_before_scorer_callback(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    _fixture_tree(tmp_path)
    claim = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json"
    _json(claim, {"state": "CLAIMED_BEFORE_MARKET_DECODE"})
    with pytest.raises(OneShotViolation, match="ONE_SHOT_ALREADY_CONSUMED"):
        run_one_shot(tmp_path, scorer=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("scored")))


@pytest.mark.parametrize("drift", ["hash", "schema", "window", "gap"])
def test_market_input_drift_consumes_attempt_and_cannot_retry(tmp_path: Path, drift: str) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)
    payloads = dict(fixture["payloads"])
    if drift == "hash":
        payloads["BTCUSDT"] = b"{}"
    elif drift == "schema":
        value = json.loads(payloads["BTCUSDT"])
        value["schema_id"] = "wrong"
        payloads["BTCUSDT"] = json.dumps(value).encode()
    elif drift == "window":
        value = json.loads(payloads["BTCUSDT"])
        value["window"]["end_utc_exclusive"] = "2026-06-30T00:00:00Z"
        payloads["BTCUSDT"] = json.dumps(value).encode()
    else:
        payloads["BTCUSDT"] = _payload("BTCUSDT", gap=True)
    with pytest.raises(OneShotViolation):
        run_one_shot(tmp_path, market_opener=lambda path: payloads[path.stem])
    claim = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json"
    assert claim.is_file()
    with pytest.raises(OneShotViolation, match="ONE_SHOT_ALREADY_CONSUMED"):
        run_one_shot(tmp_path, market_opener=lambda path: payloads[path.stem])


def test_three_way_decision_boundary() -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import three_way_decision

    thresholds = {"n_gte": 2, "mean_r_gt": "0", "profit_factor_gte": "1", "both_halves_r_gt": "0",
                  "max_sequential_drawdown_r_lte": "2", "positive_month_fraction_gte": "0.5",
                  "positive_symbol_concentration_lte": "0.9", "minimum_leave_one_symbol_out_r_gt": "0"}
    passing = {"n": 2, "mean_r": "1", "profit_factor": "2", "chronological_halves_r": ["1", "1"],
               "max_sequential_drawdown_r": "1", "positive_month_fraction": "1", "positive_symbol_concentration": "0.5",
               "minimum_leave_one_symbol_out_r": "1", "sum_r": "2"}
    assert three_way_decision(passing, passing, thresholds, negative_stress_n=20) == "PASS_ZERO_RISK_INTEGRATION_ONLY"
    failing = {**passing, "mean_r": "-1", "sum_r": "-1"}
    assert three_way_decision(failing, failing, thresholds, negative_stress_n=2) == "FAIL_CLOSED"
    assert three_way_decision({**failing, "n": 1}, {**failing, "n": 1}, thresholds, negative_stress_n=2) == "INCONCLUSIVE_LOW_N"


def test_cli_has_no_force_reset_path_or_parameter_overrides() -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import build_parser

    parser = build_parser()
    for forbidden in ("--force", "--reset", "--output", "--manifest", "--costs", "--thresholds"):
        with pytest.raises(SystemExit):
            parser.parse_args([forbidden])


def test_warm_btc_regime_matches_continuous_history_not_reserved_reseed() -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import warm_btc_regime

    hour = 3_600_000
    preholdout = [(1_699_999_200_000 + index * hour, 10, 11, 9, 10 + index / 100, 1) for index in range(201)]
    reserved = [(preholdout[-1][0] + hour + index * hour, 20, 21, 19, 20 + index / 10, 1) for index in range(3)]
    warm = warm_btc_regime(preholdout, reserved)

    assert set(warm) == {row[0] + hour for row in reserved}
    assert warm[reserved[0][0] + hour].ema200 != reserved[0][4]


def test_reserved_payload_hash_matches_materializer_producer_contract() -> None:
    from scripts.materialize_att1_sbr1_reserved_m5_v1 import canonical_sha

    payload = json.loads(_payload("BTCUSDT"))
    assert payload["records_sha256"] == canonical_sha(payload["records"])


def test_reserved_manifest_view_replaces_preholdout_data_identities(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import build_reserved_manifest_view

    fixture = _fixture_tree(tmp_path)
    candidate = json.loads((tmp_path / "configs/research/att1_sbr1_live_native_parity_v1.json").read_text())
    view = build_reserved_manifest_view(candidate, fixture["manifest"], _sha_file(fixture["manifest_path"]))

    assert view.payload["window"] == {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"}
    assert view.manifest_sha256 != _sha_file(fixture["manifest_path"])
    assert view.payload["input_manifest_sha256"] == _sha_file(fixture["manifest_path"])
    assert [row["path"] for row in view.payload["data_files"]] == [row["source_path"] for row in fixture["manifest"]["inputs"]]
    assert all("preholdout" not in row["path"] for row in view.payload["data_files"])


def test_stale_output_refuses_before_claim(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    _fixture_tree(tmp_path)
    stale = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/att1_base_live.jsonl"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")
    with pytest.raises(OneShotViolation, match="stale output"):
        run_one_shot(tmp_path)
    assert not (tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json").exists()


def test_symlinked_output_refuses_before_claim(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    _fixture_tree(tmp_path)
    output = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1"
    output.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    output.symlink_to(target, target_is_directory=True)
    with pytest.raises(OneShotViolation, match="symlink"):
        run_one_shot(tmp_path)
    assert not (target / "one_shot_claim.json").exists()


def test_interrupt_after_claim_writes_terminal_receipt(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import run_one_shot

    fixture = _fixture_tree(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        run_one_shot(
            tmp_path,
            market_opener=lambda path: fixture["payloads"][path.stem],
            scorer=lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
    receipt = json.loads((tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/receipt.json").read_text())
    assert receipt["terminal_state"] == "FAIL_CLOSED_AFTER_CLAIM"


def test_success_receipt_has_exact_forensic_identity_and_inventory(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import _expected_scoring_artifacts, run_one_shot

    fixture = _fixture_tree(tmp_path)

    def scorer(*, output: Path, **_kwargs: object) -> None:
        output.mkdir(parents=True, exist_ok=True)
        for name in _expected_scoring_artifacts():
            path = output / name
            if name.endswith("parity_report.json"):
                path.write_text('{"decision":"PASS"}\n', encoding="utf-8")
            elif name.startswith(("att1_evaluation", "sbr1_evaluation")):
                path.write_text("\n", encoding="utf-8")
            else:
                sleeve = name.split("_")[0].upper()
                row = {"schema_id": "research_live_adapter_parity_v2", "sleeve_id": sleeve,
                       "release_or_promotion_authority": False, "exception": None,
                       "bar_ts": START_MS, "fill_ts_ms": START_MS, "exit_ts_ms": START_MS + 300_000,
                       "time_stop": {"deadline_ms": START_MS + 300_000}, "symbol": "BTCUSDT",
                       "signal_id": f"{sleeve}-{name}", "net_r": "1"}
                path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    receipt = run_one_shot(
        tmp_path, market_opener=lambda path: fixture["payloads"][path.stem], scorer=scorer,
        summarizer=lambda *_args, **_kwargs: {"ATT1": {"decision": "INCONCLUSIVE_LOW_N"}, "SBR1": {"decision": "INCONCLUSIVE_LOW_N"}},
    )
    assert receipt["claim_sha256"] == _sha_file(tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/one_shot_claim.json")
    assert receipt["reserved_window"] == {"start_utc": "2025-10-01T00:00:00Z", "end_utc_exclusive": "2026-07-01T00:00:00Z"}
    assert set(receipt["output_file_sha256"]) == _expected_scoring_artifacts()
    assert receipt["market_decode_started_at_utc"] <= receipt["market_decode_finished_at_utc"]
