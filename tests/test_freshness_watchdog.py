"""Tests for scripts.freshness_watchdog.evaluate_freshness (Opus 2026-06-08)."""
import importlib.util
spec = importlib.util.spec_from_file_location("fw", "scripts/freshness_watchdog.py")
fw = importlib.util.module_from_spec(spec); spec.loader.exec_module(fw)
H = 3600.0


def test_all_ok():
    items = [
        {"name": "a", "present": True, "age_sec": 1 * H, "max_age_sec": 8 * H},
        {"name": "b", "present": True, "age_sec": 0.2 * H, "max_age_sec": 2 * H},
    ]
    r = fw.evaluate_freshness(items, 0)
    assert r["verdict"] == "ok" and not r["stale"] and set(r["ok"]) == {"a", "b"}


def test_detects_stale():
    items = [
        {"name": "allowlist", "present": True, "age_sec": 1437 * H, "max_age_sec": 8 * H},
        {"name": "regime", "present": True, "age_sec": 0.5 * H, "max_age_sec": 2 * H},
    ]
    r = fw.evaluate_freshness(items, 0)
    assert r["verdict"] == "stale"
    assert any(s["name"] == "allowlist" for s in r["stale"])
    assert "regime" in r["ok"]


def test_detects_missing():
    items = [{"name": "x", "present": False, "age_sec": 0, "max_age_sec": H}]
    r = fw.evaluate_freshness(items, 0)
    assert r["verdict"] == "stale" and r["missing"] == ["x"]
