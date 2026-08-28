from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

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
    return {"config": config, "config_path": config_path, "authorization": authorization, "authorization_path": authorization_path,
            "candidate_path": tmp_path / config["candidate_manifest"]["path"], "manifest": manifest,
            "manifest_path": manifest_path, "payloads": payloads}


def _rebind_payload_and_authority(fixture: dict[str, object], symbol: str, mutated_bytes: bytes) -> None:
    payloads, manifest = fixture["payloads"], fixture["manifest"]
    payloads[symbol] = mutated_bytes
    row = next(item for item in manifest["inputs"] if item["symbol"] == symbol)
    row["sha256"], row["bytes"] = _sha_bytes(mutated_bytes), len(mutated_bytes)
    _json(fixture["manifest_path"], manifest)
    config = fixture["config"]
    config["reserved_data_contract"]["reserved_m5_input_manifest"]["sha256"] = _sha_file(fixture["manifest_path"])
    config.pop("config_fingerprint_sha256", None)
    config["config_fingerprint_sha256"] = _canonical_sha(config)
    _json(fixture["config_path"], config)
    authorization = fixture["authorization"]
    authorization["input_manifest_sha256"] = _sha_file(fixture["manifest_path"])
    authorization["config_sha256"] = _sha_file(fixture["config_path"])
    _json(fixture["authorization_path"], authorization)


