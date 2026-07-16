from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "configs/preregistered/public_cashcarry_station_v1_20260716.json"
RUNNER = ROOT / "scripts/run_public_cashcarry_station_v1.py"
FIXTURE = ROOT / "tests/fixtures/bybit_cashcarry_shadow_v2_replay.json"

from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError
from bot.bybit_cashcarry_shadow_v2 import (
    DurableCollectorConfigV2,
    InstrumentRulesV2,
    PublicMarketSnapshotV2,
    snapshots_from_json,
)
from bot.public_cashcarry_station_v1 import (
    BYBIT_ADAPTER_ID,
    BYBIT_EXCHANGE_ID,
    BYBIT_SOURCE_ID,
    AtomicStationStateStore,
    FunctionPublicAdapter,
    PublicCashCarryStationV1,
    StationStateV1,
    load_station_config,
    read_station_status,
)


def _loaded():
    return load_station_config(SPEC, root=ROOT)


def _snapshot_for(snapshot: PublicMarketSnapshotV2, symbol: str) -> PublicMarketSnapshotV2:
    rules = InstrumentRulesV2(
        symbol=symbol,
        funding_interval_minutes=snapshot.instruments.funding_interval_minutes,
        spot=snapshot.instruments.spot,
        linear_perp=snapshot.instruments.linear_perp,
    )
    return dataclasses.replace(snapshot, symbol=symbol, instruments=rules)


class FakeClock:
    def __init__(self, now_ms: int) -> None:
        self.value = now_ms

    def now_ms(self) -> int:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += int(seconds * 1000)


class SequenceFetcher:
    def __init__(self, snapshots: list[PublicMarketSnapshotV2]) -> None:
        self.snapshots = snapshots
        self.calls: dict[str, int] = {}

    def __call__(self, symbol: str, **kwargs) -> PublicMarketSnapshotV2:
        assert kwargs["base"] == "https://api.bybit.com"
        assert kwargs["timeout"] > 0
        assert 2 <= kwargs["book_limit"] <= 200
        index = self.calls.get(symbol, 0)
        self.calls[symbol] = index + 1
        return _snapshot_for(self.snapshots[min(index, len(self.snapshots) - 1)], symbol)


def _station(tmp_path: Path, *, clock: FakeClock, config=None, fetcher=None):
    _, frozen_config, shadow, collector = _loaded()
    config = config or frozen_config
    active = dataclasses.replace(collector, enabled=True, shadow_enabled=True)
    snapshots = snapshots_from_json(json.loads(FIXTURE.read_text(encoding="utf-8")))
    fetcher = fetcher or SequenceFetcher(snapshots)
    adapter = FunctionPublicAdapter(
        adapter_id=BYBIT_ADAPTER_ID,
        exchange_id=BYBIT_EXCHANGE_ID,
        source_id=BYBIT_SOURCE_ID,
        base_url="https://api.bybit.com",
        fetcher=fetcher,
    )
    return PublicCashCarryStationV1(
        config=config,
        shadow_config=shadow,
        collector_config=active,
        adapter=adapter,
        root=tmp_path,
        now_ms=clock.now_ms,
        sleep=clock.sleep,
    ), fetcher, shadow, collector


def test_frozen_spec_and_default_preflight_are_disabled_bounded_and_no_write(tmp_path: Path) -> None:
    payload, config, shadow, collector = _loaded()
    assert payload["default_enabled"] is False
    assert payload["live_permission"] == "FORBIDDEN"
    assert config.symbols == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "SUIUSDT",
    )
    assert config.max_runtime_seconds == 7 * 24 * 60 * 60
    assert config.max_total_bytes == 512 * 1024 * 1024
    assert config.min_free_bytes == 80 * 1024**3
    assert shadow.enabled is False
    assert collector.enabled is False and collector.shadow_enabled is False

    missing = tmp_path / "must-not-exist"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "preflight"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout)
    assert receipt["network_calls"] is False
    assert receipt["filesystem_writes"] is False
    assert receipt["api_keys_or_environment_reads"] is False
    assert receipt["executable"] is False
    assert not missing.exists()


