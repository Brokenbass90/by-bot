"""Counterexamples target source substitution, post-hoc joins and double counting."""
import hashlib,importlib,json,datetime
from pathlib import Path
import pytest
from test_polymarket_v2_snapshot_inputs_v1 import gamma,book

T=1793782800000

def module():return importlib.import_module('research_lab.polymarket_signal_cycle_v1')
def digest(b):return hashlib.sha256(b).hexdigest()
def line(x):return json.dumps(x,sort_keys=True).encode()
def fixture(tmp_path,token='11'):
 root=tmp_path/'lab';(root/'prereg').mkdir(parents=True);(root/'data/poly_signaly').mkdir(parents=True);(root/'data/poly_sport_shiroko').mkdir()
 policy='PREREG_POLY_95_V2_SHIROKO_2026_11_03';(root/'prereg'/ (policy+'.md')).write_bytes(b'frozen control policy')
 a=dict(id='123',token='11',t=T/1000,ask=.97,bid=.96,gl_ask=200,lest_ask=[[.97,200]])
 b=dict(id='123',token='22',t=T/1000,ask=.04,bid=.03,gl_ask=150,lest_ask=[[.04,200]])
 ar,br=line(a),line(b);(root/'data/poly_sport_shiroko/knigi.jsonl').write_bytes(ar+b'\n'+br+b'\n')
 market=dict(id='123',sob='dobavlen',tokeny=['11','22'],conditionId='0x'+'a'*64)
 (root/'data/poly_sport_shiroko/rynki.jsonl').write_bytes(line(market)+b'\n')
 q=a if token=='11' else b
 s=dict(schema='POLY_SIGNAL_V1',signal_observation_id=digest((policy+'|123|'+token).encode())[:24],policy=policy,policy_sha256=digest(b'frozen control policy'),market_id='123',condition_id=None,token_id=token,side='BUY',signal_ms=T+10,received_ms=T,source='poly_sport_shiroko/knigi.jsonl',source_sha256=digest(ar+b'\n'+(br if token=='22' else b'')),quote=dict(ask=q['ask'],bid=q['bid'],ask_depth_usd=q['gl_ask'],ask_ladder=q['lest_ask']),price_limit=.985,stake_model_usd=97,fee_model=.0015,p_model=None,status='SHADOW',finance_allowed=False,prev_sha256='0'*64)
 journal=root/'data/poly_signaly/POLY_95_V2_SHIROKO.jsonl';journal.write_bytes(line(s)+b'\n')
 return root,journal,s

def transport(now,terminal=False,status='resolved',condition='0x'+'a'*64):
 def get(url):
  if '/resolutions?' in url:
   obj=dict(data=[dict(condition_id=condition,status=status,resolved_at=datetime.datetime.fromtimestamp((T+100000)/1000,datetime.timezone.utc).isoformat(),payouts=[1,0])]) if terminal else dict(data=[])
   raw=json.dumps(obj);return dict(method='GET',url=url,http_status=200,request_ms=now[0]-1,received_ms=now[0],raw_text=raw,raw_sha256=digest(raw.encode()))
  c=gamma() if '/markets/' in url else book(url.rsplit('=',1)[1]);c.update(request_ms=now[0]-2,received_ms=now[0]-1)
  obj=json.loads(c['raw_text']);obj['closed']=False
  if 'timestamp' in obj:obj.update(timestamp=str(now[0]-1),asks=[dict(price='.97',size='200')])
  raw=json.dumps(obj);c.update(raw_text=raw,raw_sha256=digest(raw.encode()));return c
 return get

def setup(tmp_path,monkeypatch,token='11'):
 m=module();root,j,s=fixture(tmp_path,token);now=[T+100]
 monkeypatch.setattr(m,'now_ms',lambda:now[0]);monkeypatch.setattr(m.snap.time,'time_ns',lambda:now[0]*1000000);monkeypatch.setattr(m.snap,'get_capture',transport(now))
 return m,root,j,s,now,tmp_path/'state'

