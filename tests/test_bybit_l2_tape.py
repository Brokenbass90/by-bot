from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
import time
from pathlib import Path

import pytest

from bot.bybit_l2_tape import (
    BOOK_SCHEMA,
    TRADE_SCHEMA,
    BookReplayValidator,
    BookSequenceTracker,
    FrameContractError,
    StorageLimitExceeded,
    TapeStorageError,
    TapeStore,
    TradeReplayValidator,
    atomic_write_json,
    compress_jsonl_partition,
    enforce_storage_budget,
    expired_partition_files,
    iter_jsonl,
    marker_record,
    normalize_book_frame,
    normalize_trade_frame,
    prune_expired_partitions,
    select_partition_file,
    utc_day,
    validate_public_ws_url,
    validate_tape_file,
)


def _book_wire(
    *,
    kind: str = "snapshot",
    update_id: int = 10,
    seq: int = 100,
    bids=None,
    asks=None,
    symbol: str = "BTCUSDT",
):
    return {
        "topic": f"orderbook.200.{symbol}",
        "type": kind,
        "ts": 1_720_000_000_010,
        "data": {
            "s": symbol,
            "b": bids if bids is not None else [["100.0", "2.5"], ["99.5", "1"]],
            "a": asks if asks is not None else [["100.5", "3"], ["101.0", "4"]],
            "u": update_id,
            "seq": seq,
            "cts": 1_720_000_000_009,
        },
    }


def _book_record(wire, *, recv_ms=1_720_000_000_020, connection="c1", frame=1):
    return normalize_book_frame(
        wire,
        recv_ts_ms=recv_ms,
        recv_ts_ns=recv_ms * 1_000_000,
        connection_id=connection,
        frame_seq=frame,
        depth=200,
    )


def _marker(stream: str, kind: str, *, recv_ms: int, reason: str = "test"):
    return marker_record(
        stream=stream,
        symbol="BTCUSDT",
        kind=kind,
        reason=reason,
        recv_ts_ms=recv_ms,
        recv_ts_ns=recv_ms * 1_000_000,
        connection_id="c1",
        frame_seq=0,
    )


def test_book_normalization_preserves_decimal_text_and_exchange_sequence():
    row = _book_record(_book_wire())
    assert row["schema"] == BOOK_SCHEMA
    assert row["update_id"] == 10
    assert row["seq"] == 100
    assert row["exch_ts_ms"] == 1_720_000_000_009
    assert row["system_ts_ms"] == 1_720_000_000_010
    assert row["payload"]["b"][0] == ["100.0", "2.5"]


def test_book_normalization_rejects_wrong_topic_and_bad_levels():
    wrong = _book_wire()
    wrong["topic"] = "orderbook.50.BTCUSDT"
    with pytest.raises(FrameContractError):
        _book_record(wrong)
    bad = _book_wire(bids=[["100", "NaN"]])
    with pytest.raises(FrameContractError):
        _book_record(bad)


def test_sequence_tracker_marks_regression_gap_and_blocks_until_new_snapshot():
    tracker = BookSequenceTracker("BTCUSDT", 200)
    start = tracker.on_connection_start(
        connection_id="c1", recv_ts_ms=1_720_000_000_000,
        recv_ts_ns=1_720_000_000_000_000_000, frame_seq=0,
    )
    assert start["kind"] == "stream_start"

    snapshot, reconnect = tracker.process(_book_record(_book_wire(), frame=1))
    assert reconnect is False and snapshot[0]["replayable"] is True
    delta, reconnect = tracker.process(
        _book_record(
            _book_wire(kind="delta", update_id=11, seq=250, bids=[["100.0", "3"]], asks=[]),
            recv_ms=1_720_000_000_120,
            frame=2,
        )
    )
    assert reconnect is False and delta[0]["segment_id"] == snapshot[0]["segment_id"]

    rows, reconnect = tracker.process(
        _book_record(
            _book_wire(kind="delta", update_id=10, seq=300, bids=[], asks=[]),
            recv_ms=1_720_000_000_220,
            frame=3,
        )
    )
    assert reconnect is True
    assert rows[0]["kind"] == "gap" and rows[0]["reason"] == "non_monotonic_update_id"
    assert rows[1]["kind"] == "delta" and rows[1]["replayable"] is False
    assert tracker.valid is False


