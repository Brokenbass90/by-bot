from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.live_native_regime_gate import H1_MS
from bot.persisted_btc_h1_regime import BTCRegimeContractError
from bot.btc_h1_regime_updater import (
    BTCRegimeUpdaterError,
    fetch_public_btc_h1,
    update_btc_h1_regime,
    verify_btc_h1_regime_restart,
)
from scripts.update_btc_h1_regime import main as update_cli


START = 1_700_000_000_000 // H1_MS * H1_MS


def rows(count: int) -> list[list[str]]:
    return [
        [str(START + index * H1_MS), "100", "101", "99", "100", "1"]
        for index in range(count)
    ]


def response(raw_rows: list[list[str]], observed_at_ms: int) -> bytes:
    # Bybit returns newest-first; the updater must canonicalize this before
    # handing rows to the causal state machine.
    return json.dumps(
        {
            "retCode": 0,
            "time": observed_at_ms,
            "result": {"list": list(reversed(raw_rows))},
        },
        separators=(",", ":"),
    ).encode()


def test_updater_is_disabled_without_explicit_enable_and_does_not_fetch_or_write(
    tmp_path: Path,
) -> None:
    called = False

    def forbidden(*_args, **_kwargs) -> bytes:
        nonlocal called
        called = True
        raise AssertionError("network must not be reached while disabled")

    with pytest.raises(BTCRegimeUpdaterError, match="regime_updater_disabled"):
        update_btc_h1_regime(
            tmp_path / "state.json",
            enabled=False,
            fetch=forbidden,
            observed_at_ms=START + 500 * H1_MS + 1,
        )
    assert called is False
    assert not (tmp_path / "state.json").exists()


def test_enabled_updater_bootstraps_public_closed_history_and_restart_proof(
    tmp_path: Path,
) -> None:
    raw_rows = rows(501)
    observed = int(raw_rows[-2][0]) + H1_MS + 1
    body = response(raw_rows, observed)
    calls: list[tuple[str, float]] = []

    def fetch(url: str, *, timeout: float) -> bytes:
        calls.append((url, timeout))
        return body

    path = tmp_path / "state.json"
    result = update_btc_h1_regime(
        path,
        enabled=True,
        fetch=fetch,
        observed_at_ms=observed,
        max_age_ms=300_000,
    )

    assert result.action == "bootstrapped"
    assert result.applied_bars == 500
    assert result.receipt.state.observation_count == 500
    assert result.receipt.money_authority is False
    assert result.receipt.promotion_authority is False
    assert len(calls) == 1
    assert (
        calls[0][0]
        == "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=60&limit=1000"
    )

    proof = verify_btc_h1_regime_restart(
        path,
        observed_at_ms=observed,
        max_age_ms=300_000,
    )
    assert proof.receipt_sha256 == result.receipt.receipt_sha256
    assert proof.last_closed_h1_ts_ms == observed - 1
    assert proof.regime_value == "flat_up"
    assert proof.research_only is True
    assert proof.money_authority is False


