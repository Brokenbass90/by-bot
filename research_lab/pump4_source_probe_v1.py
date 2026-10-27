"""Isolated source evidence only: never strategy/intake/account/order authority."""
import json,hashlib,math
from decimal import Decimal
H=3600000

def need(ok,why):
 if not ok:raise ValueError('PUMP4_PROBE_'+why)
def decimal(value,zero=False):
 need(type(value) is str,'NUMBER_TYPE');v=Decimal(value);need(v.is_finite() and (v>=0 if zero else v>0) and math.isfinite(float(v)),'NUMBER');return v

def projection(row):
 o,h,l,c=[decimal(row[k]) for k in ('open','high','low','close')];v=decimal(row['volume'],True);t=decimal(row['turnover'],True)
 need(l<=min(o,c)<=max(o,c)<=h,'OHLC');return tuple(str(x) for x in (o,h,l,c,v,t))

def same(a,b):return tuple(map(Decimal,a))==tuple(map(Decimal,b))

def decode(raw):
 def pairs(values):
  d=dict(values);need(len(d)==len(values),'DUPLICATE_JSON_KEY');return d
 return json.loads(raw,object_pairs_hook=pairs)

class Probe:
 def __init__(self,boundary,symbols):
  need(type(boundary) is int and boundary%H==0 and 0<len(symbols)<=8 and len(set(symbols))==len(symbols),'MANIFEST')
  self.boundary=boundary;self.symbols=tuple(symbols);self.closed={};self.opened={};self.conflicts=set();self.connections=set()
 def add(self,raw,*,received_ms,connection):
  need(type(received_ms) is int and len(raw.encode())<=1000000,'RECEIVE');v=decode(raw);self.connections.add(connection)
  if 'topic' not in v:return dict(kind='CONTROL')
  topic=v['topic'];need(topic in ['kline.60.'+s for s in self.symbols] and v['type']=='snapshot','TOPIC');symbol=topic[9:]
  ts=v['ts'];need(type(ts) is int and 0<ts<=received_ms+5000,'SERVER_CLOCK');need(isinstance(v['data'],list) and 1<=len(v['data'])<=3,'ROWS')
  for row in v['data']:
   start=row['start'];need(type(start) is int and start%H==0 and row['end']==start+H-1 and row['interval']=='60' and type(row['confirm']) is bool,'BAR_SCOPE')
   # Actual combined close/open frames may share a post-boundary timestamp.
   # Closure comes from confirm/start/end plus frame and receive clocks.
   values=projection(row);need(type(row['timestamp']) is int and 0<=row['timestamp']<=ts,'LAST_TRADE_CLOCK')
   if start==self.boundary-H and row['confirm'] is True:
    need(ts>=self.boundary and received_ms>=self.boundary,'UNCLOSED_CLOCK');value=dict(values=values,received_ms=received_ms,connection=connection,server_ms=ts,sha256=hashlib.sha256(raw.encode()).hexdigest())
    if symbol in self.closed and not same(self.closed[symbol]['values'],values):self.conflicts.add(symbol)
    self.closed.setdefault(symbol,value)
   elif start==self.boundary and row['confirm'] is False:
    value=dict(value=str(decimal(row['open'])),received_ms=received_ms,connection=connection,server_ms=ts)
    if symbol in self.opened and Decimal(self.opened[symbol]['value'])!=Decimal(value['value']):self.conflicts.add(symbol)
    self.opened.setdefault(symbol,value)
  return dict(kind='KLINE_EVIDENCE',symbol=symbol)
 def summary(self):
  rows={}
  for s in self.symbols:
   c=self.closed.get(s);o=self.opened.get(s);pair=max(c['received_ms'],o['received_ms']) if c and o else None
   rows[s]=dict(closed_first_received_ms=c['received_ms'] if c else None,new_open_first_received_ms=o['received_ms'] if o else None,pair_first_received_ms=pair,timely_pair=pair is not None and self.boundary<=pair<=self.boundary+60000 and s not in self.conflicts,same_connection=bool(c and o and c['connection']==o['connection']),conflict=s in self.conflicts)
  return dict(schema='PUMP4_ISOLATED_SOURCE_PROBE_V2',boundary_ms=self.boundary,symbols=rows,connection_ids=sorted(self.connections),reconnected=any(c>1 for c in self.connections),orders_allowed=False,money_authority=False,production_admission=False)
 def compare(self,symbol,rows):
  need(symbol in self.symbols,'SYMBOL');bars={}
  for raw in rows:
   start=int(raw[0])
   if start not in (self.boundary-H,self.boundary):continue
   need(len(raw)==7,'REST_ROW');v=projection(dict(zip(('open','high','low','close','volume','turnover'),raw[1:])))
   if start in bars:need(same(bars[start],v),'REST_CHANGED_DUPLICATE')
   bars[start]=v
  need(self.boundary-H in bars and self.boundary in bars,'REST_PAIR_MISSING')
  c=self.closed.get(symbol);o=self.opened.get(symbol)
  return dict(closed_decimal_equal=bool(c and same(c['values'],bars[self.boundary-H])),next_open_equal=bool(o and Decimal(o['value'])==Decimal(bars[self.boundary][0])),closed_float_projection_equal=bool(c and list(map(float,c['values'][:5]))==list(map(float,bars[self.boundary-H][:5]))))
