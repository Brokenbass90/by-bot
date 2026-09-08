from pathlib import Path
from types import SimpleNamespace

from research_lab.att1_lifecycle_profile import build_profile
from research_lab import att1_lifecycle_public_inputs as inputs


ROOT = Path(__file__).resolve().parents[1]


def test_public_inputs_adapter_exists():
    assert (ROOT / "research_lab" / "att1_lifecycle_public_inputs.py").is_file()


def test_causal_att1_replay_serializes_a_full_source_bound_signal(monkeypatch):
    h1 = 3_600_000
    rows = [[i * h1, "100", "101", "99", "100", "10"] for i in range(2160)]
    calls = []
    class Engine:
        def __init__(self, feed): self.feed = feed
        def _get_strategy(self, _symbol): return object()
        def signal(self, symbol, *row, observed_at_ms):
            calls.append((symbol, int(row[0]), observed_at_ms))
            return SimpleNamespace(side="short", entry=100.0, sl=110.0, tps=[88.0, 75.0], tp_fracs=[.55, .45], time_stop_bars=4032) if len(calls) == 48 else None
    monkeypatch.setattr(inputs, "ATT1LiveEngine", Engine)
    monkeypatch.setattr(inputs, "_resolved_config_hash", lambda *_args: inputs.PROFILE_FIXED51_CONFIG_HASHES["ATT1"])
    profile = build_profile(ROOT)
    available = 2160 * h1 + 20
    result = inputs.signal_from_rows("BTCUSDT", rows, profile, source_available_ms=available, clock_ms=available + 1)
    assert result["schema_id"] == "att1_lifecycle_signal_v1"
    assert result["stream"] == "EXECUTION_FORWARD"
    assert result["tps"] == ["88", "75"] and result["tp_fracs"] == ["0.55", "0.45"]
    assert result["profile_sha256"] == profile["profile_sha256"]
    assert len(calls) == 48 and all(call[2] == call[1] + h1 for call in calls)