def test_enabled_updater_advances_one_new_bar_and_duplicate_is_unchanged(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    initial_rows = rows(501)
    initial_observed = int(initial_rows[-2][0]) + H1_MS + 1
    update_btc_h1_regime(
        path,
        enabled=True,
        fetch=lambda *_args, **_kwargs: response(initial_rows, initial_observed),
        observed_at_ms=initial_observed,
        max_age_ms=300_000,
    )

    advanced_rows = rows(502)
    advanced_observed = int(advanced_rows[-1][0]) + H1_MS + 1
    advanced = update_btc_h1_regime(
        path,
        enabled=True,
        fetch=lambda *_args, **_kwargs: response(advanced_rows, advanced_observed),
        observed_at_ms=advanced_observed,
        max_age_ms=300_000,
    )
    repeated = update_btc_h1_regime(
        path,
        enabled=True,
        fetch=lambda *_args, **_kwargs: response(advanced_rows, advanced_observed + 1),
        observed_at_ms=advanced_observed + 1,
        max_age_ms=300_000,
    )

    assert advanced.action == "advanced"
    assert advanced.applied_bars == 2
    assert advanced.receipt.state.observation_count == 502
    assert repeated.action == "unchanged"
    assert repeated.applied_bars == 0
    assert repeated.receipt.to_dict() == advanced.receipt.to_dict()


def test_updater_rejects_stale_latest_bar_before_partial_backfill(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    seed_rows = rows(501)
    seed_observed = int(seed_rows[-2][0]) + H1_MS + 1
    update_btc_h1_regime(
        path,
        enabled=True,
        fetch=lambda *_args, **_kwargs: response(seed_rows, seed_observed),
        observed_at_ms=seed_observed,
        max_age_ms=300_000,
    )
    before = path.read_bytes()
    stale_rows = rows(502)
    stale_observed = int(stale_rows[-1][0]) + H1_MS + 300_001
    with pytest.raises(BTCRegimeUpdaterError, match="public_h1_decision_too_old"):
        update_btc_h1_regime(
            path,
            enabled=True,
            fetch=lambda *_args, **_kwargs: response(stale_rows, stale_observed),
            observed_at_ms=stale_observed,
            max_age_ms=300_000,
        )
    assert path.read_bytes() == before


def test_updater_rejects_mutated_duplicate_current_bar(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    seed_rows = rows(501)
    seed_observed = int(seed_rows[-2][0]) + H1_MS + 1
    update_btc_h1_regime(
        path,
        enabled=True,
        fetch=lambda *_args, **_kwargs: response(seed_rows, seed_observed),
        observed_at_ms=seed_observed,
        max_age_ms=300_000,
    )
    conflicting = rows(501)
    conflicting[-2][4] = "101"
    with pytest.raises(BTCRegimeContractError, match="conflicting_regime_duplicate"):
        update_btc_h1_regime(
            path,
            enabled=True,
            fetch=lambda *_args, **_kwargs: response(conflicting, seed_observed),
            observed_at_ms=seed_observed,
            max_age_ms=300_000,
        )


def test_updater_rejects_nonpublic_endpoint_and_malformed_public_payload() -> None:
    with pytest.raises(BTCRegimeUpdaterError, match="nonpublic_bybit_request_rejected"):
        fetch_public_btc_h1(
            "https://evil.example",
            fetch=lambda *_args, **_kwargs: b"{}",
        )

    with pytest.raises(BTCRegimeUpdaterError, match="public_kline_missing_result"):
        fetch_public_btc_h1(
            "https://api.bybit.com",
            fetch=lambda *_args, **_kwargs: b'{"retCode":10001}',
        )


def test_restart_proof_fails_closed_when_receipt_is_missing_or_stale(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(BTCRegimeContractError, match="state_file_unreadable"):
        verify_btc_h1_regime_restart(
            path,
            observed_at_ms=START + H1_MS,
            max_age_ms=300_000,
        )

    seeded = tmp_path / "seeded.json"
    raw_rows = rows(501)
    observed = int(raw_rows[-2][0]) + H1_MS + 1
    body = response(raw_rows, observed)
    update_btc_h1_regime(
        seeded,
        enabled=True,
        fetch=lambda *_args, **_kwargs: body,
        observed_at_ms=observed,
        max_age_ms=300_000,
    )
    with pytest.raises(BTCRegimeContractError, match="evidence_too_old"):
        verify_btc_h1_regime_restart(
            seeded,
            observed_at_ms=observed + 300_001,
            max_age_ms=300_000,
        )


def test_cli_defaults_to_fail_closed_without_mutation(tmp_path: Path, capsys) -> None:
    path = tmp_path / "state.json"
    assert update_cli(["--state-path", str(path)]) == 2
    assert not path.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL_CLOSED"


def test_systemd_release_is_hourly_public_zero_risk_and_hardened() -> None:
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/systemd/btc-h1-regime-updater.service").read_text()
    timer = (root / "deploy/systemd/btc-h1-regime-updater.timer").read_text()

    assert "scripts/update_btc_h1_regime.py --enable" in service
    assert "--max-age-ms 300000" in service
    assert "WorkingDirectory=/opt/bybot-research/live-caller-parity" in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=true" in service
    assert "NoNewPrivileges=true" in service
    assert "ReadWritePaths=/opt/bybot-research/live-caller-parity/runtime" in service
    assert "OnCalendar=*-*-* *:03:00 UTC" in timer
    assert "Persistent=true" in timer


def test_systemd_release_manifest_contains_complete_python_import_closure() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "deploy/systemd/btc-h1-regime-updater.files"
    paths = tuple(
        line.strip()
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    assert paths == (
        "bot/__init__.py",
        "bot/btc_h1_regime_updater.py",
        "bot/persisted_btc_h1_regime.py",
        "bot/live_native_regime_gate.py",
        "bot/live_native_decision_contract.py",
        "scripts/update_btc_h1_regime.py",
        "deploy/systemd/btc-h1-regime-updater.service",
        "deploy/systemd/btc-h1-regime-updater.timer",
    )
    assert all((root / rel).is_file() for rel in paths)

    updater = (root / "bot/btc_h1_regime_updater.py").read_text(encoding="utf-8")
    persisted = (root / "bot/persisted_btc_h1_regime.py").read_text(encoding="utf-8")
    regime = (root / "bot/live_native_regime_gate.py").read_text(encoding="utf-8")
    cli = (root / "scripts/update_btc_h1_regime.py").read_text(encoding="utf-8")
    assert "from bot.persisted_btc_h1_regime import" in updater
    assert "from bot.live_native_regime_gate import H1_MS" in updater
    assert "from bot.live_native_regime_gate import" in persisted
    assert "from bot.live_native_decision_contract import" in regime
    assert "from bot.btc_h1_regime_updater import" in cli
    assert "from bot.persisted_btc_h1_regime import" in cli