def test_update_id_and_cross_sequence_must_increase_but_need_not_be_contiguous():
    tracker = BookSequenceTracker("BTCUSDT", 200)
    tracker.on_connection_start(connection_id="c1", recv_ts_ms=1, recv_ts_ns=1, frame_seq=0)
    tracker.process(_book_record(_book_wire(update_id=10, seq=100)))
    rows, reconnect = tracker.process(
        _book_record(_book_wire(kind="delta", update_id=42, seq=10_000, bids=[], asks=[]), frame=2)
    )
    assert reconnect is False and rows[0]["replayable"] is True


def test_trade_normalization_preserves_every_trade_and_message_order():
    wire = {
        "topic": "publicTrade.BTCUSDT",
        "type": "snapshot",
        "ts": 1_720_000_000_100,
        "data": [
            {"T": 1_720_000_000_090, "s": "BTCUSDT", "S": "Sell", "v": "0.25", "p": "100.10", "i": "t1", "seq": 400, "L": "MinusTick"},
            {"T": 1_720_000_000_091, "s": "BTCUSDT", "S": "Buy", "v": "0.50", "p": "100.20", "i": "t2", "seq": 400, "BT": True},
        ],
    }
    rows = normalize_trade_frame(
        wire,
        recv_ts_ms=1_720_000_000_110,
        recv_ts_ns=1_720_000_000_110_000_000,
        connection_id="c1",
        frame_seq=8,
    )
    assert [row["trade_id"] for row in rows] == ["t1", "t2"]
    assert [row["message_index"] for row in rows] == [0, 1]
    assert rows[0]["schema"] == TRADE_SCHEMA
    assert rows[0]["exch_ts_ms"] == 1_720_000_000_090
    assert rows[1]["block_trade"] is True


def test_trade_normalization_rejects_unsorted_exchange_time():
    wire = {
        "topic": "publicTrade.BTCUSDT",
        "ts": 200,
        "data": [
            {"T": 190, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "1", "i": "a", "seq": 1},
            {"T": 189, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "1", "i": "b", "seq": 1},
        ],
    }
    with pytest.raises(FrameContractError):
        normalize_trade_frame(wire, recv_ts_ms=201, recv_ts_ns=201_000_000, connection_id="c", frame_seq=1)


def test_deterministic_book_replay_reconstructs_same_digest():
    tracker = BookSequenceTracker("BTCUSDT", 200)
    records = [
        tracker.on_connection_start(
            connection_id="c1", recv_ts_ms=1_720_000_000_000,
            recv_ts_ns=1_720_000_000_000_000_000, frame_seq=0,
        )
    ]
    for wire, recv, frame in (
        (_book_wire(update_id=10, seq=100), 1_720_000_000_020, 1),
        (_book_wire(kind="delta", update_id=11, seq=150, bids=[["100.0", "0"], ["99.8", "5"]], asks=[]), 1_720_000_000_120, 2),
    ):
        rows, reconnect = tracker.process(_book_record(wire, recv_ms=recv, frame=frame))
        assert reconnect is False
        records.extend(rows)
    results = []
    for _ in range(2):
        validator = BookReplayValidator(expected_symbol="BTCUSDT", expected_depth=200)
        for row in records:
            validator.consume(row)
        results.append(validator.result())
    assert results[0]["valid"] is True
    assert results[0]["final_book_sha256"] == results[1]["final_book_sha256"]
    assert results[0]["raw_records_sha256"] == results[1]["raw_records_sha256"]
    assert results[0]["final_book_levels"] == {"bids": 2, "asks": 2}


