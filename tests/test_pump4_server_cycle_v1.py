"""Server DATA-only path and existing financial-owner adapter integration."""
import copy,hashlib,json
from pathlib import Path
import pytest
from test_pump4_bybit_sources_v1 import klines,NOW
from test_pump4_account_owner_v1 import create,inputs,FP
from research_lab.pump4_bybit_sources_v1 import closed_h1,universe


def archive(tmp_path):
    root=tmp_path/'source';(root/'symbols').mkdir(parents=True)
    caps=klines();s=closed_h1(caps,'ZROUSDT',next_open_ms=NOW,observed_ms=NOW+2)
    for symbol in universe():
        row=dict(symbol=symbol,status='UNAVAILABLE_INSTRUMENT',captures=[])
        if symbol=='ZROUSDT':row=dict(symbol=symbol,status='READY_H1_BOOTSTRAP_NOT_ENTRY',captures=caps,source=s)
        (root/'symbols'/(symbol+'.json')).write_text(json.dumps(row))
    seal=dict(source_hour_open_ms=NOW,source_capture_files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.json')})
    (root/'receipt.json').write_text(json.dumps(seal));return root


def test_real_source_path_restarts_without_reseeding_or_crediting_bootstrap(tmp_path):
    from research_lab.pump4_server_cycle_v1 import analyze
    (tmp_path/'owner-fixture').mkdir()
    s=create(tmp_path/'owner-fixture');o,e,t,c,f,l=s
    try:
        x,p=inputs(e,now=t[0]);src=archive(tmp_path)
        a=analyze(tmp_path/'data',src,x,p,o.scope['policy'],fingerprint=FP,now_ms=t[0],physical=dict(owner_active=True,lock_held=True))
        before=(tmp_path/'data/ZROUSDT.jsonl').read_bytes()
        b=analyze(tmp_path/'data',src,x,p,o.scope['policy'],fingerprint=FP,now_ms=t[0],physical=dict(owner_active=True,lock_held=True))
        assert a['source_intake_pass']==b['source_intake_pass']==1
        assert b['duplicate_decisions']==1 and (tmp_path/'data/ZROUSDT.jsonl').read_bytes()==before
        assert b['physical_owner_status']=='EXISTING_OWNER_BUSY_NO_SECOND_WRITER'
        assert b['prospective_decisions_credited']==b['broker_writes']==0
        assert e.state['calls']==0
    finally:l.close()


def test_changed_raw_source_is_rejected_before_intake(tmp_path):
    from research_lab.pump4_server_cycle_v1 import analyze
    (tmp_path/'owner-fixture').mkdir()
    s=create(tmp_path/'owner-fixture');o,e,t,c,f,l=s
    try:
        x,p=inputs(e,now=t[0]);src=archive(tmp_path)
        with (src/'symbols/ZROUSDT.json').open('a') as out:out.write(' ')
        with pytest.raises(ValueError,match='ARCHIVE_HASH'):analyze(tmp_path/'data',src,x,p,o.scope['policy'],fingerprint=FP,now_ms=t[0],physical={})
        assert not (tmp_path/'data').exists()
    finally:l.close()


def test_same_runner_calls_existing_owner_for_entire_memory_cycle(tmp_path):
    from research_lab.pump4_server_cycle_v1 import owner_cycle
    s=create(tmp_path);o,e,t,c,f,l=s
    try:
        for price,role in [('100','ENTRY'),('97.8','TP1'),('95.7','TP2')]:
            x,p=inputs(e,now=t[0],price=price)
            assert owner_cycle(o,f.config['plan'],x,p,apply=True)['role']==role
            t[0]+=1000
        x,p=inputs(e,now=t[0],price='95.7')
        assert owner_cycle(o,f.config['plan'],x,p,apply=True)['status']=='FLAT_COSTS_PENDING'
        assert len(e.state['submitted_links'])==3
    finally:l.close()


def test_server_cli_default_has_no_account_or_public_requests(monkeypatch,capsys):
    from scripts import run_pump4_orders_off_v1 as cli
    def forbidden(*a,**k):raise AssertionError('NO_REQUESTS_EXPECTED')
    monkeypatch.setattr(cli,'capture',forbidden);monkeypatch.setattr(cli,'load_bound_credentials',forbidden)
    assert cli.main([])==0
    assert json.loads(capsys.readouterr().out)['status']=='ORDERS_OFF_NO_REQUESTS'


def test_server_cli_has_no_dispatch_or_go_mode():
    from scripts import run_pump4_orders_off_v1 as cli
    with pytest.raises(SystemExit) as exc:cli.main(['--dispatch'])
    assert exc.value.code==2


def test_resealed_changed_seed_history_cannot_reuse_old_decision_lineage(tmp_path):
    from research_lab.pump4_server_cycle_v1 import analyze
    (tmp_path/'fixture').mkdir()
    s=create(tmp_path/'fixture')
    o,e,t,c,f,l=s
    try:
        x,p=inputs(e,now=t[0]);src=archive(tmp_path)
        args=dict(fingerprint=FP,now_ms=t[0],physical={})
        analyze(tmp_path/'data',src,x,p,o.scope['policy'],**args)
        z=src/'symbols/ZROUSDT.json';r=json.loads(z.read_bytes());cap=r['captures'][0]
        cap['body']['result']['list'][-1][5]='999'
        cap['raw']=json.dumps(cap['body']);cap['raw_sha256']=hashlib.sha256(cap['raw'].encode()).hexdigest()
        r['source']=closed_h1(r['captures'],'ZROUSDT',next_open_ms=NOW,observed_ms=NOW+2)
        z.write_text(json.dumps(r));seal=json.loads((src/'receipt.json').read_bytes());seal['source_capture_files']['symbols/ZROUSDT.json']=hashlib.sha256(z.read_bytes()).hexdigest();(src/'receipt.json').write_text(json.dumps(seal))
        with pytest.raises(ValueError,match='SOURCE_HISTORY_CONFLICT'):analyze(tmp_path/'data',src,x,p,o.scope['policy'],**args)
    finally:l.close()
