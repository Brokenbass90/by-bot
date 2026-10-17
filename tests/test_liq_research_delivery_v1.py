import json
from pathlib import Path
import pytest
from bot.bybit_liquidation_collector_v2 import Journal
from research_lab import liq_research_delivery_v1 as delivery

NOW=1792261000000

@pytest.fixture
def source(tmp_path,monkeypatch):
    root=tmp_path/'runtime'
    with Journal(root,('BTCUSDT',),{'s':'a'*64},now_ms=NOW-10000,min_free_bytes=0) as j:
        j.connected('one','sub',NOW-9000)
        wire=json.dumps(dict(topic='allLiquidation.BTCUSDT',type='snapshot',ts=NOW-8000,
          data=[dict(T=NOW-8001,s='BTCUSDT',S='Buy',v='1',p='100')]))
        j.receive(wire,recv_ms=NOW-8000,connection_id='one')
        j.receive(wire,recv_ms=NOW-7999,connection_id='one')
        j.disconnected('test',NOW-7000);j.connected('two','sub',NOW-6000);j.heartbeat(NOW)
        manifest=json.loads((root/'source-manifest.json').read_bytes())
    monkeypatch.setattr(delivery,'EPOCH',manifest['epoch_id'])
    monkeypatch.setattr(delivery,'MANIFEST',manifest['manifest_sha256'])
    monkeypatch.setattr(delivery,'SYMBOLS',tuple(manifest['symbols']))
    return root


def test_actual_rows_retained_with_gap_sidecar_and_byte_preserving_reimport(source,tmp_path):
    before={p:p.read_bytes() for p in source.glob('runs/*/frames.jsonl')}
    result=delivery.seal_daily(source,'20261017',now_ms=NOW)
    assert result['event_count']==2 and not result['source_gate_pass'] and not result['orders_allowed']
    assert result['coverage']=='UNKNOWN_NO_SEQUENCE_OR_BACKFILL'
    qa=json.loads((source/'exports/normalized-20261017.qa.json').read_bytes())
    assert qa['gap_records']==1 and qa['prospective_decisions']==0
    rows=[json.loads(s) for s in (source/'exports/normalized-20261017.jsonl').read_text().splitlines()]
    assert rows[0]['t_available_ms']==NOW-8000 and rows[0]['ts_ms']==NOW-8001
    assert 'DUPLICATE_CANDIDATE_RETAINED' in rows[1]['qa_flags']
    dest=tmp_path/'research';one=delivery.import_snapshot(source/'exports',dest,'20261017')
    old={p.name:p.read_bytes() for p in dest.iterdir() if p.is_file()}
    two=delivery.import_snapshot(source/'exports',dest,'20261017')
    assert one['event_count']==two['event_count']==2 and two['already_imported'] is True
    assert old=={p.name:p.read_bytes() for p in dest.iterdir() if p.is_file()}
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert delivery.seal_daily(source,'20261017',now_ms=NOW)['already_sealed'] is True


@pytest.mark.parametrize('bad',['normalized','receipt','heartbeat','wrong_epoch','missing_delivery'])
def test_untrusted_snapshot_is_not_imported(source,tmp_path,bad):
    delivery.seal_daily(source,'20261017',now_ms=NOW)
    suffix={'normalized':'.jsonl','receipt':'.receipt.json','heartbeat':'.heartbeat.json','wrong_epoch':'.delivery.json','missing_delivery':'.delivery.json'}[bad]
    p=source/('exports/normalized-20261017'+suffix)
    if bad=='missing_delivery':p.unlink()
    elif bad=='wrong_epoch':
        x=json.loads(p.read_bytes());x['epoch_id']='other';p.chmod(0o600);p.write_text(json.dumps(x))
    else:p.chmod(0o600);p.write_bytes(p.read_bytes()+b'corrupt')
    with pytest.raises((ValueError,FileNotFoundError)):delivery.import_snapshot(source/'exports',tmp_path/'bad','20261017')
    assert not (tmp_path/'bad/normalized-20261017.delivery.json').exists()


def test_existing_import_cannot_be_replaced_or_adopt_conflicting_bytes(source,tmp_path):
    delivery.seal_daily(source,'20261017',now_ms=NOW);dest=tmp_path/'research';dest.mkdir()
    p=dest/'normalized-20261017.jsonl';p.write_bytes(b'foreign\n')
    with pytest.raises(ValueError,match='CONFLICT'):delivery.import_snapshot(source/'exports',dest,'20261017')
    assert p.read_bytes()==b'foreign\n'


def test_partial_export_without_original_receipt_is_not_recreated(source):
    delivery.seal_daily(source,'20261017',now_ms=NOW)
    (source/'exports/normalized-20261017.delivery.json').unlink()
    (source/'exports/normalized-20261017.receipt.json').unlink()
    with pytest.raises(ValueError,match='PARTIAL'):delivery.seal_daily(source,'20261017',now_ms=NOW)


def test_wrong_date_or_symlink_does_not_write(source,tmp_path):
    with pytest.raises(ValueError):delivery.seal_daily(source,'20261016',now_ms=NOW)
    alias=tmp_path/'alias';alias.symlink_to(source,target_is_directory=True)
    with pytest.raises(ValueError):delivery.seal_daily(alias,'20261017',now_ms=NOW)


def test_restart_finishes_sidecars_from_existing_export_without_new_export(source,monkeypatch):
    delivery.seal_daily(source,'20261017',now_ms=NOW)
    (source/'exports/normalized-20261017.delivery.json').unlink()
    monkeypatch.setattr(delivery,'export',lambda *a:pytest.fail('must not export source again'))
    out=delivery.seal_daily(source,'20261017',now_ms=NOW)
    assert out['event_count']==2


def test_normalized_stream_is_copied_without_loading_entire_file(source,tmp_path,monkeypatch):
    delivery.seal_daily(source,'20261017',now_ms=NOW)
    original=Path.read_bytes
    def guarded(path):
        if path.suffix=='.jsonl':pytest.fail('normalized file must stream')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    result=delivery.import_snapshot(source/'exports',tmp_path/'streamed','20261017')
    assert result['event_count']==2


def test_default_cli_has_no_side_effects(monkeypatch,capsys):
    from scripts import run_liq_research_delivery_v1 as cli
    monkeypatch.setattr(cli,'seal_daily',lambda *a,**k:pytest.fail('default must not seal'))
    assert cli.main([])==0 and 'NO_NETWORK_DATA_ONLY' in capsys.readouterr().out
