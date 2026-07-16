from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "configs/preregistered/bitget_cashcarry_public_v1_20260716.json"
FIXTURE = ROOT / "tests/fixtures/bitget_cashcarry_public_v1_responses.json"
RUNNER = ROOT / "scripts/run_bitget_cashcarry_public_v1.py"

from bot.bitget_cashcarry_public_v1 import (
    BITGET_ADAPTER_ID,
    BITGET_EXCHANGE_ID,
    BITGET_SOURCE_ID,
    BITGET_STATION_COMPATIBILITY,
    BitgetPublicCashCarrySnapshotV1,
    normalize_public_payloads,
    normalization_receipt,
)
from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError
from bot.bybit_cashcarry_shadow_v2 import PublicMarketSnapshotV2
from scripts import run_bitget_cashcarry_public_v1 as runner


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot() -> BitgetPublicCashCarrySnapshotV1:
    fixture = _fixture()
    return normalize_public_payloads(fixture["responses"], symbol=fixture["symbol"])


def test_preflight_is_default_disabled_no_network_no_write_and_source_separated(tmp_path: Path) -> None:
    receipt = runner._preflight(SPEC)
    assert receipt["adapter_id"] == BITGET_ADAPTER_ID
    assert receipt["exchange_id"] == BITGET_EXCHANGE_ID
    assert receipt["source_id"] == BITGET_SOURCE_ID
    assert receipt["default_enabled"] is False
    assert receipt["network_calls"] is False
    assert receipt["filesystem_writes"] is False
    assert receipt["api_keys_or_environment_reads"] is False
    assert receipt["private_api_calls"] is False
    assert receipt["broker_calls"] is False
    assert receipt["executable"] is False
    assert receipt["blocked_from_bybit_journal"] is True
    assert receipt["station_compatibility"] == BITGET_STATION_COMPATIBILITY
    assert not (tmp_path / "unexpected").exists()


def test_official_shape_fixture_normalizes_exact_precision_books_funding_and_fees() -> None:
    snapshot = _snapshot()
    assert snapshot.adapter_id == BITGET_ADAPTER_ID
    assert snapshot.source == BITGET_SOURCE_ID
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.instruments.spot.tick_size == "0.01"
    assert snapshot.instruments.spot.qty_step == "0.000001"
    assert snapshot.instruments.spot.min_order_qty == "0.000001"
    assert snapshot.instruments.spot.min_notional_usdt == "1"
    assert snapshot.instruments.spot.taker_fee_rate_public_default == "0.002"
    assert snapshot.instruments.usdt_perpetual.tick_size == "0.1"
    assert snapshot.instruments.usdt_perpetual.qty_step == "0.001"
    assert snapshot.instruments.usdt_perpetual.min_order_qty == "0.001"
    assert snapshot.instruments.usdt_perpetual.min_notional_usdt == "5"
    assert snapshot.instruments.usdt_perpetual.taker_fee_rate_public_default == "0.0006"
    assert snapshot.instruments.funding_interval_minutes == 480
    assert [row.settled_at_ms for row in snapshot.funding_settlements] == sorted(
        row.settled_at_ms for row in snapshot.funding_settlements
    )
    assert snapshot.funding_settlements[-1].perp_mark_price_proxy == pytest.approx(100020.05)
    assert snapshot.funding_settlements[-2].perp_mark_price_proxy is None
    assert snapshot.spot_bids[0].price == "99999.99"
    assert snapshot.perp_asks[0].price == "100020.1"


def test_normalization_is_deterministic_and_receipt_cannot_claim_station_or_execution() -> None:
    first = _snapshot()
    second = _snapshot()
    assert first.observation_id == second.observation_id
    assert first.payload() == second.payload()
    receipt = normalization_receipt(first)
    assert receipt["observation_id"] == first.observation_id
    assert receipt["station_compatibility"] == BITGET_STATION_COMPATIBILITY
    assert receipt["research_only"] is True
    assert receipt["executable"] is False
    assert receipt["broker_calls"] is False
    assert receipt["private_api_calls"] is False
    assert receipt["performance_claims"] is False
    assert len(receipt["blockers"]) == 4


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda p: p["spot_instrument"]["data"][0].update(status="halt"), "not tradable"),
        (
            lambda p: p["current_funding"]["data"][0].update(fundingRateInterval="4"),
            "interval mismatch",
        ),
        (lambda p: p["perp_book"]["data"].update(scale="1"), "scale differs"),
        (
            lambda p: p["spot_book"]["data"]["bids"].__setitem__(0, ["99999.995", "0.5"]),
            "off tick",
        ),
        (
            lambda p: p["spot_book"].update(requestTime=1784176000001),
            "after final server time",
        ),
    ],
)
def test_schema_drift_status_interval_scale_tick_and_time_fail_closed(mutate, match: str) -> None:
    payloads = copy.deepcopy(_fixture()["responses"])
    mutate(payloads)
    with pytest.raises(CashCarryShadowError, match=match):
        normalize_public_payloads(payloads, symbol="BTCUSDT")