def _bootstrap_payload(symbol: str) -> bytes:
    return json.dumps(
        {
            "schema_id": "bybit_public_m5_preholdout_v1",
            "symbol": symbol,
            "records": [{"ts_ms": 1_700_000_000_000, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _install_tiny_bootstrap(fixture: dict[str, object], *, corrupt_second: bool = False) -> None:
    candidate_path = fixture["candidate_path"]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    rows = []
    for index, symbol in enumerate(SYMBOLS):
        relative = f"research_lab/data/tiny-bootstrap/{symbol}.json"
        raw = b"not-json" if corrupt_second and index == 1 else _bootstrap_payload(symbol)
        path = candidate_path.parents[2] / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows.append({"symbol": symbol, "path": relative, "sha256": _sha_bytes(raw), "bytes": len(raw)})
    candidate["data_files"] = rows
    _json(candidate_path, candidate)

    config = fixture["config"]
    candidate_sha = _sha_file(candidate_path)
    config["candidate_manifest"]["sha256"] = candidate_sha
    for pin in config["source_pins"]:
        if pin["path"] == config["candidate_manifest"]["path"]:
            pin["sha256"] = candidate_sha
    config.pop("config_fingerprint_sha256", None)
    config["config_fingerprint_sha256"] = _canonical_sha(config)
    _json(fixture["config_path"], config)

    authorization = fixture["authorization"]
    authorization["config_sha256"] = _sha_file(fixture["config_path"])
    _json(fixture["authorization_path"], authorization)


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


@pytest.mark.parametrize("drift", ["hash", "schema", "window", "gap", "records_sha", "infinite_ohlc"])
def test_market_input_drift_consumes_attempt_and_cannot_retry(tmp_path: Path, drift: str) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)
    payloads = fixture["payloads"]
    if drift == "hash":
        payloads["BTCUSDT"] = b"{}"
    elif drift == "schema":
        value = json.loads(payloads["BTCUSDT"])
        value["schema_id"] = "wrong"
        _rebind_payload_and_authority(fixture, "BTCUSDT", json.dumps(value).encode())
    elif drift == "window":
        value = json.loads(payloads["BTCUSDT"])
        value["window"]["end_utc_exclusive"] = "2026-06-30T00:00:00Z"
        _rebind_payload_and_authority(fixture, "BTCUSDT", json.dumps(value).encode())
    elif drift == "records_sha":
        value = json.loads(payloads["BTCUSDT"])
        value["records_sha256"] = "0" * 64
        _rebind_payload_and_authority(fixture, "BTCUSDT", json.dumps(value).encode())
    elif drift == "infinite_ohlc":
        from scripts.materialize_att1_sbr1_reserved_m5_v1 import canonical_sha
        value = json.loads(payloads["BTCUSDT"])
        value["records"][0]["high"] = "Infinity"
        value["records_sha256"] = canonical_sha(value["records"])
        _rebind_payload_and_authority(fixture, "BTCUSDT", json.dumps(value).encode())
    else:
        _rebind_payload_and_authority(fixture, "BTCUSDT", _payload("BTCUSDT", gap=True))
    expected = {"hash": "hash drift", "schema": "schema/window", "window": "schema/window", "gap": "M5 gap", "records_sha": "records SHA", "infinite_ohlc": "OHLC"}[drift]
    with pytest.raises(OneShotViolation, match=expected):
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


def test_prepare_scoring_market_keeps_exact_warm_prefix_and_half_open_decisions() -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import MAJOR8, START_MS, END_MS, _prepare_scoring_market

    hour = 3_600_000
    prefix = tuple((START_MS - 201 * hour + index * hour, 10, 11, 9, 10 + index / 100, 1) for index in range(201))
    reserved = tuple((START_MS + index * hour, 20, 21, 19, 20 + index / 10, 1) for index in range(273 * 24))
    m5 = tuple((START_MS + index * 300_000, 10, 11, 9, 10, 1) for index in range(12))
    market, regime = _prepare_scoring_market(
        preholdout_h1={symbol: prefix for symbol in MAJOR8}, reserved_m5={symbol: m5 for symbol in MAJOR8}, reserved_h1={symbol: reserved for symbol in MAJOR8},
    )
    for data in market.values():
        assert len(data.h1[:200]) == 200
        assert data.h1[200][0] == START_MS
        assert all(START_MS < row[0] + hour < END_MS for row in data.h1[200:])
    assert set(regime) == {row[0] + hour for row in reserved if row[0] + hour < END_MS}


def test_real_scorer_prepares_market_once_and_reuses_exact_objects_for_both_sleeves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from research_lab import run_att1_sbr1_actual_adapter_parity as parity
    from scripts import run_att1_sbr1_reserved_oos_v1 as runner

    bootstrap_rows = []
    for symbol in SYMBOLS:
        relative = f"bootstrap/{symbol}.json"
        raw = _bootstrap_payload(symbol)
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        bootstrap_rows.append({"symbol": symbol, "path": relative, "sha256": _sha_bytes(raw), "bytes": len(raw)})

    prepared_market, prepared_regime = object(), object()
    prepare_calls: list[tuple[object, object, object]] = []
    sleeve_calls: list[tuple[str, object, object]] = []

    def prepare(**kwargs: object) -> tuple[object, object]:
        prepare_calls.append((kwargs["preholdout_h1"], kwargs["reserved_m5"], kwargs["reserved_h1"]))
        return prepared_market, prepared_regime

    def run_sleeve(sleeve: str, _root: Path, _output: Path, _manifest: object, market_data: object, regime: object) -> str:
        sleeve_calls.append((sleeve, market_data, regime))
        return sleeve

    monkeypatch.setattr(runner, "_prepare_scoring_market", prepare)
    monkeypatch.setattr(parity, "_aggregate_h1", lambda _rows: ((1_700_000_000_000, 10, 11, 9, 10, 1),))
    monkeypatch.setattr(parity, "_frozen_env", lambda _universe: nullcontext())
    monkeypatch.setattr(parity, "_run_sleeve", run_sleeve)

    result = runner._real_scorer(
        root=tmp_path,
        output=tmp_path / "output",
        candidate={"data_files": bootstrap_rows},
        market={symbol: {"records": []} for symbol in SYMBOLS},
        manifest_view=SimpleNamespace(universe=tuple(SYMBOLS)),
    )

    assert result == {"ATT1": "ATT1", "SBR1": "SBR1"}
    assert len(prepare_calls) == 1
    assert sleeve_calls == [("ATT1", prepared_market, prepared_regime), ("SBR1", prepared_market, prepared_regime)]
    assert all(market_data is prepared_market and regime is prepared_regime for _, market_data, regime in sleeve_calls)


def test_semantic_reserved_failure_preserves_observed_rows_and_staged_accounting(tmp_path: Path) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)
    payload = json.loads(fixture["payloads"]["BTCUSDT"])
    payload["records_sha256"] = "0" * 64
    _rebind_payload_and_authority(fixture, "BTCUSDT", json.dumps(payload).encode())

    with pytest.raises(OneShotViolation, match="records SHA"):
        run_one_shot(tmp_path, market_opener=lambda path: fixture["payloads"][path.stem])

    receipt = json.loads((tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/receipt.json").read_text())
    reserved = receipt["decode_accounting"]["reserved"]
    bitcoin = reserved["inputs"]["BTCUSDT"]
    assert receipt["market_decode_finished_at_utc"]
    assert bitcoin["opened_bytes"] == len(fixture["payloads"]["BTCUSDT"])
    assert bitcoin["opened_sha256"] == _sha_bytes(fixture["payloads"]["BTCUSDT"])
    assert bitcoin["json_decoded"] is True
    assert bitcoin["rows_observed"] == ROWS
    assert bitcoin["validation_status"] == "FAILED"
    assert "records SHA drift:BTCUSDT" in bitcoin["validation_error"]
    assert reserved["inputs_opened"] == 1
    assert reserved["inputs_decoded"] == 1
    assert reserved["inputs_validated"] == 0
    assert reserved["rows_observed"] == ROWS
    assert reserved["rows_validated"] == 0


def test_bootstrap_parse_failure_keeps_consumed_claim_and_partial_forensics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot
    from research_lab import run_att1_sbr1_actual_adapter_parity as parity

    fixture = _fixture_tree(tmp_path)
    _install_tiny_bootstrap(fixture, corrupt_second=True)
    monkeypatch.setattr(parity, "_aggregate_h1", lambda _rows: ((1_700_000_000_000, 10, 11, 9, 10, 1),))

    with pytest.raises(OneShotViolation, match="TASK3_BOOTSTRAP_PREHOLDOUT_UNREADABLE:ETHUSDT"):
        run_one_shot(tmp_path, market_opener=lambda path: fixture["payloads"][path.stem])

    output = tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1"
    receipt = json.loads((output / "receipt.json").read_text())
    bootstrap = receipt["decode_accounting"]["bootstrap"]
    assert (output / "one_shot_claim.json").is_file()
    assert receipt["terminal_state"] == "FAIL_CLOSED_AFTER_CLAIM"
    assert receipt["classification"] == "RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION"
    assert receipt["terminal_at_utc"]
    assert set(bootstrap["inputs"]) == {"BTCUSDT", "ETHUSDT"}
    assert bootstrap["inputs"]["BTCUSDT"]["validation_status"] == "VALIDATED"
    assert bootstrap["inputs"]["ETHUSDT"]["validation_status"] == "FAILED"
    assert receipt["decode_accounting"]["reserved"]["inputs_validated"] == len(SYMBOLS)
    assert receipt["partial_output_file_sha256"] == {}
    assert receipt["market_decode_finished_at_utc"] == bootstrap["ended_at_utc"]
    assert receipt["market_decode_finished_at_utc"] >= bootstrap["started_at_utc"]


@pytest.mark.parametrize("artifact", ["extra", "symlink"])
def test_failure_receipt_observes_unexpected_or_symlinked_output_entry(tmp_path: Path, artifact: str) -> None:
    from scripts.run_att1_sbr1_reserved_oos_v1 import OneShotViolation, run_one_shot

    fixture = _fixture_tree(tmp_path)

    def scorer(*, output: Path, **_kwargs: object) -> None:
        output.mkdir(parents=True, exist_ok=True)
        if artifact == "extra":
            (output / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
        else:
            target = tmp_path / "symlink-target.txt"
            target.write_text("target\n", encoding="utf-8")
            (output / "unexpected-link").symlink_to(target)

    with pytest.raises(OneShotViolation, match="unexpected scorer output inventory"):
        run_one_shot(tmp_path, market_opener=lambda path: fixture["payloads"][path.stem], scorer=scorer)

    receipt = json.loads((tmp_path / "research_lab/results/att1_sbr1_reserved_oos_v1/receipt.json").read_text())
    name = "unexpected.txt" if artifact == "extra" else "unexpected-link"
    observed = next(entry for entry in receipt["observed_output_entries"] if entry["name"] == name)
    assert observed["status"] == ("HASHED" if artifact == "extra" else "UNHASHED_SYMLINK")
    assert observed["is_symlink"] is (artifact == "symlink")
