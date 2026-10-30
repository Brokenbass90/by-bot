import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_lab import pump4_brain_timely_v1 as B

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'reports/evidence/pump4_brain_timely_20261029/brain_shadow_v1.pinned.py'
H=3600000
T=1793307600000

def publication(signal=None):
    core=dict(domain_schema='PUMP4_CLOSED_H1_INTAKE_V1',symbol='BTCUSDT',bar_open_ms=T-H,
              history_sha256='a'*64,source_pins=B.FROZEN_SIGNAL_PINS,signal=signal)
    d=dict(core,decision_id='pump4-'+B.digest(core),available_ms=T+1000,
           first_observed_ms=T+1100,orders_allowed=False,money_authority=False)
    obs=dict(schema='PUMP4_DATA_DECISION_OBSERVATION_V1',decision=d,archive_id='b'*64,
             mode='CURRENT_CLOSED_BAR',status='NO_SIGNAL' if signal is None else 'STREAM_SIGNAL_REQUIRES_FRESH_HTTPS',
             orders_allowed=False,money_authority=False)
    return dict(symbol='BTCUSDT',status='CLOSED_H1_INTAKE_PASS',mode='CURRENT_CLOSED_BAR',
                publication_completed_ms=T+1200,pair_received_ms=T+1000,
                source_kind='CONFIRMED_WS_WITH_FROZEN_JOURNAL_PREFIX',decisions=[obs],
                orders_allowed=False,money_authority=False,broker_writes=0)

class TimelyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir="/private/tmp" if Path("/private/tmp").is_dir() else "/tmp");self.root=Path(self.tmp.name).resolve()
        self.policy=B.FrozenBrain(POLICY)
    def tearDown(self):self.tmp.cleanup()
    def event(self,p=None,**kw):
        return B.pair_event(p or publication(),policy=self.policy,observed_ms=T+2000,
                            epoch_ms=T-10000,**kw)
    def test_original_policy_loaded_without_running_producer(self):
        self.assertEqual(self.policy.version,'BRAIN_V3')
        self.assertEqual(self.policy.evaluate(None)['brain']['action'],'NO_OPPORTUNITY')
        result=self.policy.evaluate(5.0)
        self.assertEqual(result['baseline']['allocation_units'],1)
        self.assertEqual(result['brain']['allocation_units'],0)
        self.assertIn('unknown_edge',result['brain']['reasons'])
        self.assertEqual(result['funding_bps'],'UNKNOWN')
    def test_policy_byte_drift_rejected(self):
        p=self.root/'policy.py';p.write_bytes(POLICY.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'POLICY_SOURCE_PIN'):B.FrozenBrain(p)
    def test_no_signal_not_counted_as_profitable_trade(self):
        event=self.event()
        self.assertEqual(event['kind'],'NO_OPPORTUNITY')
        self.assertFalse(event['money_authority'])
        self.assertEqual(event['comparison']['baseline']['action'],'NO_OPPORTUNITY')
        self.assertEqual(event['pre_live_decision_proven'],'UNKNOWN')
    def test_hash_identity_authority_and_clock_rejected(self):
        for change in ('hash','authority','future','pins','mode'):
            p=publication()
            if change=='hash':p['decisions'][0]['decision']['decision_id']='pump4-'+'0'*64
            if change=='authority':p['decisions'][0]['money_authority']=True
            if change=='future':p['publication_completed_ms']=T+3000
            if change=='pins':p['decisions'][0]['decision']['source_pins']={}
            if change=='mode':p['mode']='CATCHUP_REPLAY'
            with self.subTest(change=change),self.assertRaises(ValueError):self.event(p)
    def test_restart_replay_no_second_pair_and_conflict_detected(self):
        event=self.event();path=self.root/'events.jsonl'
        first=B.record_pair(path,event,clock=lambda:T+2200)
        again=B.record_pair(path,self.event(),clock=lambda:T+4000)
        self.assertTrue(first['new']);self.assertFalse(again['new'])
        self.assertEqual(first['witness'],again['witness'])
        changed=self.event();changed['source_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_CONFLICT'):B.record_pair(path,changed,clock=lambda:T+5000)
    def test_late_durable_write_never_timely(self):
        result=B.record_pair(self.root/'events.jsonl',self.event(),clock=lambda:T+61000)
        self.assertFalse(result['witness']['within_entry_60s'])
    def test_history_before_observer_epoch_never_prospective(self):
        event=B.pair_event(publication(),policy=self.policy,observed_ms=T+2000,epoch_ms=T+1500)
        result=B.record_pair(self.root/'events.jsonl',event,clock=lambda:T+2200)
        self.assertFalse(result['witness']['prospective'])
    def test_partial_tail_is_preserved(self):
        path=self.root/'events.jsonl';B.record_pair(path,self.event(),clock=lambda:T+2200)
        with path.open('ab') as f:f.write(b'{')
        raw=path.read_bytes()
        with self.assertRaises(ValueError):B.record_pair(path,self.event(),clock=lambda:T+2300)
        self.assertEqual(path.read_bytes(),raw)
    def test_symlink_and_duplicate_json_rejected(self):
        p=self.root/'x.json';p.write_text('{"a":1,"a":2}')
        with self.assertRaises(ValueError):B.read_json(p)
        p.write_text('{}');q=self.root/'link';q.symlink_to(p)
        with self.assertRaises(ValueError):B.read_json(q)
    def test_signal_needs_verified_next_open_not_signal_close(self):
        signal=dict(strategy='pump_fade',symbol='BTCUSDT',side='short',entry=100.0,sl=101.0,
                    tps=[98.0,96.0],tp_fracs=[.4,.6])
        p=publication(signal)
        with self.assertRaisesRegex(ValueError,'REFERENCE_PLAN_REQUIRED'):self.event(p)
    def test_model_pair_known_geometry_preserves_unknown_funding(self):
        signal=dict(strategy='pump_fade',symbol='BTCUSDT',side='short',entry=100.0,sl=101.0,
                    tps=[98.0,96.0],tp_fracs=[.4,.6])
        event=self.event(publication(signal),next_open=100.0)
        self.assertEqual(event['kind'],'SHADOW_PAIR')
        self.assertEqual(event['comparison']['brain']['reasons'],['unknown_edge'])
        self.assertEqual(event['comparison']['risk_pct'],4.0)
        self.assertEqual(event['comparison']['net_economics_qualified'],False)
    def test_witness_after_lost_reply_recovers_without_repeating_pair(self):
        path=self.root/'events.jsonl';event=self.event()
        from research_lab.att1_lifecycle_journal import LifecycleJournal
        LifecycleJournal(path).append_checked(event,B.reduce_events)
        result=B.record_pair(path,self.event(),clock=lambda:T+70000)
        self.assertFalse(result['new']);self.assertTrue(result['witness']['recovered'])
        self.assertFalse(result['witness']['within_entry_60s'])

    def test_public_raw_frames_supply_next_open_and_pin_tamper_fails(self):
        root=self.root/'source';folder=root/str(T);(folder/'frames').mkdir(parents=True);(folder/'batches').mkdir()
        p=publication();pins=[]
        for n,(start,confirm,received,opening) in enumerate([(T-H,True,T+500,'100'),(T,False,T+1000,'101')],1):
            row=dict(start=start,end=start+H-1,interval='60',confirm=confirm,open=opening,high='103',low='99',close='101',volume='50',turnover='5000',timestamp=received)
            raw=json.dumps(dict(topic='kline.60.BTCUSDT',type='snapshot',ts=received,data=[row]))
            cap=dict(schema='PUMP4_WS_RAW_CAPTURE_V1',endpoint='wss://stream.bybit.com/v5/public/linear',connection=1,
                     received_ms=received,raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest())
            target=folder/'frames'/(str(n)+'.json');target.write_text(json.dumps(cap))
            pins.append(dict(path='/original/public/frames/'+target.name,sha256=B.digest(cap)))
        batch=dict(symbol='BTCUSDT',archive_id='b'*64,raw_captures=pins)
        (folder/'batches'/'BTCUSDT.json').write_text(json.dumps(batch))
        self.assertEqual(B.next_open_from_source(root,p),101.0)
        changed=json.loads(target.read_text());changed['raw_sha256']='0'*64;target.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'FRAME_PIN'):B.next_open_from_source(root,p)

if __name__=='__main__':unittest.main()
