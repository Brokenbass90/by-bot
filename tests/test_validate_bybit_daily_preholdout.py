import json

from scripts.materialize_bybit_daily_preholdout import AUTHORITY, canonical_sha
from scripts.validate_bybit_daily_preholdout import validate


def test_validator_separates_integrity_from_partial_market_coverage(tmp_path):
    root = tmp_path / "spot"
    (root / "bars").mkdir(parents=True)
    rows = [{"ts_ms": 1000, "open": 1, "high": 2, "low": .5, "close": 1.5}]
    (root / "bars" / "AAAUSDT.json").write_text(json.dumps({
        "symbol": "AAAUSDT", "category": "spot", "records": rows,
        "payload_sha256": canonical_sha(rows),
    }), encoding="utf-8")
    (root / "status.json").write_text(json.dumps({
        "state": "complete", "authority": AUTHORITY, "private_api_calls": False,
        "orders_or_risk_mutation": False, "sealed_holdout_rows_decoded": 0,
        "category": "spot", "requested": 2, "completed": ["AAAUSDT"],
        "failed": {"BBBUSD": "unsupported"}, "skipped": [],
        "start_ms": 1000, "end_exclusive_ms": 2000,
    }), encoding="utf-8")
    result = validate(root)
    assert result["verdict"] == "INTEGRITY_PASS_PARTIAL_MARKET_COVERAGE"
    assert result["total_rows"] == 1
    assert result["pit_universe_ready"] is False
