from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from bot.att1_fixed51_shadow import (
    ATT1_FIXED51_UNIVERSE,
    ATT1_MONEY_UNIVERSE,
    AUTHORITY,
    ShadowViolation,
    load_config,
    preflight,
    verify_manifest,
)
from scripts.run_att1_fixed51_zero_risk_shadow import (
    H1_MS,
    _LockedJournal,
    replay_att1_latest,
    run_cycle,
    validate_closed_h1_window,
)


ROOT = Path(__file__).resolve().parents[1]


def _aligned_public_payload(
    *,
    count: int = 240,
    observation_offset_ms: int = 120_000,
    closed_shift_hours: int = 0,
    mutate_open: bool = False,
) -> bytes:
    latest_close = (int(time.time() * 1000) // H1_MS) * H1_MS - closed_shift_hours * H1_MS
    latest_start = latest_close - H1_MS
    first = latest_start - (count - 1) * H1_MS
    rows = [
        [str(first + index * H1_MS), "100", "101", "99", "100", "10", "1000"]
        for index in range(count)
    ]
    # The mutable open bar must never enter the closed-data identity.
    rows.append(
        [str(latest_close), "100", "102" if mutate_open else "101", "99", "101" if mutate_open else "100", "11", "1100"]
    )
    return json.dumps(
        {"retCode": 0, "time": latest_close + observation_offset_ms, "result": {"list": list(reversed(rows))}},
        separators=(",", ":"),
    ).encode("utf-8")


def _cycle_config(tmp_path: Path) -> tuple[Path, Path]:
    config_path = tmp_path / "config.json"
    raw = json.loads((ROOT / "configs/att1_fixed51_zero_risk_shadow_v1.json").read_text())
    raw["enabled"] = True
    relative = Path("runtime/pytest_att1_fixed51") / tmp_path.name / "events.jsonl"
    raw["journal_path"] = relative.as_posix()
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    journal = ROOT / relative
    shutil.rmtree(journal.parent, ignore_errors=True)
    return config_path, journal


def _cleanup_journal(journal: Path) -> None:
    shutil.rmtree(journal.parent, ignore_errors=True)


def _public_h1_bytes(observed: int, start: int) -> bytes:
    rows = [[str(start + i * 3_600_000), "100", "101", "99", "100", "10"] for i in range(120)]
    return json.dumps({"retCode": 0, "time": observed, "result": {"list": rows}}).encode("utf-8")


def test_repository_config_pins_exact_fixed51_manifest_and_major8_money_universe() -> None:
    config = load_config(ROOT / "configs/att1_fixed51_zero_risk_shadow_v1.json")
    assert config.enabled is False
    assert config.authority == AUTHORITY
    assert config.evidence_universe == ATT1_FIXED51_UNIVERSE
    assert len(config.evidence_universe) == 51
    assert config.money_universe == ATT1_MONEY_UNIVERSE
    manifest = verify_manifest(ROOT, config)
    assert manifest["manifest_sha256"] == config.expected_manifest_sha256
    assert manifest["evidence_universe_sha256"] == config.evidence_universe_sha256
    assert manifest["prereg_sha256"] == config.expected_preregistration_sha256


def test_preflight_is_no_network_and_reports_evidence_money_separation(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("preflight attempted network")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    report = preflight(ROOT, ROOT / "configs/att1_fixed51_zero_risk_shadow_v1.json")
    assert report["ok"] is True
    assert report["network_calls"] is False
    assert report["money_authority"] is False
    assert report["orders_allowed"] is False
    assert report["private_api_allowed"] is False
    assert report["money_universe"] == list(ATT1_MONEY_UNIVERSE)
    assert report["evidence_universe"] == list(ATT1_FIXED51_UNIVERSE)


def test_all_att1_environment_inputs_are_restored_after_cycle(tmp_path, monkeypatch) -> None:
    config_path, journal = _cycle_config(tmp_path)
    names = {
        "ATT1_ALLOW_LONGS", "ATT1_ALLOW_SHORTS", "ATT1_SIGNAL_TF", "ATT1_SIGNAL_LOOKBACK",
        "ATT1_ATR_PERIOD", "ATT1_RSI_PERIOD", "ATT1_PIVOT_LEFT", "ATT1_PIVOT_RIGHT", "ATT1_MIN_PIVOTS",
        "ATT1_MAX_PIVOTS_USED", "ATT1_MAX_PIVOT_AGE", "ATT1_MIN_SLOPE_PCT", "ATT1_MAX_SLOPE_PCT",
        "ATT1_LONG_MAX_NEG_SLOPE", "ATT1_SHORT_MAX_POS_SLOPE", "ATT1_MIN_R2", "ATT1_TOUCH_ATR",
        "ATT1_REJECT_ATR", "ATT1_MIN_BODY_FRAC", "ATT1_RSI_LONG_MAX", "ATT1_RSI_SHORT_MIN",
        "ATT1_RSI_SHORT_MAX", "ATT1_TREND_GUARD_BARS", "ATT1_GEOMETRY_V2_ENABLE", "ATT1_GEOMETRY_V2_OBSERVE",
        "ATT1_G2_MIN_DESC_SLOPE", "ATT1_G2_MIN_R2", "ATT1_G2_MAX_ENTRY_DIST_ATR", "ATT1_G2_MAX_TOUCH_MISS_ATR",
        "ATT1_G2_MIN_ROOM_R", "ATT1_G2_PROFILE", "ATT1_SL_ATR_MULT", "ATT1_MAX_ENTRY_DIST_ATR",
        "ATT1_MIN_ENTRY_DIST_ATR", "ATT1_MIN_RR", "ATT1_MIN_STOP_PCT", "ATT1_MAX_STOP_PCT", "ATT1_TP1_RR",
        "ATT1_TP2_RR", "ATT1_TP1_FRAC", "ATT1_BE_TRIGGER_RR", "ATT1_BE_LOCK_RR", "ATT1_TRAIL_ATR_MULT",
        "ATT1_TRAIL_ACTIVATE_RR", "ATT1_TIME_STOP_BARS_5M", "ATT1_COOLDOWN_BARS_5M", "ATT1_SYMBOL_ALLOWLIST",
        "ATT1_SYMBOL_DENYLIST", "ATT1_CANARY_EXPIRY_UTC",
    }
    before = {name: f"ambient-{name}" for name in names}
    for name, value in before.items():
        monkeypatch.setenv(name, value)
    run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW",
              fetch=lambda *_args, **_kwargs: _aligned_public_payload())
    assert {name: __import__("os").environ.get(name) for name in names} == before
    _cleanup_journal(journal)


def test_runner_rejects_config_drift_before_public_fetch(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    raw = json.loads((ROOT / "configs/att1_fixed51_zero_risk_shadow_v1.json").read_text())
    raw["enabled"] = True
    raw["evidence_universe"] = list(raw["evidence_universe"][:-1])
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network called after config drift")

    with pytest.raises(ShadowViolation, match="fixed51_universe_mismatch"):
        run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=forbidden)
    assert called is False


def test_runner_module_has_no_private_or_order_surface() -> None:
    tree = ast.parse((ROOT / "scripts/run_att1_fixed51_zero_risk_shadow.py").read_text())
    forbidden = {"pybit", "ccxt", "requests", "private", "order", "broker", "smart_pump_reversal_bot"}
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "").lower())
    assert not any(any(token in name for token in forbidden) for name in imports)