def run(m,r,j,state):return m.cycle_once(r,j.name,state)

def test_real_source_pair_preserves_id_budget_and_no_orders(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);out=run(m,r,j,state)
 assert out['measured']==1 and out['joined']==0
 p=state/'signals'/s['signal_observation_id'];rec=json.loads((p/'capture/sample-0/measurement.json').read_bytes())
 selected=next(x['measurement'] for x in rec['outcomes'] if x['supplied_signal'])
 assert selected['model_gross']=='97' and selected['estimated_win_net']=='2.85450'
 assert rec['signal_observation_id']==s['signal_observation_id'] and rec['order_posts']==rec['independent_opportunities']==0
 assert json.loads((p/'intake.json').read_bytes())['before_sports_final_proven'] is False
 assert run(m,r,j,state)['measured']==0

@pytest.mark.parametrize('field,value,reason',[('source','../../configs/secret.env','SOURCE_PATH'),('source_sha256','b'*64,'SOURCE_PROVENANCE'),('policy_sha256','b'*64,'POLICY_DRIFT'),('token_id','99','SIGNAL_IDENTITY'),('received_ms',T+200,'SIGNAL_TIME')])
def test_untrusted_source_or_policy_never_reaches_network(tmp_path,monkeypatch,field,value,reason):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);s[field]=value;j.write_bytes(line(s)+b'\n')
 monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('unqualified signal attempted GET'))
 out=run(m,r,j,state);assert out['blocked']==1 and reason in out['issues'][0]

def test_partial_tail_preserved_and_observed_history_rewrite_blocks(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);original=j.read_bytes();j.write_bytes(original+b'{"partial":')
 assert run(m,r,j,state)['measured']==1 and j.read_bytes()==original+b'{"partial":'
 s['quote']['ask']=.98;j.write_bytes(line(s)+b'\n')
 with pytest.raises(ValueError,match='WITNESSED_PREFIX'):run(m,r,j,state)

def test_stale_signal_not_replayed_at_current_price(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);n[0]=T+121000
 monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('late replay'))
 out=run(m,r,j,state);assert out['blocked']==1 and 'STALE_SIGNAL' in out['issues'][0]

def test_real_token_b_source_not_synthetic_complement(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch,'22');out=run(m,r,j,state)
 assert out['measured']==1
 saved=json.loads((state/'signals'/s['signal_observation_id']/'intake.json').read_bytes())
 assert saved['signal']['model_price']==.04


def test_resolution_future_official_join_is_idempotent_and_preserves_measurement(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);run(m,r,j,state);p=state/'signals'/s['signal_observation_id'];before=(p/'measurement-manifest.json').read_bytes()
 n[0]=T+200000;monkeypatch.setattr(m.snap,'get_capture',transport(n,True));out=run(m,r,j,state)
 assert out['joined']==1 and (p/'measurement-manifest.json').read_bytes()==before
 joined=json.loads((p/'outcome.json').read_bytes());assert joined['model_net']=='2.85450' and joined['real_fill'] is False and joined['actual_net_pnl'] is None
 assert joined['signal_observation_id']==s['signal_observation_id'] and joined['e2e_sports_before_final_confirmed'] is False
 assert run(m,r,j,state)['joined']==0

@pytest.mark.parametrize('status,condition',[('proposed','0x'+'a'*64),('resolved','0x'+'b'*64)])
def test_proposal_or_wrong_condition_does_not_join(tmp_path,monkeypatch,status,condition):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);run(m,r,j,state);n[0]=T+200000
 monkeypatch.setattr(m.snap,'get_capture',transport(n,True,status,condition));out=run(m,r,j,state)
 assert out['joined']==0 and not (state/'signals'/s['signal_observation_id']/'outcome.json').exists()

