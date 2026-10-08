from pathlib import Path
import urllib.request,json,hashlib,datetime as dt
R=Path('/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/alpaca_opening_20261008_1333')
urls={'BrokFeeSched.pdf':'https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf','fractional.html':'https://docs.alpaca.markets/us/docs/fractional-trading','buy_minimum.html':'https://alpaca.markets/support/can-we-submit-orders-smaller-than-1-usd-in-notional-value','commission.html':'https://alpaca.markets/support/commission-clearing-fees'}
manifest={}
for name,url in urls.items():
 req=urllib.request.Request(url,method='GET',headers={'User-Agent':'Alpaca-protocol-intake/1.0'})
 with urllib.request.urlopen(req,timeout=12) as response:
  raw=response.read(4000001);resolved=response.url
 assert len(raw)<=4000000
 p=R/name
 with p.open('xb') as f:f.write(raw)
 p.chmod(0o400)
 manifest[name]={'url':url,'resolved_url':resolved,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'received_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
with (R/'official_source_manifest.json').open('x') as f:json.dump(manifest,f,indent=2)
print(json.dumps(manifest))
