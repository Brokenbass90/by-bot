import ast, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
R=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824')
S=R.parent/'bybit-bot-clean-v28'
REF='cf904086a2d887a96ac2be3324a3d78433e1a94b'
A1='881dde00b5891e932d93d83bb415e9dcce6a85bd'
OUT=R/'.private/b3_frozen_once_20261008'
EV=R/'reports/evidence/alpaca_b3_gate_closure_20261008'
def git(rev,p):return subprocess.check_output(['git','show',rev+':'+p],cwd=R)
def sha(b):return hashlib.sha256(b).hexdigest()
paths=['bot/__init__.py','bot/strategy_priority_router.py','bot/regime_orchestrator.py','research_lab/os2/B3_KONFIG.json','research_lab/os2/B3_POPRAVKA_A1.md','research_lab/os2/replay.py','research_lab/os2/wf.py','research_lab/os2/rezhim_v1.py','research_lab/os2/REZHIM_V1_ZAMOK.json','research_lab/os2/REZHIM_V1_ZAMOK_v0.json','research_lab/os2/test_b3_popravka_a1.py','research_lab/os2/test_replay.py','research_lab/os2/test_rezhim_v1.py','research_lab/os2/test_wf.py','research_lab/orch_signals.json','research_lab/data/h1/BTCUSDT.npz','research_lab/os2/potoki/MANIFEST.json','research_lab/os2/dannye_15m_MANIFEST.json']
paths += ['research_lab/os2/potoki/'+p+'.json' for p in ('ASR1','ETS2','SF3','BOUNCE1')]
assert not (S/'research_lab/os2/B3_KVITANCIYA.json').exists(),'prior consumption receipt'
for rev in (REF,A1):
 assert subprocess.run(['git','cat-file','-e',rev+':research_lab/os2/B3_KVITANCIYA.json'],cwd=R,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
assert not OUT.exists(),'execution staging already exists; inspect, never recreate'
pins={}; blobs={}
for p in paths:
 b=git(REF,p); assert b==git(A1,p),('A1 drift',p); assert (S/p).read_bytes()==b,('sibling drift',p)
 pins[p]={'sha256':sha(b),'bytes':len(b),'origin':'git:'+REF};blobs[p]=b
manifest=json.loads(blobs['research_lab/os2/dannye_15m_MANIFEST.json'])
source15={}
for name,record in manifest.items():
 p=S/'research_lab/os2/dannye_15m'/name
 assert p.is_file() and sha(p.read_bytes())==record['sha256'],('data drift',name)
 source15[name]={'sha256':record['sha256'],'bytes':p.stat().st_size}
# Judge consumes pinned precomputed streams + BTC H1 only. It never imports signaly or regenerates streams.
for p,b in blobs.items():
 dest=OUT/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b);dest.chmod(0o400)
assert len(source15)==137
import numpy as np
pre={'status':'FROZEN_INPUTS_ACCEPTED','research_ref':REF,'repaired_checkpoint_ref':A1,'files':pins,'upstream_15m_files':source15,'upstream_15m_verified':len(source15),'execution_root':str(OUT),'judge_command':[str(R/'.venv/bin/python'),str(OUT/'research_lab/os2/wf.py')],'runtime':{'python':sys.version,'numpy':np.__version__},'no_prior_b3_receipt':True,'money_authority':False,'determinism':'pinned immutable inputs/source, stable sort/order, no RNG/network; timestamp metadata excluded from result semantics','upstream_15m_not_replayed':'Frozen judge consumes pinned streams, not raw bar generators; checked every upstream source without regenerating trades.'}
(EV/'b3_input_acceptance.json').write_text(json.dumps(pre,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'status':pre['status'],'pinned_files':len(pins),'upstream_15m_verified':len(source15),'python':sys.version.split()[0],'numpy':np.__version__,'execution_root':str(OUT)},ensure_ascii=False))
