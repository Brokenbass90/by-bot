"""Network boundary tests: only public subscribe/ping, persisted evidence not mocks."""
import asyncio
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("liquidation_v2_driver", ROOT / "scripts/collect_bybit_liquidations_v2.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_driver_keeps_raw_events_and_can_only_send_public_messages(tmp_path):
    sent = []
    class Socket:
        async def send(self, value): sent.append(json.loads(value))
        async def recv(self):
            if not getattr(self, "ack", False):
                self.ack = True
                return json.dumps(dict(op="subscribe", success=True, req_id=sent[0]["req_id"]))
            if not getattr(self, "event", False):
                self.event = True
                now = time.time_ns() // 1000000
                return json.dumps(dict(topic="allLiquidation.BTCUSDT", type="snapshot", ts=now,
                     data=[dict(T=now, s="BTCUSDT", S="Sell", v="1", p="100")]))
            await asyncio.sleep(1)
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
    socket = Socket()
    asyncio.run(driver.run(tmp_path, ("BTCUSDT",), {"test.py": "c" * 64},
                           connector=lambda *args, **kwargs: socket,
                           duration_sec=0.15, tick_sec=0.03, min_free_bytes=0))
    health = json.loads((tmp_path / "heartbeat.json").read_text())
    assert health["observed_event_count"] == 1
    assert health["status"] == "STOPPED"
    assert health["orders_allowed"] is False
    rows = [json.loads(line) for p in tmp_path.glob("runs/*/frames.jsonl") for line in p.read_text().splitlines()]
    event = next(e for row in rows for e in row.get("normalized_events", []))
    assert event["liquidated_position_side"] == "short"
    assert all(m["op"] in {"subscribe", "ping"} for m in sent)
    assert sent[0]["args"] == ["allLiquidation.BTCUSDT"]


def test_subscription_failure_is_persisted_not_reported_as_healthy(tmp_path):
    sent = []
    class Socket:
        async def send(self, value): sent.append(json.loads(value))
        async def recv(self):
            return json.dumps(dict(op="subscribe", success=False, req_id=sent[0]["req_id"]))
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
    asyncio.run(driver.run(tmp_path, ("BTCUSDT",), {"test.py": "c" * 64},
                           connector=lambda *args, **kwargs: Socket(),
                           duration_sec=0.1, tick_sec=0.02, min_free_bytes=0))
    h = json.loads((tmp_path / "heartbeat.json").read_text())
    assert h["subscription_confirmed"] is False
    assert h["observed_event_count"] == 0
    assert h["qa_counts"]["SUBSCRIPTION_REJECTED"] >= 1
    assert h["counts"]["DISCONNECTED"] >= 1


def test_cli_bad_symbols_creates_no_output(tmp_path):
    import subprocess
    result = subprocess.run([__import__("sys").executable,
        str(ROOT / "scripts/collect_bybit_liquidations_v2.py"), "--root", str(tmp_path / "bad"),
        "--symbols", "BTCUSDT,BTCUSDT", "--duration-sec", "0.01"], capture_output=True)
    assert result.returncode == 78
    assert not (tmp_path / "bad").exists()


def test_cli_verify_only_does_not_create_capture_or_connection(tmp_path):
    import subprocess
    result = subprocess.run([__import__("sys").executable,
        str(ROOT / "scripts/collect_bybit_liquidations_v2.py"), "--root", str(tmp_path / "empty"),
        "--verify-only"], capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PUBLIC_SOURCE_CODE_VERIFIED_NOT_STARTED"
    assert not (tmp_path / "empty").exists()
