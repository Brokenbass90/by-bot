from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

import scripts.run_horizontal_breakout_long_72h_sealed_v1 as runner


ROOT = Path(__file__).resolve().parents[1]


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_default_preflight_fails_before_any_market_row_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):  # pragma: no cover - failure sentinel
        raise AssertionError("sealed price loader must not run")

    monkeypatch.setattr(runner, "_load_price_slice", forbidden)
    receipt, funding = runner.build_preflight(
        ROOT, runner.DEFAULT_CONFIG, runner.DEFAULT_AUTHORIZATION
    )

    assert receipt["permission"] == "BLOCKED_FAIL_CLOSED"
    assert receipt["market_snapshots_opened"] == 0
    assert receipt["sealed_holdout_rows_decoded"] == 0
    assert receipt["performance_computed"] is False
    assert set(receipt["blockers"]) >= {
        "funding_cohort_13_of_13_not_proven",
        "funding_coverage_through_2026_07_04_not_proven",
        "funding_manifest_not_hash_pinned_complete",
    }
    assert funding is None


def test_blocked_performance_never_reaches_one_shot_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "build_preflight",
        lambda *args, **kwargs: (
            {"permission": "BLOCKED_FAIL_CLOSED", "blockers": ["funding_missing"]},
            None,
        ),
    )

    def forbidden(*args, **kwargs):  # pragma: no cover - failure sentinel
        raise AssertionError("blocked evidence must not claim the holdout")

    monkeypatch.setattr(runner, "claim_one_shot", forbidden)

    with pytest.raises(runner.SealedScoringBlocked, match="funding_missing"):
        runner.run_performance(ROOT, runner.DEFAULT_CONFIG, runner.DEFAULT_AUTHORIZATION)


def _complete_funding_manifest(root: Path) -> dict[str, object]:
    first = runner.HOLDOUT_START_MS - runner.MAX_FUNDING_GAP_MS
    last = runner.HOLDOUT_END_MS + runner.MAX_FUNDING_GAP_MS
    histories: dict[str, object] = {}
    for symbol in runner.EXPECTED_SYMBOLS:
        events = []
        ts = first
        while ts <= last:
            events.append({"funding_ts": ts, "funding_rate": 0.0001})
            ts += runner.MAX_FUNDING_GAP_MS
        descending = list(reversed(events))
        api_pages = []
        requested_end = runner.HOLDOUT_END_MS + runner.MAX_FUNDING_GAP_MS
        for page_index, offset in enumerate(range(0, len(descending), 200)):
            selected = descending[offset : offset + 200]
            raw = {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "category": "linear",
                    "list": [
                        {
                            "symbol": symbol,
                            "fundingRate": str(row["funding_rate"]),
                            "fundingRateTimestamp": str(row["funding_ts"]),
                        }
                        for row in selected
                    ],
                },
                "retExtInfo": {},
                "time": runner.HOLDOUT_END_MS,
            }
            raw_path = root / "pages" / symbol / f"page_{page_index}.json"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(raw), encoding="utf-8")
            newest = max(int(row["funding_ts"]) for row in selected)
            oldest = min(int(row["funding_ts"]) for row in selected)
            api_pages.append(
                {
                    "page_index": page_index,
                    "request_end_time": requested_end,
                    "raw_path": raw_path.relative_to(root).as_posix(),
                    "raw_sha256": runner.sha256_file(raw_path),
                    "response_rows": len(selected),
                    "newest_returned_ts": newest,
                    "oldest_returned_ts": oldest,
                }
            )
            requested_end = oldest - 1
        histories[symbol] = {
            "query_complete": True,
            "oldest_returned_ts": events[0]["funding_ts"],
            "newest_returned_ts": events[-1]["funding_ts"],
            "api_pages": api_pages,
            "events": events,
        }
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": runner.EXPECTED_FUNDING_KIND,
        "research_only": True,
        "provider": "Bybit_V5_public_funding_history",
        "category": "linear",
        "credentials_or_private_endpoints_used": False,
        "pagination_complete": True,
        "symbols": runner.EXPECTED_SYMBOLS,
        "window": {
            "coverage_start_ts": runner.HOLDOUT_START_MS,
            "coverage_end_ts_exclusive": runner.HOLDOUT_END_MS,
            "event_inclusion": "entry_ts_lte_funding_ts_lt_exit_ts",
            "actual_symbol_specific_timestamps": True,
            "fixed_8h_schedule_assumed": False,
            "maximum_gap_validation_ms": runner.MAX_FUNDING_GAP_MS,
        },
        "histories": histories,
    }
    payload["manifest_fingerprint_sha256"] = _canonical(payload)
    return payload


