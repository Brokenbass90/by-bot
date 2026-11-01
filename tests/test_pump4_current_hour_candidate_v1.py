"""Opt-in bounded current-hour index; same frozen replay and no real account I/O."""
import copy
import json
from pathlib import Path

import pytest

from research_lab import pump4_runtime_sources_v1 as R
from research_lab.alpaca_dynamic_v1 import digest
from test_pump4_runtime_sources_v1 import bound_candidate
from test_pump4_account_owner_v1 import create
from research_lab.pump4_bybit_sources_v1 import H


def index_case(tmp_path, *, signal=True):
    config, candidate, wire, journal = bound_candidate(tmp_path)
    config['candidate_source'] = 'CURRENT_H1_PUBLICATIONS_V1'
    root = Path(config['data_source']['root'])
    oldpath = next((root/'observations').glob('*.json'))
    row = json.loads(oldpath.read_bytes())
    row['schema'] = 'PUMP4_DATA_DECISION_OBSERVATION_V1'
    row['status'] = 'STREAM_SIGNAL_REQUIRES_FRESH_HTTPS'
    if not signal:
        row['decision']['signal'] = None
        core = {k: row['decision'][k] for k in ('domain_schema','symbol','bar_open_ms','history_sha256','source_pins','signal')}
        row['decision']['decision_id'] = 'pump4-'+digest(core)
        row['status'] = 'NO_SIGNAL'
    obs = root/'observations'/(row['decision']['decision_id']+'.json')
    obs.write_text(json.dumps(row))
    hour = row['decision']['bar_open_ms']+H
    folder = root/'ws-hours'/str(hour)/'published'
    folder.mkdir(parents=True)
    pub = dict(symbol=row['decision']['symbol'],status='CLOSED_H1_INTAKE_PASS',mode='CURRENT_CLOSED_BAR',
        cursor_ms=row['decision']['bar_open_ms'],accepted_bars=1,decisions=[row],
        publication_completed_ms=row['decision']['first_observed_ms'],
        pair_received_ms=row['decision']['available_ms'],
        source_kind='CONFIRMED_WS_WITH_FROZEN_JOURNAL_PREFIX',
        broker_writes=0,orders_allowed=False,money_authority=False)
    target = folder/(row['decision']['symbol']+'.json')
    target.write_text(json.dumps(pub))
    return config,candidate,wire,root,obs,target,pub


def test_current_signal_survives_20000_archived_observations_without_archive_scan(tmp_path, monkeypatch):
    owner, exchange, tick, _, _, lease = create(tmp_path)
    try:
        config,candidate,wire,root,obs,target,pub = index_case(tmp_path/'data')
        for i in range(20001):
            (root/'observations'/f'archive-{i}.json').touch()
        original_glob = Path.glob
        def bounded_glob(path, pattern):
            if path == root/'observations':
                pytest.fail('current-hour reader scanned the growing archive')
            return original_glob(path, pattern)
        monkeypatch.setattr(Path,'glob',bounded_glob)
        provider = R.TrustedSources(config,owner,wire=wire,clock=lambda:tick[0])
        got = provider.candidate()
        assert got['decision_id'] == candidate['decision_id']
        assert provider.candidate() is None and exchange.state['calls']==0
        assert (root/'observations/archive-20000.json').exists()
    finally:
        lease.close()


def test_missing_current_index_cannot_fall_back_to_archived_positive(tmp_path):
    owner, exchange, tick, _, _, lease = create(tmp_path)
    try:
        config,_,wire,root,obs,target,pub = index_case(tmp_path/'data')
        target.unlink()
        assert R.TrustedSources(config,owner,wire=wire,clock=lambda:tick[0]).candidate() is None
        assert obs.exists() and exchange.state['calls']==0
    finally:lease.close()


@pytest.mark.parametrize('fault',['wrong_symbol','wrong_hour','future_time','mode','source_kind','decision_hash','observation_conflict','symlink','too_many'])
def test_invalid_current_publication_fails_closed_before_http(tmp_path,fault):
    owner, exchange, tick, _, _, lease = create(tmp_path)
    try:
        config,_,wire,root,obs,target,pub = index_case(tmp_path/'data')
        if fault=='wrong_symbol':pub['symbol']='BTCUSDT'
        elif fault=='wrong_hour':pub['decisions'][0]['decision']['bar_open_ms']-=H
        elif fault=='future_time':pub['publication_completed_ms']=tick[0]+1
        elif fault=='mode':pub['mode']='RECOVERY_REPLAY'
        elif fault=='source_kind':pub['source_kind']='CALLER_PROVIDED'
        elif fault=='decision_hash':pub['decisions'][0]['decision']['decision_id']='pump4-'+'0'*64
        elif fault=='observation_conflict':pub['decisions'][0]['archive_id']='conflict'
        elif fault=='too_many':
            for i in range(138):(target.parent/f'INVALID{i}USDT.json').write_text('{}')
        if fault=='symlink':
            target.unlink();target.symlink_to(obs)
        else:target.write_text(json.dumps(pub))
        with pytest.raises(ValueError):
            R.TrustedSources(config,owner,wire=lambda *a:pytest.fail('HTTP before source verification'),clock=lambda:tick[0]).candidate()
        assert exchange.state['calls']==0
    finally:lease.close()


