from __future__ import annotations

import dataclasses
import gzip
import io
import json
import math
import os
import urllib.error
from pathlib import Path

import pytest

from bot.event_universe_v1 import (
    DAY_MS,
    M5_INTERVAL_MS,
    EventUniverseConfigV1,
    EventUniverseError,
    build_snapshot_payload,
    closed_contiguous_m5,
    evaluate_market_eligibility,
    score_event_m5,
    select_prefetch_symbols,
    sha256_payload,
    validate_snapshot_payload,
)
from scripts.run_event_universe_v1 import (
    PublicBybitEventClientV1,
    _bind_normalized_replay,
    _decode_and_validate_replay,
    _launch_receipt,
    _preflight,
    collect_once,
    persist_snapshot,
    read_status,
)


BASE_TS = 1_780_000_000_000 // M5_INTERVAL_MS * M5_INTERVAL_MS


def _config(**changes):
    return dataclasses.replace(EventUniverseConfigV1(), **changes)


def _rows(*, baseline_turnover=100_000.0, recent_turnover=300_000.0, jump_pct=2.0):
    cfg = _config()
    rows = []
    price = 100.0
    for index in range(cfg.baseline_bars):
        close = 100.0 + (0.1 if index % 2 else -0.1)
        rows.append([BASE_TS + index * M5_INTERVAL_MS, price, 101.0, 99.0, close, 999999.0, baseline_turnover])
        price = close
    event_price = rows[-1][4] * (1.0 + jump_pct / 100.0)
    for offset in range(cfg.recent_bars):
        start = BASE_TS + (cfg.baseline_bars + offset) * M5_INTERVAL_MS
        close = event_price * (1.0 + 0.001 * offset)
        rows.append([start, event_price, close + 0.4, event_price - 0.4, close, 1.0, recent_turnover])
        event_price = close
    return rows


def _as_of(rows):
    return int(rows[-1][0]) + M5_INTERVAL_MS


def _instrument(symbol="AKEUSDT", *, launch_ms=BASE_TS - 10 * DAY_MS, **changes):
    payload = {
        "symbol": symbol,
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "launchTime": str(launch_ms),
    }
    payload.update(changes)
    return payload


def _ticker(symbol="AKEUSDT", **changes):
    payload = {
        "symbol": symbol,
        "turnover24h": "2500000",
        "bid1Price": "1.0000",
        "ask1Price": "1.0010",
        "price24hPcnt": "0.12",
    }
    payload.update(changes)
    return payload


def test_forming_tail_mutation_cannot_change_score():
    cfg = _config()
    rows = _rows()
    forming_start = int(rows[-1][0]) + M5_INTERVAL_MS
    as_of = forming_start + 60_000
    first = rows + [[forming_start, 1, 999, 0.1, 700, 1e12, 1e12]]
    second = rows + [[forming_start, 1, 2, 0.5, 1.5, 1, 1]]
    score_a = score_event_m5("AKEUSDT", first, as_of_ms=as_of, listing_tier="normal", config=cfg)
    score_b = score_event_m5("AKEUSDT", second, as_of_ms=as_of, listing_tier="normal", config=cfg)
    assert score_a == score_b


def test_first_recent_bar_jump_is_included_and_zero_mad_is_finite():
    rows = _rows(jump_pct=10.0)
    score = score_event_m5("AKEUSDT", rows, as_of_ms=_as_of(rows), listing_tier="normal", config=_config())
    assert score.recent_return_pct > 9.0
    assert math.isfinite(score.inflow_z)
    assert score.inflow_z < 100.0
    assert score.rank_semantics == "heuristic_rank_not_probability"


def test_true_quote_turnover_is_required_instead_of_close_times_base_volume():
    cfg = _config(min_recent_quote_usd=100_000.0)
    rows = _rows(recent_turnover=1.0)
    for row in rows[-cfg.recent_bars :]:
        row[5] = 1e12
    score = score_event_m5("AKEUSDT", rows, as_of_ms=_as_of(rows), listing_tier="normal", config=cfg)
    assert not score.ok
    assert score.reason == "recent_quote_too_low"
    assert score.recent_quote_usd == 3.0


@pytest.mark.parametrize("mutation", ["duplicate", "gap"])
def test_duplicate_or_gap_in_required_tail_fails_closed(mutation):
    rows = _rows()
    if mutation == "duplicate":
        rows[-1][0] = rows[-2][0]
    else:
        rows[-1][0] += M5_INTERVAL_MS
    with pytest.raises(EventUniverseError):
        closed_contiguous_m5(rows, as_of_ms=_as_of(rows) + M5_INTERVAL_MS, required_bars=75)