def test_complete_hash_pinned_funding_manifest_is_accepted(tmp_path: Path) -> None:
    manifest = _complete_funding_manifest(tmp_path)
    path = tmp_path / "funding.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    gate = {
        "manifest_path": "funding.json",
        "manifest_sha256": runner.sha256_file(path),
    }

    histories, receipt = runner.validate_funding_manifest(tmp_path, gate)

    assert set(histories) == set(runner.EXPECTED_SYMBOLS)
    assert receipt["symbols_complete"] == 13
    assert all(row["max_gap_ms"] == runner.MAX_FUNDING_GAP_MS for row in receipt["quality"])


def test_funding_gap_or_missing_symbol_fails_closed(tmp_path: Path) -> None:
    manifest = _complete_funding_manifest(tmp_path)
    del manifest["histories"]["XRPUSDT"]  # type: ignore[index]
    manifest.pop("manifest_fingerprint_sha256")
    manifest["manifest_fingerprint_sha256"] = _canonical(manifest)
    path = tmp_path / "funding.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    gate = {
        "manifest_path": "funding.json",
        "manifest_sha256": runner.sha256_file(path),
    }

    with pytest.raises(runner.SealedScoringError, match="13/13"):
        runner.validate_funding_manifest(tmp_path, gate)


def _h1_bars_for_one_breakout() -> list[tuple[int, float, float, float, float, float]]:
    start = runner.HOLDOUT_START_MS - runner.WARMUP_H1 * runner.H1_MS
    bars = []
    for index in range(100):
        ts = start + index * runner.H1_MS
        if index < runner.WARMUP_H1:
            bars.append((ts, 99.0, 100.0, 98.5, 99.0, 1.0))
        elif index == runner.WARMUP_H1:
            bars.append((ts, 100.0, 101.5, 99.5, 101.0, 1.0))
        else:
            bars.append((ts, 101.0, 101.5, 100.5, 101.5, 1.0))
    return bars