def test_outside_entry_window_does_not_read_archive_or_send_http(tmp_path,monkeypatch):
    owner, exchange, tick, _, _, lease = create(tmp_path)
    try:
        config,_,wire,root,obs,target,pub = index_case(tmp_path/'data')
        tick[0]+=60001
        monkeypatch.setattr(Path,'glob',lambda *a:pytest.fail('outside-window directory scan'))
        assert R.TrustedSources(config,owner,wire=lambda *a:pytest.fail('late HTTP'),clock=lambda:tick[0]).candidate() is None
    finally:lease.close()


def test_negative_current_publication_is_not_a_trade_opportunity(tmp_path):
    owner, exchange, tick, _, _, lease = create(tmp_path)
    try:
        config,_,wire,root,obs,target,pub = index_case(tmp_path/'data',signal=False)
        assert R.TrustedSources(config,owner,wire=lambda *a:pytest.fail('no-signal HTTP'),clock=lambda:tick[0]).candidate() is None
        assert exchange.state['calls']==0
    finally:lease.close()

@pytest.mark.parametrize('during_http',[False,True])
def test_publication_change_after_read_blocks_candidate(tmp_path,monkeypatch,during_http):
    owner,exchange,tick,_,_,lease=create(tmp_path)
    try:
        config,_,wire,root,obs,target,pub=index_case(tmp_path/'data')
        changed=[False]
        def change():
            if not changed[0]:
                changed[0]=True
                other=copy.deepcopy(pub);other['mode']='RECOVERY_REPLAY'
                target.write_text(json.dumps(other))
        if during_http:
            def altered_wire(*args):change();return wire(*args)
        else:
            original=R.observation_bytes
            def altered_read(path):
                result=original(path)
                if path==obs:change()
                return result
            monkeypatch.setattr(R,'observation_bytes',altered_read)
            altered_wire=wire
        with pytest.raises(ValueError,match='CURRENT_.*CHANGED'):
            R.TrustedSources(config,owner,wire=altered_wire,clock=lambda:tick[0]).candidate()
        assert changed[0] and exchange.state['calls']==0
    finally:lease.close()


def test_selected_off_supervisor_uses_current_index_and_original_account_lease(tmp_path,monkeypatch):
    from test_pump4_execution_supervisor_v1 import setup
    from test_pump4_runtime_sources_v1 import wire_fixture
    from research_lab import pump4_execution_supervisor_v1 as supervisor
    from research_lab.kity_micro_physical_owner_v1 import AccountLease
    import hashlib,urllib.parse
    runner,state,path,pin,config,scope,called=setup(tmp_path,monkeypatch)
    source_config,_,public_wire,root,obs,target,pub=index_case(tmp_path/'data')
    config.update(candidate_source=source_config['candidate_source'],data_source=source_config['data_source'])
    scope['runner_config_sha256']=runner.config_sha(config)
    scope_path=Path(config['authority']['path']);scope_path.write_text(json.dumps(scope))
    config['authority']['sha256']=hashlib.sha256(scope_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(config));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    private_wire,calls=wire_fixture(state[1],state[2][0])
    def wire(method,url,headers,data,timeout):
        if urllib.parse.urlsplit(url).path=='/v5/market/kline':return public_wire(method,url,headers,data,timeout)
        return private_wire(method,url,headers,data,timeout)
    def factory(config,owner):
        owner.lease.assert_held()
        with pytest.raises(BlockingIOError):AccountLease(state[-1].path)
        return R.TrustedSources(config,owner,wire=wire,clock=lambda:state[2][0])
    out=supervisor.run(path,pin,orders_off=True,once=True,source_factory=factory,clock=lambda:state[2][0])
    assert out[0]['result']['status']=='ACTION_RESERVED_ORDERS_OFF' and out[0]['result']['role']=='ENTRY'
    assert out[0]['broker_writes']==0 and state[1].state['calls']==0
    second=supervisor.run(path,pin,orders_off=True,once=True,source_factory=factory,clock=lambda:state[2][0])
    assert second[0]['result']['status']=='RECONCILE_ONLY' and state[1].state['calls']==0