def test_market_listing_tiers_and_missing_launch_fail_closed():
    cfg = _config()
    as_of = BASE_TS
    too_young = evaluate_market_eligibility(
        _instrument(launch_ms=as_of - 23 * 3_600_000), _ticker(), as_of_ms=as_of, config=cfg
    )
    fresh = evaluate_market_eligibility(
        _instrument(launch_ms=as_of - 24 * 3_600_000), _ticker(), as_of_ms=as_of, config=cfg
    )
    normal = evaluate_market_eligibility(
        _instrument(launch_ms=as_of - 7 * DAY_MS), _ticker(), as_of_ms=as_of, config=cfg
    )
    missing = evaluate_market_eligibility(
        _instrument(launchTime=""), _ticker(), as_of_ms=as_of, config=cfg
    )
    assert (too_young.eligible, too_young.reason) == (False, "listing_younger_than_frozen_minimum")
    assert fresh.eligible and fresh.listing_tier == "fresh_shadow"
    assert normal.eligible and normal.listing_tier == "normal"
    assert not missing.eligible and missing.reason == "launch_time_missing_or_invalid"


def test_missing_price_change_fails_closed_instead_of_becoming_zero():
    row = evaluate_market_eligibility(
        _instrument(),
        _ticker(price24hPcnt=""),
        as_of_ms=BASE_TS,
        config=_config(),
    )
    assert not row.eligible
    assert row.reason == "ticker_invalid:price24hPcnt is missing"


@pytest.mark.parametrize(
    ("instrument_change", "ticker_change", "reason"),
    [
        ({"status": "PreLaunch"}, {}, "instrument_not_trading"),
        ({"contractType": "LinearFutures"}, {}, "instrument_not_linear_perpetual"),
        ({"settleCoin": "USDC"}, {}, "instrument_not_usdt_quoted_and_settled"),
        ({}, {"bid1Price": "1.1", "ask1Price": "1.0"}, "ticker_book_crossed"),
        ({}, {"bid1Price": "1.0", "ask1Price": "1.1"}, "spread_above_frozen_cap"),
    ],
)
def test_market_contract_and_spread_guards(instrument_change, ticker_change, reason):
    cfg = _config()
    as_of = BASE_TS
    row = evaluate_market_eligibility(
        _instrument(launch_ms=as_of - 10 * DAY_MS, **instrument_change),
        _ticker(**ticker_change),
        as_of_ms=as_of,
        config=cfg,
    )
    assert not row.eligible
    assert row.reason == reason


def test_prefetch_union_preserves_event_and_liquid_controls():
    cfg = _config(max_prefetch_symbols=6, top_k=3)
    rows = []
    for index in range(12):
        row = evaluate_market_eligibility(
            _instrument(f"X{index}USDT", launch_ms=BASE_TS - 10 * DAY_MS),
            _ticker(
                f"X{index}USDT",
                turnover24h=str(1_000_000 + index * 1_000_000),
                price24hPcnt=str((20 - index) / 100),
            ),
            as_of_ms=BASE_TS,
            config=cfg,
        )
        rows.append(row)
    selected = select_prefetch_symbols(rows, config=cfg)
    assert len(selected) == 6
    assert len(set(selected)) == 6
    assert "X11USDT" in selected  # liquid control
    top_event = max(rows, key=lambda row: row.prefetch_proxy).symbol
    assert top_event in selected


def _client(**changes):
    args = dict(
        config=_config(public_requests_per_second=10.0),
        timeout_seconds=1,
        max_retries=2,
        backoff_base_seconds=0.01,
        sleep=lambda _seconds: None,
        monotonic=lambda: 0.0,
        wall_time=lambda: BASE_TS / 1000,
    )
    args.update(changes)
    return PublicBybitEventClientV1(**args)


def test_instrument_pagination_over_500_and_repeated_cursor_guard(monkeypatch):
    client = _client()
    pages = [
        {"retCode": 0, "time": BASE_TS, "result": {"list": [_instrument("AAUSDT")], "nextPageCursor": "next"}},
        {"retCode": 0, "time": BASE_TS + 1, "result": {"list": [_instrument("BBUSDT")], "nextPageCursor": ""}},
    ]
    monkeypatch.setattr(client, "get_json", lambda _path, _params: pages.pop(0))
    items, hashes, server_time = client.fetch_instruments()
    assert [row["symbol"] for row in items] == ["AAUSDT", "BBUSDT"]
    assert len(hashes) == 2 and server_time == BASE_TS + 1

    repeated = [
        {"retCode": 0, "time": BASE_TS, "result": {"list": [_instrument("AAUSDT")], "nextPageCursor": "same"}},
        {"retCode": 0, "time": BASE_TS, "result": {"list": [_instrument("BBUSDT")], "nextPageCursor": "same"}},
    ]
    monkeypatch.setattr(client, "get_json", lambda _path, _params: repeated.pop(0))
    with pytest.raises(EventUniverseError, match="cursor repeated"):
        client.fetch_instruments()