def test_tampered_measurement_blocks_join(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);run(m,r,j,state);p=state/'signals'/s['signal_observation_id'];(p/'capture/sample-0/measurement.json').write_text('{}')
 n[0]=T+200000;monkeypatch.setattr(m.snap,'get_capture',transport(n,True))
 with pytest.raises(ValueError,match='MEASUREMENT_DRIFT'):run(m,r,j,state)

def test_missing_real_journal_is_waiting_not_fabricated(tmp_path):
 m=module();r=tmp_path/'lab';r.mkdir();state=tmp_path/'state';out=m.cycle_once(r,'POLY_95_V2_SHIROKO.jsonl',state)
 assert out['status']=='WAITING_REAL_SIGNAL' and out['measured']==out['joined']==0


def test_pending_outcomes_do_not_starve_behind_cooling_polls(tmp_path,monkeypatch):
 import copy
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);all_rows=[];prev='0'*64
 for i in range(6):
  x=copy.deepcopy(s);x['policy']=s['policy']+'_'+str(i);(r/'prereg'/(x['policy']+'.md')).write_bytes(b'frozen control policy')
  x['signal_observation_id']=digest((x['policy']+'|123|11').encode())[:24];x['prev_sha256']=prev
  raw=line(x);all_rows.append(raw);prev=digest(raw)
 j.write_bytes(b'\n'.join(all_rows)+b'\n')
 for _ in range(3):run(m,r,j,state)
 assert len(list((state/'signals').glob('*/polls/*.json')))==6

@pytest.mark.parametrize('payouts,when', [([1,1],T+100000),([1,0],T)])
def test_ambiguous_payout_or_resolution_before_witness_never_joins(tmp_path,monkeypatch,payouts,when):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);run(m,r,j,state);n[0]=T+200000
 original=transport(n,True)
 def get(url):
  c=original(url);obj=json.loads(c['raw_text']);obj['data'][0].update(payouts=payouts,resolved_at=datetime.datetime.fromtimestamp(when/1000,datetime.timezone.utc).isoformat())
  c['raw_text']=json.dumps(obj);c['raw_sha256']=digest(c['raw_text'].encode());return c
 monkeypatch.setattr(m.snap,'get_capture',get)
 assert run(m,r,j,state)['joined']==0
 assert not (state/'signals'/s['signal_observation_id']/'outcome.json').exists()


def test_cycle_cli_waits_for_a_real_signal_without_network(tmp_path,monkeypatch,capsys):
 m=module();r=tmp_path/'lab';r.mkdir();monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('invented signal'))
 assert m.snap.main(['--cycle-once','--research-root',str(r),'--signal-journal','POLY_95_V2_SHIROKO.jsonl','--state-root',str(tmp_path/'state')])==0
 assert 'WAITING_REAL_SIGNAL' in capsys.readouterr().out


def v3_fixture(tmp_path,monkeypatch,token=None,index=1):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);old=s['policy'];policy='PREREG_POLY_SCHET_MODEL_V3_SILA_2026_11_03';(r/'prereg'/(policy+'.md')).write_bytes(b'frozen control policy')
 s.update(policy=policy,token_id=token,outcome_index=index,source='poly_sport_shiroko+poly_ws_vps_v1/sports',stake_model_usd=None,p_model=.99,score=dict(score_received_ms=T-1000,score_on_mac_ms=T-500,gameId=123))
 s['signal_observation_id']=digest((policy+'|123|'+str(index)).encode())[:24]
 raw=(r/'data/poly_sport_shiroko/knigi.jsonl').read_bytes().splitlines()[0];s['source_sha256']=digest(raw)
 s['quote']=dict(ask=.04,bid=None,ask_depth_usd=None,ask_ladder=None,kak='synthetic complement, not executable')
 j.write_bytes(line(s)+b'\n');return m,r,j,s,n,state


