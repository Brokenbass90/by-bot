"""DATA-only bounded public GET recovery; failed raw attempts remain immutable.

No credentials, POST, hourly retry/reseed, source-clock rebasing or financial
admission. The verified initial hour anchors retries once, including monotonic
budget protection against local clock reversal.
"""
import base64,hashlib,json,threading,time,urllib.request,urllib.error
from research_lab.kity_micro_transport_v1 import NoRedirect
from research_lab.pump4_bybit_sources_v1 import public_get,need

HEADERS=('x-bapi-limit','x-bapi-limit-status','x-bapi-limit-reset-timestamp')

def observed_public_get(path,params,*,timeout=12,clock=None):
    clock=clock or (lambda:time.time_ns()//1000000);begin=clock();observed={}
    def wire(method,url,headers,data,wire_timeout):
        need(method=='GET' and data is None,'RETRY_GET_ONLY')
        request=urllib.request.Request(url,headers=headers,method='GET')
        opener=urllib.request.build_opener(NoRedirect())
        try:response=opener.open(request,timeout=min(timeout,wire_timeout))
        except urllib.error.HTTPError as error:response=error
        with response:
            status=response.code;raw=response.read(2000001)
            selected={k:str(response.headers[k])[:256] for k in HEADERS if response.headers.get(k) is not None}
        observed.update(status=status,raw=raw,headers=selected)
        return status,raw
    try:cap=public_get(path,params,wire=wire,clock=clock)
    except (ValueError,UnicodeError):
        if not observed:raise
        # Preserve even an HTML/error body. Unchanged checked() rejects this
        # capture; raw failure evidence must survive before any retry decision.
        raw=observed['raw'];text=raw.decode(errors='replace')
        cap=dict(endpoint=path,params=dict(params),method='GET',signed=False,request_ms=begin,receive_ms=clock(),
            http_status=observed['status'],raw=text,raw_sha256=hashlib.sha256(text.encode()).hexdigest(),body={},error_type='INVALID_PUBLIC_BODY',
            wire_raw_b64=base64.b64encode(raw).decode(),wire_raw_sha256=hashlib.sha256(raw).hexdigest())
    cap['response_headers']=observed['headers'];return cap


class PublicRetry:
    def __init__(self,*,getter=observed_public_get,persist,clock=None,monotonic=None,sleep=None):
        self.getter,self.persist=getter,persist
        self.clock=clock or (lambda:time.time_ns()//1000000)
        self.monotonic=monotonic or time.monotonic;self.sleep=sleep or time.sleep
        self.lock=threading.Lock();self.until=0.;self.http_attempts=0;self.deadline=None;self.monotonic_deadline=None;self.halted=False

    def anchor(self,deadline_ms):
        need(type(deadline_ms) is int and self.deadline is None,'RETRY_ANCHOR_ONCE')
        self.deadline=deadline_ms;self.monotonic_deadline=self.monotonic()+max(0,min(60000,deadline_ms-self.clock()))/1000

    def remaining(self):
        if self.deadline is None:return 0.
        return max(0,min((self.deadline-self.clock())/1000,self.monotonic_deadline-self.monotonic()))

    def wait(self,*,retry):
        while True:
            if retry and self.remaining()<=0:return False
            with self.lock:
                need(not self.halted,'HTTP403_GLOBAL_STOP')
                delay=max(0,self.until-self.monotonic())
            if delay==0:return True
            if retry and delay>=self.remaining():return False
            self.sleep(delay) # mutex released; another response may extend it

    def defer(self,cap):
        delay=1.
        try:
            reset=int(cap.get('response_headers',{})['x-bapi-limit-reset-timestamp']);stamp=cap['body']['time']
            if type(stamp) is int and 0<=reset-stamp<=10000:delay=max(.1,(reset-stamp+100)/1000)
        except (KeyError,TypeError,ValueError,OverflowError):pass
        with self.lock:self.until=max(self.until,self.monotonic()+delay)

    @staticmethod
    def rate_limited(cap,path,params):
        try:
            return (cap['method']=='GET' and cap['signed'] is False and cap['endpoint']==path and cap['params']==params
                and cap['http_status']==200 and not cap.get('error_type') and type(cap['body']['retCode']) is int
                and cap['body']['retCode']==10006 and hashlib.sha256(cap['raw'].encode()).hexdigest()==cap['raw_sha256']
                and json.loads(cap['raw'])==cap['body'])
        except (KeyError,ValueError,TypeError):return False

    def get(self,path,params):
        last=None;query=dict(params)
        for attempt in range(1,4):
            if not self.wait(retry=attempt>1):return last
            timeout=12 if attempt==1 else min(12,self.remaining())
            if timeout<=0:return last
            with self.lock:
                need(not self.halted,'HTTP403_GLOBAL_STOP')
                self.http_attempts+=1;serial=self.http_attempts
            begin=self.clock()
            try:cap=self.getter(path,dict(query),timeout=timeout)
            except OSError as error:
                cap=dict(endpoint=path,params=dict(query),method='GET',signed=False,request_ms=begin,
                    receive_ms=self.clock(),error_type=type(error).__name__,body={})
            last=cap;body=cap.get('body')
            failed=(cap.get('http_status')!=200 or cap.get('error_type') or not isinstance(body,dict)
                or type(body.get('retCode')) is not int or body['retCode']!=0)
            if not failed:return cap
            if cap.get('http_status')==403:
                with self.lock:self.halted=True
            limited=self.rate_limited(cap,path,query)
            if limited:self.defer(cap) # stop other workers before fsync latency
            # Caller supplies fsynced atomic publication. Failure must propagate
            # before a second network attempt is even considered.
            self.persist(dict(schema='PUMP4_FAILED_PUBLIC_HTTP_ATTEMPT_V1',request_serial=serial,
                endpoint=path,params=query,attempt_index=attempt,capture=cap,broker_writes=0))
            if not limited:return cap
        return last