def test_closed_window_rejects_stale_gap_and_bad_ohlc() -> None:
    payload = json.loads(_aligned_public_payload().decode("utf-8"))
    observed = payload["time"]
    rows = list(reversed(payload["result"]["list"]))
    closed = validate_closed_h1_window(rows, observed_at_ms=observed, max_age_ms=300_000, min_bars=121)
    assert len(closed) == 240

    stale_payload = json.loads(_aligned_public_payload(closed_shift_hours=2).decode("utf-8"))
    with pytest.raises(ShadowViolation, match="closed_h1_decision_too_old"):
        validate_closed_h1_window(
            list(reversed(stale_payload["result"]["list"])),
            observed_at_ms=stale_payload["time"] + 2 * H1_MS,
            max_age_ms=300_000,
            min_bars=121,
        )

    gap = [list(row) for row in rows]
    del gap[20]
    with pytest.raises(ShadowViolation, match="noncontiguous_closed_h1_rows"):
        validate_closed_h1_window(gap, observed_at_ms=observed, max_age_ms=300_000, min_bars=121)

    bad = [list(row) for row in rows]
    bad[20][2] = "nan"
    with pytest.raises(ShadowViolation, match="invalid_closed_h1_ohlcv"):
        validate_closed_h1_window(bad, observed_at_ms=observed, max_age_ms=300_000, min_bars=121)


