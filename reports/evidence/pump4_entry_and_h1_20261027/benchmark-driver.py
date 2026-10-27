from pathlib import Path
import json,subprocess
base=Path('/opt/bybot-research/pump4-server-orders-off-20261023');op=base/'entry-handoff-20261027'
rows=[]
for app in [base/'candidate-70d4a1009c13eccf/app',base/'candidate-ffb31e24c703d9ed/app']:
 for _ in range(3):
  result=subprocess.check_output(['/root/by-bot/.venv/bin/python','-B',str(op/'profile-single.py'),str(op/'profile-case.json')],cwd=app,text=True)
  r=json.loads(result.splitlines()[0]);r['app']=app.parent.name;rows.append(r)
assert len({r['result_sha256'] for r in rows})==1 and len({r['journal_sha256'] for r in rows})==1
print(json.dumps(dict(schema='PUMP4_ONE_CURRENT_BAR_BENCHMARK_V1',samples=rows,same_result_and_journal=True,new_H1_proof=False,network_disabled=True,real_journal_modified=False)))
