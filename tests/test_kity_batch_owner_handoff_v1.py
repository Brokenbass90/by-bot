import json
import pytest
from scripts import kity_batch_owner_handoff_v1 as handoff


def test_default_never_reads_a_manifest_or_mutates(capsys,monkeypatch):
    monkeypatch.setattr(handoff,'load',lambda *a:pytest.fail('default read'))
    assert handoff.main([])==0
    assert json.loads(capsys.readouterr().out)['broker_writes']==0


def test_exact_policy_and_config_changes_only():
    old=dict(money_go=False,policy_valid_until_ms=None,unit_template_sha256='old',
        app_root='/app',runtime_root='/runtime',entry_dispatch_window_ms=60000)
    new=dict(old,money_go=True,policy_valid_until_ms=10000,unit_template_sha256='new')
    handoff.config_delta(old,new,10000)
    for change in ({'entry_dispatch_window_ms':70000},{'app_root':'/other'},
                   {'money_go':False},{'runtime_root':'/other'},{'extra':True}):
        with pytest.raises(ValueError):handoff.config_delta(old,dict(new,**change),10000)


@pytest.mark.parametrize('at',[1000,2000,10000])
def test_expiry_and_start_fail_closed(at):
    p=dict(created_ms=2000,valid_until_ms=10000)
    if at==2000:handoff.session(p,at)
    else:
        with pytest.raises(ValueError):handoff.session(p,at)


def test_manifest_hash_conflict_cannot_reach_execution(tmp_path):
    p=tmp_path/'m.json';p.write_text('{}')
    with pytest.raises(ValueError,match='MANIFEST_PIN'):
        handoff.main(['--manifest',str(p),'--manifest-sha256','0'*64,'--owner-execute'])


def test_rollback_refuses_any_possible_go_or_wire_history(tmp_path):
    assert handoff.rollback_safe(tmp_path) is True
    (tmp_path/'go-may-have-been-queued.json').write_text('{}')
    assert handoff.rollback_safe(tmp_path) is False
    (tmp_path/'go-may-have-been-queued.json').unlink()
    (tmp_path/'wire').mkdir();(tmp_path/'wire'/'send-x.json').write_text('{}')
    assert handoff.rollback_safe(tmp_path) is False


def test_personal_command_resolves_pinned_app_from_an_unrelated_cwd(tmp_path,monkeypatch):
    # A synthetic module, no account/config loader, writer or exchange calls.
    app=tmp_path/'pinned-app';pkg=app/'research_lab';pkg.mkdir(parents=True)
    (pkg/'__init__.py').write_text('')
    (pkg/'kity_batch_service_v1.py').write_text('import json;print(json.dumps(dict(status="FIXTURE_NO_NETWORK")))')
    c=tmp_path/'config.json';c.write_text('{}')
    monkeypatch.chdir(tmp_path)
    result=handoff.queue_command({'app_root':str(app)},dict(new_config=str(c),policy_id='a'*64))
    assert json.loads(result)['status']=='FIXTURE_NO_NETWORK'