def test_exact_next_open_72h_exit_and_adverse_funding_costs() -> None:
    config = json.loads(runner.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    bars = _h1_bars_for_one_breakout()
    entry_ts = runner.HOLDOUT_START_MS + runner.H1_MS
    funding = [(entry_ts + 8 * runner.H1_MS, 0.0001)]

    trades, counters = runner.score_symbol("BTCUSDT", bars, funding, config)

    assert counters["detected_signals"] == 1
    assert counters["scored_trades"] == 1
    assert len(trades) == 1
    trade = trades[0]
    assert trade["side"] == "long"
    assert trade["entry_ts"] == entry_ts
    assert trade["exit_ts"] == entry_ts + 72 * runner.H1_MS
    assert trade["funding_events"] == 1
    assert trade["base_funding_debit_bps"] == pytest.approx(1.0)
    assert trade["stress_funding_debit_bps"] == pytest.approx(5.0)
    expected_base = (
        (101.5 * (1 - 0.0002)) / (101.0 * (1 + 0.0002)) - 1
    ) * 10_000 - 12 - 1
    assert trade["base_net_bps"] == pytest.approx(expected_base)


@pytest.mark.parametrize(
    ("hours_after_fold_boundary", "expected_scored"),
    [(72, 0), (73, 1)],
)
def test_internal_fold_embargo_excludes_first_72_completed_h1_closes(
    hours_after_fold_boundary: int,
    expected_scored: int,
) -> None:
    config = json.loads(runner.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    start = runner.HOLDOUT_START_MS - runner.WARMUP_H1 * runner.H1_MS
    bars = [
        (start + index * runner.H1_MS, 100.0, 101.0, 99.0, 100.0, 1.0)
        for index in range(1_000)
    ]
    fold_2_start = int(
        __import__("datetime").datetime.fromisoformat(
            config["temporal_partition"]["folds"][1]["start_utc"].replace("Z", "+00:00")
        ).timestamp()
        * 1000
    )
    signal_close = fold_2_start + hours_after_fold_boundary * runner.H1_MS
    signal_index = (signal_close - runner.H1_MS - start) // runner.H1_MS
    bars[signal_index] = (
        int(bars[signal_index][0]),
        101.0,
        102.5,
        100.0,
        102.0,
        1.0,
    )

    trades, counters = runner.score_symbol("BTCUSDT", bars, [], config)

    assert counters["detected_signals"] == 1
    assert counters.get("scored_trades", 0) == expected_scored
    assert len(trades) == expected_scored
    assert counters.get("excluded_internal_embargo", 0) == (0 if expected_scored else 1)


def test_one_shot_claim_is_atomic_and_refuses_second_attempt(tmp_path: Path) -> None:
    preflight = {
        "authorization": {"sha256": "a" * 64, "fingerprint": "b" * 64}
    }
    first = runner.claim_one_shot(tmp_path, preflight)

    assert first.exists()
    with pytest.raises(runner.SealedScoringError, match="refusing to overwrite"):
        runner.claim_one_shot(tmp_path, preflight)


def test_concurrent_one_shot_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    preflight = {
        "authorization": {"sha256": "a" * 64, "fingerprint": "b" * 64}
    }
    barrier = threading.Barrier(2)
    winners: list[Path] = []
    errors: list[Exception] = []

    def claim() -> None:
        barrier.wait()
        try:
            winners.append(runner.claim_one_shot(tmp_path, preflight))
        except Exception as exc:  # asserted below
            errors.append(exc)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert len(winners) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], runner.SealedScoringError)
    assert "refusing to overwrite" in str(errors[0])


def test_empty_evidence_cannot_pass_promotion_gates() -> None:
    config = json.loads(runner.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    evaluation = runner.evaluate_gates(
        [], [], config, {}, {symbol: [] for symbol in runner.EXPECTED_SYMBOLS}
    )

    assert evaluation["research_gate_pass"] is False
    assert evaluation["aggregate"]["closed_trades"] == 0
    assert any(
        row["gate"] == "stress_closed_trades_min" and row["pass"] is False
        for row in evaluation["checks"]
    )


def test_mtm_drawdown_includes_funding_settled_exactly_at_mark() -> None:
    entry = runner.HOLDOUT_START_MS
    mark = entry + runner.H1_MS
    exit_ts = entry + 2 * runner.H1_MS
    trade = {
        "symbol": "BTCUSDT",
        "entry_ts": entry,
        "exit_ts": exit_ts,
        "entry_open": 100.0,
        "stress_entry_fill": 100.0,
        "stress_net_pnl_usd": 0.0,
    }
    bars = {"BTCUSDT": [(entry, 100.0, 100.0, 100.0, 100.0, 1.0)]}
    funding = {"BTCUSDT": [(mark, 0.0001)]}

    drawdown = runner._max_drawdown_pct(
        [trade],
        bars,
        funding,
        scenario="stress",
        starting_equity=10_000.0,
        notional=1_000.0,
        fee_bps_per_side=10.0,
        slippage_bps_per_side=5.0,
    )

    # Immediate liquidation includes 5 bps exit slippage + 20 bps fees;
    # the next mark also includes the 5 bps stress funding floor.
    assert drawdown == pytest.approx(0.03)


def test_runner_contains_no_network_broker_or_live_stack_imports() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import requests",
        "import ccxt",
        "from pybit",
        "place_order",
        "smart_pump_reversal_bot",
        "load_dotenv",
        "os.environ",
    ):
        assert forbidden not in source