def test_public_fetcher_uses_exact_allowlist_get_queries_and_final_server_time() -> None:
    fixture = _fixture()["responses"]
    by_path = {
        "/api/v2/spot/public/symbols": fixture["spot_instrument"],
        "/api/v2/spot/market/orderbook": fixture["spot_book"],
        "/api/v2/mix/market/contracts": fixture["perp_instrument"],
        "/api/v2/mix/market/merge-depth": fixture["perp_book"],
        "/api/v2/mix/market/current-fund-rate": fixture["current_funding"],
        "/api/v2/mix/market/history-fund-rate": fixture["funding_history"],
        "/api/v2/public/time": fixture["server_time"],
    }
    calls: list[str] = []

    def fake_get(url: str, *, timeout: float) -> dict:
        assert timeout == 12.0
        calls.append(url)
        parsed = urlparse(url)
        assert parsed.scheme == "https" and parsed.hostname == runner.PUBLIC_HOST
        query = parse_qs(parsed.query)
        if parsed.path != "/api/v2/public/time":
            assert query.get("symbol") == ["BTCUSDT"]
        if parsed.path.startswith("/api/v2/mix/"):
            assert query.get("productType") == ["usdt-futures"]
        return copy.deepcopy(by_path[parsed.path])

    snapshot = runner.fetch_public_snapshot(
        "BTCUSDT",
        timeout=12.0,
        book_limit=50,
        get_json=fake_get,
    )
    assert snapshot.observation_id == _snapshot().observation_id
    assert [urlparse(url).path for url in calls] == list(runner.PUBLIC_PATHS)
    assert urlparse(calls[-1]).path == "/api/v2/public/time"
    assert all("access-key" not in url.lower() and "/mix/order/" not in url for url in calls)


def test_url_guard_rejects_other_host_credentials_private_and_non_allowlisted_paths() -> None:
    bad = (
        "https://example.com/api/v2/public/time",
        "https://user:pass@api.bitget.com/api/v2/public/time",
        "https://api.bitget.com/api/v2/spot/account/info",
        "https://api.bitget.com/api/v2/mix/order/orders-history",
    )
    for url in bad:
        with pytest.raises(CashCarryShadowError, match="frozen public Bitget"):
            runner._get_json(url)
    with pytest.raises(CashCarryShadowError, match="unknown or duplicate"):
        runner._get_json("https://api.bitget.com/api/v2/public/time?ACCESS-KEY=secret")
    with pytest.raises(CashCarryShadowError, match="explicit USDT"):
        runner.fetch_public_payloads("BTCUSDT&secret=x", get_json=lambda *args, **kwargs: {})
    with pytest.raises(CashCarryShadowError, match="timeout"):
        runner.fetch_public_payloads("BTCUSDT", timeout=0, get_json=lambda *args, **kwargs: {})


def test_bitget_snapshot_is_not_bybit_snapshot_and_bybit_payload_constructor_rejects_it() -> None:
    snapshot = _snapshot()
    assert not isinstance(snapshot, PublicMarketSnapshotV2)
    assert snapshot.source != "bybit_public_v5"
    with pytest.raises((CashCarryShadowError, KeyError, TypeError)):
        PublicMarketSnapshotV2.from_mapping(snapshot.payload())


def test_runner_preflight_and_fixture_cli_are_offline_and_collect_requires_two_opt_ins(tmp_path: Path) -> None:
    preflight = subprocess.run(
        [sys.executable, str(RUNNER), "preflight"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(preflight.stdout)["network_calls"] is False
    normalized = subprocess.run(
        [sys.executable, str(RUNNER), "normalize-fixture"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(normalized.stdout)["source_id"] == BITGET_SOURCE_ID
    blocked = subprocess.run(
        [sys.executable, str(RUNNER), "collect-once", "--symbol", "BTCUSDT"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 2
    assert "requires --allow-public-network" in blocked.stderr
    assert list(tmp_path.iterdir()) == []


def test_sources_have_no_environment_key_private_account_order_or_transfer_adapter() -> None:
    sources = [
        (ROOT / "bot/bitget_cashcarry_public_v1.py").read_text(encoding="utf-8").lower(),
        RUNNER.read_text(encoding="utf-8").lower(),
    ]
    forbidden = (
        "os.getenv",
        "os.environ",
        "access-key",
        "access-sign",
        "access-passphrase",
        "/api/v2/spot/account/",
        "/api/v2/mix/account/",
        "/api/v2/mix/position/",
        "/api/v2/mix/order/",
        "/api/v2/spot/trade/",
        "/api/v2/spot/wallet/",
    )
    for source in sources:
        for token in forbidden:
            assert token not in source
