import copy,json
import pytest
from research_lab import pump4_source_probe_v1 as m
T=1793091600000

def msg(start,confirm,opened='100'):
 return dict(topic='kline.60.BTCUSDT',type='snapshot',ts=T+200,data=[dict(start=start,end=start+m.H-1,interval='60',open=opened,high='102',low='99',close='101',volume='4',turnover='400',confirm=confirm,timestamp=start+123)])

def test_closed_and_new_open_are_separate_original_receive_events():
 p=m.Probe(T,['BTCUSDT']);p.add(json.dumps(msg(T,False)),received_ms=T+500,connection=1);p.add(json.dumps(msg(T-m.H,True)),received_ms=T+700,connection=1)
 r=p.summary()['symbols']['BTCUSDT'];assert r['pair_first_received_ms']==T+700 and r['timely_pair'] and r['closed_first_received_ms']==T+700 and r['new_open_first_received_ms']==T+500
 assert p.summary()['money_authority'] is False

@pytest.mark.parametrize('fault',['unconfirmed','interval','end','nan','topic','future_ts'])
def test_invalid_or_unconfirmed_cannot_be_closed_evidence(fault):
 p=m.Probe(T,['BTCUSDT']);v=msg(T-m.H,True)
 if fault=='unconfirmed':v['data'][0]['confirm']=False
 elif fault=='interval':v['data'][0]['interval']='1'
 elif fault=='end':v['data'][0]['end']+=1
 elif fault=='nan':v['data'][0]['high']='NaN'
 elif fault=='topic':v['topic']='kline.60.ETHUSDT'
 else:v['ts']=T+10000
 try:p.add(json.dumps(v),received_ms=T+700,connection=1)
 except ValueError:pass
 assert p.summary()['symbols']['BTCUSDT']['closed_first_received_ms'] is None


def test_changed_confirmation_conflicts_never_overwrite_first():
 p=m.Probe(T,['BTCUSDT']);v=msg(T-m.H,True);p.add(json.dumps(v),received_ms=T+500,connection=1);v['data'][0]['close']='101.5';p.add(json.dumps(v),received_ms=T+800,connection=1)
 r=p.summary()['symbols']['BTCUSDT'];assert r['conflict'] and r['closed_first_received_ms']==T+500


def test_reconnect_and_late_pair_do_not_become_continuous_or_timely():
 p=m.Probe(T,['BTCUSDT']);p.add(json.dumps(msg(T-m.H,True)),received_ms=T+200,connection=1);p.add(json.dumps(msg(T,False)),received_ms=T+61000,connection=2)
 r=p.summary()['symbols']['BTCUSDT'];assert not r['timely_pair'] and not r['same_connection']


def test_rest_two_rows_and_ws_decimal_projection_match_without_using_forming_range():
 p=m.Probe(T,['BTCUSDT']);p.add(json.dumps(msg(T-m.H,True)),received_ms=T+500,connection=1);p.add(json.dumps(msg(T,False)),received_ms=T+600,connection=1)
 rows=[[str(T),'100','999','1','300','40','9999'],[str(T-m.H),'100','102','99','101','4','400']]
 assert p.compare('BTCUSDT',rows)['closed_decimal_equal'] and p.compare('BTCUSDT',rows)['next_open_equal']
 rows[1][5]='4.01';assert not p.compare('BTCUSDT',rows)['closed_decimal_equal']


def script_module():
 import importlib.util
 from pathlib import Path
 s=importlib.util.spec_from_file_location('source_script',Path(__file__).parents[1]/'scripts/probe_pump4_source_architecture_v1.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v


def test_bad_wire_frame_and_rejected_ack_are_logged_and_classified():
 s=script_module()
 class Log:
  def __init__(self):self.rows=[]
  def add(self,kind,**values):self.rows.append((kind,values))
 log=Log();p=m.Probe(T,['BTCUSDT']);acks=[];errors=[];request=dict(req_id='expected')
 for raw in ('{invalid',json.dumps(dict(op='subscribe',success=False,req_id='expected'))):s.consume_frame(log,p,raw,connection=1,received=T+100,request=request,acked=acks,errors=errors)
 assert len(errors)==2 and len([r for r in log.rows if r[0]=='WS_FRAME'])==2 and not acks


def test_successful_pairs_followed_by_failed_reconnect_do_not_support_hypothesis():
 s=script_module();symbols={str(i):dict(timely_pair=True,same_connection=True) for i in range(8)}
 r=dict(symbols=symbols,comparison=dict(status='SEALED_REFERENCE_COMPARED',symbols={k:dict(closed_decimal_equal=True,next_open_equal=True,closed_float_projection_equal=True) for k in symbols}),subscription_acks=[dict(connection=1,received_ms=T-100)],validation_errors=[],connection_attempts=1,connection_errors=[],reconnected=False)
 assert s.supported(r,T)
 r.update(connection_attempts=2,connection_errors=[dict(connection=1,error_type='ConnectionClosed')])
 assert not s.supported(r,T)


def test_confirmed_and_forming_pair_can_share_post_boundary_timestamp():
 p=m.Probe(T,['BTCUSDT']);v=msg(T-m.H,True);v['data'][0]['timestamp']=T+200;v['data'].append(msg(T,False)['data'][0]);v['data'][1]['timestamp']=T+200
 p.add(json.dumps(v),received_ms=T+338,connection=1)
 assert p.summary()['symbols']['BTCUSDT']['pair_first_received_ms']==T+338
 assert p.summary()['symbols']['BTCUSDT']['timely_pair']


def test_timestamp_cannot_be_future_of_frame_server_clock():
 p=m.Probe(T,['BTCUSDT']);v=msg(T-m.H,True);v['data'][0]['timestamp']=v['ts']+1
 with pytest.raises(ValueError):p.add(json.dumps(v),received_ms=T+338,connection=1)
 assert p.summary()['symbols']['BTCUSDT']['closed_first_received_ms'] is None


def test_confirmed_future_frame_cannot_be_received_before_boundary():
 p=m.Probe(T,['BTCUSDT']);v=msg(T-m.H,True);v['data'][0]['timestamp']=T+200
 with pytest.raises(ValueError):p.add(json.dumps(v),received_ms=T-1,connection=1)
 assert p.summary()['symbols']['BTCUSDT']['closed_first_received_ms'] is None
