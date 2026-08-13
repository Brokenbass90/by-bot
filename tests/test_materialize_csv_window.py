import csv
from datetime import datetime, timezone

from scripts.materialize_csv_window import materialize


def test_materializes_only_bounded_rows(tmp_path):
    source = tmp_path / "source.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "o", "h", "l", "c", "v"])
        for day in range(1, 5):
            ts = int(datetime(2025, 1, day, tzinfo=timezone.utc).timestamp())
            writer.writerow([ts, 1, 2, 0, 1, 1])
    output, receipt = tmp_path / "out.csv", tmp_path / "receipt.json"
    result = materialize(source, output, receipt, "2025-01-02T00:00:00Z", "2025-01-04T00:00:00Z")
    assert result["rows"] == 2
    assert result["boundary_timestamp_rows_read"] == 1
    assert result["outcome_rows_at_or_after_end_used"] == 0
    assert len(output.read_text().splitlines()) == 3


def test_rejects_unsorted_source(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("ts,o,h,l,c,v\n2,1,2,0,1,1\n1,1,2,0,1,1\n", encoding="utf-8")
    output, receipt = tmp_path / "out.csv", tmp_path / "receipt.json"
    try:
        materialize(source, output, receipt, "1970-01-01T00:00:00Z", "1970-01-01T00:00:10Z")
    except ValueError as exc:
        assert "sorted" in str(exc)
    else:
        raise AssertionError("unsorted input must fail closed")