def test_v3_null_token_resolves_by_official_pair_and_preserves_original_id(tmp_path,monkeypatch):
 m,r,j,s,n,state=v3_fixture(tmp_path,monkeypatch);out=run(m,r,j,state)
 assert out['measured']==1
 intake=json.loads((state/'signals'/s['signal_observation_id']/'intake.json').read_bytes())
 assert intake['signal']['token_id']=='22' and intake['signal']['signal_observation_id']==s['signal_observation_id']
 assert intake['provenance']['source_quote_is_execution_price'] is False
 assert intake['provenance']['sports_frame_provenance_verified'] is False

@pytest.mark.parametrize('token,index,scoretime', [('11',1,T-500),(None,True,T-500),(None,1,T+500)])
def test_v3_ambiguous_token_or_future_score_is_unknown(tmp_path,monkeypatch,token,index,scoretime):
 m,r,j,s,n,state=v3_fixture(tmp_path,monkeypatch,token,index);s['score']['score_on_mac_ms']=scoretime;j.write_bytes(line(s)+b'\n')
 out=run(m,r,j,state);assert out['measured']==0 and out['blocked']==1


def test_killed_after_intake_never_replays_or_disappears_silently(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch)
 monkeypatch.setattr(m.snap,'run_member',lambda *a,**k:(_ for _ in ()).throw(KeyboardInterrupt()))
 with pytest.raises(KeyboardInterrupt):run(m,r,j,state)
 monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('interrupted observation replayed'))
 out=run(m,r,j,state);assert out['status']=='UNKNOWN' and any('INTERRUPTED' in x for x in out['issues'])


def test_cycle_no_extra_args_processes_both_confirmed_journals(tmp_path,monkeypatch,capsys):
 m=module();repo=tmp_path/'repo';(repo/'research_lab').mkdir(parents=True);monkeypatch.chdir(repo)
 monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('no source signal'))
 assert m.snap.main(['--cycle-once'])==0
 result=json.loads(capsys.readouterr().out.splitlines()[-1]);assert set(result['journals'])=={'POLY_95_V2_SHIROKO.jsonl','POLY_SCHET_V3.jsonl'}
 assert result['order_posts']==0


def test_manifest_token_reversal_cannot_reverse_official_winner(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);run(m,r,j,state);p=state/'signals'/s['signal_observation_id'];f=p/'measurement-manifest.json'
 obj=json.loads(f.read_bytes());obj['tokens'].reverse();f.write_text(json.dumps(obj));n[0]=T+200000;monkeypatch.setattr(m.snap,'get_capture',transport(n,True))
 with pytest.raises(ValueError,match='MANIFEST|IDENTITY'):run(m,r,j,state)
 assert not (p/'outcome.json').exists()

@pytest.mark.parametrize('relative',['../outside','/tmp/outside','capture/../../outside'])
def test_local_evidence_cannot_escape_its_root(tmp_path,relative):
 with pytest.raises(ValueError,match='PATH_CUSTODY'):module().safe(tmp_path,relative)


def test_slow_get_invalidates_signal_at_actual_measurement_time(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);n[0]=T+119000;original=transport(n)
 def slow(url):n[0]+=1000;return original(url)
 monkeypatch.setattr(m.snap,'get_capture',slow);out=run(m,r,j,state)
 assert out['measured']==0 and out['blocked']==1


def test_selector_and_default_share_namespace_and_global_lock(tmp_path,monkeypatch):
 import fcntl,os
 m,r,j,s,n,state=setup(tmp_path,monkeypatch)
 args=['--cycle-once','--research-root',str(r),'--state-root',str(state)]
 assert m.snap.main(args+['--signal-journal',j.name])==0
 assert (state/j.stem/'signals'/s['signal_observation_id']/'measurement-manifest.json').exists()
 assert m.snap.main(args)==0
 assert len(list(state.glob('*/signals/*/measurement-manifest.json')))==1
 fd=os.open(state/'hook-consumer.lock',os.O_RDWR)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert m.snap.main(args+['--signal-journal',j.name])==0
 finally:os.close(fd)