def test_replay_accepts_increasing_update_id_jump():
    snapshot = _book_record(_book_wire(update_id=10, seq=100))
    snapshot.update({"replayable": True, "segment_id": "c1:1"})
    delta = _book_record(
        _book_wire(kind="delta", update_id=99, seq=200, bids=[], asks=[]),
        recv_ms=1_720_000_000_120,
        frame=2,
    )
    delta.update({"replayable": True, "segment_id": "c1:1"})
    validator = BookReplayValidator(expected_symbol="BTCUSDT", expected_depth=200)
    validator.consume(snapshot)
    validator.consume(delta)
    result = validator.result()
    assert result["valid"] is True


def test_replay_rejects_update_id_regression_without_reset_snapshot():
    snapshot = _book_record(_book_wire(update_id=10, seq=100))
    snapshot.update({"replayable": True, "segment_id": "c1:1"})
    delta = _book_record(
        _book_wire(kind="delta", update_id=9, seq=200, bids=[], asks=[]),
        recv_ms=1_720_000_000_120,
        frame=2,
    )
    delta.update({"replayable": True, "segment_id": "c1:1"})
    validator = BookReplayValidator(expected_symbol="BTCUSDT", expected_depth=200)
    validator.consume(snapshot)
    validator.consume(delta)
    result = validator.result()
    assert result["valid"] is False
    assert "update_id did not increase" in result["errors"][0]


def test_explicit_gap_allows_fresh_snapshot_and_keeps_file_valid():
    first = _book_record(_book_wire(update_id=10, seq=100))
    first.update({"replayable": True, "segment_id": "c1:1"})
    gap = _marker("book", "gap", recv_ms=1_720_000_000_100, reason="disconnect")
    fresh = _book_record(
        _book_wire(update_id=500, seq=50_000, bids=[["90", "1"]], asks=[["91", "2"]]),
        recv_ms=1_720_000_000_200,
        connection="c2",
        frame=1,
    )
    fresh.update({"replayable": True, "segment_id": "c2:2"})
    validator = BookReplayValidator(expected_symbol="BTCUSDT", expected_depth=200)
    for row in (first, gap, fresh):
        validator.consume(row)
    result = validator.result()
    assert result["valid"] is True
    assert result["gaps"] == 1


def test_trade_validator_deduplicates_for_unique_digest_but_reports_duplicate():
    start = _marker("trades", "stream_start", recv_ms=1_720_000_000_000)
    wire = {
        "topic": "publicTrade.BTCUSDT",
        "ts": 1_720_000_000_100,
        "data": [{"T": 1_720_000_000_090, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "100", "i": "same", "seq": 10}],
    }
    row = normalize_trade_frame(
        wire, recv_ts_ms=1_720_000_000_110, recv_ts_ns=1_720_000_000_110_000_000,
        connection_id="c1", frame_seq=1,
    )[0]
    duplicate = dict(row)
    duplicate["local_recv_ts_ms"] += 1
    duplicate["local_recv_ts_ns"] += 1_000_000
    duplicate["connection_frame_seq"] = 2
    validator = TradeReplayValidator(expected_symbol="BTCUSDT")
    for record in (start, row, duplicate):
        validator.consume(record)
    result = validator.result()
    assert result["valid"] is True
    assert result["duplicate_trade_count"] == 1


def test_trade_validator_detects_truncated_multi_trade_message():
    wire = {
        "topic": "publicTrade.BTCUSDT",
        "ts": 1_720_000_000_100,
        "data": [
            {"T": 1_720_000_000_090, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "100", "i": "a", "seq": 10},
            {"T": 1_720_000_000_091, "s": "BTCUSDT", "S": "Sell", "v": "1", "p": "99", "i": "b", "seq": 10},
        ],
    }
    first_only = normalize_trade_frame(
        wire, recv_ts_ms=1_720_000_000_110, recv_ts_ns=1_720_000_000_110_000_000,
        connection_id="c1", frame_seq=1,
    )[0]
    validator = TradeReplayValidator(expected_symbol="BTCUSDT")
    validator.consume(first_only)
    result = validator.result()
    assert result["valid"] is False
    assert "incomplete publicTrade message" in result["errors"][0]


