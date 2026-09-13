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


def test_cached_closed_prefix_matches_canonical_rebuild_without_future_rows():
    from bot.public_h1_cache_store import CanonicalCachedFeed, PublicCacheViolation
    import pytest
    h1=3_600_000;start=1780002000000//h1*h1
    rows=[[start+i*h1,100.,101.+i%7,99.,100.,10.] for i in range(2160)]
    feed=CanonicalCachedFeed('BTCUSDT',rows)
    for end in range(len(rows)-48,len(rows)+1):
        feed.set_closed_prefix(end)
        reference=CanonicalCachedFeed('BTCUSDT',rows[:end])
        for tf in ('60','240','1440'):
            assert feed('BTCUSDT',tf,80)==reference('BTCUSDT',tf,80)
    for end in (-1,len(rows)+1,True):
        with pytest.raises(PublicCacheViolation):feed.set_closed_prefix(end)


def test_optimized_scan_matches_all_48_legacy_decisions_and_cutoffs(monkeypatch):
    import hashlib,json,math
    from scripts.run_att1_ets2s_signal_shadow import CausalCanonicalFeed, _signal_payload
    from strategies.att1_live import ATT1LiveEngine
    h1=3_600_000;start=1780002000000//h1*h1
    rows=[]
    for i in range(2880):
        c=100+8*math.sin(i/23)+i*.003
        rows.append([start+i*h1,c,c+1,c-1,c,10.])
    traces=[]
    class TracedEngine(ATT1LiveEngine):
        def signal(self,symbol,*row,observed_at_ms):
            result=super().signal(symbol,*row,observed_at_ms=observed_at_ms)
            consumed=self.last_closed_rows(symbol,'60')
            assert not consumed or int(consumed[-1][0])+h1<=observed_at_ms
            traces.append((row[0],observed_at_ms,hashlib.sha256(json.dumps(consumed).encode()).hexdigest(),_signal_payload(result)))
            return result
    class LegacyFeed:
        def __init__(self,symbol,history):self.inner=CausalCanonicalFeed(symbol,history)
        def set_closed_prefix(self,end):self.inner.set_cursor(end-1)
        def __call__(self,*args):return self.inner(*args)
    profile=build_profile(ROOT);now=rows[-1][0]+h1+20000
    monkeypatch.setattr(inputs,'ATT1LiveEngine',TracedEngine)
    optimized=inputs.signal_from_rows('BTCUSDT',rows,profile,source_available_ms=now,clock_ms=now)
    optimized_trace=traces[:];traces.clear()
    monkeypatch.setattr(inputs,'CanonicalCachedFeed',LegacyFeed)
    legacy=inputs.signal_from_rows('BTCUSDT',rows,profile,source_available_ms=now,clock_ms=now)
    assert len(traces)==len(optimized_trace)==48
    assert traces==optimized_trace and optimized==legacy
