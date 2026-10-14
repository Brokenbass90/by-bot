"""Breaks caught: lost raw provenance, duplicate erasure, false gap/PASS and writers.

Expected sides and timestamps are literal protocol examples, not normalizer output.
"""
import hashlib
import json
from pathlib import Path

import pytest

from bot.bybit_liquidation_collector_v2 import CaptureStopped, Journal


NOW = 1791964800000
PINS = {"normalizer.py": "a" * 64, "collector.py": "b" * 64}


def open_journal(path, **kwargs):
    return Journal(path, ("BTCUSDT", "ETHUSDT"), PINS, now_ms=NOW,
                   min_free_bytes=0, **kwargs)


def payload(side="Buy", timestamp=NOW - 10, symbol="BTCUSDT", **changes):
    item = dict(T=timestamp, s=symbol, S=side, v="2", p="100")
    item.update(changes)
    return json.dumps(dict(topic="allLiquidation." + symbol, type="snapshot",
                           ts=NOW - 5, data=[item]))


def records(path):
    return [json.loads(line) for p in sorted(Path(path).glob("runs/*/frames.jsonl"))
            for line in p.read_text().splitlines()]


def ready(j):
    j.connected("c1", "subscribe-1", NOW)
    j.receive('{"op":"subscribe","req_id":"subscribe-1","success":true}',
              recv_ms=NOW, connection_id="c1")