def test_store_partitions_by_utc_and_recovers_partial_tail(tmp_path: Path):
    root = tmp_path / "tape"
    symbol_dir = root / "BTCUSDT"
    symbol_dir.mkdir(parents=True)
    recv_ms = 1_720_000_000_000
    day = utc_day(recv_ms)
    path = symbol_dir / f"{day}.book.jsonl"
    valid = _marker("book", "stream_start", recv_ms=recv_ms)
    path.write_bytes(json.dumps(valid, separators=(",", ":"), sort_keys=True).encode() + b"\n{partial")

    with TapeStore(root, fsync_every_records=1) as store:
        snapshot = _book_record(_book_wire(), recv_ms=recv_ms + 10)
        snapshot.update({"replayable": True, "segment_id": "c1:1"})
        store.append("book", snapshot)
        stats = store.stats_manifest(now_ms=recv_ms + 20)
    rows = list(iter_jsonl(path))
    assert [row["kind"] for row in rows] == ["stream_start", "gap", "snapshot"]
    assert rows[1]["reason"] == "recovered_partial_jsonl_tail"
    assert next(iter(stats.values()))["recovered_partial_tail_bytes"] == len(b"{partial")


def test_utc_rotation_finalizes_previous_partition_coverage(tmp_path: Path):
    root = tmp_path / "tape"
    noon = int(dt.datetime(2026, 7, 13, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)
    midnight = int(dt.datetime(2026, 7, 14, tzinfo=dt.timezone.utc).timestamp() * 1000)
    with TapeStore(root, fsync_every_records=1) as store:
        store.append("trades", _marker("trades", "stream_start", recv_ms=noon))
        store.append("trades", _marker("trades", "stream_resume", recv_ms=midnight))
        manifest = store.stats_manifest(now_ms=midnight + 1_000)
    old = next(row for row in manifest.values() if row["day"] == "20260713")
    assert old["covered_ms_at_manifest"] == 12 * 60 * 60 * 1000
    assert old["observed_window_ms"] == 12 * 60 * 60 * 1000
    assert old["coverage"] == 1.0


def test_store_single_writer_lock_blocks_second_process_handle(tmp_path: Path):
    first = TapeStore(tmp_path / "tape")
    second = TapeStore(tmp_path / "tape")
    first.acquire()
    try:
        with pytest.raises(BlockingIOError):
            second.acquire()
    finally:
        first.close()


def test_atomic_manifest_rejects_symlink(tmp_path: Path):
    target = tmp_path / "target.json"
    target.write_text("{}")
    link = tmp_path / "manifest.json"
    link.symlink_to(target)
    with pytest.raises(TapeStorageError):
        atomic_write_json(link, {"ok": True})


def test_storage_cap_fails_closed_and_retention_only_selects_known_old_partitions(tmp_path: Path):
    root = tmp_path / "tape"
    old = root / "BTCUSDT" / "20260101.book.jsonl"
    old.parent.mkdir(parents=True)
    old.write_text("0123456789")
    unrelated = old.parent / "notes.txt"
    unrelated.write_text("keep")
    with pytest.raises(StorageLimitExceeded):
        enforce_storage_budget(root, max_disk_bytes=5, min_free_bytes=0)
    now_ms = 1_752_537_600_000  # 2025-07-15 UTC; old name is still parseable/older
    # Use a later date so the 2026 partition is expired.
    now_ms = 1_783_958_400_000  # 2026-07-15 UTC
    selected = expired_partition_files(root, now_ms=now_ms, retention_days=30)
    assert selected == [old]
    deleted = prune_expired_partitions(root, now_ms=now_ms, retention_days=30)
    assert deleted == [str(old)]
    assert unrelated.exists()


def test_validate_file_and_partition_selector_are_read_only(tmp_path: Path):
    root = tmp_path / "tape"
    recv = 1_720_000_000_000
    day = utc_day(recv)
    path = root / "BTCUSDT" / f"{day}.book.jsonl"
    path.parent.mkdir(parents=True)
    snapshot = _book_record(_book_wire(), recv_ms=recv)
    snapshot.update({"replayable": True, "segment_id": "c1:1"})
    path.write_text(json.dumps(snapshot, separators=(",", ":"), sort_keys=True) + "\n")
    before = path.read_bytes()
    assert select_partition_file(root, symbol="BTCUSDT", day=day, stream="book") == path
    result = validate_tape_file(path, symbol="BTCUSDT", depth=200)
    assert result["valid"] is True
    assert result["recv_utc_days"] == [day]
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "url",
    [
        "ws://stream.bybit.com/v5/public/linear",
        "wss://stream.bybit.com/v5/private",
        "wss://stream.bybit.com/v5/trade",
        "wss://example.com/v5/public/linear",
    ],
)
def test_public_url_guard_rejects_non_public_surfaces(url: str):
    with pytest.raises(ValueError):
        validate_public_ws_url(url)