class _Response:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.raw


def test_retcode_10006_retries_then_resumes():
    payloads = [
        {"retCode": 10006, "retMsg": "Too many visits"},
        {"retCode": 0, "retMsg": "OK", "time": BASE_TS, "result": {"list": []}},
    ]
    client = _client(urlopen=lambda *_args, **_kwargs: _Response(payloads.pop(0)))
    result = client.get_json("/v5/market/tickers", {"category": "linear"})
    assert result["retCode"] == 0


def test_retry_count_and_cycle_wall_clock_are_hard_bounded():
    with pytest.raises(EventUniverseError, match="retry count"):
        _client(max_retries=5)

    class Clock:
        value = 0.0

        def monotonic(self):
            return self.value

        def sleep(self, seconds):
            self.value += seconds

    clock = Clock()

    def always_timeout(*_args, **_kwargs):
        clock.value += 0.8
        raise urllib.error.URLError("timeout")

    cfg = _config(poll_interval_seconds=3, max_cycle_seconds=2, public_requests_per_second=10.0)
    client = PublicBybitEventClientV1(
        config=cfg,
        timeout_seconds=1,
        max_retries=4,
        backoff_base_seconds=0.5,
        urlopen=always_timeout,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        wall_time=lambda: BASE_TS / 1000,
    )
    client.start_cycle()
    with pytest.raises(EventUniverseError, match="cycle"):
        client.get_json("/v5/market/tickers", {"category": "linear"})


def test_snapshot_chain_is_atomic_hash_bound_and_tamper_fails(tmp_path):
    cfg = _config(min_free_bytes=1, max_total_bytes=10_000_000)
    market = evaluate_market_eligibility(
        _instrument(launch_ms=BASE_TS - 10 * DAY_MS), _ticker(), as_of_ms=BASE_TS, config=cfg
    )
    rows = _rows()
    score = score_event_m5("AKEUSDT", rows, as_of_ms=_as_of(rows), listing_tier="normal", config=cfg)
    payload = build_snapshot_payload(
        as_of_ms=_as_of(rows),
        config=cfg,
        instruments_page_sha256=["a" * 64],
        tickers_sha256="b" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[score],
        errors_by_symbol={},
        sequence=1,
        previous_snapshot_sha256=None,
    )
    payload["source_receipts"]["kline_sha256_by_symbol"] = {"AKEUSDT": "c" * 64}
    normalized = [row.payload() for row in closed_contiguous_m5(rows, as_of_ms=_as_of(rows), required_bars=75)]
    payload, replay_bytes = _bind_normalized_replay(
        payload,
        {"AKEUSDT": normalized},
        previous_normalized_m5_by_symbol={},
        config=cfg,
    )
    root = tmp_path / "runtime" / "research" / "run"
    # Persistence is intentionally confined below the real repo research root;
    # patch ROOT only for this isolated test.
    import scripts.run_event_universe_v1 as runner

    old_root = runner.ROOT
    runner.ROOT = tmp_path
    try:
        path = persist_snapshot(root, payload, replay_bytes=replay_bytes, config=cfg)
        assert stat_mode(path) == 0o600
        assert read_status(root, config=cfg)["snapshot_count"] == 1
        latest_path = root / "latest_state.json"
        latest_original = latest_path.read_bytes()
        latest = json.loads(latest_original.decode())
        latest["sequence"] = 2
        latest.pop("state_sha256")
        latest["state_sha256"] = sha256_payload(latest)
        latest_path.write_text(json.dumps(latest), encoding="utf-8")
        os.chmod(latest_path, 0o600)
        with pytest.raises(EventUniverseError, match="immutable chain head"):
            read_status(root, config=cfg)
        latest_path.write_bytes(latest_original)
        os.chmod(latest_path, 0o600)
        stored = json.loads(gzip.decompress(path.read_bytes()).decode())
        stored["event_candidate_count"] += 1
        path.write_bytes(gzip.compress(json.dumps(stored).encode(), mtime=0))
        os.chmod(path, 0o600)
        with pytest.raises(EventUniverseError, match="mismatch|checksum"):
            read_status(root, config=cfg)
    finally:
        runner.ROOT = old_root


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777


