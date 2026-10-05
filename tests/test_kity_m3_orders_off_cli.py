"""Public-only acceptance tests for the KITY M3 orders-OFF CLI façade."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kity_m3_orders_off.py"


def api():
    """Load the script without importing any project trading module."""
    assert SCRIPT.is_file(), "public orders-OFF CLI module is missing"
    spec = importlib.util.spec_from_file_location("kity_m3_orders_off_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _capture(raw: str, *, venue: str = "binance", endpoint: str = "/fapi/v1/time") -> dict:
    return {
        "venue": venue,
        "endpoint": endpoint,
        "params": {},
        "request_ms": 100,
        "receive_ms": 101,
        "raw": raw,
        "sha256": _sha_bytes(raw.encode("utf-8")),
    }


def _core_fixture():
    spec=importlib.util.spec_from_file_location('kity_fixture_publish',ROOT/'tests'/'test_kity_m3_orders_off.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _receipt(identity=None):
    f=_core_fixture();signal=f.sig()
    return {'identity':'signal-2026-10-08','day':'2026-10-08','research_ref':f.REF,
            'request_digest':f.api('digest')(signal['source_bundle']),'status':signal['status'],
            'orders_allowed':False,'money_ready':False,'signal':signal}


@pytest.fixture(autouse=True)
def publication_fixture_clock(monkeypatch):
    f=_core_fixture()
    monkeypatch.setattr('time.time_ns',lambda:f.NOW*1_000_000)


class _Response:
    def __init__(self, raw: bytes, url: str):
        self.raw = raw
        self.url = url

    def read(self, amount: int = -1) -> bytes:
        return self.raw if amount < 0 else self.raw[:amount]

    def geturl(self) -> str:
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_module_exposes_only_public_orders_off_interface():
    module = api()
    assert callable(module.get_public)
    assert callable(module.compare_forward)
    assert callable(module.publish_receipt)
    assert "send_orders" not in vars(module)
    assert "moneyReady" not in vars(module)


def test_public_capture_preserves_exact_utf8_wire_and_hash(monkeypatch):
    module = api()
    raw = b'{ "serverTime" : 123 }\n'
    calls = []

    def fake_open(request, *, timeout):
        calls.append((request.full_url, timeout))
        return _Response(raw, request.full_url)

    monkeypatch.setattr(module, "_open_public", fake_open)
    result = module.get_public("binance", "/fapi/v1/time", {})

    assert result["raw"] == raw.decode("utf-8")
    assert result["sha256"] == _sha_bytes(raw)
    assert result["params"] == {}
    assert result["venue"] == "BINANCE"
    assert calls[0][1] == 10
    assert result["request_ms"] <= result["receive_ms"]


@pytest.mark.parametrize(
    ("venue", "endpoint", "params"),
    [
        ("binance", "/fapi/v1/depth", {"symbol": "BTCUSDT", "limit": True}),
        ("binance", "/fapi/v1/time", {"symbol": "BTCUSDT"}),
        ("bybit", "/v5/market/orderbook", {"category": "spot", "symbol": "BTCUSDT"}),
        ("bybit", "/v5/market/tickers", {"category": "linear", "unexpected": "x"}),
        ("binance", "https://evil.invalid/fapi/v1/time", {}),
    ],
)
def test_public_capture_rejects_nonallowlisted_endpoint_or_exact_param_type(venue, endpoint, params):
    with pytest.raises(ValueError, match="allowlisted|parameter|endpoint"):
        api().get_public(venue, endpoint, params)


def test_public_capture_rejects_redirect_and_oversized_response(monkeypatch):
    module = api()
    monkeypatch.setattr(
        module,
        "_open_public",
        lambda request, *, timeout: _Response(b"{}", "https://elsewhere.invalid/fapi/v1/time"),
    )
    with pytest.raises(ValueError, match="redirect"):
        module.get_public("binance", "/fapi/v1/time", {})

    monkeypatch.setattr(
        module,
        "_open_public",
        lambda request, *, timeout: _Response(b"x" * (module.BODY_MAX_BYTES + 1), request.full_url),
    )
    with pytest.raises(ValueError, match="body"):
        module.get_public("binance", "/fapi/v1/time", {})


def test_capture_payload_rejects_tampered_or_non_json_wire(monkeypatch):
    module = api()
    monkeypatch.setattr(module, "_open_public", lambda request, *, timeout: _Response(b"not-json", request.full_url))
    with pytest.raises(ValueError, match="JSON"):
        module.get_public("binance", "/fapi/v1/time", {})


def test_compare_forward_calls_independent_reconstruction_and_blocks_missing_wire_provenance(tmp_path, monkeypatch):
    module = api()
    calls = []
    reconstructed = {
        "status": "BLOCKED_DATA",
        "orders_allowed": False,
        "signal_valid": True,
        "day": "2026-10-08",
        "research_ref": "d6ed8126c041969de0bc6191e39fefe4a1272d5b",
        "basket": [{"symbol": f"S{i}", "side": "LONG" if i < 5 else "SHORT"} for i in range(10)],
    }
    monkeypatch.setattr(module, "_reconstruct_signal", lambda bundle, now_ms: calls.append((bundle, now_ms)) or reconstructed)
    signal = {"day": "2026-10-08", "basket": reconstructed["basket"]}
    (tmp_path / "signal.json").write_text(json.dumps(signal), encoding="utf-8")
    manifest = {"files": [{"path": "signal.json", "sha256": _sha_bytes((tmp_path / "signal.json").read_bytes())}]}
    (tmp_path / "file_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = module.compare_forward({"raw": "caller bundle"}, tmp_path, 456)

    assert calls == [({"raw": "caller bundle"}, 456)]
    assert result["status"] == "BLOCKED_DATA"
    assert result["orders_allowed"] is False
    assert result["basket_comparison"]["matches"] is True
    assert "FORWARD_RESEARCH_REF_MISSING" in result["reasons"]
    assert "RAW_WIRE_PROVENANCE_MISSING" in result["reasons"]


def test_compare_forward_accepts_declared_date_and_core_frozen_signal_shape(tmp_path, monkeypatch):
    module = api()
    legs = [{"symbol": f"S{i}", "side": "LONG" if i < 5 else "SHORT"} for i in range(10)]
    local = {
        "status": "BLOCKED_DATA",
        "orders_allowed": False,
        "day": "2026-10-08",
        "research_ref": "d6ed8126c041969de0bc6191e39fefe4a1272d5b",
        "frozen_signal": {"long": legs[:5], "short": legs[5:]},
    }
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: local)
    signal = {"date": "2026-10-08", "basket": legs}
    (tmp_path / "signal.json").write_text(json.dumps(signal), encoding="utf-8")
    (tmp_path / "file_manifest.json").write_text(
        json.dumps({"files": [{"path": "signal.json", "sha256": _sha_bytes((tmp_path / "signal.json").read_bytes())}]}),
        encoding="utf-8",
    )

    result = module.compare_forward({}, tmp_path, 1)

    assert result["basket_comparison"]["matches"] is True
    assert "FORWARD_DAY_MISMATCH" not in result["reasons"]


def test_compare_forward_consumes_current_claude_syroe_schema_but_blocks_unprovenance(tmp_path, monkeypatch):
    module = api()
    core_spec = importlib.util.spec_from_file_location("kity_m3_core_fixture_forward", ROOT / "tests" / "test_kity_m3_orders_off.py")
    assert core_spec is not None and core_spec.loader is not None
    core_fixture = importlib.util.module_from_spec(core_spec)
    core_spec.loader.exec_module(core_fixture)
    local = core_fixture.api("reconstruct_signal")(core_fixture.bundle(), core_fixture.NOW)
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: local)
    frozen = local["frozen_signal"]
    syroe = tmp_path / "syroe"
    syroe.mkdir()
    source_hashes = {}
    for name in ("exchangeInfo.json", "oi_2355.json", "klines_d-1.json"):
        raw = b"derived-only"
        (syroe / name).write_bytes(raw)
        source_hashes[name] = _sha_bytes(raw)
    forward = {
        "d": frozen["day"],
        "long": [{"s": leg["symbol"], "taker": leg["taker"]} for leg in frozen["long"]],
        "short": [{"s": leg["symbol"], "taker": leg["taker"]} for leg in frozen["short"]],
        "sha256": source_hashes,
    }
    (tmp_path / "signal.json").write_text(json.dumps(forward), encoding="utf-8")

    result = module.compare_forward(core_fixture.bundle(), tmp_path, core_fixture.NOW)

    assert result["status"] == "BLOCKED_DATA"
    assert result["orders_allowed"] is False
    assert result["basket_comparison"]["matches"] is True
    assert "FORWARD_RESEARCH_REF_MISSING" in result["reasons"]
    assert "RAW_WIRE_PROVENANCE_MISSING" in result["reasons"]


@pytest.mark.parametrize("bad_path", ["../outside.json", "nested/file.json", "/absolute.json"])
def test_compare_forward_rejects_unsafe_or_forged_manifest_entries(tmp_path, monkeypatch, bad_path):
    module = api()
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: {"status": "BLOCKED_DATA", "orders_allowed": False, "basket": []})
    (tmp_path / "signal.json").write_text("{}", encoding="utf-8")
    (tmp_path / "file_manifest.json").write_text(
        json.dumps({"files": [{"path": bad_path, "sha256": "0" * 64}]}), encoding="utf-8"
    )

    result = module.compare_forward({}, tmp_path, 1)

    assert result["status"] == "BLOCKED_DATA"
    assert result["orders_allowed"] is False
    assert any("FORWARD_MANIFEST" in reason for reason in result["reasons"])


def test_compare_forward_blocks_malformed_partial_and_wrong_hash(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: {"status": "BLOCKED_DATA", "orders_allowed": False, "basket": []})
    (tmp_path / "signal.json").write_text("{", encoding="utf-8")
    (tmp_path / "file_manifest.json").write_text(
        json.dumps({"files": [{"path": "signal.json", "sha256": "f" * 64}]}), encoding="utf-8"
    )

    result = module.compare_forward({}, tmp_path, 1)

    assert result["status"] == "BLOCKED_DATA"
    assert result["orders_allowed"] is False
    assert result["basket_comparison"]["matches"] is False
    assert any("FORWARD" in reason for reason in result["reasons"])


def test_compare_forward_blocks_forged_raw_wire_hash(tmp_path, monkeypatch):
    module = api()
    legs = [{"symbol": f"S{i}", "side": "LONG" if i < 5 else "SHORT"} for i in range(10)]
    local = {"status": "BLOCKED_DATA", "orders_allowed": False, "day": "2026-10-08", "research_ref": "d6ed8126c041969de0bc6191e39fefe4a1272d5b", "basket": legs}
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: local)
    signal = {"date": "2026-10-08", "research_ref": local["research_ref"], "basket": legs, "raw_captures": [{"raw": "{}", "sha256": "0" * 64}]}
    (tmp_path / "signal.json").write_text(json.dumps(signal), encoding="utf-8")
    (tmp_path / "file_manifest.json").write_text(
        json.dumps({"files": [{"path": "signal.json", "sha256": _sha_bytes((tmp_path / "signal.json").read_bytes())}]}),
        encoding="utf-8",
    )

    result = module.compare_forward({}, tmp_path, 1)

    assert result["status"] == "BLOCKED_DATA"
    assert "RAW_WIRE_PROVENANCE_INVALID" in result["reasons"]


def test_publish_receipt_reuses_only_byte_identical_valid_receipt(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    runtime = tmp_path / ".private" / "kity_m3_orders_off"
    runtime.mkdir(parents=True)
    receipt = _receipt()

    first = module.publish_receipt(runtime, receipt["identity"], receipt)
    second = module.publish_receipt(runtime, receipt["identity"], dict(receipt))

    assert first["status"] == "BLOCKED_DATA"
    assert first["orders_allowed"] is False
    assert first["reused"] is False
    assert second["reused"] is True
    assert Path(first["path"]).read_bytes() == Path(second["path"]).read_bytes()


def test_publish_receipt_blocks_conflicts_tampering_symlinks_and_incomplete_temp(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    runtime = tmp_path / "runtime" / "kity_m3_orders_off"
    runtime.mkdir(parents=True)
    receipt = _receipt("signal-2026-10-08")
    first = module.publish_receipt(runtime, "signal-2026-10-08", receipt)
    with pytest.raises(ValueError, match="conflict|digest"):
        module.publish_receipt(runtime, "signal-2026-10-08", {**receipt, "request_digest": "b" * 64})

    target = Path(first["path"])
    target.write_bytes(b'{"receipt":{},"receipt_sha256":"bad"}')
    with pytest.raises(ValueError, match="invalid"):
        module.publish_receipt(runtime, "signal-2026-10-08", receipt)

    target.unlink()
    target.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="symlink"):
        module.publish_receipt(runtime, "signal-2026-10-08", receipt)

    target.unlink()
    (target.parent / ".signal-2026-10-08.json.tmp.crash").write_text("incomplete", encoding="utf-8")
    assert module.publish_receipt(runtime, "signal-2026-10-08", receipt)["reused"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"research_ref": "0" * 40},
        {"day": "2026-19-99"},
        {"money_ready": True},
    ],
)
def test_publish_receipt_rejects_unpinned_invalid_or_money_ready_content(tmp_path, monkeypatch, change):
    module = api()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    runtime = tmp_path / ".private" / "kity_m3_orders_off"
    runtime.mkdir(parents=True)
    receipt = {**_receipt("signal-2026-10-08"), **change}

    with pytest.raises(ValueError):
        module.publish_receipt(runtime, "signal-2026-10-08", receipt)


def test_publish_receipt_serializes_competing_writers_without_second_intent(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    runtime = tmp_path / ".private" / "kity_m3_orders_off"
    runtime.mkdir(parents=True)
    receipt = _receipt("signal-2026-10-08")
    results: list[dict] = []
    errors: list[Exception] = []

    def write_once():
        try:
            results.append(module.publish_receipt(runtime, "signal-2026-10-08", receipt))
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    workers = [threading.Thread(target=write_once) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert errors == []
    assert len(results) == 4
    assert sum(not item["reused"] for item in results) == 1
    assert sum(item["reused"] for item in results) == 3


def test_cli_returns_nonzero_blocked_data_for_malformed_input_and_zero_for_valid_blocked(tmp_path, monkeypatch, capsys):
    module = api()
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    assert module.main(["reconstruct", "--bundle", str(malformed)]) != 0
    error = json.loads(capsys.readouterr().out)
    assert error["status"] == "BLOCKED_DATA"
    assert error["orders_allowed"] is False

    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "_reconstruct_signal", lambda *_: {"status": "BLOCKED_DATA", "orders_allowed": False, "reasons": ["MISSING"]})
    assert module.main(["reconstruct", "--bundle", str(bundle)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED_DATA"
    assert result["orders_allowed"] is False


def test_capture_cli_writes_only_to_explicit_kity_runtime(tmp_path, monkeypatch, capsys):
    module = api()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "get_public", lambda *_: _capture("{}"))
    runtime = tmp_path / ".private" / "kity_m3_orders_off"
    runtime.mkdir(parents=True)
    safe = runtime / "capture.json"
    assert module.main(["capture", "--venue", "binance", "--endpoint", "/fapi/v1/time", "--params", "{}", "--output", str(safe)]) == 0
    assert json.loads(safe.read_text(encoding="utf-8"))["raw"] == "{}"
    capsys.readouterr()

    outside = tmp_path / "outside.json"
    assert module.main(["capture", "--venue", "binance", "--endpoint", "/fapi/v1/time", "--params", "{}", "--output", str(outside)]) != 0
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED_DATA"


def test_cli_reconstruct_and_assess_synthetic_core_fixture_stays_orders_off(tmp_path, monkeypatch, capsys):
    module = api()
    core_spec = importlib.util.spec_from_file_location("kity_m3_core_fixture", ROOT / "tests" / "test_kity_m3_orders_off.py")
    assert core_spec is not None and core_spec.loader is not None
    core_fixture = importlib.util.module_from_spec(core_spec)
    core_spec.loader.exec_module(core_fixture)
    monkeypatch.setattr(module.time, "time_ns", lambda: core_fixture.NOW * 1_000_000)

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(core_fixture.bundle()), encoding="utf-8")
    assert module.main(["reconstruct", "--bundle", str(bundle_path)]) == 0
    signal = json.loads(capsys.readouterr().out)
    assert signal["signal_valid"] is True
    assert signal["orders_allowed"] is False
    assert signal["money_ready"] is False

    signal_path = tmp_path / "signal.json"
    execution_path = tmp_path / "execution.json"
    signal_path.write_text(json.dumps(signal), encoding="utf-8")
    execution_path.write_text(json.dumps(core_fixture.execution()), encoding="utf-8")
    assert module.main(["assess", "--signal", str(signal_path), "--execution", str(execution_path)]) == 0
    assessed = json.loads(capsys.readouterr().out)
    assert assessed["status"] == "BLOCKED_DATA"
    assert assessed["orders_allowed"] is False
    assert assessed["money_ready"] is False


def test_cli_help_does_not_import_core(monkeypatch):
    module = api()
    monkeypatch.setattr(module.importlib, "import_module", lambda *_: pytest.fail("core import during --help"))
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--help"])
    assert exit_info.value.code == 0

def test_review_generic_ready_friday_receipt_is_not_publishable():
    module=api();receipt={**_receipt(),'day':'2026-10-09','status':'READY_FOR_CANARY','prospective_eligible':True}
    with pytest.raises(ValueError):module._validate_receipt(receipt['identity'],receipt)


def test_review_signal_week_cannot_be_sealed_under_another_identity(tmp_path,monkeypatch):
    module=api();monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    runtime=tmp_path/'.private'/'kity_m3_orders_off';runtime.mkdir(parents=True)
    receipt=_receipt();receipt['identity']='alternate-same-week'
    with pytest.raises(ValueError):module.publish_receipt(runtime,receipt['identity'],receipt)


def test_review_actual_seal_time_prevents_late_prospective_credit_and_replay_reuses_seal(tmp_path,monkeypatch):
    module=api();f=_core_fixture();monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    runtime=tmp_path/'.private'/'kity_m3_orders_off';runtime.mkdir(parents=True)
    receipt=_receipt();late=f.T+f.DAY+1
    monkeypatch.setattr(module.time,'time_ns',lambda:late*1_000_000)
    first=module.publish_receipt(runtime,receipt['identity'],receipt)
    assert first['seal']['sealed_ms']==late and first['seal']['prospective_eligible'] is False
    original=Path(first['path']).read_bytes()
    monkeypatch.setattr(module.time,'time_ns',lambda:(late+10000)*1_000_000)
    replay=module.publish_receipt(runtime,receipt['identity'],receipt)
    assert replay['reused'] and replay['seal']==first['seal']
    assert Path(first['path']).read_bytes()==original


def test_review_sealed_metadata_tampering_is_rejected(tmp_path,monkeypatch):
    module=api();monkeypatch.setattr(module,'REPO_ROOT',tmp_path)
    runtime=tmp_path/'.private'/'kity_m3_orders_off';runtime.mkdir(parents=True)
    receipt=_receipt();first=module.publish_receipt(runtime,receipt['identity'],receipt)
    path=Path(first['path']);payload=json.loads(path.read_text());payload['seal']['sealed_ms']=1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):module.publish_receipt(runtime,receipt['identity'],receipt)

def test_review_cli_standalone_uses_pure_core_without_project_pythonpath(tmp_path):
    import subprocess
    fixture=_core_fixture();path=tmp_path/'bundle.json';path.write_text(json.dumps(fixture.bundle()))
    env={key:value for key,value in os.environ.items() if key!='PYTHONPATH'}
    result=subprocess.run([sys.executable,str(SCRIPT),'reconstruct','--bundle',str(path)],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    output=json.loads(result.stdout)
    assert output['orders_allowed'] is False and output['status']=='BLOCKED_DATA'