def test_public_url_guard_accepts_only_public_linear():
    assert validate_public_ws_url("wss://stream.bybit.com/v5/public/linear")


def test_collector_preflight_is_networkless_and_does_not_create_root(tmp_path: Path):
    from scripts.collect_bybit_l2_tape import build_parser, config_from_args, preflight

    root = tmp_path / "does-not-exist" / "tape"
    args = build_parser().parse_args(
        ["--preflight", "--root", str(root), "--min-free-gb", "0", "--max-disk-gb", "1"]
    )
    receipt = preflight(config_from_args(args))
    assert receipt["ok"] is True
    assert receipt["checks"]["network_calls"] is False
    assert receipt["checks"]["files_written"] is False
    assert receipt["config"]["authentication"] is False
    assert not root.exists()


def test_stream_selection_caps_l2_but_allows_wider_public_trade_only(tmp_path: Path):
    from scripts.collect_bybit_l2_tape import build_parser, config_from_args

    parser = build_parser()
    common = [
        "--root", str(tmp_path / "tape"), "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT",
        "--min-free-gb", "0", "--max-disk-gb", "1",
    ]
    with pytest.raises(ValueError, match="max-book-symbols"):
        config_from_args(parser.parse_args(common))
    trade_config = config_from_args(parser.parse_args(common + ["--streams", "trades"]))
    assert trade_config.streams == ("trades",)
    assert len(trade_config.symbols) == 3


def test_default_disk_guards_match_small_vps_contract():
    from scripts.collect_bybit_l2_tape import build_parser, config_from_args

    config = config_from_args(build_parser().parse_args([]))
    assert config.max_disk_bytes == 4 * 1024**3
    assert config.min_free_bytes == 4 * 1024**3
    assert config.retention_mode == "stop"
    assert config.streams == ("book", "trades")


def test_mocked_frames_flow_through_runtime_store_and_validate(tmp_path: Path):
    from scripts.collect_bybit_l2_tape import CollectorRuntime, build_parser, config_from_args

    root = tmp_path / "tape"
    args = build_parser().parse_args(
        ["--root", str(root), "--symbols", "BTCUSDT", "--min-free-gb", "0", "--max-disk-gb", "1"]
    )
    runtime = CollectorRuntime(config_from_args(args))
    runtime.store.acquire()
    runtime.existing_tape = {("BTCUSDT", "book"): False, ("BTCUSDT", "trades"): False}
    runtime.trackers = {"BTCUSDT": BookSequenceTracker("BTCUSDT", 200)}
    runtime.connection_id = "mock-c1"
    runtime._start_markers(reconnect=False)
    try:
        runtime.connection_frame_seq = 1
        runtime.handle_message(_book_wire(), recv_ts_ns=time.time_ns())
        runtime.connection_frame_seq = 2
        runtime.handle_message(
            {
                "topic": "publicTrade.BTCUSDT",
                "type": "snapshot",
                "ts": 1_720_000_000_100,
                "data": [
                    {"T": 1_720_000_000_090, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "100", "i": "mock-t1", "seq": 10}
                ],
            },
            recv_ts_ns=time.time_ns(),
        )
        runtime._stop_markers("unit_test")
        runtime.store.flush()
    finally:
        runtime.store.close()
    day = utc_day(int(time.time() * 1000))
    book = validate_tape_file(root / "BTCUSDT" / f"{day}.book.jsonl", symbol="BTCUSDT", depth=200)
    trades = validate_tape_file(root / "BTCUSDT" / f"{day}.trades.jsonl", symbol="BTCUSDT")
    assert book["valid"] is True and book["snapshots"] == 1
    assert trades["valid"] is True and trades["trades"] == 1


