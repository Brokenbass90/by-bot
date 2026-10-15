"""Executed after pinned GET transport source via SSH stdin; no remote writes."""
import concurrent.futures
import subprocess


def capture_main():
    started=time.time_ns()//1_000_000
    key,secret=existing_selected_credentials()
    reader=BybitReadTransport(key,secret)
    tasks=[('identity','/v5/user/query-api',{}),('account','/v5/account/info',{}),
           ('wallet','/v5/account/wallet-balance',{'accountType':'UNIFIED'}),
           ('server_clock','/v5/market/time',{})]
    for s in SYMBOLS:
        tasks.extend([(f'instrument:{s}','/v5/market/instruments-info',dict(category='linear',symbol=s)),
                      (f'ticker:{s}','/v5/market/tickers',dict(category='linear',symbol=s)),
                      (f'fee:{s}','/v5/account/fee-rate',dict(category='linear',symbol=s)),
                      (f'position:{s}','/v5/position/list',dict(category='linear',symbol=s))])
    values={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs={pool.submit(reader.get,path,params):name for name,path,params in tasks}
        jobs[pool.submit(reader.pages,'/v5/position/list',dict(category='linear',settleCoin='USDT',limit='200'))]='all_positions'
        jobs[pool.submit(reader.pages,'/v5/order/realtime',dict(category='linear',settleCoin='USDT',openOnly='0',limit='50'))]='all_open_orders'
        # Actual authenticated endpoint connectivity, not adoption of these rows.
        jobs[pool.submit(reader.pages,'/v5/order/history',dict(category='linear',symbol='LTCUSDT',limit='1'))]='history_connectivity'
        jobs[pool.submit(reader.pages,'/v5/execution/list',dict(category='linear',symbol='LTCUSDT',limit='1'))]='execution_connectivity'
        jobs[pool.submit(reader.pages,'/v5/account/transaction-log',dict(accountType='UNIFIED',category='linear',currency='USDT',limit='50',startTime=str(started-3600000),endTime=str(started)))]='transaction_connectivity'
        for job in concurrent.futures.as_completed(jobs):values[jobs[job]]=job.result()
    # Book group is last; do not spend its freshness on account/source discovery.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        jobs={pool.submit(reader.get,'/v5/market/orderbook',dict(category='linear',symbol=s,limit='50')):s for s in SYMBOLS}
        for job in concurrent.futures.as_completed(jobs):values['book:'+jobs[job]]=job.result()
    observed_end=time.time_ns()//1_000_000
    units={}
    for unit in ('bybot.service','trading-journal-web.service','att1-lifecycle-zero-risk-v2.service'):
        raw=subprocess.run(['systemctl','show',unit,'--no-pager',
          '--property=Id,ActiveState,SubState,MainPID,NRestarts,Restart,FragmentPath'],
          capture_output=True,text=True,timeout=8,check=True).stdout
        units[unit]=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    web_source=[]
    proc=Path('/proc/1623208')
    if proc.exists():
        args=(proc/'cmdline').read_bytes().decode().split('\0')
        for item in args:
            if item.endswith('.py'):
                p=Path(item);p=p if p.is_absolute() else (proc/'cwd').resolve()/p
                if p.is_file() and p.stat().st_size<3000000:
                    raw=p.read_bytes()
                    web_source.append(dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),
                      bybit_write_tokens=[word for word in ('/v5/order/create','/v5/order/cancel','place_market','BYBIT_API_KEY') if word.encode() in raw]))
    out=dict(schema='kity_execution_micro_get_capture_v2',purpose='EXECUTION_ONLY_NOT_RESEARCH',
        started_ms=started,completed_ms=observed_end,base=BASE,symbols=SYMBOLS,
        selected_credential_sha256=reader.account_fingerprint,
        credential_source='/root/by-bot/.env matches original production PID1648585',
        active_source_pid=1648585,captures=values,services=units,web_source=web_source,
        broker_writes=0,remote_writes=0,process_changes=0)
    print(json.dumps(out,allow_nan=False))


capture_main()
