import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

P=Path(__file__).parents[1]/'research_lab/kity_dosie.py'
spec=importlib.util.spec_from_file_location('isolated_dossier',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def packet(n):
 k=n//10
 sig={'d':'2026-10-22','monet_s_priznakom':n,
      'long':[{'s':f'L{i}USDT'} for i in range(k)],'short':[{'s':f'S{i}USDT'} for i in range(k)]}
 vh={'d':sig['d'],'pozicii':[{'s':v['s'],'side':side,'lot_ok':True} for side,key in [(1,'long'),(-1,'short')] for v in sig[key]]}
 return sig,vh


@pytest.mark.parametrize('n,expected',[(30,6),(40,8),(50,10)])
def test_cardinality_is_frozen_n_decile(n,expected):
 sig,vh=packet(n);r=m.korzina(sig,vh)
 assert r['nogi']==expected and r['long_count']==r['short_count']==n//10


@pytest.mark.parametrize('bad',['missing','duplicate','side','n','signal_duplicate'])
def test_bad_basket_not_ready(bad):
 sig,vh=packet(50)
 if bad=='missing':vh['pozicii'].pop()
 if bad=='duplicate':vh['pozicii'][1]=vh['pozicii'][0]
 if bad=='side':vh['pozicii'][0]['side']=-1
 if bad=='n':sig['monet_s_priznakom']=29
 if bad=='signal_duplicate':sig['short'][0]=sig['long'][0]
 with pytest.raises(ValueError):m.korzina(sig,vh)


def test_actual_c2_pin_and_dynamic_size(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'D',tmp_path/'data');monkeypatch.setattr(m,'LAB',tmp_path)
 c2s=[]
 for day in ('2026-10-15','2026-10-22'):
  sig,vh=packet(50);sig['d']=vh['d']=day;p=m.D/day;p.mkdir(parents=True)
  raw=json.dumps(sig).encode();(p/'signal.json').write_bytes(raw)
  (p/'vhod.json').write_text(json.dumps(vh));(p/'kvitanciya_C1.json').write_text(json.dumps({'status':'OPERATIONAL_PASS'}))
  c2={'schema':'KITY_C2_ACTUAL_SIGNAL_MATCH_V1','status':'C2_PASS_MATCH_ONLY','d':day,
      'compared_inputs':{'signal.json':hashlib.sha256(raw).hexdigest()},
      'long':[x['s'] for x in sig['long']],'short':[x['s'] for x in sig['short']]}
  f=tmp_path/(day+'.json');f.write_text(json.dumps(c2));c2s.append(str(f))
 assert m.main(['2026-10-15','2026-10-22','--c2',*c2s])==0
 text=(tmp_path/'DOSIE_KITY_BYBIT_2026-10-22.md').read_text()
 assert '10 ног (5L/5S)' in text and '$1000' in text and '4L/4S' not in text
 assert 'не является финансовым допуском' in text
 c=json.loads(Path(c2s[1]).read_bytes());c['compared_inputs']['signal.json']='0'*64;Path(c2s[1]).write_text(json.dumps(c))
 assert m.main(['2026-10-15','2026-10-22','--c2',*c2s])==2


def test_old_public_c2_needs_pinned_original_readback(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'D',tmp_path/'data');day='2026-10-15';p=m.D/day;p.mkdir(parents=True)
 sig,vh=packet(50);sig['d']=vh['d']=day
 raw=json.dumps(sig).encode();(p/'signal.json').write_bytes(raw)
 (p/'vhod.json').write_text(json.dumps(vh));(p/'kvitanciya_C1.json').write_text(json.dumps({'status':'OPERATIONAL_PASS'}))
 c={'schema':'KITY_BYBIT_C2_PUBLIC_PARITY_RECEIPT_V1','day':day,'status':'C2_PASS_MATCH_ONLY',
    'long':[x['s'] for x in sig['long']],'short':[x['s'] for x in sig['short']]}
 cp=tmp_path/'c2.json';cp.write_text(json.dumps(c))
 rb=tmp_path/'readback.json';rb.write_text(json.dumps({'schema':'KITY_C2_EXTERNAL_COMPARISON_INPUTS_READBACK_V1',
     'files':{'signal.json':{'sha256':hashlib.sha256(raw).hexdigest(),'source_unchanged_during_read':True}}}))
 pin=hashlib.sha256(rb.read_bytes()).hexdigest()
 assert m.nedelya(day,str(cp))['problemy']
 assert not m.nedelya(day,str(cp),str(rb),pin)['problemy']
 rb.write_text('{}')
 assert m.nedelya(day,str(cp),str(rb),pin)['problemy']


@pytest.mark.parametrize('status',['PASS','C2_PASS'])
def test_status_only_c2_cannot_bypass_source_binding(tmp_path,monkeypatch,status):
 monkeypatch.setattr(m,'D',tmp_path/'data');monkeypatch.setattr(m,'LAB',tmp_path)
 files=[]
 for day in ('2026-10-15','2026-10-22'):
  sig,vh=packet(50);sig['d']=vh['d']=day;p=m.D/day;p.mkdir(parents=True)
  for name,value in [('signal',sig),('vhod',vh),('kvitanciya_C1',{'status':'OPERATIONAL_PASS'})]:
   (p/(name+'.json')).write_text(json.dumps(value))
  f=tmp_path/(day+'.json');f.write_text(json.dumps({'status':status}));files.append(str(f))
 assert m.main(['2026-10-15','2026-10-22','--c2',*files])==2
