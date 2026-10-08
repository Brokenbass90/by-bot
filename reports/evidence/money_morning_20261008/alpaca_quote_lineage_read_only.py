"""Pre-open GET-only permissions/lineage probe; never an executable quote plan."""
from pathlib import Path
from dotenv import dotenv_values
from io import StringIO
import urllib.request,urllib.error,json,hashlib,time,signal,sqlite3
signal.alarm(60)
live=Path('/root/by-bot/runtime/alpaca_intended_live')
lines=(live/'profile.env').read_text().splitlines()
assert lines[0]=='source /root/by-bot/configs/alpaca_live_v38.env'
env=dict(dotenv_values('/root/by-bot/configs/alpaca_live_v38.env'))
env.update(dotenv_values(stream=StringIO('\n'.join(lines[1:]))))
assert env['ALPACA_BASE_URL'].rstrip('/')=='https://api.alpaca.markets'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):raise RuntimeError('redirect refused')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
out={'observed_ms':time.time_ns()//1000000,'broker_writes':0,'quotes_usable_for_entry':False,'new_plan_prepared':False,'quote_sources':{}}
for feed in ('sip','iex'):
    endpoint='https://data.alpaca.markets/v2/stocks/XOM/quotes/latest?feed='+feed
    start=time.time_ns()//1000000
    req=urllib.request.Request(endpoint,method='GET',headers={'APCA-API-KEY-ID':env['ALPACA_API_KEY_ID'],'APCA-API-SECRET-KEY':env['ALPACA_API_SECRET_KEY']})
    try:
        with opener.open(req,timeout=7) as r:raw=r.read(1000001)
        assert len(raw)<=1000000
        out['quote_sources'][feed]={'endpoint':endpoint,'request_ms':start,'receive_ms':time.time_ns()//1000000,'raw':raw.decode(),'raw_sha256':hashlib.sha256(raw).hexdigest()}
    except urllib.error.HTTPError as e:
        out['quote_sources'][feed]={'endpoint':endpoint,'request_ms':start,'receive_ms':time.time_ns()//1000000,'http_status':e.code}
source=Path('/opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/runtime/closed_source.json')
raw=source.read_bytes();data=json.loads(raw)
out['closed_source']={'path':str(source),'sha256':hashlib.sha256(raw).hexdigest(),'closed_session':data['closed_session'],
                     'received_ms':data['received_ms'],'captured_ms':data['captured_ms'],'XOM_earnings':data['earnings']['XOM']}
book=Path('/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/runtime/rehearsal/replacement.sqlite')
with sqlite3.connect(book.absolute().as_uri()+'?mode=ro',uri=True) as db:
    out['book_rows']={n:db.execute('SELECT * FROM '+n).fetchall() for n in ['rankings','slots','intents','exits']}
out['book_sha256']=hashlib.sha256(book.read_bytes()).hexdigest()
out['completed_ms']=time.time_ns()//1000000
print(json.dumps(out))
