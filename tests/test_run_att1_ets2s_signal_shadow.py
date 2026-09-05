from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest

from bot.att1_ets2s_signal_shadow_contract import (
    ACK,
    DEPLOYMENT_ANCHOR_SCHEMA_ID,
    SOURCE_PATHS,
    TRUSTED_CONFIG_PATH,
    TRUSTED_MANIFEST_PATH,
    load_contract,
    load_contract_from_deployment_anchor,
)
from scripts.prepare_att1_ets2s_shadow_release import write_deployment_anchor
from scripts import run_att1_ets2s_signal_shadow as runner


ROOT = Path(__file__).resolve().parents[1]
H1 = 3_600_000


def _bars(count: int) -> list[list[object]]:
    rows = []
    for hour in range(count):
        price = 100.0 + hour * 0.01
        rows.append([hour * H1, str(price), str(price + 1), str(price - 1), str(price + 0.2), "10"])
    return rows


def _isolated_enabled_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    for relative in sorted(set(SOURCE_PATHS) | {TRUSTED_MANIFEST_PATH}):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    config_path = repo / TRUSTED_CONFIG_PATH
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["enabled"] = True
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = repo / TRUSTED_MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = []
    for relative in sorted(SOURCE_PATHS):
        data = (repo / relative).read_bytes()
        source_rows.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest["source_files"] = source_rows
    manifest["source_closure_sha256"] = hashlib.sha256(
        json.dumps(
            {"files": source_rows, "schema_id": "att1_ets2s_source_closure_v1"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return repo, {
        "expected_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "expected_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }


class FakePublicMarket:
    def __init__(self, rows: list[list[object]], *, fail_symbol: str | None = None):
        self.rows = rows
        self.fail_symbol = fail_symbol
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        self.calls.append((endpoint, dict(params)))
        symbol = str(params["symbol"])
        if symbol == "HFTUSDT":
            raise runner.PublicSymbolUnavailable("structurally unavailable")
        if symbol == self.fail_symbol:
            raise runner.PublicFetchViolation("synthetic failure")
        end = int(params.get("end", 2**63 - 1))
        eligible = [row for row in self.rows if int(row[0]) <= end]
        page = list(reversed(eligible[-int(params["limit"]):]))
        return {"retCode": 0, "retMsg": "OK", "result": {"category": "linear", "symbol": symbol, "list": page}}


def test_public_request_is_exact_and_pagination_moves_backward() -> None:
    market = FakePublicMarket(_bars(2161))
    rows = runner.fetch_closed_history(
        market,
        "ETHUSDT",
        observed_at_ms=2161 * H1,
        min_bars=2160,
        page_limit=1000,
        max_response_bytes=5_000_000,
    )

    assert len(rows) >= 2160
    assert [call[1].get("end") for call in market.calls] == [None, 1161 * H1 - 1, 161 * H1 - 1]
    assert all(call[0] == "https://api.bybit.com/v5/market/kline" for call in market.calls)
    assert all(set(call[1]) in ({"category", "interval", "limit", "symbol"}, {"category", "end", "interval", "limit", "symbol"}) for call in market.calls)


@pytest.mark.parametrize(
    "params",
    [
        {"category": "linear", "interval": "60", "limit": 1001, "symbol": "ETHUSDT"},
        {"category": "inverse", "interval": "60", "limit": 1000, "symbol": "ETHUSDT"},
        {"category": "linear", "interval": "15", "limit": 1000, "symbol": "ETHUSDT"},
        {"category": "linear", "interval": "60", "limit": 1000, "symbol": "../ETH"},
        {"category": "linear", "interval": "60", "limit": 1000, "symbol": "ETHUSDT", "api_key": "x"},
    ],
)
def test_public_request_rejects_unsafe_or_unexpected_params(params: dict[str, object]) -> None:
    with pytest.raises(runner.PublicFetchViolation):
        runner.validate_public_request("https://api.bybit.com/v5/market/kline", params)


@pytest.mark.parametrize(
    "payload",
    [
        {"retCode": 1, "result": {"list": []}},
        {"retCode": 0, "result": {}},
        {"retCode": 0, "result": {"list": "bad"}},
        {"retCode": 0, "result": {"list": [[0, "bad"]]}},
    ],
)
def test_public_payload_rejects_error_or_malformed_response(payload: object) -> None:
    with pytest.raises(runner.PublicFetchViolation):
        runner.parse_public_payload(payload, symbol="ETHUSDT", limit=1000, max_response_bytes=1000)


def test_public_payload_rejects_oversized_response() -> None:
    payload = {"retCode": 0, "result": {"list": [_bars(1)[0]]}}
    with pytest.raises(runner.PublicFetchViolation, match="oversized"):
        runner.parse_public_payload(payload, symbol="ETHUSDT", limit=1000, max_response_bytes=1)


def test_causal_feed_uses_closed_canonical_h1_h4_d1() -> None:
    feed = runner.CausalCanonicalFeed("ETHUSDT", _bars(48))
    feed.set_cursor(28)

    assert feed("ETHUSDT", "60", 1)[-1][0] == 28 * H1
    assert feed("ETHUSDT", "240", 20)[-1][0] == 24 * H1
    assert [row[0] for row in feed("ETHUSDT", "1440", 20)] == [0]
    assert feed.requested_timeframes == {60, 240, 1440}


def test_actual_profiles_emit_explicit_att1_and_ets2s_decisions() -> None:
    decisions = runner.evaluate_symbol_decisions(
        symbol="ETHUSDT",
        rows=_bars(2160),
        observed_at_ms=2160 * H1,
        stream="ALPHA_FORWARD_BACKFILL",
        cycle_id="cycle:test",
        cache_hash="a" * 64,
    )

    assert {row["sleeve_id"] for row in decisions} == {"ATT1", "ETS2S"}
    assert all(row["exception"] is None for row in decisions)
    assert all(row["signal"] is not None or row["no_signal_reason"] for row in decisions)
    assert {60, 1440}.issubset(
        set(next(row for row in decisions if row["sleeve_id"] == "ETS2S")["requested_timeframes"])
    )


def _synthetic_decisions(**kwargs: object) -> list[dict[str, object]]:
    common = {
        "schema_id": "att1_ets2s_signal_shadow_decision_v1",
        "symbol": kwargs["symbol"],
        "bar_start_ms": int(kwargs["rows"][-1][0]),
        "bar_close_ms": int(kwargs["rows"][-1][0]) + H1,
        "observed_at_ms": kwargs["observed_at_ms"],
        "decision_age_ms": int(kwargs["observed_at_ms"]) - (int(kwargs["rows"][-1][0]) + H1),
        "stream": kwargs["stream"],
        "cycle_id": kwargs["cycle_id"],
        "signal": None,
        "no_signal_reason": "synthetic_no_signal",
        "exception": None,
        "orders_allowed": False,
        "private_api_allowed": False,
        "money_authority": False,
        "broker_calls": 0,
        "order_calls": 0,
        "cache_rows": len(kwargs["rows"]),
        "cache_hash": kwargs["cache_hash"],
        "store_contract_id": "canonical_closed_utc_buckets_v1",
        "requested_timeframes": [60],
    }
    return [
        {**common, "sleeve_id": sleeve, "claim_key": f"decision:{kwargs['stream']}:{sleeve}:{kwargs['symbol']}:{int(kwargs['rows'][-1][0]) + H1}"}
        for sleeve in ("ATT1", "ETS2S")
    ]


def test_cycle_bootstrap_is_backfill_retry_is_idempotent_and_next_bar_is_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, anchors = _isolated_enabled_repo(tmp_path)
    market = FakePublicMarket(_bars(2161))
    monkeypatch.setattr(runner, "evaluate_symbol_decisions", _synthetic_decisions)

    first = runner.run_cycle(
        repo,
        repo / TRUSTED_CONFIG_PATH,
        ACK,
        fetch=market,
        observed_at_ms=2161 * H1,
        **anchors,
    )
    assert first["healthy"] is True
    assert first["rows_written"] == 100
    assert first["stream_counts"] == {"ALPHA_FORWARD_BACKFILL": 100, "EXECUTION_FORWARD": 0}
    assert first["expected_unavailable"] == ["HFTUSDT"]

    retry = runner.run_cycle(
        repo,
        repo / TRUSTED_CONFIG_PATH,
        ACK,
        fetch=market,
        observed_at_ms=2161 * H1,
        **anchors,
    )
    assert retry["healthy"] is True
    assert retry["rows_written"] == 0

    market.rows.append(_bars(2162)[-1])
    forward = runner.run_cycle(
        repo,
        repo / TRUSTED_CONFIG_PATH,
        ACK,
        fetch=market,
        observed_at_ms=2162 * H1,
        **anchors,
    )
    assert forward["healthy"] is True
    assert forward["rows_written"] == 100
    assert forward["stream_counts"]["EXECUTION_FORWARD"] == 100


def test_unknown_fetch_failure_is_unhealthy_and_heartbeat_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, anchors = _isolated_enabled_repo(tmp_path)
    market = FakePublicMarket(_bars(2161), fail_symbol="ETHUSDT")
    monkeypatch.setattr(runner, "evaluate_symbol_decisions", _synthetic_decisions)
    receipt = runner.run_cycle(
        repo,
        repo / TRUSTED_CONFIG_PATH,
        ACK,
        fetch=market,
        observed_at_ms=2161 * H1,
        **anchors,
    )
    heartbeat = repo / "runtime/att1_ets2s_signal_shadow/heartbeat.json"
    assert receipt["healthy"] is False
    assert any(row["symbol"] == "ETHUSDT" for row in receipt["errors"])
    assert json.loads(heartbeat.read_text(encoding="utf-8"))["healthy"] is False
    assert heartbeat.stat().st_mode & 0o777 == 0o600


def test_cycle_fails_before_fetch_when_runtime_disk_guard_is_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, anchors = _isolated_enabled_repo(tmp_path)
    fetch_called = False

    def unexpected_fetch(*_args: object, **_kwargs: object) -> object:
        nonlocal fetch_called
        fetch_called = True
        raise AssertionError("fetch must not run below disk floor")

    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _path: SimpleNamespace(free=0))
    with pytest.raises(runner.RunnerViolation, match="runtime free-space guard"):
        runner.run_cycle(
            repo,
            repo / TRUSTED_CONFIG_PATH,
            ACK,
            fetch=unexpected_fetch,
            observed_at_ms=2161 * H1,
            **anchors,
        )
    assert fetch_called is False


def test_runner_imports_no_broker_order_or_private_client_modules() -> None:
    tree = ast.parse((ROOT / "scripts/run_att1_ets2s_signal_shadow.py").read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint({"ccxt", "pybit", "alpaca", "broker", "orders", "private_client"})


def test_deployed_cli_preflight_consumes_anchor_and_is_network_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, anchors = _isolated_enabled_repo(tmp_path)
    config = repo / TRUSTED_CONFIG_PATH
    contract = load_contract(repo, config, **anchors)
    anchor_path = tmp_path / "anchor.json"
    anchor = {
        "schema_id": DEPLOYMENT_ANCHOR_SCHEMA_ID,
        "git_commit_sha": "1" * 40,
        "config_path": TRUSTED_CONFIG_PATH,
        "config_sha256": anchors["expected_config_sha256"],
        "manifest_path": TRUSTED_MANIFEST_PATH,
        "manifest_sha256": anchors["expected_manifest_sha256"],
        "source_closure_sha256": contract.source_closure_sha256,
        "privileged_launcher_sha256": hashlib.sha256(
            (repo / "scripts/launch_att1_ets2s_shadow.py").read_bytes()
        ).hexdigest(),
        "acknowledgement": ACK,
        "enabled": True,
        "money_authority": False,
        "orders_allowed": False,
        "private_api_allowed": False,
    }
    write_deployment_anchor(anchor_path, anchor, expected_owner_uid=os.geteuid())
    real_loader = load_contract_from_deployment_anchor
    monkeypatch.setattr(
        runner,
        "load_contract_from_deployment_anchor",
        lambda root, config_path, deployment_anchor_path: real_loader(
            root,
            config_path,
            deployment_anchor_path,
            expected_owner_uid=os.geteuid(),
        ),
    )
    monkeypatch.setattr(
        runner,
        "_network_fetch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )
    code = runner.main(
        [
            "--root",
            str(repo),
            "--deployment-anchor",
            str(anchor_path),
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "OPT_IN_CONFIG_PRESENT"
