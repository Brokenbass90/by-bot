import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from bot.bybit_liquidation_collector_v2 import Journal
from test_bybit_liquidation_universe_v2_1 import source
from research_lab.bybit_liquidation_universe_v2_1 import freeze

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("liquidation_v2_1_export", ROOT / "scripts/export_bybit_liquidation_v2_1.py")
exporter = importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)


def test_launcher_verify_only_binds_frozen_universe_without_starting_a_writer(tmp_path):
    pages, tick = source();m = freeze(pages, tick, prereg_sha256="d" * 64)
    p = tmp_path / "universe.json";p.write_text(json.dumps(m))
    r = subprocess.run([sys.executable, str(ROOT / "scripts/start_bybit_liquidation_v2_1.py"),
                        "--universe", str(p), "--root", str(tmp_path / "runtime"), "--verify-only"],
                       capture_output=True,text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["status"] == "V2_1_UNIVERSE_AND_CODE_VERIFIED_NOT_STARTED"
    assert len(d["symbols"]) == 25
    assert d["orders_allowed"] is False
    assert not (tmp_path / "runtime").exists()


def test_flat_export_retains_duplicate_candidates_and_keeps_source_bytes(tmp_path):
    runtime = tmp_path / "runtime";now = 1791964800000
    with Journal(runtime, ("BTCUSDT",), {"source.py":"a"*64}, now_ms=now, min_free_bytes=0) as j:
        j.connected("c1","sub",now)
        wire = json.dumps(dict(topic="allLiquidation.BTCUSDT",type="snapshot",ts=now,
                    data=[dict(T=now-1,s="BTCUSDT",S="Buy",v="1",p="100")]))
        j.receive(wire,recv_ms=now,connection_id="c1")
        j.receive(wire,recv_ms=now+1,connection_id="c1")
        capture = next(runtime.glob("runs/*/frames.jsonl"));before=capture.read_bytes()
        output = runtime / "exports" / "normalized.jsonl"
        receipt = exporter.export(runtime, output)
        assert receipt["event_count"] == 2
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        assert rows[0]["side"] == "long" and rows[0]["ts_ms"] == now-1
        assert rows[0]["recv_ts_ms"] == now
        assert "DUPLICATE_CANDIDATE_RETAINED" in rows[1]["qa_flags"]
        assert receipt["strategy_runs"] == 0 and receipt["source_gate_pass"] is False
        assert capture.read_bytes() == before
        assert output.stat().st_mode & 0o222 == 0
        with pytest.raises(FileExistsError):exporter.export(runtime,output)


def test_corrupt_source_cannot_publish_a_normalized_export(tmp_path):
    runtime=tmp_path/'runtime'
    with Journal(runtime,("BTCUSDT",),{"s":"a"*64},now_ms=1791964800000,min_free_bytes=0):pass
    capture=next(runtime.glob('runs/*/frames.jsonl'))
    capture.write_bytes(capture.read_bytes().replace(b'PROCESS_START',b'PROCESS_BAD!!'))
    output=runtime/'exports'/'bad.jsonl'
    with pytest.raises(ValueError,match='CHAIN'):exporter.export(runtime,output)
    assert not output.exists()


def test_export_cannot_write_outside_own_export_directory(tmp_path):
    runtime=tmp_path/'runtime'
    with Journal(runtime,("BTCUSDT",),{"s":"a"*64},now_ms=1791964800000,min_free_bytes=0):pass
    with pytest.raises(ValueError,match='EXPORT_PATH'):exporter.export(runtime,tmp_path/'other.jsonl')


def test_zero_event_export_does_not_claim_gate_pass(tmp_path):
    runtime=tmp_path/'runtime'
    with Journal(runtime,("BTCUSDT",),{"s":"a"*64},now_ms=1791964800000,min_free_bytes=0):pass
    receipt=exporter.export(runtime,runtime/'exports'/'empty.jsonl')
    assert receipt['event_count']==0
    assert receipt['status']=='SOURCE_EXPORT_ONLY_NOT_RESEARCH_READY'
    assert receipt['full_exchange_coverage']=='UNKNOWN_NO_SEQUENCE_OR_BACKFILL'
