"""Guarded unattended execution, with no real cohort outcome consumption."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/ets2m_unattended_verdict.py'

def api():
    assert SCRIPT.is_file(), 'guarded evaluator launcher missing'
    s=importlib.util.spec_from_file_location('ets_guard',SCRIPT);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def fixture(tmp_path):
    source=tmp_path/'source';source.mkdir();p=source/'research_lab/data/yadro/ETS2M';p.mkdir(parents=True)
    epoch={'epoha':'ETS2M','hesh_yadra':'a'*16,'hesh_strategii':'b'*16,'hesh_konfiga':'c'*16}
    (p/'epoha.json').write_text(json.dumps(epoch))
    entries=[{'id':str(i),'ts':i,'sym':'S','epoha':'ETS2M','hesh_strategii':'b'*16,'hesh_konfiga':'c'*16} for i in range(900)]
    (p/'vhody.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in entries))
    (source/'guarded.py').write_text('print("not executed")')
    m=api();manifest={'schema_id':'ets2m_unattended_v1','source_root':str(source),'due_utc':'2026-10-10T19:00:00Z','pins':{'guarded.py':m.sha((source/'guarded.py').read_bytes()),'research_lab/data/yadro/ETS2M/epoha.json':m.sha((p/'epoha.json').read_bytes())},'cohort_sha256':m.sha(m.canonical(entries))}
    return m,manifest,p


def test_not_due_does_not_read_outcomes_or_create_receipt(tmp_path):
    m,manifest,p=fixture(tmp_path)
    assert m.evaluate(manifest,tmp_path/'runtime',now_ms=m.DUE_MS-1)['status']=='NOT_DUE'
    assert not (tmp_path/'runtime').exists()


def test_changed_frozen_source_blocks_before_outcome_read(tmp_path):
    m,manifest,p=fixture(tmp_path);(Path(manifest['source_root'])/'guarded.py').write_text('changed')
    with pytest.raises(ValueError,match='SOURCE_PIN'):
        m.verify_inputs(manifest)


def test_appended_future_entries_do_not_change_frozen_cohort(tmp_path):
    m,manifest,p=fixture(tmp_path)
    with (p/'vhody.jsonl').open('a') as f:f.write(json.dumps({'id':'later','ts':9999,'sym':'S'})+'\n')
    assert len(m.verify_inputs(manifest)[1])==900


def test_replacement_of_first900_is_blocked(tmp_path):
    m,manifest,p=fixture(tmp_path);rows=(p/'vhody.jsonl').read_text().splitlines();v=json.loads(rows[0]);v['id']='replacement';rows[0]=json.dumps(v);(p/'vhody.jsonl').write_text('\n'.join(rows)+'\n')
    with pytest.raises(ValueError,match='COHORT_PIN'):m.verify_inputs(manifest)


def test_torn_input_is_not_silently_skipped(tmp_path):
    m,manifest,p=fixture(tmp_path)
    with (p/'vhody.jsonl').open('a') as f:f.write('{torn')
    with pytest.raises(ValueError,match='JSONL'):m.verify_inputs(manifest)


def test_conflicting_outcome_ids_are_rejected_without_last_writer_wins(tmp_path):
    m=api();p=tmp_path/'events.jsonl';p.write_text('{"id":"a","dvigatel":"WIDE","R":1}\n{"id":"a","dvigatel":"WIDE","R":2}\n')
    with pytest.raises(ValueError,match='CONFLICTING_RECORD'):m.read_rows(p,('id','dvigatel'))


def test_identical_outcome_duplicates_are_deduplicated(tmp_path):
    m=api();p=tmp_path/'events.jsonl';p.write_text('{"id":"a","R":1}\n'*2)
    assert m.read_rows(p,('id',))==[{'id':'a','R':1}]


def complete_fixture(tmp_path):
    m,manifest,p=fixture(tmp_path);root=Path(manifest['source_root']);original=SCRIPT.parents[1]/'tests/fixtures'
    for name,file in [('yadro.py','ets2m_yadro_pure.py'),('vnutri.py','ets2m_vnutri_pure.py')]:
        target=root/'research_lab'/name;target.write_bytes((original/file).read_bytes());manifest['pins']['research_lab/'+name]=m.sha(target.read_bytes())
    epoch=json.loads((p/'epoha.json').read_bytes());epoch['nachalo_ms']=0;(p/'epoha.json').write_text(json.dumps(epoch));manifest['pins']['research_lab/data/yadro/ETS2M/epoha.json']=m.sha((p/'epoha.json').read_bytes())
    rows=m.read_rows(p/'vhody.jsonl',('id',))
    for i,r in enumerate(rows):r.update(sym='S'+str(i%6),side='short',stop_dolya=0.04,k1=0.25)
    (p/'vhody.jsonl').write_bytes(b''.join(m.canonical(r)+b'\n' for r in rows));manifest['cohort_sha256']=m.sha(m.canonical(rows))
    isp=[{'id':r['id'],'ispolnen':True} for r in rows]
    ish=[{'id':r['id'],'dvigatel':engine,'R':value} for r in rows for engine,value in [('CONTROL',-0.1),('24H',0.2),('WIDE',0.1)]]
    source=[{'sym':r['sym'],'ts':r['ts'],'side':'short','stop_dolya':0.04,'rr1':0.25,'R':-0.1} for r in rows]
    for path,data in [(p/'ispolnenie.jsonl',isp),(p/'ishody.jsonl',ish),(root/'research_lab/data/ten_ETS2S.jsonl',source)]:path.write_bytes(b''.join(m.canonical(r)+b'\n' for r in data))
    return m,manifest,p


def test_exact_frozen_evaluator_runs_isolated_with_no_source_writes(tmp_path):
    m,manifest,p=complete_fixture(tmp_path);root=Path(manifest['source_root'])
    before={str(f.relative_to(root)):m.sha(f.read_bytes()) for f in root.rglob('*') if f.is_file()}
    result=m.evaluate(manifest,tmp_path/'runtime',now_ms=m.DUE_MS)
    assert result['status']=='EVALUATED_RESEARCH_ONLY'
    assert 'ПАРИТЕТ ИСТОЧНИКА ЕСТЬ' in result['evaluator_stdout']
    assert result['money_ready'] is False and result['strategy_pass_inferred_from_exit_code'] is False
    after={str(f.relative_to(root)):m.sha(f.read_bytes()) for f in root.rglob('*') if f.is_file()}
    assert after==before


def test_missing_slow_terminal_stays_blocked_instead_of_selecting_fast_winners(tmp_path):
    m,manifest,p=complete_fixture(tmp_path);path=p/'ishody.jsonl';lines=path.read_bytes().splitlines(keepends=True);path.write_bytes(b''.join(lines[:-1]))
    result=m.evaluate(manifest,tmp_path/'runtime',now_ms=m.DUE_MS)
    assert result['status']=='BLOCKED_DATA' and result['evaluator_returncode']==2
    assert 'NOT_MEASURED' in result['evaluator_stdout']
    assert 'сумма R' not in result['evaluator_stdout']


def test_source_parity_failure_blocks_branch_metrics(tmp_path):
    m,manifest,p=complete_fixture(tmp_path);path=p.parent.parent/'ten_ETS2S.jsonl';rows=m.read_rows(path,None);rows[0]['side']='long';path.write_bytes(b''.join(m.canonical(r)+b'\n' for r in rows))
    result=m.evaluate(manifest,tmp_path/'runtime',now_ms=m.DUE_MS)
    assert result['status']=='BLOCKED_DATA'
    assert 'ПАРИТЕТА НЕТ' in result['evaluator_stdout']
    assert 'ОЦЕНКА ЭПОХИ' not in result['evaluator_stdout']


def test_conflicting_eligible_source_duplicate_cannot_reach_branch_evaluation(tmp_path):
    m,manifest,p=complete_fixture(tmp_path);path=p.parent.parent/'ten_ETS2S.jsonl'
    duplicate=m.read_rows(path,None)[0];duplicate['R']=999
    with path.open('ab') as f:f.write(m.canonical(duplicate)+b'\n')
    with pytest.raises(ValueError,match='CONFLICTING_SOURCE_RECORD'):
        m.evaluate(manifest,tmp_path/'runtime',now_ms=m.DUE_MS)
