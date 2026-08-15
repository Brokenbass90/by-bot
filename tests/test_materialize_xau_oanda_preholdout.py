import argparse
import csv
import datetime as dt
import json

import pytest

import scripts.materialize_xau_oanda_preholdout as materializer


def _args(tmp_path, **overrides):
    values = dict(
        from_utc="2025-01-01",
        to_utc="2025-01-02",
        out_dir=str(tmp_path),
        base_url="https://api-fxpractice.oanda.com",
        token="secret-not-written",
        count_per_request=5000,
        sleep_sec=0.0,
        min_free_gb=0.0,
        max_pages=0,
        preflight_only=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def _candle(when: dt.datetime, price: float = 2000.0):
    return {
        "complete": True,
        "time": when.isoformat().replace("+00:00", "Z"),
        "mid": {"o": str(price), "h": str(price + 1), "l": str(price - 1), "c": str(price + 0.5)},
        "volume": 12,
    }


def test_refuses_sealed_holdout_before_token_or_network(tmp_path):
    calls = []
    with pytest.raises(ValueError, match="sealed holdout"):
        materializer.materialize(
            _args(tmp_path, to_utc="2025-10-02", token=""),
            fetch_page=lambda **kwargs: calls.append(kwargs) or {},
        )
    assert calls == []


def test_preflight_needs_no_token_and_persists_nothing(tmp_path, capsys):
    assert materializer.materialize(_args(tmp_path, token="", preflight_only=True)) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "preflight_pass"
    assert output["sealed_holdout_rows_decoded"] == 0
    assert list(tmp_path.iterdir()) == []


def test_materializes_pages_without_persisting_token(tmp_path):
    start = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return {"candles": [_candle(start), _candle(start + dt.timedelta(minutes=5))]}

    assert materializer.materialize(_args(tmp_path, to_utc="2025-01-01T00:10:00Z"), fetch_page=fetch) == 0
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "complete_requires_independent_validation"
    assert status["rows"] == 2
    assert status["bearer_token_persisted"] is False
    assert "secret-not-written" not in (tmp_path / "status.json").read_text()
    assert calls[0]["instrument"] == "XAU_USD"
    with (tmp_path / "XAUUSD_M5.csv").open() as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_resumes_after_budget_pause_without_refetching_page(tmp_path):
    start = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    calls = []

    def fetch(**kwargs):
        cursor = kwargs["frm"]
        calls.append(cursor)
        return {"candles": [_candle(cursor)]}

    args = _args(tmp_path, to_utc="2025-01-01T00:10:00Z", count_per_request=1, max_pages=1)
    assert materializer.materialize(args, fetch_page=fetch) == 3
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "paused_budget"
    args.max_pages = 0
    assert materializer.materialize(args, fetch_page=fetch) == 0
    assert calls == [start, start + dt.timedelta(minutes=5)]


def test_page_hash_mismatch_fails_closed_before_network(tmp_path):
    start = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    args = _args(tmp_path, to_utc="2025-01-01T00:10:00Z", count_per_request=1, max_pages=1)
    assert materializer.materialize(args, fetch_page=lambda **kwargs: {"candles": [_candle(start)]}) == 3
    page = tmp_path / "pages/page_000001.csv"
    page.write_text("tampered\n")
    calls = []
    with pytest.raises(ValueError, match="receipt mismatch"):
        materializer.materialize(args, fetch_page=lambda **kwargs: calls.append(kwargs) or {})
    assert calls == []


def test_count_is_capped_by_official_limit(tmp_path):
    with pytest.raises(ValueError, match="between 1 and 5000"):
        materializer.materialize(_args(tmp_path, count_per_request=5001), fetch_page=lambda **kwargs: {})