def test_real_ten_minute_schedule_and_failed_gets_do_not_starve_pending(tmp_path,monkeypatch):
 import copy
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);rows=[];prev='0'*64
 for i in range(6):
  x=copy.deepcopy(s);x['policy']+= '_'+str(i);(r/'prereg'/(x['policy']+'.md')).write_bytes(b'frozen control policy')
  x['signal_observation_id']=digest((x['policy']+'|123|11').encode())[:24];x['prev_sha256']=prev;raw=line(x);rows.append(raw);prev=digest(raw)
 j.write_bytes(b'\n'.join(rows)+b'\n');run(m,r,j,state);run(m,r,j,state)
 attempted=set()
 def failure(url):
  attempted.add(url);raise OSError('read timeout')
 monkeypatch.setattr(m.snap,'get_capture',failure)
 for i in range(3):n[0]+=600000;run(m,r,j,state)
 assert len(list((state/'signals').glob('*/attempts/*.json')))>=6
 assert len({p.parent.parent.name for p in (state/'signals').glob('*/attempts/*.json')})==6


def test_epoch_two_uses_pinned_manifest_and_never_reads_broken_e1(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);epoch='E2_20261104';e=j.parent/epoch;e.mkdir();(e/j.name).write_bytes(j.read_bytes());j.write_bytes(b'BROKEN_E1_DO_NOT_REPAIR\n')
 (r/'fabrika').mkdir();(r/'fabrika/poly_signal_zhurnal.py').write_bytes(b'writer lock');(r/'poly_signaly.py').write_bytes(b'producer')
 monkeypatch.setattr(m,'PRODUCERS',{'POLY_95_V2_SHIROKO.jsonl':('poly_signaly.py',digest(b'producer'))})
 monkeypatch.setattr(m,'JOURNAL_MODULE_PIN',digest(b'writer lock'))
 binding=dict(schema='POLY_SIGNAL_V1',epoha=epoch,pravilo=j.stem,zhurnal='research_lab/data/poly_signaly/'+epoch+'/'+j.name,producer='poly_signaly.py',producer_sha256=digest(b'producer'),zhurnal_modul_sha256=digest(b'writer lock'),pid=1,start_utc='2026-11-04T09:00:00Z',strok_pri_starte=0)
 f=e/('MANIFEST_'+j.stem+'.json');f.write_text(json.dumps(binding))
 (e/('MANIFEST_'+j.stem+'.history.jsonl')).write_bytes(line(dict(binding,perv_stroka_etogo_zapuska=1))+b'\n')
 out=m.cycle_many(r,state,journals=(j.name,),epoch=epoch);assert out['journals'][j.name]['measured']==1
 assert j.read_bytes()==b'BROKEN_E1_DO_NOT_REPAIR\n'
 assert (state/epoch/j.stem/'signals'/s['signal_observation_id']/'measurement-manifest.json').exists()
 (r/'poly_signaly.py').write_bytes(b'changed');out=m.cycle_many(r,state,journals=(j.name,),epoch=epoch)
 assert out['status']=='UNKNOWN' and 'PRODUCER_DRIFT' in out['journals'][j.name]['reason']


