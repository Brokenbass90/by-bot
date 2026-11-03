"""Pure source-patch comparison; never financial authority or transport."""
from pathlib import Path
ALLOWED={'research_lab/alpaca_dynamic_live_runtime_v1.py','research_lab/alpaca_monthly_cost_source_v1.py','research_lab/alpaca_monthly_cycle_v1.py','research_lab/alpaca_monthly_native_binding_v1.py'}
def require(value,reason):
 if not value:raise ValueError(reason)
def compare(old,new,oldscope,scope,app):
 require({k:v for k,v in old.items() if k not in ('files','authority')}=={k:v for k,v in new.items() if k not in ('files','authority')},'CONFIG_CHANGE')
 require(set(old['files'])==set(new['files']) and {n for n in old['files'] if old['files'][n]!=new['files'][n]}==ALLOWED,'SOURCE_DIFF')
 excluded={'source_files','revocation_path','strategy_identity'}
 require({k:v for k,v in oldscope.items() if k not in excluded}=={k:v for k,v in scope.items() if k not in excluded},'FINANCIAL_SCOPE_CHANGE')
 a=oldscope['strategy_identity']['material'];b=scope['strategy_identity']['material']
 require({k:v for k,v in a.items() if k!='files'}=={k:v for k,v in b.items() if k!='files'},'FROZEN_STRATEGY_CHANGE')
 require(set(a['files'])==set(b['files']) and {n for n in a['files'] if a['files'][n]!=b['files'][n]}=={'research_lab/alpaca_monthly_native_binding_v1.py'},'STRATEGY_IMPLEMENTATION_DIFF')
 require(scope['revocation_path']==str(Path(old['manager']['root'])/'OWNER_ENTRY_REVOKED_opening_v7.json'),'REVOKE_PATH')
 require({str(Path(v['path']).relative_to(app)):v['sha256'] for v in scope['source_files']}==new['files'],'SOURCE_SCOPE')
