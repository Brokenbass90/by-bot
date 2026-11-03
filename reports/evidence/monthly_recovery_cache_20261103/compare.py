"""Pure exact comparison: one date exception, no other financial/config change."""
import copy,json,hashlib,sqlite3
from pathlib import Path

def need(v,e):
 if not v:raise ValueError(e)
def compare(old,new,oldscope,scope,app):
 expected_old=json.loads((Path(__file__).parent/'packet.json').read_bytes())
 a=copy.deepcopy(old);b=copy.deepcopy(new)
 for v in [a,b]:v.pop('files');v.pop('authority')
 need(a==b,'OPERATIONAL_CONFIG_CHANGED')
 a=copy.deepcopy(oldscope);b=copy.deepcopy(scope)
 for v in [a,b]:
  for k in ['source_files','strategy_identity','revocation_path','selection_policy','initial_recovery']:v.pop(k,None)
 need(a==b,'FINANCIAL_TERMS_CHANGED')
 need(oldscope['selection_policy']=='EXISTING_SEALED_FROZEN_MONTHLY_ONLY' and 'initial_recovery' not in oldscope,'OLD_POLICY_CHANGED')
 from research_lab.alpaca_monthly_binding_v1 import RECOVERY_SELECTION_POLICY,validate_initial_recovery
 approved_ref=expected_old['approved_prior_scope'];approved_raw=Path(approved_ref['path']).read_bytes();need(hashlib.sha256(approved_raw).hexdigest()==approved_ref['sha256'],'APPROVED_PRIOR_SCOPE_PIN');approved=json.loads(approved_raw)
 a=copy.deepcopy(approved);b=copy.deepcopy(scope)
 for v in [a,b]:
  for k in ['source_files','strategy_identity','revocation_path']:v.pop(k)
 need(a==b,'APPROVED_FINANCIAL_TERMS_CHANGED')
 changed={n for n,h in approved['strategy_identity']['material']['files'].items() if scope['strategy_identity']['material']['files'].get(n)!=h}
 need(changed=={'research_lab/alpaca_monthly_binding_v1.py'},'CACHE_REPAIR_SOURCE_DELTA')
 need(scope['selection_policy']==RECOVERY_SELECTION_POLICY and scope['initial_recovery']==expected_old['policy'],'EXCEPTION_POLICY_CHANGED')
 oldfiles=oldscope['strategy_identity']['material'];newfiles=scope['strategy_identity']['material'];a=copy.deepcopy(oldfiles);b=copy.deepcopy(newfiles);a.pop('files');b.pop('files');need(a==b,'FROZEN_CONTRACT_CHANGED')
 changed={n for n in oldfiles['files'] if oldfiles['files'][n]!=newfiles['files'].get(n)}
 need(set(oldfiles['files'])==set(newfiles['files']) and changed=={'research_lab/alpaca_monthly_binding_v1.py','research_lab/alpaca_monthly_native_binding_v1.py'},'UNEXPECTED_STRATEGY_SOURCE_CHANGE')
 with sqlite3.connect(Path(scope['book']).as_uri()+'?mode=ro',uri=True) as db:
  rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM selections')]
 original=next(r for r in rows if r['selection_id']==scope['initial_recovery']['original_selection_id'])
 p=Path(__file__).parent
 original_file=(p/'original-selection.json').read_bytes();ticket_file=(p/'original-ticket.json').read_bytes()
 need(hashlib.sha256(original_file).hexdigest()==expected_old['original_selection_file_sha256'] and json.loads(original_file)==original,'ORIGINAL_SELECTION_DRIFT')
 need(hashlib.sha256(ticket_file).hexdigest()==expected_old['original_ticket_file_sha256'],'ORIGINAL_TICKET_FILE_DRIFT')
 ticket=json.loads(ticket_file);actual=Path(new['manager']['root'])/'tickets'/(ticket['client_order_id']+'.json')
 need(json.loads(actual.read_bytes())==ticket,'CURRENT_ORIGINAL_TICKET_DRIFT')
 validate_initial_recovery(scope['initial_recovery'],original,ticket)
 return True