def test_raw_bytes_and_long_position_side_survive_normalization(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        raw = payload()
        events = j.receive(raw, recv_ms=NOW, connection_id="c1")
        assert events[0]["liquidated_position_side"] == "long"
        assert events[0]["ts_ms"] == NOW - 10
        assert events[0]["t_available_ms"] == NOW
        assert events[0]["price_basis"] == "bankruptcy_price"
        row = records(tmp_path)[-1]
        assert row["raw_text"] == raw
        assert row["raw_payload_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
        assert events[0]["source_manifest_sha256"] == j.manifest["manifest_sha256"]


def test_same_event_is_flagged_and_retained_twice_not_deduplicated(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        first = j.receive(payload(), recv_ms=NOW, connection_id="c1")
        second = j.receive(payload(), recv_ms=NOW + 1, connection_id="c1")
        assert len(first) == len(second) == 1
        assert first[0]["capture_event_id"] != second[0]["capture_event_id"]
        assert "DUPLICATE_CANDIDATE_RETAINED" in second[0]["qa_flags"]
        assert j.health(NOW + 1)["observed_event_count"] == 2
        assert j.health(NOW + 1)["unique_exchange_event_count"] is None


@pytest.mark.parametrize("bad", [NOW // 1000, NOW * 1000, NOW + 120000])
def test_wrong_timestamp_units_or_future_event_never_become_causal_events(tmp_path, bad):
    with open_journal(tmp_path) as j:
        ready(j)
        assert j.receive(payload(timestamp=bad), recv_ms=NOW, connection_id="c1") == []
        assert "EVENT_TIMESTAMP_INVALID" in records(tmp_path)[-1]["qa_flags"]
        assert records(tmp_path)[-1]["raw_text"] == payload(timestamp=bad)


def test_missing_T_is_not_replaced_with_frame_or_receive_time(tmp_path):
    raw = '{"topic":"allLiquidation.BTCUSDT","type":"snapshot","ts":1791964800000,"data":[{"s":"BTCUSDT","S":"Buy","v":"2","p":"100"}]}'
    with open_journal(tmp_path) as j:
        ready(j)
        assert j.receive(raw, recv_ms=NOW, connection_id="c1") == []
        assert "EVENT_SCHEMA_INVALID" in records(tmp_path)[-1]["qa_flags"]


@pytest.mark.parametrize("raw,reason", [
    ("not json", "MALFORMED_JSON"),
    ('{"topic":"allLiquidation.BTCUSDT","type":"snapshot","ts":1791964800000,"data":{}}', "FRAME_SCHEMA_INVALID"),
    ('{"topic":"orderbook.1.BTCUSDT","data":[]}', "UNEXPECTED_TOPIC"),
])
def test_bad_schema_is_retained_and_counted_without_normalized_events(tmp_path, raw, reason):
    with open_journal(tmp_path) as j:
        ready(j)
        assert j.receive(raw, recv_ms=NOW, connection_id="c1") == []
        assert reason in records(tmp_path)[-1]["qa_flags"]
        assert records(tmp_path)[-1]["raw_text"] == raw


def test_symbol_topic_conflict_and_unsubscribed_name_are_not_admitted(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        raw = payload(s="ETHUSDT")
        assert j.receive(raw, recv_ms=NOW, connection_id="c1") == []
        assert "EVENT_SCHEMA_INVALID" in records(tmp_path)[-1]["qa_flags"]
        assert j.receive(payload(symbol="SOLUSDT"), recv_ms=NOW, connection_id="c1") == []
        assert "UNREQUESTED_SYMBOL" in records(tmp_path)[-1]["qa_flags"]


def test_quiet_healthy_connection_does_not_prove_event_coverage(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.receive('{"op":"ping","success":true,"ret_msg":"pong"}',
                  recv_ms=NOW + 20000, connection_id="c1")
        h = j.heartbeat(NOW + 21000)
        assert h["status"] == "CONNECTED_QUIET"
        assert h["last_pong_ms"] == NOW + 20000
        assert h["observed_event_count"] == 0
        assert h["full_exchange_coverage"] == "UNKNOWN_NO_SEQUENCE_OR_BACKFILL"
        assert h["orders_allowed"] is False


def test_wrong_ack_and_failed_ack_never_mark_subscription_ready(tmp_path):
    with open_journal(tmp_path) as j:
        j.connected("c1", "subscribe-1", NOW)
        j.receive('{"op":"subscribe","req_id":"other","success":true}',
                  recv_ms=NOW, connection_id="c1")
        assert j.health(NOW)["subscription_confirmed"] is False
        j.receive('{"op":"subscribe","req_id":"subscribe-1","success":false}',
                  recv_ms=NOW + 1, connection_id="c1")
        assert j.health(NOW + 1)["subscription_confirmed"] is False
        assert "SUBSCRIPTION_REJECTED" in records(tmp_path)[-1]["qa_flags"]


def test_disconnect_and_reconnect_preserve_unobserved_interval(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.disconnected("peer_closed", NOW + 1000)
        assert j.health(NOW + 1000)["status"] == "DISCONNECTED"
        j.connected("c2", "subscribe-2", NOW + 4000)
        gaps = [r for r in records(tmp_path) if r["kind"] == "OBSERVATION_GAP"]
        assert gaps[-1]["start_ms"] == NOW + 1000
        assert gaps[-1]["end_ms"] == NOW + 4000
        assert gaps[-1]["missing_event_count"] is None


def test_real_second_writer_cannot_touch_first_journal(tmp_path):
    with open_journal(tmp_path) as j:
        before = (tmp_path / "source-manifest.json").read_bytes()
        with pytest.raises(CaptureStopped, match="ALREADY_RUNNING"):
            open_journal(tmp_path)
        assert (tmp_path / "source-manifest.json").read_bytes() == before
        assert len(list((tmp_path / "runs").iterdir())) == 1


def test_restart_keeps_epoch_and_records_restart_gap(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.receive(payload(), recv_ms=NOW, connection_id="c1")
        j.heartbeat(NOW + 1000)
        manifest_bytes = (tmp_path / "source-manifest.json").read_bytes()
    with open_journal(tmp_path) as j:
        assert (tmp_path / "source-manifest.json").read_bytes() == manifest_bytes
        assert j.health(NOW + 2000)["observed_event_count"] == 1
        assert j.health(NOW + 2000)["restart_gap_count"] == 1
        assert len(list((tmp_path / "runs").iterdir())) == 2


def test_changed_pins_or_limits_are_blocked_not_silently_new_epoch(tmp_path):
    with open_journal(tmp_path):
        pass
    changed = dict(PINS, **{"collector.py": "c" * 64})
    with pytest.raises(CaptureStopped, match="MANIFEST_DRIFT"):
        Journal(tmp_path, ("BTCUSDT", "ETHUSDT"), changed, now_ms=NOW, min_free_bytes=0)
    with pytest.raises(CaptureStopped, match="MANIFEST_DRIFT"):
        open_journal(tmp_path, max_capture_bytes=123456)


def test_manifest_tampering_fails_closed(tmp_path):
    with open_journal(tmp_path):
        pass
    p = tmp_path / "source-manifest.json"
    d = json.loads(p.read_text());d["created_ms"] += 1;p.write_text(json.dumps(d))
    with pytest.raises(CaptureStopped, match="MANIFEST_HASH_INVALID"):
        open_journal(tmp_path)


def test_symlinked_output_is_rejected_without_writing_target(tmp_path):
    real = tmp_path / "real";real.mkdir()
    link = tmp_path / "link";link.symlink_to(real, target_is_directory=True)
    with pytest.raises(CaptureStopped, match="SYMLINK"):
        open_journal(link)
    assert list(real.iterdir()) == []


def test_storage_bound_stops_capture_and_preserves_existing_bytes(tmp_path):
    with open_journal(tmp_path, max_capture_bytes=6000) as j:
        ready(j)
        before = sum(p.stat().st_size for p in tmp_path.glob("runs/*/frames.jsonl"))
        with pytest.raises(CaptureStopped, match="STORAGE_CAP"):
            j.receive("x" * 6000, recv_ms=NOW, connection_id="c1")
        assert sum(p.stat().st_size for p in tmp_path.glob("runs/*/frames.jsonl")) == before


def test_event_order_regression_is_flagged_but_retained(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.receive(payload(), recv_ms=NOW, connection_id="c1")
        e = j.receive(payload(timestamp=NOW - 20), recv_ms=NOW + 1, connection_id="c1")
        assert len(e) == 1
        assert "EVENT_TIME_REGRESSION_RETAINED" in e[0]["qa_flags"]


def test_frame_chain_binds_raw_and_normalized_events(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.receive(payload(), recv_ms=NOW, connection_id="c1")
    previous = "0" * 64
    for row in records(tmp_path):
        assert row["prev_sha256"] == previous
        claimed = row.pop("record_sha256")
        actual = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        assert claimed == actual
        previous = claimed


def test_duplicate_items_inside_one_frame_are_retained_and_flagged(tmp_path):
    raw = json.loads(payload());raw["data"].append(dict(raw["data"][0]))
    with open_journal(tmp_path) as j:
        ready(j)
        events = j.receive(json.dumps(raw), recv_ms=NOW, connection_id="c1")
        assert len(events) == 2
        assert "DUPLICATE_CANDIDATE_RETAINED" in events[1]["qa_flags"]


def test_subscription_failure_does_not_poison_a_new_connection(tmp_path):
    with open_journal(tmp_path) as j:
        j.connected("c1", "s1", NOW)
        j.receive('{"op":"subscribe","req_id":"s1","success":false}',
                  recv_ms=NOW, connection_id="c1")
        assert j.subscription_rejected is True
        j.disconnected("rejected", NOW + 1)
        j.connected("c2", "s2", NOW + 5000)
        assert j.subscription_rejected is False
        j.receive('{"op":"subscribe","req_id":"s2","success":true}',
                  recv_ms=NOW + 5000, connection_id="c2")
        assert j.subscription_confirmed is True


def test_old_connection_pong_cannot_make_current_connection_fresh(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        j.disconnected("closed", NOW + 1)
        j.connected("c2", "s2", NOW + 5000)
        j.receive('{"op":"ping","success":true,"ret_msg":"pong"}',
                  recv_ms=NOW + 6000, connection_id="c1")
        assert j.last_pong_ms is None
        assert "STALE_CONNECTION_FRAME" in records(tmp_path)[-1]["qa_flags"]


def test_partial_capture_after_crash_is_blocked_without_truncation(tmp_path):
    with open_journal(tmp_path):
        pass
    p = next(tmp_path.glob("runs/*/frames.jsonl"))
    with p.open("ab") as stream:stream.write(b'{"partial":')
    before = p.read_bytes()
    with pytest.raises(CaptureStopped, match="PARTIAL"):
        open_journal(tmp_path)
    assert p.read_bytes() == before


def test_event_after_receive_marks_causal_clock_uncertainty(tmp_path):
    with open_journal(tmp_path) as j:
        ready(j)
        e = j.receive(payload(timestamp=NOW + 10), recv_ms=NOW, connection_id="c1")
        assert "EVENT_AFTER_RECEIVE_CLOCK_SKEW" in e[0]["qa_flags"]
        assert e[0]["causal_clock_status"] == "UNKNOWN"


def test_binary_payload_is_retained_byte_exact(tmp_path):
    import base64
    wire = b'\xff\xfe\x00'
    with open_journal(tmp_path) as j:
        ready(j)
        assert j.receive(wire, recv_ms=NOW, connection_id="c1") == []
        row = records(tmp_path)[-1]
        assert base64.b64decode(row["raw_base64"]) == wire
        assert row["raw_payload_sha256"] == hashlib.sha256(wire).hexdigest()


def test_free_space_guard_fails_before_any_event_is_appended(tmp_path):
    import shutil
    with pytest.raises(CaptureStopped, match="FREE_SPACE"):
        Journal(tmp_path, ("BTCUSDT",), PINS, now_ms=NOW,
                min_free_bytes=shutil.disk_usage(tmp_path).free + 1024**4)


def test_durability_failure_stops_source_instead_of_transport_retry(tmp_path, monkeypatch):
    import os
    with open_journal(tmp_path) as j:
        ready(j)
        def fail(_):raise OSError("disk I/O failure")
        monkeypatch.setattr(os, "fsync", fail)
        with pytest.raises(CaptureStopped, match="DURABILITY"):
            j.receive(payload(), recv_ms=NOW, connection_id="c1")


def test_missing_capture_file_is_blocked_as_integrity_failure(tmp_path):
    with open_journal(tmp_path):pass
    next(tmp_path.glob("runs/*/frames.jsonl")).unlink()
    with pytest.raises(CaptureStopped, match="CAPTURE_MISSING"):
        open_journal(tmp_path)