def score_witness_fixture(tmp_path):
 import time
 from research_lab.polymarket_ws_data_v1 import SegmentStore,encoded
 from scripts.pull_polymarket_ws_data_v1 import import_segment
 root=tmp_path/'lab';native=tmp_path/'native';at=time.time_ns()//1000000-1000
 game=dict(gameId=123,leagueAbbreviation='nba',score='88-82',period='Q4',elapsed='4:00',live=True,ended=False)
 store=SegmentStore(native,'sports',clock=lambda:at,min_free=0)
 store.append('RECV',dict(frame=json.dumps(game)),received_ms=at);store.close()
 sealpath=next((native/'sports/sealed').glob('*.delivery.json'));seal=json.loads(sealpath.read_bytes());raw=(native/seal['file']).read_bytes()
 archive=root/'data/poly_ws_vps_v1';receipt=import_segment(archive,seal,raw,observed_ms=at+1000)
 segment=archive/seal['file'];import gzip
 rowbytes=gzip.decompress(raw).splitlines()[0];row=json.loads(rowbytes);delivery=(segment.with_name(segment.name+'.delivery.json')).stat().st_mtime_ns//1000000
 signal=dict(received_ms=at+2000,signal_ms=at+3000,score=dict(gameId=123,score_away_home='88-82',period='Q4',clock='4:00',score_received_ms=at,score_on_mac_ms=delivery))
 signal['score']['source_witness']=dict(segment='research_lab/data/poly_ws_vps_v1/'+seal['file'],segment_sha256=digest(raw),line_index=0,line_sha256=digest(rowbytes),received_ms=at,monotonic_ns=row['monotonic_ns'],delivery_mtime_ms=delivery,segment_first_seen_by_producer_ms=at+2000,book_received_ms=at+2000)
 return root,signal,archive,seal


def test_sports_witness_verifies_original_bytes_and_import_before_decision(tmp_path):
 m=module();root,signal,archive,seal=score_witness_fixture(tmp_path)
 proof=m.verify_sports_witness(signal,root)
 assert proof['sports_frame_provenance_verified'] is True and proof['score_available_by_decision'] is True
 assert proof['raw_frame_reports_live'] is True and proof['before_sports_final_proven'] is False
 assert proof['segment_sha256']==signal['score']['source_witness']['segment_sha256']

@pytest.mark.parametrize('change,reason', [('path','SCORE_SOURCE_PATH'),('frame','SCORE_FRAME_HASH'),('mono','SCORE_MONOTONIC'),('score','SCORE_FRAME_MISMATCH'),('import','SCORE_AVAILABLE_AFTER_DECISION')])
def test_sports_witness_rejects_forged_or_late_evidence(tmp_path,change,reason):
 m=module();root,signal,archive,seal=score_witness_fixture(tmp_path);w=signal['score']['source_witness']
 if change=='path':w['segment']='../../configs/secret.env'
 if change=='frame':w['line_sha256']='b'*64
 if change=='mono':w['monotonic_ns']+=1
 if change=='score':signal['score']['score_away_home']='99-82'
 if change=='import':signal['signal_ms']=signal['score']['score_received_ms']
 with pytest.raises(ValueError,match=reason):m.verify_sports_witness(signal,root)


def test_sports_witness_distinguishes_import_after_old_quote(tmp_path):
 m=module();root,s,archive,seal=score_witness_fixture(tmp_path)
 s['received_ms']=s['score']['score_received_ms']+1
 s['score']['source_witness']['book_received_ms']=s['received_ms']
 proof=m.verify_sports_witness(s,root)
 assert proof['score_available_by_decision'] is True and proof['score_available_before_book'] is False


def test_sports_witness_rejects_future_claimed_first_observation(tmp_path):
 m=module();root,s,archive,seal=score_witness_fixture(tmp_path)
 s['score']['source_witness']['segment_first_seen_by_producer_ms']=s['signal_ms']+1
 with pytest.raises(ValueError,match='SCORE_FIRST_SEEN_TIME'):m.verify_sports_witness(s,root)