def test_public_trade_only_runtime_needs_no_book_tracker(tmp_path: Path):
    from scripts.collect_bybit_l2_tape import CollectorRuntime, build_parser, config_from_args

    root = tmp_path / "trade-tape"
    config = config_from_args(
        build_parser().parse_args(
            [
                "--root", str(root), "--symbols", "BTCUSDT,SOLUSDT", "--streams", "trades",
                "--min-free-gb", "0", "--max-disk-gb", "1",
            ]
        )
    )
    runtime = CollectorRuntime(config)
    runtime.store.acquire()
    runtime.existing_tape = {
        ("BTCUSDT", "trades"): False,
        ("SOLUSDT", "trades"): False,
    }
    runtime.trackers = {}
    runtime.connection_id = "mock-trades"
    runtime._start_markers(reconnect=False)
    try:
        runtime.connection_frame_seq = 1
        runtime.handle_message(
            {
                "topic": "publicTrade.BTCUSDT",
                "ts": 1_720_000_000_100,
                "data": [
                    {"T": 1_720_000_000_090, "s": "BTCUSDT", "S": "Buy", "v": "1", "p": "100", "i": "only-t1", "seq": 10}
                ],
            },
            recv_ts_ns=time.time_ns(),
        )
        runtime._stop_markers("unit_test")
        runtime.store.flush()
    finally:
        runtime.store.close()
    day = utc_day(int(time.time() * 1000))
    assert not (root / "BTCUSDT" / f"{day}.book.jsonl").exists()
    result = validate_tape_file(root / "BTCUSDT" / f"{day}.trades.jsonl", symbol="BTCUSDT")
    assert result["valid"] is True and result["trades"] == 1


def test_startup_storage_block_releases_single_writer_lock(tmp_path: Path):
    from scripts.collect_bybit_l2_tape import CollectorRuntime, build_parser, config_from_args

    root = tmp_path / "blocked-tape"
    config = config_from_args(
        build_parser().parse_args(
            ["--root", str(root), "--symbols", "BTCUSDT", "--min-free-gb", "0", "--max-disk-gb", "1"]
        )
    )
    config = dataclasses.replace(config, max_disk_bytes=0)
    with pytest.raises(StorageLimitExceeded):
        asyncio.run(CollectorRuntime(config).run())
    probe = TapeStore(root)
    probe.acquire()
    probe.close()


def test_zstd_compression_is_verified_and_replayable(tmp_path: Path):
    pytest.importorskip("zstandard")
    path = tmp_path / "20260714.book.jsonl"
    snapshot = _book_record(_book_wire())
    snapshot.update({"replayable": True, "segment_id": "c1:1"})
    path.write_text(json.dumps(snapshot, separators=(",", ":"), sort_keys=True) + "\n")
    compressed = compress_jsonl_partition(path)
    assert compressed.name.endswith(".jsonl.zst")
    assert compressed.exists() and not path.exists()
    result = validate_tape_file(compressed, symbol="BTCUSDT", depth=200)
    assert result["valid"] is True
    assert result["snapshots"] == 1
