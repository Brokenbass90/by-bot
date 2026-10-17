import json
from pathlib import Path
import pytest
from research_lab import kity_batch_service_v1 as service
from research_lab.kity_batch_ws_v1 import GO_PREFIX


def test_default_entrypoint_is_offline_no_service_or_credentials(capsys):
    assert service.main([])==0
    assert 'KITY_BATCH_PREPARATION_ONLY_NO_NETWORK' in capsys.readouterr().out


@pytest.mark.parametrize('kind',['GO','GO_POST_GO','GO_BOUNDED','PREPARE_POST_GO'])
def test_legacy_commands_cannot_reach_new_batch_service(kind):
    with pytest.raises(ValueError):service.validate_control(dict(kind=kind))


def test_batch_money_go_requires_new_literal_and_valid_clock():
    cmd=dict(kind='GO_BATCH',batch_policy_id='a'*64,exact_go=GO_PREFIX+'a'*64,issued_ms=2000)
    assert service.validate_control(cmd)==cmd
    for change in ({'exact_go':'GO KITY_EXECUTION_MICRO_POLICY_V1 '+'a'*64},{'issued_ms':True},
                   {'price':'2'},{'batch_policy_id':'bad'}):
        with pytest.raises(ValueError):service.validate_control(dict(cmd,**change))


def test_orders_off_service_refuses_go_before_capture_selection_or_journal(tmp_path):
    s=service.BatchSupervisor.__new__(service.BatchSupervisor);s.config={'money_go':False};s.root=tmp_path
    s.journal=None
    with pytest.raises(ValueError,match='ORDERS_OFF'):
        s.control(dict(kind='GO_BATCH',batch_policy_id='a'*64,exact_go=GO_PREFIX+'a'*64,issued_ms=2000))
    assert not list(tmp_path.iterdir())


def test_disabled_prepare_only_reads_sources_without_a_policy_or_real_intent(tmp_path):
    s=service.BatchSupervisor.__new__(service.BatchSupervisor);s.root=tmp_path;s.config={'money_go':False}
    s.check=lambda:None;s.inbox=type('I',(),{'_auth':True,'_sub':True})()
    calls=[]
    def fresh(path):
        calls.append(path)
        return dict(current_basket_gross_usdt='206',plan={'blocked_reasons':[]},
                    common_clock_at_capture={'status':'OBSERVED_COMMON_2S_PASS'}),{}
    s.fresh=fresh
    r=s.control({'kind':'PREPARE_BATCH'})
    assert calls==[tmp_path/'readiness'] and r['status']=='KITY_BATCH_WS_BOUND_ORDERS_OFF'
    assert r['policy_created'] is False and r['actual_intents_created']==0 and not list(tmp_path.iterdir())


def test_missing_selection_with_wire_or_experiment_history_blocks_no_repair(tmp_path):
    s=service.BatchSupervisor.__new__(service.BatchSupervisor);s.root=tmp_path
    (tmp_path/'wire').mkdir();(tmp_path/'wire'/'send-x.json').write_text('immutable')
    with pytest.raises(ValueError,match='MISSING_BATCH_SELECTION'):s.unselected_history()
    assert (tmp_path/'wire'/'send-x.json').read_text()=='immutable'


def test_disabled_binding_cannot_inherit_old_namespace_or_70s_scope(tmp_path):
    cfg=dict(operation_scope='KITY_BATCH_WS_V1',default_orders_off=True,money_go=False,
        entry_dispatch_window_ms=60000,runtime_root=str(tmp_path/'batch-ws-20261017'),custody_runtime_root=str(tmp_path))
    service.validate_config(cfg)
    for change in ({'runtime_root':str(tmp_path/'post-go-closeout2-20261016')},
        {'entry_dispatch_window_ms':70000},{'default_orders_off':False},{'operation_scope':'ONE_CLOSEOUT2_MICRO_2026_10_16'}):
        with pytest.raises(ValueError):service.validate_config(dict(cfg,**change))


def test_human_cli_is_required_for_money_control_even_when_loading_valid_config(tmp_path):
    cfg=tmp_path/'config.json';cfg.write_text('{}')
    import hashlib
    with pytest.raises(ValueError,match='PERSONAL_OWNER_COMMAND'):
        service.main(['--config',str(cfg),'--config-sha256',hashlib.sha256(cfg.read_bytes()).hexdigest(),
          '--command',json.dumps(dict(kind='GO_BATCH',batch_policy_id='a'*64,exact_go=GO_PREFIX+'a'*64,issued_ms=2000))])


def test_future_enabled_policy_capture_failure_is_spent_once_no_retry(tmp_path,monkeypatch):
    from research_lab import kity_batch_ws_v1 as batch
    from research_lab.kity_micro_physical_owner_v1 import publish
    from test_kity_micro_post_go_pricing_v1 import policy
    p=batch.make_batch_policy(policy());identifier=p['batch_policy_id']
    s=service.BatchSupervisor.__new__(service.BatchSupervisor);s.root=tmp_path;s.journal=None
    s.config=dict(money_go=True,_config_sha256=p['base_policy']['physical_config_sha256'])
    s.custody_root=tmp_path;s.check=lambda:None
    monkeypatch.setattr(service,'now_ms',lambda:5000001)
    monkeypatch.setattr(service.bo,'read_predecessor',lambda _:None)
    monkeypatch.setattr(service,'rows',lambda *a:[]);s.reader=None
    publish(tmp_path/'policies'/(identifier+'.json'),p);calls=[]
    def fail(store):
        assert (tmp_path/'selected-batch.json').exists()
        assert (store/'batch-policy-claim.json').exists()
        calls.append(1);raise ValueError('SOURCE_UNKNOWN')
    s.fresh=fail
    cmd=dict(kind='GO_BATCH',batch_policy_id=identifier,exact_go=GO_PREFIX+identifier,issued_ms=4999800)
    with pytest.raises(ValueError,match='SOURCE_UNKNOWN'):s.control(cmd)
    with pytest.raises(ValueError,match='ALREADY_SELECTED'):s.control(cmd)
    assert calls==[1] and (s.store(identifier)/'batch-no-send.json').exists()


def test_owned_runtime_keeps_private_ping_without_creating_entry(tmp_path,monkeypatch):
    s=service.BatchSupervisor.__new__(service.BatchSupervisor);s.last_ping_ms=1;s.feed=type('F',(),{'socket':object()})()
    calls=[];s.ping_stream=lambda:calls.append('ping')
    s.runtime=type('R',(),{'tick':lambda _:calls.append('owned_maintenance')})()
    monkeypatch.setattr(service,'now_ms',lambda:16000)
    s.cycle();assert calls==['ping','owned_maintenance']
