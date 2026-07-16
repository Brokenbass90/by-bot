import json
import time

from bot import health_gate


def _gate_for(tmp_path, monkeypatch, *, age_sec: int, status: str = "KILL"):
    path = tmp_path / "strategy_health.json"
    path.write_text(json.dumps({"strategies": {"alt_trendline_touch_v1": {"status": status}}}))
    ts = time.time() - age_sec
    path.touch()
    # touch() uses now; set the intended provenance age afterwards.
    import os
    os.utime(path, (ts, ts))
    monkeypatch.setattr(health_gate, "HEALTH_FILE", path)
    monkeypatch.setattr(health_gate, "ALERT_LOG", tmp_path / "alerts.json")
    monkeypatch.setenv("HEALTH_GATE_MAX_SOURCE_AGE_SEC", "100")
    return health_gate.HealthGate()


def test_stale_health_snapshot_cannot_block_live_entry(tmp_path, monkeypatch):
    gate = _gate_for(tmp_path, monkeypatch, age_sec=500, status="KILL")
    sent = []
    monkeypatch.setattr(health_gate, "_tg", lambda token, chat, msg: sent.append(msg))

    assert gate.allow_entry("alt_trendline_touch_v1", "BTCUSDT") is True
    assert gate.get_status("alt_trendline_touch_v1") == "WATCH"
    assert gate.source_meta()["stale"] is True
    assert len(sent) == 1

    # The stale-source warning is deduplicated for the day.
    assert gate.allow_entry("alt_trendline_touch_v1", "ETHUSDT") is True
    assert len(sent) == 1


def test_fresh_kill_snapshot_still_blocks(tmp_path, monkeypatch):
    gate = _gate_for(tmp_path, monkeypatch, age_sec=1, status="KILL")
    monkeypatch.setattr(health_gate, "_tg", lambda *args, **kwargs: None)

    assert gate.source_meta()["stale"] is False
    assert gate.allow_entry("alt_trendline_touch_v1", "BTCUSDT") is False


def test_missing_health_snapshot_is_fail_open(tmp_path, monkeypatch):
    monkeypatch.setattr(health_gate, "HEALTH_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(health_gate, "ALERT_LOG", tmp_path / "alerts.json")
    monkeypatch.setattr(health_gate, "_tg", lambda *args, **kwargs: None)
    gate = health_gate.HealthGate()

    assert gate.source_meta()["stale"] is True
    assert gate.allow_entry("alt_trendline_touch_v1", "BTCUSDT") is True