def epoch_binding_fixture(m,root,j,monkeypatch,started=0):
 epoch='E2_20261104';folder=j.parent/epoch;folder.mkdir();(folder/j.name).write_bytes(j.read_bytes())
 (root/'fabrika').mkdir(exist_ok=True);(root/'fabrika/poly_signal_zhurnal.py').write_bytes(b'new writer with startup history');(root/'poly_signaly.py').write_bytes(b'new producer')
 monkeypatch.setattr(m,'PRODUCERS',{j.name:('poly_signaly.py',digest(b'new producer'))});monkeypatch.setattr(m,'JOURNAL_MODULE_PIN',digest(b'new writer with startup history'))
 manifest=dict(schema='POLY_SIGNAL_V1',epoha=epoch,pravilo=j.stem,zhurnal='research_lab/data/poly_signaly/'+epoch+'/'+j.name,producer='poly_signaly.py',producer_sha256=digest(b'new producer'),zhurnal_modul_sha256=digest(b'new writer with startup history'),pid=2,start_utc='2026-11-05T05:27:20Z',strok_pri_starte=started)
 path=folder/('MANIFEST_'+j.stem+'.json');path.write_bytes(line(manifest))
 history=folder/('MANIFEST_'+j.stem+'.history.jsonl');history.write_bytes(line(dict(manifest,perv_stroka_etogo_zapuska=started+1))+b'\n')
 return epoch,folder,path,history,manifest


def test_current_producer_binding_preserves_startup_history(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);epoch,folder,path,history,manifest=epoch_binding_fixture(m,r,j,monkeypatch)
 bound=m.producer_binding(r,j.name,epoch)
 assert bound['producer_history_sha256']==digest(history.read_bytes())
 assert bound['producer_history_raw_text']==history.read_text()
 assert history.read_bytes()==line(dict(manifest,perv_stroka_etogo_zapuska=1))+b'\n'


@pytest.mark.parametrize('fault',['different_producer','wrong_start_line','partial_tail'])
def test_startup_history_conflict_blocks_even_when_current_files_match(tmp_path,monkeypatch,fault):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);epoch,folder,path,history,manifest=epoch_binding_fixture(m,r,j,monkeypatch)
 row=dict(manifest,perv_stroka_etogo_zapuska=1)
 if fault=='different_producer':row['producer_sha256']='f'*64
 if fault=='wrong_start_line':row['perv_stroka_etogo_zapuska']=2
 history.write_bytes(line(row)+(b'' if fault=='partial_tail' else b'\n'))
 with pytest.raises(ValueError,match='PRODUCER_HISTORY'):m.producer_binding(r,j.name,epoch)


def test_old_unobserved_producer_prefix_is_not_replayed_after_handoff(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);epoch,folder,path,history,manifest=epoch_binding_fixture(m,r,j,monkeypatch,started=1)
 monkeypatch.setattr(m.snap,'get_capture',lambda _:pytest.fail('previous producer signal must not be repriced'))
 out=m.cycle_many(r,state,journals=(j.name,),epoch=epoch)
 z=out['journals'][j.name];assert z['measured']==0 and z['blocked']==1 and any('PREVIOUS_PRODUCER_UNOBSERVED_NO_REPLAY' in x for x in z['issues'])
 assert (folder/j.name).read_bytes()==j.read_bytes()


def test_witnessed_measurement_survives_writer_restart_without_repricing(tmp_path,monkeypatch):
 m,r,j,s,n,state=setup(tmp_path,monkeypatch);epoch,folder,path,history,manifest=epoch_binding_fixture(m,r,j,monkeypatch)
 assert m.cycle_many(r,state,journals=(j.name,),epoch=epoch)['journals'][j.name]['measured']==1
 signal_folder=state/epoch/j.stem/'signals'/s['signal_observation_id']
 before={name:(signal_folder/name).read_bytes() for name in ['source-signal.json','intake.json','measurement-manifest.json']}
 restarted=dict(manifest,pid=3,strok_pri_starte=1);path.write_bytes(line(restarted))
 with history.open('ab') as f:f.write(line(dict(restarted,perv_stroka_etogo_zapuska=2))+b'\n')
 def only_resolution(url):
  assert '/resolutions?' in url,'writer restart must not fetch a fresh book'
  return transport(n)(url)
 monkeypatch.setattr(m.snap,'get_capture',only_resolution)
 out=m.cycle_many(r,state,journals=(j.name,),epoch=epoch)
 assert out['journals'][j.name]['measured']==0
 assert all((signal_folder/name).read_bytes()==raw for name,raw in before.items())
