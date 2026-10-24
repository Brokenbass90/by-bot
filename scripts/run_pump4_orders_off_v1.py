#!/usr/bin/env python3
"""Explicit DATA-only server process. No LIVE/apply/GO or POST capability.

Uses the known pinned KITY credential binding only for existing GET transport;
never constructs its supervisor, writer, private feed or journal. The financial
owner stays selected and untouched. Bootstrap is not a prospective entry.
"""
import argparse,concurrent.futures as cf,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from research_lab.kity_micro_physical_owner_v1 import load_bound_credentials,publish
from research_lab.kity_micro_transport_v1 import BybitReadTransport,wire_get
from research_lab.pump4_bybit_sources_v1 import public_get,checked,universe
from research_lab.pump4_server_cycle_v1 import analyze
from scripts.capture_pump4_sources_v1 import capture


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',action='store_true')
    p.add_argument('--root',type=Path);p.add_argument('--owner-config',type=Path);p.add_argument('--owner-config-sha256');a=p.parse_args(argv)
    if not a.capture:print(json.dumps(dict(status='ORDERS_OFF_NO_REQUESTS',broker_writes=0)));return 0
    if not a.root or not a.owner_config or not a.owner_config_sha256:raise ValueError('EXPLICIT_PINNED_CAPTURE_ARGUMENTS_REQUIRED')
    root=a.root.absolute()
    if not root.is_relative_to(ROOT/'.private') or root.exists() or any(x.is_symlink() for x in (root,*root.parents)):raise ValueError('EXCLUSIVE_PRIVATE_DATA_ROOT_REQUIRED')
    raw=a.owner_config.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.owner_config_sha256:raise ValueError('ORIGINAL_OWNER_CONFIG_DRIFT')
    config=json.loads(raw)
    for name,pin in config['source_files'].items():
        if hashlib.sha256((Path(config['app_root'])/name).read_bytes()).hexdigest()!=pin:raise ValueError('ORIGINAL_OWNER_SOURCE_DRIFT')
    root.mkdir(mode=0o700,parents=True);public_root=root/'public';capture(public_root)
    # Renew filters at the end of the large historical H1 bootstrap. Old public
    # metadata does not become fresh merely because private GET just completed.
    pages=[];cursor=''
    for _ in range(8):
        c=public_get('/v5/market/instruments-info',dict(category='linear',limit=1000,**({'cursor':cursor} if cursor else {})))
        r=checked(c,'/v5/market/instruments-info',now_ms=time.time_ns()//1000000,private=False);pages.append(c);cursor=r.get('nextPageCursor','')
        if not cursor:break
    else:raise ValueError('INSTRUMENT_PAGE_BOUND')
    key,secret=load_bound_credentials(config);routes=[]
    def get_wire(method,url,headers,data,timeout):
        if method!='GET' or data is not None:raise ValueError('GET_ONLY_SERVER_PROCESS')
        routes.append(url.split('?',1)[0]);return wire_get(method,url,headers,data,6)
    reader=BybitReadTransport(key,secret,wire=get_wire,symbols=universe());start=time.time_ns()//1000000;begin=start-86400000
    specs=[('account','/v5/account/info',{},False),('wallet','/v5/account/wallet-balance',dict(accountType='UNIFIED'),False),('fees','/v5/account/fee-rate',dict(category='linear'),False),('positions','/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'),True),('orders','/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'),True),('quote','/v5/market/tickers',dict(category='linear'),False)]
    for name,path,limit,extra in [('history','/v5/order/history','50',{}),('executions','/v5/execution/list','100',{}),('transactions','/v5/account/transaction-log','50',dict(accountType='UNIFIED',currency='USDT'))]:specs.append((name,path,dict(category='linear',startTime=str(begin),endTime=str(start),limit=limit,**extra),True))
    def read(spec):
        name,path,params,paged=spec;cap=reader.pages(path,params) if paged else reader.get(path,params)
        for row in cap.get('pages',[cap]):
            reader.result(row)
            if row['signed']:row['account_fingerprint']=reader.account_fingerprint
        return name,cap
    with cf.ThreadPoolExecutor(max_workers=9) as pool:caps=dict(pool.map(read,specs))
    history={k:caps.pop(k) for k in ('history','executions','transactions')}
    bundle=dict(schema='PUMP4_ACCOUNT_GET_CAPTURE_V1',started_ms=start,completed_ms=time.time_ns()//1000000,account_fingerprint=reader.account_fingerprint,captures=caps,history_start_ms=begin,history_end_ms=start,history_windows=[dict(start_ms=begin,end_ms=start,groups=history)])
    public=dict(instruments=dict(complete=True,pages=pages),quote=caps['quote']);publish(root/'account.json',bundle);publish(root/'public-fresh.json',public)
    lock=Path(config['custody_runtime_root'])/'account.lock';st=lock.stat()
    import subprocess
    state=subprocess.run(['systemctl','show',config['unit'],'--property=MainPID,ActiveState','--no-pager'],capture_output=True,text=True,timeout=3,check=True).stdout
    fields=dict(x.split('=',1) for x in state.splitlines() if '=' in x)
    held=any(x.split()[5].rsplit(':',1)[-1]==str(st.st_ino) for x in Path('/proc/locks').read_text().splitlines())
    physical=dict(owner_active=fields['ActiveState']=='active',lock_held=held,original_lock_inode=st.st_ino,expected_inode=config['account_lock_inode'],unit=config['unit'],pid=fields['MainPID'])
    if st.st_ino!=config['account_lock_inode']:raise ValueError('ORIGINAL_ACCOUNT_LOCK_CHANGED')
    policy=dict(allocation_usdt='50',gross_usdt='30',reserve_usdt='20',risk_usdt='1',slippage_bps='10',day_loss_usdt='2',week_loss_usdt='3',drawdown_usdt='6',max_entries=1,max_positions=1)
    def symbol_get(symbol):
        _,cap=read(('symbol_position','/v5/position/list',dict(category='linear',symbol=symbol),False))
        bundle.setdefault('symbol_positions',{})[symbol]=cap
        return cap,time.time_ns()//1000000
    result=analyze(root/'intake',public_root,bundle,public,policy,fingerprint=reader.account_fingerprint,now_ms=bundle['completed_ms']+1,physical=physical,read_symbol=symbol_get)
    publish(root/'account-with-symbols.json',bundle)
    # Same raw captures and cursor in the same server process; replay at their
    # actual cutoff proves restart/idempotence, never current-time freshness.
    replay=analyze(root/'intake',public_root,bundle,public,policy,fingerprint=reader.account_fingerprint,now_ms=bundle['completed_ms']+1,physical=physical,diagnostics=False)
    result.update(restart_replay_duplicates=replay['duplicate_decisions'],authenticated_get_requests=len(routes),policy='PROPOSAL_ONLY_NOT_OWNER_APPROVED')
    publish(root/'receipt.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'},sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