def test_replay_uses_real_wrapper_state_and_can_emit_on_final_bar(monkeypatch) -> None:
    import strategies.alt_trendline_touch_v1 as strategy_module

    payload = json.loads(_aligned_public_payload(count=121).decode("utf-8"))
    rows = validate_closed_h1_window(
        list(reversed(payload["result"]["list"])),
        observed_at_ms=payload["time"],
        max_age_ms=300_000,
        min_bars=121,
    )
    monkeypatch.setattr(strategy_module, "_atr_from_rows", lambda *_args: 1.0)
    monkeypatch.setattr(strategy_module, "_rsi", lambda *_args: 60.0)
    monkeypatch.setattr(
        strategy_module.AltTrendlineTouchV1Strategy,
        "_check_short_trendline",
        lambda *_args: (101.0, -0.1),
    )
    result = replay_att1_latest("BTCUSDT", rows, signal_lookback=120)
    assert result["replay_evaluations"] == 2
    assert result["raw_signal"] is not None
    assert result["raw_signal"]["side"] == "short"
    assert result["no_signal_reason"] == ""


def test_observation_and_open_bar_changes_are_idempotent_but_closed_mutation_conflicts(tmp_path) -> None:
    config_path, journal = _cycle_config(tmp_path)
    cycle = 0

    def fetch(_url, **_kwargs):
        return _aligned_public_payload(
            observation_offset_ms=120_000 + cycle * 30_000,
            mutate_open=bool(cycle),
        )

    first = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=fetch)
    assert first["status"] == "RAW_DECISION_SHADOW_OK"
    before = journal.read_bytes()
    cycle = 1
    duplicate = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=fetch)
    assert duplicate["journal_events"] == 0
    assert journal.read_bytes() == before

    original_fetch = fetch

    def changed_closed(url, **kwargs):
        raw = json.loads(original_fetch(url, **kwargs).decode("utf-8"))
        ordered = list(reversed(raw["result"]["list"]))
        ordered[30][4] = "100.5"
        raw["result"]["list"] = list(reversed(ordered))
        return json.dumps(raw, separators=(",", ":")).encode("utf-8")

    with pytest.raises(ShadowViolation, match="journal_claim_conflict"):
        run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=changed_closed)
    _cleanup_journal(journal)


def test_next_closed_h1_creates_new_raw_event_per_symbol(tmp_path) -> None:
    config_path, journal = _cycle_config(tmp_path)
    shift = 0

    def fetch(_url, **_kwargs):
        # First call sees one H1 close; second cycle advances exactly one H1.
        payload = json.loads(_aligned_public_payload().decode("utf-8"))
        if shift:
            rows = list(reversed(payload["result"]["list"]))
            next_start = int(rows[-1][0]) + H1_MS
            rows.append([str(next_start), "100", "101", "99", "100", "10", "1000"])
            payload["result"]["list"] = list(reversed(rows[-241:]))
            payload["time"] += H1_MS
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    one = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=fetch)
    shift = 1
    two = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=fetch)
    assert one["journal_events"] == 51
    assert two["journal_events"] == 51
    assert len(journal.read_text(encoding="ascii").splitlines()) == 102
    _cleanup_journal(journal)


