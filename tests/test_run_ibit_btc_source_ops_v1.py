"""Scheduling wrapper stays network-off and refuses changed/financial packages."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_ibit_btc_source_ops_v1 as ops


def package(tmp_path,monkeypatch):
    monkeypatch.setattr(ops,'ROOT',tmp_path)
    files={name:hashlib.sha256(name.encode()).hexdigest() for name in ops.REQUIRED}
    for name in files:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
    raw=json.dumps({'schema':'IBIT_DATA_ONLY_SOURCE_PACKAGE_V1','orders_enabled':False,'files':files}).encode()
    p=tmp_path/'spec.json';p.write_bytes(raw)
    return p,hashlib.sha256(raw).hexdigest()


def test_default_never_constructs_collector_or_reads_profile(monkeypatch,capsys):
    def forbidden(*a,**kw):pytest.fail('network construction in default mode')
    monkeypatch.setattr(ops,'Collector',forbidden)
    assert ops.main([])==0
    assert json.loads(capsys.readouterr().out)['status']=='NO_NETWORK'


def test_changed_package_blocks_before_client(tmp_path,monkeypatch):
    path,pin=package(tmp_path,monkeypatch)
    assert ops.verify(path,pin)['orders_enabled'] is False
    (tmp_path/next(iter(ops.REQUIRED))).write_text('changed')
    with pytest.raises(ops.SourceError,match='SOURCE_PIN'):ops.verify(path,pin)


def test_financial_package_rejected_even_with_matching_hash(tmp_path,monkeypatch):
    path,pin=package(tmp_path,monkeypatch);value=json.loads(path.read_bytes());value['orders_enabled']=True
    raw=json.dumps(value).encode();path.write_bytes(raw)
    with pytest.raises(ops.SourceError,match='PACKAGE_AUTHORITY'):ops.verify(path,hashlib.sha256(raw).hexdigest())
