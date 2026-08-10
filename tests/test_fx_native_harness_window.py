from datetime import datetime, timezone

import pytest

from scripts.run_fx_native_harness import _parse_utc_boundary


def test_parse_utc_boundary_is_midnight_utc():
    value = _parse_utc_boundary("2025-07-08")

    assert value == datetime(2025, 7, 8, tzinfo=timezone.utc).timestamp()


def test_parse_utc_boundary_allows_empty_value():
    assert _parse_utc_boundary("") is None


def test_parse_utc_boundary_rejects_non_iso_date():
    with pytest.raises(ValueError):
        _parse_utc_boundary("08/07/2025")
