import json
from pathlib import Path

from scripts.materialize_bybit_research_archive import _sha256
from scripts.validate_bybit_research_archive import validate


def _write(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_archive_integrity_can_pass_while_pit_survivorship_remains_blocked(tmp_path: Path):
    provider = {
        "records": [
            {"symbol": "AAAUSDT", "status": "Trading"},
            {"symbol": "OLDUSDT", "status": "Closed"},
        ]
    }
    listing = {
        "requested_symbols": ["AAAUSDT"],
        "provider_snapshot": provider,
        "payload_sha256": _sha256(provider),
    }
    rows = [{"funding_time_ms": 1000, "funding_rate": 0.0001}]
    funding = {
        "symbol": "AAAUSDT",
        "requested_start_ms": 0,
        "as_of_ms": 2000,
        "instrument": {"status": "Trading"},
        "coverage": {"observations": 1, "coverage_vs_upper_bound": 1.0},
        "records": rows,
        "payload_sha256": _sha256(rows),
    }
    _write(tmp_path / "status.json", {"state": "complete", "private_api_calls": False, "orders_or_risk_mutation": False, "failed": {}})
    _write(tmp_path / "listing_intervals.json", listing)
    _write(tmp_path / "funding/AAAUSDT.json", funding)

    result = validate(tmp_path)

    assert result["integrity_pass"] is True
    assert result["verdict"] == "INTEGRITY_PASS_PIT_NOT_READY"
    assert result["pit_ohlcv_survivorship_resolved"] is False


def test_archive_hash_mismatch_fails_integrity(tmp_path: Path):
    provider = {"records": [{"symbol": "AAAUSDT", "status": "Trading"}]}
    _write(tmp_path / "status.json", {"state": "complete", "private_api_calls": False, "orders_or_risk_mutation": False, "failed": {}})
    _write(tmp_path / "listing_intervals.json", {"requested_symbols": ["AAAUSDT"], "provider_snapshot": provider, "payload_sha256": _sha256(provider)})
    _write(tmp_path / "funding/AAAUSDT.json", {
        "symbol": "AAAUSDT", "requested_start_ms": 0, "as_of_ms": 2000,
        "instrument": {"status": "Trading"},
        "coverage": {"observations": 1, "coverage_vs_upper_bound": 1.0},
        "records": [{"funding_time_ms": 1000}], "payload_sha256": "bad",
    })
    result = validate(tmp_path)
    assert result["integrity_pass"] is False
    assert "AAAUSDT:payload_hash_mismatch" in result["errors"]
