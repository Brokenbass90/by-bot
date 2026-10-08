from pathlib import Path
from io import StringIO
from dotenv import dotenv_values
import urllib.request,urllib.error,json,hashlib,time,signal,subprocess,sqlite3
signal.alarm(85)
live=Path('/root/by-bot/runtime/alpaca_intended_live');paper=Path('/root/by-bot/runtime/alpaca_intended_paper')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):raise RuntimeError('redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
allowed={'/v2/account','/v2/clock','/v2/positions','/v2/orders?status=open&limit=100&nested=true','/v2/orders?status=all&after=2026-09-30T00:00:00Z&limit=100&direction=asc','/v2/account/activities?after=2026-09-30T00:00:00Z&direction=asc&page_size=100','/v2/assets/XOM'}
def capture(host,path,env):
 assert host in {'https://api.alpaca.markets','https://paper-api.alpaca.markets'} and path in allowed
 req_ms=time.time_ns()//1000000
 req=urllib.request.Request(host+path,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
 with opener.open(req,timeout=7) as response:raw=response.read(1_000_001)
 assert len(raw)<=1_000_000
 return {'endpoint':host+path,'request_ms':req_ms,'receive_ms':time.time_ns()//1000000,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw':raw.decode()}
lines=(live/'profile.env').read_text().splitlines();assert lines[0]=='source /root/by-bot/configs/alpaca_live_v38.env'
e=dict(dotenv_values('/root/by-bot/configs/alpaca_live_v38.env'));e.update(dotenv_values(stream=StringIO('\n'.join(lines[1:]))));assert e['ALPACA_BASE_URL'].rstrip('/')=='https://api.alpaca.markets'
p=dict(dotenv_values('/root/by-bot/configs/alpaca_paper_local.env'));assert p['ALPACA_BASE_URL'].rstrip('/')=='https://paper-api.alpaca.markets'
fields={'account':'/v2/account','clock':'/v2/clock','positions':'/v2/positions','open_orders':'/v2/orders?status=open&limit=100&nested=true','asset_XOM':'/v2/assets/XOM'}
result={'schema':'ALPACA_OCT8_MORNING_READ_ONLY_V1','broker_writes':0,'new_plan_prepared':False,'observed_ms':time.time_ns()//1000000,'live':{k:capture('https://api.alpaca.markets',v,e) for k,v in fields.items()},'paper':{k:capture('https://paper-api.alpaca.markets',v,p) for k,v in fields.items()}}
for k,path in {'activity_source':'/v2/account/activities?after=2026-09-30T00:00:00Z&direction=asc&page_size=100','order_source':'/v2/orders?status=all&after=2026-09-30T00:00:00Z&limit=100&direction=asc'}.items():result['live'][k]=capture('https://api.alpaca.markets',path,e)
for name,rows in [('activity_source',100),('order_source',100),('open_orders',100)]:assert len(json.loads(result['live'][name]['raw']))<rows,'truncated source '+name
binding=json.loads((live/'binding.json').read_text());assert json.loads(result['live']['account']['raw'])['id']==binding['account_id'];assert json.loads(result['paper']['account']['raw'])['id']=='4cdbfb77-d1e0-4789-86b2-341bc886efaf'
halt=Path(binding['account_lock_path']).with_suffix('.paper-kill')/'.paper-entry-halt.json'
result['live_runtime']={'binding_sha256':sha(live/'binding.json'),'profile_sha256':sha(live/'profile.env'),'wrapper_sha256':sha(live/'run.sh'),'entry_halt':json.loads(halt.read_text()),'halt_sha256':sha(halt),'hwm':json.loads((live/'protective_exit/protective_exit_hwm.json').read_text())}
roots=['/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app','/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/app','/opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/app']
result['source_manifests']={}
for root in roots:
 app=Path(root);m=json.loads((app/'source_manifest.json').read_text());bad=[n for n,h in m.items() if sha(app/n)!=h]
 result['source_manifests'][root]={'manifest_sha256':sha(app/'source_manifest.json'),'files':len(m),'mismatches':bad};assert not bad
result['services']={n:subprocess.check_output(['systemctl','show',n,'-p','MainPID','-p','NRestarts','-p','ActiveState'],text=True).splitlines() for n in ['bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service']}
result['cron']=[s for s in subprocess.check_output(['crontab','-l'],text=True).splitlines() if 'alpaca' in s.lower()]
result['paper_runtime']={'legacy_exclusions':json.loads((paper/'legacy_exclusions.json').read_text()),'legacy_exclusions_sha256':sha(paper/'legacy_exclusions.json'),'legacy_wrapper_sha256':sha(paper/'legacy_preserve.sh')}
base=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007')
books={'sealed':'/opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/runtime/selection/replacement.sqlite','continuation':str(base/'runtime/rehearsal/replacement.sqlite')}
result['books']={}
for kind,name in books.items():
 b=Path(name)
 with sqlite3.connect(b.absolute().as_uri()+'?mode=ro',uri=True) as db:counts={n:db.execute('SELECT COUNT(*) FROM '+n).fetchone()[0] for n in ['rankings','slots','intents','exits']}
 result['books'][kind]={'path':name,'sha256':sha(b),'counts':counts}
result['paper_lifecycle_runtime_exists']=(base/'runtime/broker_paper/paper.sqlite').exists();result['completed_ms']=time.time_ns()//1000000
print(json.dumps(result))
