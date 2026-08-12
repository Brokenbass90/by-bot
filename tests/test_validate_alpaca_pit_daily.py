import json

from scripts.validate_alpaca_pit_daily import canonical_sha, validate_archive


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validator_builds_pool_pit_interval_without_promoting(tmp_path):
    archive = tmp_path / "archive"
    rows = [{"t": 1704067200000, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]
    _write(archive / "universe.json", {
        "symbols": ["AAA"],
        "reference": [{"ticker": "AAA", "active": True}],
    })
    _write(archive / "status.json", {"state": "complete", "requested": 1, "failed": {}})
    _write(archive / "bars/AAA.json", {
        "symbol": "AAA", "adjusted": True, "records": rows, "payload_sha256": canonical_sha(rows),
    })
    receipt, manifest = validate_archive(archive)
    assert receipt["integrity_pass"] is True
    assert receipt["clean_subset_integrity_pass"] is True
    assert receipt["point_in_time_membership_within_selected_pool"] is True
    assert receipt["full_market_point_in_time_universe"] is False
    assert receipt["promotion_authorized"] is False
    assert manifest["intervals"][0]["observed_from"] == "2024-01-01"


def test_validator_fails_on_running_or_tampered_archive(tmp_path):
    archive = tmp_path / "archive"
    rows = [{"t": 1704067200000}]
    _write(archive / "universe.json", {"symbols": ["AAA"], "reference": []})
    _write(archive / "status.json", {"state": "running", "requested": 1, "failed": {}})
    _write(archive / "bars/AAA.json", {
        "symbol": "AAA", "adjusted": True, "records": rows, "payload_sha256": "bad",
    })
    receipt, _ = validate_archive(archive)
    assert receipt["integrity_pass"] is False
    assert "materialization_not_complete:running" in receipt["errors"]
    assert "AAA:sha256_mismatch" in receipt["errors"]
    assert receipt["clean_subset_integrity_pass"] is False


def test_validator_quarantines_post_delist_ticker_identity_conflict(tmp_path):
    archive = tmp_path / "archive"
    good_rows = [{"t": 1704067200000, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]
    reused_rows = [{"t": 1722470400000, "o": 1, "h": 2, "l": 1, "c": 2, "v": 3}]
    _write(archive / "universe.json", {
        "symbols": ["GOOD", "REUSE"],
        "reference": [
            {"ticker": "GOOD", "active": True},
            {"ticker": "REUSE", "active": False, "delisted_utc": "2024-06-01T00:00:00Z"},
        ],
    })
    _write(archive / "status.json", {"state": "complete", "requested": 2, "failed": {}})
    _write(archive / "bars/GOOD.json", {
        "symbol": "GOOD", "adjusted": True, "records": good_rows,
        "payload_sha256": canonical_sha(good_rows),
    })
    _write(archive / "bars/REUSE.json", {
        "symbol": "REUSE", "adjusted": True, "records": reused_rows,
        "payload_sha256": canonical_sha(reused_rows),
    })

    receipt, manifest = validate_archive(archive)

    assert receipt["integrity_pass"] is False
    assert receipt["clean_subset_integrity_pass"] is True
    assert receipt["promotion_authorized"] is False
    assert receipt["clean_subset_symbols"] == 1
    assert receipt["quarantined_symbols"] == [{
        "symbol": "REUSE",
        "reason": "ticker_identity_conflict_bar_after_delist",
    }]
    assert [row["symbol"] for row in manifest["intervals"]] == ["GOOD"]
    assert manifest["promotion_authorized"] is False