def test_preflight_is_no_network_no_write_and_code_has_no_live_imports(tmp_path):
    receipt = _preflight(Path(__file__).resolve().parents[1] / "configs/preregistered/event_universe_v1_20260718.json")
    assert receipt["network_calls"] is False
    assert receipt["filesystem_writes"] is False
    assert receipt["executable"] is False
    source = (Path(__file__).resolve().parents[1] / "bot/event_universe_v1.py").read_text(encoding="utf-8")
    forbidden = ("pybit", "place_order", "create_order", "smart_pump_reversal_bot", "os.getenv")
    assert not any(token in source for token in forbidden)


def test_status_is_read_only_and_normalized_path_cannot_escape(tmp_path, monkeypatch):
    import scripts.run_event_universe_v1 as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    root = tmp_path / "runtime/research/never_created"
    status = read_status(root, config=_config())
    assert status["snapshot_count"] == 0
    assert not root.exists()
    escaped = tmp_path / "runtime/research/inside/../../../outside"
    with pytest.raises(EventUniverseError, match="stay below"):
        read_status(escaped, config=_config())


def test_launch_receipt_binds_spec_implementation_and_deadline(tmp_path, monkeypatch):
    import scripts.run_event_universe_v1 as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "_implementation_sha256_by_path", lambda: {"impl.py": "d" * 64})
    root = tmp_path / "runtime/research/run"
    cfg = _config()
    spec = {"schema": "frozen", "public_io": {"kline_limit": 77}}
    receipt = _launch_receipt(root, spec=spec, config=cfg)
    assert receipt["spec_sha256"] == sha256_payload(spec)
    with pytest.raises(EventUniverseError, match="spec/implementation"):
        _launch_receipt(root, spec={**spec, "changed": True}, config=cfg)

    path = root / "launch_receipt.json"
    tampered = json.loads(path.read_text())
    tampered["deadline_at_ms"] += 1
    tampered.pop("launch_sha256")
    tampered["launch_sha256"] = sha256_payload(tampered)
    path.write_text(json.dumps(tampered), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(EventUniverseError, match="deadline"):
        _launch_receipt(root, spec=spec, config=cfg)


def test_top_cards_exclude_failed_high_rank_observations():
    cfg = _config()
    market = evaluate_market_eligibility(_instrument(), _ticker(), as_of_ms=BASE_TS, config=cfg)
    rows = _rows()
    score = score_event_m5("AKEUSDT", rows, as_of_ms=_as_of(rows), listing_tier="normal", config=cfg)
    failed = dataclasses.replace(score, ok=False, reason="forced_test_failure", heuristic_rank=99.0)
    payload = build_snapshot_payload(
        as_of_ms=_as_of(rows),
        config=cfg,
        instruments_page_sha256=["a" * 64],
        tickers_sha256="b" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[failed],
        errors_by_symbol={},
        sequence=1,
        previous_snapshot_sha256=None,
    )
    assert payload["top_observations"] == [failed.payload()]
    assert payload["top_cards"] == []


def test_semantically_inconsistent_rehashed_snapshot_is_rejected():
    cfg = _config()
    market = evaluate_market_eligibility(_instrument(), _ticker(), as_of_ms=BASE_TS, config=cfg)
    payload = build_snapshot_payload(
        as_of_ms=BASE_TS,
        config=cfg,
        instruments_page_sha256=["a" * 64],
        tickers_sha256="b" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[],
        errors_by_symbol={},
        sequence=1,
        previous_snapshot_sha256=None,
    )
    payload["prefetch_count"] = 99
    payload.pop("snapshot_sha256")
    payload["snapshot_sha256"] = sha256_payload(payload)
    with pytest.raises(EventUniverseError, match="prefetch count"):
        validate_snapshot_payload(payload, config=cfg)


def test_delta_replay_reconstructs_exact_next_closed_tail():
    cfg = _config()
    market = evaluate_market_eligibility(_instrument(), _ticker(), as_of_ms=BASE_TS, config=cfg)
    rows1 = _rows()
    normalized1 = [row.payload() for row in closed_contiguous_m5(rows1, as_of_ms=_as_of(rows1), required_bars=75)]
    score1 = score_event_m5("AKEUSDT", normalized1, as_of_ms=_as_of(rows1), listing_tier="normal", config=cfg)
    payload1 = build_snapshot_payload(
        as_of_ms=_as_of(rows1),
        config=cfg,
        instruments_page_sha256=["a" * 64],
        tickers_sha256="b" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[score1],
        errors_by_symbol={},
        sequence=1,
        previous_snapshot_sha256=None,
    )
    payload1["source_receipts"]["kline_sha256_by_symbol"] = {"AKEUSDT": "c" * 64}
    payload1, replay1 = _bind_normalized_replay(
        payload1,
        {"AKEUSDT": normalized1},
        previous_normalized_m5_by_symbol={},
        config=cfg,
    )
    body1, reconstructed1 = _decode_and_validate_replay(
        replay1,
        snapshot=payload1,
        previous_normalized_m5_by_symbol={},
        config=cfg,
    )
    assert body1["replay_by_symbol"]["AKEUSDT"]["mode"] == "checkpoint"

    last = list(normalized1[-1])
    last[0] += M5_INTERVAL_MS
    rows2 = normalized1[1:] + [last]
    as_of2 = int(last[0]) + M5_INTERVAL_MS
    score2 = score_event_m5("AKEUSDT", rows2, as_of_ms=as_of2, listing_tier="normal", config=cfg)
    payload2 = build_snapshot_payload(
        as_of_ms=as_of2,
        config=cfg,
        instruments_page_sha256=["d" * 64],
        tickers_sha256="e" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[score2],
        errors_by_symbol={},
        sequence=2,
        previous_snapshot_sha256=payload1["snapshot_sha256"],
    )
    payload2["source_receipts"]["kline_sha256_by_symbol"] = {"AKEUSDT": "f" * 64}
    payload2, replay2 = _bind_normalized_replay(
        payload2,
        {"AKEUSDT": rows2},
        previous_normalized_m5_by_symbol=reconstructed1,
        config=cfg,
    )
    body2, reconstructed2 = _decode_and_validate_replay(
        replay2,
        snapshot=payload2,
        previous_normalized_m5_by_symbol=reconstructed1,
        config=cfg,
    )
    assert body2["replay_by_symbol"]["AKEUSDT"]["mode"] == "delta"
    assert len(body2["replay_by_symbol"]["AKEUSDT"]["rows"]) == 1
    assert reconstructed2["AKEUSDT"] == rows2
    assert len(replay2) < len(replay1)


def test_collect_once_fake_public_pipeline_persists_replayable_snapshot(tmp_path, monkeypatch):
    import scripts.run_event_universe_v1 as runner

    cfg = _config(min_free_bytes=1, max_total_bytes=64 * 1024 * 1024)
    rows = _rows()
    as_of = _as_of(rows)

    class FakePublicClient:
        cycle_started = False

        def start_cycle(self):
            self.cycle_started = True

        def fetch_instruments(self):
            return [_instrument(launch_ms=as_of - 10 * DAY_MS)], ["a" * 64], as_of

        def fetch_tickers(self):
            return [_ticker()], "b" * 64, as_of

        def fetch_m5(self, symbol, *, as_of_ms, limit):
            assert self.cycle_started and symbol == "AKEUSDT" and as_of_ms == as_of and limit == 77
            return rows, "c" * 64

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    root = tmp_path / "runtime/research/integration"
    path, payload = collect_once(
        root=root,
        spec={"public_io": {"kline_limit": 77}},
        config=cfg,
        client=FakePublicClient(),
    )
    assert path.name.startswith("snapshot_000001_") and path.suffix == ".gz"
    assert payload["replay_bundle"]["scope"] == "score_replay_delta_chain_source_hashes_asserted_not_replayed"
    assert read_status(root, config=cfg)["snapshot_count"] == 1
    with pytest.raises(EventUniverseError, match="cutoff did not advance"):
        collect_once(
            root=root,
            spec={"public_io": {"kline_limit": 77}},
            config=cfg,
            client=FakePublicClient(),
        )


def test_snapshot_checksum_roundtrip():
    cfg = _config()
    market = evaluate_market_eligibility(
        _instrument(launch_ms=BASE_TS - 10 * DAY_MS), _ticker(), as_of_ms=BASE_TS, config=cfg
    )
    rows = _rows()
    score = score_event_m5("AKEUSDT", rows, as_of_ms=_as_of(rows), listing_tier="normal", config=cfg)
    payload = build_snapshot_payload(
        as_of_ms=_as_of(rows),
        config=cfg,
        instruments_page_sha256=["a" * 64],
        tickers_sha256="b" * 64,
        market_rows=[market],
        prefetch_symbols=["AKEUSDT"],
        scores=[score],
        errors_by_symbol={},
        sequence=1,
        previous_snapshot_sha256=None,
    )
    validate_snapshot_payload(payload, config=cfg)