def test_events_are_raw_only_include_runtime_reason_hashes_and_diagnostic_regime(tmp_path) -> None:
    config_path, journal = _cycle_config(tmp_path)
    result = run_cycle(
        ROOT,
        config_path,
        acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW",
        fetch=lambda _url, **_kwargs: _aligned_public_payload(),
    )
    assert result["status"] == "RAW_DECISION_SHADOW_OK"
    event = json.loads(journal.read_text(encoding="ascii").splitlines()[0])
    body = event["payload"]
    assert body["status"] in {"RAW_DECISION_SHADOW_SIGNAL", "RAW_DECISION_SHADOW_NO_SIGNAL"}
    assert body["evidence_admitted"] is False
    assert body["performance_authority"] is False
    assert body["final_n_eligible"] is False
    assert body["regime_eligible"] is False
    assert body["regime"]["value"] == "flat_up"
    assert body["raw_signal"] is None
    assert body["no_signal_reason"] not in {"", "first_signal_bar", "same_signal_bar"}
    for field in (
        "runtime_contract_sha256",
        "source_closure_sha256",
        "closed_history_sha256",
        "latest_closed_row_sha256",
        "btc_regime_history_sha256",
        "config_sha256",
    ):
        assert len(body[field]) == 64
    _cleanup_journal(journal)


def test_expected_hft_unavailable_is_explicit_but_unknown_gap_fails_partial(tmp_path) -> None:
    config_path, journal = _cycle_config(tmp_path)

    def expected_hft(url, **_kwargs):
        if "HFTUSDT" in url:
            raise OSError("frozen member is unavailable")
        return _aligned_public_payload()

    expected = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=expected_hft)
    assert expected["status"] == "RAW_DECISION_SHADOW_PARTIAL_EXPECTED_HFT"
    assert expected["ok"] is True
    assert expected["expected_unavailable_symbols"] == ["HFTUSDT"]
    _cleanup_journal(journal)

    def unknown_gap(url, **_kwargs):
        if "XRPUSDT" not in url:
            return _aligned_public_payload()
        raw = json.loads(_aligned_public_payload().decode("utf-8"))
        ordered = list(reversed(raw["result"]["list"]))
        del ordered[20]
        raw["result"]["list"] = list(reversed(ordered))
        return json.dumps(raw, separators=(",", ":")).encode("utf-8")

    partial = run_cycle(ROOT, config_path, acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW", fetch=unknown_gap)
    assert partial["status"] == "RAW_DECISION_SHADOW_PARTIAL"
    assert partial["ok"] is False
    assert partial["failed_symbols"] == ["XRPUSDT"]
    _cleanup_journal(journal)


def test_zero_success_is_raw_fail_closed(tmp_path, monkeypatch) -> None:
    config_path, journal = _cycle_config(tmp_path)
    import scripts.run_att1_fixed51_zero_risk_shadow as runner

    monkeypatch.setattr(runner, "replay_att1_latest", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("broken")))
    result = run_cycle(
        ROOT,
        config_path,
        acknowledgement="ATT1_FIXED51_ZERO_RISK_SHADOW",
        fetch=lambda _url, **_kwargs: _aligned_public_payload(),
    )
    assert result["status"] == "RAW_DECISION_SHADOW_FAIL_CLOSED"
    assert result["ok"] is False
    assert result["failure_reason"] == "zero_successful_symbol_evaluations"
    _cleanup_journal(journal)


def test_secure_journal_rejects_symlink_and_busy_lock(tmp_path) -> None:
    target = tmp_path / "target.jsonl"
    target.write_text("", encoding="ascii")
    link = tmp_path / "events.jsonl"
    link.symlink_to(target)
    with pytest.raises(ShadowViolation, match="journal_symlink_rejected"):
        with _LockedJournal(link, root=tmp_path):
            pass

    path = tmp_path / "locked.jsonl"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ShadowViolation, match="journal_lock_busy"):
            with _LockedJournal(path, root=tmp_path):
                pass
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_att1_units_are_default_off_hardened_and_scheduled_after_h1_close() -> None:
    service = (ROOT / "deploy/systemd/att1-fixed51-raw-shadow.service").read_text()
    timer = (ROOT / "deploy/systemd/att1-fixed51-raw-shadow.timer").read_text()
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "PrivateDevices=true" in service
    assert "UMask=0077" in service
    assert "--ack ATT1_FIXED51_ZERO_RISK_SHADOW" in service
    assert "TimeoutStartSec=150" in service
    assert "RuntimeMaxSec=" not in service
    assert "OnCalendar=*-*-* *:02:20 UTC" in timer
    assert "Persistent=false" in timer
    assert "WantedBy=timers.target" in timer