def test_run_requires_all_four_explicit_opt_ins_before_creating_root(tmp_path: Path) -> None:
    run_root = tmp_path / "absent"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "run", "--run-root", str(run_root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "explicit opt-ins" in completed.stderr
    assert not run_root.exists()


def test_one_cycle_is_per_symbol_durable_and_resume_reconciles_without_overwrite(tmp_path: Path) -> None:
    snapshots = snapshots_from_json(json.loads(FIXTURE.read_text(encoding="utf-8")))
    clock = FakeClock(snapshots[0].observed_at_ms)
    station, fetcher, shadow, collector = _station(tmp_path, clock=clock)
    first = station.run(max_cycles_this_process=1)
    assert first.resumed is False
    assert first.state["status"] == "PAUSED"
    assert first.state["durable_observation_count"] == 6
    assert first.state["broker_calls"] is False
    assert first.state["executable"] is False
    assert (tmp_path / "launch_receipt.json").stat().st_mode & 0o777 == 0o600
    for symbol in station.config.symbols:
        assert (tmp_path / "journals" / f"{symbol.lower()}.jsonl").exists()

    launch_before = (tmp_path / "launch_receipt.json").read_bytes()
    resumed_station, _, _, _ = _station(tmp_path, clock=clock, fetcher=fetcher)
    second = resumed_station.run(resume_existing=True, max_cycles_this_process=1)
    assert second.resumed is True
    assert second.state["durable_observation_count"] == 12
    assert second.state["cycle_count"] == 2
    assert (tmp_path / "launch_receipt.json").read_bytes() == launch_before

    status = read_station_status(
        root=tmp_path,
        config=station.config,
        shadow_config=shadow,
        collector_config=collector,
    )
    assert status["network_calls"] is False
    assert sum(row["record_count"] for row in status["journals"].values()) == 12


def test_scheduler_prefers_post_funding_capture_and_transient_retry(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshots = snapshots_from_json(payload)
    clock = FakeClock(snapshots[0].observed_at_ms)
    station, _, _, _ = _station(tmp_path, clock=clock)
    state = StationStateV1(
        station_config_sha256=station.config.config_sha256,
        started_at_ms=clock.value,
        deadline_at_ms=clock.value + 100_000_000,
        updated_at_ms=clock.value,
        next_funding_time_ms_by_symbol={"BTCUSDT": clock.value + 10 * 60 * 1000},
    )
    assert station._next_due(state, clock.value, any_success=True) == (
        clock.value + 10 * 60 * 1000 + 30 * 1000
    )
    state.next_funding_time_ms_by_symbol = {}
    assert station._next_due(state, clock.value, any_success=False) == (
        clock.value + station.config.transient_retry_seconds * 1000
    )
    state.next_funding_time_ms_by_symbol = {"BTCUSDT": clock.value - 30_000}
    state.last_error_by_symbol = {"BTCUSDT": "temporary public race"}
    assert station._next_due(state, clock.value, any_success=True) == (
        clock.value + station.config.funding_capture_retry_seconds * 1000
    )


def test_storage_cap_stops_before_any_network_fetch(tmp_path: Path) -> None:
    _, config, _, _ = _loaded()
    tiny = dataclasses.replace(
        config,
        max_journal_bytes_per_symbol=2,
        max_total_bytes=2,
        max_append_reserve_bytes=1,
        min_free_bytes=1,
    )
    clock = FakeClock(1_700_000_000_000)
    station, fetcher, _, _ = _station(tmp_path, clock=clock, config=tiny)
    result = station.run(max_cycles_this_process=1)
    assert result.state["status"] == "BLOCKED"
    assert result.state["stop_reason"] == "max_total_bytes_reached"
    assert fetcher.calls == {}


def test_low_free_space_is_fail_closed_without_deletion(tmp_path: Path) -> None:
    _, config, _, _ = _loaded()
    clock = FakeClock(1_700_000_000_000)
    station, fetcher, _, _ = _station(tmp_path, clock=clock, config=config)
    station.disk_usage = lambda path: shutil._ntuple_diskusage(100, 99, 1)
    result = station.run(max_cycles_this_process=1)
    assert result.state["status"] == "BLOCKED"
    assert result.state["stop_reason"] == "minimum_free_bytes_breached"
    assert fetcher.calls == {}
    assert (tmp_path / "launch_receipt.json").exists()


def test_corrupt_state_and_adapter_identity_fail_closed(tmp_path: Path) -> None:
    _, config, shadow, collector = _loaded()
    clock = FakeClock(1_700_000_000_000)
    station, _, _, _ = _station(tmp_path, clock=clock, config=config)
    station.run(max_cycles_this_process=1)
    path = tmp_path / "station_state.json"
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"status":"PAUSED"', '"status":"ACTIVE"'), encoding="utf-8")
    store = AtomicStationStateStore(path, config_sha256=config.config_sha256)
    with pytest.raises(CashCarryShadowError, match="checksum mismatch"):
        store.load()

    active = DurableCollectorConfigV2(
        enabled=True,
        shadow_enabled=True,
        basis_stress_bps=collector.basis_stress_bps,
        minimum_expected_edge_bps=collector.minimum_expected_edge_bps,
    )
    wrong = FunctionPublicAdapter(
        adapter_id="bitget_public_v2_cashcarry_v1",
        exchange_id="bitget",
        source_id="bitget_public_v2",
        fetcher=lambda *args, **kwargs: None,
    )
    with pytest.raises(CashCarryShadowError, match="identity differs"):
        PublicCashCarryStationV1(
            config=config,
            shadow_config=shadow,
            collector_config=active,
            adapter=wrong,
            root=tmp_path / "bitget",
        )


def test_source_has_no_key_environment_private_or_order_paths() -> None:
    sources = [
        (ROOT / "bot/public_cashcarry_station_v1.py").read_text(encoding="utf-8"),
        RUNNER.read_text(encoding="utf-8"),
    ]
    forbidden = (
        "os.getenv",
        "os.environ",
        "/v5/order/",
        "/v5/account/",
        "/v5/position/",
        "/v5/asset/transfer",
        "api-secret",
        "api-key",
    )
    for source in sources:
        lowered = source.lower()
        for token in forbidden:
            assert token not in lowered
