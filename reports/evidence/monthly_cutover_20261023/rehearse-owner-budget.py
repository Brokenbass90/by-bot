from pathlib import Path
import hashlib,json,re,socket,sys,time,types,traceback
root=Path.cwd();sys.path.insert(0,str(root))
def denied(*a,**k):raise AssertionError('MONTHLY400_NETWORK_DENIED')
class Off(socket.socket):connect=denied;connect_ex=denied;sendto=denied
socket.socket=Off;socket.create_connection=denied
p=root/'scripts/rehearse_alpaca_monthly_cycle_v1.py';raw=p.read_bytes();source=raw.decode()
assert source.count("cash='487.42'")==1
source=source.replace("cash='487.42'","cash='496.31'").replace('487.42','400').replace("max_entry_notional_usd='204.7164'","max_entry_notional_usd='168'").replace("max_cumulative_net_loss_usd='20'","max_cumulative_net_loss_usd='8'")
source,n=re.subn(r"(liability_reserve_usd=)(['\"])(?:0?\.03|0)\2",lambda m:m[1]+m[2]+'40'+m[2],source)
assert n>=4
source=source.replace("out=json.loads(stream.getvalue());assert rc in (0,2),out","out=json.loads(stream.getvalue());publish(root/('cli-result-'+str(cli_calls[0])+'.json'),out);assert rc in (0,2),out")
source=source.replace("capital_usd='400'","capital_usd='400.0'")
module=types.ModuleType('monthly400_rehearsal_fixture_only');module.__file__=str(p)
exec(compile(source,str(p)+'[OWNER_BUDGET_FIXTURE_ONLY]','exec'),module.__dict__)
out=root/'.private/monthly_cutover_20261023';start=time.monotonic()
try:
 result=module.run_pending_rotation(out/'budget400-r3-full-cli',production_entrypoint=True)
 value=dict(schema='MONTHLY_OWNER400_FIXTURE_ACCEPTANCE_V1',status='PASS',elapsed_seconds=round(time.monotonic()-start,3),budget=dict(capital='400',gross='280',reserve='40',max_entry='168',loss_admission='8',fixture_account_cash='496.31'),result=result,source_helper_sha256=hashlib.sha256(raw).hexdigest(),fixture_variant_sha256=hashlib.sha256(source.encode()).hexdigest(),variant_semantics='ONLY_REHEARSAL_FINANCIAL_INPUT_LITERALS_CHANGED_CORE_SOURCES_UNCHANGED',orders_allowed=False,money_authority=False,real_broker_requests=0,real_broker_writes=0)
except Exception as e:
 value=dict(schema='MONTHLY_OWNER400_FIXTURE_ACCEPTANCE_V1',status='FAIL',elapsed_seconds=round(time.monotonic()-start,3),error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc(),orders_allowed=False,money_authority=False,real_broker_requests=0,real_broker_writes=0)
with (out/'budget400-r3-acceptance.json').open('x') as v:json.dump(value,v,sort_keys=True,indent=2);v.write('\n')
print(json.dumps({k:v for k,v in value.items() if k not in ('result','traceback')}));assert p.read_bytes()==raw
raise SystemExit(0 if value['status']=='PASS' else 2)
