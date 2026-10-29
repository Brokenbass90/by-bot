import ast,json,types,urllib.parse,subprocess
from pathlib import Path
repo=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824');src=subprocess.check_output(['git','show','47b90288c55114ad7e730377c2265b54c5a97406:research_lab/fanding_mezhbirzhevoy.py'],cwd=repo,text=True)
node=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef) and n.name=='k_bybit');code=compile(ast.Module(body=[node],type_ignores=[]),'published-k_bybit','exec')
H4=14400000;outputs=[]
for close in (120.,150.):
 env=dict(OT=0,DO=H4,H4=H4,W=28800000,time=types.SimpleNamespace(sleep=lambda _:None),get=lambda url,close=close:{'result':{'list':[['0','100','160','90',str(close),'1','1']]}})
 exec(code,env);got=env['k_bybit']('FIXTUREUSDT');assert got==[(0,close)];outputs.append(got)
assert outputs[0][0][0]==outputs[1][0][0] and outputs[0][0][1]!=outputs[1][0][1]
out=dict(schema='FUNDING_PUBLISHED_TIME_DEFECT_REPRODUCER_V1',status='DEFECT_REPRODUCED',source_ref='47b90288c55114ad7e730377c2265b54c5a97406',synthetic_only=True,bar_open_ms=0,close_available_after_ms=H4,known_open_price=100,perturbed_future_closes=[120,150],returned_entry_price_map=outputs,interpretation='Changing H4 future close changes price stored at the same bar-open key used by published main for entry',producer_changed=False,prereg_changed=False,judge_run=False,network_requests=0)
(repo/'.private/funding_sync_20261029/causal-reproducer.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
